// The tap-along calibration's arithmetic (arch §2.6.1): tap time minus click time for each click,
// stray taps left out, then the average (the latency offset) and the spread (standard deviation).

export interface Calibration {
  ok: boolean;              // enough taps to trust the average
  steady: boolean;          // spread under about 20 ms (the qualification test's pass mark)
  offsetMs: number;
  spreadMs: number;
  used: number;
  missed: number;           // clicks without a tap
  outliers: number[];       // indexes of the stray taps left out
  message: string;
}

export const MIN_TAPS = 16;         // of 24: two in three clicks must have a tap
export const STRAY_MS = 80;         // a tap this far from the median is a stray (a slip, not latency)
export const STEADY_MS = 20;

export function calibrate(taps: (number | null)[]): Calibration {
  const idx = taps.map((t, i) => [t, i] as const).filter((x): x is readonly [number, number] => x[0] !== null);
  const missed = taps.length - idx.length;
  const sorted = idx.map(([t]) => t).sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  const outliers = idx.filter(([t]) => Math.abs(t - median) > STRAY_MS).map(([, i]) => i);
  const used = idx.filter(([, i]) => !outliers.includes(i)).map(([t]) => t);
  const none = { steady: false, offsetMs: 0, spreadMs: 0, used: used.length, missed, outliers };
  if (used.length < MIN_TAPS) {
    return { ...none, ok: false, message: `Only ${used.length} steady taps (at least ${MIN_TAPS} are needed): try again, one tap with each click.` };
  }
  const mean = used.reduce((a, b) => a + b, 0) / used.length;
  const sd = Math.sqrt(used.reduce((a, b) => a + (b - mean) ** 2, 0) / (used.length - 1));
  const spreadMs = Math.round(sd);
  return { ok: true, steady: spreadMs <= STEADY_MS, offsetMs: Math.round(mean), spreadMs, used: used.length, missed, outliers, message: "" };
}
