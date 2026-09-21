function grain(ctx: CanvasRenderingContext2D, w: number, h: number, amount: number) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (Math.random() - 0.5) * amount;
    d[i] = Math.max(0, Math.min(255, (d[i] ?? 0) + n));
    d[i + 1] = Math.max(0, Math.min(255, (d[i + 1] ?? 0) + n));
    d[i + 2] = Math.max(0, Math.min(255, (d[i + 2] ?? 0) + n));
  }
  ctx.putImageData(img, 0, 0);
}

function makeCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

/** Four darkroom plates so the studio is never empty. */
export function makeProceduralPlates(size = 1024): HTMLCanvasElement[] {
  const plates: HTMLCanvasElement[] = [];

  {
    const c = makeCanvas(size, size);
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#14110e";
    ctx.fillRect(0, 0, size, size);
    const g = ctx.createRadialGradient(size * 0.5, size * 0.48, 20, size * 0.5, size * 0.5, size * 0.62);
    g.addColorStop(0, "#d7cbb8");
    g.addColorStop(0.35, "#8a6a4a");
    g.addColorStop(0.7, "#2a221c");
    g.addColorStop(1, "#0c0b0a");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    ctx.strokeStyle = "rgba(235,230,220,0.18)";
    ctx.lineWidth = 2;
    for (let i = 1; i < 14; i++) {
      ctx.beginPath();
      ctx.arc(size * 0.5, size * 0.5, i * size * 0.035, 0, Math.PI * 2);
      ctx.stroke();
    }
    grain(ctx, size, size, 18);
    plates.push(c);
  }

  {
    const c = makeCanvas(size, size);
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#0e0d0c";
    ctx.fillRect(0, 0, size, size);
    for (let i = 0; i < 18; i++) {
      ctx.save();
      ctx.translate(size / 2, size / 2);
      ctx.rotate((i / 18) * Math.PI);
      ctx.fillStyle = i % 2 === 0 ? "#cfc6b6" : "#3a322a";
      ctx.fillRect(-size, -size * 0.04, size * 2, size * 0.08);
      ctx.restore();
    }
    ctx.globalCompositeOperation = "multiply";
    const vg = ctx.createRadialGradient(size / 2, size / 2, size * 0.2, size / 2, size / 2, size * 0.7);
    vg.addColorStop(0, "rgba(255,255,255,0)");
    vg.addColorStop(1, "rgba(8,7,6,0.85)");
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, size, size);
    ctx.globalCompositeOperation = "source-over";
    grain(ctx, size, size, 22);
    plates.push(c);
  }

  {
    const c = makeCanvas(size, size);
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#1a1612";
    ctx.fillRect(0, 0, size, size);
    const cols = 8;
    const rows = 8;
    const cw = size / cols;
    const ch = size / rows;
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const on = (x + y) % 2 === 0;
        ctx.fillStyle = on ? "#e6dcc8" : "#2b241c";
        ctx.beginPath();
        ctx.moveTo(x * cw, (y + 1) * ch);
        ctx.lineTo((x + 0.5) * cw, y * ch);
        ctx.lineTo((x + 1) * cw, (y + 1) * ch);
        ctx.closePath();
        ctx.fill();
      }
    }
    grain(ctx, size, size, 16);
    plates.push(c);
  }

  {
    const c = makeCanvas(size, size);
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#100e0c";
    ctx.fillRect(0, 0, size, size);
    const rects = [
      [0.08, 0.1, 0.5, 0.62],
      [0.42, 0.22, 0.5, 0.48],
      [0.18, 0.55, 0.64, 0.36],
      [0.62, 0.08, 0.28, 0.3],
    ];
    const fills = ["#d8cbb4", "#6d5844", "#b7a48a", "#3d342c"];
    rects.forEach((r, i) => {
      ctx.fillStyle = fills[i] ?? "#888";
      ctx.fillRect(r[0]! * size, r[1]! * size, r[2]! * size, r[3]! * size);
    });
    ctx.strokeStyle = "rgba(235,230,220,0.25)";
    ctx.lineWidth = 3;
    ctx.strokeRect(size * 0.06, size * 0.06, size * 0.88, size * 0.88);
    grain(ctx, size, size, 20);
    plates.push(c);
  }

  return plates;
}

export async function bitmapFromUrl(url: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("Could not read image"));
    img.src = url;
  });
  return img;
}

/** Extra plates from one artwork so lens peel and blend have material. */
export function plateVariants(img: CanvasImageSource, size = 1024): HTMLCanvasElement[] {
  const filters = [
    "none",
    "hue-rotate(32deg) saturate(1.15)",
    "hue-rotate(-48deg) saturate(1.1)",
    "hue-rotate(160deg) contrast(1.12)",
  ];
  return filters.map((filter) => {
    const c = makeCanvas(size, size);
    const ctx = c.getContext("2d")!;
    ctx.filter = filter;
    const iw = "width" in img ? Number(img.width) : size;
    const ih = "height" in img ? Number(img.height) : size;
    const scale = Math.max(size / iw, size / ih);
    const dw = iw * scale;
    const dh = ih * scale;
    ctx.drawImage(img, (size - dw) / 2, (size - dh) / 2, dw, dh);
    ctx.filter = "none";
    return c;
  });
}

export async function bitmapFromFile(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("Could not read image"));
    img.src = url;
  });
  return img;
}
