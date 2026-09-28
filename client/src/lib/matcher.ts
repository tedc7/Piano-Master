// Simple play-along note matching (arch §7.1, §7.2): each played note matches the nearest
// unmatched expected note of the same pitch within the match window. M2 builds the full
// evaluator (accuracy, timing points, stars) on the results kept here.
//
// Times: `beat` is the playback beat the note was played at, already corrected for latency;
// `spb` is seconds per beat at the current tempo, so windows stay in milliseconds at any preset.

export interface Windows { onTimeMs: number; earlyLateMs: number; matchMs: number }

/** Prep A to Prep B (arch §7.1). Later level bands are narrower. */
export const PREP_WINDOWS: Windows = { onTimeMs: 150, earlyLateMs: 300, matchMs: 450 };

export const BRUSH_VELOCITY = 15;     // softer than this is a brush, not a wrong note
export const BRUSH_RELEASE_MS = 40;   // released this fast: a brush
export const RESTRIKE_MS = 150;       // the same correct key again this soon: a re-strike

export interface Expected { id: number; pitch: number; beat: number; phrase: number }

export type Verdict =
  | { kind: "hit"; noteId: number; deltaMs: number; onTime: boolean }
  | { kind: "wrong"; pitch: number; beat: number }
  | { kind: "ignored"; reason: "brush" | "restrike" };

interface Hit { deltaMs: number; beat: number }
interface Wrong { pitch: number; beat: number; phrase: number; timeMs: number; retracted: boolean }

export class Matcher {
  readonly hits = new Map<number, Hit>();
  readonly missed = new Set<number>();
  readonly wrongs: Wrong[] = [];
  private byPitch = new Map<number, Expected[]>();
  private lastHitAt = new Map<number, number>();    // pitch -> timeMs
  private missCursor = 0;

  constructor(
    readonly expected: Expected[],               // sorted by beat
    private phraseAt: (beat: number) => number,
    readonly windows: Windows = PREP_WINDOWS,
  ) {
    for (const e of expected) {
      if (!this.byPitch.has(e.pitch)) this.byPitch.set(e.pitch, []);
      this.byPitch.get(e.pitch)!.push(e);
    }
  }

  /** Match window for one expected note, in beats: never more than half the gap to the
   *  neighbouring expected notes of the same pitch, so fast repeats can't match the wrong one. */
  windowBeats(e: Expected, spb: number): number {
    let w = this.windows.matchMs / 1000 / spb;
    const same = this.byPitch.get(e.pitch)!;
    const i = same.indexOf(e);
    if (i > 0) w = Math.min(w, (e.beat - same[i - 1].beat) / 2);
    if (i + 1 < same.length) w = Math.min(w, (same[i + 1].beat - e.beat) / 2);
    return w;
  }

  noteOn(pitch: number, beat: number, velocity: number, spb: number, timeMs: number): Verdict {
    if (velocity < BRUSH_VELOCITY) return { kind: "ignored", reason: "brush" };
    let best: Expected | null = null;
    let bestDelta = Infinity;
    for (const e of this.byPitch.get(pitch) ?? []) {
      if (this.hits.has(e.id) || this.missed.has(e.id)) continue;
      const d = beat - e.beat;
      if (Math.abs(d) <= this.windowBeats(e, spb) + 1e-9 && Math.abs(d) < Math.abs(bestDelta)) {
        best = e;
        bestDelta = d;
      }
    }
    if (best) {
      const deltaMs = bestDelta * spb * 1000;
      this.hits.set(best.id, { deltaMs, beat });
      this.lastHitAt.set(pitch, timeMs);
      return { kind: "hit", noteId: best.id, deltaMs, onTime: Math.abs(deltaMs) <= this.windows.onTimeMs };
    }
    const last = this.lastHitAt.get(pitch);
    if (last !== undefined && timeMs - last <= RESTRIKE_MS) return { kind: "ignored", reason: "restrike" };
    this.wrongs.push({ pitch, beat, phrase: this.phraseAt(beat), timeMs, retracted: false });
    return { kind: "wrong", pitch, beat };
  }

  /** A wrong note released within 40 ms was a brush: take it back. */
  noteOff(pitch: number, timeMs: number): void {
    for (let i = this.wrongs.length - 1; i >= 0; i--) {
      const w = this.wrongs[i];
      if (w.pitch !== pitch || w.retracted) continue;
      if (timeMs - w.timeMs <= BRUSH_RELEASE_MS) w.retracted = true;
      return;
    }
  }

  /** Mark notes whose window has closed unmatched; returns the ids newly missed. */
  advance(beat: number, spb: number): number[] {
    const out: number[] = [];
    for (let i = this.missCursor; i < this.expected.length; i++) {
      const e = this.expected[i];
      if (e.beat > beat) break;
      if (this.hits.has(e.id) || this.missed.has(e.id)) {
        if (i === this.missCursor) this.missCursor++;
        continue;
      }
      if (e.beat + this.windowBeats(e, spb) < beat) {
        this.missed.add(e.id);
        out.push(e.id);
        if (i === this.missCursor) this.missCursor++;
      }
    }
    return out;
  }

  /** A new pass from `beat` (after a rewind or restart): only the last pass counts (§7.2). */
  resetFrom(beat: number): void {
    for (const e of this.expected) {
      if (e.beat >= beat - 1e-6) {
        this.hits.delete(e.id);
        this.missed.delete(e.id);
      }
    }
    for (const w of this.wrongs) if (w.beat >= beat - 1e-6) w.retracted = true;
    this.missCursor = this.expected.findIndex((e) => e.beat >= beat - 1e-6);
    if (this.missCursor < 0) this.missCursor = this.expected.length;
  }

  /** Missed plus wrong notes in one phrase (the rewind trigger counts both, §3). */
  phraseErrors(phrase: number): { count: number; firstBeat: number | null } {
    const beats: number[] = [];
    for (const e of this.expected) if (e.phrase === phrase && this.missed.has(e.id)) beats.push(e.beat);
    for (const w of this.wrongs) if (w.phrase === phrase && !w.retracted) beats.push(w.beat);
    return { count: beats.length, firstBeat: beats.length ? Math.min(...beats) : null };
  }

  /** The earliest expected note at or after `beat` that has not been played. */
  firstUnplayedFrom(beat: number): Expected | null {
    for (const e of this.expected) if (e.beat >= beat - 1e-6 && !this.hits.has(e.id)) return e;
    return null;
  }

  summary() {
    let onTime = 0;
    for (const h of this.hits.values()) if (Math.abs(h.deltaMs) <= this.windows.onTimeMs) onTime++;
    return {
      expected: this.expected.length,
      hits: this.hits.size,
      onTime,
      missed: this.expected.length - this.hits.size,
      wrong: this.wrongs.filter((w) => !w.retracted).length,
    };
  }
}
