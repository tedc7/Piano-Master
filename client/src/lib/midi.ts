// MIDI input (arch §4): Web MIDI only. The piano is chosen by name, ignoring virtual ports such
// as MIDIWeb Browser's own "MIDIWeb Out" and iPadOS's "Network Session 1", which appear even with
// no keyboard (feasibility test Q2, step 3). Reconnects when the piano is unplugged and replugged.

export type MidiStatus = "starting" | "unsupported" | "denied" | "no-piano" | "connected";

export interface MidiNote {
  type: "on" | "off";
  pitch: number;
  velocity: number;
  timeMs: number;      // performance.now() time of the key press
  delayMs: number;     // delivery delay: handling time minus the event's own time stamp
}

export interface MidiPedal { type: "pedal"; value: number; timeMs: number }

const VIRTUAL = [/midiweb/i, /network session/i, /midi through/i, /iac driver/i, /virtual/i];

export function isVirtualPort(name: string): boolean {
  return VIRTUAL.some((re) => re.test(name));
}

/** The input to use: the preferred name if present, else the first non-virtual input. */
export function choosePort(names: string[], preferred: string | null): string | null {
  if (preferred && names.includes(preferred)) return preferred;
  return names.find((n) => !isVirtualPort(n)) ?? null;
}

/** Decode one MIDI message; null for anything the app does not use. */
export function decode(data: Uint8Array, timeMs: number, delayMs: number): MidiNote | MidiPedal | null {
  if (data.length < 3) return null;
  const kind = data[0] & 0xf0;
  if (kind === 0x90 && data[2] > 0) return { type: "on", pitch: data[1], velocity: data[2], timeMs, delayMs };
  if (kind === 0x80 || kind === 0x90) return { type: "off", pitch: data[1], velocity: 0, timeMs, delayMs };
  if (kind === 0xb0 && data[1] === 64) return { type: "pedal", value: data[2], timeMs };
  return null;
}

type Listener = (e: MidiNote | MidiPedal) => void;

export class MidiInput {
  status: MidiStatus = "starting";
  inputName: string | null = null;
  names: string[] = [];
  delays: number[] = [];               // recent delivery delays (ms), for the piano check
  private access: MIDIAccess | null = null;
  private input: MIDIInput | null = null;
  private listeners = new Set<Listener>();
  private changeListeners = new Set<() => void>();

  constructor(private preferred: () => string | null) {}

  async start(): Promise<void> {
    if (!("requestMIDIAccess" in navigator)) {
      this.setStatus("unsupported");
      return;
    }
    try {
      this.access = await navigator.requestMIDIAccess({ sysex: false });
    } catch {
      this.setStatus("denied");
      return;
    }
    this.access.onstatechange = () => this.select();
    this.select();
  }

  onEvent(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  onChange(fn: () => void): () => void {
    this.changeListeners.add(fn);
    return () => this.changeListeners.delete(fn);
  }

  /** Re-choose the input (after a device change, or when the preferred name changes). */
  select(): void {
    if (!this.access) return;
    const inputs = [...this.access.inputs.values()].filter((i) => i.state !== "disconnected");
    this.names = inputs.map((i) => i.name ?? "");
    const name = choosePort(this.names, this.preferred());
    const next = inputs.find((i) => i.name === name) ?? null;
    if (next !== this.input) {
      if (this.input) this.input.onmidimessage = null;
      this.input = next;
      if (next) next.onmidimessage = (e) => this.handle(e as MIDIMessageEvent);
    }
    this.inputName = next?.name ?? null;
    this.setStatus(next ? "connected" : "no-piano");
  }

  private handle(e: MIDIMessageEvent): void {
    const now = performance.now();
    // the event's time stamp is in the performance.now() time base; trust it only when sensible
    const ts = e.timeStamp;
    const timeMs = Number.isFinite(ts) && ts > 0 && ts <= now + 1 && now - ts < 1000 ? ts : now;
    if (!e.data) return;
    const ev = decode(e.data, timeMs, now - timeMs);
    if (!ev) return;
    if (ev.type === "on") {
      this.delays.push(ev.delayMs);
      if (this.delays.length > 200) this.delays.shift();
    }
    for (const fn of this.listeners) fn(ev);
  }

  private setStatus(s: MidiStatus): void {
    this.status = s;
    for (const fn of this.changeListeners) fn();
  }
}
