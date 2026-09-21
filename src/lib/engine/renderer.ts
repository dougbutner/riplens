import { idleFeatures, type AudioEngine } from "./audio";
import { coverDraw, rgbCss } from "./color";
import { EFFECTS, filmGrain, overlayGlyphs, overlaySolids, shouldSkipSolidsOverlay, type EffectCtx } from "./effects";
import { makeProceduralPlates } from "./plates";
import { cueAt, drawSubtitles, type Cue } from "./subtitles";
import {
  DEFAULT_COOLDOWN,
  DEFAULT_THRESHOLD,
  EFFECT_ORDER,
  RATIOS,
  featuresToHsv,
  type AudioFeatures,
  type EffectId,
  type RatioId,
} from "./types";

export interface EngineSnapshot {
  rms: number;
  bass: number;
  mid: number;
  treble: number;
  hue: number;
  sat: number;
  val: number;
  effectIndex: number;
  effectId: EffectId;
  effectName: string;
  plateIndex: number;
  plateCount: number;
  threshold: number;
  playing: boolean;
  recording: boolean;
  ratio: RatioId;
  time: number;
  solidsLayer: boolean;
  glyphsLayer: boolean;
  subsLayer: boolean;
  cueText: string;
}

type Listener = (s: EngineSnapshot) => void;

const WORK: Record<RatioId, { w: number; h: number }> = {
  "1x1": { w: 640, h: 640 },
  "16x9": { w: 960, h: 540 },
  "9x16": { w: 540, h: 960 },
};

export class RipLensRenderer {
  readonly view: HTMLCanvasElement;
  readonly audio: AudioEngine;
  private work: HTMLCanvasElement;
  private scratch: HTMLCanvasElement;
  private feedback: HTMLCanvasElement;
  private wctx: CanvasRenderingContext2D;
  private sctx: CanvasRenderingContext2D;
  private vctx: CanvasRenderingContext2D;
  private plates: CanvasImageSource[] = [];
  private plateIndex = 0;
  private effectIndex = 0;
  private lastSwitch = -99;
  private peel = 0;
  private peeling = false;
  private peelFrom = 0;
  private peelTo = 1;
  private ratio: RatioId = "1x1";
  private threshold = DEFAULT_THRESHOLD;
  private cooldown = DEFAULT_COOLDOWN;
  private lockEffect: EffectId | null = null;
  private solidsLayer = false;
  private glyphsLayer = true;
  private subsLayer = true;
  private cues: Cue[] = [];
  private captionFamily = "RipLensCaption";
  private raf = 0;
  private t0 = performance.now();
  private listeners = new Set<Listener>();
  private recording = false;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private lastFeat: AudioFeatures = idleFeatures(0);
  destroyed = false;

  constructor(view: HTMLCanvasElement, audio: AudioEngine) {
    this.view = view;
    this.audio = audio;
    this.work = document.createElement("canvas");
    this.scratch = document.createElement("canvas");
    this.feedback = document.createElement("canvas");
    this.wctx = this.work.getContext("2d", { willReadFrequently: true })!;
    this.sctx = this.scratch.getContext("2d", { willReadFrequently: true })!;
    this.vctx = view.getContext("2d")!;
    this.plates = makeProceduralPlates(768);
    this.applyRatio("1x1");
  }

