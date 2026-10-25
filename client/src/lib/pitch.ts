// Microphone note detection (arch §4 "Microphone input", v0.38): an interim stand-in for the MIDI
// piano. Turns short frames of microphone audio into the same key-down and key-up events the MIDI
// input gives, for up to 4 keys at once. Pure code, so the tests can feed it synthetic tones.
//
// Each frame (4096 samples, every ~10 ms) goes through:
//  1. Spectrum: Hann window and FFT.
//  2. Noise floor: each frequency bin keeps a running estimate of the room's steady background
//     (fans, hum, hiss), which rises slowly and falls fast, and twice that is taken off the
//     spectrum (spectral subtraction). A note held a long time is not mistaken for background.
//     Echo: when given the app's own output (its vocals, backing and piano), the detector learns
//     how loud that comes back through the microphone, held for 150 ms for the room's echo, so the
//     app's music can play while the child does (the browser's echo cancellation removes most of
//     it first). A key counts only when it is at least twice as loud as the app's own sound of
//     that key would be: a key the child plays along with the singing still counts, as it adds
//     at least as much again.
//  3. Note candidates: every key in range is scored by the energy at its harmonics (harmonic
//     sum). The best key is taken, its harmonics removed, and the search repeats, so a note's own
//     octaves and fifths are not reported as extra keys.
//  4. Is it a piano note? The harmonics must stand well above the spectrum between them (a door
//     bang, a clap or hiss spreads energy evenly and fails), at least two of the first four
//     harmonics must be there, and the pitch must sit within 30 cents of the key and hold within
//     15 cents for 4 frames (a voice slides; a piano string holds its pitch).
//  5. Strike: a hammer makes the key's own harmonics jump from nothing within a few ms, which a
//     voice sliding between keys, a fan or a TV mostly does not. A key goes down only when it
//     passes for 4 frames in a row, its harmonics jumped in short windows (which time it, to 5 ms)
//     and its level in the full frame (which tells neighbouring keys apart) was low just before.
//     A key already down is struck again only when its harmonics jump again (a piano note only
//     decays on its own).
//  6. The app's own sounds: keys the app is sounding itself (its piano, the metronome) are masked.
//
// Each key-down carries `sure`: whether it is clear enough to count as a wrong note. A borderline
// detection, or a single pure tone (a top key, or just as likely an "s" or a whistle), can match the
// note the music expects, but is never scored as a mistake.

export const FRAME = 4096;
export const MAX_KEYS = 4;
const HARMONICS = 8;
const MAX_HZ = 5000;
// What a tablet's microphone hears of a small keyboard (measured on the iPad with the family's
// keyboard, Oct 2026): almost nothing below about 200 Hz, so a low key is heard only by its
// overtones (A0's partials 14 to 24), which piano strings stretch sharp; and the top two octaves
// as nearly pure tones, quietly.
const AUDIBLE_HZ = 150;        // partials below this are not counted on
const LOW_HZ = 250;            // a key below this may have no fundamental to hear
const LOW_PARTIALS = 16;       // a low key is scored on up to this many overtones
const STRETCH = 8e-5;          // string stiffness: partial n is at n·f0·√(1 + STRETCH·n²)
const PURE_FROM = 76;          // from E5 up, one clear partial is enough (nearly pure on a small keyboard)
const CENTS_OK = 30;           // the key's pitch must be within this many cents
const CENTS_DRIFT = 15;        // and hold within this while it is confirmed (a voice slides)
const CENTS_SURE = 10;         // a key held this steady can count as a wrong note
const PEAKINESS = 4;           // harmonic peaks over the spectrum beside them (unfiltered)
const CONFIRM_FRAMES = 4;
const BLOCK_S = 0.005;         // strikes are timed to 5 ms
const RISE_WINDOW = 1024;      // ...from 21 ms windows
const RISE_RATIO = 1.8;        // a struck key's harmonics rise this much on 25 ms before...
const RISE_LEVEL = 3;          // ...and its level in the full frame this much on 50-80 ms before
const HISTORY = 10;
const ONSET_KEPT_MS = 250;     // a key must be confirmed within this long of being struck
const RESTRIKE_JUMP = 2;       // a struck-again key at least doubles its harmonics' energy...
const RESTRIKE_LEVEL = 1.5;    // ...and its level in the full frame rises this much on its lowest...
const RESTRIKE_CONFIRM_MS = 80; // ...within this long
const RESTRIKE_GAP_MS = 90;    // and no sooner than this after its last strike
const OFF_FRACTION = 0.12;     // key up when the level falls below this share of its peak
const OFF_FRAMES = 3;
const FLOOR_UP = 0.004;        // per frame: the noise floor rises over a few seconds...
const FLOOR_DOWN = 0.25;       // ...and falls straight away when the room goes quiet
const OVERSUBTRACT = 2;
const ECHO_MARGIN = 2;         // a key must be twice as loud as the app's own sound of it...
const ECHO_HOLD = 0.86;        // ...held per frame, down to a tenth in 150 ms (the room's echo)
const ECHO_LAGS = 10;          // the echo's delay is found among the last 10 frames

