// Microphone input (arch §4 "Microphone input", v0.38): an interim stand-in for the MIDI piano,
// for a keyboard without MIDI. It gives the same events as MidiInput (lib/midi.ts), so the Play
// screen, the lessons, the piano check and the latency calibration work unchanged.
//
// Clean-up before the note detector (lib/pitch.ts), which does the rest:
//  - The browser's echo cancellation takes most of the app's own sound (backing, vocals, its
//    piano, the lesson voice) out of the microphone signal. Its noise suppression and automatic
//    gain are off: they are tuned for speech, and would fade a held piano note and move the levels.
//    On iPadOS echo cancellation brings the device's whole voice processing, which may be tuned
//    for speech too, so the parent can turn it off (Device settings: "Voice processing").
//  - The detector is also given everything the app plays, learns how loud it comes back through
//    the microphone, and only counts a key well above the app's own sound of it, so the vocals
//    and backing can play while the child does, as with the MIDI piano.
//  - A band-pass filter (55 Hz to 5 kHz) keeps the piano's range and drops rumble and hiss.
//  - Keys the app's own piano is sounding are set aside too.
import type { AudioEngine } from "./audio";
import type { MidiNote, MidiStatus } from "./midi";
import { FRAME, NoteDetector, SENSITIVITY, type DetectedNote } from "./pitch";

export type Sensitivity = 1 | 2 | 3;

/** A stretch of microphone sound, as the browser gave it (before the app's band-pass), with the
 *  keys heard in it, for tuning the detector (Config > Piano check). */
export interface MicRecording {
  rate: number;
  samples: Float32Array;
  output: Float32Array;                    // what the app played meanwhile (vocals, backing, its piano)
  keys: { type: "on" | "off"; pitch: number; ms: number; sure: boolean }[];
  settings: Record<string, unknown>;       // what the browser applied (echo cancellation, ...)
}
const TICK_MS = 10;
const SILENT_TICKS = 300;        // 3 s of exact zeros: the microphone isn't giving sound

/** A key event from the microphone: a MIDI-style note, and whether it is clear enough to count
 *  as a wrong note (lib/pitch.ts). */
export type MicNote = MidiNote & { sure: boolean };

type Listener = (e: MicNote) => void;

export class MicInput {
  status: MidiStatus = "starting";
  inputName: string | null = null;
  deviceLabel = "";                      // the browser's name for the microphone
  readonly names: string[] = [];
  delays: number[] = [];                 // detection delays (ms), for the piano check
  /** Loudness and the noise floor (dBFS), for the parent's level meter. */
  levelDb = -100;
  floorDb = -100;
  private stream: MediaStream | null = null;
  private nodes: AudioNode[] = [];
  private analyser: AnalyserNode | null = null;
  private outputTap: AnalyserNode | null = null;
  private outBuf = new Float32Array(FRAME);
  private detector: NoteDetector | null = null;
  private buf = new Float32Array(FRAME);
  private timer = 0;
  private silentTicks = 0;
  private starting: Promise<void> | null = null;
  private listeners = new Set<Listener>();
  private changeListeners = new Set<() => void>();

  private source: MediaStreamAudioSourceNode | null = null;
  private recording: { chunks: Float32Array[]; outs: Float32Array[]; keys: MicRecording["keys"]; start: number } | null = null;

  constructor(private audio: AudioEngine, private sensitivity: () => Sensitivity, private voiceProcessing: () => boolean,
              private keys: () => 61 | 88 | null) {}

  /** Start again, after the voice-processing setting changes. */
  async restart(): Promise<void> {
    if (!this.stream) return;
    this.stop();
    await this.start();
  }

  /** Record what the microphone hears for `seconds`, with the keys heard. */
  async record(seconds: number, progress: (done: number) => void): Promise<MicRecording | null> {
    const ctx = this.audio.ctx;
    if (!this.source || !ctx || this.recording) return null;
    // a ScriptProcessor, though old, runs everywhere this app does (an AudioWorklet needs a module);
    // the microphone on one channel, the app's own output on the other
    const merge = ctx.createChannelMerger(2);
    const proc = ctx.createScriptProcessor(4096, 2, 1);
    const sink = new GainNode(ctx, { gain: 0 });
    const rec = { chunks: [] as Float32Array[], outs: [] as Float32Array[], keys: [] as MicRecording["keys"], start: performance.now() };
    this.recording = rec;
    proc.onaudioprocess = (e) => {
      rec.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      rec.outs.push(new Float32Array(e.inputBuffer.getChannelData(1)));
    };
    this.source.connect(merge, 0, 0);
    this.outputTap?.connect(merge, 0, 1);
    merge.connect(proc);
    proc.connect(sink).connect(ctx.destination);
    const end = rec.start + seconds * 1000;
    await new Promise<void>((done) => {
      const tick = () => {
        progress(Math.min(1, (performance.now() - rec.start) / (seconds * 1000)));
        if (performance.now() >= end || !this.stream) done(); else setTimeout(tick, 250);
      };
      tick();
    });
    try { this.source?.disconnect(merge); this.outputTap?.disconnect(merge); } catch { /* the microphone stopped */ }
    merge.disconnect();
    proc.disconnect();
    sink.disconnect();
    this.recording = null;
    const join = (parts: Float32Array[]) => {
      const all = new Float32Array(parts.reduce((n, c) => n + c.length, 0));
      let at = 0;
      for (const c of parts) { all.set(c, at); at += c.length; }
      return all;
    };
    const track = this.stream?.getAudioTracks()[0];
    return { rate: ctx.sampleRate, samples: join(rec.chunks), output: join(rec.outs), keys: rec.keys,
             settings: { ...(track?.getSettings() ?? {}), sensitivity: this.sensitivity(), voiceProcessing: this.voiceProcessing(),
                         coupling: this.detector?.coupling ?? null, label: this.deviceLabel, userAgent: navigator.userAgent } };
  }

