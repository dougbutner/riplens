# Lyrics

Accurate captions start with the **words**, not with a speech model.

1. Put the lyric sheet at `sources/lyrics/<stem>.txt` — one phrase per line.
2. `riplens lyrics` isolates the vocal and times each line locally (FFmpeg + NumPy). No Whisper. No API.
3. Open `<stem>.srt` if a line lands late. Fix words in the `.txt`, then `riplens lyrics --force`.
4. `riplens render --subs` burns the SRT.

An `.lrc` next to the song, or ID3 unsynced lyrics in the audio file, are used if no `.txt` is present.

`riplens lyrics --asr whisper` can draft words from the audio (`pip install faster-whisper`). Treat that as a sketch — singing is not speech, and a rap will come out wrong.
