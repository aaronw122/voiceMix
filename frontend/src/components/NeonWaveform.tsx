// Neon rainbow reactive waveform (canvas).
// Modes:
//   'recording'    — live bars pushed from analyser (real mic) or simulated amplitude
//   'transforming' — shimmering morph "thinking" animation over captured bars
//   'ready'        — captured waveform, dimmed, with a play affordance
//   'playing'      — captured waveform filling with rainbow as progress advances
// The rainbow runs green→cyan→blue→magenta→red→orange→yellow to match the brand icon.
import { useEffect, useRef, type MutableRefObject } from "react";

const BAR_COUNT = 54;

export type WaveMode = "recording" | "transforming" | "ready" | "playing";

// hue sweep that matches the icon: green(140) → ... → yellow(60) the long way round
export function rainbowAt(t: number): number {
  return (140 + t * 280) % 360;
}
function rainbowColor(t: number, light = 60, sat = 100, alpha = 1): string {
  return `hsla(${rainbowAt(t)}, ${sat}%, ${light}%, ${alpha})`;
}

function roundBar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const r = Math.min(w / 2, h / 2, 6);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  ctx.fill();
}

interface Props {
  mode?: WaveMode;
  analyserRef?: MutableRefObject<AnalyserNode | null> | null;
  progress?: number; // 0..1 for playing
  capturedRef?: MutableRefObject<number[]> | null; // captured bar array (mutated during recording)
  height?: number;
  glow?: number;
}

export function NeonWaveform({
  mode = "recording",
  analyserRef = null,
  progress = 0,
  capturedRef = null,
  height = 140,
  glow = 1,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef(0);
  const modeRef = useRef(mode);
  const progressRef = useRef(progress);
  const tRef = useRef(0);
  const scrollRef = useRef<number[]>([]); // live recording rolling buffer

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  useEffect(() => {
    progressRef.current = progress;
  }, [progress]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let W = 0,
      H = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);

    function resize() {
      const r = canvas!.getBoundingClientRect();
      W = r.width;
      H = r.height;
      canvas!.width = W * dpr;
      canvas!.height = H * dpr;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const freqData = new Uint8Array(2048);

    function liveAmplitude(): number {
      const a = analyserRef && analyserRef.current;
      if (a) {
        const data = freqData.subarray(0, a.frequencyBinCount);
        a.getByteFrequencyData(data);
        // weight lower-mid frequencies (voice band)
        let sum = 0,
          n = 0;
        const lim = Math.floor(data.length * 0.45);
        for (let i = 0; i < lim; i++) {
          sum += data[i];
          n++;
        }
        const avg = sum / (n * 255);
        return Math.min(1, Math.pow(avg * 1.7, 0.9));
      }
      // simulated: layered sines + noise → lively voice-like envelope
      const t = tRef.current;
      const env = 0.5 + 0.5 * Math.sin(t * 1.7) * Math.sin(t * 0.6 + 1);
      const burst = Math.max(0, Math.sin(t * 9.0)) * 0.5;
      const noise = Math.random() * 0.35;
      return Math.min(1, 0.18 + env * 0.55 + burst * 0.4 * Math.random() + noise);
    }

    function draw() {
      tRef.current += 0.016;
      const t = tRef.current;
      const m = modeRef.current;
      ctx!.clearRect(0, 0, W, H);
      const mid = H / 2;
      const gap = W / BAR_COUNT;
      const bw = Math.max(2.5, gap * 0.42);

      if (m === "recording") {
        const amp = liveAmplitude();
        const buf = scrollRef.current;
        buf.push(amp);
        while (buf.length > BAR_COUNT) buf.shift();
        if (capturedRef) capturedRef.current = buf.slice();

        for (let i = 0; i < buf.length; i++) {
          const x = i * gap + gap / 2;
          const tcol = i / BAR_COUNT;
          const h = Math.max(3, buf[i] * (height * 0.5));
          ctx!.shadowBlur = 14 * glow;
          ctx!.shadowColor = rainbowColor(tcol, 62, 100, 0.9);
          ctx!.fillStyle = rainbowColor(tcol, 62);
          roundBar(ctx!, x - bw / 2, mid - h, bw, h * 2);
        }
      } else if (m === "transforming") {
        const cap = (capturedRef && capturedRef.current) || [];
        for (let i = 0; i < BAR_COUNT; i++) {
          const x = i * gap + gap / 2;
          const tcol = i / BAR_COUNT;
          const base = cap[i] != null ? cap[i] : 0.4;
          const wave = Math.sin(i * 0.5 - t * 6) * 0.5 + 0.5;
          const pulse = 0.35 + 0.65 * wave;
          const h = Math.max(3, base * pulse * (height * 0.5));
          const drift = (tcol + t * 0.15) % 1;
          ctx!.shadowBlur = (10 + wave * 16) * glow;
          ctx!.shadowColor = rainbowColor(drift, 62, 100, 0.95);
          ctx!.fillStyle = rainbowColor(drift, 60 + wave * 8);
          roundBar(ctx!, x - bw / 2, mid - h, bw, h * 2);
        }
      } else {
        // ready / playing
        const cap = (capturedRef && capturedRef.current) || [];
        const prog = m === "playing" ? progressRef.current : 0;
        for (let i = 0; i < BAR_COUNT; i++) {
          const x = i * gap + gap / 2;
          const tcol = i / BAR_COUNT;
          const base = cap[i] != null ? cap[i] : 0.2 + 0.6 * Math.abs(Math.sin(i * 0.7));
          const h = Math.max(3, base * (height * 0.5));
          const played = i / BAR_COUNT <= prog;
          if (played) {
            ctx!.shadowBlur = 14 * glow;
            ctx!.shadowColor = rainbowColor(tcol, 62, 100, 0.9);
            ctx!.fillStyle = rainbowColor(tcol, 62);
          } else {
            ctx!.shadowBlur = 0;
            ctx!.fillStyle = m === "playing" ? "rgba(255,255,255,0.16)" : rainbowColor(tcol, 52, 70, 0.5);
          }
          roundBar(ctx!, x - bw / 2, mid - h, bw, h * 2);
        }
      }
      ctx!.shadowBlur = 0;
      rafRef.current = requestAnimationFrame(draw);
    }

    if (modeRef.current === "recording" && scrollRef.current.length === 0) {
      scrollRef.current = seedBuffer();
    }
    draw(); // synchronous first frame (paints even when rAF is throttled/hidden)
    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // seed rolling buffer when (re)entering recording so the wave looks alive instantly
  useEffect(() => {
    if (mode === "recording") scrollRef.current = seedBuffer();
  }, [mode]);

  return <canvas ref={canvasRef} style={{ width: "100%", height, display: "block" }} />;
}

function seedBuffer(): number[] {
  return Array.from({ length: BAR_COUNT }, (_, i) => {
    const env = 0.4 + 0.45 * Math.abs(Math.sin(i * 0.5) * Math.cos(i * 0.21));
    return Math.max(0.08, env * (0.6 + 0.4 * Math.random()));
  });
}
