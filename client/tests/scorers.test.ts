// The later scorers (arch §7.7, v0.50): held notes from Level 3, and loud and soft, replayed
// through the same Attempt the Play screen uses.
import { describe, expect, it } from "vitest";
import { replay, type ReplayNote } from "../src/lib/replay";
import { dynamics, dynamicsMargin, scorersFor, type PlayedNote } from "../src/lib/scorers";
import { buildTimeline } from "../src/lib/timeline";
import { FOUR_BARS, piece } from "./fixtures";

const TEMPO = 60;                         // a beat a second at 100%

function perfect(tl: ReturnType<typeof buildTimeline>, held = 0.9, velocity = (_: number) => 80): ReplayNote[] {
  return tl.notes.map((n) => ({ beat: n.beat, pitch: n.pitch, velocity: velocity(n.beat), durMs: n.duration * 1000 * held }));
}

describe("which scorers a play runs", () => {
  it("runs none of them at Prep A, with the microphone, or for a skill that doesn't ask", () => {
    expect(scorersFor("Prep A", "midi", true)).toEqual([]);
    expect(scorersFor("Level 3", "mic", true)).toEqual([]);
    expect(scorersFor("Level 3", "midi", true)).toEqual(["held", "dynamics"]);
    expect(scorersFor("Level 3", "midi", false)).toEqual(["held"]);           // keys without touch: no dynamics
    expect(scorersFor("Prep A", "midi", null, ["dynamics"])).toEqual(["dynamics"]);
  });
  it("takes the margin a change must show from the keyboard's measured range", () => {
    expect(dynamicsMargin(null, null)).toBe(12);
    expect(dynamicsMargin(30, 110)).toBe(16);
    expect(dynamicsMargin(60, 70)).toBe(6);
  });
});

describe("held notes (§7.2)", () => {
  const tl = buildTimeline(FOUR_BARS);
  const opts = { hands: "both" as const, handsWritten: "R" as const, section: null, preset: "100" as const, level: "Level 3" };

  it("costs nothing when every note is held long enough", () => {
    const r = replay(tl, TEMPO, { ...opts, scorers: ["held"] }, [perfect(tl, 0.9)]).result;
    expect(r.evaluation.short).toBe(0);
    expect(r.evaluation.rawAccuracy).toBe(1);
    expect(r.noteResults[0]).toEqual([0, 0, 0.9, 80]);
  });
  it("gives a note let go before half its length 0.75 credit", () => {
    const notes = perfect(tl, 0.9).map((n, i) => (i < 4 ? { ...n, durMs: 300 } : n));   // four notes held 0.3 of a beat
    const r = replay(tl, TEMPO, { ...opts, scorers: ["held"] }, [notes]).result;
    expect(r.evaluation.short).toBe(4);
    expect(r.evaluation.rawAccuracy).toBeCloseTo((16 - 4 * 0.25) / 16);
    expect(r.evaluation.scorers[0]).toMatchObject({ id: "notes", detail: "4 notes let go early" });
  });
  it("changes nothing below Level 3 (the scorer isn't run)", () => {
    const notes = perfect(tl, 0.2);
    const r = replay(tl, TEMPO, { ...opts, level: "Prep A" }, [notes]).result;
    expect(r.evaluation.rawAccuracy).toBe(1);
    expect(r.evaluation.scorers.map((s) => s.id)).toEqual(["notes", "timing"]);
  });
});

describe("loud and soft", () => {
  // 4 bars: the first two forte (velocity 100 in the notation), the last two piano (50)
  const quarters = [60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 62, 64, 64, 60, 60].map((p) => [p, 1] as [number, number]);
  const tl = buildTimeline(piece(quarters, 2, quarters.map((_, i) => ({ velocity: i < 8 ? 100 : 50 }))));
  const opts = { hands: "both" as const, handsWritten: "R" as const, section: null, preset: "100" as const, level: "Level 3",
                 scorers: ["dynamics" as const] };

  it("scores a clear change the right way as 5 stars, with its own row", () => {
    const r = replay(tl, TEMPO, opts, [perfect(tl, 0.9, (b) => (b < 8 ? 95 : 60))]).result;
    const row = r.evaluation.scorers.find((s) => s.id === "dynamics")!;
    expect(row).toMatchObject({ label: "Loud and soft", score: 1, stars: 5, detail: "1 of 1 change heard", advice: null });
  });
  it("gives part credit for a change too small, and says which way to go", () => {
    const r = replay(tl, TEMPO, opts, [perfect(tl, 0.9, (b) => (b < 8 ? 80 : 74))]).result;
    const row = r.evaluation.scorers.find((s) => s.id === "dynamics")!;
    expect(row.score).toBeCloseTo(0.5);
    expect(row.advice).toBe("Make the soft parts softer.");
  });
  it("scores 0 when the change goes the wrong way", () => {
    const r = replay(tl, TEMPO, opts, [perfect(tl, 0.9, (b) => (b < 8 ? 60 : 90))]).result;
    expect(r.evaluation.scorers.find((s) => s.id === "dynamics")!.score).toBe(0);
  });
  it("judges nothing without a change of mark, or with too few notes under one", () => {
    const one: PlayedNote[] = Array.from({ length: 8 }, (_, i) => ({ id: i, beat: i, length: 1, hit: i, release: i + 0.9, velocity: 80, written: 100 }));
    expect(dynamics(one).score).toBeNull();
    const two = one.map((n, i) => ({ ...n, written: i < 6 ? 100 : 50 }));   // only two notes under the piano
    expect(dynamics(two).score).toBeNull();
    const plain = replay(buildTimeline(FOUR_BARS), TEMPO, opts, [perfect(buildTimeline(FOUR_BARS))]).result;
    expect(plain.evaluation.scorers.map((s) => s.id)).toEqual(["notes", "timing"]);
  });
});
