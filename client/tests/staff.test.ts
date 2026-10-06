import { describe, expect, it } from "vitest";
import { beatAt, xAt } from "../src/lib/staff";

describe("Dragging the staff (v0.33)", () => {
  const map: [number, number][] = [[0, 100], [1, 160], [1.5, 175], [4, 300], [8, 520]];

  it("finds the beat at a staff position: xAt the other way round", () => {
    for (const b of [-2, -0.5, 0, 0.3, 1, 1.2, 2.75, 4, 6.1, 8]) expect(beatAt(map, xAt(map, b))).toBeCloseTo(b, 6);
  });

  it("stops at the end of the piece", () => {
    expect(beatAt(map, 900)).toBe(8);
  });
});
