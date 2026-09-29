import { describe, expect, it } from "vitest";
import { calibrate } from "../src/lib/calibrate";

describe("tap-along calibration (arch §2.6.1)", () => {
  it("averages tap minus click and measures the spread", () => {
    const taps = Array.from({ length: 24 }, (_, i) => 40 + (i % 2 ? 5 : -5));
    const c = calibrate(taps);
    expect(c.ok && c.steady).toBe(true);
    expect(c.offsetMs).toBe(40);
    expect(c.spreadMs).toBe(5);
  });

  it("leaves out stray taps and counts missed clicks", () => {
    const taps: (number | null)[] = Array.from({ length: 24 }, () => 30);
    taps[3] = 250;           // a slip
    taps[7] = null;
    const c = calibrate(taps);
    expect(c.outliers).toEqual([3]);
    expect(c.missed).toBe(1);
    expect(c.used).toBe(22);
    expect(c.offsetMs).toBe(30);
  });

  it("needs 16 steady taps, and flags an unsteady setup", () => {
    expect(calibrate(Array.from({ length: 24 }, (_, i) => (i < 10 ? 20 : null))).ok).toBe(false);
    const wobbly = calibrate(Array.from({ length: 24 }, (_, i) => 50 + (i % 2 ? 35 : -35)));
    expect(wobbly.ok).toBe(true);
    expect(wobbly.steady).toBe(false);
  });
});
