import type { AudioFeatures, EffectId, Hsv } from "./types";
import { coverDraw, hsvToRgb, rgbCss } from "./color";
import {
  SOLID_CYCLE,
  flowerCenters,
  fruitCenters,
  strokeSolid,
  type SolidKind,
} from "./geometry3d";
import { GLYPHS, drawGlyph } from "./glyphs";

export interface EffectCtx {
  w: number;
  h: number;
  t: number;
  feat: AudioFeatures;
  hsv: Hsv;
  src: CanvasImageSource;
  work: CanvasRenderingContext2D;
  scratch: CanvasRenderingContext2D;
  feedback: HTMLCanvasElement;
  plateIndex: number;
  plateCount: number;
  nextPlate: CanvasImageSource;
  peel: number;
}

function copySrc(c: EffectCtx) {
  c.work.save();
  coverDraw(c.work, c.src, c.w, c.h, 1 + c.feat.rms * 0.08);
  c.work.restore();
}

function kaleidoscope(c: EffectCtx) {
  const segments = 6 + Math.round((c.t * 0.55 + c.feat.bass * 8) % 11);
  const slice = (Math.PI * 2) / segments;
  const angle = c.t * (0.12 + c.feat.rms * 0.4);
  const cx = c.w / 2;
  const cy = c.h / 2;
  c.scratch.clearRect(0, 0, c.w, c.h);
  coverDraw(c.scratch, c.src, c.w, c.h, 1.05);
  c.work.fillStyle = "#0c0b0a";
  c.work.fillRect(0, 0, c.w, c.h);
  for (let i = 0; i < segments; i++) {
    c.work.save();
    c.work.translate(cx, cy);
    c.work.rotate(i * slice + angle);
    c.work.beginPath();
    c.work.moveTo(0, 0);
    const r = Math.hypot(cx, cy);
    c.work.arc(0, 0, r, -slice / 2, slice / 2);
    c.work.closePath();
    c.work.clip();
    if (i % 2 === 1) c.work.scale(1, -1);
    c.work.drawImage(c.scratch.canvas, -cx, -cy, c.w, c.h);
    c.work.restore();
  }
}

function chromatic(c: EffectCtx) {
  const ox = (8 + c.feat.bass * 28) * (c.feat.peak ? 1.6 : 1);
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  c.scratch.putImageData(img, 0, 0);
  c.work.globalCompositeOperation = "screen";
  c.work.fillStyle = "rgb(255,0,0)";
  c.work.globalAlpha = 0.55;
  c.work.drawImage(c.scratch.canvas, ox, 0);
  c.work.fillStyle = "rgb(0,0,255)";
  c.work.drawImage(c.scratch.canvas, -ox, 0);
  c.work.globalAlpha = 1;
  c.work.globalCompositeOperation = "source-over";
  c.work.filter = `hue-rotate(${c.hsv.h * 0.4}deg) saturate(${1 + c.hsv.s})`;
  c.work.drawImage(c.work.canvas, 0, 0);
  c.work.filter = "none";
}

function scanline(c: EffectCtx) {
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  const src = new Uint8ClampedArray(img.data);
  const amp = 12 + c.feat.rms * 48;
  const band = 6 + Math.floor(c.feat.treble * 18);
  for (let y = 0; y < c.h; y++) {
    const tear = Math.sin(y * 0.08 + c.t * 9) > 0.55;
    const shift = tear ? Math.round(Math.sin(y * 0.2 + c.t * 14) * amp) : Math.round(Math.sin(y * 0.4) * 2);
    for (let x = 0; x < c.w; x++) {
      const sx = (x + shift + c.w) % c.w;
      const di = (y * c.w + x) * 4;
      const si = (y * c.w + sx) * 4;
      img.data[di] = src[si] ?? 0;
      img.data[di + 1] = src[si + 1] ?? 0;
      img.data[di + 2] = src[si + 2] ?? 0;
    }
    if (y % band === 0) {
      for (let x = 0; x < c.w; x++) {
        const di = (y * c.w + x) * 4;
        img.data[di] = Math.max(0, (img.data[di] ?? 0) - 28);
        img.data[di + 1] = Math.max(0, (img.data[di + 1] ?? 0) - 28);
        img.data[di + 2] = Math.max(0, (img.data[di + 2] ?? 0) - 28);
      }
    }
  }
  c.work.putImageData(img, 0, 0);
}

