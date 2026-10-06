// One attempt at a piece or a section (arch §5 Attempt, §7): the matching, rewind decisions and
// raw events of every pass, and the scored result. The Play screen and the fixture runner both
// drive this class, so recorded performances are scored exactly like live play.
import { Matcher, type Expected, type Verdict } from "./matcher";
import { RewindPolicy, type PlayRange, type RewindPlan } from "./rewind";
import { evaluate, levelBand, WINDOWS_BY_BAND, type Conditions, type Evaluation } from "./scoring";
import { phraseIndexAt, type Timeline } from "./timeline";
import type { Preset } from "./types";

export interface RawEvent {
  t: number;                    // performance.now() ms
  type: "on" | "off" | "pedal";
  pitch?: number;
  velocity?: number;
  value?: number;
  beat: number | null;          // latency-corrected playback beat, when the song clock was running
  pass: number;
}

export interface AttemptOptions {
  hands: "both" | "R" | "L";
  handsWritten: "R" | "L" | "RL";
  section: { start: number; end: number } | null;   // beats; null = the whole piece
  /** Play started part-way, from the staff dragged to this beat (v0.33): the notes before it aren't
   *  expected, and the attempt is practice of part of the song, like a section. */
  from?: number;
  level?: string;
  preset: Preset;
}

/** A missed written note, or a wrong key. A wrong key is paired with the missed written note
 *  nearest it (within half a beat), which is how Diagnostics finds note confusions (arch §8.8). */
export interface NoteError {
  kind: "missed" | "wrong"; beat: number; pitch: number; hand?: string; bar: number;
  note?: number;          // missed: the note's index in the notation
  expected?: number;      // wrong: the written pitch it was played for
}

export interface AttemptResult {
  evaluation: Evaluation;
  conditions: Conditions;
  completed: boolean;
  perPhraseErrors: number[];    // missed + wrong in the last pass of each phrase
  noteErrors: NoteError[];
  /** Each written note of the scored pass: [index in the notation, timing in ms, or null when
   *  missed]. Notes the attempt never reached (stopped part-way) are left out. */
  noteResults: [number, number | null][];
  tricky: { phrase: number; bars: [number, number] } | null;
}

