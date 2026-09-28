// Performance scoring (arch §7): accuracy and timing from the matched notes, the practice-aid
// factor, and star ratings. Fixed, published rules: the same playing always earns the same stars.
// All numbers are a first version, to be tuned against recorded performances (§7.10).
import type { Windows } from "./matcher";
import type { Preset } from "./types";

/** Timing windows by level band (§7.1). */
export const WINDOWS_BY_BAND: Record<string, Windows> = {
  prep: { onTimeMs: 150, earlyLateMs: 300, matchMs: 450 },
  "1-2": { onTimeMs: 120, earlyLateMs: 250, matchMs: 400 },
  "3-4": { onTimeMs: 100, earlyLateMs: 220, matchMs: 350 },
  "5+": { onTimeMs: 80, earlyLateMs: 200, matchMs: 300 },
};

export function levelBand(level: string | undefined): string {
  const m = /level\s*(\d+)/i.exec(level ?? "");
  if (!m) return "prep";                 // Prep A, Prep B (and test pieces)
  const n = Number(m[1]);
  return n <= 2 ? "1-2" : n <= 4 ? "3-4" : "5+";
}

export const EXTRA_PENALTY = 0.25;       // per extra note (§7.3)
export const EXTRA_CAP = 0.1;            // ... capped at 10% of the expected notes
export const TIMING_STARS_MIN_ACCURACY = 0.5;

/** The conditions an attempt was played under (§5 Attempt.conditions). */
export interface Conditions {
  mode: "play";
  tempoPreset: Preset;                   // the slowest preset used in the attempt
  hands: "both" | "R" | "L";             // what was played
  handsWritten: "R" | "L" | "RL";        // what the item asks for
  sectionOnly: boolean;                  // a section loop or "Practice tricky part"
  extraHints: boolean;
  rewinds: number;
}

export interface Aid { id: string; label: string; factor: number }

/** The practice aids used, each with its factor (§7.5). Factors multiply. */
export function practiceAids(c: Conditions): Aid[] {
  const aids: Aid[] = [];
  const tempo: Record<Preset, number> = { "100": 1, "90": 0.92, "75": 0.86, "50": 0.78 };
  if (c.tempoPreset !== "100") aids.push({ id: "tempo", label: `${c.tempoPreset}% speed`, factor: tempo[c.tempoPreset] });
  if (c.rewinds > 0) {
    const f = c.rewinds === 1 ? 0.95 : c.rewinds === 2 ? 0.9 : 0.85;
    aids.push({ id: "rewinds", label: c.rewinds === 1 ? "1 rewind" : `${c.rewinds} rewinds`, factor: f });
  }
  if (c.handsWritten === "RL" && c.hands !== "both") {
    aids.push({ id: "hands", label: c.hands === "R" ? "right hand only" : "left hand only", factor: 0.85 });
  }
  if (c.sectionOnly) aids.push({ id: "section", label: "one section", factor: 0.9 });
  if (c.extraHints) aids.push({ id: "hints", label: "extra hints", factor: 0.95 });
  return aids;
}

/** Stars from a score after the aid factor (§7.6): half-star steps, steeper at the top. */
const STAR_STEPS: [number, number][] = [[0.96, 5], [0.91, 4.5], [0.86, 4], [0.8, 3.5], [0.74, 3], [0.67, 2.5], [0.6, 2], [0.5, 1.5], [0.4, 1]];
export function stars(score: number): number {
  for (const [min, s] of STAR_STEPS) if (score >= min - 1e-9) return s;
  return 0.5;
}

export const STAR_MEANING: Record<number, string> = {
  0.5: "Just starting", 1: "Just starting", 1.5: "Keep practicing", 2: "Keep practicing", 2.5: "Getting there",
  3: "Passed: ready to move on", 3.5: "Good", 4: "Mastered: solid", 4.5: "Very good", 5: "Excellent",
};

export interface Tally {
  expected: number;
  deltasMs: number[];      // one per matched note: played minus expected, after latency correction
  extra: number;           // played notes with no match (brushes, re-strikes, the other hand excluded)
}

export interface Evaluation {
  expected: number;
  matched: number;
  missed: number;
  extra: number;
  onTime: number;
  offTime: number;         // early or late
  outside: number;         // matched, but outside the early/late window
  rawAccuracy: number;
  rawTiming: number | null;
  factor: number;
  accuracy: number;
  timing: number | null;
  accuracyStars: number;
  timingStars: number | null;   // shown only when accuracy is 50% or more
  tendency: "early" | "late" | null;
  aids: Aid[];
  hint: string | null;     // one friendly line about earning more stars
}

export function evaluate(t: Tally, w: Windows, c: Conditions): Evaluation {
  let onTime = 0, offTime = 0, outside = 0, early = 0, late = 0;
  for (const d of t.deltasMs) {
    const a = Math.abs(d);
    if (a <= w.onTimeMs) onTime++;
    else {
      if (a <= w.earlyLateMs) offTime++; else outside++;
      if (d < 0) early++; else late++;
    }
  }
  const matched = t.deltasMs.length;
  const penalty = Math.min(EXTRA_PENALTY * t.extra, EXTRA_CAP * t.expected);
  const rawAccuracy = t.expected ? Math.max(0, (matched - penalty) / t.expected) : 0;
  const rawTiming = matched ? (onTime + 0.5 * offTime) / matched : null;
  const aids = practiceAids(c);
  const factor = aids.reduce((f, a) => f * a.factor, 1);
  const accuracy = rawAccuracy * factor;
  const timing = rawTiming === null ? null : rawTiming * factor;
  const showTiming = timing !== null && rawAccuracy >= TIMING_STARS_MIN_ACCURACY;
  // "mostly early (rushing) or late (dragging)": at least 3 notes off time, two thirds one way
  const off = early + late;
  const tendency = off >= 3 && early >= (2 / 3) * off ? "early" : off >= 3 && late >= (2 / 3) * off ? "late" : null;
  return {
    expected: t.expected, matched, missed: t.expected - matched, extra: t.extra,
    onTime, offTime, outside, rawAccuracy, rawTiming, factor, accuracy, timing,
    accuracyStars: stars(accuracy),
    timingStars: showTiming ? stars(timing!) : null,
    tendency, aids, hint: hint(aids),
  };
}

/** "Play the whole song at full speed with both hands to earn up to 5 stars!" */
function hint(aids: Aid[]): string | null {
  if (!aids.length) return null;
  const has = (id: string) => aids.some((a) => a.id === id);
  const parts = [
    has("section") ? "the whole song" : "",
    has("tempo") ? "at full speed" : "",
    has("hands") ? "with both hands" : "",
    has("rewinds") ? "without stopping" : "",
  ].filter(Boolean);
  if (!parts.length) return "Play it with the usual hints to earn up to 5 stars!";
  return `Play ${parts.join(" ")} to earn up to 5 stars!`;
}