function pixelSort(c: EffectCtx) {
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  const d = img.data;
  const thresh = 90 + c.feat.mid * 80;
  const step = c.feat.rms > 0.7 ? 1 : 2;
  for (let y = 0; y < c.h; y += step) {
    const row: number[] = [];
    for (let x = 0; x < c.w; x++) {
      const i = (y * c.w + x) * 4;
      const lum = 0.2126 * (d[i] ?? 0) + 0.7152 * (d[i + 1] ?? 0) + 0.0722 * (d[i + 2] ?? 0);
      if (lum > thresh) row.push(x);
    }
    if (row.length < 8) continue;
    let start = row[0]!;
    for (let k = 1; k <= row.length; k++) {
      const prev = row[k - 1]!;
      const cur = row[k];
      if (cur === undefined || cur !== prev + 1) {
        const end = prev;
        if (end - start > 6) sortInterval(d, c.w, y, start, end);
        if (cur !== undefined) start = cur;
      }
    }
  }
  c.work.putImageData(img, 0, 0);
}

function sortInterval(d: Uint8ClampedArray, w: number, y: number, x0: number, x1: number) {
  const px: [number, number, number, number][] = [];
  for (let x = x0; x <= x1; x++) {
    const i = (y * w + x) * 4;
    px.push([d[i] ?? 0, d[i + 1] ?? 0, d[i + 2] ?? 0, d[i + 3] ?? 255]);
  }
  px.sort((a, b) => a[0] + a[1] + a[2] - (b[0] + b[1] + b[2]));
  for (let x = x0; x <= x1; x++) {
    const p = px[x - x0]!;
    const i = (y * w + x) * 4;
    d[i] = p[0];
    d[i + 1] = p[1];
    d[i + 2] = p[2];
    d[i + 3] = p[3];
  }
}

function blockCorrupt(c: EffectCtx) {
  copySrc(c);
  const n = 8 + Math.floor(c.feat.rms * 18);
  const bw = 16 + Math.floor(c.feat.bass * 48);
  const bh = 10 + Math.floor(c.feat.treble * 36);
  for (let i = 0; i < n; i++) {
    const sx = Math.floor(Math.random() * c.w);
    const sy = Math.floor(Math.random() * c.h);
    const dx = Math.floor(Math.random() * c.w);
    const dy = Math.floor(Math.random() * c.h);
    try {
      c.work.drawImage(c.work.canvas, sx, sy, bw, bh, dx, dy, bw, bh);
    } catch {
      /* ignore */
    }
  }
  if (c.feat.peak) {
    c.work.save();
    c.work.globalCompositeOperation = "difference";
    c.work.fillStyle = rgbCss(c.hsv.h, 0.8, 0.6, 0.35);
    c.work.fillRect(0, Math.random() * c.h, c.w, 8 + c.feat.rms * 24);
    c.work.restore();
  }
}

let juliaCache: ImageData | null = null;
let juliaKey = "";

function fractal(c: EffectCtx) {
  copySrc(c);
  const fw = 140;
  const fh = 140;
  const cx = -0.4 + c.feat.bass * 0.5;
  const cy = 0.6 - c.feat.mid * 0.7;
  const key = `${cx.toFixed(2)}:${cy.toFixed(2)}:${c.hsv.h.toFixed(0)}`;
  if (!juliaCache || juliaKey !== key) {
    juliaCache = renderJulia(fw, fh, cx, cy, c.hsv.h);
    juliaKey = key;
  }
  c.scratch.putImageData(juliaCache, 0, 0);
  c.work.save();
  c.work.globalCompositeOperation = "screen";
  c.work.globalAlpha = 0.35 + c.feat.rms * 0.4;
  c.work.drawImage(c.scratch.canvas, 0, 0, fw, fh, 0, 0, c.w, c.h);
  c.work.globalCompositeOperation = "overlay";
  c.work.globalAlpha = 0.45;
  c.work.drawImage(c.scratch.canvas, 0, 0, fw, fh, 0, 0, c.w, c.h);
  c.work.restore();
}

