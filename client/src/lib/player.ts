// The Play screen's engine (arch §3 "Play and smooth rewind"): one song clock drives the staff,
// lyrics, audio and note matching, so they can't drift apart. Framework-free: the screen calls
// frame() from requestAnimationFrame and draws what it returns.
//
// Two modes: Play (play along, scored, with smooth automatic rewind) and Listen (the app plays it;
// no scoring). Either runs over the whole piece or over a section of bars chosen on the screen,
// which then goes round and round ("Practice tricky part" picks one at a slower preset). A section
// in Play mode is stored as a "loop" attempt, one per time round.
//
// The app's piano: Listen mode plays every note; in Play mode with one hand chosen, it plays the
// other hand (the student setting "otherHand"), so one-hand practice still sounds like the piece.
import { Attempt, type AttemptResult, type RawEvent } from "./attempt";
import type { AudioEngine, StemBuffers } from "./audio";
import type { Verdict } from "./matcher";
import type { MidiNote, MidiPedal } from "./midi";
import type { RewindPlan } from "./rewind";
import type { Settings } from "./settings";
import { gridBeat, phraseIndexAt, type Timeline, type TimelineNote } from "./timeline";
import type { Piece, Preset } from "./types";

export type Mode = "play" | "listen";
export type State = "idle" | "loading" | "gliding" | "countin" | "playing" | "paused" | "finished";
export type Hands = "both" | "R" | "L";

export const GLIDE_MS = 700;       // the staff glides back over 0.6-0.8 s
export const FADE_S = 0.2;         // vocals and backing fade out over about 0.2 s
const PREROLL_S = 0.15;            // stems fade back in just before the resume point
const LEAD_S = 0.12;               // scheduling margin for a fresh start
const HORIZON_S = 0.3;             // clicks and tones are scheduled this far ahead
const PULSE_LEVEL = 0.3;           // the soft pulse that keeps the beat through a glide
const OTHER_HAND_LEVEL = 0.6;      // the app's other hand sits under the student's playing

interface Clock { t0: number; beat0: number; spb: number }

/** A finished (or stopped) attempt, ready to store (arch §5 Attempt). */
export interface AttemptRecord extends AttemptResult {
  id: string;
  pieceId: string;
  mode: "play" | "loop";
  section: { fromBeat: number; toBeat: number } | null;
  startedAt: string;
  durationSec: number;
  latencyOffsetMs: number;
  displayOffsetMs: number;
  rawEvents: RawEvent[];
  passes: { from: number; t: number }[];
}

export interface PlayerHooks {
  state(s: State): void;
  verdict(v: Verdict, pitch: number): void;     // a key press judged in Play or Loop mode
  keyUp(pitch: number): void;
  keyDown(pitch: number): void;                  // a key press not judged (not playing, count-in, Listen)
  missed(noteIds: number[]): void;
  pass(fromBeat: number, targetPhrase: number | null): void;   // a new pass: reset colours from here
  finished(r: AttemptRecord): void;             // the whole piece, in Play mode
  loopPass(r: AttemptRecord): void;             // one time round a section loop
  save(r: AttemptRecord): void;                 // every attempt with notes played, finished or not
  loading(fraction: number): void;
  error(message: string): void;
}

export interface Frame {
  beat: number;                 // display beat (where the staff sits)
  logicBeat: number;            // scoring beat
  countIn: { total: number; current: number } | null;
}

export class Player {
  mode: Mode = "play";
  preset: Preset;
  hands: Hands = "both";
  /** The section being played (phrase indices, inclusive), or null for the whole piece. */
  section: [number, number] | null = null;
  state: State = "idle";
  /** The metronome for this visit, overriding the song's remembered choice (a remedy item's). */
  forceClick: boolean | null = null;
  private attempt: Attempt;
  private clock: Clock | null = null;
  private glide: { t0: number; from: number; to: number; target: number } | null = null;
  private displayBeat: number;
  private logicBeat: number;
  private passStart = 0;
  private resumeFrom: number | null = null;   // set by Rewind while paused
  private stems: StemBuffers | null = null;
  private nextClick = 0;
  private pulseAt: number | null = null;      // context time of the next beat on the running grid
  private pulseSpb = 0.6;
  private toneCursor = 0;
  private wake: WakeLockSentinel | null = null;

