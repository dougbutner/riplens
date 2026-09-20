# Lyrics

`riplens lyrics` writes an **editable SRT** here, plus a plain `.txt` for proofreading.

1. Run `riplens lyrics` (needs `pip install faster-whisper`; optional `pip install demucs` for cleaner vocals).
2. Open `<stem>.srt` in any text editor. Fix words and timings.
3. `riplens render --subs` burns the SRT. The renderer will not overwrite your SRT unless you pass `--force`.

The `.words.json` file is the raw word timings if you want to rebuild cues.
