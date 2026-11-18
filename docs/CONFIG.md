# Configuration reference

Everything specific to one video lives in its `video.toml`. Copy `videos/_template/`, which has every field with a comment.

**Markup in any on-screen text:**
- `[words]`: key words in the highlight colour.
- `{words}`: big numbers in the accent colour (covers).
- `|`: line break (cover headline).

**Timing by speech:** most overlays are placed by the words being spoken, not by timestamps.
- `at = "words"`: starts when those words are said.
- `until = "words"`: ends when those words are said.
- `after = 120`: only matches after 120 s of raw footage (for words said more than once).

| Section | Key fields |
|---|---|
| top level | `title`, `language`, `speed`, `title_scale`, `chip_scale`, `head_top`, `bio_top`, `photo_style`, `points_layout`, `sticker_y`, `music` |
| `[transcribe]` | `terms` (names to spell right), `fix` (stretches to re-transcribe) |
| `[cut]` | `remove` (retakes, by word), `exact` (exact audio ranges) |
| `[subtitles]` | `replace`, `keywords`, `dings`, `whole`, `swap`, `keep`, `hide` |
| `[top_title]` | `text`, `label` |
| `[[points]]` | `text`, `at`, `after`, `label` |
| `[[popups]]` | `label`, `text`, `at`, `seconds` |
| `[[photos]]` | `file`, `caption`, `caption_en`, `at`, `until`, `fill`, `rotate`, `start` |
| `[[stickers]]` | `file`, `width`, `at`, `side`, `seconds` |
| `[bio]` | overrides the bio card in `library/brand/profile.toml`: `enabled`, `at`, `lines`, `seconds`, `position` |
| `[end_card]` | `tagline` |
| `[cover]` | `photo`, `photo_head_top`, `face_x` (or `frame`, `frame_footage`, `frame_exact`), `tag`, `headline`, `line1`, `line2`, `line_size`, `line_spacing` |

**Shared files:**
- `library/brand/theme.toml`: every colour and font (the fonts themselves go in `toolkit/fonts/`).
- `library/brand/profile.toml`: handle and bio card.
- `library/language/<code>.toml`: the Whisper language and prompt, filler words, line-break rules and end-card buttons.
- `library/platform/sensitive_words.toml`: `hide` and `swap` lists.
