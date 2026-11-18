# Workflow

Every video goes through the same stages, and **each stage ends at a checkpoint**: nothing moves on until the creator approves it. Lists and text (cuts, flagged words, on-screen text) are reviewed as numbered lists, so a reply can be as short as "keep #3". Images (key frames, covers) are reviewed with their timestamps.

## 1. Intake check (no editing yet)
- Check the footage (length, resolution, frame rate, sound), the script, b-roll and `brief.md`.
- Flag anything missing or unclear, such as a viewpoint without the words that start it, or a photo with no moment.
- Check the machine: free disk space, files still cloud-only, and the footage's audio delay.
- Suggest b-roll for the key moments: free stock stills or clips, or an animation from `animations.py`.
- **Checkpoint 1:** the creator fills the gaps and picks the b-roll.

## 2A. Transcribe, then plan the cuts and words
- Compare the transcript with the script: where the speaker went off-script, and the Whisper corrections.
- List each repeated take to remove (the last take is kept) and the expected final length.
- List every flagged word that will be hidden or respelled in the subtitles, shown in its sentence.
- **Checkpoint 2A.**

## 2B. Plan on-screen text and visuals
- The top title, each viewpoint and its trigger words, the highlighted key words and the ding moments.
- Stickers and photos: which ones, at which line, on which side.
- Cover text, checked for flagged words.
- **Checkpoint 2B.**

## 3. Key frames, before the full render
- Measure the top of the speaker's head and their chin (`head_top`, `bio_top`).
- Run `build_edit.py --dry`, then `keyframes.py`. This renders stills of:
  - the opening;
  - a two-line subtitle during the bio card;
  - each photo moment;
  - all viewpoints showing;
  - a sticker;
  - the end card.
- Flag anything close to the face.
- **Checkpoint 3:** adjust and re-render until the layout is approved.

## 4. Render and check
Before sending the render:
- Picture/sound sync, to within one frame.
- No clipped sentence endings: transcribe the edited voice again and compare.
- Subtitle timing, loudness of about −14 LUFS, and no flagged words left.
- **Checkpoint 4:** feedback becomes v2, v3, … Each version goes in its own `exports/vN/` folder and never overwrites an earlier one.

## 5. Cover
- The creator sends a 3:4 photo, or a screenshot of a frame with its rough time in the original footage. The screenshot is matched to the exact frame.
- `cover.py` builds the cover. Each new version is saved as a new file (`cover.png`, `cover-2.png`, …).
- **Checkpoint 5.**

## 6. Wrap-up
- Anything new learned goes into `DESIGN_RULES.md`.
- With the creator's OK, delete the raw footage and the large working files (`work/edit/*/pass1.mov`). Keep the exports, transcript and settings, so the video can still be re-cut later from a fresh copy of the footage.
