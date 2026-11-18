"""Transcribe a video's footage with mlx-whisper large-v3, keeping word-level timestamps.

Usage: python -I transcribe.py <video folder>
Writes work/transcript/: audio16k.wav, transcript.json, and script.txt (from script/, if there is one).
Names and terms Whisper should spell right come from [transcribe] terms in video.toml.
"""
import json, os, pathlib, subprocess, sys, tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves the script folder off the path
from brandkit import FFMPEG, TOOLKIT, language  # noqa: E402

os.environ.setdefault("HF_HOME", str(TOOLKIT / "models" / "hf_home"))  # keep model caches inside the project
import mlx_whisper  # noqa: E402

MODEL = str(TOOLKIT / "models" / "whisper-large-v3-mlx")

VID = pathlib.Path(sys.argv[1]).resolve()
CFG = tomllib.loads((VID / "video.toml").read_text(encoding="utf-8"))
LANG = language(CFG)
OUT = VID / "work" / "transcript"
OUT.mkdir(parents=True, exist_ok=True)

src = next(f for f in sorted((VID / "footage").iterdir()) if not f.name.startswith("."))
audio = OUT / "audio16k.wav"
subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)], check=True)

scripts = [f for f in sorted((VID / "script").glob("*")) if not f.name.startswith(".")] if (VID / "script").exists() else []
if scripts:  # plain text of the script, used to check names and mishearings
    subprocess.run(["textutil", "-convert", "txt", "-output", str(OUT / "script.txt"), str(scripts[0])], check=True)

# the language pack's prompt (e.g. "write Simplified Chinese") plus the names and terms in this video, so Whisper spells them right
PROMPT = LANG.get("whisper_prompt", "") + CFG.get("transcribe", {}).get("terms", "")

result = mlx_whisper.transcribe(
    str(audio),
    path_or_hf_repo=MODEL,
    language=LANG["whisper_language"],
    initial_prompt=PROMPT,
    word_timestamps=True,
    condition_on_previous_text=False,  # stops one misheard line from repeating through the rest
)
(OUT / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
for seg in result["segments"]:
    print(f"[{seg['start']:7.2f} → {seg['end']:7.2f}] {seg['text']}")
