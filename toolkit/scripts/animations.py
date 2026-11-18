"""Explainer b-roll animations (1080x1920, 30 fps, MP4), drawn frame by frame.

Usage: python -I animations.py <video folder> [name ...]
Writes broll/anim_<name>.mp4 in the video folder. Content sits in the middle of the frame (y 520-1320),
so the title tab and chips at the top and the subtitles at the bottom don't cover it. Two-line subtitles start at
about y 1340 (labels lower than that get hidden).
Each animation is a function below; text comes from its arguments, so it can be reused for other videos.

Pacing and wording -- every new animation calls pace_check() with its timings and texts:
- Concise words: a label is a few words, not a sentence (at most WORDS_MAX reading units; headings shorter).
  Reading units: one per Chinese character, two per Latin-script word (about the same time to read).
- Not rushed: new elements come in at least GAP_MIN s apart, and there are no more than about CHARS_PER_S
  reading units of text per second of animation (viewers read while listening to you).
- Calm ending: everything is in by END_HOLD s before the end and the last frame then holds still, so the
  animation never ends mid-movement. If the line it covers is too short, cut content rather than speed up.
"""
import math, pathlib, re, subprocess, sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import FFMPEG, LATIN as _LATIN, MAIN as _MAIN, font_file, rgb  # noqa: E402

W, H, FPS = 1080, 1920, 30
INK, PANEL, RAISED, LINE = rgb("ink"), rgb("panel"), rgb("raised"), rgb("line")
WHITE, ACCENT, HIGHLIGHT, FILL, MUTED = rgb("text"), rgb("accent"), rgb("highlight"), rgb("fill"), rgb("muted")
MAIN, LATIN = str(_MAIN[1]), str(_LATIN[1])
_f = {}


def font(path, size):
    if (path, size) not in _f:
        _f[(path, size)] = ImageFont.truetype(str(font_file((None, path))), size)
    return _f[(path, size)]


WORDS_MAX, GAP_MIN, CHARS_PER_S, END_HOLD = 10, 0.8, 3, 2.5


def units(text):
    """Reading units: one per CJK character, two per Latin-script word or number."""
    return len(re.findall(r"[\u3400-\u9fff]", text)) + 2 * len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.%+-]*", text))


def pace_check(name, seconds, cues, texts=()):
    """Warn when an animation is wordy or rushed (see the pacing rule at the top).
    cues: times (s) when new elements start coming in; texts: every piece of text it shows."""
    cues = sorted(cues)
    for a, b in zip(cues, cues[1:]):
        if b - a < GAP_MIN - 1e-6:
            print(f"WARNING {name}: elements at {a:.1f}s and {b:.1f}s come in only {b - a:.1f}s apart (min {GAP_MIN}s)")
    if cues and seconds - cues[-1] < END_HOLD:
        print(f"WARNING {name}: the last element comes in at {cues[-1]:.1f}s, only {seconds - cues[-1]:.1f}s "
              f"before the end (hold at least {END_HOLD}s): make it longer or cut content")
    for tx in texts:
        n = units(tx)
        if n > WORDS_MAX:
            print(f"WARNING {name}: '{tx}' is {n} reading units; keep labels to {WORDS_MAX} or fewer")
    chars = sum(units(tx) for tx in texts)
    if chars > CHARS_PER_S * seconds:
        print(f"WARNING {name}: {chars} reading units of text in {seconds:.1f}s is a lot to read while you talk "
              f"(max about {CHARS_PER_S} a second); cut words or add time")


def ease(t):  # smooth 0..1
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def background(h=H):
    """Dark ground with a faint grid."""
    im = Image.new("RGB", (W, h), INK)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 60):
        d.line([(x, 0), (x, H)], fill=LINE)
    for y in range(0, H, 60):
        d.line([(0, y), (W, y)], fill=LINE)
    return im


