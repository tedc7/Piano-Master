// The piano input (arch §4): the MIDI piano, or the microphone as an interim stand-in until a MIDI
// piano is used (v0.38). The parent picks one in Config > Device settings; every screen listens
// here and gets the same note events from either. Only the chosen input's notes come through,
// and the microphone is let go while MIDI is chosen.
import type { MicInput } from "./mic";
import type { MidiInput, MidiNote, MidiPedal, MidiStatus } from "./midi";

export type InputMode = "midi" | "mic";

type Listener = (e: MidiNote | MidiPedal) => void;

export class PianoInput {
  private listeners = new Set<Listener>();
  private changeListeners = new Set<() => void>();

  constructor(readonly midi: MidiInput, readonly mic: MicInput, private mode: () => InputMode) {
    midi.onEvent((e) => { if (this.mode() === "midi") this.emit(e); });
    mic.onEvent((e) => { if (this.mode() === "mic") this.emit(e); });
    midi.onChange(() => this.changed());
    mic.onChange(() => this.changed());
  }

  private get active(): MidiInput | MicInput {
    return this.mode() === "mic" ? this.mic : this.midi;
  }

  get status(): MidiStatus { return this.active.status; }
  get inputName(): string | null { return this.active.inputName; }
  /** Recent delivery (MIDI) or detection (microphone) delays, in ms. */
  get delays(): number[] { return this.active.delays; }

  async start(): Promise<void> {
    void this.midi.start();
    await this.apply();
  }

  /** After the mode changes: start or let go of the microphone. */
  async apply(): Promise<void> {
    if (this.mode() === "mic") await this.mic.start();
    else this.mic.stop();
    this.changed();
  }

  onEvent(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  onChange(fn: () => void): () => void {
    this.changeListeners.add(fn);
    return () => this.changeListeners.delete(fn);
  }

  private emit(e: MidiNote | MidiPedal): void {
    for (const fn of this.listeners) fn(e);
  }

  private changed(): void {
    for (const fn of this.changeListeners) fn();
  }
}