function renderJulia(w: number, h: number, cx: number, cy: number, hue: number): ImageData {
  const img = new ImageData(w, h);
  const d = img.data;
  const max = 22;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let zr = (x / w) * 3.0 - 1.5;
      let zi = (y / h) * 3.0 - 1.5;
      let i = 0;
      while (zr * zr + zi * zi < 4 && i < max) {
        const tmp = zr * zr - zi * zi + cx;
        zi = 2 * zr * zi + cy;
        zr = tmp;
        i++;
      }
      const v = i / max;
      const [r, g, b] = hsvToRgb(hue + v * 80, 0.55, v);
      const p = (y * w + x) * 4;
      d[p] = r;
      d[p + 1] = g;
      d[p + 2] = b;
      d[p + 3] = Math.floor(v * 255);
    }
  }
  return img;
}

function hsvGeometry(c: EffectCtx) {
  copySrc(c);
  c.work.save();
  c.work.globalCompositeOperation = "overlay";
  const cols = 7;
  const rows = 9;
  const gw = c.w / cols;
  const gh = c.h / rows;
  const pulse = 0.35 + c.hsv.v * 0.7;
  const sides = 3 + Math.floor((c.t * 0.4 + c.feat.bass * 3) % 6);
  const rot = c.t * 0.35;
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const ox = row % 2 === 0 ? 0 : gw / 2;
      const x = col * gw + ox;
      const y = row * gh * 0.75 + gh * 0.2;
      const hue = (c.hsv.h + col * 18 + row * 8) % 360;
      c.work.beginPath();
      ngonPath(c.work, x, y, gw * 0.42 * pulse, sides, rot);
      c.work.fillStyle = rgbCss(hue, c.hsv.s, c.hsv.v, 0.55);
      c.work.fill();
      c.work.strokeStyle = rgbCss(hue, 0.3, 1, 0.35);
      c.work.lineWidth = 1 + c.feat.rms * 2;
      c.work.stroke();
    }
  }
  c.work.restore();
  drawWaveGeometry(c);
}

function ngonPath(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, n: number, rot: number) {
  const count = Math.max(3, n);
  ctx.moveTo(x + r * Math.cos(rot), y + r * Math.sin(rot));
  for (let i = 1; i < count; i++) {
    const a = rot + (i * Math.PI * 2) / count;
    ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a));
  }
  ctx.closePath();
}

function drawWaveGeometry(c: EffectCtx) {
  c.work.save();
  c.work.globalCompositeOperation = "screen";
  c.work.strokeStyle = rgbCss(c.hsv.h, c.hsv.s, 1, 0.55);
  c.work.lineWidth = 1.5 + c.feat.rms * 3;
  c.work.beginPath();
  const amp = c.h * 0.08 * c.hsv.v;
  for (let x = 0; x <= c.w; x += 4) {
    const y = c.h * 0.5 + Math.sin(x * 0.02 + c.t * 4) * amp + Math.sin(x * 0.05 + c.t * 7) * amp * 0.4;
    if (x === 0) c.work.moveTo(x, y);
    else c.work.lineTo(x, y);
  }
  c.work.stroke();
  c.work.restore();
}

const BLENDS: GlobalCompositeOperation[] = [
  "overlay",
  "difference",
  "screen",
  "multiply",
  "color-dodge",
  "soft-light",
];

function blend(c: EffectCtx) {
  copySrc(c);
  const mode = BLENDS[Math.floor(c.t * 0.35 + c.feat.rms * 3) % BLENDS.length]!;
  c.work.save();
  c.work.globalCompositeOperation = mode;
  c.work.filter = `hue-rotate(${c.hsv.h}deg) saturate(${1.2 + c.hsv.s})`;
  c.work.globalAlpha = 0.55 + c.feat.mid * 0.35;
  c.work.translate(c.w / 2, c.h / 2);
  c.work.rotate(c.feat.bass * 0.15);
  c.work.scale(1.08, 1.08);
  c.work.drawImage(c.src as CanvasImageSource, -c.w / 2, -c.h / 2, c.w, c.h);
  c.work.filter = "none";
  c.work.restore();
  c.work.save();
  c.work.globalCompositeOperation = "color";
  c.work.fillStyle = rgbCss(c.hsv.h, c.hsv.s, c.hsv.v, 0.28);
  c.work.fillRect(0, 0, c.w, c.h);
  c.work.restore();
}

