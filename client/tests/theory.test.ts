import { describe, expect, it } from "vitest";
import { echoScore, editDistance, questionPoints } from "../src/lib/theory";

describe("theory and ear-training scoring (arch §7.8)", () => {
  it("gives a question 1 point first time, half the second, then none", () => {
    expect([0, 1, 2, 5].map(questionPoints)).toEqual([1, 0.5, 0, 0]);
  });

  it("scores a play-back by edit distance, less 10% for each replay (at most two)", () => {
    expect(editDistance([60, 62, 64], [60, 64])).toBe(1);
    expect(editDistance([60, 62, 64], [60, 62, 64])).toBe(0);
    expect(echoScore([60, 62, 64, 65], [60, 62, 64, 65], 0)).toBe(1);
    expect(echoScore([60, 62, 64, 65], [60, 62, 65, 65], 0)).toBe(0.75);
    expect(echoScore([60, 62, 64, 65], [60, 62, 64, 65], 1)).toBeCloseTo(0.9);
    expect(echoScore([60, 62, 64, 65], [60, 62, 64, 65], 5)).toBeCloseTo(0.81);
    expect(echoScore([60, 62], [67, 69, 71, 72], 0)).toBe(0);
  });
});
