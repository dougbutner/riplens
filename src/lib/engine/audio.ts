import type { AudioFeatures } from "./types";

export interface AudioEngine {
  ctx: AudioContext;
  analyser: AnalyserNode;
  master: GainNode;
  playing: boolean;
  duration: number;
  currentTime: () => number;
  play: () => Promise<void>;
  pause: () => void;
  loadFile: (file: File) => Promise<void>;
  loadUrl: (url: string) => Promise<void>;
  loadDemo: () => Promise<void>;
  features: () => AudioFeatures;
  destroy: () => void;
}

function bandEnergy(mags: Uint8Array, from: number, to: number): number {
  let sum = 0;
  const end = Math.min(to, mags.length);
  const start = Math.min(from, end);
  if (end <= start) return 0;
  for (let i = start; i < end; i++) sum += mags[i] ?? 0;
  return sum / ((end - start) * 255);
}

function makeKickSnareLoop(ctx: AudioContext): AudioBuffer {
  const sr = ctx.sampleRate;
  const bpm = 100;
  const beat = 60 / bpm;
  const bars = 8;
  const dur = bars * 4 * beat;
  const n = Math.floor(sr * dur);
  const buf = ctx.createBuffer(2, n, sr);
  const L = buf.getChannelData(0);
  const R = buf.getChannelData(1);

  for (let i = 0; i < n; i++) {
    const t = i / sr;
    const posInBeat = (t % beat) / beat;
    const beatIndex = Math.floor(t / beat) % 16;
    const barBeat = beatIndex % 4;

    const kickEnv = Math.exp(-posInBeat * 16);
    const kickF = 48 + (1 - posInBeat) * 70;
    const kick = Math.sin(2 * Math.PI * kickF * t) * kickEnv * (barBeat === 0 || barBeat === 2 ? 0.9 : 0.15);

    const snareOn = barBeat === 1 || barBeat === 3;
    const snareEnv = snareOn ? Math.exp(-posInBeat * 22) : 0;
    const noise = (Math.random() * 2 - 1) * snareEnv * 0.45;
    const snareTone = Math.sin(2 * Math.PI * 180 * t) * snareEnv * 0.2;

    const hatOn = posInBeat < 0.08 && beatIndex % 2 === 1;
    const hat = hatOn ? (Math.random() * 2 - 1) * Math.exp(-posInBeat * 60) * 0.22 : 0;

    const drone = Math.sin(2 * Math.PI * (110 + Math.sin(t * 0.4) * 8) * t) * 0.08
      + Math.sin(2 * Math.PI * 165 * t) * 0.04 * (0.5 + 0.5 * Math.sin(t * 0.7));

    const eighth = (t % (beat / 2)) / (beat / 2);
    const tom = beatIndex % 8 === 6 ? Math.sin(2 * Math.PI * 90 * t) * Math.exp(-eighth * 10) * 0.35 : 0;

    const sample = kick + noise + snareTone + hat + drone + tom;
    const pan = Math.sin(t * 0.3) * 0.15;
    L[i] = sample * (1 - pan) * 0.85;
    R[i] = sample * (1 + pan) * 0.85;
  }
  return buf;
}

export function createAudioEngine(): AudioEngine {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.72;
  const master = ctx.createGain();
  master.gain.value = 0.85;
  master.connect(analyser);
  analyser.connect(ctx.destination);

  const time = new Uint8Array(analyser.fftSize);
  const freq = new Uint8Array(analyser.frequencyBinCount);

  let source: AudioBufferSourceNode | null = null;
  let buffer: AudioBuffer | null = null;
  let startedAt = 0;
  let pausedAt = 0;
  let playing = false;
  let lastRms = 0;
  let peakHold = 0;

  function stopSource() {
    if (source) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
      source.disconnect();
      source = null;
    }
  }

  function connectBuffer(buf: AudioBuffer, offset: number) {
    stopSource();
    buffer = buf;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    src.connect(master);
    src.start(0, offset % buf.duration);
    source = src;
    startedAt = ctx.currentTime - offset;
    playing = true;
  }

  const engine: AudioEngine = {
    ctx,
    analyser,
    master,
    get playing() {
      return playing;
    },
    get duration() {
      return buffer?.duration ?? 0;
    },
    currentTime() {
      if (!buffer) return 0;
      if (!playing) return pausedAt;
      return (ctx.currentTime - startedAt) % buffer.duration;
    },
    async play() {
      if (ctx.state === "suspended") await ctx.resume();
      if (!buffer) await engine.loadDemo();
      if (playing) return;
      connectBuffer(buffer!, pausedAt);
    },
    pause() {
      if (!playing) return;
      pausedAt = engine.currentTime();
      playing = false;
      stopSource();
    },
    async loadFile(file: File) {
      const arr = await file.arrayBuffer();
      if (ctx.state === "suspended") await ctx.resume();
      const buf = await ctx.decodeAudioData(arr.slice(0));
      pausedAt = 0;
      connectBuffer(buf, 0);
    },
    async loadUrl(url: string) {
      const res = await fetch(url);
      const arr = await res.arrayBuffer();
      const buf = await ctx.decodeAudioData(arr.slice(0));
      stopSource();
      buffer = buf;
      pausedAt = 0;
      playing = false;
    },
    async loadDemo() {
      if (ctx.state === "suspended") await ctx.resume();
      const buf = makeKickSnareLoop(ctx);
      pausedAt = 0;
      connectBuffer(buf, 0);
    },
    features() {
      analyser.getByteTimeDomainData(time);
      analyser.getByteFrequencyData(freq);
      let sum = 0;
      for (let i = 0; i < time.length; i++) {
        const v = ((time[i] ?? 128) - 128) / 128;
        sum += v * v;
      }
      const rms = Math.min(1, Math.sqrt(sum / time.length) * 2.4);
      const bass = Math.min(1, bandEnergy(freq, 1, 10) * 3.2);
      const mid = Math.min(1, bandEnergy(freq, 10, 48) * 2.6);
      const treble = Math.min(1, bandEnergy(freq, 48, 180) * 2.8);
      let magSum = 0;
      let weighted = 0;
      for (let i = 1; i < freq.length; i++) {
        const m = freq[i] ?? 0;
        magSum += m;
        weighted += m * i;
      }
      const centroid = magSum > 0 ? Math.min(1, weighted / magSum / (freq.length * 0.35)) : 0.4;
      const rising = rms > lastRms + 0.04;
      lastRms = rms;
      const peak = rising && rms > peakHold * 0.9;
      peakHold = Math.max(rms, peakHold * 0.992);
      return { rms, bass, mid, treble, centroid, peak };
    },
    destroy() {
      stopSource();
      void ctx.close();
    },
  };

  return engine;
}

export function idleFeatures(t: number): AudioFeatures {
  const pulse = 0.5 + 0.5 * Math.sin(t * 1.7);
  const kick = Math.max(0, Math.sin(t * 6.2));
  const rms = 0.28 + pulse * 0.22 + kick * 0.35;
  return {
    rms: Math.min(1, rms),
    bass: 0.25 + kick * 0.55,
    mid: 0.3 + 0.3 * Math.sin(t * 2.1 + 1),
    treble: 0.2 + 0.35 * Math.sin(t * 3.4),
    centroid: 0.35 + 0.25 * Math.sin(t * 0.6),
    peak: kick > 0.92,
  };
}