  constructor(
    readonly piece: Piece,
    readonly tl: Timeline,
    private audio: AudioEngine,
    private settings: () => Settings,
    private hooks: PlayerHooks,
    preset: Preset,
  ) {
    this.preset = preset;
    this.attempt = this.newAttempt();
    this.displayBeat = this.logicBeat = this.start - tl.barLength;
  }

  get tempo(): number { return this.piece.media?.bpm ?? this.piece.notation.header.tempo; }
  get spb(): number { return 60 / (this.tempo * Number(this.preset) / 100); }
  get hasStems(): boolean { return !!this.piece.media?.presets[this.preset]; }
  get running(): boolean { return this.state === "countin" || this.state === "playing" || this.state === "gliding"; }
  get scoring(): boolean { return this.mode === "play"; }
  /** Where play starts and ends: the whole piece, or the section. */
  get start(): number { return this.section ? this.tl.phrases[this.section[0]].start : 0; }
  get end(): number { return this.section ? this.tl.phrases[this.section[1]].end : this.tl.length; }

  private setState(s: State): void {
    this.state = s;
    this.hooks.state(s);
  }

  private newAttempt(): Attempt {
    const loop = !!this.section;
    return new Attempt(this.tl, {
      hands: this.hands,
      handsWritten: this.piece.hands,
      section: loop ? { start: this.start, end: this.end } : null,
      level: this.piece.level,
      preset: this.preset,
    });
  }

  /** Store the attempt if anything was played; `completed` = played to the end. */
  private closeAttempt(completed: boolean): AttemptRecord | null {
    const a = this.attempt;
    if (!this.scoring || !a.passes.length || !a.played) return null;
    const s = this.settings();
    const rec: AttemptRecord = {
      ...a.result(completed),
      id: a.id,
      pieceId: this.piece.id,
      mode: this.section ? "loop" : "play",
      section: this.section ? { fromBeat: this.start, toBeat: this.end } : null,
      startedAt: a.startedAt.toISOString(),
      durationSec: Math.round((Date.now() - a.startedAt.getTime()) / 100) / 10,
      latencyOffsetMs: s.latencyOffsetMs,
      displayOffsetMs: s.displayOffsetMs,
      rawEvents: a.rawEvents,
      passes: a.passes,
    };
    this.hooks.save(rec);
    return rec;
  }

  // ------------------------------------------------------------------ controls

  /** Play from the start (a new attempt), or resume after a pause. */
  async play(): Promise<void> {
    if (this.state === "paused") {
      // Listen carries on from the bar it stopped in; Play goes back to the phrase start, so the
      // phrase is scored as one pass
      const at = this.resumeFrom ?? (this.scoring ? this.phraseStartFor(this.displayBeat) : this.barStartFor(this.displayBeat));
      this.resumeFrom = null;
      return this.resumeAt(at);
    }
    if (this.state === "finished") return this.again();
    if (this.running || this.state === "loading") return;
    if (!(await this.ensureReady())) return;
    this.attempt = this.newAttempt();
    this.hooks.pass(-Infinity, phraseIndexAt(this.tl.phrases, this.start));
    this.startAt(this.start);
  }

  pause(): void {
    if (!this.running) return;
    this.quiet(0.1);
    this.clock = null;
    this.glide = null;
    this.pulseAt = null;
    this.setState("paused");
    this.releaseWake();
  }

