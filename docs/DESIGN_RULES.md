# Design rules

Each rule came from a problem in a real published video. The version where it was added is noted in brackets.

## Cutting and pace
- **Tight but natural pauses.** About 0.15 s between phrases: 0.18 s after a sentence and 0.10 s mid-sentence. No silence over about 0.3 s. *(v1: viewers wanted a faster pace.)*
- **Never cut while the voice is audible.** Each cut runs on up to 0.3 s until the voice fades, because Whisper often ends a word before its last syllable. *(v1: sentence endings were clipped.)*
- **Repeated takes:** keep the last take.
- **Stray sounds at a join** (a breath, a click, the first syllable of a false start) survive a normal cut. Remove them with `exact = [[start, end]]`, placed in the quiet dip, and check the join by re-transcribing.
- **Cut 0.02 s before a word, never exactly on it.** Whisper stores times like 56.539999, so a cut ending at 56.54 silently drops that word.
- **Words lost at a retake.** At a false start, Whisper often folds the pause and the real take into one long word that starts inside the cut. Because the cut list is built from word timings, that word disappears from the audio as well as the subtitles. The fix is `fix_transcript.py`: it re-transcribes the kept stretch and splices the words back in.

## Picture and sound
- **Phones start recording sound slightly after the picture** (0.72 s on the first video). The audio start is measured and both streams are shifted to match.
- **Voice chain:** high-pass filter, RNNoise denoising, EQ, compression, then about −14 LUFS.
- **Music** sits 15 dB under the voice, is ducked further while the speaker talks, and fades in and out.
- **Sound effects:** whoosh on viewpoints and pop-ups, glitch on photos, pop on stickers, ding on key lines, click on the follow button.

## Subtitles
- Each subtitle appears 0.1 s before the words are spoken.
- **Lines break only between words.** Segmentation uses jieba for Chinese. No line starts with a particle, and names never split (`whole = [...]`).
- **No subtitle shorter than about 0.7 s;** very short ones merge with their neighbours.
- **Except across a topic change.** A finished sentence followed by a pause of more than 0.8 s never joins the next line.
- **Key words** are in the highlight colour and about 30% bigger.
- **Platform compliance.** Flagged words are removed from the subtitles only; the voice is unchanged and the rest of the sentence still shows. Words that must stay readable are respelled instead (`swap`). Every build prints what it hid or swapped, and warns if titles, pop-ups or the cover use a flagged word.
- **Comment keywords as a pop-up.** When viewers are asked to comment a keyword, the subtitle drops the word and a pop-up box shows it under the title.

## Layout: the face is never covered
- **Everything at the top stays above `head_top`,** the measured top of the speaker's head.
- **Stickers** sit at shoulder height at the sides, below the chin and above the subtitles.
- **The title tab** stays up for the whole video. The title is always bigger than the viewpoint chips; a long title shrinks only as far as it needs to fit.
- **Viewpoint chips** (01, 02, …) are added as each point is reached, and earlier ones stay.
- **One thing at a time.** Chips and the bio card hide while any b-roll is on screen. B-roll less than 0.8 s apart counts as one block, so nothing flickers.
- **The bio card** starts at the self-introduction ("I'm …", set in `profile.toml`), as long as no b-roll is up. Otherwise it shows at the opening, or at the first clear stretch after the introduction.
- **B-roll fills the screen.**
  - Portrait photos and clips are cropped to fill the frame.
  - Landscape ones show whole on a blurred, darkened copy of themselves.
  - Screenshots and documents can be forced to show whole (`fill = "whole"`).
  - Clip sound is muted.
- **The end card** starts only after the last word.
- **No emoji.**

## Animations
- **Short labels:** 10 reading units or fewer (one per Chinese character, two per English word), never full sentences.
- **Not rushed:** new elements at least 0.8 s apart, and no more than about 3 reading units per second.
- **Calm ending:** everything is in place 2.5 s before the end, and the last frame holds still. If the line an animation covers is too short, cut content rather than speed up.
- **Clear of the overlays:** content sits in the middle of the frame (y 520–1320), so the title, chips and subtitles never cover it.
- `pace_check()` warns about each of these.

## Covers
- **3:4 (1080×1440).** An outlined headline at the top, the face clear in the middle, and two short lines at the bottom.
- **The headline sits above the hair.** With high hair, keep it to one line.
- **Markup:** `[words]` puts key words in the highlight colour and `{3}` makes big numbers in the accent colour. The two bottom lines are 1.45× the line size apart.
- **Long headlines** break at `|`, and any line that's too wide shrinks to fit.

## Files
- **Never overwrite a finished render or cover.** Every render goes to `exports/vN/`, and every cover is a new file. A render only appears in exports once it has fully finished.