  /** What the browser applied to the microphone (for the piano check's saved results). */
  get applied(): Record<string, unknown> {
    const s = this.stream?.getAudioTracks()[0]?.getSettings();
    return s ? { echoCancellation: s.echoCancellation, noiseSuppression: s.noiseSuppression, autoGainControl: s.autoGainControl, sampleRate: s.sampleRate } : {};
  }

  onEvent(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  onChange(fn: () => void): () => void {
    this.changeListeners.add(fn);
    return () => this.changeListeners.delete(fn);
  }

  get listening(): boolean {
    return this.stream !== null;
  }

  /** Ask for the microphone and start listening (the browser asks permission the first time). */
  start(): Promise<void> {
    if (this.stream) return Promise.resolve();
    this.starting ??= this.open().finally(() => { this.starting = null; });
    return this.starting;
  }

  /** Stop listening and let the microphone go (iPadOS stops showing it in use). */
  stop(): void {
    clearInterval(this.timer);
    if (this.outputTap) this.audio.untapOutput(this.outputTap);
    this.outputTap = null;
    for (const n of this.nodes) n.disconnect();
    this.nodes = [];
    this.analyser = null;
    this.detector = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.source = null;
    this.inputName = null;
    this.setStatus("starting");
  }

  /** Re-read the sensitivity setting. */
  select(): void {
    if (this.detector) this.detector.threshold = SENSITIVITY[this.sensitivity()];
  }

  private async open(): Promise<void> {
    this.setStatus("starting");
    if (!navigator.mediaDevices?.getUserMedia) { this.setStatus("unsupported"); return; }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: this.voiceProcessing(), noiseSuppression: false, autoGainControl: false, channelCount: 1 },
      });
    } catch (e) {
      const name = (e as DOMException).name;
      this.setStatus(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "no-piano");
      return;
    }
    const ctx = this.audio.create();
    const source = ctx.createMediaStreamSource(stream);
    const high = new BiquadFilterNode(ctx, { type: "highpass", frequency: 55, Q: 0.707 });
    const low = new BiquadFilterNode(ctx, { type: "lowpass", frequency: 5000, Q: 0.707 });
    const analyser = new AnalyserNode(ctx, { fftSize: FRAME, smoothingTimeConstant: 0 });
    // an analyser is only sure to run when it leads to the output: through a silent gain
    const sink = new GainNode(ctx, { gain: 0 });
    source.connect(high).connect(low).connect(analyser).connect(sink).connect(ctx.destination);
    // the app's own output, to compare with what the microphone hears
    const outputTap = new AnalyserNode(ctx, { fftSize: FRAME, smoothingTimeConstant: 0 });
    this.audio.tapOutput(outputTap);
    outputTap.connect(sink);
    this.outputTap = outputTap;
    this.nodes = [source, high, low, analyser, outputTap, sink];
    this.stream = stream;
    this.source = source;
    this.analyser = analyser;
    // the keyboard's keys: C2 to C7 on 61 keys, A0 to C8 on 88 (and when not set)
    const [lo, hi] = this.keys() === 61 ? [36, 96] : [21, 108];
    this.detector = new NoteDetector(ctx.sampleRate, lo, hi, this.sensitivity());
    const track = stream.getAudioTracks()[0];
    this.inputName = "Microphone";
    this.deviceLabel = track?.label ?? "";
    track?.addEventListener("ended", () => { this.stop(); this.setStatus("no-piano"); });
    // iPadOS mutes the microphone while a call, Siri or another app has it
    track?.addEventListener("mute", () => this.setStatus("silent"));
    track?.addEventListener("unmute", () => this.setStatus("connected"));
    this.timer = window.setInterval(() => this.tick(), TICK_MS);
    this.setStatus("connected");
  }

  private tick(): void {
    const ctx = this.audio.ctx;
    if (!this.analyser || !this.detector || !ctx || ctx.state !== "running") return;
    // the analyser holds the latest samples, up to the last block the audio thread rendered: now
    const now = performance.now();
    this.analyser.getFloatTimeDomainData(this.buf);
    this.outputTap?.getFloatTimeDomainData(this.outBuf);
    // exact digital silence is no room, however quiet: the microphone gives no sound at all
    // (a Piano check recording of 60 s of zeros, Oct 28, 2026)
    const zero = this.buf.every((v) => v === 0);
    this.silentTicks = zero ? this.silentTicks + 1 : 0;
    if (this.silentTicks === SILENT_TICKS && this.status === "connected") this.setStatus("silent");
    if (!zero && this.status === "silent" && !this.stream?.getAudioTracks()[0]?.muted) this.setStatus("connected");
    const self = this.audio.selfSound(ctx.currentTime);
    const events = this.detector.process(this.buf, now, (p) => self.pitches.has(p), this.outBuf);
    this.levelDb = this.detector.levelDb;
    this.floorDb = this.detector.floorDb;
    for (const e of events) this.emit(e, now);
  }

  private emit(e: DetectedNote, now: number): void {
    const note: MicNote = { type: e.type, pitch: e.pitch, velocity: e.velocity, timeMs: e.timeMs, delayMs: now - e.timeMs, sure: e.sure };
    if (this.recording) this.recording.keys.push({ type: e.type, pitch: e.pitch, ms: Math.round(e.timeMs - this.recording.start), sure: e.sure });
    if (e.type === "on") {
      this.delays.push(note.delayMs);
      if (this.delays.length > 200) this.delays.shift();
    }
    for (const fn of this.listeners) fn(note);
  }

  private setStatus(s: MidiStatus): void {
    this.status = s;
    for (const fn of this.changeListeners) fn();
  }
}
