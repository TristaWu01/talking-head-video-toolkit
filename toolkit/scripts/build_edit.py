"""Build the edit for one video: cut list -> pass 1 (cuts, speed-up, voice) -> subtitles/overlays -> pass 2 (final).

Usage: python -I build_edit.py <video folder> <version> [--plan | --dry | --redo]
  --plan  stop after the cut list (prints the length)
  --dry   also write subtitles/overlays, but render nothing
  --redo  re-render pass 1 even if it exists
Everything specific to a video comes from <video folder>/video.toml.
"""
import json, pathlib, re, subprocess, sys, tomllib, wave

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import *  # noqa: E402,F401,F403  (styling helpers and paths)

VID = pathlib.Path(sys.argv[1]).resolve()
VERSION = sys.argv[2]
CFG = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))
LANG = language(CFG)    # library/language/<code>.toml
PROFILE = profile()     # library/brand/profile.toml: your handle and bio card
T = VID / "work" / "transcript"
EDIT = VID / "work" / "edit" / VERSION
EDIT.mkdir(parents=True, exist_ok=True)
OUT_DIR = VID / "exports" / VERSION
# A finished video is never written over: each new render is a new version (v2, v3...).
if (OUT_DIR / f"{CFG['title']}_{VERSION}.mp4").exists() and not ({"--plan", "--dry"} & set(sys.argv)):
    taken = {d.name for d in (VID / "exports").iterdir()}
    nxt = next(f"v{k}" for k in range(2, 100) if f"v{k}" not in taken)
    sys.exit(f"{VERSION} is already finished; it is never written over. Render a new version instead, e.g. {nxt}.")
TITLE = CFG["title"]


def asset(name):
    """A file named in video.toml: this video's folder first, then the shared library."""
    for base in (VID, LIBRARY):
        if (base / name).exists():
            return base / name
    raise FileNotFoundError(name)


def media():
    """Audio start and length of the footage, cached so the footage can be deleted after the edit."""
    cache = VID / "work" / "media.json"
    if not cache.exists():
        src = next(f for f in sorted((VID / "footage").iterdir()) if not f.name.startswith("."))

        def probe(*args):
            return float(subprocess.run([FFPROBE, "-v", "error", *args, "-of", "csv=p=0", str(src)],
                                        capture_output=True, text=True).stdout)
        cache.write_text(json.dumps(dict(source=src.name, audio_start=probe("-select_streams", "a:0", "-show_entries", "stream=start_time"),
                                         duration=probe("-show_entries", "format=duration"))))
    m = json.loads(cache.read_text())
    return VID / "footage" / m["source"], m["audio_start"], m["duration"]


SRC, AUDIO_START, SRC_DURATION = media()

SPEED = CFG.get("speed", 1.2)  # playback speed for this video
FPS = 30
END_HOLD = 3.4          # seconds the end card stays up after your last word (output time)

# ---------------------------------------------------------------- cut list
# Repeated takes: drop every word that starts inside these source ranges (the last take is kept).
REMOVE = [tuple(r) for r in CFG["cut"]["remove"]]
# exact audio to cut (seconds), for takes Whisper timed badly; words are still dropped with `remove`
EXACT = [tuple(r) for r in CFG["cut"].get("exact", [])]
FILLERS = set(LANG.get("fillers", []))  # um / uh sounds, dropped from the cut
HEAD_PAD, TAIL_PAD = 0.06, 0.10     # kept around each phrase
MAX_GAP = 0.15                      # pauses up to this long stay as they are
SENTENCE_PAUSE = 0.18               # a longer pause after a sentence becomes this
PHRASE_PAUSE = 0.10                 # a longer pause mid-sentence becomes this
SILENCE_DB, SILENCE_MIN = -42, 0.22  # silences inside a phrase longer than this get shortened
TAIL_GRACE = 0.30                   # a phrase end may run on this far while the voice is still audible

# The phone starts recording sound a little after the picture (AUDIO_START, about 0.7 s). All
# transcript times are audio times, so pass 1 shifts both streams to start where the audio does.
MUSIC_DB, SFX_BOOST = -15, 5        # background music level; extra dB on every sound effect
SFX = {k: LIBRARY / "sound_effects" / f for k, f in dict(
    whoosh="whoosh.mp3", pop="pop.mp3", glitch="glitch.mp3", ding="ding.mp3", click="click.mp3").items()}  # see library/sound_effects/README.md

words = [dict(t0=w["start"], t1=w["end"], raw=w["word"], seg=k)
         for k, s in enumerate(json.load(open(T / "transcript.json"))["segments"]) for w in s["words"]]
seg_ends = {round(s["end"], 2) for s in json.load(open(T / "transcript.json"))["segments"]}
for w in words:
    w["end_sentence"] = bool(re.search(r"[。？！?!,，]$", w["raw"].strip())) or round(w["t1"], 2) in seg_ends
    w["stop"] = bool(re.search(r"[。？！?!]$", w["raw"].strip())) or round(w["t1"], 2) in seg_ends  # a full stop, not a comma

kept = [w for w in words
        if not any(a <= w["t0"] < b for a, b in REMOVE) and w["raw"].strip() not in FILLERS]
LAST_WORD_END = kept[-1]["t1"]

# phrase intervals from word timings
intervals = []
for i, w in enumerate(kept):
    if i == 0:
        intervals.append([max(0.0, w["t0"] - HEAD_PAD), w["t1"]])
        continue
    prev = kept[i - 1]
    gap = w["t0"] - prev["t1"]
    if gap <= MAX_GAP and not any(prev["t1"] <= a < w["t0"] for a, _ in REMOVE):
        intervals[-1][1] = w["t1"]
    else:
        pause = SENTENCE_PAUSE if prev["end_sentence"] else PHRASE_PAUSE
        tail = min(TAIL_PAD + max(0, pause - HEAD_PAD - TAIL_PAD), gap / 2) if gap > 0 else 0
        intervals[-1][1] = prev["t1"] + tail
        intervals.append([max(intervals[-1][1], w["t0"] - HEAD_PAD), w["t1"]])
intervals[-1][1] = LAST_WORD_END + TAIL_PAD

# shorten long silences hidden inside words (hesitations Whisper folded into a word)
wav = wave.open(str(T / "audio16k.wav"))
sr = wav.getframerate()
pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768
HOP = 0.02
n = len(pcm) // int(HOP * sr)
level = 20 * np.log10(np.sqrt((pcm[:n * int(HOP * sr)].reshape(n, -1) ** 2).mean(1)) + 1e-9)
# "audible" is judged against this recording's own background noise, so soft starts aren't taken for silence
SILENCE_DB = min(SILENCE_DB, float(np.percentile(level, 10)) + 8)


def split_silences(a, b):
    out, start = [], a
    i0, i1 = int(a / HOP), int(b / HOP)
    quiet = level[i0:i1] < SILENCE_DB
    i = 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            s0, s1 = a + i * HOP, a + j * HOP
            if s1 - s0 > SILENCE_MIN and s0 > a + 0.1 and s1 < b - 0.1:
                out.append([start, s0 + 0.10])
                start = s1 - 0.10
            i = j
        else:
            i += 1
    out.append([start, b])
    return out


# Whisper often ends a word before its last syllable fades: run on while the voice is still audible
def audible(t):
    i = int(t / HOP)
    return i < len(level) and level[i] > SILENCE_DB


for k, iv in enumerate(intervals):
    limit = min(iv[1] + TAIL_GRACE, intervals[k + 1][0] if k + 1 < len(intervals) else iv[1] + TAIL_GRACE)
    while iv[1] < limit and audible(iv[1]):
        iv[1] = min(iv[1] + HOP, limit)
# ...and Whisper often starts a word late: a phrase may also start earlier while the voice is already audible,
# but never reaching back into the previous piece or into a removed take
for k, iv in enumerate(intervals):
    limit = max([iv[0] - TAIL_GRACE, intervals[k - 1][1] if k else 0.0] + [min(b, iv[0]) for a, b in REMOVE + EXACT if a < iv[0]])
    while iv[0] - HOP > limit and audible(iv[0] - HOP):
        iv[0] = max(iv[0] - HOP, limit)
intervals = [piece for a, b in intervals for piece in split_silences(a, b)]


