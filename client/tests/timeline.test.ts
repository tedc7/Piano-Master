import { describe, expect, it } from "vitest";
import { keyboardRange, noteName } from "../src/lib/keyboard";
import { choosePort, decode, isVirtualPort } from "../src/lib/midi";
import { beatUnit, buildTimeline, nextBarLine, nextOnset } from "../src/lib/timeline";
import { FOUR_BARS, piece } from "./fixtures";

describe("timeline", () => {
  it("lays notes out in playback order with phrases and bar lines", () => {
    const tl = buildTimeline(FOUR_BARS);
    expect(tl.length).toBe(16);
    expect(tl.phrases.map((p) => [p.start, p.end, p.noteIds.length])).toEqual([[0, 8, 8], [8, 16, 8]]);
    expect(tl.barLines).toEqual([0, 4, 8, 12, 16]);
    expect(nextBarLine(tl, 5.2)).toBe(8);
  });

  it("unrolls repeats and gives each pass its verse's words", () => {
    const n = piece([[60, 4], [62, 4]]);
    n.playbackOrder = [{ measure: 0, verse: 1 }, { measure: 1, verse: 1 }, { measure: 0, verse: 2 }, { measure: 1, verse: 2 }];
    n.lyrics = [{ note: 0, verse: 1, text: "one", syllabic: "single" }, { note: 0, verse: 2, text: "two", syllabic: "single" }];
    const tl = buildTimeline(n);
    expect(tl.notes.map((x) => [x.beat, x.lyric?.text ?? null])).toEqual([[0, "one"], [4, null], [8, "two"], [12, null]]);
  });

  it("marks tied continuations so they are not expected again", () => {
    const tl = buildTimeline(piece([[60, 2], [60, 2], [62, 4]], 2, [{ tieToNext: true }]));
    expect(tl.notes.map((x) => x.tieContinuation)).toEqual([false, true, false]);
    expect(tl.phrases[0].noteIds).toEqual([0, 2]);
    expect(nextOnset(tl, 1).map((x) => x.pitch)).toEqual([62]);
  });

  it("counts dotted quarters in 6/8", () => {
    expect(beatUnit("6/8")).toBe(1.5);
    expect(beatUnit("3/4")).toBe(1);
  });
});

describe("keyboard", () => {
  it("shows whole octaves, at least two, around the range", () => {
    expect(keyboardRange(60, 67)).toEqual([48, 71]);      // C position: C3..B4
    expect(keyboardRange(48, 67)).toEqual([48, 71]);
    expect(keyboardRange(62, 74)).toEqual([60, 83]);
  });
  it("names notes with sharps or flats", () => {
    expect(noteName(61)).toBe("C♯");
    expect(noteName(70, true)).toBe("B♭");
  });
});

describe("MIDI input", () => {
  it("skips virtual ports and prefers the saved piano", () => {
    const names = ["MIDIWeb Out / 5of12", "Network Session 1", "Roland Digital Piano"];
    expect(names.map(isVirtualPort)).toEqual([true, true, false]);
    expect(choosePort(names, null)).toBe("Roland Digital Piano");
    expect(choosePort(["MIDIWeb Out / 5of12", "Network Session 1"], null)).toBeNull();
    expect(choosePort(names, "Network Session 1")).toBe("Network Session 1");
  });
  it("decodes note on, note off (including velocity 0) and the sustain pedal", () => {
    expect(decode(new Uint8Array([0x90, 60, 100]), 5, 1)).toMatchObject({ type: "on", pitch: 60, velocity: 100 });
    expect(decode(new Uint8Array([0x90, 60, 0]), 5, 1)).toMatchObject({ type: "off", pitch: 60 });
    expect(decode(new Uint8Array([0x81, 60, 64]), 5, 1)).toMatchObject({ type: "off" });
    expect(decode(new Uint8Array([0xb0, 64, 127]), 5, 1)).toEqual({ type: "pedal", value: 127, timeMs: 5 });
    expect(decode(new Uint8Array([0xfe]), 5, 1)).toBeNull();
  });
});
