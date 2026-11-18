"""Stage 3 key frames: stills of the planned edit on the real footage, before the full render.

Usage: python -I keyframes.py <video folder> <version> [seconds ...]
Run build_edit.py <video folder> <version> --dry first (it writes the cut list, subtitles and overlay positions).
With no seconds given it picks the key moments: opening, a two-line subtitle during the bio card, each photo,
the first sticker, all viewpoints showing, and the end card. Writes work/keyframes/<version>/ and a contact sheet.
"""
import json, pathlib, re, subprocess, sys, tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import FFMPEG, FONTS, LATIN, H, W, font_file, rgb  # noqa: E402

VID = pathlib.Path(sys.argv[1]).resolve()
VERSION = sys.argv[2]
CFG = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))
EDIT = VID / "work" / "edit" / VERSION
OUT = VID / "work" / "keyframes" / VERSION
OUT.mkdir(parents=True, exist_ok=True)
SPEED = CFG.get("speed", 1.2)
media = json.loads((VID / "work" / "media.json").read_text())
SRC, AUDIO_START = VID / "footage" / media["source"], media["audio_start"]
cut = json.loads((EDIT / "cutlist.json").read_text())
overlays = json.loads((EDIT / "overlays.json").read_text())
ASS = EDIT / "subtitles.ass"


def to_source(t_out):
    """Output time -> time in the footage (picture), through the cut list."""
    acc = 0.0
    for a, b in cut["intervals"]:
        if t_out * SPEED <= acc + (b - a):
            return a + (t_out * SPEED - acc) + AUDIO_START
        acc += b - a
    a, b = cut["intervals"][-1]
    return b + AUDIO_START


def srt_cards():
    srt = (EDIT / "subtitles.srt").read_text(encoding="utf-8")
    for block in srt.strip().split("\n\n"):
        lines = block.split("\n")
        h, m, s = lines[1].split(" --> ")[0].replace(",", ".").split(":")
        yield int(h) * 3600 + int(m) * 60 + float(s), lines[2:]


def ass_time(pattern):
    m = re.search(r"Dialogue: \d+,(\d+):(\d+):([\d.]+),[^\n]*" + re.escape(pattern), ASS.read_text(encoding="utf-8"))
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def moments():
    shots = [("opening", 1.5)]
    bio_end = 15
    two = next((t for t, lines in srt_cards() if len(lines) > 1 and 1 < t < bio_end), None)
    if two:
        shots.append(("two-line subtitle during bio", two + 0.4))
    for i, o in enumerate(o for o in overlays if o["kind"] in ("glitch", "full", "fullvideo")):
        shots.append((f"photo {i + 1}", (o["t0"] + o["t1"]) / 2))
    first_sticker = next((o for o in overlays if o["kind"] == "pop"), None)
    if first_sticker:
        shots.append(("sticker", first_sticker["t0"] + 1.0))
    n = len(CFG.get("points", []))
    if n:
        t = ass_time(f"{n:02d}  ")
        if t:
            shots.append(("all viewpoints", t + 1.5))
    shots.append(("end card", cut["total"] - 0.5))
    return shots


def still(name, t, k):
    out = OUT / f"{k:02d}.png"
    if t >= cut["speech_end"]:  # end card: the last shot, blurred and dimmed like the real one
        src_t = to_source(cut["speech_end"] - 0.05)
        pre = "gblur=sigma=18,colorchannelmixer=rr=0.35:gg=0.35:bb=0.35,"
    else:
        src_t, pre = to_source(t), ""
    inputs = ["-ss", f"{src_t:.3f}", "-i", str(SRC)]
    active = [o for o in overlays if o["t0"] <= t <= o["t1"]]
    full = any(o["kind"] == "full" for o in active) and json.loads((EDIT / "pip.json").read_text()).get("on", False)
    graph = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,{pre}setpts=PTS-STARTPTS" + (",split[b][ps]" if full else "[b]")
    last = "[b]"
    for j, o in enumerate(active):
        inputs += (["-ss", f"{t - o['t0']:.3f}"] if o["kind"] == "fullvideo" else []) + ["-i", o["path"]]
        # every stream starts at 0 here (a video b-roll is already seeked to the shot); the shot's time is put back
        # just before the subtitles, which need it
        graph += f";[{j + 1}:v]setpts=PTS-STARTPTS,format=rgba[i{j}];{last}[i{j}]overlay={o['x']}:{o['y']}[o{j}]"
        last = f"[o{j}]"
    if full:  # the circle of you over a full-screen photo
        pip = json.loads((EDIT / "pip.json").read_text())
        n = len(active) + 1
        inputs += ["-i", pip["mask"], "-i", pip["ring"]]
        x, y, size = pip["crop"]
        d, (px, py) = pip["d"], pip["pos"]
        graph += (f";[ps]crop={size}:{size}:{x}:{y},scale={d}:{d},format=rgba[pc];[{n}:v]format=gray,scale={d}:{d}[pm];"
                  f"[pc][pm]alphamerge[pip];{last}[pip]overlay={px}:{py}[pp];[pp][{n + 1}:v]overlay={px - 6}:{py - 6}[pr]")
        last = "[pr]"
    graph += f";{last}setpts=PTS+{t:.3f}/TB,ass={ASS}:fontsdir={FONTS}[v]"
    subprocess.run([FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", str(out)], check=True)
    return out


shots = [(f"{float(t):.1f}s", float(t)) for t in sys.argv[3:]] or moments()
files = []
for k, (name, t) in enumerate(shots, 1):
    files.append(still(name, t, k))
    print(f"{k:2d}. {int(t // 60)}:{t % 60:04.1f}  {name}")

# contact sheet: numbered, half size
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
font = ImageFont.truetype(str(font_file(LATIN)), 30)
cols = 4
tw, th = W // 2, H // 2
sheet = Image.new("RGB", (cols * (tw + 16) + 16, ((len(files) + cols - 1) // cols) * (th + 60) + 16), rgb("ink"))
d = ImageDraw.Draw(sheet)
for k, (f, (name, t)) in enumerate(zip(files, shots)):
    x, y = 16 + (k % cols) * (tw + 16), 16 + (k // cols) * (th + 60)
    sheet.paste(Image.open(f).convert("RGB").resize((tw, th)), (x, y))
    d.text((x, y + th + 10), f"{k + 1}. {int(t // 60)}:{t % 60:04.1f} {name}", font=font, fill=rgb("accent"))
sheet.save(OUT / "sheet.jpg", quality=88)
print("wrote", OUT / "sheet.jpg")
