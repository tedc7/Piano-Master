// The later scorers (arch §7.7, v0.50). Each takes the played notes of an attempt (every matched
// written note, with when its key went down and came up and how hard it was pressed) and gives
// what it found; scoring.ts turns the results into star rows beside notes and timing.
//
//  - held notes (§7.2): from Level 3, a note let go before half its written length earns 0.75
//    credit. Part of the notes score, not a row of its own.
//  - dynamics: loud and soft judged against each other within the play, never against fixed
//    numbers: where the written dynamic mark changes, the notes after it must be louder or softer
//    than the notes before it by a clear margin. Its own star row ("Loud and soft").
// Both need MIDI: the microphone input hears no key coming up and only guesses at loudness (§4).
// Articulation and pedal (§7.7 steps 5 and 6) wait for staccato, slur and pedal marks in the
// notation, which the song import doesn't carry yet.
import { levelBand } from "./scoring";

export type ScorerId = "notes" | "timing" | "held" | "dynamics";

/** One matched written note, as played. */
export interface PlayedNote {
  id: number;             // the timeline note
  beat: number;           // its written beat
  length: number;         // its written length in beats (a tied note: the whole tied length)
  hit: number;            // the beat its key went down (latency-corrected)
  release: number | null; // the beat its key came up, or null if still down when the attempt ended
  velocity: number;       // how hard it was pressed (MIDI 1..127)
  written: number | null; // the velocity of its dynamic mark (§5 dynamics; 100 is forte), if any
}

/** What a scorer gives back: one star row, before the practice-aid factor. */
export interface ScorerRow {
  id: ScorerId;
  label: string;          // "Notes", "Timing", "Loud and soft"
  score: number | null;   // 0..1, before the practice-aid factor; null when there was nothing to score
  stars: number | null;   // after the factor
  detail?: string;        // "3 of 4 changes heard"
  advice?: string | null; // one friendly line
}

const ADVANCED = new Set(["3-4", "5+"]);

/** Which of the later scorers this play runs: the level must have reached it (§6.4: from Level 3)
 *  or the skill being learned must ask for it (`passNeeds`), and the setup must support it. */
export function scorersFor(level: string | undefined, input: "midi" | "mic", velocitySensitive: boolean | null,
                           needs: string[] = []): ScorerId[] {
  if (input !== "midi") return [];
  const band = ADVANCED.has(levelBand(level));
  const out: ScorerId[] = [];
  if (band) out.push("held");
  if (velocitySensitive !== false && (band || needs.includes("dynamics"))) out.push("dynamics");
  return out;
}

/** Notes let go before half their written length (§7.2). A key still down at the end was held. */
export function heldShort(notes: PlayedNote[]): { checked: number; short: number; ids: number[] } {
  const ids = notes.filter((n) => n.release !== null && n.length > 0 && (n.release - n.hit) < 0.5 * n.length).map((n) => n.id);
  return { checked: notes.length, short: ids.length, ids };
}

export const DYNAMICS_MIN_NOTES = 3;      // notes under each of two marks, to judge the change between them
export const DYNAMICS_MARGIN = 12;        // velocity steps a change must show, before the piano check measures the keyboard

/** The margin a change must show on this keyboard: a fifth of the range between a soft and a loud
 *  press measured in the piano check, between 6 and 20; 12 until measured. */
export function dynamicsMargin(soft: number | null | undefined, loud: number | null | undefined): number {
  if (soft == null || loud == null || loud <= soft) return DYNAMICS_MARGIN;
  return Math.max(6, Math.min(20, 0.2 * (loud - soft)));
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Loud and soft: at each change of written dynamic mark (in playback order) with enough notes on
 *  both sides, credit for how far the played loudness moved the right way, up to the margin. The
 *  score is the mean credit; null when the piece has no change to judge in what was played. */
export function dynamics(notes: PlayedNote[], margin = DYNAMICS_MARGIN): {
  score: number | null; changes: number; heard: number; louder: boolean | null;
} {
  const marked = [...notes].filter((n) => n.written !== null).sort((a, b) => a.beat - b.beat);
  const runs: { written: number; v: number[] }[] = [];
  for (const n of marked) {
    if (!runs.length || runs[runs.length - 1].written !== n.written) runs.push({ written: n.written!, v: [] });
    runs[runs.length - 1].v.push(n.velocity);
  }
  let total = 0, changes = 0, heard = 0;
  let worst: { credit: number; louder: boolean } | null = null;
  for (let i = 1; i < runs.length; i++) {
    const a = runs[i - 1], b = runs[i];
    if (a.v.length < DYNAMICS_MIN_NOTES || b.v.length < DYNAMICS_MIN_NOTES) continue;
    const up = b.written > a.written;
    const moved = (median(b.v) - median(a.v)) * (up ? 1 : -1);
    const credit = Math.max(0, Math.min(1, moved / margin));
    total += credit;
    changes++;
    if (credit >= 1) heard++;
    if (!worst || credit < worst.credit) worst = { credit, louder: up };
  }
  return { score: changes ? total / changes : null, changes, heard, louder: worst && worst.credit < 1 ? worst.louder : null };
}