  /** The Rewind button: while playing, glide back `bars` bars (from the start of the current bar)
   *  and play on after the count-in; while paused, move the resume point back; after the end,
   *  back to the start, ready to play again. Never before the section's start. In Play mode it
   *  counts as a rewind, like the automatic ones (arch §7.5). */
  rewindBars(bars: number): void {
    if (this.state === "finished") {
      this.stop();
      this.reposition();
      return;
    }
    if (this.state !== "paused" && !this.running) return;
    const from = this.state === "gliding" ? this.resumeBeat! :
      this.state === "paused" ? (this.resumeFrom ?? this.displayBeat) :
      this.state === "countin" ? this.passStart : this.logicBeat;
    // the start of the current bar, then `bars` bar lines further back
    const lines = this.tl.barLines;
    let i = 0;
    while (i + 1 < lines.length && lines[i + 1] <= from + 0.05) i++;
    const target = Math.max(this.start, lines[Math.max(0, i - bars)]);
    if (this.scoring) this.attempt.rewinds++;
    const phrase = phraseIndexAt(this.tl.phrases, target);
    this.hooks.pass(target, phrase);
    if (this.state === "paused") {
      this.resumeFrom = target;
      this.displayBeat = this.logicBeat = target - this.tl.barLength;
      return;
    }
    this.quiet(FADE_S);
    this.beginGlide(this.displayBeat, target);
  }

  /** Play again after the end: a new attempt, gliding back to the start. */
  private async again(): Promise<void> {
    const from = this.displayBeat;
    if (!(await this.ensureReady())) return;
    this.attempt = this.newAttempt();
    this.hooks.pass(-Infinity, phraseIndexAt(this.tl.phrases, this.start));
    this.beginGlide(from, this.start);
  }

  /** Stop and go back to the start position; an attempt under way is saved as not completed. */
  stop(): void {
    if (this.state !== "finished" && this.state !== "idle") this.closeAttempt(false);
    this.quiet(0.08);
    this.clock = null;
    this.glide = null;
    this.pulseAt = null;
    this.displayBeat = this.logicBeat = this.start - this.tl.barLength;
    this.resumeFrom = null;
    this.attempt = this.newAttempt();
    this.setState("idle");
    this.releaseWake();
  }

  async setPreset(p: Preset): Promise<void> {
    if (p === this.preset || this.state === "loading") return;
    const wasRunning = this.running;
    const at = this.phraseStartFor(this.displayBeat);
    if (wasRunning) this.pause();
    this.preset = p;
    this.stems = null;
    // stopped or paused: stay put (Play resumes at the new tempo)
    if (!wasRunning) {
      if (this.piece.media) void this.preload();
      return;
    }
    await this.resumeAt(at);
  }

  setMode(m: Mode): void {
    if (m === this.mode) return;
    this.stop();
    this.mode = m;
    this.reposition();
  }

  setHands(h: Hands): void {
    if (h === this.hands) return;
    this.stop();
    this.hands = h;
    this.reposition();
  }

  /** Choose the section (phrase indices, inclusive), or null for all bars. */
  setSection(range: [number, number] | null): void {
    const n = this.tl.phrases.length;
    this.stop();
    if (range) {
      const a = Math.max(0, Math.min(n - 1, range[0]));
      this.section = [a, Math.max(a, Math.min(n - 1, range[1]))];
    } else {
      this.section = null;
    }
    this.reposition();
  }

  /** "Practice tricky part": play along with that phrase, round and round, at the next slower
   *  preset (arch §3). */
  async practiceTricky(phrase: number): Promise<Preset> {
    this.stop();
    this.mode = "play";
    this.section = [phrase, phrase];
    const slower: Record<Preset, Preset> = { "100": "90", "90": "75", "75": "50", "50": "50" };
    if (slower[this.preset] !== this.preset) {
      this.preset = slower[this.preset];
      this.stems = null;
    }
    this.reposition();
    void this.play();
    return this.preset;
  }

  private reposition(): void {
    this.attempt = this.newAttempt();
    this.displayBeat = this.logicBeat = this.start - this.tl.barLength;
    this.hooks.pass(-Infinity, null);
  }

  /** Stems and piano notes stop together: a pause, rewind, loop or stop. */
  private quiet(fade: number): void {
    this.audio.stopStems(fade);
    this.audio.silencePiano(fade);
  }

  /** The piano samples this piece needs (small, from the piano server). */
  private loadPiano(): Promise<void> {
    return this.audio.loadPiano(this.tl.notes.map((n) => n.pitch));
  }

  /** Fetch and decode this preset's stems and the piano samples ahead of time (works before the
   *  first tap). */
  async preload(): Promise<void> {
    void this.loadPiano();
    if (!this.piece.media || !this.hasStems) return;
    const preset = this.preset;
    try {
      const bufs = await this.audio.loadStems(this.piece.id, this.piece.media, preset, (f) => this.hooks.loading(f));
      if (this.preset === preset) this.stems = bufs;     // the tempo may have changed meanwhile
    } catch (e) {
      this.hooks.error((e as Error).message);
    }
  }

