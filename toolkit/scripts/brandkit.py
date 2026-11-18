"""Shared styling for ASS subtitles and overlays. Colours and fonts come from library/brand/theme.toml."""
import io, os, pathlib, re, shutil, subprocess, tomllib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLKIT = ROOT / "toolkit"
LIBRARY = ROOT / "library"     # theme, profile, language packs, music, sound effects, stickers
FONTS = TOOLKIT / "fonts"      # the font files named in theme.toml (libass looks for fonts here)
# ffmpeg needs libass (subtitles), rubberband (speed-up without pitch change) and arnndn (noise removal).
# Homebrew's ffmpeg-full has all three; set FFMPEG_DIR to use another build.
_FF_DIR = os.environ.get("FFMPEG_DIR") or ("/opt/homebrew/opt/ffmpeg-full/bin" if pathlib.Path("/opt/homebrew/opt/ffmpeg-full/bin").exists() else None)
FFMPEG = str(pathlib.Path(_FF_DIR) / "ffmpeg") if _FF_DIR else (shutil.which("ffmpeg") or "ffmpeg")
FFPROBE = str(pathlib.Path(_FF_DIR) / "ffprobe") if _FF_DIR else (shutil.which("ffprobe") or "ffprobe")


def language(cfg):
    """The language pack for a video: library/language/<code>.toml, chosen by `language = "..."` in video.toml
    (default "zh"). It holds the Whisper settings, filler words, line-break rules and the end-card button words."""
    code = cfg.get("language", "zh")
    return tomllib.loads((LIBRARY / "language" / f"{code}.toml").read_text(encoding="utf-8"))


def profile():
    """The creator's profile: name, handle and bio card text (library/brand/profile.toml)."""
    return tomllib.loads((LIBRARY / "brand" / "profile.toml").read_text(encoding="utf-8"))

W, H = 1080, 1920

# the visual style: library/brand/theme.toml, or another theme file named by the THEME environment variable
THEME = tomllib.loads(pathlib.Path(os.environ.get("THEME") or LIBRARY / "brand" / "theme.toml").read_text(encoding="utf-8"))


def hex_colour(name):
    """A theme colour as #RRGGBB."""
    return THEME["colours"][name]


def rgb(name):
    """A theme colour as an (r, g, b) tuple, for Pillow."""
    h = hex_colour(name)
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _font_spec(key):
    spec = THEME["fonts"][key]
    path = pathlib.Path(spec["file"])
    return spec["name"], path if path.is_absolute() else FONTS / path


def font_file(font):
    """A font's file path (font = (family name, path)), with a clear message if the file hasn't been added yet."""
    path = pathlib.Path(font[1])
    if not path.exists():
        raise SystemExit(f"Font file not found: {path}\n"
                         "Add a font to toolkit/fonts/ and name it in library/brand/theme.toml (see README, Quick start).")
    return path


MAIN = _font_spec("main")    # subtitles, headings, covers (must cover the video's language)
LATIN = _font_spec("latin")  # Latin-letter labels and numbers


def ass_colour(hex_rgb, alpha=0):
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H{alpha:02X}{b}{g}{r}&".upper()


WHITE = ass_colour(hex_colour("text"))
ACCENT = ass_colour(hex_colour("accent"))
HIGHLIGHT = ass_colour(hex_colour("highlight"))
FILL = ass_colour(hex_colour("fill"))
INK = ass_colour(hex_colour("ink"))
PANEL = ass_colour(hex_colour("panel"), 0x1A)  # ~90% opaque

# top overlays stay in this band: below the app's top bar, above the head (about y=430)
SAFE_TOP, SAFE_BOTTOM = 150, 410

_fonts = {}


def text_width(text, font, size):
    """Width of text as libass draws it (libass sizes fonts by ascent + descent)."""
    path = font[1]
    if path not in _fonts:
        f = ImageFont.truetype(str(font_file(font)), 1000)
        asc, desc = f.getmetrics()
        _fonts[path] = (f, asc + desc)
    f, height = _fonts[path]
    return f.getlength(text) * size / height


def missing_glyphs(text, font=None):
    """Characters the font can't draw (they would show as boxes)."""
    f = ImageFont.truetype(str(font_file(font or MAIN)), 40)

    def shape(ch):
        im = Image.new("L", (60, 60))
        ImageDraw.Draw(im).text((5, 0), ch, font=f, fill=255)
        return im.tobytes()
    tofu = shape("\uffff")
    return sorted({ch for ch in text if not ch.isspace() and shape(ch) == tofu})