# trim quiet at the edges of each piece so the joins stay tight
def trim(a, b, lead=0.08, lag=0.10):
    s0, s1 = a, b
    while s0 < b - 0.1 and not audible(s0):
        s0 += HOP
    while s1 > s0 + 0.1 and not audible(s1 - HOP):
        s1 -= HOP
    return [max(a, s0 - lead), min(b, s1 + lag)]


intervals = [trim(a, b) for a, b in intervals]
# end-card tail: the shot after your last word (voice muted there)
TAIL_SRC = (intervals[-1][1], min(intervals[-1][1] + 2.4, SRC_DURATION - AUDIO_START))

# snap to the frame grid so picture and sound cut at the same instant
for x0, x1 in EXACT:  # take the exact ranges out of the pieces
    intervals = [piece for a, b in intervals for piece in ((a, min(b, x0)), (max(a, x1), b)) if piece[1] - piece[0] > 0.02]
    intervals = [list(iv) for iv in intervals]
intervals = [[round(a * FPS) / FPS, round(b * FPS) / FPS] for a, b in intervals]
intervals = [iv for iv in intervals if iv[1] - iv[0] >= 1 / FPS]
tail = [round(TAIL_SRC[0] * FPS) / FPS, round(TAIL_SRC[1] * FPS) / FPS]
if tail[0] < intervals[-1][1]:
    tail[0] = intervals[-1][1]
all_iv = intervals + [tail]

# source time -> output time
offsets, acc = [], 0.0
for a, b in all_iv:
    offsets.append(acc)
    acc += b - a
CUT_LEN = acc


def to_out(t):
    for (a, b), off in zip(all_iv, offsets):
        if t < a:
            return off / SPEED
        if t <= b:
            return (off + t - a) / SPEED
    return CUT_LEN / SPEED


SPEECH_END = to_out(intervals[-1][1])
TOTAL = SPEECH_END + END_HOLD
json.dump(dict(intervals=all_iv, speech_end=SPEECH_END, total=TOTAL), open(EDIT / "cutlist.json", "w"), indent=1)
print(f"{len(intervals)} pieces kept; {sum(b - a for a, b in intervals):.1f}s of the {SRC_DURATION:.0f}s source -> "
      f"{SPEECH_END:.1f}s at {SPEED}x, {TOTAL:.1f}s with end card")
if "--plan" in sys.argv:
    sys.exit()

# ---------------------------------------------------------------- pass 1: cut, speed, voice
voice = EDIT / "pass1.mov"


def render_pass1():
    if not voice.exists() or "--redo" in sys.argv:
        terms = [f"between(t,{a - 0.5 / FPS:.4f},{b - 0.5 / FPS:.4f})" for a, b in intervals]
        # ffmpeg's expression parser runs out of room on a long flat sum, so add them up in groups
        sel = asel = "+".join("(" + "+".join(terms[i:i + 10]) + ")" for i in range(0, len(terms), 10))
        sel_tail = f"between(t,{tail[0] - 0.5 / FPS:.4f},{tail[1] - 0.5 / FPS:.4f})"
        rnn = TOOLKIT / "models" / "rnnoise" / "cb.rnnn"
        fc = (
            f"[0:v]setpts=PTS-{AUDIO_START:.6f}/TB,fps={FPS},select='{sel}+{sel_tail}',setpts=N/{FPS}/TB,setpts=PTS/{SPEED},fps={FPS},"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v];"  # any phone size -> 1080x1920
            # voice: same pieces; the end-card tail is kept but silent
            f"[0:a]aresample=48000,asetpts=PTS-{AUDIO_START:.6f}/TB,pan=mono|c0=0.5*c0+0.5*c1,asetnsamples=n=1600:p=0,"
            f"volume=enable='{sel_tail}':volume=0,aselect='{asel}+{sel_tail}',asetpts=N/SR/TB,"
            f"highpass=f=80,arnndn=m={rnn},"
            f"equalizer=f=250:t=q:w=1.2:g=-2.5,equalizer=f=3200:t=q:w=1.5:g=2.5,equalizer=f=9000:t=q:w=1:g=1.5,"
            f"acompressor=threshold=-24dB:ratio=3:attack=8:release=120:makeup=2,"
            f"atempo={SPEED}[a]"
        )
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-stats", "-y", "-i", str(SRC),
                        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p",
                        "-c:a", "pcm_s24le", str(voice)], check=True)

    # measure the voice so the final mix lands at -14 LUFS (RedNote/Douyin level)
    meas = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(voice), "-map", "0:a",
                           "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    voice_lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", meas)[-1])
    print(f"voice after processing: {voice_lufs:.1f} LUFS -> gain {-14.5 - voice_lufs:+.1f} dB")
    return -14.5 - voice_lufs


# ---------------------------------------------------------------- subtitles text
REPLACE = [tuple(r) for r in CFG["subtitles"]["replace"]]  # Whisper's mishearings, fixed from the script

# tokens: Latin words stay whole; Chinese splits into characters with evenly shared timing
tokens = []
for w in kept:
    raw = w["raw"]
    clean = re.sub(r"[，。,.？?！!、：:；;]", "", raw.strip())
    punct = raw.strip()[-1] if raw.strip() and raw.strip()[-1] in "，。,.？?！!" else ""
    if not clean:
        continue
    if re.search(r"[A-Za-z]", clean):
        tokens.append(dict(text=(" " if raw.startswith(" ") and tokens and re.search(r"[A-Za-z]$", tokens[-1]["text"]) else "") + clean,
                           t0=w["t0"], t1=w["t1"], ws=True, brk=w["end_sentence"], stop=w["stop"], seg=w["seg"], q=punct != "" and punct in "？?"))
    else:
        d = (w["t1"] - w["t0"]) / len(clean)
        for k, ch in enumerate(clean):
            last = k == len(clean) - 1
            tokens.append(dict(text=ch, t0=w["t0"] + k * d, t1=w["t0"] + (k + 1) * d, ws=k == 0,
                               brk=last and w["end_sentence"], stop=last and w["stop"], seg=w["seg"], q=last and punct != "" and punct in "？?"))



def rewrite(tokens, pairs, keep=(), report=None):
    """Rewrite words across tokens (old -> new); a match inside a kept phrase is left alone."""
    joined = "".join(t["text"] for t in tokens)
    for old, new in pairs:
        kept_spans = [(m.start(), m.end()) for k in keep for m in re.finditer(re.escape(k), joined)]
        for m in reversed(list(re.finditer(re.escape(old), joined, flags=re.I))):
            if any(a <= m.start() and m.end() <= b for a, b in kept_spans):
                continue
            # map the match back onto tokens and rewrite them
            pos, idx = 0, []
            for i, t in enumerate(tokens):
                if pos + len(t["text"]) > m.start() and pos < m.end():
                    idx.append(i)
                pos += len(t["text"])
            before = "".join(tokens[i]["text"] for i in idx)
            tokens[idx[0]]["text"] = re.sub(re.escape(old), lambda _: new, before, count=1, flags=re.I)
            for i in idx[1:]:
                tokens[i]["text"] = ""
            if report is not None:
                report.append(f"「{old}」→「{new}」 in 「{joined[max(0, m.start() - 8):m.end() + 8]}」")
        joined = "".join(t["text"] for t in tokens)
    return [t for t in tokens if t["text"]]


tokens = rewrite(tokens, REPLACE)

# platform sensitive words stay out of the subtitles (the voice is unchanged): see library/platform/sensitive_words.toml
SENSITIVE = tomllib.loads((LIBRARY / "platform" / CFG.get("platform_words", "sensitive_words.toml")).read_text(encoding="utf-8"))
KEEP = CFG["subtitles"].get("keep", [])  # words or phrases this video keeps on purpose
SENSITIVE["hide"] = SENSITIVE["hide"] + CFG["subtitles"].get("hide", [])  # extra words this video removes


def plain(text):
    return text.replace(" ", "").lower()


censored = []  # what was hidden, for the report
joined = "".join(t["text"] for t in tokens)
kept_spans = [(m.start(), m.end()) for k in KEEP for m in re.finditer(re.escape(k), joined)]
remove = set()  # character positions of sensitive words, longest words first
for w in sorted(SENSITIVE["hide"], key=len, reverse=True):
    if w in KEEP:
        continue
    for m in re.finditer(re.escape(w), joined, flags=re.I):
        span = set(range(m.start(), m.end()))
        if span & remove or any(a <= m.start() and m.end() <= b for a, b in kept_spans):
            continue
        remove |= span
        censored.append(f"「{w}」 in 「{joined[max(0, m.start() - 8):m.end() + 8]}」")
