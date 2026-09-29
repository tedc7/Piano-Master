import { describe, expect, it } from "vitest";
import { Attempt } from "../src/lib/attempt";
import { buildTimeline } from "../src/lib/timeline";
import { FOUR_BARS } from "./fixtures";

const SPB = 0.5;

describe("Attempt results for Diagnostics (arch §8.8)", () => {
  it("pairs a wrong key with the written note it replaced, and lists every note's timing", () => {
    const tl = buildTimeline(FOUR_BARS);
    const a = new Attempt(tl, { hands: "both", handsWritten: "R", section: null, preset: "100" });
    a.beginPass(0, 0);
    for (const n of tl.notes) {
      const pitch = n.beat === 3 ? 69 : n.pitch;          // F4 (65) played as A4 at beat 3
      a.noteOn(pitch, n.beat + 0.1, 80, SPB, n.beat * 500);
      a.tick(n.beat + 0.2, SPB, false);
    }
    a.tick(20, SPB, false);
    const r = a.result(true);
    const wrong = r.noteErrors.find((e) => e.kind === "wrong")!;
    expect(wrong).toMatchObject({ pitch: 69, expected: 65, hand: "R" });
    expect(r.noteErrors.find((e) => e.kind === "missed")).toMatchObject({ pitch: 65, note: 3 });
    expect(r.noteResults).toHaveLength(16);
    expect(r.noteResults[3]).toEqual([3, null]);
    expect(r.noteResults[0]).toEqual([0, 50]);             // 0.1 beat late at 0.5 s a beat
  });

  it("leaves out notes an attempt stopped before", () => {
    const tl = buildTimeline(FOUR_BARS);
    const a = new Attempt(tl, { hands: "both", handsWritten: "R", section: null, preset: "100" });
    a.beginPass(0, 0);
    for (const n of tl.notes.slice(0, 4)) a.noteOn(n.pitch, n.beat, 80, SPB, n.beat * 500);
    expect(a.result(false).noteResults.map(([i]) => i)).toEqual([0, 1, 2, 3]);
  });
});
