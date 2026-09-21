export interface Cue {
  start: number;
  end: number;
  text: string;
}

const TIME = /(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;

export function parseTime(ts: string): number {
  const m = TIME.exec(ts.trim());
  if (!m) return 0;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / 1000;
}

export function parseSrt(raw: string): Cue[] {
  const text = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/^WEBVTT.*\n/, "");
  const blocks = text.trim().split(/\n\s*\n/);
  const timeLine = /(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})/;
  const cues: Cue[] = [];
  for (const block of blocks) {
    const lines = block.split("\n").filter((ln) => ln.trim() !== "");
    if (!lines.length) continue;
    let i = 0;
    if (/^\d+$/.test(lines[0]!.trim())) i = 1;
    const m = timeLine.exec(lines[i] ?? "");
    if (!m) continue;
    const body = lines
      .slice(i + 1)
      .join("\n")
      .replace(/<[^>]+>/g, "")
      .trim();
    if (!body) continue;
    cues.push({ start: parseTime(m[1]!), end: parseTime(m[2]!), text: body });
  }
  return cues;
}

export function cueAt(cues: Cue[], t: number): Cue | null {
  for (const c of cues) {
    if (t >= c.start && t < c.end) return c;
  }
  return null;
}

/** Spread a lyric sheet across the take so a .txt can preview before CLI align. */
export function cuesFromPlain(raw: string, duration: number): Cue[] {
  const lines = raw
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s && !s.startsWith("#") && !/-->/.test(s));
  if (!lines.length || duration <= 0) return [];
  const weights = lines.map((l) => Math.max(l.length, 8));
  const total = weights.reduce((a, b) => a + b, 0);
  const cues: Cue[] = [];
  let t = duration * 0.03;
  const span = Math.max(duration * 0.94 - t, 1);
  for (let i = 0; i < lines.length; i++) {
    const d = (weights[i]! / total) * span;
    const end = i === lines.length - 1 ? duration * 0.97 : t + d;
    cues.push({ start: t, end: Math.max(t + 0.5, end), text: lines[i]! });
    t = cues[cues.length - 1]!.end;
  }
  return cues;
}

export const CAPTION_FONTS: { id: string; name: string; file: string }[] = [
  { id: "montserrat", name: "Montserrat ExtraBold", file: "/fonts/Montserrat-ExtraBold.ttf" },
  { id: "inter", name: "Inter Bold", file: "/fonts/Inter-Bold.ttf" },
  { id: "poppins", name: "Poppins Bold", file: "/fonts/Poppins-Bold.ttf" },
  { id: "satoshi", name: "Satoshi Bold", file: "/fonts/Satoshi-Bold.ttf" },
  { id: "clash", name: "Clash Display Bold", file: "/fonts/ClashDisplay-Bold.ttf" },
  { id: "general", name: "General Sans Bold", file: "/fonts/GeneralSans-Bold.ttf" },
  { id: "anton", name: "Anton", file: "/fonts/Anton-Regular.ttf" },
  { id: "bebas", name: "Bebas Neue", file: "/fonts/BebasNeue-Regular.ttf" },
  { id: "atkinson", name: "Atkinson Hyperlegible", file: "/fonts/AtkinsonHyperlegible-Bold.ttf" },
  { id: "oswald", name: "Oswald Bold", file: "/fonts/Oswald-Bold.ttf" },
];

const loaded = new Map<string, Promise<string>>();

export function loadCaptionFont(file: string, family = "RipLensCaption"): Promise<string> {
  const key = `${family}::${file}`;
  const hit = loaded.get(key);
  if (hit) return hit;
  const p = (async () => {
    const face = new FontFace(family, `url(${file})`);
    const ok = await face.load();
    document.fonts.add(ok);
    return family;
  })();
  loaded.set(key, p);
  return p;
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const paras = text.split("\n").map((s) => s.trim()).filter(Boolean);
  const lines: string[] = [];
  for (const para of paras) {
    const words = para.split(/\s+/);
    let line = "";
    for (const w of words) {
      const trial = line ? `${line} ${w}` : w;
      if (ctx.measureText(trial).width <= maxW || !line) line = trial;
      else {
        lines.push(line);
        line = w;
      }
    }
    if (line) lines.push(line);
  }
  return lines.slice(0, 3);
}

export function drawSubtitles(
  ctx: CanvasRenderingContext2D,
  text: string,
  w: number,
  h: number,
  fontFamily = "RipLensCaption",
) {
  const size = Math.max(16, Math.round(h * 0.052));
  const stroke = Math.max(3, Math.round(size * 0.12));
  ctx.save();
  ctx.font = `700 ${size}px "${fontFamily}", "Montserrat", system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const lines = wrapText(ctx, text, w * 0.86);
  const gap = size * 0.18;
  const lineH = size * 1.12;
  const blockH = lines.length * lineH + (lines.length - 1) * gap;
  const y0 = h - h * 0.09 - blockH;
  const x = w / 2;
  let maxLine = 0;
  for (const ln of lines) maxLine = Math.max(maxLine, ctx.measureText(ln).width);
  const padX = size * 0.55;
  const padY = size * 0.32;
  ctx.fillStyle = "rgba(8,7,6,0.58)";
  const bw = maxLine + padX * 2;
  const bh = blockH + padY * 2;
  const bx = x - bw / 2;
  const by = y0 - padY;
  const r = size * 0.35;
  ctx.beginPath();
  ctx.moveTo(bx + r, by);
  ctx.arcTo(bx + bw, by, bx + bw, by + bh, r);
  ctx.arcTo(bx + bw, by + bh, bx, by + bh, r);
  ctx.arcTo(bx, by + bh, bx, by, r);
  ctx.arcTo(bx, by, bx + bw, by, r);
  ctx.closePath();
  ctx.fill();
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.strokeStyle = "rgba(12,10,8,0.92)";
  ctx.lineWidth = stroke;
  ctx.fillStyle = "rgb(255,252,245)";
  lines.forEach((ln, i) => {
    const y = y0 + i * (lineH + gap);
    ctx.strokeText(ln, x, y);
    ctx.fillText(ln, x, y);
  });
  ctx.restore();
}