function lensPeel(c: EffectCtx) {
  const p = c.peel;
  c.work.fillStyle = "#f3efe6";
  c.work.fillRect(0, 0, c.w, c.h);
  c.work.save();
  coverDraw(c.work, c.nextPlate, c.w, c.h, 1.02);
  c.work.restore();

  c.work.save();
  const yRip = c.h * (1 - p);
  c.work.beginPath();
  c.work.moveTo(0, 0);
  c.work.lineTo(c.w, 0);
  c.work.lineTo(c.w, yRip);
  for (let x = c.w; x >= 0; x -= 10) {
    const jag = Math.sin(x * 0.18 + c.t * 9) * 16 * Math.min(1, p * 3);
    c.work.lineTo(x, yRip + jag);
  }
  c.work.closePath();
  c.work.clip();
  c.work.translate(0, -p * c.h * 0.18);
  c.work.scale(1 + p * 0.12, 1 + p * 0.12);
  c.work.filter = `brightness(${1 + p * 0.8})`;
  coverDraw(c.work, c.src, c.w, c.h);
  c.work.filter = "none";
  c.work.restore();

  const flash = Math.sin(p * Math.PI);
  if (flash > 0.05) {
    c.work.fillStyle = `rgba(243,239,230,${flash * 0.55})`;
    c.work.fillRect(0, 0, c.w, c.h);
  }
}

function feedback(c: EffectCtx) {
  c.work.save();
  c.work.translate(c.w / 2, c.h / 2);
  c.work.rotate(0.008 + c.feat.bass * 0.02);
  c.work.scale(1.03 + c.feat.rms * 0.02, 1.03 + c.feat.rms * 0.02);
  c.work.globalAlpha = 0.86;
  c.work.drawImage(c.feedback, -c.w / 2, -c.h / 2, c.w, c.h);
  c.work.restore();
  c.work.save();
  c.work.globalAlpha = 0.55 + c.feat.rms * 0.3;
  c.work.globalCompositeOperation = "lighter";
  coverDraw(c.work, c.src, c.w, c.h, 1);
  c.work.restore();
  c.work.save();
  c.work.globalCompositeOperation = "overlay";
  c.work.fillStyle = rgbCss(c.hsv.h, c.hsv.s, c.hsv.v, 0.22);
  c.work.fillRect(0, 0, c.w, c.h);
  c.work.restore();
}

function remapPolar(
  c: EffectCtx,
  map: (x: number, y: number, cx: number, cy: number, rmax: number) => [number, number],
) {
  c.scratch.clearRect(0, 0, c.w, c.h);
  coverDraw(c.scratch, c.src, c.w, c.h, 1);
  const src = c.scratch.getImageData(0, 0, c.w, c.h);
  const dst = c.work.createImageData(c.w, c.h);
  const s = src.data;
  const d = dst.data;
  const cx = c.w / 2;
  const cy = c.h / 2;
  const rmax = Math.hypot(cx, cy);
  for (let y = 0; y < c.h; y++) {
    for (let x = 0; x < c.w; x++) {
      let [sx, sy] = map(x, y, cx, cy, rmax);
      sx = ((sx % c.w) + c.w) % c.w;
      sy = ((sy % c.h) + c.h) % c.h;
      const di = (y * c.w + x) * 4;
      const si = (Math.floor(sy) * c.w + Math.floor(sx)) * 4;
      d[di] = s[si] ?? 0;
      d[di + 1] = s[si + 1] ?? 0;
      d[di + 2] = s[si + 2] ?? 0;
      d[di + 3] = 255;
    }
  }
  c.work.putImageData(dst, 0, 0);
}

