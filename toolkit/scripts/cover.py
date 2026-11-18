"""Social cover (3:4, 1080x1440: RedNote; also Instagram feed 4:5 crops): big outlined headline on top, terminal-style lines at the bottom,
your face clear in the middle. Text and photo come from [cover] in the video's video.toml.

Usage: python -I cover.py <video folder> <version> [frame seconds] [output name] [head style]
cover.background (a photo) replaces the video frame behind the text; you then appear as cover.head:
circle (big, centre), circle_right (smaller, lower right), card (portrait card, right), split (you in the lower part)
or after_text (a small circle after the bottom lines).
With a frame time it uses the sharpest frame within 0.4 s of it (for offering frame options).
The frame is taken from work/edit/<version>/pass1.mov (the edit before overlays) and kept as
work/cover/frame.png, which is reused when pass1.mov has been cleaned up.
"""
import pathlib, re, subprocess, sys, tomllib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import FFMPEG, LIBRARY, MAIN as _MAIN, blurred, font_file, rgb  # noqa: E402

W, H = 1080, 1440
INK, PANEL, LINE = rgb("ink"), rgb("panel"), rgb("line")
WHITE, ACCENT, HIGHLIGHT = rgb("text"), rgb("accent"), rgb("highlight")
MAIN = font_file(_MAIN)

VID = pathlib.Path(sys.argv[1]).resolve()
VERSION = sys.argv[2]
CFG = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))["cover"]
TAG = CFG["tag"]


def asset(name):
    for base in (VID, LIBRARY):
        if (base / name).exists():
            return base / name
    raise FileNotFoundError(name)


still = VID / "work" / "cover" / "frame.png"
still.parent.mkdir(parents=True, exist_ok=True)
edit = VID / "work" / "edit" / VERSION / "pass1.mov"
FRAME_T = float(sys.argv[3]) if len(sys.argv) > 3 else CFG.get("frame", 0.0)
if len(sys.argv) <= 3 and "frame_footage" in CFG:  # a time in the original footage (what you see when you screenshot it)
    import json
    cut = json.loads((VID / "work" / "edit" / VERSION / "cutlist.json").read_text())
    full = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))
    audio_start = json.loads((VID / "work" / "media.json").read_text())["audio_start"]
    src, acc = CFG["frame_footage"] - audio_start, 0.0
    for a, b in cut["intervals"]:
        if a <= src <= b:
            FRAME_T = (acc + src - a) / full.get("speed", 1.2)
            break
        acc += b - a
    else:
        sys.exit(f"{CFG['frame_footage']}s in the footage was cut from the edit; pick a moment that's kept")