/** Detection thresholds (harmonic-sum level, full scale = 1) by the parent's sensitivity setting. */
export const SENSITIVITY: Record<1 | 2 | 3, number> = { 1: 0.012, 2: 0.006, 3: 0.003 };

export interface DetectedNote {
  type: "on" | "off";
  pitch: number;
  velocity: number;
  timeMs: number;
  sure: boolean;
}

/** Radix-2 FFT in place (re, im of length a power of 2). */
export function fft(re: Float64Array, im: Float64Array): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k, b = a + len / 2;
        const xr = re[b] * cr - im[b] * ci;
        const xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi;
        re[a] += xr; im[a] += xi;
        const t = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = t;
      }
    }
  }
}

export const hzOf = (pitch: number) => 440 * Math.pow(2, (pitch - 69) / 12);

interface KeyState {
  down: boolean;
  passes: number;          // frames in a row it has passed, while up
  overEcho: number;        // frames in a row it has been well above the app's own sound of it
  firstCents: number;      // its pitch when the current run of passes began, in cents from the key
  drift: number;           // how far it has moved from that since
  onsetMs: number | null;  // when its harmonics jumped, if they did
  peak: number;
  low: number;             // lowest level since the strike settled
  pendingMs: number | null;   // a possible re-strike, waiting for the level to rise
  pendingBase: number;
  struckMs: number;
  releasedMs: number;
  lastPeak: number;        // its peak level the last time it was down
  fails: number;
}

/** A partial of a key that the device can hear, and its weight in the key's score. */
interface Partial { hz: number; h: number; w: number }

/** A key's partials from AUDIBLE_HZ up: 8 harmonics for most keys, and up to 16 overtones for a
 *  low key (whose fundamental may be missing), weighted from the first one heard. */
export function partialsOf(pitch: number): Partial[] {
  const f0 = hzOf(pitch), low = f0 < LOW_HZ, out: Partial[] = [];
  for (let h = 1; out.length < (low ? LOW_PARTIALS : HARMONICS); h++) {
    const hz = h * f0 * Math.sqrt(1 + STRETCH * h * h);
    if (hz > MAX_HZ) break;
    if (hz < AUDIBLE_HZ) continue;
    out.push({ hz, h, w: Math.pow(low ? 0.9 : 0.84, out.length) });
  }
  return out;
}

interface Candidate {
  pitch: number; level: number; peaky: number; cents: number;
  echo: number;            // the app's own sound of this key, as the microphone hears it
  pure: boolean;           // heard as one partial only (a top key; or an "s", a whistle, a beep)
}

