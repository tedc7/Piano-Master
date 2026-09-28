import { describe, expect, it } from "vitest";
import { Matcher } from "../src/lib/matcher";
import { RewindPolicy } from "../src/lib/rewind";
import { buildTimeline, phraseIndexAt } from "../src/lib/timeline";
import { FOUR_BARS } from "./fixtures";

const SPB = 0.5;

function setup() {
  const tl = buildTimeline(FOUR_BARS);
  const expected = tl.notes.map((x) => ({ id: x.id, pitch: x.pitch, beat: x.beat, phrase: x.phrase }));
  const m = new Matcher(expected, (b) => phraseIndexAt(tl.phrases, b));
  const p = new RewindPolicy(tl, m);
  p.beginPass(0);
  /** Play the expected notes from..to (beats), each on time, stepping the clock like frames. */
  const play = (from: number, to: number, skip: number[] = [], wrongAt: number[] = []) => {
    let plan = null;
    for (let b = from; b < to - 1e-9; b += 0.05) {
      const beat = Math.round(b * 100) / 100;
      for (const e of expected) {
        if (Math.abs(e.beat - beat) < 1e-6 && !skip.includes(e.beat)) { p.played(beat); m.noteOn(e.pitch, beat, 80, SPB, beat * 500); }
      }
      if (wrongAt.some((w) => Math.abs(w - beat) < 1e-6)) { p.played(beat); m.noteOn(59, beat, 80, SPB, beat * 500 + 1); }
      m.advance(beat, SPB);
      plan = plan ?? p.update(beat);
      if (plan) return { plan, at: beat };
    }
    return null;
  };
  return { tl, m, p, play };
}

describe("RewindPolicy", () => {
  it("does not rewind a clean run, or for timing alone", () => {
    expect(setup().play(0, 16.5)).toBeNull();
  });

  it("rewinds at the end of a phrase with 2 errors, to that phrase's start", () => {
    const r = setup().play(0, 16.1, [9], [10.5]);        // miss beat 9, wrong note at 10.5: phrase 1 (beats 8-16)
    expect(r?.plan).toMatchObject({ reason: "errors", phrase: 1, targetPhrase: 1, targetBeat: 8, atBeat: 16 });
    expect(r?.at).toBeCloseTo(16);
  });

  it("goes back one more phrase when the first error is on the phrase's first beat", () => {
    const r = setup().play(0, 16.1, [8, 9]);
    expect(r?.plan).toMatchObject({ phrase: 1, targetPhrase: 0, targetBeat: 0 });
  });

  it("one error in a phrase is not enough", () => {
    expect(setup().play(0, 16.5, [9])).toBeNull();
  });

  it("rewinds at the next bar line after 2 beats of silence while notes are expected", () => {
    const r = setup().play(0, 16, [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);   // stops after beat 4
    expect(r?.plan).toMatchObject({ reason: "lost", phrase: 0, targetBeat: 0, atBeat: 8 });
  });

  it("keeps going after 3 rewinds of the same phrase", () => {
    const { p, m, tl, play } = setup();
    p.beginPass(8);
    for (let i = 0; i < 3; i++) {
      const r = play(8, 16.1, [9], [10.5]);
      expect(r?.plan.phrase).toBe(1);
      m.resetFrom(8);
      p.beginPass(8);
    }
    expect(play(8, 16.5, [9], [10.5])).toBeNull();
    expect(p.rewinds[1]).toBe(3);
    expect(p.trickiest()).toBe(1);
    expect(tl.phrases).toHaveLength(2);
  });
});