NAME = sys.argv[4] if len(sys.argv) > 4 else "cover.png"
PHOTO = CFG.get("photo")  # a photo you took (already 3:4) instead of a frame from the edit
if edit.exists() and not PHOTO:  # sharpest frame near the chosen time (sharpness of the face area)
    import numpy as np
    tmp = still.parent / "_near"
    tmp.mkdir(exist_ok=True)
    for f in tmp.glob("*.png"):
        f.unlink()
    window = 0.0 if CFG.get("frame_exact") else 0.4  # frame_exact: exactly the frame you picked
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(max(0.0, FRAME_T - window)), "-i", str(edit),
                    *(["-frames:v", "1"] if window == 0 else ["-t", "0.8", "-vf", "fps=15"]), str(tmp / "%02d.png")], check=True)
    best = max(sorted(tmp.glob("*.png")), key=lambda f: np.asarray(
        Image.open(f).convert("L").crop((250, 450, 850, 1500)).filter(ImageFilter.FIND_EDGES), dtype=float).var())
    im = Image.open(best)
    if im.size != (1080, 1920):  # same 1080x1920 as the edit
        k = max(1080 / im.width, 1920 / im.height)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im = im.crop(((im.width - 1080) // 2, (im.height - 1920) // 2, (im.width - 1080) // 2 + 1080, (im.height - 1920) // 2 + 1920))
    im.save(still)
if PHOTO:  # scale and crop the photo to the 1080x1440 cover
    _p = Image.open(asset(PHOTO)).convert("RGB")
    _k = max(1080 / _p.width, 1440 / _p.height)
    _p = _p.resize((round(_p.width * _k), round(_p.height * _k)), Image.LANCZOS)
    frame = _p.crop(((_p.width - 1080) // 2, (_p.height - 1440) // 2, (_p.width - 1080) // 2 + 1080, (_p.height - 1440) // 2 + 1440))
else:
    frame = Image.open(still).convert("RGB")
out = VID / "exports" / VERSION / "cover"
out.mkdir(parents=True, exist_ok=True)
_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = ImageFont.truetype(str(MAIN), size)
    return _fonts[size]


def width(runs, track=0):
    """runs: (text, colour, size); track adds that many px after every character."""
    return sum(font(s).getlength(t) + track * len(t) for t, _, s in runs)


def line(img, x, base, runs, stroke=0, shadow=False, bold=2, track=0):
    """Runs on one baseline. Poster style: thick ink outline, soft shadow, slightly emboldened fill.
    Keep bold at 0 for small text: it fills the gaps inside dense CJK characters."""
    if x == "c":
        x = (W - width(runs, track)) / 2
    chars = [(ch, colour, s) for t, colour, s in runs for ch in t]
    if shadow:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d, cx = ImageDraw.Draw(layer), x
        for ch, _, s in chars:
            d.text((cx + 6, base + 8), ch, font=font(s), anchor="ls", fill=(0, 0, 0, 200), stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
            cx += font(s).getlength(ch) + track
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(8)))
    d, cx = ImageDraw.Draw(img), x
    for ch, colour, s in chars:
        if stroke:
            d.text((cx, base), ch, font=font(s), anchor="ls", fill=INK, stroke_width=stroke, stroke_fill=INK)
        d.text((cx, base), ch, font=font(s), anchor="ls", fill=colour, stroke_width=bold, stroke_fill=colour)
        cx += font(s).getlength(ch) + track
    return x, cx - track


def block(img, x0, y0, x1, y1, fill, r=16, alpha=255, outline=None):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0, x1, y1], r, fill=(*fill, alpha) if fill else None,
                                            outline=outline, width=3 if outline else 0)
    img.alpha_composite(layer)


def fade(img, y0, y1, a0, a1, colour=INK):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(y0, y1):
        d.line([(0, y), (W, y)], fill=(*colour, round(a0 + (a1 - a0) * (y - y0) / max(1, y1 - y0 - 1))))
    img.alpha_composite(layer)


def grid(img, y0, y1, step=60, colour=(*LINE, 70)):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, W, step):
        d.line([(x, y0), (x, y1)], fill=colour)
    for y in range(y0 - y0 % step, y1, step):
        d.line([(0, y), (W, y)], fill=colour)
    img.alpha_composite(layer)


def tag(img, y, centre=True, x=60, filled=False):
    size = 54
    w = width([(TAG, ACCENT, size)], track=4) + 60
    x = (W - w) / 2 if centre else x
    block(img, x, y, x + w, y + 84, ACCENT if filled else None, r=14, outline=None if filled else ACCENT, alpha=255)
    if not filled:  # dark glass behind the outline so the accent-coloured text reads on a busy background
        block(img, x + 2, y + 2, x + w - 2, y + 82, PANEL, r=13, alpha=170)
    line(img, x + 30, y + 64, [(TAG, INK if filled else ACCENT, size)], bold=0, track=4)


HEAD_STYLE = sys.argv[5] if len(sys.argv) > 5 else CFG.get("head", "circle")
HEAD_TOP = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8")).get("head_top", 540)
if PHOTO:  # where your head is in the photo (cover coordinates)
    HEAD_TOP = CFG.get("photo_head_top", HEAD_TOP)
FACE_X = CFG.get("face_x", frame.width // 2)  # centre of your face, left to right


def cover_fill(im):
    """Scale and crop a picture to fill the 3:4 cover."""
    k = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    return im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))


