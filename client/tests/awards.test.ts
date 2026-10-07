import { describe, expect, it } from "vitest";
import { groupHeadline, starText, topStep, type Award, type Series } from "../src/lib/awards";

describe("rewards (M10)", () => {
  it("writes stars in half steps", () => {
    expect([0, 0.5, 3, 4.5, 312.5].map(starText)).toEqual(["0", "½", "3", "4½", "312½"]);
  });

  it("names unit and level medals", () => {
    const a = (kind: Award["kind"], detail: string): Award => ({ id: "x", kind, tier: "bronze", title: "t", detail, date: "" });
    expect(groupHeadline(a("unit", "Complete"))).toBe("Unit complete");
    expect(groupHeadline(a("level", "All mastered"))).toBe("Level: all mastered");
  });

  it("finds the highest medal earned in a row of steps", () => {
    const s: Series = { kind: "streak", name: "Practice streak", value: 9, next: null, steps: [
      { at: 3, tier: "bronze", label: "3", earned: { date: "", new: false } },
      { at: 7, tier: "bronze", label: "7", earned: { date: "", new: true } },
      { at: 14, tier: "silver", label: "14", earned: null }] };
    expect(topStep(s)?.at).toBe(7);
    expect(topStep({ ...s, steps: s.steps.map((x) => ({ ...x, earned: null })) })).toBeNull();
  });
});