  /** Audio running and this preset's stems decoded; false if the stems could not load. */
  private async ensureReady(): Promise<boolean> {
    await this.audio.ensure();
    await this.loadPiano();              // a sample that fails to load falls back to the plain tone
    if (this.piece.media && this.hasStems && !this.stems) {
      const prev = this.state;
      this.setState("loading");
      try {
        this.stems = await this.audio.loadStems(this.piece.id, this.piece.media, this.preset, (f) => this.hooks.loading(f));
        this.setState(prev === "loading" ? "idle" : prev);
      } catch (e) {
        this.hooks.error((e as Error).message);
        this.setState("idle");
        return false;
      }
    }
    return true;
  }

  private phraseStartFor(beat: number): number {
    if (beat < this.start) return this.start;
    const p = this.tl.phrases[phraseIndexAt(this.tl.phrases, Math.max(beat, this.passStart))];
    return Math.max(p.start, this.start);
  }

  private barStartFor(beat: number): number {
    const lines = this.tl.barLines;
    let i = 0;
    while (i + 1 < lines.length && lines[i + 1] <= beat + 0.05) i++;
    return Math.max(this.start, Math.min(lines[i], this.end - 1e-6));
  }

  private async resumeAt(target: number): Promise<void> {
    if (!(await this.ensureReady())) return;
    this.beginGlide(this.displayBeat, target);
  }

  // ------------------------------------------------------------------ the song clock

  private beginGlide(from: number, target: number): void {
    this.glide = { t0: performance.now(), from, to: target - this.tl.barLength, target };
    this.clock = null;
    this.setState("gliding");
  }

  /** Count in one bar, then play from `beat`. */
  private startAt(beat: number): void {
    const ctx = this.audio.ctx!;
    const spb = this.spb;
    const bar = this.tl.barLength;
    // keep the pulse steady through a rewind: the count-in starts on the next pulse
    let t0 = ctx.currentTime + LEAD_S;
    if (this.pulseAt !== null) {
      t0 = this.pulseAt;
      while (t0 < ctx.currentTime + 0.05) t0 += this.pulseSpb;
    }
    this.clock = { t0, beat0: beat - bar, spb };
    this.passStart = beat;
    if (this.stems && this.piece.media) {
      const offset = (beat + this.piece.media.padBeats) * spb;
      this.audio.startStems(this.stems, offset, t0 + bar * spb, PREROLL_S);
    }
    this.attempt.usedPreset(this.preset);    // an attempt counts at the slowest preset it used
    this.attempt.beginPass(beat, performance.now());
    this.nextClick = gridBeat(this.tl, this.piece.notation.header.pickupBeats, beat - bar);
    this.toneCursor = this.tl.notes.findIndex((n) => n.beat >= beat - 1e-6);
    if (this.toneCursor < 0) this.toneCursor = this.tl.notes.length;
    this.pulseSpb = this.tl.beatUnit * spb;
    this.setState("countin");
    void this.holdWake();
  }

  private beatAt(ctxTime: number): number {
    const c = this.clock!;
    return c.beat0 + (ctxTime - c.t0) / c.spb;
  }

  private timeOf(beat: number): number {
    const c = this.clock!;
    return c.t0 + (beat - c.beat0) * c.spb;
  }