const PRESET_ORDER: Preset[] = ["50", "75", "90", "100"];

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export class Attempt {
  readonly id = uuid();
  readonly startedAt = new Date();
  readonly matcher: Matcher;
  readonly policy: RewindPolicy;
  readonly range: PlayRange;
  readonly rawEvents: RawEvent[] = [];
  readonly passes: { from: number; t: number }[] = [];
  rewinds = 0;
  /** The furthest beat the song clock has reached in this attempt. */
  reached = -Infinity;
  slowest: Preset;
  private other: Expected[];       // the other hand's notes, when practising one hand

  constructor(readonly tl: Timeline, readonly opts: AttemptOptions) {
    const s = opts.section;
    this.range = { start: Math.max(s?.start ?? 0, opts.from ?? 0), end: s?.end ?? tl.length, loop: !!s };
    const inRange = (b: number) => b >= this.range.start - 1e-6 && b < this.range.end - 1e-6;
    const all = tl.notes.filter((n) => !n.tieContinuation && inRange(n.beat))
      .map((n) => ({ id: n.id, pitch: n.pitch, beat: n.beat, phrase: n.phrase, hand: n.hand }));
    const mine = (h: string) => opts.hands === "both" || h === opts.hands;
    this.other = all.filter((n) => !mine(n.hand));
    const windows = WINDOWS_BY_BAND[levelBand(opts.level)];
    this.matcher = new Matcher(all.filter((n) => mine(n.hand)), (b) => phraseIndexAt(tl.phrases, b), windows);
    this.policy = new RewindPolicy(tl, this.matcher, undefined, this.range);
    this.slowest = opts.preset;
  }

  get pass(): number { return this.passes.length - 1; }
  get played(): boolean { return this.rawEvents.some((e) => e.type === "on"); }

  beginPass(beat: number, t: number): void {
    this.passes.push({ from: beat, t });
    this.reached = Math.max(this.reached, beat);
    this.matcher.resetFrom(beat);
    this.policy.beginPass(beat);
  }

  usedPreset(p: Preset): void {
    if (PRESET_ORDER.indexOf(p) < PRESET_ORDER.indexOf(this.slowest)) this.slowest = p;
  }

  record(ev: Omit<RawEvent, "pass">): void {
    this.rawEvents.push({ ...ev, pass: this.pass });
  }

  noteOn(pitch: number, beat: number, velocity: number, spb: number, timeMs: number): Verdict {
    const w = this.matcher.windows.matchMs / 1000 / spb;
    if (beat < this.range.start - w || beat >= this.range.end + w) return { kind: "ignored", reason: "outside" };
    // carrying on past the end of a section (or the piece) is not a wrong note, unless it is a
    // late hit on one of the last notes
    if (beat >= this.range.end - 1e-6 && !this.matcher.expected.some((e) => e.pitch === pitch && Math.abs(e.beat - beat) <= w)) {
      return { kind: "ignored", reason: "outside" };
    }
    // practising one hand: the other hand's notes are not extra notes (§7.2)
    if (this.other.some((n) => n.pitch === pitch && Math.abs(n.beat - beat) <= w)) {
      this.policy.played(beat);
      return { kind: "ignored", reason: "otherHand" };
    }
    this.policy.played(beat);
    return this.matcher.noteOn(pitch, beat, velocity, spb, timeMs);
  }

  noteOff(pitch: number, timeMs: number): void {
    this.matcher.noteOff(pitch, timeMs);
  }

  /** Advance to `beat`: newly missed notes, and a rewind plan when one is due. */
  tick(beat: number, spb: number, autoRewind: boolean): { missed: number[]; plan: RewindPlan | null } {
    this.reached = Math.max(this.reached, beat);
    const missed = this.matcher.advance(beat, spb);
    const plan = autoRewind ? this.policy.update(beat) : null;
    if (plan) this.rewinds++;
    return { missed, plan };
  }

  result(completed: boolean): AttemptResult {
    const m = this.matcher;
    const deltasMs = [...m.hits.values()].map((h) => h.deltaMs);
    const extra = m.wrongs.filter((w) => !w.retracted).length;
    const conditions: Conditions = {
      mode: "play",
      tempoPreset: this.slowest,
      hands: this.opts.hands,
      handsWritten: this.opts.handsWritten,
      sectionOnly: !!this.opts.section || (this.opts.from ?? 0) > 1e-6,
      extraHints: false,
      rewinds: this.rewinds,
    };
    const windows = m.windows;
    const evaluation = evaluate({ expected: m.expected.length, deltasMs, extra }, windows, conditions);
    const ph = this.tl.phrases;
    const inRange = (i: number) => ph[i].end > this.range.start + 1e-6 && ph[i].start < this.range.end - 1e-6;
    const perPhraseErrors = ph.map((_, i) => (inRange(i) ? m.phraseErrors(i).count : 0));
    const barAt = (b: number) => {
      let e = this.tl.entries[0];
      for (const x of this.tl.entries) if (x.start <= b + 1e-6) e = x;
      return e.m.number;
    };
    const missed = m.expected.filter((e) => m.missed.has(e.id) || (completed && !m.hits.has(e.id)));
    const missedIds = new Set(missed.map((e) => e.id));
    const noteResults: [number, number | null][] = m.expected
      .filter((e) => m.hits.has(e.id) || missedIds.has(e.id))
      .map((e) => [this.tl.notes[e.id].index, m.hits.has(e.id) ? Math.round(m.hits.get(e.id)!.deltaMs) : null]);
    const pairFor = (beat: number, pitch: number) => {
      let best: Expected | null = null;
      for (const e of missed) {
        if (Math.abs(e.beat - beat) > 0.5) continue;
        if (!best || Math.abs(e.beat - beat) < Math.abs(best.beat - beat) ||
            (Math.abs(e.beat - beat) === Math.abs(best.beat - beat) && Math.abs(e.pitch - pitch) < Math.abs(best.pitch - pitch))) best = e;
      }
      return best;
    };
    const noteErrors: NoteError[] = [
      ...missed.map((e) => ({ kind: "missed" as const, beat: e.beat, pitch: e.pitch, hand: this.tl.notes[e.id].hand, bar: barAt(e.beat),
                              note: this.tl.notes[e.id].index })),
      ...m.wrongs.filter((w) => !w.retracted).map((w) => {
        const e = pairFor(w.beat, w.pitch);
        return { kind: "wrong" as const, beat: w.beat, pitch: w.pitch, bar: barAt(w.beat),
                 ...(e ? { expected: e.pitch, hand: this.tl.notes[e.id].hand } : {}) };
      }),
    ].sort((a, b) => a.beat - b.beat);
    // the tricky spot: the phrase rewound most, else the one with the most errors (2 or more)
    let tp = this.policy.trickiest();
    if (tp === null) {
      let most = 1;
      perPhraseErrors.forEach((n, i) => { if (n > most) { most = n; tp = i; } });
    }
    let tricky: AttemptResult["tricky"] = null;
    if (tp !== null) {
      const p = ph[tp];
      const inside = this.tl.entries.filter((e) => e.start >= p.start - 1e-6 && e.start < p.end - 1e-6);
      const first = inside[0] ?? this.tl.entries[0];
      const last = inside[inside.length - 1] ?? first;
      tricky = { phrase: tp, bars: [first.m.number, last.m.number] };
    }
    return { evaluation, conditions, completed, perPhraseErrors, noteErrors, noteResults, tricky };
  }
}