def runs_width(runs):
    return sum(text_width(t, font, size) for t, _, font, size in runs)


def ts(seconds):
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def dialogue(layer, start, end, text):
    return f"Dialogue: {layer},{ts(start)},{ts(end)},Default,,0,0,0,,{text}"


def _rect_path(x, y, w, h, r):
    x2, y2 = x + w, y + h
    return (f"m {x+r} {y} l {x2-r} {y} b {x2} {y} {x2} {y} {x2} {y+r} "
            f"l {x2} {y2-r} b {x2} {y2} {x2} {y2} {x2-r} {y2} "
            f"l {x+r} {y2} b {x} {y2} {x} {y2} {x} {y2-r} "
            f"l {x} {y+r} b {x} {y} {x} {y} {x+r} {y}")


def rounded_rect(x, y, w, h, r, colour, start, end, layer=0, anim=""):
    return dialogue(layer, start, end,
                    rf"{{\an7\pos(0,0){anim}\bord0\shad0\1c{colour}\1a&H{colour[2:4]}&\p1}}{_rect_path(x, y, w, h, r)}")


def outline_rect(x, y, w, h, r, colour, thickness, start, end, layer=1, anim=""):
    return dialogue(layer, start, end,
                    rf"{{\an7\pos(0,0){anim}\1a&HFF&\bord{thickness}\shad0\3c{colour}\p1}}{_rect_path(x, y, w, h, r)}")


def text_line(x, y, runs, start, end, layer=2, align=7, anim=""):
    """runs: list of (text, colour, font, size). (x, y) is the anchor given by align."""
    parts = [rf"{{\an{align}\pos({x:.0f},{y:.0f}){anim}\bord0\shad0}}"]
    for t, colour, font, size in runs:
        parts.append(rf"{{\fn{font[0]}\fs{size}\1c{colour}}}{t}")
    return dialogue(layer, start, end, "".join(parts))


def ass_file(events):
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{MAIN[0]},70,{WHITE},{WHITE},{INK},&H00000000,0,0,0,0,100,100,2,0,1,0,0,7,0,0,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, ""])


def blurred(src, regions, out):
    """Copy of a photo with regions blurred out (e.g. a Wi-Fi password on a screen).
    regions: [[x0, y0, x1, y1], ...] as fractions of the (upright) photo's width and height."""
    from PIL import ImageFilter
    im = Image.open(src).convert("RGB")
    for x0, y0, x1, y1 in regions:
        box = (round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height))
        im.paste(im.crop(box).filter(ImageFilter.GaussianBlur(max(8, (box[2] - box[0]) // 12))), box)
    im.save(out, quality=94)
    return out


def card(src, width, out, border_hex=None, border=8, radius=24):
    """A photo as a rounded card with a coloured border, saved as a PNG."""
    border_hex = border_hex or hex_colour("fill")
    im = Image.open(src).convert("RGBA")
    h = round(im.height * width / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    outer = Image.new("RGBA", (width + 2 * border, h + 2 * border), (0, 0, 0, 0))
    ImageDraw.Draw(outer).rounded_rectangle([0, 0, outer.width - 1, outer.height - 1], radius + border, fill=border_hex)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, h - 1], radius, fill=255)
    outer.paste(im, (border, border), mask)
    outer.save(out)
    return outer.size


def sticker(src, width, out):
    """A sticker trimmed to its content, about `width` px wide. Pixel-art SVGs (crispEdges, e.g. a mascot)
    are scaled by whole pixels with no smoothing, so they stay crisp."""
    src = pathlib.Path(src)
    if src.suffix == ".svg":
        text = src.read_text(encoding="utf-8", errors="ignore")
        if "crispEdges" in text:
            grid_w = float(re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+)', text).group(1))
            png = subprocess.run(["rsvg-convert", "-w", str(int(grid_w)), str(src)], capture_output=True, check=True).stdout
            im = Image.open(io.BytesIO(png)).convert("RGBA")  # one image pixel per art pixel
            im = im.crop(im.getbbox())
            k = max(1, round(width / im.width))
            im = im.resize((im.width * k, im.height * k), Image.NEAREST)
            im.save(out)
            return im.size
        png = subprocess.run(["rsvg-convert", "-w", "1200", str(src)], capture_output=True, check=True).stdout
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    else:
        im = Image.open(src).convert("RGBA")
    im = im.crop(im.getbbox())
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(out)
    return im.size