  /** Advance everything to performance time `now`; returns where to draw. */
  frame(now: number): Frame {
    let countIn: Frame["countIn"] = null;
    if (this.glide) {
      const p = Math.min(1, (now - this.glide.t0) / GLIDE_MS);
      const g = this.glide;
      this.displayBeat = this.logicBeat = g.from + (g.to - g.from) * ease(p);
      this.softPulse();
      if (p >= 1) {
        this.glide = null;
        this.startAt(g.target);
      }
    } else if (this.clock) {
      const s = this.settings();
      const heard = this.audio.outputTimeAt(now);
      this.displayBeat = this.beatAt(heard - s.displayOffsetMs / 1000);
      this.logicBeat = this.beatAt(heard - s.latencyOffsetMs / 1000);
      if (this.state === "countin" && this.logicBeat >= this.passStart - 1e-6) this.setState("playing");
      this.scheduleClicks();
      if (this.mode === "listen" || this.otherHandSounds) this.scheduleTones();
      if (this.scoring && this.state === "playing") {
        const { missed, plan } = this.attempt.tick(this.logicBeat, this.clock.spb, s.autoRewind);
        if (missed.length) this.hooks.missed(missed);
        if (plan) this.rewind(plan);
      }
      if (this.clock) {
        if (this.section && this.logicBeat >= this.end + 0.1) this.loopAround();
        else if (!this.section && this.logicBeat >= this.end + 0.25) this.finish();
      }
      if (this.clock && this.displayBeat < this.passStart) {
        const u = this.tl.beatUnit;
        const ciStart = this.passStart - this.tl.barLength;
        countIn = { total: Math.round(this.tl.barLength / u), current: Math.floor((this.displayBeat - ciStart) / u + 1e-6) };
      }
    }
    return { beat: this.displayBeat, logicBeat: this.logicBeat, countIn };
  }

  private rewind(plan: RewindPlan): void {
    this.quiet(FADE_S);
    this.hooks.pass(plan.targetBeat, plan.targetPhrase);
    this.beginGlide(this.displayBeat, plan.targetBeat);
  }

  /** One time round the loop: score it as its own (section) attempt, then go again. */
  private loopAround(): void {
    const rec = this.closeAttempt(true);
    if (rec) this.hooks.loopPass(rec);
    this.attempt = this.newAttempt();
    this.quiet(FADE_S);
    this.hooks.pass(this.start, this.section![0]);
    this.beginGlide(this.displayBeat, this.start);
  }

  private finish(): void {
    this.quiet(0.8);
    this.clock = null;
    this.pulseAt = null;
    this.setState("finished");
    this.releaseWake();
    const rec = this.closeAttempt(true);
    if (rec && this.mode === "play") this.hooks.finished(rec);
  }

  // ------------------------------------------------------------------ sound scheduling

  private scheduleClicks(): void {
    const ctx = this.audio.ctx!;
    const horizon = ctx.currentTime + HORIZON_S;
    const u = this.tl.beatUnit;
    const bar = this.tl.barLength;
    const pick = this.piece.notation.header.pickupBeats;
    const clickOn = this.forceClick ?? this.settings().click[this.piece.id] ?? !this.piece.media;
    for (;;) {
      const t = this.timeOf(this.nextClick);
      if (t > horizon) break;
      if (t >= ctx.currentTime) {
        const countIn = this.nextClick < this.passStart - 1e-6;
        const down = Math.abs((this.nextClick - pick) / bar - Math.round((this.nextClick - pick) / bar)) < 1e-6;
        if (countIn || clickOn) this.audio.click(t, down, countIn ? 1 : 0.7);
      }
      this.nextClick += u;
      this.pulseAt = this.timeOf(this.nextClick);
    }
  }

  private softPulse(): void {
    const ctx = this.audio.ctx;
    if (!ctx || this.pulseAt === null) return;
    while (this.pulseAt < ctx.currentTime + HORIZON_S) {
      if (this.pulseAt >= ctx.currentTime) this.audio.click(this.pulseAt, false, PULSE_LEVEL);
      this.pulseAt += this.pulseSpb;
    }
  }

  /** Play mode with one hand chosen: the app plays the other hand. */
  get otherHandSounds(): boolean {
    return this.scoring && this.hands !== "both" && this.piece.hands === "RL" && this.settings().otherHand;
  }

