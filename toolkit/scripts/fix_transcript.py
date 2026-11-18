"""Re-transcribe short stretches of a video and splice their words into the transcript.

Usage: python -I fix_transcript.py <video folder>

Why: at a false start, Whisper often folds the pause and the real take into one long word that starts inside
the cut (e.g. one word from 7.7 s to 10.4 s). The build drops that word, so the kept take loses words in the
subtitles AND in the audio (the cut list is made from word timings). Re-transcribing just the kept take
gives it proper word timings.

The stretches are [transcribe] fix = [[start, end], ...] in video.toml (seconds of the raw footage). Start each
at the end of a retake cut and end it in a pause after the sentence. Every run starts again from the original
transcript (work/transcript/transcript_original.json, saved the first time), so it is safe to re-run.
"""
import json, os, pathlib, subprocess, sys, tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import FFMPEG, TOOLKIT, language  # noqa: E402

os.environ.setdefault("HF_HOME", str(TOOLKIT / "models" / "hf_home"))  # keep model caches inside the project
import mlx_whisper  # noqa: E402

MODEL = str(TOOLKIT / "models" / "whisper-large-v3-mlx")
VID = pathlib.Path(sys.argv[1]).resolve()
T = VID / "work" / "transcript"
CFG = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))
FIX = CFG.get("transcribe", {}).get("fix", [])
LANG = language(CFG)
PHANTOM = set(LANG.get("phantom", []))  # stock phrases Whisper invents on silence
PROMPT = LANG.get("whisper_prompt", "") + CFG.get("transcribe", {}).get("terms", "")

original = T / "transcript_original.json"
if not original.exists():
    original.write_text((T / "transcript.json").read_text(encoding="utf-8"), encoding="utf-8")
data = json.loads(original.read_text(encoding="utf-8"))
segments = data["segments"]

def transcribe(a, b):
    clip = T / "_fix.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", str(T / "audio16k.wav"), str(clip)],
                   check=True)
    r = mlx_whisper.transcribe(str(clip), path_or_hf_repo=MODEL, language=LANG["whisper_language"], initial_prompt=PROMPT,
                               word_timestamps=True, condition_on_previous_text=False)
    clip.unlink()
    new = []
    for s in r["segments"]:
        ws = [dict(w, start=round(a + w["start"], 2), end=round(min(b, a + w["end"]), 2)) for w in s["words"]]
        ws = [w for w in ws if w["start"] < b]
        for k in range(len(ws)):  # Whisper's stock phrases on silence ("thanks for watching"…) at the end of a stretch
            if "".join(w["word"] for w in ws[k:]).strip(" ,，。.!！") in PHANTOM:
                print("  dropped phantom words:", "".join(w["word"] for w in ws[k:]).strip())
                ws = ws[:k]
                break
        if ws:
            new.append(dict(start=ws[0]["start"], end=ws[-1]["end"], text="".join(w["word"] for w in ws), words=ws))
    return new


for a, b in FIX:
    # too short to transcribe (Whisper invents text on near-silence): just remove the words there
    new = [] if b - a < 0.6 else transcribe(a, b)
    # drop the old words in [a, b); a segment that spans the stretch splits into its part before and after it
    kept = []
    for s in segments:
        for part in ([w for w in s["words"] if w["start"] < a], [w for w in s["words"] if w["start"] >= b]):
            if part:
                kept.append(dict(s, start=part[0]["start"], end=part[-1]["end"], text="".join(w["word"] for w in part), words=part))
    segments = kept + new
    segments.sort(key=lambda s: s["start"])
    print(f"[{a:7.2f} → {b:7.2f}]", " ".join(s["text"] for s in new))

data["segments"] = segments
(T / "transcript.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", T / "transcript.json")
