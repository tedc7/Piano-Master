import { describe, expect, it } from "vitest";
import { Matcher, PREP_WINDOWS } from "../src/lib/matcher";
import { buildTimeline, phraseIndexAt } from "../src/lib/timeline";
import { FOUR_BARS, piece } from "./fixtures";

const SPB = 0.5;   // 120 bpm: 1 beat = 500 ms

function matcherFor(n = FOUR_BARS) {
  const tl = buildTimeline(n);
  const expected = tl.notes.filter((x) => !x.tieContinuation).map((x) => ({ id: x.id, pitch: x.pitch, beat: x.beat, phrase: x.phrase }));
  return { tl, m: new Matcher(expected, (b) => phraseIndexAt(tl.phrases, b)) };
}

describe("Matcher", () => {
  it("matches the nearest expected note of the same pitch and grades on-time vs late", () => {
    const { m } = matcherFor();
    const a = m.noteOn(60, 0.1, 80, SPB, 1000);            // 50 ms late
    expect(a).toEqual({ kind: "hit", noteId: 0, deltaMs: expect.closeTo(50, 6), onTime: true });
    const b = m.noteOn(62, 1.4, 80, SPB, 1700);            // 200 ms late: matched, off time
    expect(b.kind).toBe("hit");
    expect(b.kind === "hit" && b.onTime).toBe(false);
  });

  it("counts a note outside the match window, or of the wrong pitch, as wrong", () => {
    const { m } = matcherFor();
    expect(m.noteOn(60, 1.0, 80, SPB, 1000).kind).toBe("wrong");   // 500 ms after C: beyond 450 ms
    expect(m.noteOn(61, 0, 80, SPB, 1000).kind).toBe("wrong");
    expect(m.summary().wrong).toBe(2);
  });

  it("caps the window at half the gap to the next note of the same pitch", () => {
    // E E at beats 12 and 13 in FOUR_BARS; at 60 bpm the 450 ms window would reach the next E
    const { tl, m } = matcherFor();
    const e1 = tl.notes.find((x) => x.beat === 12)!;
    expect(m.windowBeats(m.expected[e1.id], 1.0)).toBeCloseTo(0.45);
    const slow = matcherFor(piece([[64, 0.5], [64, 0.5], [60, 3]])).m;
    expect(slow.windowBeats(slow.expected[0], 1.0)).toBeCloseTo(0.25);   // half of 0.5 beats
    const hit = slow.noteOn(64, 0.4, 80, 1.0, 1000);                    // closer to the 2nd E
    expect(hit.kind === "hit" && hit.noteId).toBe(1);
  });

  it("ignores brushes and re-strikes, and retracts a wrong note released within 40 ms", () => {
    const { m } = matcherFor();
    expect(m.noteOn(61, 0, 10, SPB, 1000)).toEqual({ kind: "ignored", reason: "brush" });
    m.noteOn(60, 0, 80, SPB, 1000);
    expect(m.noteOn(60, 0.2, 80, SPB, 1100)).toEqual({ kind: "ignored", reason: "restrike" });
    m.noteOn(70, 0.5, 80, SPB, 2000);
    m.noteOff(70, 2030);
    expect(m.summary().wrong).toBe(0);
  });

  it("marks missed notes once their window closes, and counts phrase errors", () => {
    const { m } = matcherFor();
    expect(m.advance(0.5, SPB)).toEqual([]);      // C's window (0.9 beats at 120 bpm) still open
    expect(m.advance(1.0, SPB)).toEqual([0]);
    m.noteOn(70, 1.5, 80, SPB, 2000);             // a wrong note in phrase 0
    expect(m.phraseErrors(0)).toEqual({ count: 2, firstBeat: 0 });
    expect(m.phraseErrors(1).count).toBe(0);
  });

  it("resets the replayed part on a new pass: only the last pass counts", () => {
    const { m } = matcherFor();
    m.advance(9, SPB);
    expect(m.missed.size).toBeGreaterThan(8);
    m.resetFrom(8);
    expect([...m.missed].every((id) => m.expected[id].beat < 8)).toBe(true);
    expect(m.noteOn(64, 8, 80, SPB, 5000).kind).toBe("hit");
  });

  it("uses the Prep windows by default", () => {
    expect(matcherFor().m.windows).toBe(PREP_WINDOWS);
  });
});