  /** The app's piano: every note in Listen mode, the other hand's in one-hand Play practice. */
  private scheduleTones(): void {
    const ctx = this.audio.ctx!;
    const horizon = ctx.currentTime + HORIZON_S;
    const notes = this.tl.notes;
    const listen = this.mode === "listen";
    const level = listen ? (this.hasStems ? 0.6 : 1) : OTHER_HAND_LEVEL;
    while (this.toneCursor < notes.length) {
      const n = notes[this.toneCursor];
      const t = this.timeOf(n.beat);
      if (t > horizon) break;
      if (!n.tieContinuation && t >= ctx.currentTime - 0.01 && (listen || n.hand !== this.hands) && n.beat < this.end - 1e-6) {
        let dur = n.duration;
        // a tied note sounds once, for the whole tied length
        for (let k = n, j = this.toneCursor + 1; k.tieToNext && j < notes.length; j++) {
          const m = notes[j];
          if (m.pitch === k.pitch && m.staff === k.staff && m.voice === k.voice && Math.abs(m.beat - (k.beat + k.duration)) < 1e-6) {
            dur += m.duration;
            k = m;
          }
        }
        // a dynamic mark's velocity (100 is forte) makes the note louder or softer
        this.audio.piano(n.pitch, Math.max(t, ctx.currentTime), dur * this.clock!.spb * 0.95,
          level * Math.min(1, (n.velocity ?? 100) / 100));
      }
      this.toneCursor++;
    }
  }

  // ------------------------------------------------------------------ MIDI

  onMidi(ev: MidiNote | MidiPedal): void {
    if (ev.type === "pedal") {
      this.attempt.record({ t: ev.timeMs, type: "pedal", value: ev.value, beat: null });
      return;
    }
    // a rhythm tap drill: any key counts as the drill's note; only the timing matters (§7.8)
    const any = this.piece.drill?.anyKey;
    if (any !== undefined) ev = { ...ev, pitch: any };
    let beat: number | null = null;
    if (this.clock && this.audio.ctx) {
      beat = this.beatAt(this.audio.outputTimeAt(ev.timeMs) - this.settings().latencyOffsetMs / 1000);
    }
    this.attempt.record({ t: ev.timeMs, type: ev.type, pitch: ev.pitch, velocity: ev.velocity, beat });
    if (ev.type === "off") {
      this.attempt.noteOff(ev.pitch, ev.timeMs);
      this.hooks.keyUp(ev.pitch);
      return;
    }
    const judged = this.scoring && beat !== null && (this.state === "countin" || this.state === "playing") &&
      beat >= this.passStart - this.attempt.matcher.windows.matchMs / 1000 / this.spb;   // count-in notes are ignored
    if (!judged) {
      this.hooks.keyDown(ev.pitch);
      return;
    }
    const v = this.attempt.noteOn(ev.pitch, beat!, ev.velocity, this.spb, ev.timeMs);
    if (v.kind === "ignored") this.hooks.keyDown(ev.pitch);
    else this.hooks.verdict(v, ev.pitch);
  }

  // ------------------------------------------------------------------ screen wake

  private async holdWake(): Promise<void> {
    if (this.wake || !("wakeLock" in navigator)) return;
    try {
      this.wake = await navigator.wakeLock.request("screen");
      this.wake.addEventListener("release", () => { this.wake = null; });
    } catch { /* not allowed now; the next start tries again */ }
  }

  private releaseWake(): void {
    void this.wake?.release();
    this.wake = null;
  }

  /** The next notes to play at or after `beat`, skipping ones already played (for the keyboard). */
  nextTargets(beat: number): TimelineNote[] {
    const m = this.attempt.matcher;
    const expected = new Set(m.expected.map((e) => e.id));
    const open = (n: TimelineNote) => expected.has(n.id) && !m.hits.has(n.id);
    const first = this.tl.notes.find((n) => n.beat >= beat - 1e-6 && open(n));
    if (!first) return [];
    return this.tl.notes.filter((n) => Math.abs(n.beat - first.beat) < 1e-6 && open(n));
  }

  /** During a glide: the beat play resumes from. */
  get resumeBeat(): number | null {
    return this.glide?.target ?? null;
  }

  /** Where the song is: the staff's beat and the scoring beat. */
  get position(): { display: number; logic: number } {
    return { display: this.displayBeat, logic: this.logicBeat };
  }

  /** For tests and the settings sheet. */
  debug() {
    return {
      matcher: this.attempt.matcher.summary(),
      rewinds: [...this.attempt.policy.rewinds],
      passStart: this.passStart,
      state: this.state,
    };
  }
}

function ease(p: number): number {
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
}
