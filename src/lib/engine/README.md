# Live canvas engine

These TypeScript files are the browser gate. They must stay in lockstep with
the Python renderer:

| Browser | Python |
|---|---|
| `types.ts` `EFFECT_ORDER` | `riplens/__init__.py` |
| `effects.ts` | `riplens/effects.py` |
| `glyphs.ts` | `riplens/glyphs.py` |
| `audio.ts` HSV map | `riplens/audio.py` |
| `subtitles.ts` | `riplens/subtitles.py` |

If you change a look, a glyph, or the HSV formulas, update both sides and
`skills/glitch-visualizer/SKILL.md` in the same commit.