function vortex(c: EffectCtx) {
  const twist = 1.8 + c.feat.rms * 3.4;
  remapPolar(c, (x, y, cx, cy, rmax) => {
    const dx = x - cx;
    const dy = y - cy;
    const r = Math.hypot(dx, dy);
    const fall = (1 - Math.min(1, r / rmax)) ** 2;
    const a = Math.atan2(dy, dx) + twist * fall + c.t * 0.25;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
}

function sliceScramble(c: EffectCtx) {
  copySrc(c);
  c.scratch.drawImage(c.work.canvas, 0, 0);
  const strip = Math.max(6, Math.floor(8 + c.feat.bass * 28));
  const seed = Math.floor(c.t * 2.4);
  for (let x = 0; x < c.w; x += strip) {
    const srcX = ((x * 13 + seed * 47) % Math.max(1, c.w - strip) + c.w) % Math.max(1, c.w - strip);
    const yoff = Math.sin(x * 0.03 + c.t * 5) * c.h * (0.04 + c.feat.rms * 0.08);
    c.work.drawImage(c.scratch.canvas, srcX, 0, strip, c.h, x, yoff, strip, c.h);
  }
}

function vhs(c: EffectCtx) {
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  const src = new Uint8ClampedArray(img.data);
  const tearY = Math.floor(((c.t * 90) % 1) * c.h);
  const tearH = 6 + Math.floor(c.feat.treble * 22);
  const ox = Math.floor(10 + c.feat.bass * 24);
  for (let y = 0; y < c.h; y++) {
    const tracking = y > tearY && y < tearY + tearH;
    const shift = tracking ? ox * 3 : Math.round(Math.sin(y * 0.3 + c.t * 8) * (2 + c.feat.rms * 6));
    for (let x = 0; x < c.w; x++) {
      const sx = (x + shift + c.w) % c.w;
      const di = (y * c.w + x) * 4;
      const si = (y * c.w + sx) * 4;
      img.data[di] = src[(y * c.w + ((sx + ox) % c.w)) * 4] ?? 0;
      img.data[di + 1] = src[si + 1] ?? 0;
      img.data[di + 2] = src[(y * c.w + ((sx - ox + c.w) % c.w)) * 4 + 2] ?? 0;
    }
  }
  c.work.putImageData(img, 0, 0);
  c.work.save();
  c.work.globalAlpha = 0.18;
  c.work.fillStyle = "rgba(0,0,0,0.5)";
  for (let y = 0; y < c.h; y += 3) c.work.fillRect(0, y, c.w, 1);
  c.work.restore();
}

function waveWarp(c: EffectCtx) {
  const ax = 10 + c.feat.rms * 36;
  const ay = 8 + c.feat.mid * 28;
  remapPolar(c, (x, y) => [
    x + Math.sin(y * 0.045 + c.t * 6) * ax,
    y + Math.cos(x * 0.035 + c.t * 4.2) * ay,
  ]);
}

function neonEdge(c: EffectCtx) {
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  const d = img.data;
  const w = c.w;
  const out = c.work.createImageData(c.w, c.h);
  const o = out.data;
  const [cr, cg, cb] = hsvToRgb(c.hsv.h, 0.85, 1);
  for (let y = 1; y < c.h - 1; y++) {
    for (let x = 1; x < c.w - 1; x++) {
      const i = (y * w + x) * 4;
      const lum = (xx: number, yy: number) => {
        const p = (yy * w + xx) * 4;
        return 0.2126 * (d[p] ?? 0) + 0.7152 * (d[p + 1] ?? 0) + 0.0722 * (d[p + 2] ?? 0);
      };
      const gx = -lum(x - 1, y - 1) + lum(x + 1, y - 1) - 2 * lum(x - 1, y) + 2 * lum(x + 1, y) - lum(x - 1, y + 1) + lum(x + 1, y + 1);
      const gy = -lum(x - 1, y - 1) - 2 * lum(x, y - 1) - lum(x + 1, y - 1) + lum(x - 1, y + 1) + 2 * lum(x, y + 1) + lum(x + 1, y + 1);
      const mag = Math.min(255, Math.hypot(gx, gy) * (0.8 + c.feat.rms));
      o[i] = Math.min(255, (d[i] ?? 0) + (cr * mag) / 255);
      o[i + 1] = Math.min(255, (d[i + 1] ?? 0) + (cg * mag) / 255);
      o[i + 2] = Math.min(255, (d[i + 2] ?? 0) + (cb * mag) / 255);
      o[i + 3] = 255;
    }
  }
  c.work.putImageData(out, 0, 0);
}

function fisheye(c: EffectCtx) {
  const k = 0.55 + c.feat.bass * 0.85;
  remapPolar(c, (x, y, cx, cy, rmax) => {
    const dx = x - cx;
    const dy = y - cy;
    const r = Math.hypot(dx, dy) / rmax;
    const r2 = r === 0 ? 0 : rmax * (r + k * r * r * r);
    const a = Math.atan2(dy, dx);
    return [cx + Math.cos(a) * r2, cy + Math.sin(a) * r2];
  });
}

function zoomStreak(c: EffectCtx) {
  copySrc(c);
  c.scratch.drawImage(c.work.canvas, 0, 0);
  c.work.save();
  c.work.globalCompositeOperation = "lighter";
  const n = 9;
  for (let i = 1; i <= n; i++) {
    const s = 1 + i * (0.035 + c.feat.rms * 0.04);
    c.work.globalAlpha = 0.08 + c.feat.treble * 0.04;
    c.work.drawImage(c.scratch.canvas, (c.w - c.w * s) / 2, (c.h - c.h * s) / 2, c.w * s, c.h * s);
  }
  c.work.restore();
}

function mosaic(c: EffectCtx) {
  const cell = Math.max(6, Math.floor(8 + c.feat.rms * 36));
  const nw = Math.max(4, Math.floor(c.w / cell));
  const nh = Math.max(4, Math.floor(c.h / cell));
  c.scratch.clearRect(0, 0, c.w, c.h);
  coverDraw(c.scratch, c.src, nw, nh, 1);
  c.work.imageSmoothingEnabled = false;
  c.work.drawImage(c.scratch.canvas, 0, 0, nw, nh, 0, 0, c.w, c.h);
  c.work.imageSmoothingEnabled = true;
}

function dimPlate(c: EffectCtx, amount = 0.32) {
  copySrc(c);
  c.work.save();
  c.work.fillStyle = `rgba(8,7,6,${amount})`;
  c.work.fillRect(0, 0, c.w, c.h);
  c.work.restore();
}

function strokeHalo(
  c: EffectCtx,
  draw: () => void,
) {
  c.work.save();
  c.work.globalCompositeOperation = "source-over";
  c.work.lineJoin = "round";
  c.work.lineCap = "round";
  c.work.strokeStyle = "rgba(10,9,8,0.72)";
  c.work.lineWidth = 4.5 + c.feat.rms * 2;
  draw();
  c.work.strokeStyle = rgbCss(c.hsv.h, Math.min(1, c.hsv.s + 0.2), 1, 0.95);
  c.work.lineWidth = 1.6 + c.feat.rms;
  draw();
  c.work.restore();
}

function solids(c: EffectCtx) {
  dimPlate(c, 0.28);
  const kind = SOLID_CYCLE[Math.floor(c.t * 0.38 + c.feat.bass * 2) % SOLID_CYCLE.length] as SolidKind;
  const cx = c.w / 2;
  const cy = c.h / 2;
  const R = Math.min(c.w, c.h) * (0.28 + c.hsv.v * 0.12);
  strokeHalo(c, () => {
    strokeSolid(c.work, kind, cx, cy, R, c.t * 0.7, c.t * 0.45, c.feat.bass);
    const orbit = Math.min(c.w, c.h) * 0.34;
    for (let i = 0; i < 3; i++) {
      const a = c.t * 0.55 + (i * Math.PI * 2) / 3;
      const k = SOLID_CYCLE[(SOLID_CYCLE.indexOf(kind) + i + 1) % SOLID_CYCLE.length]!;
      strokeSolid(
        c.work,
        k,
        cx + Math.cos(a) * orbit,
        cy + Math.sin(a) * orbit * 0.72,
        R * 0.28,
        c.t * 1.1 + i,
        c.t * 0.8,
        i,
      );
    }
  });
}

function flower(c: EffectCtx) {
  dimPlate(c, 0.28);
  const cx = c.w / 2;
  const cy = c.h / 2;
  const R = Math.min(c.w, c.h) * (0.11 + c.hsv.v * 0.04);
  const pts = flowerCenters(cx, cy, R);
  strokeHalo(c, () => {
    c.work.save();
    c.work.translate(cx, cy);
    c.work.rotate(c.t * 0.08);
    c.work.translate(-cx, -cy);
    for (const [x, y] of pts) {
      c.work.beginPath();
      c.work.arc(x, y, R, 0, Math.PI * 2);
      c.work.stroke();
    }
    c.work.restore();
  });
}

function metatron(c: EffectCtx) {
  dimPlate(c, 0.3);
  const cx = c.w / 2;
  const cy = c.h / 2;
  const R = Math.min(c.w, c.h) * (0.12 + c.feat.rms * 0.03);
  const pts = fruitCenters(cx, cy, R);
  strokeHalo(c, () => {
    c.work.save();
    c.work.translate(cx, cy);
    c.work.rotate(c.t * 0.12);
    c.work.translate(-cx, -cy);
    c.work.beginPath();
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i]!;
        const b = pts[j]!;
        c.work.moveTo(a[0], a[1]);
        c.work.lineTo(b[0], b[1]);
      }
    }
    c.work.stroke();
    for (const [x, y] of pts) {
      c.work.beginPath();
      c.work.arc(x, y, R * 0.18, 0, Math.PI * 2);
      c.work.stroke();
    }
    c.work.restore();
  });
}

