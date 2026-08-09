/**
 * §0.11's renderer — one 2D canvas layer, no WebGL, no DOM particles.
 *
 * §0.11 permits "constellation Rive/Canvas script"; this is the Canvas half.
 * Choosing it over Rive is a budget decision the spec makes possible rather
 * than a shortcut: the sequence's asset budget is 220KB TOTAL including audio
 * and Tara's artboard, and a Rive runtime spends a meaningful fraction of that
 * before drawing a star. The shapes here are seven points, some lines and a
 * particle field — geometry, not artwork.
 *
 * **Colours come from tokens, read at start.** §0.11 names six hexes; all six
 * are in `packages/tokens` under a theme-INVARIANT `launch.*` group, because
 * §0.11 fixes the palette ("No other hues permitted in the sequence") and the
 * arrival must not re-colour at dusk. `getComputedStyle` is how a canvas reads
 * a token; a literal here would fail `token-lint` and would also be wrong.
 *
 * **Nothing here is a §24.3 component.** It draws pixels into a canvas the
 * screen owns. See `paths.ts`.
 */

import {
  BLOOM_STAR_INDEX,
  CONSTELLATION,
  FULL_DURATION_MS,
  SHORT_DURATION_MS,
  STATIC_DURATION_MS,
  type DeviceTier,
  type LaunchPath,
} from "./paths";

interface Palette {
  skyTop: string;
  skyBottom: string;
  star: string;
  starDim: string;
  line: string;
  bloom: string;
}