  onFrame(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  setRatio(id: RatioId) {
    this.ratio = id;
    this.applyRatio(id);
  }

  setThreshold(v: number) {
    this.threshold = Math.min(0.95, Math.max(0.2, v));
  }

  setLock(id: EffectId | null) {
    this.lockEffect = id;
    if (id) {
      const idx = EFFECT_ORDER.findIndex((e) => e.id === id);
      if (idx >= 0) this.effectIndex = idx;
    }
  }

  setSolidsLayer(on: boolean) {
    this.solidsLayer = on;
  }

  setGlyphsLayer(on: boolean) {
    this.glyphsLayer = on;
  }

  setSubsLayer(on: boolean) {
    this.subsLayer = on;
  }

  setCues(cues: Cue[]) {
    this.cues = cues;
  }

  setCaptionFamily(name: string) {
    this.captionFamily = name;
  }

  addPlates(images: CanvasImageSource[]) {
    if (images.length === 0) return;
    this.plates = images;
    this.plateIndex = 0;
  }

  get plateCount() {
    return this.plates.length;
  }

  start() {
    cancelAnimationFrame(this.raf);
    const loop = (now: number) => {
      if (this.destroyed) return;
      this.tick((now - this.t0) / 1000);
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }

  destroy() {
    this.destroyed = true;
    this.stop();
    this.audio?.destroy();
  }

  async startRecording(): Promise<void> {
    if (this.recording) return;
    const stream = this.view.captureStream(30);
    const dest = this.audio?.ctx.createMediaStreamDestination();
    if (dest && this.audio) {
      this.audio.master.connect(dest);
      dest.stream.getAudioTracks().forEach((t) => stream.addTrack(t));
    }
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : "video/webm";
    this.chunks = [];
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
    rec.ondataavailable = (e) => {
      if (e.data.size) this.chunks.push(e.data);
    };
    rec.start(400);
    this.recorder = rec;
    this.recording = true;
  }

  stopRecording(): Promise<Blob | null> {
    return new Promise((resolve) => {
      const rec = this.recorder;
      if (!rec || rec.state === "inactive") {
        this.recording = false;
        resolve(null);
        return;
      }
      rec.onstop = () => {
        this.recording = false;
        resolve(new Blob(this.chunks, { type: rec.mimeType }));
      };
      rec.stop();
    });
  }

  private applyRatio(id: RatioId) {
    const spec = WORK[id];
    const display = RATIOS.find((r) => r.id === id)!;
    this.work.width = spec.w;
    this.work.height = spec.h;
    this.scratch.width = spec.w;
    this.scratch.height = spec.h;
    this.feedback.width = spec.w;
    this.feedback.height = spec.h;
    this.view.width = spec.w;
    this.view.height = spec.h;
    this.view.style.aspectRatio = `${display.w} / ${display.h}`;
  }

  private tick(t: number) {
    const playing = this.audio?.playing ?? false;
    const feat = playing ? this.audio!.features() : idleFeatures(t);
    this.lastFeat = feat;
    const hsv = featuresToHsv(feat);

    if (!this.lockEffect && feat.rms >= this.threshold && t - this.lastSwitch > this.cooldown) {
      this.effectIndex = (this.effectIndex + 1) % EFFECT_ORDER.length;
      this.lastSwitch = t;
      if (EFFECT_ORDER[this.effectIndex]?.id === "lens_peel") {
        this.beginPeel();
      }
    }

    if (this.peeling) {
      this.peel = Math.min(1, this.peel + 0.018 + feat.rms * 0.01);
      if (this.peel >= 1) {
        this.peeling = false;
        this.plateIndex = this.peelTo;
        this.peel = 0;
      }
    }

    const id = this.lockEffect ?? EFFECT_ORDER[this.effectIndex]!.id;
    const src = this.plates[this.plateIndex] ?? this.plates[0]!;
    const next = this.plates[this.peelTo] ?? src;
    const w = this.work.width;
    const h = this.work.height;

    this.wctx.fillStyle = "#0c0b0a";
    this.wctx.fillRect(0, 0, w, h);

    const ctx: EffectCtx = {
      w,
      h,
      t,
      feat,
      hsv,
      src,
      work: this.wctx,
      scratch: this.sctx,
      feedback: this.feedback,
      plateIndex: this.plateIndex,
      plateCount: this.plates.length,
      nextPlate: next,
      peel: id === "lens_peel" ? (this.peeling ? this.peel : 0.45 + 0.25 * Math.sin(t * 1.4)) : this.peel,
    };

    EFFECTS[id](ctx);
    if (this.solidsLayer && !shouldSkipSolidsOverlay(id)) overlaySolids(ctx);
    if (this.glyphsLayer) overlayGlyphs(ctx, this.solidsLayer);
    filmGrain(ctx);
    const songT = this.audio?.currentTime() ?? 0;
    const cue = this.subsLayer ? cueAt(this.cues, songT) : null;
    if (cue) drawSubtitles(this.wctx, cue.text, w, h, this.captionFamily);

    this.sctx.drawImage(this.work, 0, 0);
    this.feedback.getContext("2d")!.drawImage(this.work, 0, 0);

    this.vctx.fillStyle = "#0c0b0a";
    this.vctx.fillRect(0, 0, this.view.width, this.view.height);
    this.vctx.drawImage(this.work, 0, 0);

    if (this.recording) {
      this.vctx.save();
      this.vctx.fillStyle = rgbCss(12, 0.7, 0.85, 1);
      this.vctx.beginPath();
      this.vctx.arc(18, 18, 6, 0, Math.PI * 2);
      this.vctx.fill();
      this.vctx.restore();
    }

    const snap: EngineSnapshot = {
      rms: feat.rms,
      bass: feat.bass,
      mid: feat.mid,
      treble: feat.treble,
      hue: hsv.h,
      sat: hsv.s,
      val: hsv.v,
      effectIndex: this.effectIndex,
      effectId: id,
      effectName: EFFECT_ORDER.find((e) => e.id === id)?.name ?? id,
      plateIndex: this.plateIndex,
      plateCount: this.plates.length,
      threshold: this.threshold,
      playing,
      recording: this.recording,
      ratio: this.ratio,
      time: t,
      solidsLayer: this.solidsLayer,
      glyphsLayer: this.glyphsLayer,
      subsLayer: this.subsLayer,
      cueText: cue?.text ?? "",
    };
    this.listeners.forEach((fn) => fn(snap));
  }

  private beginPeel() {
    this.peeling = true;
    this.peel = 0;
    this.peelFrom = this.plateIndex;
    this.peelTo = (this.plateIndex + 1) % Math.max(1, this.plates.length);
  }

  snapshot(): EngineSnapshot {
    const hsv = featuresToHsv(this.lastFeat);
    const id = this.lockEffect ?? EFFECT_ORDER[this.effectIndex]!.id;
    return {
      rms: this.lastFeat.rms,
      bass: this.lastFeat.bass,
      mid: this.lastFeat.mid,
      treble: this.lastFeat.treble,
      hue: hsv.h,
      sat: hsv.s,
      val: hsv.v,
      effectIndex: this.effectIndex,
      effectId: id,
      effectName: EFFECT_ORDER.find((e) => e.id === id)?.name ?? id,
      plateIndex: this.plateIndex,
      plateCount: this.plates.length,
      threshold: this.threshold,
      playing: this.audio?.playing ?? false,
      recording: this.recording,
      ratio: this.ratio,
      time: 0,
      solidsLayer: this.solidsLayer,
      glyphsLayer: this.glyphsLayer,
      subsLayer: this.subsLayer,
      cueText: cueAt(this.cues, this.audio?.currentTime() ?? 0)?.text ?? "",
    };
  }
}

export { coverDraw };
