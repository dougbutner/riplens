export function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const hh = ((h % 360) + 360) % 360 / 60;
  const c = v * s;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  const m = v - c;
  let r = 0, g = 0, b = 0;
  if (hh < 1) [r, g, b] = [c, x, 0];
  else if (hh < 2) [r, g, b] = [x, c, 0];
  else if (hh < 3) [r, g, b] = [0, c, x];
  else if (hh < 4) [r, g, b] = [0, x, c];
  else if (hh < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return [
    Math.round((r + m) * 255),
    Math.round((g + m) * 255),
    Math.round((b + m) * 255),
  ];
}

export function rgbCss(h: number, s: number, v: number, a = 1): string {
  const [r, g, b] = hsvToRgb(h, s, v);
  return `rgba(${r},${g},${b},${a})`;
}

export function coverDraw(
  ctx: CanvasRenderingContext2D,
  img: CanvasImageSource,
  w: number,
  h: number,
  zoom = 1,
  ox = 0,
  oy = 0,
) {
  const iw = "width" in img ? Number(img.width) : w;
  const ih = "height" in img ? Number(img.height) : h;
  const scale = Math.max(w / iw, h / ih) * zoom;
  const dw = iw * scale;
  const dh = ih * scale;
  const x = (w - dw) / 2 + ox;
  const y = (h - dh) / 2 + oy;
  ctx.drawImage(img, x, y, dw, dh);
}
