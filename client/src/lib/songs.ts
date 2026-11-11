// Each song's progress (arch §8.12, v0.50), as the server keeps it: its stage and the facts its
// next step comes from. The words the student sees are here, so every screen says it the same way.

export type SongStage = "new" | "hands-apart" | "learning" | "slow" | "learned" | "solid" | "excellent";
export const STAGES: SongStage[] = ["new", "hands-apart", "learning", "slow", "learned", "solid", "excellent"];

export interface SongState {
  stage: SongStage;
  best: number | null;             // the song's stars in the collection
  fullStars: number | null;        // the best as written at 100%
  tempoReached: "50" | "75" | "90" | "100" | null;   // the fastest preset played as written with 3 stars or more
  handsDone: string[];             // "R", "L", "both": played to the end with
  hands: "R" | "L" | "RL" | null;
  plays: number;
  lastPlayed: string | null;
  learned: string | null;          // the day it was first learned
}

const NEXT_PRESET: Record<string, string> = { "50": "75", "75": "90", "90": "100" };

/** A short name for the stage, for a chip beside the song; null for a song not played yet. */
export function stageLabel(s: SongState | undefined): string | null {
  if (!s) return null;
  switch (s.stage) {
    case "new": return null;
    case "hands-apart": return "Hands apart";
    case "learning": return "Learning";
    case "slow": return `Learned at ${s.tempoReached}%`;
    case "learned": return "Learned";
    case "solid": return "Solid";
    case "excellent": return "Excellent";
  }
}

/** What to aim for next, in a few words: "Right hand done: left hand next", "Learned at 75%: try 90%". */
export function nextStep(s: SongState | undefined): string | null {
  if (!s) return null;
  const done = new Set(s.handsDone);
  switch (s.stage) {
    case "new": return null;
    case "hands-apart":
      if (done.has("R") && done.has("L")) return "Both hands apart: now together";
      return done.has("R") ? "Right hand done: left hand next" : "Left hand done: right hand next";
    case "learning": return "3 stars with all its notes learns it";
    case "slow": return `Try ${NEXT_PRESET[s.tempoReached ?? "50"] ?? "100"}% next`;
    case "learned": return "4 stars at full speed makes it solid";
    case "solid": return "5 stars makes it excellent";
    case "excellent": return null;
  }
}

/** What a song's card says of its progress: only what its stars can't (v0.50, after the family's
 *  first look). A song's best stars already say Learned, Solid and Excellent: the practice-aid factor
 *  caps a slower play (at most 3 stars at 50%, 4 at 75%), so high stars mean full speed. The stars
 *  don't say that a song for both hands has been played one hand at a time (those plays aren't in
 *  the star collection), or that it was learned at a slower tempo: "Learned at 75% · Try 90% next". */
export function songNote(s: SongState | undefined): string | null {
  if (!s) return null;
  if (s.stage === "hands-apart") return nextStep(s);
  if (s.stage === "slow") return `${stageLabel(s)} · ${nextStep(s)}`;
  return null;
}

/** The furthest of several versions of a song (the library shows a song by the version furthest along). */
export function furthest(xs: (SongState | undefined)[]): SongState | undefined {
  let best: SongState | undefined;
  for (const x of xs) if (x && (!best || STAGES.indexOf(x.stage) > STAGES.indexOf(best.stage))) best = x;
  return best;
}

/** The words for a stage reached on the result card ("You learned this song!"), or null. */
export function stageMoment(stage: SongStage): string | null {
  switch (stage) {
    case "learned": return "Song learned: you can play it!";
    case "slow": return "Learned it slowly: now a little faster";
    default: return null;
  }
}