function merkaba(c: EffectCtx) {
  dimPlate(c, 0.28);
  const cx = c.w / 2;
  const cy = c.h / 2;
  const R = Math.min(c.w, c.h) * (0.34 + c.hsv.v * 0.1);
  strokeHalo(c, () => {
    strokeSolid(c.work, "merkaba", cx, cy, R, c.t * 0.55, c.t * 0.8, c.t * 0.2);
    strokeSolid(c.work, "cube", cx, cy, R * 0.42, c.t * 0.3, -c.t * 0.4, 0);
  });
}

function rgbPrism(c: EffectCtx) {
  copySrc(c);
  const img = c.work.getImageData(0, 0, c.w, c.h);
  const red = c.work.createImageData(c.w, c.h);
  const green = c.work.createImageData(c.w, c.h);
  const cyan = c.work.createImageData(c.w, c.h);
  const s = img.data;
  for (let i = 0; i < s.length; i += 4) {
    const r = s[i] ?? 0;
    const g = s[i + 1] ?? 0;
    const b = s[i + 2] ?? 0;
    const lum = 0.299 * r + 0.587 * g + 0.114 * b;
    red.data[i] = Math.min(255, r * 0.35 + lum * 0.75);
    red.data[i + 3] = 255;
    green.data[i + 1] = Math.min(255, g * 0.35 + lum * 0.75);
    green.data[i + 3] = 255;
    cyan.data[i + 1] = Math.min(255, g * 0.25 + lum * 0.55);
    cyan.data[i + 2] = Math.min(255, b * 0.45 + lum * 0.7);
    cyan.data[i + 3] = 255;
  }
  const oxR = 10 + Math.sin(c.t * 1.73) * 9 + c.feat.bass * 24;
  const oyR = Math.sin(c.t * 1.11) * 4;
  const oxC = -(10 + Math.sin(c.t * 1.31 + 1.1) * 9 + c.feat.treble * 24);
  const oyC = Math.cos(c.t * 0.97) * 4;
  const oxG = Math.sin(c.t * 0.83) * (3 + c.feat.mid * 8);
  const oyG = Math.sin(c.t * 2.07) * (5 + c.feat.mid * 12);
  c.work.fillStyle = "#000";
  c.work.fillRect(0, 0, c.w, c.h);
  c.work.globalCompositeOperation = "lighter";
  c.scratch.putImageData(cyan, 0, 0);
  c.work.drawImage(c.scratch.canvas, oxC, oyC);
  c.scratch.putImageData(green, 0, 0);
  c.work.drawImage(c.scratch.canvas, oxG, oyG);
  c.scratch.putImageData(red, 0, 0);
  c.work.drawImage(c.scratch.canvas, oxR, oyR);
  c.work.globalCompositeOperation = "source-over";
}