pos = 0
for t in tokens:
    n = len(t["text"])
    if any(pos + k in remove for k in range(n)):
        t["text"] = "".join(ch for k, ch in enumerate(t["text"]) if pos + k not in remove)
    pos += n
for i, t in enumerate(tokens):  # an emptied token hands its line-break flags on
    if not t["text"].strip():
        prev = next((x for x in reversed(tokens[:i]) if x["text"].strip()), None)
        nxt = next((x for x in tokens[i + 1:] if x["text"].strip()), None)
        if prev:
            prev["brk"] |= t["brk"]
            prev["stop"] |= t["stop"]
            prev["q"] |= t["q"]
        if nxt and t["ws"]:
            nxt["ws"] = True
tokens = [t for t in tokens if t["text"].strip()]
# swapped words (sensitive_words.toml swap, plus this video's [subtitles] swap): a flagged word -> a respelling
SWAP = [tuple(s) for s in SENSITIVE.get("swap", []) + CFG["subtitles"].get("swap", []) if s[0] not in KEEP]
swapped = []
tokens = rewrite(tokens, sorted(SWAP, key=lambda s: len(s[0]), reverse=True), KEEP, swapped)

# line breaks only between words: Whisper often gives single characters, so mark word starts with jieba
import jieba  # noqa: E402
jieba.setLogLevel(60)
jieba.dt.tmp_dir = str(TOOLKIT / "models")  # keep its cache inside the project
for w in [*LANG.get("whole_words", []), *PROFILE.get("whole_words", []), *CFG["subtitles"].get("keywords", []),
          *CFG["subtitles"].get("whole", [])]:  # keep these whole (whole = [...]: names a line must not split)
    jieba.add_word(w)
starts, pos = set(), 0
for w in jieba.cut("".join(t["text"] for t in tokens)):
    starts.add(pos)
    pos += len(w)
pos = 0
for t in tokens:
    t["ws"] = pos in starts or t["text"].startswith(" ")
    pos += len(t["text"])
for what in censored:
    print("hidden from subtitles:", what)
for what in swapped:
    print("swapped in subtitles:", what)

KEYWORDS = CFG["subtitles"]["keywords"]

designed = [CFG.get("hook", {}).get("title", ""), CFG.get("hook", {}).get("answer", "")]
designed += [p["text"] for p in CFG.get("popups", [])] + [p.get("caption", "") for p in CFG.get("photos", [])]
designed += [CFG.get("cover", {}).get(k, "") for k in ("tag", "headline", "line1", "line2")]
for text in designed:
    for w in SENSITIVE["hide"]:
        if w not in KEEP and plain(w) in plain(re.sub(r"[\[\]{}]", "", text)):
            print(f"WARNING: on-screen text 「{text}」 contains the sensitive word 「{w}」")
    for w, new in SWAP:
        if plain(w) in plain(re.sub(r"[\[\]{}]", "", text)):
            print(f"WARNING: on-screen text 「{text}」 contains 「{w}」; write it as 「{new}」")

SUB_SIZE, KEY_SIZE = 66, 80
SUB_LEAD = 0.10  # show each subtitle this much before the first word (measured lag was +0.10 s)
LINE_MAX = 800   # px of text per line (panel stays inside the frame)


def phrase_breaks():
    """Group tokens into phrases at sentence ends, punctuation and pauses."""
    phrases, cur = [], []
    for i, t in enumerate(tokens):
        cur.append(t)
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        gap = (nxt["t0"] - t["t1"]) if nxt else 99
        if t["brk"] or gap > 0.18 or nxt is None:
            phrases.append(cur)
            cur = []
    return phrases


def width_of(toks):
    return text_width("".join(t["text"] for t in toks), MAIN, SUB_SIZE) * 1.08  # room for bigger key words


def keyword_inside(toks):
    """Token indexes that sit inside a key word (a line may not start there)."""
    text, starts, pos = "", [], 0
    for t in toks:
        starts.append(pos)
        pos += len(t["text"])
        text += t["text"]
    inside = set()
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            inside |= {i for i, s in enumerate(starts) if m.start() < s < m.end()}
    return inside


def layout(phrases):
    """Lay phrases out on at most 2 lines; returns the lines or None if they don't fit.
    Breaks go between phrases if possible, else between Whisper's words, never inside a key word."""
    toks = [t for ph in phrases for t in ph]
    if width_of(toks) <= LINE_MAX:
        return [toks]
    phrase_starts, n = set(), 0
    for ph in phrases:
        phrase_starts.add(n)
        n += len(ph)
    blocked = keyword_inside(toks)
    best = None
    for k in range(1, len(toks)):
        if k in blocked or not toks[k]["ws"] or toks[k]["text"][0] in LANG.get("no_line_start", ""):  # no line starts with a particle
            continue
        a, b = toks[:k], toks[k:]
        if width_of(a) > LINE_MAX or width_of(b) > LINE_MAX:
            continue
        score = abs(width_of(a) - width_of(b)) - (10_000 if k in phrase_starts else 0)
        if best is None or score < best[0]:
            best = (score, k)
    return [toks[:best[1]], toks[best[1]:]] if best else None


def dur(phrases):
    return to_out(phrases[-1][-1]["t1"]) - to_out(phrases[0][0]["t0"])


def is_short(g):
    return dur(g) < 1.0 or sum(len(t["text"]) for p in g for t in p) <= 3


def ends_sentence(g):
    return g[-1][-1]["stop"]


def tail_of(before, g):
    """g is the short end of the sentence that `before` starts ("…was born | in Paris": a two-word tail)."""
    return is_short(g) and ends_sentence(g) and g[0][0]["seg"] == before[-1][-1]["seg"]


# group phrases into cards: short phrases join the next one when they fit on two lines,
# unless they are the end of the sentence before them
groups = []
for ph in phrase_breaks():
    if groups:
        prev = groups[-1]
        gap = to_out(ph[0]["t0"]) - to_out(prev[-1][-1]["t1"])
        is_tail = len(groups) > 1 and tail_of(groups[-2], prev)
        # a finished sentence followed by a long pause in the footage (a new topic, or a retake cut out
        # between them) never joins the next line ("…I'll send it. | Question three")
        new_topic = prev[-1][-1]["stop"] and ph[0]["t0"] - prev[-1][-1]["t1"] > 0.8
        if is_short(prev) and not is_tail and not new_topic and gap < 0.6 and layout(prev + [ph]):
            prev.append(ph)
            continue
    groups.append([ph])
# a very short card left over joins the one before it; so does a short sentence ending
merged = []
for g in groups:
    gap = to_out(g[0][0]["t0"]) - to_out(merged[-1][-1][-1]["t1"]) if merged else 99
    if merged and layout(merged[-1] + g) and ((dur(g) < 0.7 and gap < 0.4) or tail_of(merged[-1], g)):
        merged[-1] += g
    else:
        merged.append(g)

cards = []  # each: lines (token lists), start, end (output time)
for g in merged:
    lines = layout(g)
    if lines is None:  # one long phrase: split it over as many two-line cards as needed
        toks = [t for ph in g for t in ph]
        lines, cur = [], []
        for t in toks:
            if cur and t["ws"] and width_of(cur + [t]) > LINE_MAX:
                lines.append(cur)
                cur = []
            cur.append(t)
        lines.append(cur)
    for i in range(0, len(lines), 2):
        group = lines[i:i + 2]
        cards.append(dict(lines=group, t0=max(0.0, to_out(group[0][0]["t0"]) - SUB_LEAD), t1=to_out(group[-1][-1]["t1"]),
                          q=group[-1][-1]["q"]))
# hold each card until the next one starts (short gaps only)
for a, b in zip(cards, cards[1:]):
    a["t1"] = b["t0"] if b["t0"] - a["t1"] < 0.6 else a["t1"] + 0.25
cards[-1]["t1"] = min(cards[-1]["t1"] + 0.3, SPEECH_END)