export class NoteDetector {
  threshold: number;
  private readonly window = new Float64Array(FRAME);
  private readonly re = new Float64Array(FRAME);
  private readonly im = new Float64Array(FRAME);
  private readonly mag = new Float64Array(FRAME / 2);
  private readonly floor = new Float64Array(FRAME / 2);
  private readonly clean = new Float64Array(FRAME / 2);
  private readonly echo = new Float64Array(FRAME / 2);      // the app's own output, held, as the mic would hear it at 1:1
  // the app's own output in each of the last frames (newest first), with each one's strongest
  // bin: the microphone hears it some 20-100 ms later
  private readonly outputs = Array.from({ length: ECHO_LAGS }, () => new Float64Array(FRAME / 2));
  private readonly outputPeaks = new Float64Array(ECHO_LAGS);
  private readonly beside = new Float64Array(FRAME / 2);    // the spectrum less the echo, for peakiness
  /** How loud the app's own output comes back through the microphone (learned). */
  coupling = 1;
  private readonly keys = new Map<number, KeyState>();
  private readonly block: number;
  private readonly riseWindow = new Float64Array(RISE_WINDOW);
  private readonly history: Float64Array;      // each key's level in the full frame, for the last HISTORY frames
  private readonly partials: Partial[][];      // each key's partials (partialsOf), from lo
  private frameNo = 0;
  private started = false;
  /** The last frame's loudness and the noise floor, in dBFS, for the parent's level meter. */
  levelDb = -100;
  floorDb = -100;