const GEOM_LOOKS = new Set<EffectId>(["solids", "flower", "metatron", "merkaba"]);

export function overlaySolids(c: EffectCtx) {
  const kind = SOLID_CYCLE[Math.floor(c.t * 0.38 + c.feat.bass * 2) % SOLID_CYCLE.length] as SolidKind;
  const cx = c.w / 2;
  const cy = c.h / 2;
  const R = Math.min(c.w, c.h) * (0.2 + c.hsv.v * 0.08);
  strokeHalo(c, () => {
    strokeSolid(c.work, kind, cx, cy, R, c.t * 0.7, c.t * 0.45, c.feat.bass);
  });
}

export function overlayGlyphs(c: EffectCtx, solidsOn: boolean) {
  const cx = c.w / 2;
  const cy = c.h / 2;
  const ring = Math.min(c.w, c.h) * (solidsOn ? 0.42 : 0.33);
  const size = Math.min(c.w, c.h) * (0.06 + c.feat.rms * 0.03);
  const start = Math.floor(c.t * 0.72 + c.feat.bass * 8) % GLYPHS.length;
  const n = 8;
  strokeHalo(c, () => {
    for (let i = 0; i < n; i++) {
      const glyph = GLYPHS[(start + i * 11) % GLYPHS.length]!;
      const a = c.t * 0.18 + (i * Math.PI * 2) / n;
      drawGlyph(
        c.work,
        glyph,
        cx + Math.cos(a) * ring,
        cy + Math.sin(a) * ring * 0.78,
        size,
        a + c.t * 0.4 + i,
      );
    }
    if (!solidsOn) {
      const glyph = GLYPHS[(start + 17) % GLYPHS.length]!;
      drawGlyph(c.work, glyph, cx, cy - ring * 0.08, size * 1.45, c.t * 0.22);
      for (let j = 0; j < 2; j++) {
        const g2 = GLYPHS[(start + 23 + j * 13) % GLYPHS.length]!;
        const a = c.t * 0.55 + j * Math.PI;
        const rr = ring * 0.16;
        drawGlyph(c.work, g2, cx + Math.cos(a) * rr, cy + Math.sin(a) * rr, size * 0.72, a);
      }
    }
  });
}