def face(size, side=760):
    """A square around your face from the chosen frame (a smaller side = a tighter crop)."""
    x0, y0 = min(max(0, FACE_X - side // 2), frame.width - side), max(0, HEAD_TOP + 310 - side // 2)  # centred on your face
    return frame.crop((x0, y0, x0 + side, y0 + side)).resize((size, size), Image.LANCZOS).convert("RGBA")


def ringed_circle(size, ring=10, side=760):
    out = Image.new("RGBA", (size + 2 * ring, size + 2 * ring), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse([0, 0, out.width - 1, out.height - 1], fill=ACCENT)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out.paste(face(size, side), (ring, ring), mask)
    return out


def base():
    """The video frame full-bleed, face in the middle third; or a photo with you added in (cover.background)."""
    if not CFG.get("background"):
        return (frame if frame.height == H else frame.crop((0, 80, 1080, 1520))).convert("RGBA")
    src = asset(CFG["background"])
    if src.suffix.lower() in (".heic", ".heif") or CFG.get("background_rotate"):
        jpg = still.parent / "background.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", *(["-r", str(CFG["background_rotate"])] if CFG.get("background_rotate") else []),
                        str(src), "--out", str(jpg)], check=True, capture_output=True)
        src = jpg
    if CFG.get("background_blur"):  # hide private details on the photo
        src = blurred(src, CFG["background_blur"], still.parent / "background_blur.jpg")
    img = cover_fill(Image.open(src).convert("RGB")).convert("RGBA")
    if HEAD_STYLE == "split":  # you in the lower part, fading up into the photo
        me = frame.crop((0, HEAD_TOP - 160, 1080, HEAD_TOP - 160 + 820)).convert("RGBA")
        alpha = Image.linear_gradient("L").resize((W, 320))  # 0 at top -> 255 at bottom
        mask = Image.new("L", me.size, 255)
        mask.paste(alpha, (0, 0))
        me.putalpha(mask)
        img.alpha_composite(me, (0, H - me.height))
    elif HEAD_STYLE == "circle":
        c = ringed_circle(560)
        img.alpha_composite(c, ((W - c.width) // 2, 470))
    elif HEAD_STYLE == "circle_top_left":  # small circle in an empty top-left corner (e.g. of a chart)
        c = ringed_circle(300, ring=8, side=700)
        img.alpha_composite(c, tuple(CFG.get("head_xy", [60, 480])))
    elif HEAD_STYLE == "circle_right":
        c = ringed_circle(440)
        img.alpha_composite(c, (W - c.width - 40, 1150 - c.height))
    elif HEAD_STYLE == "card":
        cw, ch = 470, 600
        side = 760
        x0, y0 = (frame.width - side) // 2, HEAD_TOP - 70
        me = frame.crop((x0, y0, x0 + side, y0 + round(side * ch / cw))).resize((cw, ch), Image.LANCZOS)
        cardimg = Image.new("RGBA", (cw + 20, ch + 20), (0, 0, 0, 0))
        ImageDraw.Draw(cardimg).rounded_rectangle([0, 0, cw + 19, ch + 19], 34, fill=ACCENT)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], 26, fill=255)
        cardimg.paste(me, (10, 10), mask)
        cardimg = cardimg.rotate(-4, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(cardimg, (W - cardimg.width - 30, 1190 - cardimg.height))
    return img


def avatar(size):
    """Round photo with an accent-coloured ring (cover.avatar, cropped to cover.avatar_crop)."""
    src = Image.open(asset(CFG["avatar"])).convert("RGBA")
    src = src.crop(tuple(CFG["avatar_crop"])) if "avatar_crop" in CFG else src
    src = src.resize((size, size), Image.LANCZOS)
    ring = Image.new("RGBA", (size + 16, size + 16), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, size + 15, size + 15], fill=ACCENT)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    ring.paste(src, (8, 8), mask)
    return ring


def runs(text, size, key_size=None, prompt=False):
    """'Help kids [find direction]' -> runs: [..] highlight colour, {..} big accent colour; optional '> ' prompt."""
    out = [("> ", ACCENT, round(size * 0.88))] if prompt else []
    for part in re.split(r"(\[[^]]*\]|\{[^}]*\})", text):
        if part.startswith("["):
            out.append((part[1:-1], HIGHLIGHT, size))
        elif part.startswith("{"):
            out.append((part[1:-1], ACCENT, key_size or round(size * 1.53)))
        elif part:
            out.append((part, WHITE, size))
    return out


from brandkit import missing_glyphs  # noqa: E402
for key in ("tag", "headline", "line1", "line2"):
    if missing_glyphs(CFG.get(key, "")):
        print(f"WARNING: cover {key} 「{CFG[key]}」 has characters the font can't draw: {missing_glyphs(CFG[key])}")
img = base()
fade(img, 0, 470, 250, 0)
fade(img, 1000, H, 0, 175)  # light fade, not a solid band: the photo still shows through
tag(img, 46)
# headline: "|" breaks it onto two lines; each line shrinks if it's wider than the cover
HEAD_LINES = CFG["headline"].split("|")
hsize = CFG.get("headline_size", 150 if len(HEAD_LINES) == 1 else 128)
hy = 300
# headline weight: headline_bold (fill thickening, 2 = old look), headline_stroke (ink outline, 10 = old),
# headline_track (px between characters) -- thinner settings keep dense characters readable
HB, HS, HT = CFG.get("headline_bold", 2), CFG.get("headline_stroke", 10), CFG.get("headline_track", 0)
for k, hl in enumerate(HEAD_LINES):
    size = hsize
    while width(runs(hl, size), HT) > W - 70 and size > 60:
        size -= 4
    line(img, "c", hy, runs(hl, size), stroke=HS, shadow=True, bold=HB, track=HT)
    hy += round(size * 1.12)
if len(HEAD_LINES) > 1 and hy - round(hsize * 1.12) > 470:
    print(f"WARNING: the two-line headline reaches y={hy - round(hsize * 1.12)}; check it doesn't sit on your face")


# the bottom lines centred in one column, the round photo after it; the whole group centred
def fit(text, room, size=86):
    """A bottom line at the usual size, or smaller if it's wider than the room it has."""
    while width(runs(text, size, prompt=True), 3) + 52 > room and size > 44:
        size -= 2
    return runs(text, size, prompt=True)


if CFG.get("background") and HEAD_STYLE == "after_text":
    av = ringed_circle(210, ring=8, side=700)  # you, in a circle after the bottom lines (tighter on your face)
elif CFG.get("background") and HEAD_STYLE == "after_text_portrait":
    pw, phh, side = 230, 320, 640  # you, in a portrait rectangle after the bottom lines (taller than the text)
    x0 = min(max(0, FACE_X - side // 2), frame.width - side)
    y0 = HEAD_TOP - 40
    me = frame.crop((x0, y0, x0 + side, y0 + round(side * phh / pw))).resize((pw, phh), Image.LANCZOS)
    av = Image.new("RGBA", (pw + 16, phh + 16), (0, 0, 0, 0))
    ImageDraw.Draw(av).rounded_rectangle([0, 0, pw + 15, phh + 15], 24, fill=ACCENT)
    m = Image.new("L", (pw, phh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, pw - 1, phh - 1], 18, fill=255)
    av.paste(me, (8, 8), m)
else:
    av = avatar(170) if CFG.get("avatar") else None
room = W - 80 - (av.width + 40 if av else 0)  # the lines share the width with the picture after them
LINE_SIZE = CFG.get("line_size", 86)  # bottom lines (e.g. 104 for bigger lines)
l1, l2 = fit(CFG["line1"], room, LINE_SIZE), fit(CFG["line2"], room, LINE_SIZE)
w1, w2 = width(l1, 3), width(l2, 3) + 52  # line 2 includes the cursor
col = max(w1, w2)
gx = (W - (col + (40 + av.width if av else 0))) / 2
LINE_GAP = CFG.get("line_spacing", 1.45)  # baseline to baseline, times the line size (1.23 looks tight)
line(img, gx + (col - w1) / 2, 1388 - round(LINE_SIZE * LINE_GAP), l1, stroke=3, shadow=True, bold=0, track=3)
_, x2 = line(img, gx + (col - w2) / 2, 1388, l2, stroke=3, shadow=True, bold=0, track=3)
block(img, x2 + 12, 1376, x2 + 52, 1386, ACCENT, r=2)  # cursor
if av:
    img.alpha_composite(av, (round(gx + col + 40), 1402 - av.height))
target = out / NAME  # never write over an earlier cover: cover.png, cover-2.png, cover-3.png...
k = 2
while target.exists():
    target = out / f"{pathlib.Path(NAME).stem}-{k}{pathlib.Path(NAME).suffix}"
    k += 1
img.convert("RGB").save(target)
print("wrote", target)
