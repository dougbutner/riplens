---
name: lyrics
description: >
  Local lyric extraction and subtitle burn for RipLens. Demucs vocal stem
  (optional) + faster-whisper transcription → editable SRT. No cloud APIs.
  Use when adding, fixing, or documenting riplens lyrics / --subs / fonts/.
---

# RipLens lyrics

Canonical code: `riplens/lyrics.py`, `riplens/subtitles.py`.

## Why this stack

Sung words on a dense mix defeat vanilla speech-to-text. 2026 local practice:

1. **Isolate the vocal first.** HTDemucs (`htdemucs`, MIT, Meta) is the free benchmark. `--two-stems=vocals` is enough. Fine-tuned `htdemucs_ft` is slower and cleaner; default is `htdemucs` so a Mac finishes a 4-minute song in about a minute on MPS.
2. **Transcribe the stem, not the mix.** `faster-whisper` (CTranslate2) with **VAD off**. Silero VAD is trained on speech and will drop sung phrases.
3. **Word timestamps → packed cues.** Max ~42 characters, ~4.4s, split on pauses ≥ 0.42s. Two lines max.
4. **The SRT is the source of truth.** Never overwrite unless `--force`. A human edits one file; render reads it.

Center-channel FFmpeg extract is the fallback when Demucs is not installed (vocals usually sit in the middle of a stereo pop/electronic mix).

Do not call lyric APIs, Genius, Musixmatch, or OpenAI.

## Commands

```
riplens lyrics
riplens lyrics --song sources/music/track.mp3 --model small
riplens lyrics --force --model medium
riplens render --subs
riplens render --no-subs
```

Models: `base` (fast, rough), `small` (default), `medium` (better singing), `large-v3` (if VRAM allows).

Optional extras (`pyproject.toml`):

```
pip install 'riplens[lyrics]'   # faster-whisper
pip install 'riplens[stems]'    # demucs
```

## Files

```
sources/lyrics/<stem>.srt          ← edit this
sources/lyrics/<stem>.txt          ← plain proofread
sources/lyrics/<stem>.words.json   ← word timings
sources/lyrics/_stems/<stem>.vocals.wav
fonts/                             ← 100+ commercial-free families
```

## Burn

PIL FreeType overlay, after grain, so captions sit on top of glyphs/solids. White fill, dark stroke, dim rounded pill — survives bright plates. Font resolves from `fonts/` by substring (`Montserrat-ExtraBold` default).

Studio toggle is independent of glyphs/solids. Studio timebase is `audio.currentTime()`, not wall clock.

## Mac

- `faster-whisper` CPU int8 is the reliable default (CTranslate2 has no MPS path).
- `demucs` uses Apple Silicon MPS when torch MPS is available.
- Homebrew `ffmpeg` already has `libass` if you ever want an ffmpeg subtitles filter; the Python burn does not need it.