def glow(im, draw_fn, radius=18):
    """Draw something twice: blurred underneath for a soft glow, sharp on top."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    im.paste(layer.filter(ImageFilter.GaussianBlur(radius)), (0, 0), layer.filter(ImageFilter.GaussianBlur(radius)))
    im.paste(layer, (0, 0), layer)


def write(frames, out):
    p = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    print("wrote", out)


def frontier(out, title="Knowledge edge", human="Us", ai="AI", seconds=4.5, box=(150, 960, 1380, 640), height=H, still=False):
    """A. Two lines climbing; the AI line overtakes the human one and keeps going. Ends on the crossing.
    still=True saves only the last frame as a PNG (e.g. a cover background: height=1440, a smaller box, no title)."""
    x0, x1, y0, y1 = box  # chart area (y0 bottom)
    n = int(seconds * FPS)

    def human_y(u):  # slow, steady rise
        return 0.18 + 0.42 * u

    def ai_y(u):  # starts low, then shoots up and crosses
        return 0.05 + 0.92 * u ** 2.3

    cross = next(i / 400 for i in range(1, 401) if ai_y(i / 400) >= human_y(i / 400))
    frames = []
    for k in range(n):
        t = k / (n - 1)
        u = ease(min(1.0, t / 0.8))  # lines draw over the first 80%
        if still and k < n - 1:
            continue
        im = background(height)
        d = ImageDraw.Draw(im)
        # title and axes
        if title:
            d.text((W // 2, 520), title, font=font(MAIN, 92), fill=WHITE, anchor="mm")
            d.text((W // 2, 600), "KNOWLEDGE FRONTIER", font=font(LATIN, 30), fill=ACCENT, anchor="mm")
        d.line([(x0, y0), (x1, y0)], fill=MUTED, width=4)
        d.line([(x0, y0), (x0, y1 - 20)], fill=MUTED, width=4)
        d.text((x1, y0 + 46), "Time", font=font(MAIN, 40), fill=MUTED, anchor="rm")
        d.text((x0 - 20, y1 - 10), "Edge", font=font(MAIN, 40), fill=MUTED, anchor="rm")

        def pts(fn):
            m = max(2, int(120 * u))
            return [(x0 + (x1 - x0) * (i / 120), y0 - (y0 - y1) * fn(i / 120)) for i in range(m)]
        hp, ap = pts(human_y), pts(ai_y)
        glow(im, lambda dd: dd.line(hp, fill=ACCENT + (255,), width=12, joint="curve"), 10)
        glow(im, lambda dd: dd.line(ap, fill=HIGHLIGHT + (255,), width=12, joint="curve"), 14)
        d = ImageDraw.Draw(im)
        for p, colour, label in ((hp[-1], ACCENT, human), (ap[-1], HIGHLIGHT, ai)):
            d.rectangle([p[0] - 14, p[1] - 14, p[0] + 14, p[1] + 14], fill=colour)  # pixel dot at the head
            d.text((p[0] + 30, p[1]), label, font=font(MAIN, 52), fill=colour, anchor="lm")
        if u * 120 / 120 > cross:  # mark the crossing
            cx, cy = x0 + (x1 - x0) * cross, y0 - (y0 - y1) * human_y(cross)
            a = ease((u - cross) / 0.15)
            r = 26 + 10 * math.sin(k / 4)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=FILL, width=5)
            if a > 0.5:
                d.rounded_rectangle([cx - 180, cy + 50, cx + 180, cy + 130], 14, fill=PANEL, outline=FILL, width=3)
                d.text((cx, cy + 90), "> AI overtakes _", font=font(MAIN, 44), fill=WHITE, anchor="mm")
        frames.append(im)
    if still:
        frames[-1].save(out)
        print("wrote", out)
    else:
        write(frames, out)


def process_vs_result(out, left=("Researchers love", "the process"), right=("Society pays for", "the result"), seconds=5.0):
    """C. Two panels side by side; the left fills with small 'steps', then the right lights up and wins focus."""
    n = int(seconds * FPS)
    pw, ph, gap = 440, 760, 40
    lx, rx, top = (W - 2 * pw - gap) // 2, (W - 2 * pw - gap) // 2 + pw + gap, 600
    steps = ["Ask", "Try", "Fail", "Retry", "Ding! Found"]
    frames = []
    for k in range(n):
        t = k / (n - 1)
        im = background()
        d = ImageDraw.Draw(im)
        dim = ease((t - 0.62) / 0.15)  # left dims as the right takes over
        # left panel: the process
        lc = tuple(round(c * (1 - 0.45 * dim) + INK[i] * 0.45 * dim) for i, c in enumerate(ACCENT))
        d.rounded_rectangle([lx, top, lx + pw, top + ph], 18, fill=PANEL, outline=lc, width=4)
        d.text((lx + pw // 2, top + 60), left[0], font=font(MAIN, 44), fill=MUTED, anchor="mm")
        d.text((lx + pw // 2, top + 130), left[1], font=font(MAIN, 64), fill=lc, anchor="mm")
        for i, s in enumerate(steps):
            a = ease((t - 0.08 - i * 0.09) / 0.08)
            if a <= 0:
                continue
            y = top + 220 + i * 100
            col = HIGHLIGHT if s.startswith("Ding") else WHITE
            col = tuple(round(c * a * (1 - 0.5 * dim) + INK[j] * (1 - a * (1 - 0.5 * dim))) for j, c in enumerate(col))
            d.rounded_rectangle([lx + 50, y, lx + pw - 50, y + 72], 10, fill=RAISED)
            d.text((lx + pw // 2, y + 36), s, font=font(MAIN, 40), fill=col, anchor="mm")
            if i < len(steps) - 1 and a > 0.9:
                d.text((lx + pw // 2, y + 88), "↓", font=font(LATIN, 26), fill=MUTED, anchor="mm")
        # right panel: the result, lights up at the end
        on = ease((t - 0.6) / 0.18)
        rc = tuple(round(MUTED[i] * (1 - on) + HIGHLIGHT[i] * on) for i in range(3))
        if on > 0:
            glow(im, lambda dd: dd.rounded_rectangle([rx, top, rx + pw, top + ph], 18, outline=HIGHLIGHT + (round(255 * on),), width=10), 22)
            d = ImageDraw.Draw(im)
        d.rounded_rectangle([rx, top, rx + pw, top + ph], 18, fill=PANEL, outline=rc, width=4)
        d.text((rx + pw // 2, top + 60), right[0], font=font(MAIN, 44), fill=MUTED, anchor="mm")
        d.text((rx + pw // 2, top + 130), right[1], font=font(MAIN, 64), fill=rc, anchor="mm")
        # a pixel "result" block that pops in
        s = 150 * ease((t - 0.66) / 0.12)
        if s > 1:
            cx, cy = rx + pw // 2, top + 430
            d.rectangle([cx - s, cy - s, cx + s, cy + s], fill=HIGHLIGHT)
            d.rectangle([cx - s + 24, cy - s + 24, cx - s + 60, cy - s + 60], fill=WHITE)
            if s > 140:  # pixel tick (the fonts have no ✓)
                tick = ["........##", ".......###", "......###.", "##...###..", "###.###...", ".#####....", "..###.....", "...#......"]
                px = 18
                for j, row in enumerate(tick):
                    for i, ch in enumerate(row):
                        if ch == "#":
                            x, y = cx - 5 * px + i * px, cy - 4 * px + j * px
                            d.rectangle([x, y, x + px - 1, y + px - 1], fill=INK)
        if t > 0.8:  # who found it? AI chip
            a = ease((t - 0.8) / 0.1)
            d.rounded_rectangle([rx + 70, top + 640, rx + pw - 70, top + 712], 12, fill=RAISED, outline=FILL, width=3)
            d.text((rx + pw // 2, top + 676), "AI can do it", font=font(MAIN, 40), fill=tuple(round(c * a) for c in WHITE), anchor="mm")
        # the dividing question
        d.text((W // 2, 520), "Process  vs  result", font=font(MAIN, 84), fill=WHITE, anchor="mm")
        frames.append(im)
    write(frames, out)





# ---- set 4: three_groups, brain_city, memory, debt, order ----
# Shared helpers: pixel sprites and fading layers. Frames are RGBA while drawing, RGB when written.

PERSON = ["..####..", "..####..", "..####..", "...##...", ".######.", "########", "#.####.#", "#.####.#",
          "..#..#..", "..#..#..", "..#..#.."]
CHAT = [".#########.", "###########", "##o##o##o##", "###########", ".#########.", "..##.......", ".##........"]
LENS = ["..####....", ".##..##...", "##....##..", "##....##..", ".##..##...", "..####....", "......##..",
        ".......##.", "........##"]
PENCIL = ["........##", ".......###", "......###.", ".....###..", "....###...", "...###....", "..###.....",
          ".###......", ".##.......", "#........."]


def sprite(d, rows, x, y, px, colour, hole=INK):
    """Pixel art: '#' in colour, 'o' in the hole colour, anything else transparent. Whole pixels only."""
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in "#o":
                d.rectangle([x + i * px, y + j * px, x + (i + 1) * px - 1, y + (j + 1) * px - 1],
                            fill=colour if ch == "#" else hole)


def layer(im, fn, a=1.0, dy=0.0):
    """Draw fn on a transparent layer, then lay it over im at opacity a, shifted down by dy (for slide-ins)."""
    if a <= 0:
        return
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    fn(ImageDraw.Draw(lay))
    if a < 1:
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
    if dy:
        moved = Image.new("RGBA", im.size, (0, 0, 0, 0))
        moved.paste(lay, (0, int(round(dy))))
        lay = moved
    im.alpha_composite(lay)


def mix(c1, c2, u):
    return tuple(round(a * (1 - u) + b * u) for a, b in zip(c1, c2))


def frame_rgba():
    return background().convert("RGBA")


def write_rgba(frames, out):
    write([f.convert("RGB") for f in frames], out)


def appear(t, start, dur=0.35):  # 0..1 as an element fades/slides in at `start` seconds
    return ease((t - start) / dur)


def three_groups(out, seconds=9.0, cues=(0.8, 2.9, 6.0), header="54 people • 4 months", header_en="MIT MEDIA LAB",
                 groups=(("ChatGPT", "AI group"), ("Search", "like Google"), ("Brain only", "no tools"))):
    """A. Three cards appear one by one as each group is named: AI (chat bubble), search (lens), own brain (pencil)."""
    n = int(seconds * FPS)
    icons, colours = (CHAT, LENS, PENCIL), (HIGHLIGHT, ACCENT, FILL)
    cw, gap, top, ch = 310, 25, 720, 640
    x0 = (W - 3 * cw - 2 * gap) // 2
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: (d.text((W // 2, 570), header, font=font(MAIN, 76), fill=WHITE, anchor="mm"),
                             d.text((W // 2, 645), header_en, font=font(LATIN, 32), fill=ACCENT, anchor="mm")), appear(t, 0.1))
        for g, ((name, sub), icon, col) in enumerate(zip(groups, icons, colours)):
            a = appear(t, cues[g], 0.4)
            x = x0 + g * (cw + gap)

            def card(d, x=x, name=name, sub=sub, icon=icon, col=col):
                d.rounded_rectangle([x, top, x + cw, top + ch], 22, fill=PANEL + (235,), outline=col, width=5)
                d.text((x + 34, top + 50), f"0{g + 1}", font=font(LATIN, 34), fill=col, anchor="lm")
                px = 16
                sprite(d, icon, x + (cw - len(icon[0]) * px) // 2, top + 150, px, col)
                d.text((x + cw // 2, top + 440), name, font=font(MAIN if not name.isascii() else LATIN, 58 if not name.isascii() else 50),
                       fill=WHITE, anchor="mm")
                d.text((x + cw // 2, top + 530), sub, font=font(MAIN, 40), fill=MUTED, anchor="mm")
            if a > 0:
                if a > 0.95:
                    glow(im, lambda d, x=x, col=col: d.rounded_rectangle([x, top, x + cw, top + ch], 22, outline=col + (150,), width=8), 16)
                layer(im, card, a, 60 * (1 - a))
        frames.append(im)
    write_rgba(frames, out)


def brain_city(out, seconds=9.0, switch=4.4, busy=("Brain only", "a busy city"), quiet=("With AI", "quiet roads")):
    """B. Two brains drawn as city road maps: the first full of moving cars, the second (appears at `switch`) nearly empty.
    A small activity meter beside each."""
    import random
    n = int(seconds * FPS)
    rng = random.Random(4)
    pw, ph, px0 = 960, 420, (W - 960) // 2
    tops = (575, 1035)
    cx_off, rx, ry, step = 330, 290, 175, 35

    def roads_for(seed):
        r = random.Random(seed)
        segs = []
        inside = lambda x, y: ((x) / rx) ** 2 + ((y) / ry) ** 2 < 0.92
        for gx in range(-rx, rx + 1, step):
            for gy in range(-ry, ry + 1, step):
                if inside(gx, gy) and inside(gx + step, gy) and r.random() < 0.8:
                    segs.append((gx, gy, gx + step, gy))
                if inside(gx, gy) and inside(gx, gy + step) and r.random() < 0.8:
                    segs.append((gx, gy, gx, gy + step))
        return segs
    roads = roads_for(7)
    cars_busy = [(rng.randrange(len(roads)), rng.random(), rng.choice((0.6, 0.9, 1.2)), rng.choice((FILL, ACCENT, HIGHLIGHT, WHITE)))
                 for _ in range(150)]
    cars_quiet = [(rng.randrange(len(roads)), rng.random(), 0.5, ACCENT) for _ in range(7)]
    # chain cars along neighbouring segments so they look like traffic, not blinking dots
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for p, (top, (label, sub), cars, level, start, col) in enumerate((
                (tops[0], busy, cars_busy, 0.92, 0.0, FILL), (tops[1], quiet, cars_quiet, 0.22, switch, HIGHLIGHT))):
            a = appear(t, start + 0.1, 0.45)
            if a <= 0:
                continue
            cx, cy = px0 + cx_off, top + ph // 2 + 10
            road_col = RAISED if p == 0 else LINE

            def panel(d, top=top, label=label, sub=sub, cars=cars, level=level, col=col, cx=cx, cy=cy, road_col=road_col, start=start):
                d.rounded_rectangle([px0, top, px0 + pw, top + ph], 22, fill=PANEL + (235,), outline=col, width=4)
                d.ellipse([cx - rx - 14, cy - ry - 14, cx + rx + 14, cy + ry + 14], outline=col, width=5)
                d.line([(cx, cy - ry - 10), (cx, cy + ry + 10)], fill=col, width=3)  # the two halves
                for x1, y1, x2, y2 in roads:
                    d.line([(cx + x1, cy + y1), (cx + x2, cy + y2)], fill=road_col, width=6)
                for i, ph0, sp, c in cars:
                    x1, y1, x2, y2 = roads[i]
                    u = (ph0 + sp * (t - start)) % 1.0
                    x, y = cx + x1 + (x2 - x1) * u, cy + y1 + (y2 - y1) * u
                    d.rectangle([x - 5, y - 5, x + 5, y + 5], fill=c)
                # label and meter on the right
                mx = px0 + 700
                d.text((mx + 110, top + 70), label, font=font(MAIN, 54), fill=WHITE, anchor="mm")
                d.text((mx + 110, top + 130), sub, font=font(MAIN, 34), fill=MUTED, anchor="mm")
                d.text((mx + 110, top + 200), "Activity", font=font(MAIN, 32), fill=MUTED, anchor="mm")
                bx, by, bw, bh = mx + 50, top + 230, 120, 150
                d.rectangle([bx, by, bx + bw, by + bh], outline=MUTED, width=3)
                lv = level * ease((t - start - 0.3) / 0.8)
                blocks = 6
                for b in range(blocks):
                    if (b + 1) / blocks <= lv + 0.01:
                        y = by + bh - (b + 1) * (bh / blocks)
                        d.rectangle([bx + 8, y + 4, bx + bw - 8, y + bh / blocks - 2], fill=col)
            layer(im, panel, a, 40 * (1 - a))
        frames.append(im)
    write_rgba(frames, out)


def memory(out, seconds=10.5, groups=(("Own-work group", 2, 0.4, 1.8), ("AI group", 15, 3.8, 5.3)),
           question="Quote one line from your essay?"):
    """C. Two groups of 18 pixel people; the ones who couldn't recall a sentence turn grey with a '?' and the count ticks up."""
    n = int(seconds * FPS)
    px, per_row, sx, sy = 8, 9, 100, 136
    x0 = (W - (per_row - 1) * sx - 8 * px) // 2
    tops = (690, 1090)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: d.text((W // 2, 585), question, font=font(MAIN, 44), fill=WHITE, anchor="mm"), appear(t, 0.0))
        for g, ((label, lost, start, grey_at), top) in enumerate(zip(groups, tops)):
            a = appear(t, start, 0.4)
            if a <= 0:
                continue
            spread = 0.15 if lost < 5 else 0.11  # one after another

            def block(d, label=label, lost=lost, top=top, grey_at=grey_at, spread=spread):
                gone = sum(1 for i in range(lost) if t >= grey_at + i * spread)
                d.text((x0, top), label, font=font(MAIN, 48), fill=WHITE, anchor="lm")
                num = f"{gone}"
                d.text((W - x0, top), "/ 18 can't", font=font(MAIN, 40), fill=MUTED, anchor="rm")
                wtxt = d.textlength("/ 18 can't", font=font(MAIN, 40))
                d.text((W - x0 - wtxt - 14, top + 4), num, font=font(LATIN, 72), fill=HIGHLIGHT if gone else MUTED, anchor="rm")
                order = list(range(18))[::-1]  # grey from the end of the bottom row, so the remembering ones lead
                greyed = set(order[:gone])
                for i in range(18):
                    r, c = divmod(i, per_row)
                    x, y = x0 + c * sx, top + 60 + r * sy
                    if i in greyed:
                        sprite(d, PERSON, x, y, px, MUTED)
                        d.text((x + 4 * px, y - 4), "?", font=font(LATIN, 34), fill=HIGHLIGHT, anchor="mb")
                    else:
                        sprite(d, PERSON, x, y, px, ACCENT)
            layer(im, block, a, 40 * (1 - a))
        frames.append(im)
    write_rgba(frames, out)


def debt(out, seconds=9.5, title="Thinking debt", title_en="COGNITIVE DEBT", card_at=3.0, swipe_at=4.3, skip_at=5.6, end_at=7.6,
         easy="Easy now", skipped="Skipped thinking", later="Pay it back later"):
    """E. Thinking debt like a credit card: the card slides in and swipes (easy now), skipped thinking piles up as debt,
    and the bill line lands at the end."""
    n = int(seconds * FPS)
    cw, chh = 560, 340
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: (d.text((W // 2, 590), title, font=font(MAIN, 104), fill=WHITE, anchor="mm"),
                             d.text((W // 2, 680), title_en, font=font(LATIN, 36), fill=ACCENT, anchor="mm")), appear(t, 0.2, 0.4))
        a = appear(t, card_at, 0.45)
        if a > 0:
            dip = 26 * math.sin(math.pi * min(1.0, max(0.0, (t - swipe_at) / 0.35)))  # the swipe
            cx = W // 2 - 600 * (1 - a)
            cy = 760 + dip

            def card(d, cx=cx, cy=cy):
                x, y = cx - cw // 2, cy
                d.rounded_rectangle([x, y, x + cw, y + chh], 30, fill=HIGHLIGHT)
                d.rectangle([x, y + 70, x + cw, y + 120], fill=INK)  # stripe
                d.rounded_rectangle([x + 50, y + 160, x + 140, y + 230], 10, fill=FILL)  # chip
                for i in range(3):
                    d.line([(x + 50, y + 183 + i * 16), (x + 140, y + 183 + i * 16)], fill=HIGHLIGHT, width=3)
                d.text((x + cw - 40, y + 285), "THINKING  •  2026", font=font(LATIN, 30), fill=INK, anchor="rm")
            layer(im, card, a)
        e = appear(t, swipe_at + 0.25, 0.3)
        if e > 0:
            layer(im, lambda d: (d.rounded_rectangle([W // 2 - 190, 1135, W // 2 + 190, 1205], 14, fill=PANEL, outline=FILL, width=3),
                                 d.text((W // 2, 1170), f"> {easy} _", font=font(MAIN, 42), fill=WHITE, anchor="mm")), e)
        s = appear(t, skip_at, 0.3)
        if s > 0:
            fill = min(1.0, max(0.0, (t - skip_at) / (end_at - skip_at)))
            count = int(1 + fill * 11)

            def ledger(d, fill=fill, count=count):
                bx, by, bw, bh = 110, 1270, W - 220, 56
                d.text((bx, by - 34), f"{skipped}  ×{count}", font=font(MAIN, 40), fill=WHITE, anchor="lm")
                d.text((bx + bw, by - 34), "Debt", font=font(MAIN, 40), fill=HIGHLIGHT, anchor="rm")
                d.rectangle([bx, by, bx + bw, by + bh], outline=MUTED, width=3)
                cells = 18
                cwid = (bw - 12) / cells
                for c in range(int(cells * fill + 0.999)):
                    d.rectangle([bx + 6 + c * cwid, by + 6, bx + 6 + (c + 1) * cwid - 4, by + bh - 6], fill=HIGHLIGHT)
            layer(im, ledger, s)
        f = appear(t, end_at, 0.35)
        if f > 0:
            layer(im, lambda d: d.text((W // 2, 1410), f"> {later} _", font=font(MAIN, 56), fill=HIGHLIGHT, anchor="mm"), f, 20 * (1 - f))
        frames.append(im)
    write_rgba(frames, out)


def order(out, seconds=7.5, title="Order matters", step1=("Think first", "Write 3 ideas, however rough"), step2="Then ask AI",
          asks=("Where is my idea weak?", "What am I missing?"), wrong=("AI first", "then think"), cues=(0.5, 1.9, 3.6, 5.2)):
    """F. Two steps in order: 01 your own ideas, then 02 AI challenges them (two questions pop in); the wrong order is crossed out."""
    n = int(seconds * FPS)
    x0, x1 = 90, W - 90
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: d.text((W // 2, 580), title, font=font(MAIN, 90), fill=WHITE, anchor="mm"), appear(t, 0.0))

        def s1(d):
            d.rounded_rectangle([x0, 680, x1, 870], 22, fill=PANEL + (235,), outline=ACCENT, width=4)
            d.text((x0 + 50, 775), "01", font=font(LATIN, 64), fill=ACCENT, anchor="lm")
            d.text((x0 + 180, 745), step1[0], font=font(MAIN, 62), fill=WHITE, anchor="lm")
            d.text((x0 + 180, 818), step1[1], font=font(MAIN, 36), fill=MUTED, anchor="lm")
        layer(im, s1, appear(t, 0.1))
        layer(im, lambda d: d.text((W // 2, 925), "↓", font=font(LATIN, 60), fill=MUTED, anchor="mm"), appear(t, cues[0]))
        a2 = appear(t, cues[0], 0.4)
        if a2 > 0:
            if a2 > 0.95:
                glow(im, lambda d: d.rounded_rectangle([x0, 980, x1, 1310], 22, outline=HIGHLIGHT + (150,), width=8), 16)

            def s2(d):
                d.rounded_rectangle([x0, 980, x1, 1310], 22, fill=PANEL + (235,), outline=HIGHLIGHT, width=4)
                d.text((x0 + 50, 1050), "02", font=font(LATIN, 64), fill=HIGHLIGHT, anchor="lm")
                d.text((x0 + 180, 1050), step2, font=font(MAIN, 62), fill=WHITE, anchor="lm")
            layer(im, s2, a2, 40 * (1 - a2))
        for q, (txt, at) in enumerate(zip(asks, cues[1:3])):
            qa = appear(t, at, 0.3)
            y = 1130 + q * 90
            layer(im, lambda d, y=y, txt=txt: (d.rounded_rectangle([x0 + 40, y, x1 - 40, y + 70], 12, fill=RAISED),
                                               d.text((x0 + 70, y + 35), f"> {txt}", font=font(MAIN, 40), fill=WHITE, anchor="lm")), qa, 20 * (1 - qa))
        wa = appear(t, cues[3], 0.35)
        if wa > 0:
            def wrong_order(d):
                y = 1400
                l1, l2 = font(MAIN, 52), font(LATIN, 52)
                w1, w2, w3 = d.textlength(wrong[0], font=l1), d.textlength(" → ", font=l2), d.textlength(wrong[1], font=l1)
                x = W // 2 - (w1 + w2 + w3) / 2
                d.text((x, y), wrong[0], font=l1, fill=MUTED, anchor="lm")
                d.text((x + w1, y), " → ", font=l2, fill=MUTED, anchor="lm")
                d.text((x + w1 + w2, y), wrong[1], font=l1, fill=MUTED, anchor="lm")
                d.line([(x - 20, y + 2), (x + w1 + w2 + w3 + 20, y + 2)], fill=HIGHLIGHT, width=4)  # crossed out
                sx = x + w1 + w2 + w3 + 50
                d.line([(sx, y - 22), (sx + 44, y + 22)], fill=HIGHLIGHT, width=8)
                d.line([(sx, y + 22), (sx + 44, y - 22)], fill=HIGHLIGHT, width=8)
            layer(im, wrong_order, wa)
        frames.append(im)
    write_rgba(frames, out)




# ---- set 5: perception_gap, cliff, four_types, ask_better, interests ----
# Each calls pace_check(): short labels, elements >= 0.8 s apart, everything in 2.5 s before the end.

STAR = ["....#....", "....#....", "...###...", "#########", ".#######.", "..#####..", "..##.##..", ".##...##.", "##.....##"]
PAD = [".#########.", "###########", "#.#####oo##", "...####oo##", "#.#####oo##", "###########", "###.....###", ".#.......#."]
BULB = ["..#####..", ".#######.", "#########", "#########", "#########", ".#######.", "..#####..", "...###...", "..#####..",
        "...###..."]
NO = ["..#####..", ".##...##.", "##...###.", "#...###.#", "#..###..#", "#.###...#", ".###...##", ".##...##.", "..#####.."]
BOOK = ["#####.#####", "#...#.#...#", "#.#.#.#.#.#", "#...#.#...#", "#.#.#.#.#.#", "#...#.#...#", "#####.#####",
        "...######.."]




def perception_gap(out, seconds=12.0, cues=(0.6, 4.0, 7.0), kids=("Kids say", 26), parents=("Parents think", 65),
                   gap="~40% gap", title="Like school?"):
    """#1 Two bars: what kids say (26%) and what parents think (65%); then the gap between them is marked."""
    n = int(seconds * FPS)
    base_y, top_y, bw = 1250, 700, 250
    xs = (W // 2 - 420, W // 2 - 90)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: d.text((W // 2, 580), title, font=font(MAIN, 86), fill=WHITE, anchor="mm"), appear(t, 0.0))
        layer(im, lambda d: d.line([(110, base_y), (W - 110, base_y)], fill=MUTED, width=4), appear(t, 0.0))
        for (label, pct), x, col, at in ((kids, xs[0], HIGHLIGHT, cues[0]), (parents, xs[1], ACCENT, cues[1])):
            g = ease((t - at) / 1.0)  # bar grows over a second
            if g <= 0:
                continue
            h = (base_y - top_y) * pct / 100 * g
            glow(im, lambda d, x=x, h=h, col=col: d.rectangle([x, base_y - h, x + bw, base_y], fill=col + (255,)), 14)
            layer(im, lambda d, x=x, h=h, pct=pct, g=g, col=col: (
                d.text((x + bw // 2, base_y - h - 50), f"{round(pct * g)}%", font=font(LATIN, 72), fill=col, anchor="mm"),
                d.text((x + bw // 2, base_y + 55), label, font=font(MAIN, 50), fill=WHITE, anchor="mm")))
        a = appear(t, cues[2], 0.5)
        if a > 0:
            y26 = base_y - (base_y - top_y) * kids[1] / 100
            y65 = base_y - (base_y - top_y) * parents[1] / 100
            bx = xs[1] + bw + 40

            def bracket(d):
                d.line([(xs[0] + bw, y26), (bx, y26)], fill=MUTED, width=3)
                d.line([(bx - 20, y65), (bx, y65), (bx, y26), (bx - 20, y26)], fill=FILL, width=6)
                big, small = gap.split(" ", 1) if " " in gap else (gap, "")
                mid = (y65 + y26) / 2
                d.text((bx + 140, mid - 40), big, font=font(MAIN, 76), fill=FILL, anchor="mm")
                d.text((bx + 140, mid + 45), small, font=font(MAIN, 58), fill=WHITE, anchor="mm")
            layer(im, bracket, a, 30 * (1 - a))
        frames.append(im)
    pace_check("perception_gap", seconds, cues, [title, kids[0], parents[0], gap])
    write_rgba(frames, out)


def cliff(out, seconds=9.0, cues=(0.4, 2.6, 4.4), title="Kids who like school", start=("Grade 3", 74), end=("Grade 10", 26)):
    """#3 A line from grade 3 (74%) that falls off a cliff to grade 10 (26%)."""
    n = int(seconds * FPS)
    x0, x1, base_y, top_y = 170, W - 170, 1250, 720
    frames = []

    def y_of(pct):
        return base_y - (base_y - top_y) * pct / 100

    def curve(u):  # gentle slide, then a steep drop in the middle
        return start[1] + (end[1] - start[1]) * ease((u - 0.25) / 0.5)
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: (d.text((W // 2, 580), title, font=font(MAIN, 86), fill=WHITE, anchor="mm"),
                             d.line([(x0 - 30, base_y), (x1 + 30, base_y)], fill=MUTED, width=4)), appear(t, 0.0))
        a0 = appear(t, cues[0], 0.4)
        layer(im, lambda d: (d.rectangle([x0 - 16, y_of(start[1]) - 16, x0 + 16, y_of(start[1]) + 16], fill=ACCENT),
                             d.text((x0, y_of(start[1]) - 70), f"{start[1]}%", font=font(LATIN, 64), fill=ACCENT, anchor="mm"),
                             d.text((x0, base_y + 55), start[0], font=font(MAIN, 46), fill=WHITE, anchor="mm")), a0)
        u = ease((t - cues[1]) / 1.4)  # the line draws over 1.4 s
        if u > 0:
            pts = [(x0 + (x1 - x0) * i / 100, y_of(curve(i / 100))) for i in range(int(100 * u) + 1)]
            if len(pts) > 1:
                glow(im, lambda d: d.line(pts, fill=HIGHLIGHT + (255,), width=12, joint="curve"), 12)
        a2 = appear(t, cues[2], 0.4)
        layer(im, lambda d: (d.rectangle([x1 - 16, y_of(end[1]) - 16, x1 + 16, y_of(end[1]) + 16], fill=HIGHLIGHT),
                             d.text((x1, y_of(end[1]) - 70), f"{end[1]}%", font=font(LATIN, 64), fill=HIGHLIGHT, anchor="mm"),
                             d.text((x1, base_y + 55), end[0], font=font(MAIN, 46), fill=WHITE, anchor="mm")), a2)
        frames.append(im)
    pace_check("cliff", seconds, cues, [title, start[0], end[0], f"{start[1]}%", f"{end[1]}%"])
    write_rgba(frames, out)


def four_types(out, seconds=9.0, cues=(0.4, 1.4, 2.4, 3.4, 4.8), title="4 learner types", rare="Rarest",
               types=(("Resister", NO, HIGHLIGHT), ("Passenger", None, MUTED), ("Achiever", BOOK, ACCENT), ("Explorer", LENS, FILL))):
    """#4 Four cards, two by two, one at a time; then Explorer lights up and gets a 'Rarest' tag."""
    n = int(seconds * FPS)
    cw, chh, gap = 430, 330, 40
    x0, y0 = (W - 2 * cw - gap) // 2, 700 if title else 600
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        layer(im, lambda d: d.text((W // 2, 580), title, font=font(MAIN, 86), fill=WHITE, anchor="mm"), appear(t, 0.0))
        hi = appear(t, cues[4], 0.5)
        for i, (name, icon, col) in enumerate(types):
            a = appear(t, cues[i], 0.4)
            if a <= 0:
                continue
            x, y = x0 + (i % 2) * (cw + gap), y0 + (i // 2) * (chh + gap)
            last = i == 3
            dim = 0.0 if last else 0.45 * hi  # the others step back when Explorer lights up
            c = mix(col, INK, dim)
            if last and hi > 0.9:
                glow(im, lambda d, x=x, y=y: d.rounded_rectangle([x, y, x + cw, y + chh], 22, outline=FILL + (170,), width=10), 18)

            def card(d, x=x, y=y, name=name, icon=icon, c=c, i=i):
                d.rounded_rectangle([x, y, x + cw, y + chh], 22, fill=PANEL + (235,), outline=c, width=5)
                d.text((x + 30, y + 44), f"0{i + 1}", font=font(LATIN, 34), fill=c, anchor="lm")
                if icon:
                    px = 12
                    sprite(d, icon, x + (cw - len(icon[0]) * px) // 2, y + 60, px, c)
                else:  # Passenger: sleepy z z z
                    d.text((x + cw // 2, y + 120), "z Z z", font=font(LATIN, 72), fill=c, anchor="mm")
                d.text((x + cw // 2, y + 250), name, font=font(MAIN, 64), fill=mix(WHITE, INK, dim), anchor="mm")
            layer(im, card, a, 40 * (1 - a))
        if hi > 0:
            x, y = x0 + cw + gap, y0 + chh + gap
            layer(im, lambda d: (d.rounded_rectangle([x + cw - 190, y - 30, x + cw + 10, y + 36], 14, fill=FILL),
                                 d.text((x + cw - 90, y + 3), rare, font=font(MAIN, 42), fill=INK, anchor="mm")), hi, -20 * (1 - hi))
        frames.append(im)
    pace_check("four_types", seconds, cues, [title, rare] + [n_ for n_, _, _ in types])
    write_rgba(frames, out)


def ask_better(out, seconds=10.0, cues=(0.4, 2.2, 4.6), old="How was school?", reply="Fine", new="Best class today?",
               label="Ask it better"):
    """#10 Chat: the usual question gets a flat 'Fine' and is crossed out; a better question takes its place."""
    n = int(seconds * FPS)
    frames = []

    def bubble(d, y, text, colour, right=False, size=64):
        w = d.textlength(text, font=font(MAIN, size)) + 90
        x = W - 90 - w if right else 90
        d.rounded_rectangle([x, y, x + w, y + 130], 28, fill=PANEL + (240,), outline=colour, width=5)
        d.text((x + 45, y + 65), text, font=font(MAIN, size), fill=WHITE, anchor="lm")
        return x, w
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a0, a1, a2 = appear(t, cues[0]), appear(t, cues[1]), appear(t, cues[2], 0.45)
        strike = ease((t - cues[2]) / 0.4)

        def first(d):
            x, w = bubble(d, 640, old, mix(ACCENT, MUTED, strike))
            if strike > 0:
                d.line([(x + 30, 705), (x + 30 + (w - 60) * strike, 705)], fill=HIGHLIGHT, width=7)
        layer(im, first, a0, 30 * (1 - a0))
        if reply:
            layer(im, lambda d: bubble(d, 820, reply, MUTED, right=True), a1, 30 * (1 - a1))
        if a2 > 0:
            layer(im, lambda d: (d.text((W // 2, 1060), f"> {label}", font=font(MAIN, 54), fill=ACCENT, anchor="mm")), a2)
            if a2 > 0.95:
                glow(im, lambda d: bubble(d, 1140, new, HIGHLIGHT + (200,), size=72), 14)
            layer(im, lambda d: bubble(d, 1140, new, HIGHLIGHT, size=72), a2, 30 * (1 - a2))
        frames.append(im)
    pace_check("ask_better", seconds, cues, [x for x in (old, reply, label, new) if x])
    write_rgba(frames, out)


def interests(out, seconds=9.0, cues=(0.4, 1.4, 3.4), items=(("Fandom", STAR, HIGHLIGHT), ("Gaming", PAD, ACCENT)), result="Curiosity"):
    """#11 Two interests (a star, a game pad) each send a line down into one lit bulb: Curiosity."""
    n = int(seconds * FPS)
    xs, iy, by = (W // 2 - 230, W // 2 + 230), 560, 930
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for (name, icon, col), x, at in zip(items, xs, cues[:2]):
            a = appear(t, at, 0.4)
            px = 16
            layer(im, lambda d, x=x, name=name, icon=icon, col=col: (
                d.rounded_rectangle([x - 170, iy, x + 170, iy + 300], 22, fill=PANEL + (235,), outline=col, width=5),
                sprite(d, icon, x - len(icon[0]) * px // 2, iy + 50, px, col),
                d.text((x, iy + 240), name, font=font(MAIN, 56), fill=WHITE, anchor="mm")), a, 40 * (1 - a))
        u = ease((t - cues[2]) / 0.8)  # lines run down to the bulb, then it lights
        if u > 0:
            for x in xs:
                sx, sy, ex, ey = x, iy + 300, W // 2, by + 20
                layer(im, lambda d, sx=sx, sy=sy, ex=ex, ey=ey: d.line([(sx, sy), (sx + (ex - sx) * u, sy + (ey - sy) * u)],
                                                                       fill=MUTED, width=5))
        on = ease((t - cues[2] - 0.7) / 0.5)
        if on > 0:
            px = 22
            bx = W // 2 - len(BULB[0]) * px // 2
            glow(im, lambda d: sprite(d, BULB, bx, by + 40, px, FILL + (round(255 * on),)), 26)
            layer(im, lambda d: (sprite(d, BULB, bx, by + 40, px, FILL),
                                 d.text((W // 2, by + 330), result, font=font(MAIN, 76), fill=WHITE, anchor="mm")), on)
        frames.append(im)
    pace_check("interests", seconds, list(cues), [n_ for n_, _, _ in items] + [result])
    write_rgba(frames, out)


# ---------------------------------------------------------------- set 6: kids confiding in AI chatbots
SAD = [".#######.", "#.......#", "#.##.##.#", "#.......#", "#..###..#", "#.#...#.#", "#.......#", ".#######."]
SHIELD = ["#########", "#########", "####.####", "###...###", ".##...##.", ".#######.", "..#####..", "...###...", "....#...."]
MOON = ["..####..", ".###....", "###.....", "###.....", "###.....", "###.....", ".###....", "..####.."]


def pill(d, cx, cy, text, colour, size=50, fill=None, text_fill=WHITE, f=None):
    """A rounded label centred on (cx, cy); returns its box."""
    f = f or font(MAIN, size)
    w = d.textlength(text, font=f) + size * 1.2
    h = size * 1.9
    box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    d.rounded_rectangle(box, h / 2, fill=fill or PANEL + (240,), outline=colour, width=5)
    d.text((cx, cy), text, font=f, fill=text_fill, anchor="mm")
    return box


def chat_bubble(d, y, text, colour, right=False, size=60, tag=None, chars=None):
    """A chat bubble on the left (AI) or right (you); `chars` shows only the first n characters (typing)."""
    f = font(MAIN, size)
    w = d.textlength(text, font=f) + 90
    x = W - 90 - w if right else 90
    d.rounded_rectangle([x, y, x + w, y + size + 70], 28, fill=PANEL + (240,), outline=colour, width=5)
    shown = text if chars is None else text[:chars] + ("_" if chars < len(text) else "")
    d.text((x + 45, y + (size + 70) / 2), shown, font=f, fill=WHITE, anchor="lm")
    if tag:
        d.text((x + (w - 10 if right else 10), y - 30), tag, font=font(LATIN, 34), fill=colour,
               anchor="rm" if right else "lm")


def tree_hole(out, seconds=13.0, cues=(0.4, 2.5, 7.2, 9.0), third=("1/3", "confidant"), header="1000+ teens",
              pct=72, label="chatted with AI"):
    """#A1 A ring fills a third (confidant); then a 10x10 grid of teens fills to 72%."""
    n = int(seconds * FPS)
    cx, cy, r = W // 2, 820, 210
    cell, gx, gy = 54, W // 2 - 270, 700
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        out1 = 1 - appear(t, cues[2] - 0.3, 0.4)  # scene 1 fades as scene 2 comes in
        if out1 > 0:
            g = ease((t - cues[0]) / 0.8)
            layer(im, lambda d: d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RAISED, width=34), out1 * appear(t, 0.0))
            if g > 0:
                glow(im, lambda d: d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 120 * g,
                                         fill=HIGHLIGHT + (round(255 * out1),), width=34), 12)
                layer(im, lambda d: d.text((cx, cy), third[0], font=font(LATIN, 120), fill=HIGHLIGHT, anchor="mm"), out1 * g)
            a = appear(t, cues[1])
            layer(im, lambda d: d.text((cx, cy + r + 110), third[1], font=font(MAIN, 84), fill=WHITE, anchor="mm"),
                  out1 * a, 30 * (1 - a))
        a2 = appear(t, cues[2], 0.4)
        if a2 > 0:
            fill = ease((t - cues[3]) / 1.2) * pct

            def grid(d):
                d.text((W // 2, 610), header, font=font(MAIN, 66), fill=WHITE, anchor="mm")
                for i in range(100):
                    x, y = gx + (i % 10) * cell + cell // 2, gy + (i // 10) * cell + cell // 2
                    d.ellipse([x - 17, y - 17, x + 17, y + 17], fill=ACCENT if i < fill else RAISED)
            layer(im, grid, a2, 30 * (1 - a2))
            a3 = appear(t, cues[3], 0.4)
            layer(im, lambda d: (d.text((W // 2 - 30, 1275), f"{round(fill)}%", font=font(LATIN, 84), fill=ACCENT, anchor="rm"),
                                 d.text((W // 2 + 10, 1275), label, font=font(MAIN, 60), fill=WHITE, anchor="lm")), a3)
        frames.append(im)
    pace_check("tree_hole", seconds, cues, list(third) + [header, f"{pct}%", label])
    write_rgba(frames, out)


def bug_stamp(out, seconds=14.6, cues=(0.3, 3.4, 4.9, 7.9, 10.0), name=("New", "ChatGPT"), tags=("Agrees with you", "Praises a lot"),
              pulled="Pulled in days", stamp=("Too agreeable", "= Bug")):
    """#A3 A product card gains two flattering tags, is pulled, then gets stamped Too agreeable = Bug."""
    n = int(seconds * FPS)
    x0, y0, x1, y1 = 140, 600, W - 140, 1020
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        dim = 0.55 * appear(t, cues[3], 0.5)
        a0 = appear(t, cues[0])

        def card(d):
            c = mix(ACCENT, INK, dim)
            d.rounded_rectangle([x0, y0, x1, y1], 30, fill=PANEL + (235,), outline=c, width=6)
            d.text((W // 2, y0 + 70), name[0], font=font(MAIN, 46), fill=mix(MUTED, INK, dim), anchor="mm")
            d.text((W // 2, y0 + 160), name[1], font=font(LATIN, 96), fill=mix(WHITE, INK, dim), anchor="mm")
        layer(im, card, a0, 30 * (1 - a0))
        for tag, at, cx in zip(tags, cues[1:3], (W // 2 - 190, W // 2 + 200)):
            a = appear(t, at)
            layer(im, lambda d, tag=tag, cx=cx: pill(d, cx, y0 + 320, tag, mix(HIGHLIGHT, INK, dim), 48,
                                                     text_fill=mix(WHITE, INK, dim)), a, -30 * (1 - a))
        a3 = appear(t, cues[3], 0.4)
        layer(im, lambda d: pill(d, W // 2, y1, pulled, FILL, 50, fill=FILL, text_fill=INK), a3, -30 * (1 - a3))
        a4 = appear(t, cues[4], 0.35)
        if a4 > 0:
            def mark(d):
                f1, f2 = font(MAIN, 76), font(LATIN, 104)
                w1, w2 = d.textlength(stamp[0], font=f1), d.textlength(stamp[1], font=f2)
                left = (W - w1 - w2 - 30) / 2
                d.rounded_rectangle([left - 50, 1110, left + w1 + w2 + 80, 1300], 26, fill=PANEL + (245,), outline=HIGHLIGHT, width=7)
                d.text((left, 1205), stamp[0], font=f1, fill=WHITE, anchor="lm")
                d.text((left + w1 + 30, 1205), stamp[1], font=f2, fill=HIGHLIGHT, anchor="lm")
            if a4 > 0.95:
                glow(im, mark, 16)
            layer(im, mark, a4, -70 * (1 - a4))
        frames.append(im)
    pace_check("bug_stamp", seconds, cues, list(name) + list(tags) + [pulled] + list(stamp))
    write_rgba(frames, out)


def yes_man(out, seconds=5.2, cues=(0.2, 1.0, 1.8), ask="Am I right?", replies=("You're right!", "So right!")):
    """#A2 You ask; the AI agrees, then agrees even louder."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        layer(im, lambda d: chat_bubble(d, 640, ask, ACCENT, right=True, size=64, tag="YOU"), a, 30 * (1 - a))
        for i, (text, at) in enumerate(zip(replies, cues[1:])):
            a = appear(t, at)
            size = 64 + 16 * i
            y = 860 + i * 200
            if a > 0.95 and i == len(replies) - 1:
                glow(im, lambda d, y=y, text=text, size=size: chat_bubble(d, y, text, HIGHLIGHT + (200,), size=size), 14)
            layer(im, lambda d, y=y, text=text, size=size: chat_bubble(d, y, text, HIGHLIGHT, size=size, tag="AI"), a, 30 * (1 - a))
        frames.append(im)
    pace_check("yes_man", seconds, cues, [ask] + list(replies))
    write_rgba(frames, out)


def echo(out, seconds=7.6, cues=(0.2, 2.4, 3.6, 5.0), say="I'm right!", echoes=("Yes!", "You're right"), label="Everyone agrees"):
    """#A4 The child's own words come back from both sides, louder each time: an echo chamber."""
    n = int(seconds * FPS)
    cx, cy, px = W // 2, 900, 14
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for i, at in enumerate(cues[1:3]):  # echo walls appear with each echo
            a = appear(t, at, 0.5)
            r = 230 + 120 * i
            layer(im, lambda d, r=r: d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RAISED, width=8), a)
        a = appear(t, cues[0])
        layer(im, lambda d: (sprite(d, PERSON, cx - len(PERSON[0]) * px // 2, cy - len(PERSON) * px // 2, px, ACCENT),
                             pill(d, cx, 610, say, ACCENT, 56)), a, 30 * (1 - a))
        for i, (text, at) in enumerate(zip(echoes, cues[1:3])):
            a = appear(t, at)
            x = 250 if i == 0 else W - 250
            layer(im, lambda d, x=x, text=text, i=i: pill(d, x, cy + 30 - 90 * i, text, HIGHLIGHT, 50 + 10 * i), a,
                  30 * (1 - a))
        a = appear(t, cues[3], 0.45)
        if a > 0.95:
            glow(im, lambda d: d.text((cx, 1250), label, font=font(MAIN, 76), fill=FILL + (200,), anchor="mm"), 14)
        layer(im, lambda d: d.text((cx, 1250), label, font=font(MAIN, 76), fill=FILL, anchor="mm"), a, 30 * (1 - a))
        frames.append(im)
    pace_check("echo", seconds, cues, [say] + list(echoes) + [label])
    write_rgba(frames, out)


def safety(out, seconds=4.4, cues=(0.2, 1.0, 1.9), y_label="Safeguards", x_label="Chat length", label="Weakens"):
    """#A5 Safety falls as the chat gets longer; a moon marks late night."""
    n = int(seconds * FPS)
    x0, x1, base, top = 190, 900, 1250, 720
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        layer(im, lambda d: (d.line([(x0, top - 40), (x0, base), (x1 + 20, base)], fill=MUTED, width=5),
                             d.text((x0 - 20, top - 90), y_label, font=font(MAIN, 52), fill=WHITE, anchor="lm"),
                             d.text((x1 + 20, base + 55), x_label, font=font(MAIN, 46), fill=MUTED, anchor="rm")), a)
        u = ease((t - cues[1]) / 1.4)
        if u > 0:
            pts = [(x0 + 20 + (x1 - x0 - 20) * i / 100, top + 20 + (base - 80 - top) * ease(i / 100) ** 0.8)
                   for i in range(int(100 * u) + 1)]
            if len(pts) > 1:
                glow(im, lambda d: d.line(pts, fill=HIGHLIGHT + (255,), width=12, joint="curve"), 12)
        a = appear(t, cues[2], 0.45)
        layer(im, lambda d: (d.text((W // 2 + 110, 860), label, font=font(MAIN, 80), fill=FILL, anchor="mm"),
                             sprite(d, MOON, x1 - 60, base - 250, 12, ACCENT)), a, 30 * (1 - a))
        frames.append(im)
    pace_check("safety", seconds, cues, [y_label, x_label, label])
    write_rgba(frames, out)


def sort_secrets(out, seconds=9.0, cues=(0.3, 3.6, 4.4, 5.6, 6.4), left="Tell AI", right="Tell a person",
                 items=(("Research", 0), ("English", 0), ("Secrets", 1), ("Worries", 1))):
    """#A6 Two columns: what's fine to tell AI, and what only goes to a real person."""
    n = int(seconds * FPS)
    xs, colours = (W // 2 - 250, W // 2 + 250), (ACCENT, HIGHLIGHT)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])

        def heads(d):
            for x, text, c, icon in zip(xs, (left, right), colours, (CHAT, PERSON)):
                d.rounded_rectangle([x - 220, 560, x + 220, 800], 26, fill=PANEL + (235,), outline=c, width=5)
                px = 11
                sprite(d, icon, x - len(icon[0]) * px // 2, 585, px, c)
                d.text((x, 750), text, font=font(MAIN, 56), fill=WHITE, anchor="mm")
        layer(im, heads, a, 30 * (1 - a))
        slots = [0, 0]
        for (text, side), at in zip(items, cues[1:]):
            y = 900 + slots[side] * 150
            slots[side] += 1
            a = appear(t, at, 0.4)
            layer(im, lambda d, text=text, side=side, y=y: pill(d, xs[side], y, text, colours[side], 54), a, -50 * (1 - a))
        frames.append(im)
    pace_check("sort_secrets", seconds, cues, [left, right] + [x for x, _ in items])
    write_rgba(frames, out)


def push_back(out, seconds=6.8, cues=(0.2, 1.8, 4.3), prompt="Find the biggest flaw", reply="The flaw is…",
              label="Make AI honest"):
    """#A7 You type a prompt asking AI to find the flaw; it answers honestly; Make AI honest."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        typed = min(len(prompt), int(len(prompt) * max(0.0, t - cues[0]) / 1.5))
        layer(im, lambda d: chat_bubble(d, 640, prompt, ACCENT, right=True, size=58, tag="YOU", chars=typed), a, 30 * (1 - a))
        a = appear(t, cues[1])
        layer(im, lambda d: chat_bubble(d, 880, reply, HIGHLIGHT, size=62, tag="AI"), a, 30 * (1 - a))
        a = appear(t, cues[2], 0.45)
        if a > 0.95:
            glow(im, lambda d: pill(d, W // 2, 1180, label, FILL, 66, fill=FILL, text_fill=INK), 14)
        layer(im, lambda d: pill(d, W // 2, 1180, label, FILL, 66, fill=FILL, text_fill=INK), a, 30 * (1 - a))
        frames.append(im)
    pace_check("push_back", seconds, cues, [prompt, reply, label])
    write_rgba(frames, out)


def real_people(out, seconds=5.2, cues=(0.2, 1.0, 1.8, 2.6), header="Ask a person",
                items=(("Feeling low", SAD), ("Safety", SHIELD), ("Health", PERSON))):
    """#A8 Three kinds of trouble, each pointing up to Ask a person."""
    n = int(seconds * FPS)
    cw, gap, top = 290, 25, 860
    x0 = (W - 3 * cw - 2 * gap) // 2
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        if a > 0.95:
            glow(im, lambda d: d.text((W // 2, 640), header, font=font(MAIN, 92), fill=FILL + (200,), anchor="mm"), 14)
        layer(im, lambda d: d.text((W // 2, 640), header, font=font(MAIN, 92), fill=FILL, anchor="mm"), a, 30 * (1 - a))
        for i, ((name, icon), at) in enumerate(zip(items, cues[1:])):
            a = appear(t, at, 0.4)
            x = x0 + i * (cw + gap)

            def card(d, x=x, name=name, icon=icon):
                d.line([(x + cw // 2, top - 20), (x + cw // 2, 740)], fill=MUTED, width=4)
                d.rounded_rectangle([x, top, x + cw, top + 330], 24, fill=PANEL + (235,), outline=HIGHLIGHT, width=5)
                px = 13
                sprite(d, icon, x + (cw - len(icon[0]) * px) // 2, top + 45, px, HIGHLIGHT)
                d.text((x + cw // 2, top + 270), name, font=font(MAIN, 60), fill=WHITE, anchor="mm")
            layer(im, card, a, 40 * (1 - a))
        frames.append(im)
    pace_check("real_people", seconds, cues, [header] + [x for x, _ in items])
    write_rgba(frames, out)


# ---------------------------------------------------------------- set 7: dinner-table questions
MEDAL = ["#.....#", "##...##", ".#####.", "..###..", ".#####.", "##...##", "#.###.#", "#.#.#.#", "##...##", ".#####."]
COIN = ["..#####..", ".#######.", "###.#.###", "##.....##", "###.#.###", "####.####", "##.....##", "###.#.###",
        ".#######.", "..#####.."]


def strike_pill(d, cx, cy, text, colour, size, u):
    box = pill(d, cx, cy, text, mix(colour, MUTED, u), size)
    if u > 0:
        d.line([(box[0] + 20, cy), (box[0] + 20 + (box[2] - box[0] - 40) * u, cy)], fill=HIGHLIGHT, width=7)


def dull_chat(out, seconds=9.0, cues=(0.3, 1.5, 4.0, 4.8, 5.6), ask="How was school?", reply="Fine",
              tags=("Specific", "Curious", "No judging")):
    """#A1 The usual dinner question gets 'Fine'; then what a good question needs: three tags."""
    n = int(seconds * FPS)
    xs = (W // 2 - 300, W // 2, W // 2 + 300)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        layer(im, lambda d: chat_bubble(d, 620, ask, ACCENT, size=64), a, 30 * (1 - a))
        a = appear(t, cues[1])
        layer(im, lambda d: chat_bubble(d, 820, reply, MUTED, right=True, size=64), a, 30 * (1 - a))
        for x, tag, at in zip(xs, tags, cues[2:]):
            a = appear(t, at)
            if a > 0.95:
                glow(im, lambda d, x=x, tag=tag: pill(d, x, 1150, tag, FILL, 60), 12)
            layer(im, lambda d, x=x, tag=tag: pill(d, x, 1150, tag, FILL, 60), a, 30 * (1 - a))
        frames.append(im)
    pace_check("dull_chat", seconds, cues, [ask, reply] + list(tags))
    write_rgba(frames, out)


def three_cards(out, seconds=9.0, cues=(0.3, 2.3, 4.6), cards=(("01", "Nobel", MEDAL, FILL), ("02", "Billionaire", COIN, ACCENT),
                                                                ("03", "AI era", CHAT, HIGHLIGHT))):
    """#A2 Three cards, one per question: a Nobel prize, a billionaire, the AI age."""
    n = int(seconds * FPS)
    cw, gap = 310, 25
    x0, y0 = (W - 3 * cw - 2 * gap) // 2, 700
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for i, ((num, name, icon, col), at) in enumerate(zip(cards, cues)):
            a = appear(t, at, 0.4)
            x = x0 + i * (cw + gap)

            def card(d, x=x, num=num, name=name, icon=icon, col=col):
                d.rounded_rectangle([x, y0, x + cw, y0 + 440], 24, fill=PANEL + (235,), outline=col, width=5)
                d.text((x + 28, y0 + 44), num, font=font(LATIN, 40), fill=col, anchor="lm")
                px = 15
                sprite(d, icon, x + (cw - len(icon[0]) * px) // 2, y0 + 110, px, col)
                d.text((x + cw // 2, y0 + 370), name, font=font(MAIN, 60), fill=WHITE, anchor="mm")
            layer(im, card, a, 40 * (1 - a))
        frames.append(im)
    pace_check("three_cards", seconds, cues, [c[1] for c in cards])
    write_rgba(frames, out)


def answer_vs_question(out, seconds=7.0, cues=(0.3, 2.4), rows=(("Answers", "AI: 1 sec", ACCENT), ("Questions", "Kids' own", HIGHLIGHT))):
    """#A4 Answers: AI gives them in a second. A good question: only the child can ask it."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for i, ((left, right, col), at) in enumerate(zip(rows, cues)):
            a = appear(t, at, 0.4)
            y = 720 + i * 300
            last = i == len(rows) - 1

            def row(d, y=y, left=left, right=right, col=col):
                d.rounded_rectangle([110, y, 430, y + 200], 26, fill=PANEL + (235,), outline=col, width=5)
                d.text((270, y + 100), left, font=font(MAIN, 68), fill=WHITE, anchor="mm")
                d.line([(460, y + 100), (560, y + 100)], fill=MUTED, width=6)
                d.polygon([(560, y + 82), (590, y + 100), (560, y + 118)], fill=MUTED)
                d.text((620, y + 100), right, font=font(MAIN, 72), fill=col, anchor="lm")
            if last and a > 0.95:
                glow(im, row, 14)
            layer(im, row, a, 30 * (1 - a))
        frames.append(im)
    pace_check("answer_vs_question", seconds, cues, [x for r in rows for x in r[:2]])
    write_rgba(frames, out)


def failure_view(out, seconds=10.0, cues=(0.3, 2.5, 4.3, 6.2), title="Study 2016", wrong="How they see smarts", right="How they see failure",
                 result="Skills can grow"):
    """#A5 What shapes a child's belief that ability can grow: not how parents see smartness, but how they see failure."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        layer(im, lambda d: d.text((W // 2, 590), title, font=font(MAIN, 70), fill=WHITE, anchor="mm"), a)
        a = appear(t, cues[1])
        u = ease((t - cues[2]) / 0.4)
        layer(im, lambda d: strike_pill(d, W // 2, 740, wrong, ACCENT, 64, u), a, 30 * (1 - a))
        a = appear(t, cues[2], 0.4)
        if a > 0.95:
            glow(im, lambda d: pill(d, W // 2, 940, right, HIGHLIGHT, 72), 14)
        layer(im, lambda d: pill(d, W // 2, 940, right, HIGHLIGHT, 72), a, 30 * (1 - a))
        a = appear(t, cues[3], 0.45)
        layer(im, lambda d: (d.line([(W // 2, 1025), (W // 2, 1110)], fill=MUTED, width=5),
                             d.polygon([(W // 2 - 18, 1105), (W // 2 + 18, 1105), (W // 2, 1135)], fill=MUTED),
                             d.text((W // 2, 1215), result, font=font(MAIN, 80), fill=FILL, anchor="mm")), a, 30 * (1 - a))
        frames.append(im)
    pace_check("failure_view", seconds, cues, [title, wrong, right, result])
    write_rgba(frames, out)


def confident_wrong(out, seconds=6.0, cues=(0.3, 2.0), answer="Obviously it's this!", stamp="Wrong, confidently"):
    """#A7 A confident AI answer, then a stamp: Wrong, confidently."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])

        def ai(d):
            chat_bubble(d, 660, answer, HIGHLIGHT, size=64, tag="AI")
            for j, wbar in enumerate((640, 520, 580)):  # the rest of its long answer as grey lines
                d.rounded_rectangle([110, 860 + j * 56, 110 + wbar, 860 + j * 56 + 24], 12, fill=RAISED)
        layer(im, ai, a, 30 * (1 - a))
        a = appear(t, cues[1], 0.3)
        if a > 0:
            def mark(d):
                f = font(MAIN, 76)
                w = d.textlength(stamp, font=f)
                d.rounded_rectangle([(W - w) / 2 - 50, 1100, (W + w) / 2 + 50, 1270], 22, fill=PANEL + (245,),
                                    outline=FILL, width=7)
                d.text((W // 2, 1185), stamp, font=f, fill=FILL, anchor="mm")
            if a > 0.95:
                glow(im, mark, 14)
            layer(im, mark, a, -60 * (1 - a))
        frames.append(im)
    pace_check("confident_wrong", seconds, cues, [answer, stamp])
    write_rgba(frames, out)


def two_skills(out, seconds=6.0, cues=(0.3, 1.6, 2.6), left="Use AI", right="Judge AI", note="Two skills"):
    """#A8 Using AI and judging AI are two different skills."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        a = appear(t, cues[0])
        layer(im, lambda d: pill(d, W // 2, 700, left, ACCENT, 76), a, 30 * (1 - a))
        a = appear(t, cues[1])
        layer(im, lambda d: d.text((W // 2, 860), "≠", font=font(LATIN, 120), fill=MUTED, anchor="mm"), a)
        a2 = appear(t, cues[1] + 0.4, 0.4)
        if a2 > 0.95:
            glow(im, lambda d: pill(d, W // 2, 1020, right, HIGHLIGHT, 76), 14)
        layer(im, lambda d: pill(d, W // 2, 1020, right, HIGHLIGHT, 76), a2, 30 * (1 - a2))
        a = appear(t, cues[2])
        layer(im, lambda d: d.text((W // 2, 1210), note, font=font(MAIN, 64), fill=FILL, anchor="mm"), a, 30 * (1 - a))
        frames.append(im)
    pace_check("two_skills", seconds, cues, [left, right, note])
    write_rgba(frames, out)


def judge_bulb(out, seconds=8.0, cues=(0.3, 1.8, 3.6), asks=("Which line is off?", "How do you know?"), result="Judgment"):
    """#A9 Two follow-up questions run down into one lit bulb: Judgment."""
    n = int(seconds * FPS)
    ys, by = (620, 780), 900
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for i, (q, at) in enumerate(zip(asks, cues)):
            a = appear(t, at)
            layer(im, lambda d, q=q, i=i: pill(d, W // 2 + (-110 if i == 0 else 110), ys[i], q, ACCENT, 56), a, 30 * (1 - a))
        u = ease((t - cues[2]) / 0.6)
        if u > 0:
            layer(im, lambda d: d.line([(W // 2, 840), (W // 2, 840 + (by + 30 - 840) * u)], fill=MUTED, width=5))
        on = ease((t - cues[2] - 0.5) / 0.5)
        if on > 0:
            px = 20
            bx = W // 2 - len(BULB[0]) * px // 2
            glow(im, lambda d: sprite(d, BULB, bx, by + 40, px, FILL + (round(255 * on),)), 26)
            layer(im, lambda d: (sprite(d, BULB, bx, by + 40, px, FILL),
                                 d.text((W // 2, by + 330), result, font=font(MAIN, 80), fill=WHITE, anchor="mm")), on)
        frames.append(im)
    pace_check("judge_bulb", seconds, cues, list(asks) + [result])
    write_rgba(frames, out)


def listen_first(out, seconds=8.0, cues=(0.3, 1.3, 3.2), donts=("No judging", "No lecture"), result=("Wants to talk", "Right")):
    """#A10 Don't judge, don't lecture; the child wanting to talk matters more than being right."""
    n = int(seconds * FPS)
    frames = []
    for k in range(n):
        t = k / FPS
        im = frame_rgba()
        for i, (txt, at) in enumerate(zip(donts, cues)):
            a = appear(t, at)
            u = ease((t - at - 0.5) / 0.4)
            layer(im, lambda d, txt=txt, i=i, u=u: strike_pill(d, W // 2 + (-220 if i == 0 else 220), 700, txt, ACCENT, 60, u),
                  a, 30 * (1 - a))
        a = appear(t, cues[2], 0.45)
        if a > 0:
            def big(d):
                f = font(MAIN, 92)
                w1, w2 = d.textlength(result[0], font=f), d.textlength(result[1], font=f)
                gt = 120
                left = (W - w1 - w2 - gt) / 2
                d.text((left, 1000), result[0], font=f, fill=FILL, anchor="lm")
                d.text((left + w1 + gt / 2, 1000), ">", font=font(LATIN, 110), fill=WHITE, anchor="mm")
                d.text((left + w1 + gt, 1000), result[1], font=f, fill=MUTED, anchor="lm")
            if a > 0.95:
                glow(im, big, 14)
            layer(im, big, a, 30 * (1 - a))
        frames.append(im)
    pace_check("listen_first", seconds, cues, list(donts) + list(result))
    write_rgba(frames, out)


if __name__ == "__main__":
    VID = pathlib.Path(sys.argv[1]).resolve()
    names = sys.argv[2:] or ["frontier", "process_vs_result"]
    for name in names:
        target = VID / "broll" / f"anim_{name}.mp4"
        globals()[name](target)
