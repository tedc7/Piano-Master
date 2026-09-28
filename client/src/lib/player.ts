// The Play screen's engine (arch §3 "Play and smooth rewind"): one song clock drives the staff,
// lyrics, audio and note matching, so they can't drift apart. Framework-free: the screen calls
// frame() from requestAnimationFrame and draws what it returns.
import type { AudioEngine, StemBuffers } from "./audio";
import { Matcher, type Expected, type Verdict } from "./matcher";
import type { MidiNote, MidiPedal } from "./midi";
import { RewindPolicy, type RewindPlan } from "./rewind";
import type { Settings } from "./settings";
import { gridBeat, phraseIndexAt, type Timeline, type TimelineNote } from "./timeline";
import type { Piece, Preset } from "./types";

export type Mode = "play" | "listen";
export type State = "idle" | "loading" | "gliding" | "countin" | "playing" | "paused" | "finished";

export const GLIDE_MS = 700;       // the staff glides back over 0.6-0.8 s
export const FADE_S = 0.2;         // vocals and backing fade out over about 0.2 s
const PREROLL_S = 0.15;            // stems fade back in just before the resume point
const LEAD_S = 0.12;               // scheduling margin for a fresh start
const HORIZON_S = 0.3;             // clicks and tones are scheduled this far ahead
const PULSE_LEVEL = 0.3;           // the soft pulse that keeps the beat through a glide

interface Clock { t0: number; beat0: number; spb: number }

export interface AttemptResult {
  expected: number;
  hits: number;
  onTime: number;
  missed: number;
  wrong: number;
  rewinds: number;
  tricky: { phrase: number; bars: [number, number] } | null;
  seconds: number;
}

export interface RawEvent { t: number; type: "on" | "off" | "pedal"; pitch?: number; velocity?: number; value?: number; beat: number | null }