def srt_ts(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def styled_runs(line_toks, is_last):
    text = "".join(t["text"] for t in line_toks).strip()
    runs = [("> ", ACCENT, MAIN, SUB_SIZE)]
    spans = []
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            if not any(m.start() < e and s < m.end() for s, e in spans):
                spans.append((m.start(), m.end()))
    spans.sort()
    pos = 0
    for s, e in spans:
        if s > pos:
            runs.append((text[pos:s], WHITE, MAIN, SUB_SIZE))
        runs.append((text[s:e], HIGHLIGHT, MAIN, KEY_SIZE))
        pos = e
    if pos < len(text):
        runs.append((text[pos:], WHITE, MAIN, SUB_SIZE))
    return runs, text, bool(spans)


E0 = SPEECH_END + 0.15  # end card starts
HEAD_TOP = CFG.get("head_top", 470)  # y of the top of your head in the footage
events = []

# ---------------------------------------------------------------- title, viewpoints, bio, photos
POP_IN = r"\fad(200,200)"


def popup(label, runs, t0, dur=4.0, y=None):
    w = round(max(runs_width(runs), runs_width([(label, ACCENT, LATIN if label.isascii() else MAIN, 36)])) + 2 * 40)
    x, h = (W - w) // 2, 175
    y = SAFE_TOP + 10 if y is None else y
    move = rf"\move(0,-24,0,0,0,220)"
    lab = [(label, ACCENT, LATIN, 36)] if label.isascii() else [(label, ACCENT, MAIN, 40)]
    return [rounded_rect(x, y, w, h, 12, PANEL, t0, t0 + dur, anim=move + POP_IN),
            outline_rect(x, y, w, h, 12, ACCENT, 3, t0, t0 + dur, anim=move + POP_IN),
            text_line(x + 40, y + 22, lab, t0, t0 + dur, anim=rf"\move({x+40},{y-2},{x+40},{y+22},0,220)" + POP_IN),
            text_line(x + 40, y + 152, runs, t0, t0 + dur, align=1, anim=rf"\move({x+40},{y+128},{x+40},{y+152},0,220)" + POP_IN)]


def markup(text, size=72, key_size=84, colour=WHITE):
    """'What to learn, [matters less]' -> runs, with [key words] in the highlight colour and a bit bigger."""
    runs = []
    for part in re.split(r"(\[[^]]*\])", text):
        if part.startswith("["):
            runs.append((part[1:-1], HIGHLIGHT, MAIN, key_size))
        elif part:
            runs.append((part, colour, MAIN, size))
    return runs


def when(item, at="at", after="after"):
    """Source time of the words an item in video.toml is tied to."""
    return first_word(item[at], after=item.get(after, 0.0))


def first_word(text, after=0.0):
    """Source time of the first kept word where this text starts (it may span several words)."""
    for i, w in enumerate(kept):
        if w["t0"] < after:
            continue
        joined = "".join(x["raw"].strip() for x in kept[i:i + len(text)])
        if joined.startswith(text):
            return w["t0"]
    raise ValueError(text)



def tab_left(y, w, h, r=14):
    return (f"m 0 {y} l {w - r} {y} b {w} {y} {w} {y} {w} {y + r} l {w} {y + h - r} "
            f"b {w} {y + h} {w} {y + h} {w - r} {y + h} l 0 {y + h}")


def shape(path, colour, t0, t1, layer=0, anim=""):
    return dialogue(layer, t0, t1, rf"{{\an7\pos(0,0){anim}\bord0\shad0\1c{colour}\1a&H{colour[2:4]}&\p1}}{path}")


# video title: a dark bookmark tab flush with the left edge, accent-colour strip, up the whole video
TY, tw, th, title_lines = SAFE_TOP - 50, 0, 0, []
if "top_title" in CFG:
    T_CFG = CFG["top_title"]
    if T_CFG.get("label"):
        LS = CFG.get("title_scale", 1.0) ** 0.5  # the small line grows a little with the title (34 px was hard to read)
        lab_font, lab_size = (LATIN, round(28 * LS)) if T_CFG["label"].isascii() else (MAIN, round(34 * LS))  # Chinese labels need the Chinese font
        title_lines.append(([(T_CFG["label"], ACCENT, lab_font, lab_size)], round((44 if lab_font == MAIN else 40) * LS), 7))
    # title_scale: the title reads bigger than the chips; shrunk only if it wouldn't fit the width
    TS = CFG.get("title_scale", 1.3)
    while TS > 1.0 and runs_width(markup(T_CFG["text"], round(60 * TS), round(72 * TS))) + 80 > W - 60:
        TS = round(TS - 0.05, 2)
    if TS < CFG.get("title_scale", 1.3):
        print(f"title shrunk to scale {TS} to fit the width")
    title_lines.append((markup(T_CFG["text"], round(60 * TS), round(72 * TS)), round(82 * TS), 1))
    if T_CFG.get("answer"):
        title_lines.append(([("> ", ACCENT, MAIN, 38), (T_CFG["answer"], ACCENT, MAIN, 38), (" _", ACCENT, MAIN, 38)], 50, 1))
    tw = round(max(runs_width(r) for r, _, _ in title_lines)) + 44 + 36
    th = 14 + sum(h for _, h, _ in title_lines) + 12

# viewpoints: chips down the right side, left-aligned with each other, added as you reach them; earlier ones stay
# chip_scale: bigger chips, e.g. 1.4; chips_x = "beside_title": the column starts just right of the title tab
CHIP_S = CFG.get("chip_scale", 1.0)
CHIP_H, CHIP_PAD = round(58 * CHIP_S), round(18 * CHIP_S)
CHIP_STEP = CHIP_H + 8
POINTS = [(markup(p["text"], round(36 * CHIP_S), round(40 * CHIP_S)), when(p)) for p in CFG.get("points", [])]
if "top_title" in CFG and 36 * CHIP_S >= 60 * TS:
    print(f"WARNING: chip text ({36 * CHIP_S:.0f}px) is not smaller than the title ({60 * TS:.0f}px); "
          "raise title_scale or lower chip_scale")
# a viewpoint's number is 01, 02... in order, or its own label (e.g. label = "1a" for sub-points)
chips = [[(f"{p.get('label', f'{k + 1:02d}')}  ", ACCENT, LATIN, round(28 * CHIP_S))] + runs
         for k, (p, (runs, _)) in enumerate(zip(CFG.get("points", []), POINTS))]
CHIP_X = W - 30 - round(max([runs_width(c) for c in chips], default=0) + 2 * CHIP_PAD)  # one left edge for the column
# beside the title if there's room; a long title pushes the column down under it (still on the right)
CHIP_Y0 = TY if CHIP_X >= tw + 24 else TY + th + 16
if CFG.get("chips_x") == "beside_title" and CHIP_Y0 == TY:
    CHIP_X = tw + 24
# points_layout = "grid": two equal columns right under the title, full width (01 02 / 03 04)
GRID = CFG.get("points_layout", "column") == "grid"
GRID_W = (W - 60 - 16) // 2


def chip_box(k, c):
    """x, y, width of viewpoint chip k."""
    if GRID:
        return 30 + (k % 2) * (GRID_W + 16), TY + th + 16 + CHIP_STEP * (k // 2), GRID_W
    return CHIP_X, CHIP_Y0 + CHIP_STEP * k, round(runs_width(c) + 2 * CHIP_PAD)


if GRID:
    CHIP_Y0 = TY + th + 16
    too_wide = [k + 1 for k, c in enumerate(chips) if runs_width(c) + 2 * CHIP_PAD > GRID_W]
    if too_wide:
        print(f"WARNING: viewpoint(s) {too_wide} are too long for a half-width chip")
chips_bottom = (chip_box(len(chips) - 1, chips[-1])[1] + CHIP_H) if chips else 0
if chips and chips_bottom > HEAD_TOP - 10:
    print(f"WARNING: {len(chips)} viewpoints reach y={chips_bottom}, below the top of your head (y={HEAD_TOP})")

# bio card for the first seconds: [bio] in library/brand/profile.toml, per-video [bio] overrides.
# Name in a filled tag (ink text) at the box's right end, straddling its top border.
# position "top-right" (default): beside the title, or just under it at the right if there's no room;
# position "chin": on the right just below your chin (bio_top), subtitles move down below it.
BIO = {**PROFILE.get("bio", {}), **CFG.get("bio", {})}
bio_events, BIO_BOX = [], None
# b-roll on screen (output times), worked out the same way as in the photos section below
BROLL = sorted((to_out(when(ph)), max(to_out(when(ph, "until", "until_after")) - 0.05, to_out(when(ph)) + ph.get("seconds", 2.5)))
               for ph in CFG.get("photos", []))


def spoken(phrases):
    """Output time of the first kept word where any of these phrases starts (spaces, punctuation and case ignored)."""
    text, owner = "", []
    for i, w in enumerate(kept):
        clean = re.sub(r"[\s，。,.？?！!、：:；;]", "", w["raw"]).lower()
        text += clean
        owner += [i] * len(clean)
    hits = [text.find(re.sub(r"\s", "", ph).lower()) for ph in phrases]
    hits = [h for h in hits if h >= 0]
    return to_out(kept[owner[min(hits)]]["t0"]) if hits else None


def bio_window():
    """Bio card only while no b-roll is up. It starts at the self-introduction
    (profile.toml bio intro, or [bio] at = "..." in video.toml) whenever that moment is clear of b-roll; otherwise it falls back
    to the opening (if clear), then to the first clear stretch after the intro. Ends before the next b-roll."""
    def clear_from(s):
        for a, b in BROLL:
            if a - 0.2 <= s < b + 0.2:
                s = b + 0.2
        ends = [a - 0.2 for a, b in BROLL if a - 0.2 > s]
        return s, min([s + BIO.get("seconds", 15), E0] + ends)
    MIN = BIO.get("min_seconds", 4)
    intro = spoken([BIO["at"]] if BIO.get("at") else BIO.get("intro", []))
    s, e = clear_from(0.6)  # the opening
    if intro is None:
        print(f"WARNING: no self-introduction found ({BIO.get('at') or BIO.get('intro')}); bio card at the opening. "
              f"Set [bio] at = \"...\" to the words it should start on")
    else:
        i0, i1 = clear_from(max(0.6, intro - 0.2))
        if i0 <= intro + 0.3 and i1 - i0 >= MIN:  # the intro itself is clear of b-roll: start there (default)
            s, e = i0, i1
        elif s <= 0.6 and e - s >= MIN:
            print("bio card: b-roll around your self-introduction, so it shows at the opening instead")
        else:
            s, e = i0, i1
    if e - s < BIO.get("min_seconds", 4):
        print(f"WARNING: bio card only has {e - s:.1f}s between b-roll ({s:.1f}-{e:.1f}s); set [bio] at = \"...\"")
    print(f"bio card: {s:.1f}-{e:.1f}s")
    return s, e


if BIO.get("enabled", True):
    name = [(BIO["name"], INK, LATIN, 56)]
    nw, nh = round(runs_width(name) + 2 * 24), 74
    rows = [[("•  ", ACCENT, MAIN, 32), (line, WHITE, MAIN, 32)] for line in BIO["lines"]]
    pad_top = nh // 2 + 6  # the tag's lower half sits inside the box
    bw = round(max([runs_width(r) for r in rows] + [nw + 40]) + 2 * 24)
    bh = pad_top + 46 * len(rows) + 12
    bx = W - 30 - bw
    if BIO.get("position", "top-right") == "top-right":
        top = TY if bx >= tw + 24 else TY + th + 16
        if top > TY and chips and CHIP_Y0 > TY and not GRID:  # the chips have the right side under the title: bio goes left
            bx = 30
            if bx + bw > CHIP_X - 16:
                print(f"WARNING: the bio card (to x={bx + bw}) runs into the viewpoint chips (from x={CHIP_X})")
    else:
        top, bx = CFG.get("bio_top", 1120), W - 40 - bw
    b0, b1 = bio_window()
    # a later bio card (after opening b-roll) may meet viewpoint chips that are already up: go below them
    up = [chip_box(k, c) for k, (c, (_, ct)) in enumerate(zip(chips, POINTS)) if to_out(ct) < b1]
    below = [y + CHIP_H for x, y, w in up if x < bx + bw and bx < x + w and y < top + nh // 2 + bh and top < y + CHIP_H]
    if below:
        top = max(y + CHIP_H for x, y, w in up if x < bx + bw and bx < x + w) + 16
        print(f"bio card moved below the viewpoint chips already on screen (top y={top})")
    by = top + nh // 2  # box border runs through the middle of the tag
    nx = bx + bw - 20 - nw
    fade = r"\fad(300,300)"
    bio_events += [
        rounded_rect(bx, by, bw, bh, 12, PANEL, b0, b1, anim=fade),
        outline_rect(bx, by, bw, bh, 12, ACCENT, 2, b0, b1, anim=fade),
        rounded_rect(nx, top, nw, nh, 12, FILL, b0, b1, layer=2, anim=fade),
        text_line(nx + 24, top + nh - 16, name, b0, b1, layer=3, align=1, anim=fade)]
    bio_events += [text_line(bx + 24, by + pad_top + 46 * j + 32, r, b0, b1, align=1, anim=fade) for j, r in enumerate(rows)]
    BIO_BOX = (bx, top, bw, nh // 2 + bh, b0, b1, "right")
    if top + nh // 2 + bh > HEAD_TOP - 10 and BIO.get("position", "top-right") == "top-right":
        print(f"WARNING: the bio card reaches y={top + nh // 2 + bh}, below the top of your head (y={HEAD_TOP})")
BIO_SPAN = BIO_BOX and (BIO_BOX[4], BIO_BOX[5], BIO_BOX[6])

srt = []
events += bio_events
SUB_BOTTOM, PAD_X, PAD_Y, GAP = H - 360, 32, 24, 18
for n_card, c in enumerate(cards, 1):
    built = []
    for i, line in enumerate(c["lines"]):
        runs, text, has_key = styled_runs(line, i == len(c["lines"]) - 1)
        if i == len(c["lines"]) - 1 and c["q"]:
            runs.append(("？", WHITE, MAIN, SUB_SIZE))
        built.append((runs, KEY_SIZE if has_key else SUB_SIZE, text))
    cursor_w = text_width(" _", MAIN, SUB_SIZE)
    width = max(runs_width(r) for r, _, _ in built) + cursor_w + 2 * PAD_X
    height = sum(h for _, h, _ in built) + GAP * (len(built) - 1) + 2 * PAD_Y
    x, y = 64, SUB_BOTTOM - height
    t0, t1 = c["t0"], c["t1"]
    if BIO_BOX and t0 < BIO_BOX[5] and t1 > BIO_BOX[4] and x + width > BIO_BOX[0] and y < BIO_BOX[1] + BIO_BOX[3] + 16:
        y = BIO_BOX[1] + BIO_BOX[3] + 16  # just below the bio card while it's up
        if y + height > H - 220:
            print(f"WARNING: subtitle at {t0:.1f}s pushed into the app's bottom bar by the bio card; raise bio_top")
    events.append(rounded_rect(x, y, round(width), round(height), 12, PANEL, t0, t1, anim=r"\fad(60,0)"))
    cy = y + PAD_Y
    for i, (runs, h, _) in enumerate(built):
        events.append(text_line(x + PAD_X, cy + h, runs, t0, t1, align=1, anim=r"\fad(60,0)"))
        if i == len(built) - 1:  # blinking cursor after the last line
            cx = x + PAD_X + runs_width(runs)
            k, tt = 0, t0
            while tt < t1:
                if k % 2 == 0:
                    events.append(text_line(cx, cy + h, [(" _", ACCENT, MAIN, SUB_SIZE)], tt, min(tt + 0.5, t1), align=1))
                tt += 0.5
                k += 1
        cy += h + GAP
    srt.append(f"{n_card}\n{srt_ts(t0)} --> {srt_ts(t1)}\n"
               + "\n".join(t for _, _, t in built) + ("？" if c["q"] else "") + "\n")


# photos: big, centred over you, one at a time, between whatever is
# up at the top (title, bio card, viewpoint chips) and the subtitles; caption chip in the top-left corner
VIDEO_EXT = (".mp4", ".mov", ".m4v")
PHOTO_STYLE = CFG.get("photo_style", "card")  # "card": big card centred over you; "fullscreen": photo fills the screen
overlays = []
for i, ph in enumerate(CFG.get("photos", [])):
    t0, t1 = to_out(when(ph)), to_out(when(ph, "until", "until_after")) - 0.05
    t1 = max(t1, t0 + ph.get("seconds", 2.5))  # long enough to take in
    files = ph["file"] if isinstance(ph["file"], list) else [ph["file"]]
    vsrc = asset(files[0])
    if vsrc.suffix.lower() in VIDEO_EXT:  # video b-roll: full screen, same fill rule as photos, its own sound muted
        clip = EDIT / f"photo{i}.mp4"
        vw, vh = [int(x) for x in subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                  "stream=width,height", "-of", "csv=p=0", str(vsrc)], capture_output=True, text=True).stdout.strip().split(",")[:2]]
        fill = ph.get("fill", CFG.get("photo_fill", "auto"))  # per item: "whole" for screenshots and documents
        if fill == "cover" or (fill == "auto" and vh > vw):  # portrait: fill the screen, cropping the edges
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        else:  # landscape: whole clip across the width on a blurred, darkened copy of itself
            vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,"
                  f"colorchannelmixer=rr=0.45:gg=0.45:bb=0.45[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2")
        start = ph.get("start", 0.0)  # seconds into the clip to start from
        subprocess.run([FFMPEG, "-v", "error", "-y", "-stream_loop", "-1", "-ss", str(start), "-i", str(vsrc),
                        "-t", f"{t1 - t0 + 0.2:.3f}", "-an", "-filter_complex", f"[0:v]fps={FPS},{vf},format=yuv420p[v]",
                        "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-preset", "fast", str(clip)], check=True)
        cap = [("> ", ACCENT, MAIN, 40), (ph["caption"], WHITE, MAIN, 40)] if ph.get("caption") else []
        overlays.append(dict(path=clip, x=0, y=0, t0=t0, t1=t1, kind="fullvideo",
                             caption=(cap, round(runs_width(cap) + 2 * 22) if cap else 0, 30 - 22, TY + th + 16 - 22)))
        continue
    rotations = ph.get("rotate", 0)
    rotations = rotations if isinstance(rotations, list) else [rotations] * len(files)
    srcs = []
    for j, (f, rot) in enumerate(zip(files, rotations)):
        src = asset(f)
        if src.suffix.lower() in (".heic", ".heif") or rot:  # iPhone photos; some need turning upright
            jpg = EDIT / f"photo{i}_{j}_src.jpg"
            subprocess.run(["sips", "-s", "format", "jpeg", *(["-r", str(rot)] if rot else []), str(src), "--out", str(jpg)],
                           check=True, capture_output=True)
            src = jpg
        if ph.get("blur"):  # hide private details, e.g. a Wi-Fi password on a screen
            src = blurred(src, ph["blur"], EDIT / f"photo{i}_{j}_blur.jpg")
        srcs.append(src)
    if len(srcs) > 1:  # several photos side by side in one card
        from PIL import Image as _Image
        ims = [_Image.open(x).convert("RGB") for x in srcs]
        hh = min(im.height for im in ims)
        ims = [im.resize((round(im.width * hh / im.height), hh)) for im in ims]
        gap = round(hh * 0.02)
        col = _Image.new("RGB", (sum(im.width for im in ims) + gap * (len(ims) - 1), hh), rgb("panel"))
        x = 0
        for im in ims:
            col.paste(im, (x, 0))
            x += im.width + gap
        src = EDIT / f"photo{i}_src.jpg"
        col.save(src, quality=92)
    else:
        src = srcs[0]
    from PIL import Image as _Image
    if PHOTO_STYLE == "fullscreen":  # the photo is the screen (optionally with you in a small circle, see pass 2)
        full = _Image.open(src).convert("RGB")
        fill = ph.get("fill", CFG.get("photo_fill", "auto"))  # auto: portrait fills, landscape on a blur; "whole" always on a blur
        if fill == "cover" or (fill == "auto" and full.height > full.width):  # fill the whole screen, cropping the edges
            k = max(W / full.width, H / full.height)
            full = full.resize((round(full.width * k), round(full.height * k)), _Image.LANCZOS)
            full = full.crop(((full.width - W) // 2, (full.height - H) // 2, (full.width - W) // 2 + W, (full.height - H) // 2 + H))
        else:  # whole photo across the width, on a blurred, darkened copy of itself
            from PIL import ImageFilter as _IF, ImageEnhance as _IE
            k = max(W / full.width, H / full.height)
            bg = full.resize((round(full.width * k), round(full.height * k)), _Image.LANCZOS)
            bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
            bg = _IE.Brightness(bg.filter(_IF.GaussianBlur(40))).enhance(0.45)
            fg = full.resize((W, round(full.height * W / full.width)), _Image.LANCZOS)
            if fg.height > H:
                fg = fg.crop((0, (fg.height - H) // 2, W, (fg.height - H) // 2 + H))
            bg.paste(fg, (0, (H - fg.height) // 2))
            full = bg
        full.save(EDIT / f"photo{i}.png")
        cap = [("> ", ACCENT, MAIN, 40), (ph["caption"], WHITE, MAIN, 40)] + ([("  " + ph["caption_en"], ACCENT, LATIN, 34)] if ph.get("caption_en") else [])
        overlays.append(dict(path=EDIT / f"photo{i}.png", x=0, y=0, t0=t0, t1=t1, kind="full",
                             caption=(cap, round(runs_width(cap) + 2 * 22), 30 - 22, TY + th + 16 - 22)))
        continue
    pw_, ph_ = _Image.open(src).size
    top_edge = TY + th
    if BIO_BOX and t0 < BIO_BOX[5] and t1 > BIO_BOX[4]:
        top_edge = max(top_edge, BIO_BOX[1] + BIO_BOX[3])
    shown = sum(1 for _, t in POINTS if to_out(t) < t1)
    if shown:
        top_edge = max(top_edge, chip_box(shown - 1, chips[shown - 1])[1] + CHIP_STEP)
    top_edge += 24
    bottom_edge = H - 360 - 212 - 16  # above the tallest two-line subtitle (one line with a big key word)
    room = bottom_edge - top_edge
    cw, ch = card(src, min(W - 140, round(room * pw_ / ph_)), EDIT / f"photo{i}.png")
    jx, jy = (W - cw) // 2, top_edge + (room - ch) // 2
    cap = [("> ", ACCENT, MAIN, 40), (ph["caption"], WHITE, MAIN, 40)] + ([("  " + ph["caption_en"], ACCENT, LATIN, 34)] if ph.get("caption_en") else [])
    capw = round(runs_width(cap) + 2 * 22)
    overlays.append(dict(path=EDIT / f"photo{i}.png", x=jx, y=jy, t0=t0, t1=t1, kind="glitch", caption=(cap, capw, jx, jy)))
# the circle of you shown over full-screen photos: crop around your face, bottom right above the subtitles
PIP_D = CFG.get("pip_size", 380)
PIP_CROP = CFG.get("pip_crop", [(W - 760) // 2, HEAD_TOP - 60, 760])  # x, y, size of the square around your face
PIP_POS = (W - 40 - PIP_D, H - 360 - 212 - 24 - PIP_D)
if CFG.get("pip", False) and any(o["kind"] == "full" for o in overlays):
    from PIL import Image as _Image, ImageDraw as _ID
    m = _Image.new("L", (PIP_D * 4, PIP_D * 4), 0)
    _ID.Draw(m).ellipse([0, 0, PIP_D * 4 - 1, PIP_D * 4 - 1], fill=255)
    m.resize((PIP_D, PIP_D), _Image.LANCZOS).save(EDIT / "pip_mask.png")
    ring = _Image.new("RGBA", (PIP_D * 4 + 48, PIP_D * 4 + 48), (0, 0, 0, 0))
    _ID.Draw(ring).ellipse([0, 0, ring.width - 1, ring.height - 1], outline=(*rgb("accent"), 255), width=28)
    ring.resize(((PIP_D + 12), (PIP_D + 12)), _Image.LANCZOS).save(EDIT / "pip_ring.png")
for a, b in zip(overlays, overlays[1:]):  # a photo gives way to the next one
    if a["t1"] > b["t0"] - 0.1:
        a["t1"] = b["t0"] - 0.1
for o in overlays:  # caption chip in the top-left corner of each card
    cap, capw, jx, jy = o.pop("caption")  # card: top-left corner of the photo; full screen: under the title
    t0, t1 = o["t0"], o["t1"]
    if o["kind"] in ("full", "fullvideo") and BIO_BOX and t0 < BIO_BOX[5] and BIO_BOX[0] < jx + capw:
        jy = max(jy, BIO_BOX[1] + BIO_BOX[3] + 16 - 22)  # under the bio card while it's up
    if not cap:
        continue
    events += [rounded_rect(jx + 22, jy + 22, capw, 70, 12, PANEL, t0 + 0.15, t1, layer=3, anim=r"\fad(120,150)"),
               text_line(jx + 44, jy + 22 + 70 - 16, cap, t0 + 0.15, t1, layer=4, align=1, anim=r"\fad(120,150)")]

# title tab and viewpoint chips (drawn after the photos' captions, on top of everything at the top)
if title_lines:
    events += [shape(tab_left(TY, tw, th), PANEL, 0.0, E0), shape(f"m 0 {TY} l 12 {TY} l 12 {TY + th} l 0 {TY + th}", ACCENT, 0.0, E0, 1)]
    y = TY + 14
    for runs, h, align in title_lines:
        events.append(text_line(44, y if align == 7 else y + h - 12, runs, 0.0, E0, align=align))
        y += h
# viewpoint chips only while it's just you talking: hidden during every photo, clip and
# animation, back when it ends; b-roll less than 0.8 s apart counts as one, so the chips don't flash in between
BROLL_ON = []
for o in sorted((o for o in overlays if o["kind"] in ("full", "fullvideo")), key=lambda o: o["t0"]):
    if BROLL_ON and o["t0"] - BROLL_ON[-1][1] < 0.8:
        BROLL_ON[-1][1] = max(BROLL_ON[-1][1], o["t1"])
    else:
        BROLL_ON.append([o["t0"], o["t1"]])


def clear_spans(start, end):
    """Parts of [start, end] with no b-roll on screen."""
    spans, s = [], start
    for a, b in BROLL_ON:
        if b <= s or a >= end:
            continue
        if a > s:
            spans.append((s, a))
        s = max(s, b)
    if s < end:
        spans.append((s, end))
    return [(a, b) for a, b in spans if b - a > 0.3]


for k, (c, (_, t)) in enumerate(zip(chips, POINTS)):
    x, y, w = chip_box(k, c)
    for n_, (s, e) in enumerate(clear_spans(to_out(t), E0)):
        fade = r"\fad(250,150)" if e < E0 else r"\fad(250,0)"
        events += [rounded_rect(x, y, w, CHIP_H, 10, PANEL, s, e, anim=fade),
                   outline_rect(x, y, w, CHIP_H, 10, ACCENT, 2, s, e, anim=fade),
                   text_line(x + CHIP_PAD, y + round(45 * CHIP_S), c, s, e, align=1, anim=fade)]

# older style: pop-ups that come and go, and an opening hook panel
# with a top title, a pop-up (e.g. a comment keyword) sits centred just below the title tab and any chips
# on screen at that moment, for `seconds` (default 4)
POPUPS = [(p["label"], markup(p["text"]), when(p), p) for p in CFG.get("popups", [])]
for label, runs, t, p in POPUPS:
    t0, y = to_out(t), None
    if "top_title" in CFG:
        up = [chip_box(k, c)[1] + CHIP_H for k, (c, (_, ct)) in enumerate(zip(chips, POINTS)) if ct <= t]
        y = max([TY + th] + up) + 24
        if y + 175 > HEAD_TOP - 10:
            print(f"WARNING: pop-up '{p['text']}' reaches y={y + 175}, below the top of your head (y={HEAD_TOP})")
    events += popup(label, runs, t0, p.get("seconds", 4.0), y)
if "hook" in CFG and "top_title" not in CFG:
    HOOK = CFG["hook"]
    hook_end = to_out(first_word(HOOK["until"])) - 0.1
    title = markup(HOOK["title"])
    label = [(HOOK["label"], ACCENT, LATIN, 36)]
    answer = [("> ", ACCENT, MAIN, 50), (HOOK["answer"], ACCENT, MAIN, 50), (" _", ACCENT, MAIN, 50)]
    pw = round(max(runs_width(title), runs_width(label), runs_width(answer)) + 2 * 40)
    px, py, ph = (W - pw) // 2, SAFE_TOP, 250
    fade = r"\fad(0,250)"
    events += [rounded_rect(px, py, pw, ph, 12, PANEL, 0, hook_end, anim=fade),
               text_line(px + 40, py + 24, label, 0, hook_end, anim=fade),
               text_line(px + 40, py + 158, title, 0, hook_end, align=1, anim=fade),
               text_line(px + 40, py + 224, answer, 0, hook_end, align=1, anim=fade)]


# ---------------------------------------------------------------- images (ffmpeg overlays)
for i, st in enumerate(CFG.get("stickers", [])):  # slide in from the side (sticker_spot picks where)
    try:
        src = asset(st["file"])
    except FileNotFoundError:
        if "--dry" not in sys.argv:
            raise
        print(f"WARNING: sticker {st['file']} not found, skipped in this dry run")
        continue
    t = to_out(when(st))
    if CFG.get("sticker_spot") == "above_head_left":
        # in the space above your head on the left: under the title tab, left of the chips, above your head
        top = TY + th + 20
        if BIO_BOX and BIO_BOX[0] < W // 2 and BIO_BOX[4] - 1 < t < BIO_BOX[5]:
            top = max(top, BIO_BOX[1] + BIO_BOX[3] + 20)  # under a bio card on the left
        room_h = HEAD_TOP - 20 - top
        room_w = (CHIP_X - 30 if CHIP_Y0 > TY else W // 2) - 60
        sw, sh = sticker(src, min(st["width"], room_w), EDIT / f"sticker{i}.png")
        if sh > room_h:  # too tall for the space: make it smaller
            sw, sh = sticker(src, max(80, round(sw * room_h / sh)), EDIT / f"sticker{i}.png")
        side = "left"
        # close to your head: bottom just above it, right edge near its upper-left (head_left in video.toml)
        x = max(40, CFG.get("head_left", 470) - sw)
        y = max(top, HEAD_TOP - 10 - sh)
    else:  # beside you at shoulder height
        sw, sh = sticker(src, st["width"], EDIT / f"sticker{i}.png")  # SVGs become PNGs here
        side = st.get("side", "right")
        if BIO_SPAN and BIO_SPAN[0] - 3 < t < BIO_SPAN[1] and side == BIO_SPAN[2]:  # keep clear of the bio card
            side = "left" if side == "right" else "right"
        x, y = (W - sw - 60 if side == "right" else 60), CFG.get("sticker_y", 1150) - sh // 2  # sticker_y: centre height
    overlays.append(dict(path=EDIT / f"sticker{i}.png", x=x, y=y, t0=t, t1=t + st.get("seconds", 2.6),
                         kind="pop", side=side))

# ---------------------------------------------------------------- end card
# handle, tagline and like / save / follow buttons over the blurred last shot (button words from the language pack)
heart = "m 0 10 b 0 -4 18 -6 22 6 b 26 -6 44 -4 44 10 b 44 24 30 32 22 40 b 14 32 0 24 0 10"
star = "m 22 0 l 28 15 l 44 16 l 32 27 l 36 42 l 22 34 l 8 42 l 12 27 l 0 16 l 16 15 l 22 0"
plus = "m 18 0 l 26 0 l 26 18 l 44 18 l 44 26 l 26 26 l 26 44 l 18 44 l 18 26 l 0 26 l 0 18 l 18 18 l 18 0"
up = r"\fad(300,0)"
events += [text_line(W / 2, 640, [("FOLLOW FOR MORE", ACCENT, LATIN, 48)], E0 + 0.1, TOTAL, align=8, anim=up),
           text_line(W / 2, 720, [("@", ACCENT, MAIN, 96), (PROFILE["handle"], WHITE, MAIN, 96)], E0 + 0.2, TOTAL, align=8, anim=up)]
if CFG.get("end_card", {}).get("tagline"):
    events.append(text_line(W / 2, 860, [(CFG["end_card"]["tagline"], WHITE, MAIN, 50)], E0 + 0.3, TOTAL, align=8, anim=up))
bw_, bh_, gap_ = 280, 120, 30
bx0 = (W - (3 * bw_ + 2 * gap_)) // 2
for i, (word, icon) in enumerate(zip(LANG["end_buttons"], (heart, star, plus))):
    bx_, by_, t = bx0 + i * (bw_ + gap_), 1010, E0 + 0.5 + i * 0.25
    primary = i == 2  # the follow button
    events.append(rounded_rect(bx_, by_, bw_, bh_, 12, HIGHLIGHT if primary else PANEL, t, TOTAL, anim=up))
    if not primary:
        events.append(outline_rect(bx_, by_, bw_, bh_, 12, ACCENT, 3, t, TOTAL, anim=up))
    events.append(dialogue(2, t, TOTAL, rf"{{\an7\pos({bx_ + 52},{by_ + 38}){up}\bord0\shad0\1c{INK if primary else ACCENT}\p1}}{icon}"))
    events.append(text_line(bx_ + 118, by_ + 26, [(word, INK if primary else WHITE, MAIN, 64)], t, TOTAL, anim=up))

shown = "".join(re.sub(r"\{[^}]*\}", "", e.split(",,", 1)[-1]) for e in events if "\\p1" not in e)
if missing_glyphs(shown):
    print(f"WARNING: on-screen text has characters the Chinese font can't draw (they'd show as boxes): {missing_glyphs(shown)}")
(EDIT / "subtitles.ass").write_text(ass_file(events), encoding="utf-8")
(EDIT / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")  # copied to exports only by a real render

# ---------------------------------------------------------------- sound effects
sfx = []  # (file, output time, gain dB)
for t in [p_[2] for p_ in POPUPS] + [t for _, t in POINTS]:
    sfx.append((SFX["whoosh"], to_out(t), -10))
for o in overlays:
    sfx.append((SFX["glitch"], o["t0"], -12) if o["kind"] == "glitch" else (SFX["pop"], o["t0"], -10))
DINGS = list(CFG["subtitles"].get("dings", []))
for c in cards:
    text = "".join(t["text"] for line in c["lines"] for t in line)
    for kw in list(DINGS):
        if kw in text:
            sfx.append((SFX["ding"], c["t0"], -14))
            DINGS.remove(kw)
sfx.append((SFX["whoosh"], E0, -12))
sfx.append((SFX["click"], E0 + 1.0, -8))  # on the follow button
sfx.sort(key=lambda x: x[1])
if "--dry" in sys.argv:  # leave the overlay positions for previews
    (EDIT / "overlays.json").write_text(json.dumps([{**o, "path": str(o["path"])} for o in overlays], indent=1))
    (EDIT / "pip.json").write_text(json.dumps(dict(on=CFG.get("pip", False), d=PIP_D, crop=PIP_CROP, pos=PIP_POS, mask=str(EDIT / "pip_mask.png"),
                                                   ring=str(EDIT / "pip_ring.png"))))
    sys.exit()

# ---------------------------------------------------------------- pass 2: everything together
VOICE_GAIN = render_pass1()
music = asset(CFG["music"]) if "music" in CFG else next(f for f in sorted((LIBRARY / "music").iterdir()) if f.suffix in (".mp3", ".wav", ".m4a"))
inputs = ["-i", str(voice), "-stream_loop", "-1", "-i", str(music)]
fc = []
# end card: blur and dim the last shot, held as a still until the end
fc.append(f"[0:v]tpad=stop_mode=clone:stop_duration={END_HOLD},trim=duration={TOTAL:.3f},split[base][blurin]")
fc.append(f"[blurin]gblur=sigma=18,colorchannelmixer=rr=0.35:gg=0.35:bb=0.35,format=yuva420p,"
          f"fade=t=in:st={E0:.3f}:d=0.4:alpha=1[blur]")
fc.append("[base][blur]overlay=shortest=1[v0]")
FULL = [o for o in overlays if o["kind"] == "full"] if CFG.get("pip", False) else []  # pip: the circle of you
if FULL:  # keep a copy of you for the circle
    fc.append("[v0]split[v0][pipsrc]")
last = "[v0]"
idx = 2
for k, o in enumerate(overlays):
    if o["kind"] == "fullvideo":
        inputs += ["-i", str(o["path"])]
    else:
        inputs += ["-loop", "1", "-t", f"{o['t1'] - o['t0'] + 0.1:.3f}", "-i", str(o["path"])]
    d = o["t1"] - o["t0"]
    fc.append(f"[{idx}:v]format=rgba,fade=t=in:st=0:d=0.18:alpha=1,fade=t=out:st={d - 0.2:.3f}:d=0.2:alpha=1,"
              f"setpts=PTS-STARTPTS+{o['t0']:.3f}/TB[ov{k}]")
    tt = f"(t-{o['t0']:.3f})"
    if o["kind"] in ("full", "fullvideo"):     # full-screen photo or clip: a short fade is enough
        xe, ye = "0", "0"
    elif o["kind"] == "glitch":   # quick horizontal jitter as it appears
        xe = f"{o['x']}+if(lt({tt},0.28),26*sin(90*{tt}),0)"
        ye = str(o["y"])
    else:                       # slide in from the side with a small overshoot
        sgn = 1 if o["side"] == "right" else -1
        xe = f"{o['x']}+{sgn}*if(lt({tt},0.3),180*(1-{tt}/0.3)*(1-{tt}/0.3)-12*sin(3.14*{tt}/0.3),0)"
        ye = str(o["y"])
    fc.append(f"{last}[ov{k}]overlay=x='{xe}':y='{ye}':eval=frame:enable='between(t,{o['t0']:.3f},{o['t1']:.3f})'[v{k + 1}]")
    last = f"[v{k + 1}]"
    idx += 1
if FULL:
    on = "+".join(f"between(t,{o['t0'] + 0.1:.3f},{o['t1'] - 0.1:.3f})" for o in FULL)
    inputs += ["-loop", "1", "-t", f"{TOTAL:.3f}", "-i", str(EDIT / "pip_mask.png"),
               "-loop", "1", "-t", f"{TOTAL:.3f}", "-i", str(EDIT / "pip_ring.png")]
    x, y, size = PIP_CROP
    fc.append(f"[pipsrc]crop={size}:{size}:{x}:{y},scale={PIP_D}:{PIP_D},format=rgba[pipc]")
    fc.append(f"[{idx}:v]format=gray,scale={PIP_D}:{PIP_D}[pipm]")
    fc.append("[pipc][pipm]alphamerge[pip]")
    fc.append(f"{last}[pip]overlay={PIP_POS[0]}:{PIP_POS[1]}:enable='{on}'[vp]")
    fc.append(f"[vp][{idx + 1}:v]overlay={PIP_POS[0] - 6}:{PIP_POS[1] - 6}:enable='{on}'[vr]")
    last = "[vr]"
    idx += 2
fc.append(f"{last}ass={EDIT / 'subtitles.ass'}:fontsdir={FONTS}[vout]")

# audio: voice, ducked music, effects
fc.append(f"[0:a]volume={VOICE_GAIN:.2f}dB,apad=whole_dur={TOTAL:.3f},asplit[vox][key]")
fc.append(f"[1:a]aresample=48000,pan=stereo|c0=c0|c1=c1,atrim=duration={TOTAL:.3f},volume={MUSIC_DB}dB,"
          f"afade=t=in:d=1.5,afade=t=out:st={TOTAL - 2.0:.3f}:d=2.0[mus]")
fc.append("[mus][key]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=500:makeup=1[duck]")
mix = ["[vox]", "[duck]"]
for k, (f, t, g) in enumerate(sfx):
    inputs += ["-i", str(f)]
    ms = int(t * 1000)
    fc.append(f"[{idx}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume={g + SFX_BOOST}dB,adelay={ms}|{ms}[s{k}]")
    mix.append(f"[s{k}]")
    idx += 1
fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,"
          f"alimiter=limit=0.84:level=false[aout]")

OUT_DIR.mkdir(parents=True, exist_ok=True)
final = OUT_DIR / f"{TITLE}_{VERSION}.mp4"
partial = OUT_DIR / f".{TITLE}_{VERSION}.rendering.mp4"  # an interrupted render never damages the finished video
subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-stats", "-y", *inputs,
                "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
                "-t", f"{TOTAL:.3f}", "-r", str(FPS),
                "-c:v", "libx264", "-crf", "20", "-preset", "slow", "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(partial)], check=True)
partial.replace(final)  # only appears once the render has finished
# macOS marks the dot-named temp file "hidden" and the flag survives the rename; clear it so Finder shows the video
subprocess.run(["chflags", "nohidden", str(final)], check=False)
(OUT_DIR / f"{TITLE}_{VERSION}.srt").write_text("\n".join(srt), encoding="utf-8")
print("wrote", final)
