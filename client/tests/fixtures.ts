import type { Notation, Note } from "../src/lib/types";

const STEPS = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"];

/** A 4/4 right-hand piece from (pitch, beats) pairs, bars of 4 beats, phrases every `phraseBars`. */
export function piece(notes: [number, number][], phraseBars = 2, extra: Partial<Note>[] = []): Notation {
  let t = 0;
  const ns: Note[] = notes.map(([pitch, d], i) => {
    const n: Note = {
      pitch, duration: d, start: t, staff: 0, hand: "R", voice: 1, isMelody: true,
      spelled: { step: STEPS[pitch % 12], alter: [1, 3, 6, 8, 10].includes(pitch % 12) ? 1 : 0, octave: Math.floor(pitch / 12) - 1 },
      ...(extra[i] ?? {}),
    };
    t += d;
    return n;
  });
  const bars = Math.ceil(t / 4);
  const phrases: number[] = [];
  for (let b = 0; b < bars; b += phraseBars) phrases.push(b * 4);
  return {
    header: { keySig: 0, timeSig: "4/4", barLength: 4, tempo: 60, pickupBeats: 0, range: [60, 72], staves: ["treble"] },
    measures: Array.from({ length: bars }, (_, i) => ({ number: i + 1, start: i * 4, duration: 4 })),
    notes: ns,
    lyrics: [],
    chordSymbols: [],
    playbackOrder: Array.from({ length: bars }, (_, i) => ({ measure: i, verse: 1 })),
    phrases,
    length: bars * 4,
  };
}

/** 4 bars of quarter notes C D E F | G A G F | E D C D | E E C C: phrases at 0 and 8. */
export const FOUR_BARS = piece([60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 62, 64, 64, 60, 60].map((p) => [p, 1] as [number, number]));
