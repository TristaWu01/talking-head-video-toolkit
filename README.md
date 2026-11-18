# Talking-Head Video Toolkit

**Turn raw talking-to-camera footage into a finished short video: cut, captioned, animated and with a cover, all driven by one config file.**

Editing a talking-head video by hand means hours of cutting retakes, timing subtitles and placing overlays. This toolkit does it from the transcript, with a human check at every stage. It was built for weekly education videos on **RedNote**. Its output, a vertical 9:16 video with burned-in subtitles and a 3:4 cover, also suits **TikTok, Instagram Reels, YouTube Shorts** and other short-video platforms.

**[See the project page: how I designed the workflow →](https://tristawu01.github.io/talking-head-video-toolkit/)**

<p align="center"><img src="docs/assets/anim-four-types.gif" width="360" alt="One of the explainer animations"></p>

---

## Key features

- **Transcription with word timings.** Whisper large-v3 runs on Apple Silicon (MLX). A custom term list keeps names spelled correctly.
- **Retake repair.** At false starts, Whisper often merges a pause and the retake into one long "word", which would be lost in the cut. `fix_transcript.py` re-transcribes those stretches and splices the words back in.
- **Automatic cuts.** Retakes, filler sounds and long pauses are removed by word timing. Silences are shortened instead of jump-cut, and the video is sped up (default 1.2×) without changing the pitch.
- **Clean audio.** RNNoise denoising, a high-pass filter, EQ and compression, then loudness normalised to −14 LUFS.
- **Smart subtitles.**
  - Lines break only between words; Chinese text is segmented with jieba.
  - No line starts with a particle, and names never split.
  - Key words are highlighted.
- **Platform compliance.** Words a platform flags are hidden or respelled in the subtitles only, and every build reports what it changed.
- **Overlays.**
  - Content: a title tab, numbered viewpoint chips, a bio card, full-screen b-roll, stickers and pop-ups.
  - Ending: an end card with like/save/follow buttons, plus sound effects.
  - All overlays are timed to the words being spoken, and none ever covers the speaker's face.
- **28 explainer animations.** Charts, chat bubbles, cards and pixel icons, drawn frame by frame in Python. A built-in pacing check keeps them readable.
- **Cover generator.** A 3:4 cover from a photo or a chosen frame, with an outlined headline and highlighted key words.
- **Key-frame preview.** Still frames of key moments, rendered on the real footage before the full render, catch layout problems early.
- **Themeable.** Every colour and font lives in one file, `library/brand/theme.toml`.
- **Multi-language.** Language rules live in small packs. Mandarin is used in production; an English pack is included.

## Tech stack and architecture

| Layer | Tools |
|---|---|
| Language | Python 3.11+ |
| Speech recognition | [MLX Whisper](https://github.com/ml-explore/mlx-examples) (large-v3), on Apple Silicon |
| Video and audio | ffmpeg with libass (subtitles), rubberband (speed-up without a pitch change) and arnndn (RNNoise) |
| Text | jieba (Chinese word segmentation) |
| Graphics | Pillow for animations and covers; ASS subtitle drawing commands for vector overlays |
| Config | TOML: one `video.toml` per video, plus shared theme, profile, language and platform files |

**How the pipeline fits together.** Each stage is a small script that reads the video's `video.toml` and writes into that video's folder.

1. `transcribe.py` and `fix_transcript.py` produce a word-timed transcript.
2. `build_edit.py --plan` turns the cut list into an edit plan.
3. `build_edit.py` renders in two passes:
   - **pass 1:** cut, speed-up and audio clean-up;
   - **pass 2:** one ASS subtitle file holding the subtitles and all vector overlays, plus image overlays, music and sound effects.
4. `keyframes.py`, `animations.py` and `cover.py` produce the previews, the b-roll and the cover.

`brandkit.py` holds the shared helpers and loads the theme. Nothing is ever overwritten: each render goes to a new version folder (`v1`, `v2`, …) and each cover to a new file.

**How it was built.** I designed the pipeline and its rules, directed the work and use it every week. Most of the code was written with [Claude Code](https://claude.com/claude-code), Anthropic's AI coding assistant, as a pair programmer. My part was:

- deciding what each stage should do;
- reviewing every render;
- turning each problem in a published video into a rule and a check.

[`docs/DESIGN_RULES.md`](docs/DESIGN_RULES.md) is that record.

## Quick start (local setup)

**Prerequisites:** macOS on Apple Silicon, [Homebrew](https://brew.sh) and Python 3.11 or newer.

```bash
# 1. Clone
git clone https://github.com/TristaWu01/talking-head-video-toolkit.git
cd talking-head-video-toolkit

# 2. System tools (ffmpeg-full includes libass, rubberband and arnndn)
brew install ffmpeg-full librsvg

# 3. Python environment
python3 -m venv toolkit/venv
source toolkit/venv/bin/activate
pip install -r requirements.txt

# 4. Models: Whisper (about 3 GB) and RNNoise
huggingface-cli download mlx-community/whisper-large-v3-mlx --local-dir toolkit/models/whisper-large-v3-mlx
mkdir -p toolkit/models/rnnoise
curl -L -o toolkit/models/rnnoise/cb.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/conjoined-burgers-2018-08-28/cb.rnnn
```

**5. Add a font.** Download [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) and copy `static/NotoSansSC-Bold.ttf` into `toolkit/fonts/`. To use a different font, name it in `library/brand/theme.toml`.

**6. Try it without footage:**

```bash
python -I toolkit/scripts/cover.py examples/demo_video v1                  # → examples/demo_video/exports/v1/cover/cover.png
python -I toolkit/scripts/animations.py examples/demo_video four_types     # → examples/demo_video/broll/anim_four_types.mp4
```

**7. Make your own.**

- Fill in `library/brand/profile.toml` (your handle and bio) and `library/brand/theme.toml` (your colours and fonts).
- Add five sound effects to `library/sound_effects/` and some music to `library/music/`; the READMEs in those folders list what's needed.
- Then edit a real video:

```bash
cp -R videos/_template videos/my-video        # put your footage in videos/my-video/footage/
python -I toolkit/scripts/transcribe.py videos/my-video
python -I toolkit/scripts/build_edit.py videos/my-video v1 --plan
python -I toolkit/scripts/keyframes.py videos/my-video v1
python -I toolkit/scripts/build_edit.py videos/my-video v1
python -I toolkit/scripts/cover.py videos/my-video v1
```

Each stage has a checkpoint before the next one starts; see [`docs/WORKFLOW.md`](docs/WORKFLOW.md). Every `video.toml` field is explained in [`docs/CONFIG.md`](docs/CONFIG.md).

### Environment variables (optional)

The toolkit calls no online services, so it needs no API keys and no `.env` file.

| Variable | Default | What it does |
|---|---|---|
| `FFMPEG_DIR` | Homebrew's `ffmpeg-full`, then `ffmpeg` on your PATH | Folder of the ffmpeg build to use |
| `THEME` | `library/brand/theme.toml` | Use a different theme file |

## Languages and platforms

Language packs in [`library/language/`](library/language/) hold the Whisper settings, filler words, line-break rules and end-card button words.

- **Mandarin (`zh`):** the language the toolkit was built for, used in production.
- **English (`en`):** included. Covers and animations have been rendered in English, but the full edit has not yet been run end to end on English footage.

The platform's sensitive-word list is a separate file, [`library/platform/sensitive_words.toml`](library/platform/sensitive_words.toml). Fill it in from your platform's own guidelines.

## Project layout

```
toolkit/scripts/     the pipeline
toolkit/fonts/       your font files (not committed)
library/brand/       theme.toml (colours, fonts) and profile.toml (handle, bio)
library/language/    language packs (zh, en)
library/platform/    sensitive-word list
library/stickers/    pixel-art stickers (made by pixel_stickers.py)
videos/_template/    copy this for each new video
examples/            a demo video config for trying the toolkit without footage
docs/                project page (index.html) plus workflow, design rules and config reference
```

## License

[MIT](LICENSE). Speech recognition by [OpenAI Whisper](https://github.com/openai/whisper); noise model from [rnnoise-models](https://github.com/GregorR/rnnoise-models).
