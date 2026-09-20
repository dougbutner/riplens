# RipLens agent contract

This file is binding for any agent (Cursor, Claude, Grok, Copilot, …) working in this repository.

## What this repo is

A **local** music-video renderer. Songs in `sources/music`, art in `sources/images`, optional B-roll in `sources/videos`. Output is three H.264 MP4 folders: `output/1x1`, `output/16x9`, `output/9x16`.

No generative AI. No network calls at render time. No SaaS APIs.

## Hard rule — keep the skill in lockstep

**If you change any of the following, you MUST update `skills/glitch-visualizer/SKILL.md` in the same commit:**

- `riplens/effects.py` — any look, blend mode, peel geometry, Julia constants
- `riplens/audio.py` — HSV mapping (`h`/`s`/`v` formulas), band edges, RMS normalization
- `riplens/__init__.py` — `EFFECT_ORDER` or `RATIOS`
- `config.yaml` defaults for `threshold`, `cooldown`, `effects` list, output sizes

The skill is how other people (and other agents) **copy the exact glitch patterns**. A recipe that exists only in Python is a bug.

If you add an eleventh look, append it to `EFFECT_ORDER`, `REGISTRY`, `config.yaml`, the README table, and the skill. Same commit.

## Do not

- Call OpenAI, xAI, Replicate, Runway, or any image/video generation endpoint
- Introduce MoviePy as a required path (FFmpeg pipe is the encoder)
- Mix the three aspect ratios into one folder
- Change output pixel formats away from `yuv420p` (breaks YouTube / Instagram)
- Commit user songs or artwork

## Do

- Keep libraries lightweight: numpy, opencv-python-headless, librosa, soundfile, pyyaml, tqdm, imageio-ffmpeg
- Prefer NVENC when `nvidia-smi` works, else libx264 CRF 18
- Cover-crop art (never stretch)
- Cycle looks on a **rising-edge RMS threshold**, with cooldown
- Ride HSV geometry on every frame, even when another look is active

## Commands you run for the user

```bash
riplens doctor
riplens analyze
riplens render
riplens render --ratio 9x16
riplens render --song sources/music/track.wav --threshold 0.7
```

Explain those. Do not invent a second CLI.
