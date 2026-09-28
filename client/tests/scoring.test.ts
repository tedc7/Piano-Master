import { describe, expect, it } from "vitest";
import { evaluate, levelBand, practiceAids, stars, WINDOWS_BY_BAND, type Conditions } from "../src/lib/scoring";

const W = WINDOWS_BY_BAND.prep;
const NORMAL: Conditions = { mode: "play", tempoPreset: "100", hands: "both", handsWritten: "RL", sectionOnly: false, extraHints: false, rewinds: 0 };

describe("stars (§7.6)", () => {
  it("follows the table, in half-star steps", () => {
    expect([0.2, 0.4, 0.5, 0.6, 0.67, 0.74, 0.8, 0.86, 0.91, 0.96, 1].map(stars)).toEqual([0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5]);
    expect(stars(0.739)).toBe(2.5);
  });
});

describe("the worked example (§7.9)", () => {
  // 40 notes: 36 matched (30 on time, 5 late, 1 outside the early/late window), 4 missed, 3 extra
  const deltas = [...Array(30).fill(20), ...Array(5).fill(200), 350];
  const tally = { expected: 40, deltasMs: deltas, extra: 3 };

  it("scores 88.1% accuracy and 90.3% timing: 4 stars each", () => {
    const e = evaluate(tally, WINDOWS_BY_BAND.prep, NORMAL);
    expect(e.accuracy).toBeCloseTo(35.25 / 40, 4);
    expect(e.timing!).toBeCloseTo(32.5 / 36, 4);
    expect([e.accuracyStars, e.timingStars]).toEqual([4, 4]);
    expect(e.aids).toEqual([]);
    expect(e.hint).toBeNull();
  });

  it("gives 3 stars at 75% tempo, and 2 at 75% with one hand", () => {
    const slow = evaluate(tally, W, { ...NORMAL, tempoPreset: "75" });
    expect(slow.accuracy).toBeCloseTo(0.758, 3);
    expect(slow.accuracyStars).toBe(3);
    expect(slow.hint).toBe("Play at full speed to earn up to 5 stars!");
    const oneHand = evaluate(tally, W, { ...NORMAL, tempoPreset: "75", hands: "R" });
    expect(oneHand.accuracy).toBeCloseTo(0.644, 3);
    expect(oneHand.accuracyStars).toBe(2);
    expect(oneHand.hint).toBe("Play at full speed with both hands to earn up to 5 stars!");
  });
});

describe("practice aids (§7.5)", () => {
  it("multiply, and cap what each aid alone can reach", () => {
    const f = (c: Partial<Conditions>) => practiceAids({ ...NORMAL, ...c }).reduce((x, a) => x * a.factor, 1);
    expect(stars(f({ tempoPreset: "90" }))).toBe(4.5);
    expect(stars(f({ tempoPreset: "50" }))).toBe(3);
    expect(stars(f({ rewinds: 1 }))).toBe(4.5);
    expect(stars(f({ rewinds: 2 }))).toBe(4);
    expect(stars(f({ rewinds: 5 }))).toBe(3.5);
    expect(stars(f({ hands: "L" }))).toBe(3.5);
    expect(stars(f({ sectionOnly: true }))).toBe(4);
    expect(stars(f({ tempoPreset: "50", hands: "R" }))).toBeLessThan(3);   // stacked aids cannot pass
    expect(practiceAids({ ...NORMAL, handsWritten: "R", hands: "R" })).toEqual([]);   // a one-hand piece
  });
});

describe("timing details (§7.4)", () => {
  it("hides timing stars below 50% accuracy and names rushing or dragging", () => {
    const few = evaluate({ expected: 20, deltasMs: [0, 0, 0, 0, 0], extra: 0 }, W, NORMAL);
    expect(few.timingStars).toBeNull();
    const rushed = evaluate({ expected: 10, deltasMs: [-200, -220, -180, -250, 0, 0, 0, 0, 0, 0], extra: 0 }, W, NORMAL);
    expect(rushed.tendency).toBe("early");
    const dragging = evaluate({ expected: 10, deltasMs: [200, 220, 180, 0, 0, 0, 0, 0, 0, 0], extra: 0 }, W, NORMAL);
    expect(dragging.tendency).toBe("late");
  });

  it("caps the extra-note penalty at 10% of the expected notes", () => {
    const flurry = evaluate({ expected: 20, deltasMs: Array(20).fill(0), extra: 30 }, W, NORMAL);
    expect(flurry.accuracy).toBeCloseTo(0.9);
  });

  it("maps levels to timing-window bands", () => {
    expect(["Prep A", "Prep B", "Level 1", "Level 4", "Level 8", undefined].map(levelBand)).toEqual(["prep", "prep", "1-2", "3-4", "5+", "prep"]);
  });
});
