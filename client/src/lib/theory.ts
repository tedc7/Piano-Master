// Theory and ear-training scoring (arch §7.8), for the concept lessons' Check and Echo cards.
//  - A question: right on the first try 1 point, on the second 0.5, otherwise 0.
//  - Echo (ear training, play back): the app plays a 2 to 8 note phrase; the student plays it
//    back. Accuracy = 1 − (note edit distance ÷ phrase length); each replay of the phrase before
//    playing multiplies it by 0.9 (up to 2 replays). Rhythm is not scored until Level 3.

export const REPLAY_FACTOR = 0.9;
export const MAX_REPLAYS = 2;

export function questionPoints(wrongTries: number): number {
  return wrongTries === 0 ? 1 : wrongTries === 1 ? 0.5 : 0;
}

/** Levenshtein distance between two note sequences. */
export function editDistance(a: number[], b: number[]): number {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}

export function echoScore(expected: number[], played: number[], replays: number): number {
  if (!expected.length) return 0;
  const acc = Math.max(0, 1 - editDistance(expected, played) / expected.length);
  return acc * Math.pow(REPLAY_FACTOR, Math.min(replays, MAX_REPLAYS));
}

/** Stars from a score (§7.6), as the Play screen gives them. */
export { stars } from "./scoring";
