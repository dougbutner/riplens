---
name: lyrics
description: >
  Local lyric timing and subtitle burn for RipLens. Default: your lyric
  sheet timed to the vocal stem (FFmpeg + NumPy). No cloud APIs. Whisper
  is an optional last-resort draft. Use when adding, fixing, or documenting
  riplens lyrics / --subs / fonts/.
---

# RipLens lyrics

Canonical code: `riplens/lyrics.py`, `riplens/align.py`, `riplens/subtitles.py`.

## Why this stack

Sung words on a dense mix defeat speech-to-text. Whisper on a rap will
invent "Stewie" and "the Sims". The accurate, free, Mac-local path is:

1. **Start with the words.** `sources/lyrics/<stem>.txt` — one phrase per line.
   `.lrc` files and ID3 `USLT` tags work too.
2. **Isolate the vocal.** HTDemucs (`htdemucs`, MIT) `--two-stems=vocals` when
   installed. Else FFmpeg mid-channel extract (vocals usually sit in the middle
   of a stereo pop/electronic mix).
3. **Force-align lines to vocal energy.** RMS envelope, skip instrumental,
   snap boundaries to pauses. No model download. No API.
4. **The SRT is what gets burned.** Never overwrite unless `--force`. Edit the
   `.txt` for words, the `.srt` for a late line.

`--asr whisper` exists only as a draft if you have no lyric sheet. It is
optional (`pip install faster-whisper`) and will be wrong on singing. Do not
make it the default.

Do not call lyric APIs, Genius, Musixmatch, or OpenAI.

## Commands

```
riplens lyrics                         # align sources/lyrics/<stem>.txt → .srt
riplens lyrics --song sources/music/track.mp3
riplens lyrics --text path/to/words.txt --force
riplens lyrics --asr whisper --force   # optional audio draft, often wrong
riplens render --subs
riplens render --no-subs
```

Optional extras (`pyproject.toml`):

```
pip install 'riplens[stems]'    # demucs
pip install 'riplens[lyrics]'   # faster-whisper (draft only)
```

## Files

```
sources/lyrics/<stem>.txt          ← source of truth (you write this)
sources/lyrics/<stem>.srt          ← timed cues (aligner writes this)
sources/lyrics/<stem>.lrc          ← used as-is if present
sources/lyrics/<stem>.asr.txt      ← Whisper draft, never the source
sources/lyrics/_stems/<stem>.vocals.wav
fonts/                             ← 170 commercial-free families
```

## Burn

PIL FreeType overlay, after grain, so captions sit on top of glyphs/solids.
Fill + dark stroke + dim rounded pill — survives bright plates. Default is
**as-written casing** (`subtitles.uppercase: false`). Font resolves from
`fonts/` by substring (`Montserrat-ExtraBold` default).

Studio toggle is independent of glyphs/solids. Studio timebase is
`audio.currentTime()`, not wall clock.

## Mac

- Aligner needs FFmpeg + NumPy only (already required).
- `demucs` uses Apple Silicon MPS when torch MPS is available.
- `faster-whisper` CPU int8 is the optional draft (CTranslate2 has no MPS path).
