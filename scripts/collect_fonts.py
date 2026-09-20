#!/usr/bin/env python3
"""Collect 100+ commercial-free fonts into pipeline/fonts/.

Sources (all free for commercial use):
- Fontshare / Indian Type Foundry  — every family (ITF Free Font License or OFL)
- Google Fonts faces recommended in 2024–2026 subtitle/video articles (OFL / Apache)
- A few Velvetyne + League of Moveable Type display cuts (OFL)

One subtitle-weight file per family (Bold / ExtraBold / the only cut).
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "fonts"
UA = "RipLens/1.0 (local subtitle font collector; OFL+ITF-FFL)"


def fetch(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ext_from(blob: bytes, url: str = "") -> str:
    if blob[:4] == b"wOFF":
        return ".woff"
    if blob[:4] == b"wOF2":
        return ".woff2"
    if blob[:4] == b"OTTO":
        return ".otf"
    if blob[:4] == b"\x00\x01\x00\x00":
        return ".ttf"
    if blob[:2] == b"PK":
        return ".zip"
    lower = url.lower()
    for e in (".ttf", ".otf", ".woff2", ".woff"):
        if e in lower:
            return e
    return ".ttf"


def save_font(dest: Path, blob: bytes) -> Path | None:
    kind = ext_from(blob)
    if kind == ".zip":
        return None
    if kind in {".woff", ".woff2"}:
        return None
    dest = dest.with_suffix(kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return dest


def pick_style(styles: list[dict]) -> dict | None:
    static = [
        s
        for s in styles
        if not s.get("is_variable") and not s.get("is_italic") and s.get("file")
    ]
    if not static:
        static = [s for s in styles if s.get("file") and not s.get("is_italic")]
    if not static:
        return None

    def score(s: dict) -> tuple:
        w = (s.get("weight") or {}).get("number") or (s.get("weight") or {}).get("weight") or 400
        try:
            w = int(w)
        except (TypeError, ValueError):
            w = 400
        prefer = {800: 0, 700: 1, 900: 2, 600: 3, 500: 4, 400: 5}
        return (prefer.get(w, 10 + abs(w - 700)), w)

    static.sort(key=score)
    return static[0]


def collect_fontshare() -> list[dict]:
    print("Fontshare API…")
    raw = fetch("https://api.fontshare.com/v2/fonts")
    data = json.loads(raw.decode("utf-8"))
    fonts = data.get("fonts") or data if isinstance(data, list) else data.get("fonts", [])
    catalog = []
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for fam in fonts:
        name = fam.get("name") or fam.get("slug") or "unknown"
        slug = fam.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        license_type = fam.get("license_type") or "itf_ffl"
        style = pick_style(fam.get("styles") or [])
        if not style:
            print(f"  skip {name} (no file)")
            continue
        file_url = style["file"]
        if file_url.startswith("//"):
            file_url = "https:" + file_url
        if not file_url.lower().endswith((".ttf", ".otf", ".woff2", ".woff")):
            file_url = file_url + ".ttf"
        weight = (style.get("weight") or {}).get("label") or (style.get("weight") or {}).get("name") or "Regular"
        safe = re.sub(r"[^A-Za-z0-9_-]+", "", name.replace(" ", ""))
        dest = FONT_DIR / "fontshare" / f"{safe}-{weight.replace(' ', '')}"
        existing = None
        for e in (".ttf", ".otf"):
            if dest.with_suffix(e).is_file():
                existing = dest.with_suffix(e)
                break
        if existing:
            catalog.append(
                {
                    "family": name,
                    "file": str(existing.relative_to(FONT_DIR)),
                    "source": "Fontshare / Indian Type Foundry",
                    "license": "OFL-1.1" if "ofl" in license_type.lower() or license_type == "ofl" else "ITF Free Font License",
                    "weight": weight,
                    "why": "Fontshare original or hosted family — free commercial use",
                }
            )
            continue
        try:
            blob = fetch(file_url)
            saved = save_font(dest, blob)
        except Exception as exc:
            print(f"  fail {name}: {exc}")
            continue
        if not saved:
            print(f"  skip {name} (not ttf/otf)")
            continue
        print(f"  {name:28} {weight:12} {saved.name}")
        catalog.append(
            {
                "family": name,
                "file": str(saved.relative_to(FONT_DIR)),
                "source": "Fontshare / Indian Type Foundry",
                "license": "OFL-1.1" if "ofl" in str(license_type).lower() else "ITF Free Font License",
                "weight": weight,
                "why": "Fontshare — free for personal and commercial use (video, print, apps)",
            }
        )
        time.sleep(0.05)
    return catalog


# Article-backed subtitle / video faces from:
# Blitzcut 2026 "only 8 you need", Monty subtitle study (2M videos),
# SpotlightFX 2026, Creative Bloq accessible subtitles, TubeLab YouTuber list,
# transcript.lol 2026 Inter/Noto/Atkinson.
GOOGLE_EXTRA = [
    ("Montserrat", "Blitzcut 2026 / Monty 2M-video study — default captions, ExtraBold"),
    ("Inter", "transcript.lol 2026 / SpotlightFX — screen captions"),
    ("Poppins", "Blitzcut 2026 / Creative Bloq — lifestyle captions"),
    ("Roboto", "Blitzcut 2026 — YouTube default caption cousin"),
    ("Open Sans", "SpotlightFX 2026 — workhorse overlays"),
    ("Lato", "Creative Bloq accessible subtitles"),
    ("Work Sans", "Open Foundry list — UI captions"),
    ("DM Sans", "Geometric captions"),
    ("Nunito", "Round geometric captions"),
    ("Space Grotesk", "Tech titles"),
    ("Outfit", "Friendly geometric"),
    ("Barlow", "Semi-condensed motion captions"),
    ("Archivo", "Grotesque captions"),
    ("Source Serif 4", "Adobe open serif quotes"),
    ("IBM Plex Serif", "Editorial serif"),
    ("IBM Plex Mono", "Tech / data captions"),
    ("JetBrains Mono", "Code / HUD captions"),
    ("Geist", "Vercel OFL — modern UI captions"),
    ("Plus Jakarta Sans", "Contemporary grotesque"),
    ("Figtree", "Friendly geometric captions"),
    # (api family, why)
    ("Anton", "Blitzcut 2026 / TubeLab — hooks, one-word emphasis"),
    ("Bebas Neue", "Blitzcut 2026 / TubeLab — titles, chapter cards"),
    ("Archivo Black", "Blitzcut 2026 / TubeLab — high-energy titles"),
    ("Atkinson Hyperlegible Next", "Creative Bloq / Braille Institute — maximum caption accessibility"),
    ("Atkinson Hyperlegible", "Braille Institute — accessible subtitles"),
    ("Bangers", "TubeLab YouTuber list — comic display"),
    ("Russo One", "Sports/motion display, high x-height"),
    ("Orbitron", "Sci-fi / electronic titles"),
    ("IBM Plex Sans", "Corporate-neutral captions"),
    ("Source Sans 3", "SpotlightFX 2026 — Adobe open caption face"),
    ("Noto Sans", "transcript.lol 2026 — world-script captions"),
    ("Instrument Sans", "Editorial UI captions"),
    ("Figtree", "Friendly geometric captions"),
    ("Urbanist", "Modern geometric, music-video titles"),
    ("Sora", "Clean geometric body captions"),
    ("Lexend", "Designed for reading fluency — caption readability"),
    ("Red Hat Display", "Open corporate display"),
    ("Fraunces", "Soft serif titles / quotes"),
    ("Newsreader", "Editorial serif titles"),
    ("Bitter", "Low-contrast serif captions"),
    ("Merriweather", "Screen serif, long-form captions"),
    ("Crimson Pro", "Book serif quotes"),
    ("Playfair Display", "Blitzcut 2026 — editorial / luxury titles"),
    ("Cinzel", "Stone-carved display, ritual/myth titles"),
    ("Abril Fatface", "Didone poster titles"),
    ("Black Ops One", "Stencil / military display"),
    ("Bungee", "Sign-painter display"),
    ("Fredoka", "Round geometric, kid-friendly captions"),
    ("Karla", "Grotesque captions"),
    ("Rubik", "Monty 2025 study — #2 short-form caption face"),
    ("Mulish", "News gothic captions"),
    ("Josefin Sans", "Geometric vintage titles"),
    ("Jost", "Futura revival, film titles"),
    ("Saira", "Semi-condensed motion captions"),
    ("Exo 2", "Tech / electronic titles"),
    ("Chakra Petch", "Square tech display"),
    ("Syncopate", "Wide futurist titles"),
    ("Permanent Marker", "Hand marker captions"),
    ("Special Elite", "Typewriter captions"),
    ("Press Start 2P", "Pixel / game titles"),
    ("VT323", "CRT / VHS captions"),
    ("Silkscreen", "Pixel caps"),
    ("Monoton", "Neon tube display"),
    ("Audiowide", "Wide techno titles"),
    ("Pacifico", "Brush script"),
    ("Lobster", "Classic script titles"),
    ("Dancing Script", "Casual script"),
    ("Caveat", "Handwritten captions"),
    ("Great Vibes", "Formal script"),
    ("Unbounded", "Monty niche table — tech/crypto titles"),
    ("Gabarito", "Monty 2025 study — #4 short-form caption face"),
    ("Onest", "Monty — education/explainer captions"),
    ("Manrope", "Monty — talking-head captions"),
    ("Nunito Sans", "Monty — personal brand captions"),
    ("Commissioner", "Monty — calm grotesque"),
    ("Fira Sans Condensed", "Monty 2025 study — #3 short-form caption; sport/motion"),
    ("PT Sans Narrow", "Monty sport/fitness condensed"),
    ("Geologica", "Monty tech table"),
    ("Golos Text", "Monty education captions"),
    ("Oswald", "Monty sport condensed; TubeLab list"),
    ("Raleway", "TubeLab YouTuber list"),
    ("Alfa Slab One", "Slab poster titles"),
    ("Staatliches", "Condensed gothic titles"),
    ("Teko", "Indian Type Foundry on Google Fonts — condensed sports"),
    ("Khand", "ITF condensed display"),
    ("Titan One", "Heavy comic display"),
    ("Bowlby One", "Ultra-bold poster"),
    ("Big Shoulders Display", "Condensed display, Chicago-inspired"),
    ("Unbounded", "repeat-skip"),
]


def collect_google(already: set[str]) -> list[dict]:
    catalog = []
    dest_root = FONT_DIR / "ofl"
    dest_root.mkdir(parents=True, exist_ok=True)
    seen = set()
    for family, why in GOOGLE_EXTRA:
        key = family.lower()
        if key in seen:
            continue
        seen.add(key)
        if any(key.replace(" ", "") == a.replace(" ", "").lower() for a in already):
            continue
        url = "https://fonts.google.com/download?family=" + urllib.parse.quote(family)
        slug = re.sub(r"[^A-Za-z0-9]+", "", family)
        marker = dest_root / f"{slug}.done"
        # pick an existing file if we already unpacked
        existing = list(dest_root.glob(f"{slug}-*.ttf")) + list(dest_root.glob(f"{family.replace(' ', '')}-*.ttf"))
        if existing:
            catalog.append(
                {
                    "family": family,
                    "file": str(existing[0].relative_to(FONT_DIR)),
                    "source": "Google Fonts",
                    "license": "OFL-1.1 or Apache-2.0",
                    "weight": existing[0].stem.split("-")[-1],
                    "why": why,
                }
            )
            continue
        print(f"  Google {family}…")
        try:
            blob = fetch(url)
        except Exception as exc:
            print(f"    fail: {exc}")
            continue
        if ext_from(blob) != ".zip":
            saved = save_font(dest_root / f"{slug}-Regular", blob)
            if saved:
                catalog.append(
                    {
                        "family": family,
                        "file": str(saved.relative_to(FONT_DIR)),
                        "source": "Google Fonts",
                        "license": "OFL-1.1",
                        "weight": "Regular",
                        "why": why,
                    }
                )
            continue
        try:
            zf = zipfile.ZipFile(BytesIO(blob))
        except zipfile.BadZipFile:
            print("    not a zip")
            continue
        chosen = _pick_zip_member(zf.namelist())
        if not chosen:
            print("    no ttf in zip")
            continue
        raw = zf.read(chosen)
        weight = Path(chosen).stem.split("-")[-1] if "-" in Path(chosen).stem else "Regular"
        saved = save_font(dest_root / f"{slug}-{weight}", raw)
        if saved:
            print(f"    {saved.name}")
            catalog.append(
                {
                    "family": family,
                    "file": str(saved.relative_to(FONT_DIR)),
                    "source": "Google Fonts",
                    "license": "OFL-1.1 or Apache-2.0",
                    "weight": weight,
                    "why": why,
                }
            )
        time.sleep(0.08)
    return catalog


def _pick_zip_member(names: list[str]) -> str | None:
    files = [n for n in names if n.lower().endswith((".ttf", ".otf"))]
    if not files:
        return None

    def score(n: str) -> tuple:
        low = n.lower()
        stem = Path(n).stem.lower()
        italic = 50 if "italic" in stem or "oblique" in stem else 0
        var = 40 if "[" in n or "variable" in low else 0
        static_bonus = 0 if "/static/" in low or "static/" in low else 8
        prefer = 8
        for i, tag in enumerate(["extrabold", "extra-bold", "bold", "black", "semibold", "semi-bold", "regular"]):
            if tag in stem.replace(" ", "").replace("_", ""):
                prefer = i
                break
        return (italic, var, static_bonus, prefer, len(n))

    files.sort(key=score)
    return files[0]


# League of Moveable Type + Velvetyne — OFL display cuts good for music video type.
LEAGUE = [
    (
        "League Gothic",
        "https://github.com/theleagueof/league-gothic/raw/master/fonts/LeagueGothic-Regular.otf",
        "The League of Moveable Type — condensed gothic titles",
    ),
    (
        "Oswald (League)",
        "https://github.com/theleagueof/oswald/raw/master/Oswald-Regular.ttf",
        "The League of Moveable Type",
    ),
    (
        "Blackout Midnight",
        "https://github.com/theleagueof/blackout/raw/master/Blackout%20Midnight.ttf",
        "The League of Moveable Type — heavy night display",
    ),
    (
        "Knewave",
        "https://github.com/theleagueof/knewave/raw/master/knewave.ttf",
        "The League of Moveable Type — brush display",
    ),
    (
        "Chunk",
        "https://github.com/theleagueof/chunk/raw/master/Chunk.otf",
        "The League of Moveable Type — slab poster",
    ),
    (
        "Raleway (League)",
        "https://github.com/theleagueof/raleway/raw/master/fonts/Raleway-Bold.otf",
        "The League of Moveable Type",
    ),
]


def collect_league() -> list[dict]:
    catalog = []
    dest_root = FONT_DIR / "league"
    dest_root.mkdir(parents=True, exist_ok=True)
    for name, url, why in LEAGUE:
        slug = re.sub(r"[^A-Za-z0-9]+", "", name)
        dest = dest_root / slug
        existing = next((dest.with_suffix(e) for e in (".ttf", ".otf") if dest.with_suffix(e).is_file()), None)
        if existing:
            catalog.append(
                {
                    "family": name,
                    "file": str(existing.relative_to(FONT_DIR)),
                    "source": "The League of Moveable Type",
                    "license": "OFL-1.1",
                    "weight": "Regular",
                    "why": why,
                }
            )
            continue
        print(f"  League {name}…")
        try:
            blob = fetch(url)
            saved = save_font(dest, blob)
        except Exception as exc:
            print(f"    fail: {exc}")
            continue
        if saved:
            catalog.append(
                {
                    "family": name,
                    "file": str(saved.relative_to(FONT_DIR)),
                    "source": "The League of Moveable Type",
                    "license": "OFL-1.1",
                    "weight": "Regular",
                    "why": why,
                }
            )
    return catalog


def copy_studio_subset(catalog: list[dict]) -> None:
    """A handful of caption faces for the browser studio."""
    public = Path("/workspace/public/fonts")
    public.mkdir(parents=True, exist_ok=True)
    wanted = [
        "Montserrat-ExtraBold",
        "Montserrat-Bold",
        "Inter-Bold",
        "Poppins-Bold",
        "Satoshi-Bold",
        "ClashDisplay-Bold",
        "GeneralSans-Bold",
        "Anton-Regular",
        "Anton-Bold",
        "BebasNeue-Regular",
        "AtkinsonHyperlegible-Bold",
        "AtkinsonHyperlegibleNext-Bold",
        "Oswald-Bold",
        "CabinetGrotesk-Bold",
        "Switzer-Bold",
        "Zodiak-Bold",
    ]
    copied = 0
    for row in catalog:
        src = FONT_DIR / row["file"]
        if not src.is_file():
            continue
        stem = src.stem.replace(" ", "")
        if any(w.lower() in stem.lower() for w in wanted) or any(
            w.lower().replace("-", "") in stem.lower().replace("-", "") for w in wanted
        ):
            dest = public / src.name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())
            copied += 1
    # always copy Montserrat-ish as a predictable name if we got one
    print(f"studio subset → {public}  ({copied} files)")


def write_readme(catalog: list[dict]) -> None:
    lines = [
        "# RipLens subtitle fonts",
        "",
        "Commercial-free type for burning lyrics. One subtitle-weight file per family.",
        "",
        f"**{len(catalog)} families** collected.",
        "",
        "## Licenses",
        "",
        "- **SIL Open Font License 1.1** — Google Fonts, League of Moveable Type, most open foundries. Use, embed, modify, redistribute (do not sell the font files themselves).",
        "- **ITF Free Font License (Fontshare originals)** — free for personal and commercial use in video, print, apps, and logos. Do not resell the font files as fonts. See https://www.fontshare.com/licenses",
        "- **Apache 2.0** — a few Google-hosted faces (Roboto / Source).",
        "",
        "Videos you export with these faces are yours. Keep this folder next to `sources/`.",
        "",
        "## Default",
        "",
        "`config.yaml` → `subtitles.font` (default `Montserrat-ExtraBold` — the most-used short-form caption face in a 2025 2-million-video study).",
        "",
        "## Catalog",
        "",
        "| Family | File | License | Why |",
        "|---|---|---|---|",
    ]
    for row in sorted(catalog, key=lambda r: r["family"].lower()):
        why = row.get("why", "").replace("|", "/")
        lines.append(f"| {row['family']} | `{row['file']}` | {row['license']} | {why} |")
    lines += [
        "",
        "## Re-run",
        "",
        "```bash",
        "python3 scripts/collect_fonts.py",
        "```",
        "",
        "Already-downloaded files are skipped.",
        "",
    ]
    (FONT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (FONT_DIR / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")


def main() -> int:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    catalog: list[dict] = []
    print("== Fontshare / Indian Type Foundry ==")
    fs = collect_fontshare()
    catalog.extend(fs)
    already = {r["family"] for r in catalog}
    print(f"Fontshare families: {len(fs)}")
    print("== Google Fonts extras (article-recommended) ==")
    import urllib.parse  # noqa: used in collect_google

    go = collect_google(already)
    catalog.extend(go)
    print(f"Google extras: {len(go)}")
    print("== League of Moveable Type ==")
    lg = collect_league()
    catalog.extend(lg)
    print(f"League: {len(lg)}")
    # de-dupe by family name
    uniq: dict[str, dict] = {}
    for row in catalog:
        uniq.setdefault(row["family"].lower(), row)
    catalog = list(uniq.values())
    write_readme(catalog)
    copy_studio_subset(catalog)
    print(f"\nTOTAL  {len(catalog)} families  → {FONT_DIR}")
    if len(catalog) < 100:
        print("WARNING: under 100 — check network failures above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
