// When the Play screen rewinds, and to where (arch §3, "Play and smooth rewind"; first version,
// tuned with the children in M1):
//  - too many errors: missed plus wrong notes in a phrase reach 2 or 25% of its notes, whichever
//    is larger; the rewind starts at the end of that phrase. Timing alone never triggers one.
//  - lost place: no notes played for 2 beats while notes are expected; the rewind starts at the
//    next bar line.
//  - it goes back to the start of the phrase with the errors, or one more phrase for a run-up
//    when the first error was on that phrase's first beat.
//  - after 3 rewinds of the same phrase in one attempt the music keeps going.
import type { Matcher } from "./matcher";
import { nextBarLine, phraseIndexAt, type Timeline } from "./timeline";

export interface RewindRules {
  minErrors: number;
  errorFraction: number;
  lostBeats: number;
  maxPerPhrase: number;
}

export const REWIND_RULES: RewindRules = { minErrors: 2, errorFraction: 0.25, lostBeats: 2, maxPerPhrase: 3 };

export interface RewindPlan {
  reason: "errors" | "lost";
  phrase: number;        // the phrase with the errors (counts toward its limit)
  targetPhrase: number;  // where it goes back to
  targetBeat: number;
  atBeat: number;        // start the rewind when the song reaches this beat
}

/** The part of the piece being played: the whole piece, or a section loop. In a loop the
 *  rewind never goes before the section start, and the loop itself handles the section end. */
export interface PlayRange { start: number; end: number; loop: boolean }

export class RewindPolicy {
  readonly rewinds: number[];
  private passStart = 0;
  private lastPlayed = -Infinity;
  private checkedTo = -1;       // phrases up to this index have had their end-of-phrase check
  private pending: RewindPlan | null = null;

  constructor(private tl: Timeline, private matcher: Matcher, readonly rules: RewindRules = REWIND_RULES,
              private range: PlayRange = { start: 0, end: tl.length, loop: false }) {
    this.rewinds = tl.phrases.map(() => 0);
  }

  /** A pass starts at `beat` (the start, or a rewind target). */
  beginPass(beat: number): void {
    this.passStart = beat;
    this.lastPlayed = -Infinity;
    this.pending = null;
    this.checkedTo = phraseIndexAt(this.tl.phrases, beat) - 1;
  }

  played(beat: number): void {
    this.lastPlayed = Math.max(this.lastPlayed, beat);
  }

  /** Call every frame with the current (scoring) beat; returns a plan once its time has come. */
  update(beat: number): RewindPlan | null {
    if (!this.pending) this.pending = this.errorsPlan(beat) ?? this.lostPlan(beat);
    if (this.pending && beat >= this.pending.atBeat - 1e-6) {
      const plan = this.pending;
      this.pending = null;
      this.rewinds[plan.phrase]++;
      return plan;
    }
    return null;
  }

  threshold(phrase: number): number {
    const n = this.tl.phrases[phrase].noteIds.length;
    return Math.max(this.rules.minErrors, this.rules.errorFraction * n);
  }

  /** The phrase with the most rewinds this attempt: the result screen's tricky spot. */
  trickiest(): number | null {
    let best: number | null = null;
    this.rewinds.forEach((n, i) => { if (n > 0 && (best === null || n > this.rewinds[best])) best = i; });
    return best;
  }

  private errorsPlan(beat: number): RewindPlan | null {
    const ph = this.tl.phrases;
    while (this.checkedTo + 1 < ph.length && ph[this.checkedTo + 1].end <= beat + 1e-6) {
      const p = ++this.checkedTo;
      if (ph[p].end <= this.passStart + 1e-6) continue;
      if (this.range.loop && ph[p].end >= this.range.end - 1e-6) continue;   // the loop goes back anyway
      if (this.rewinds[p] >= this.rules.maxPerPhrase) continue;
      const err = this.matcher.phraseErrors(p);
      if (err.count >= this.threshold(p)) return this.plan("errors", p, err.firstBeat, ph[p].end);
    }
    return null;
  }

  private lostPlan(beat: number): RewindPlan | null {
    let from = Math.max(this.lastPlayed, this.passStart);
    for (;;) {
      const e = this.matcher.firstUnplayedFrom(from);
      if (!e || e.beat > beat) return null;
      // a phrase at its rewind limit keeps going; look for silence after it
      if (this.rewinds[e.phrase] >= this.rules.maxPerPhrase) { from = this.tl.phrases[e.phrase].end; continue; }
      if (beat < Math.max(from, e.beat) + this.rules.lostBeats) return null;
      return this.plan("lost", e.phrase, e.beat, nextBarLine(this.tl, beat));
    }
  }

  private plan(reason: RewindPlan["reason"], phrase: number, firstError: number | null, atBeat: number): RewindPlan {
    const ph = this.tl.phrases;
    let target = phrase;
    // first error on the phrase's first beat: go back one more phrase for a run-up, but never
    // before the start of a section loop
    if (firstError !== null && target > 0 && firstError < ph[target].start + this.tl.beatUnit - 1e-6 &&
        ph[target - 1].start >= this.range.start - 1e-6) target--;
    const targetBeat = Math.max(ph[target].start, this.range.start);
    return { reason, phrase, targetPhrase: target, targetBeat, atBeat };
  }
}