  constructor(
    readonly sampleRate: number,
    readonly lo = 36,            // C2
    readonly hi = 96,            // C7
    sensitivity: 1 | 2 | 3 = 2,
  ) {
    this.threshold = SENSITIVITY[sensitivity];
    this.block = Math.round(sampleRate * BLOCK_S);
    this.history = new Float64Array((hi - lo + 1) * HISTORY);
    this.partials = Array.from({ length: hi - lo + 1 }, (_, i) => partialsOf(lo + i));
    for (let i = 0; i < RISE_WINDOW; i++) this.riseWindow[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (RISE_WINDOW - 1));
    for (let i = 0; i < FRAME; i++) this.window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (FRAME - 1));
    for (let p = lo; p <= hi; p++) {
      this.keys.set(p, { down: false, passes: 0, overEcho: 0, firstCents: 0, drift: 0, onsetMs: null, peak: 0, low: 0, pendingMs: null, pendingBase: 0, struckMs: -1e9, releasedMs: -1e9, lastPeak: 0, fails: 0 });
    }
  }

  /** Analyse one frame (the latest FRAME samples; `timeMs` is when its last sample was heard).
   *  `masked` says which keys the app itself is sounding now. Returns the key events. */
  process(samples: Float32Array, timeMs: number, masked: (pitch: number) => boolean = () => false,
          output?: Float32Array): DetectedNote[] {
    const frame = samples.length > FRAME ? samples.subarray(samples.length - FRAME) : samples;
    this.reference(output);
    this.spectrum(frame);
    const found = this.candidates();
    // learn the echo's level only while the child isn't playing: their keys would add to it
    if (this.down.length === 0 && found.every((c) => c.level < ECHO_MARGIN * c.echo)) this.learnCoupling();
    const out: DetectedNote[] = [];
    const seen = new Set<number>();
    for (const c of found) {
      seen.add(c.pitch);
      const k = this.keys.get(c.pitch)!;
      k.fails = 0;
      if (masked(c.pitch)) { k.passes = 0; continue; }
      // the child's key must stand well above the app's own sound of it (the echo)
      k.overEcho = c.level >= ECHO_MARGIN * c.echo ? k.overEcho + 1 : 0;
      // a sung note's vibrato in the echo wobbles the pitch of a key played along with it
      const drift = CENTS_DRIFT + (c.echo > 0.2 * c.level ? 20 : 0);
      if (!k.down) {
        if (k.passes === 0 || Math.abs(c.cents - k.firstCents) > drift) {
          k.passes = 0;
          k.firstCents = c.cents;
          k.drift = 0;
          // (the moment it was struck is kept through a moment's wobble: it must be recent, below)
        }
        k.drift = Math.max(k.drift, Math.abs(c.cents - k.firstCents));
        k.passes++;
        // the first frame holds only the start of the note: measure steadiness from the second
        if (k.passes === 2) { k.firstCents = c.cents; k.drift = 0; }
        if (k.onsetMs !== null && timeMs - k.onsetMs > ONSET_KEPT_MS) k.onsetMs = null;
        if (k.onsetMs === null) {
          const ago = this.riseAgo(frame, c.pitch, RISE_RATIO);
          if (ago !== null) k.onsetMs = timeMs - ago;
        }
        // new: its level in the full frame (which tells E from F) was low 50-80 ms ago, unless the
        // key itself was just let go (the same key played again)
        const again = timeMs - k.releasedMs < 150;
        // just let go, a key comes down again only at full strength: a top key's after-ring
        // swells back up after it dies away, but only a little
        const strong = timeMs - k.releasedMs >= 250 || c.level >= 0.5 * k.lastPeak;
        if (k.passes >= CONFIRM_FRAMES && k.onsetMs !== null && k.overEcho >= 2 && strong &&
            (again || this.levelNow(c.pitch) >= RISE_LEVEL * this.levelBefore(c.pitch))) {
          out.push(this.strike(c, k, k.onsetMs));
        }
      } else {
        // A piano note only fades on its own, so its harmonics jumping again is the key struck
        // again. The short windows time it, but can't tell it from a neighbouring key starting
        // (C4 and D4 are 33 Hz apart), so it counts only once this key's own level in the full
        // frame has risen too. While the frame is still filling with the note, its level only climbs.
        const settled = timeMs - k.struckMs >= RESTRIKE_GAP_MS;
        if (!settled) k.low = c.level;
        else if (k.pendingMs === null) {
          const ago = this.riseAgo(frame, c.pitch, RESTRIKE_JUMP, true);
          if (ago !== null && timeMs - ago - k.struckMs >= RESTRIKE_GAP_MS) { k.pendingMs = timeMs - ago; k.pendingBase = k.low; }
        }
        if (k.pendingMs !== null && c.level >= RESTRIKE_LEVEL * k.pendingBase) {
          out.push({ type: "off", pitch: c.pitch, velocity: 0, timeMs: k.pendingMs, sure: true });
          out.push(this.strike(c, k, k.pendingMs));
        } else {
          if (k.pendingMs !== null && timeMs - k.pendingMs > RESTRIKE_CONFIRM_MS) k.pendingMs = null;
          if (settled) k.low = Math.min(k.low, c.level);
          k.peak = Math.max(k.peak, c.level);
          if (c.level < k.peak * OFF_FRACTION) out.push(this.release(c.pitch, k, timeMs));
        }
      }
    }
    for (const [pitch, k] of this.keys) {
      if (seen.has(pitch)) continue;
      k.passes = k.overEcho = 0;
      if (k.down && ++k.fails >= OFF_FRAMES) out.push(this.release(pitch, k, timeMs));
    }
    this.frameNo++;
    return out;
  }

  private levelNow(pitch: number): number {
    return this.history[(pitch - this.lo) * HISTORY + (this.frameNo % HISTORY)];
  }

  /** The key's lowest level 5 to 8 frames ago (before a note struck now began to sound). */
  private levelBefore(pitch: number): number {
    let low = Infinity;
    for (let back = 5; back <= 8; back++) {
      low = Math.min(low, this.history[(pitch - this.lo) * HISTORY + ((this.frameNo - back + HISTORY * 2) % HISTORY)]);
    }
    return this.frameNo >= 8 ? low : 0;
  }

  /** Keys down now. */
  get down(): number[] {
    return [...this.keys].filter(([, k]) => k.down).map(([p]) => p);
  }

  private strike(c: Candidate, k: KeyState, timeMs: number): DetectedNote {
    k.down = true;
    k.passes = k.fails = 0;
    k.peak = k.low = c.level;
    k.pendingMs = null;
    k.onsetMs = null;
    k.struckMs = timeMs;
    // velocity: 30 at the threshold up to 110 at 30 dB above it
    const db = 20 * Math.log10(c.level / this.threshold);
    const velocity = Math.round(Math.max(30, Math.min(110, 30 + (db / 30) * 80)));
    // a single pure tone is a top key, or just as likely an "s" or a whistle: never surely wrong
    const sure = c.level >= 2 * this.threshold && c.peaky >= 2 * PEAKINESS && Math.abs(c.cents) <= CENTS_OK * 0.7 &&
      k.drift <= CENTS_SURE && !c.pure;
    return { type: "on", pitch: c.pitch, velocity, timeMs, sure };
  }

  private release(pitch: number, k: KeyState, timeMs: number): DetectedNote {
    k.down = false;
    k.releasedMs = timeMs;
    k.lastPeak = k.peak;
    k.passes = k.fails = 0;
    k.peak = k.low = 0;
    k.pendingMs = null;
    return { type: "off", pitch, velocity: 0, timeMs, sure: true };
  }

  /** When this key's own harmonics rose sharply within the frame (a hammer strike), in ms
   *  before the frame's end, or null. Short windows (21 ms) every 5 ms, each compared with the
   *  window 25 ms before it: a new key rises from nothing even under a key still ringing, and a
   *  voice sliding past never jumps at any one key. `recent` looks at the last 20 ms only. */
  private riseAgo(frame: Float32Array, pitch: number, ratio: number, recent = false): number | null {
    const sr = this.sampleRate, W = RISE_WINDOW, hop = this.block;
    const parts = this.partials[pitch - this.lo].slice(0, 6);
    const ends: number[] = [];
    for (let e = FRAME; e >= W; e -= hop) ends.unshift(e);
    const energy = ends.map((e) => {
      let sum = 0;
      for (const pt of parts) {
        // Goertzel at the partial's frequency, Hann-windowed
        const c = 2 * Math.cos((2 * Math.PI * pt.hz) / sr);
        let s1 = 0, s2 = 0;
        for (let i = 0; i < W; i++) {
          const s0 = frame[e - W + i] * this.riseWindow[i] + c * s1 - s2;
          s2 = s1; s1 = s0;
        }
        const amp = (Math.sqrt(Math.max(0, s1 * s1 + s2 * s2 - c * s1 * s2)) * 4) / W;
        sum += pt.w * amp * amp;
      }
      return sum;
    });
    const lag = Math.round(0.025 * sr / hop);
    const quiet = (this.threshold * this.threshold) / 16;
    const from = recent ? Math.max(lag, energy.length - 4) : lag;
    for (let j = from; j < energy.length; j++) {
      if (energy[j] > ratio * energy[j - lag] + quiet) return ((FRAME - ends[j] + W / 2) * 1000) / sr;
    }
    return null;
  }

  private spectrum(frame: Float32Array): void {
    const n = FRAME;
    let sum = 0;
    for (let i = 0; i < n; i++) {
      const x = frame[i] ?? 0;
      sum += x * x;
      this.re[i] = x * this.window[i];
      this.im[i] = 0;
    }
    this.levelDb = 10 * Math.log10(sum / n + 1e-12);
    fft(this.re, this.im);
    const scale = 4 / n;      // a full-scale sine reads about 1 at its peak bin
    let floorSum = 0;
    for (let b = 0; b < n / 2; b++) {
      const m = Math.hypot(this.re[b], this.im[b]) * scale;
      this.mag[b] = m;
      if (!this.started) this.floor[b] = m;
      else this.floor[b] += (m - this.floor[b]) * (m > this.floor[b] ? FLOOR_UP : FLOOR_DOWN);
      floorSum += this.floor[b] * this.floor[b];
    }
    for (let b = 0; b < n / 2; b++) {
      this.clean[b] = Math.max(0, this.mag[b] - OVERSUBTRACT * this.floor[b]);
      this.beside[b] = Math.max(this.floor[b], this.mag[b] - ECHO_MARGIN * this.coupling * this.echo[b]);
    }
    this.floorDb = 10 * Math.log10(floorSum / 2 + 1e-12);   // Hann's energy over the bins, roughly
    this.started = true;
  }

  /** Learn how loud the app's own output comes back: find the delay at which the microphone's
   *  spectrum best matches the output's, then at the output's strong peaks there, the share of it
   *  the microphone hears (the median). */
  private learnCoupling(): void {
    const top = Math.max(...this.outputPeaks);
    if (top < 1e-3) return;
    const bins = Math.round(MAX_HZ / (this.sampleRate / FRAME));
    let best = -1, bestCorr = 0.5;
    for (let lag = 0; lag < ECHO_LAGS; lag++) {
      if (this.outputPeaks[lag] < 0.5 * top) continue;     // a fading tail, not the sound itself
      const out = this.outputs[lag];
      let mo = 0, mm = 0, oo = 0;
      for (let b = 1; b < bins; b++) {
        mo += this.mag[b] * out[b]; mm += this.mag[b] * this.mag[b]; oo += out[b] * out[b];
      }
      const corr = mo / Math.sqrt(mm * oo + 1e-24);
      if (corr > bestCorr) { bestCorr = corr; best = lag; }
    }
    if (best < 0) return;
    const out = this.outputs[best], peak = this.outputPeaks[best];
    const ratios: number[] = [];
    for (let b = 1; b < bins; b++) {
      if (out[b] > 0.2 * peak && out[b] > 4 * this.floor[b]) ratios.push(this.mag[b] / out[b]);
    }
    if (ratios.length < 3) return;          // a count-in click is one tone: a few bins
    ratios.sort((x, y) => x - y);
    const est = ratios[Math.floor(ratios.length / 2)];
    this.coupling += (est - this.coupling) * 0.1;
  }

  /** The app's own output this frame (or silence): its spectrum, spread over neighbouring bins and
   *  held for the room's echo. */
  private reference(output?: Float32Array): void {
    const half = FRAME / 2;
    for (let b = 0; b < half; b++) this.echo[b] *= ECHO_HOLD;
    const now = this.outputs.pop()!;
    this.outputs.unshift(now);
    this.outputPeaks.copyWithin(1, 0);
    now.fill(0);
    this.outputPeaks[0] = 0;
    if (!output) return;
    const frame = output.length > FRAME ? output.subarray(output.length - FRAME) : output;
    let any = false;
    for (let i = 0; i < FRAME; i++) {
      const x = frame[i] ?? 0;
      if (x !== 0) any = true;
      this.re[i] = x * this.window[i];
      this.im[i] = 0;
    }
    if (!any) return;
    fft(this.re, this.im);
    const scale = 4 / FRAME;
    for (let b = 0; b < half; b++) {
      const m = Math.hypot(this.re[b], this.im[b]) * scale;
      now[b] = m;
      this.outputPeaks[0] = Math.max(this.outputPeaks[0], m);
      for (let d = -2; d <= 2; d++) {
        const k = b + d;
        if (k >= 0 && k < half && m > this.echo[k]) this.echo[k] = m;
      }
    }
  }

  /** The peak near `hz` in a spectrum, with its bin (fractional, by a parabolic fit); 0 when
   *  there is only the slope of a neighbouring peak. */
  private peakAt(spec: Float64Array, hz: number): { value: number; bin: number } {
    const binHz = this.sampleRate / FRAME;
    const centre = hz / binHz;
    // within about a third of a semitone either side, and at least the nearest bin
    const reach = Math.max(1, Math.round(centre * 0.02));
    let best = -1, value = 0;
    for (let b = Math.max(1, Math.round(centre) - reach); b <= Math.min(spec.length - 2, Math.round(centre) + reach); b++) {
      if (spec[b] > value) { value = spec[b]; best = b; }
    }
    if (best < 0 || value <= 0) return { value: 0, bin: centre };
    const a = spec[best - 1], c = spec[best + 1];
    if (a > value || c > value) return { value: 0, bin: centre };
    const d = a - 2 * value + c;
    const shift = d < 0 ? Math.max(-0.5, Math.min(0.5, (0.5 * (a - c)) / d)) : 0;
    return { value, bin: best + shift };
  }

  /** The app's own sound at a key's harmonics (held, before the coupling), weighted as in score(). */
  private echoLevel(pitch: number): number {
    const binHz = this.sampleRate / FRAME;
    let level = 0;
    for (const pt of this.partials[pitch - this.lo]) {
      const centre = pt.hz / binHz, reach = Math.max(1, Math.round(centre * 0.02));
      let most = 0;
      for (let b = Math.max(0, Math.round(centre) - reach); b <= Math.min(this.echo.length - 1, Math.round(centre) + reach); b++) {
        most = Math.max(most, this.echo[b]);
      }
      level += pt.w * most;
    }
    return level;
  }

  /** Harmonic sum for a key in `spec` (the cleaned spectrum, less keys already found), with the
   *  evidence that it is a real tone. */
  private score(spec: Float64Array, pitch: number): Candidate {
    const f0 = hzOf(pitch);
    const binHz = this.sampleRate / FRAME;
    const parts = this.partials[pitch - this.lo];
    const gap = Math.min(f0 / binHz / 2, Math.max(3, f0 / binHz / 4));
    const values: number[] = [];
    let level = 0, peaks = 0, beside = 0, present = 0, strongest = 0, centsAt = 0;
    parts.forEach((pt, k) => {
      const pk = this.peakAt(spec, pt.hz);
      values.push(pk.value);
      level += pt.w * pk.value;
      // Peakiness, on the spectrum less only the app's echo (noise subtraction leaves stray
      // peaks): the partial against the spectrum either side of it, taking the lower side, since
      // in a chord one side can hold another key's harmonic (C4's 1.25 is E4).
      const at = pt.hz / binHz;
      if (pk.value > 0) peaks += pt.w * this.mag[Math.round(pk.bin)];
      beside += pt.w * Math.min(this.beside[Math.round(at - gap)], this.beside[Math.round(at + gap)]);
      if (k < 4 && pk.value > this.threshold * 0.25) present++;
      if (k < 4 && pk.value > strongest) {
        strongest = pk.value;
        centsAt = 1200 * Math.log2((pk.bin * binHz) / pt.hz);
      }
    });
    // A key's own fundamental must sound: otherwise C3 would "explain" a C4-E4-G4 chord, whose
    // notes are its 2nd, 5th and 3rd harmonics. A low key may be heard by its overtones instead.
    // (a low key's fundamental is weak through small speakers: -17 to -22 dB for E3 on the family's)
    const fundamental = parts[0]?.h === 1 && values[0] >= (f0 < LOW_HZ ? 0.05 : 0.1) * Math.max(...values.slice(0, 4));
    if (!fundamental && !(f0 < LOW_HZ && this.lowKeyHeard(spec, parts, values))) level *= 0.1;
    const enough = pitch >= PURE_FROM ? 1 : 2;     // the top keys are nearly pure tones
    return { pitch, level, peaky: peaks / (beside + 1e-9), cents: present >= enough ? centsAt : 999, echo: 0, pure: present < 2 };
  }

  /** A low key whose fundamental the device doesn't hear is there when its overtones are, with
   *  evidence no other key could give (measured on the family's keyboard, where a low key's odd
   *  overtones carry 45% to 100% of its even ones' weight, and its 6th to 8th fade to -20 to
   *  -30 dB within 90 ms):
   *  - one of its 5th, 7th, 11th or 13th overtones (odd, and not 3 times another): the octave
   *    above has only its even ones;
   *  - two odd overtones, carrying at least 40% of its even ones' weight: a C4-E4-G4 chord is C2's
   *    4th, 5th and 6th overtones, so one odd one and about 33% (and the octave above, none);
   *  - no strong peak among its first overtones that isn't one of them (E4 in a C4-E4-G4 chord is
   *    no overtone of C3). */
  private lowKeyHeard(spec: Float64Array, parts: Partial[], values: number[]): boolean {
    const first = parts.slice(0, 8), v = values.slice(0, 8);
    const top = Math.max(...v);
    if (top <= 0) return false;
    const heard = (k: number) => v[k] >= 0.1 * top;
    const telling = first.some((pt, k) => pt.h >= 5 && pt.h % 2 === 1 && pt.h % 3 !== 0 && heard(k));
    let odd = 0, even = 0;
    first.forEach((pt, k) => { if (pt.h % 2) odd += v[k]; else even += v[k]; });
    const odds = first.filter((pt, k) => pt.h % 2 === 1 && v[k] >= 0.07 * top).length;
    if (!telling || odds < 2 || odd < 0.4 * even) return false;
    const binHz = this.sampleRate / FRAME;
    const from = Math.floor((first[0].hz * 0.97) / binHz), to = Math.ceil((first[Math.min(5, first.length - 1)].hz * 1.03) / binHz);
    for (let b = Math.max(1, from); b <= Math.min(spec.length - 2, to); b++) {
      if (spec[b] < 0.3 * top || spec[b] < spec[b - 1] || spec[b] < spec[b + 1]) continue;
      const hz = b * binHz;
      if (!parts.some((pt) => Math.abs(pt.hz - hz) <= Math.max(1.5 * binHz, pt.hz * 0.03))) return false;
    }
    return true;
  }

  /** The top keys are quiet on a small keyboard: from C6 up the threshold falls, to a quarter. */
  private thresholdFor(pitch: number): number {
    return this.threshold * (pitch > 84 ? Math.max(0.25, 1 - (pitch - 84) * 0.035) : 1);
  }

  private candidates(): Candidate[] {
    const binHz = this.sampleRate / FRAME;
    const found: Candidate[] = [];
    const taken = new Set<number>();
    let first = 0;
    const work = new Float64Array(this.clean);
    for (let round = 0; round < MAX_KEYS + 4 && found.length < MAX_KEYS; round++) {
      let best: Candidate | null = null;
      for (let p = this.lo; p <= this.hi; p++) {
        if (taken.has(p)) continue;
        const c = this.score(work, p);
        if (round === 0) this.history[(p - this.lo) * HISTORY + (this.frameNo % HISTORY)] = c.level;
        if (!best || c.level > best.level) best = c;
      }
      if (!best || best.level < this.thresholdFor(best.pitch) || best.level < first * 0.2) break;
      taken.add(best.pitch);
      // a key that isn't a clear tone (a key's knock heard as the key an octave below it) keeps
      // nothing: its partials stay for the next search, which may find the key itself
      if (best.peaky < PEAKINESS || Math.abs(best.cents) > CENTS_OK) continue;
      if (!first) first = best.level;
      // take this key's partials out before looking for the next key
      const f0 = hzOf(best.pitch);
      for (let h = 1; ; h++) {
        const hz = h * f0 * Math.sqrt(1 + STRETCH * h * h);
        if (hz > MAX_HZ + binHz) break;
        const b = Math.round(hz / binHz);
        for (let d = -2; d <= 2; d++) if (b + d > 0 && b + d < work.length) work[b + d] = 0;
      }
      best.echo = this.coupling * this.echoLevel(best.pitch);
      found.push(best);
    }
    return found;
  }
}