export interface PlayerHooks {
  state(s: State): void;
  verdict(v: Verdict, pitch: number): void;     // a key press judged in Play mode
  keyUp(pitch: number): void;
  keyDown(pitch: number): void;                  // a key press not judged (not playing, count-in, Listen)
  missed(noteIds: number[]): void;
  pass(fromBeat: number, targetPhrase: number | null): void;   // a new pass: reset colours from here
  finished(r: AttemptResult): void;
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
  state: State = "idle";
  rawEvents: RawEvent[] = [];
  private clock: Clock | null = null;
  private glide: { t0: number; from: number; to: number; target: number } | null = null;
  private displayBeat: number;
  private logicBeat: number;
  private passStart = 0;
  private stems: StemBuffers | null = null;
  private matcher!: Matcher;
  private policy!: RewindPolicy;
  private expected: Expected[];
  private nextClick = 0;
  private pulseAt: number | null = null;      // context time of the next beat on the running grid
  private pulseSpb = 0.6;
  private toneCursor = 0;
  private attemptStart = 0;
  private totalRewinds = 0;
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
    this.expected = tl.notes.filter((n) => !n.tieContinuation)
      .map((n) => ({ id: n.id, pitch: n.pitch, beat: n.beat, phrase: n.phrase }));
    this.displayBeat = this.logicBeat = -tl.barLength;
    this.newAttempt();
  }

  get tempo(): number { return this.piece.media?.bpm ?? this.piece.notation.header.tempo; }
  get spb(): number { return 60 / (this.tempo * Number(this.preset) / 100); }
  get hasStems(): boolean { return !!this.piece.media?.presets[this.preset]; }
  get running(): boolean { return this.state === "countin" || this.state === "playing" || this.state === "gliding"; }

  private setState(s: State): void {
    this.state = s;
    this.hooks.state(s);
  }

  private newAttempt(): void {
    this.matcher = new Matcher(this.expected, (b) => phraseIndexAt(this.tl.phrases, b));
    this.policy = new RewindPolicy(this.tl, this.matcher);
    this.rawEvents = [];
    this.totalRewinds = 0;
  }

  // ------------------------------------------------------------------ controls

  /** Play from the start (a new attempt), or resume after a pause. */
  async play(): Promise<void> {
    if (this.state === "paused") return this.resumeAt(this.phraseStartFor(this.displayBeat));
    if (this.state === "finished") return this.restart();
    if (this.running || this.state === "loading") return;
    if (!(await this.ensureReady())) return;
    this.newAttempt();
    this.attemptStart = performance.now();
    this.hooks.pass(-Infinity, 0);
    this.startAt(0);
  }

  pause(): void {
    if (!this.running) return;
    this.audio.stopStems(0.1);
    this.clock = null;
    this.glide = null;
    this.pulseAt = null;
    this.setState("paused");
    this.releaseWake();
  }

  /** Start over: a new attempt from the beginning, gliding back if the song is under way. */
  async restart(): Promise<void> {
    if (this.state === "loading") return;
    if (this.state === "idle") return this.play();
    const from = this.displayBeat;
    this.audio.stopStems(FADE_S);
    this.clock = null;
    if (!(await this.ensureReady())) return;
    this.newAttempt();
    this.attemptStart = performance.now();
    this.hooks.pass(-Infinity, 0);
    this.beginGlide(from, 0);
  }

  stop(): void {
    this.audio.stopStems(0.08);
    this.clock = null;
    this.glide = null;
    this.pulseAt = null;
    this.displayBeat = this.logicBeat = -this.tl.barLength;
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
    this.newAttempt();
    this.hooks.pass(-Infinity, null);
  }

  /** Fetch and decode this preset's stems ahead of time (works before the first tap). */
  async preload(): Promise<void> {
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
    if (beat < 0) return 0;
    return this.tl.phrases[phraseIndexAt(this.tl.phrases, Math.max(beat, this.passStart))].start;
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
    this.matcher.resetFrom(beat);
    this.policy.beginPass(beat);
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
      if (this.mode === "listen") this.scheduleTones();
      if (this.mode === "play" && this.state === "playing") {
        const missed = this.matcher.advance(this.logicBeat, this.clock.spb);
        if (missed.length) this.hooks.missed(missed);
        if (s.autoRewind) {
          const plan = this.policy.update(this.logicBeat);
          if (plan) this.rewind(plan);
        }
      }
      if (this.clock && this.logicBeat >= this.tl.length + 0.25) this.finish();
      const u = this.tl.beatUnit;
      const ciStart = this.passStart - this.tl.barLength;
      if (this.clock && this.displayBeat < this.passStart) {
        countIn = { total: Math.round(this.tl.barLength / u), current: Math.floor((this.displayBeat - ciStart) / u + 1e-6) };
      }
    }
    return { beat: this.displayBeat, logicBeat: this.logicBeat, countIn };
  }

  private rewind(plan: RewindPlan): void {
    this.totalRewinds++;
    this.audio.stopStems(FADE_S);
    this.hooks.pass(plan.targetBeat, plan.targetPhrase);
    this.beginGlide(this.displayBeat, plan.targetBeat);
  }

  private finish(): void {
    this.audio.stopStems(0.8);
    this.clock = null;
    this.pulseAt = null;
    this.setState("finished");
    this.releaseWake();
    if (this.mode !== "play") return;
    const sum = this.matcher.summary();
    const tp = this.policy.trickiest();
    let tricky: AttemptResult["tricky"] = null;
    if (tp !== null) {
      const ph = this.tl.phrases[tp];
      const inside = this.tl.entries.filter((e) => e.start >= ph.start - 1e-6 && e.start < ph.end - 1e-6);
      const first = inside[0] ?? this.tl.entries[0];
      const last = inside[inside.length - 1] ?? first;
      tricky = { phrase: tp, bars: [first.m.number, last.m.number] };
    }
    this.hooks.finished({ ...sum, rewinds: this.totalRewinds, tricky, seconds: (performance.now() - this.attemptStart) / 1000 });
  }

  // ------------------------------------------------------------------ sound scheduling

  private scheduleClicks(): void {
    const ctx = this.audio.ctx!;
    const horizon = ctx.currentTime + HORIZON_S;
    const u = this.tl.beatUnit;
    const bar = this.tl.barLength;
    const pick = this.piece.notation.header.pickupBeats;
    const clickOn = this.settings().click[this.piece.id] ?? !this.piece.media;
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

  private scheduleTones(): void {
    const ctx = this.audio.ctx!;
    const horizon = ctx.currentTime + HORIZON_S;
    const notes = this.tl.notes;
    while (this.toneCursor < notes.length) {
      const n = notes[this.toneCursor];
      const t = this.timeOf(n.beat);
      if (t > horizon) break;
      if (!n.tieContinuation && t >= ctx.currentTime - 0.01) {
        let dur = n.duration;
        // a tied note sounds once, for the whole tied length
        for (let k = n, j = this.toneCursor + 1; k.tieToNext && j < notes.length; j++) {
          const m = notes[j];
          if (m.pitch === k.pitch && m.staff === k.staff && m.voice === k.voice && Math.abs(m.beat - (k.beat + k.duration)) < 1e-6) {
            dur += m.duration;
            k = m;
          }
        }
        this.audio.tone(n.pitch, Math.max(t, ctx.currentTime), dur * this.clock!.spb * 0.95, this.hasStems ? 0.6 : 1);
      }
      this.toneCursor++;
    }
  }

  // ------------------------------------------------------------------ MIDI

  onMidi(ev: MidiNote | MidiPedal): void {
    if (ev.type === "pedal") {
      this.rawEvents.push({ t: ev.timeMs, type: "pedal", value: ev.value, beat: null });
      return;
    }
    let beat: number | null = null;
    if (this.clock && this.audio.ctx) {
      beat = this.beatAt(this.audio.outputTimeAt(ev.timeMs) - this.settings().latencyOffsetMs / 1000);
    }
    this.rawEvents.push({ t: ev.timeMs, type: ev.type, pitch: ev.pitch, velocity: ev.velocity, beat });
    if (ev.type === "off") {
        this.matcher.noteOff(ev.pitch, ev.timeMs);
      this.hooks.keyUp(ev.pitch);
      return;
    }
    const judged = this.mode === "play" && beat !== null && (this.state === "countin" || this.state === "playing") &&
      beat >= this.passStart - this.matcher.windows.matchMs / 1000 / this.spb;     // notes during the count-in are ignored
    if (!judged) {
      this.hooks.keyDown(ev.pitch);
      return;
    }
    this.policy.played(beat!);
    const v = this.matcher.noteOn(ev.pitch, beat!, ev.velocity, this.spb, ev.timeMs);
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
    const notes = this.tl.notes;
    const open = (n: TimelineNote) => !n.tieContinuation && !this.matcher.hits.has(n.id);
    const first = notes.find((n) => n.beat >= beat - 1e-6 && open(n));
    if (!first) return [];
    return notes.filter((n) => Math.abs(n.beat - first.beat) < 1e-6 && open(n));
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
    return { matcher: this.matcher.summary(), rewinds: [...this.policy.rewinds], passStart: this.passStart, state: this.state };
  }
}

function ease(p: number): number {
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
}