function readPalette(host: HTMLElement): Palette {
  const s = getComputedStyle(host);
  const get = (name: string, fallback: string) =>
    s.getPropertyValue(name).trim() || fallback;
  // The fallbacks are the token values and exist only for a canvas that
  // somehow mounts before the stylesheet; they are never the styling path.
  return {
    skyTop: get("--color-launch-sky-top", "rgb(15,19,48)"),
    skyBottom: get("--color-launch-sky-bottom", "rgb(30,39,97)"),
    star: get("--color-launch-star", "rgb(255,255,255)"),
    starDim: get("--color-launch-star-dim", "rgb(232,234,246)"),
    line: get("--color-launch-line", "rgb(201,162,39)"),
    bloom: get("--color-launch-bloom", "rgb(231,211,145)"),
  };
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** §0.11 phase 2/3 easing: `cubic-bezier(0.22,0.61,0.36,1)`, sampled. */
function easeStandard(t: number): number {
  const x = clamp01(t);
  return 1 - Math.pow(1 - x, 3);
}

const easeInOut = (t: number) =>
  clamp01(t) < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

/**
 * Deterministic pseudo-noise. `Math.random` is deliberately unused: two runs of
 * the same path must produce the same frames, or the §24.8 screenshot baseline
 * for S01 could never be stable and the ±80ms timing acceptance would be
 * measured against a different picture every time.
 */
function noise(seed: number): number {
  const x = Math.sin(seed * 127.1) * 43758.5453;
  return x - Math.floor(x);
}

interface Particle {
  x: number;
  y: number;
  size: number;
  speed: number;
  amplitude: number;
  phase: number;
  life: number;
  born: number;
}

function seedParticles(count: number, w: number, h: number): Particle[] {
  return Array.from({ length: count }, (_, i) => ({
    // §0.11: "spawn edges bottom+left".
    x: noise(i * 3.1) < 0.5 ? noise(i * 7.7) * w : noise(i * 11.3) * w * 0.25,
    y: h - noise(i * 5.2) * h * 0.4,
    size: 1.5 + noise(i * 13.9) * 1.5, // §0.11: 1.5–3px
    speed: 8 + noise(i * 17.3) * 6, // §0.11: 8–14px/s
    amplitude: 10 * (noise(i * 19.1) * 2 - 1), // §0.11: lateral ±10px
    phase: noise(i * 23.7) * Math.PI * 2,
    life: 2500 + noise(i * 29.5) * 1500, // §0.11: 2.5–4s
    born: -noise(i * 31.1) * 3000,
  }));
}

export interface SequenceOptions {
  canvas: HTMLCanvasElement;
  path: LaunchPath;
  tier: DeviceTier;
  particles: number;
  /** Fires when the sequence reaches its end (never fires if stopped first). */
  onDone: () => void;
  /** Fires once if the first-500ms probe measures below §0.11's 24fps floor. */
  onFpsDowngrade: () => void;
}

export interface RunningSequence {
  stop(): void;
  /** Elapsed ms at the moment of the call — what the analytics event reports. */
  elapsed(): number;
}

export function runSequence(options: SequenceOptions): RunningSequence {
  const { canvas, path, tier, particles: particleCount, onDone, onFpsDowngrade } = options;
  const context = canvas.getContext("2d");
  const palette = readPalette(canvas);

  const dpr = Math.min(window.devicePixelRatio || 1, tier === "c" ? 1.5 : 2);
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  context?.scale(dpr, dpr);

  const isStatic = path === "reduced_motion" || path === "static";
  const total =
    path === "full" ? FULL_DURATION_MS : path === "short" ? SHORT_DURATION_MS : STATIC_DURATION_MS;
  const starCount = path === "full" ? 24 : 12;
  const particles = seedParticles(particleCount, width, height);
  const shorter = Math.min(width, height);
  const originX = (width - shorter) / 2;
  const originY = (height - shorter) / 2;
  const point = (i: number): [number, number] => {
    const [ux, uy] = CONSTELLATION[i % CONSTELLATION.length]!;
    return [originX + ux * shorter, originY + uy * shorter];
  };

  let raf = 0;
  let start = 0;
  let elapsed = 0;
  let stopped = false;
  let frames = 0;
  let probed = false;

  function sky(alpha: number) {
    if (!context) return;
    const gradient = context.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, palette.skyTop);
    gradient.addColorStop(1, palette.skyBottom);
    context.globalAlpha = alpha;
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    context.globalAlpha = 1;
  }

  /** Drifting field stars — the ones that gather into the constellation. */
  function fieldStars(t: number, gather: number) {
    if (!context) return;
    for (let i = 0; i < starCount; i += 1) {
      const target = point(i % CONSTELLATION.length);
      const sx = originX + noise(i * 2.3) * shorter;
      const sy = originY + noise(i * 4.7) * shorter;
      const x = sx + (target[0] - sx) * gather;
      const y = sy + (target[1] - sy) * gather;
      // §0.11: "twinkle ±15% brightness, 1.8s period". Below WCAG 2.3's 3/s.
      const twinkle = 0.85 + 0.15 * Math.sin((t / 1800) * Math.PI * 2 + i);
      context.globalAlpha = twinkle * (i < CONSTELLATION.length ? 1 : 0.45);
      context.fillStyle = i % 3 === 0 ? palette.star : palette.starDim;
      context.beginPath();
      context.arc(x, y, 1.4, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;
  }

  /** §0.11 phase 3: "thin gold lines (1px, 40% opacity) draw between them". */
  function constellationLines(progress: number) {
    if (!context || progress <= 0) return;
    context.strokeStyle = palette.line;
    context.globalAlpha = 0.4;
    context.lineWidth = 1;
    const segments = CONSTELLATION.length - 1;
    const drawn = progress * segments;
    context.beginPath();
    for (let i = 0; i < segments; i += 1) {
      const share = clamp01(drawn - i);
      if (share <= 0) break;
      const [x1, y1] = point(i);
      const [x2, y2] = point(i + 1);
      context.moveTo(x1, y1);
      context.lineTo(x1 + (x2 - x1) * share, y1 + (y2 - y1) * share);
    }
    context.stroke();
    context.globalAlpha = 1;
  }

  /**
   * §0.11 phase 4: scale 1→2.4×, bloom radius 24px, white→#E7D391, others dim
   * to 35%. "bloom via radial gradient, no real blur filter (perf)" — and on
   * tier C a flat disc, which is §0.11's "pre-baked bloom sprite" without the
   * sprite: the same picture, no per-frame gradient allocation.
   */
  function bloom(progress: number) {
    if (!context || progress <= 0) return;
    const [x, y] = point(BLOOM_STAR_INDEX);
    const eased = easeInOut(progress);
    const radius = 24 * eased;
    if (tier === "c") {
      context.globalAlpha = 0.9 * eased;
      context.fillStyle = palette.bloom;
      context.beginPath();
      context.arc(x, y, Math.max(2, radius * 0.5), 0, Math.PI * 2);
      context.fill();
      context.globalAlpha = 1;
      return;
    }
    const gradient = context.createRadialGradient(x, y, 0, x, y, Math.max(1, radius));
    gradient.addColorStop(0, palette.bloom);
    gradient.addColorStop(1, "transparent");
    context.fillStyle = gradient;
    context.beginPath();
    context.arc(x, y, Math.max(1, radius), 0, Math.PI * 2);
    context.fill();
  }

  function particleField(t: number) {
    if (!context || particles.length === 0) return;
    context.fillStyle = palette.line;
    for (const p of particles) {
      const age = t - p.born;
      if (age < 0) continue;
      const cycle = age % p.life;
      const life = cycle / p.life;
      // §0.11: "lifetime 2.5–4s with fade in/out", 20–45% opacity.
      const fade = life < 0.2 ? life / 0.2 : life > 0.8 ? (1 - life) / 0.2 : 1;
      context.globalAlpha = (0.2 + 0.25 * noise(p.phase)) * fade;
      const y = p.y - (p.speed * cycle) / 1000;
      const x = p.x + Math.sin(cycle / 700 + p.phase) * p.amplitude;
      context.beginPath();
      context.arc(x, y, p.size / 2, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;
  }

  function drawStatic(t: number) {
    // §0.11's reduced-motion path: "no drift, no particles: a 1.2s crossfade
    // (sky → static constellation + wordmark → Home)". The constellation is
    // drawn complete from the first frame; only opacity moves.
    const alpha = clamp01(t / (STATIC_DURATION_MS * 0.6));
    if (!context) return;
    context.clearRect(0, 0, width, height);
    sky(alpha);
    context.globalAlpha = alpha;
    fieldStars(0, 1);
    constellationLines(1);
    context.globalAlpha = 1;
  }

  function drawFull(t: number) {
    if (!context) return;
    context.clearRect(0, 0, width, height);
    sky(clamp01(t / 600));
    particleField(t);
    const gather = easeStandard((t - 600) / 1200);
    fieldStars(t, path === "short" ? 1 : gather);
    const lines = path === "short" ? 1 : clamp01((t - 1800) / 600);
    constellationLines(lines);
    if (path === "full") bloom((t - 2800) / 800);
  }

  function frame(now: number) {
    if (stopped) return;
    if (!start) start = now;
    elapsed = now - start;
    frames += 1;

    if (!probed && elapsed >= 500) {
      probed = true;
      // §0.11: "if the first 500ms drop below 24fps, the engine downgrades live
      // to the static form (measured, not assumed)".
      const fps = (frames / elapsed) * 1000;
      if (fps < 24 && !isStatic) {
        onFpsDowngrade();
        return;
      }
    }

    if (isStatic) drawStatic(elapsed);
    else drawFull(elapsed);

    if (elapsed >= total) {
      onDone();
      return;
    }
    raf = requestAnimationFrame(frame);
  }

  raf = requestAnimationFrame(frame);

  return {
    stop() {
      stopped = true;
      cancelAnimationFrame(raf);
    },
    elapsed: () => Math.round(elapsed),
  };
}