export function shouldSkipSolidsOverlay(id: EffectId) {
  return GEOM_LOOKS.has(id);
}

export const EFFECTS: Record<EffectId, (c: EffectCtx) => void> = {
  kaleidoscope,
  chromatic,
  scanline,
  pixel_sort: pixelSort,
  block_corrupt: blockCorrupt,
  fractal,
  hsv_geometry: hsvGeometry,
  blend,
  lens_peel: lensPeel,
  feedback,
  vortex,
  slice_scramble: sliceScramble,
  vhs,
  wave_warp: waveWarp,
  neon_edge: neonEdge,
  fisheye,
  zoom_streak: zoomStreak,
  mosaic,
  solids,
  flower,
  metatron,
  merkaba,
  rgb_prism: rgbPrism,
};

export function filmGrain(c: EffectCtx) {
  const img = c.work.getImageData(0, 0, Math.min(c.w, 320), Math.min(c.h, 180));
  const d = img.data;
  for (let i = 0; i < d.length; i += 16) {
    const n = (Math.random() - 0.5) * 28;
    d[i] = Math.max(0, Math.min(255, (d[i] ?? 0) + n));
    d[i + 1] = Math.max(0, Math.min(255, (d[i + 1] ?? 0) + n));
    d[i + 2] = Math.max(0, Math.min(255, (d[i + 2] ?? 0) + n));
  }
  c.scratch.putImageData(img, 0, 0);
  c.work.save();
  c.work.globalAlpha = 0.12;
  c.work.drawImage(c.scratch.canvas, 0, 0, img.width, img.height, 0, 0, c.w, c.h);
  c.work.restore();
}
