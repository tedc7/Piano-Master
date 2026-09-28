// App-wide state shared by the screens: settings, the audio engine, the MIDI input, who is
// playing, parent mode and today's session.
import { api } from "./api";
import { AudioEngine } from "./audio";
import { MidiInput, type MidiStatus } from "./midi";
import type { SessionItem } from "./progress";
import { go } from "./route";
import { loadSettings, saveSettings, type Settings } from "./settings";

/** Full-screen reminder threshold (arch §2.2): 87 px of app bars on the iPad A16, 0 in full
 *  screen. Moves to the DeviceProfile with M4. */
export const FULL_SCREEN_GAP_PX = 40;

/** Parent mode logs out after this long without a touch, or when the device sleeps (arch §3). */
export const PARENT_IDLE_MS = 10 * 60 * 1000;

export interface Student { id: string; name: string; avatar: string }

/** PLACEHOLDER students until the server holds them (M4); the parent adds the real ones. */
export const SAMPLE_STUDENTS: Student[] = [
  { id: "sample-1", name: "Player 1", avatar: "🦊" },
  { id: "sample-2", name: "Player 2", avatar: "🐢" },
];

export interface Session { items: SessionItem[]; index: number }

class AppState {
  settings = $state<Settings>(loadSettings());
  midiStatus = $state<MidiStatus>("starting");
  pianoName = $state<string | null>(null);
  midiNames = $state<string[]>([]);
  screenGap = $state(0);
  student = $state<Student | null>(null);
  parentMode = $state(false);
  session = $state<Session | null>(null);
  /** Where the Play screen's Back button goes: the screen that opened the song. */
  returnTo = "home";
  private lastTouch = 0;
  readonly isIPad = /iPad|iPhone|Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1;
  readonly audio = new AudioEngine();
  readonly midi: MidiInput;

  constructor() {
    this.midi = new MidiInput(() => this.settings.pianoName);
    this.midi.onChange(() => {
      if (this.midi.status !== this.midiStatus || this.midi.inputName !== this.pianoName) {
        api.log("info", `MIDI ${this.midi.status}`, { input: this.midi.inputName, inputs: this.midi.names });
      }
      this.midiStatus = this.midi.status;
      this.pianoName = this.midi.inputName;
      this.midiNames = [...this.midi.names];
    });
    const measure = () => {
      // iOS reports screen.width/height in portrait terms whatever the orientation
      const landscape = window.innerWidth > window.innerHeight;
      const tall = landscape ? Math.min(screen.width, screen.height) : Math.max(screen.width, screen.height);
      this.screenGap = tall - window.innerHeight;
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("pointerdown", () => { this.lastTouch = performance.now(); }, { capture: true });
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.leaveParent(); });
    setInterval(() => {
      if (this.parentMode && performance.now() - this.lastTouch > PARENT_IDLE_MS) this.leaveParent();
    }, 15000);
  }

  chooseStudent(s: Student): void {
    this.student = s;
    this.session = null;
    go("home");
  }

  /** PLACEHOLDER: any 4 digits until the server checks the PIN (M4, arch §11.1). */
  enterParent(pin: string): boolean {
    if (!/^\d{4}$/.test(pin)) return false;
    this.parentMode = true;
    this.lastTouch = performance.now();
    api.log("info", "parent mode on");
    return true;
  }

  leaveParent(): void {
    if (!this.parentMode) return;
    this.parentMode = false;
    api.log("info", "parent mode off");
    if (location.hash.startsWith("#/parent")) go(this.student ? "home" : "");
  }

  openPiece(id: string, from: string): void {
    this.returnTo = from;
    go(`play/${id}`);
  }

  startSession(items: SessionItem[]): void {
    this.session = { items, index: 0 };
    go("session");
  }

  /** After an item's result: move to the next item ("Next", arch §8.5). */
  nextItem(): void {
    if (this.session) this.session.index++;
    go("session");
  }

  get needsFullScreen(): boolean {
    return this.isIPad && this.screenGap > FULL_SCREEN_GAP_PX;
  }

  save(): void {
    saveSettings($state.snapshot(this.settings) as Settings);
    this.audio.mix.backingVolume = this.settings.backingVolume;
    this.audio.applyMix();
  }

  choosePiano(name: string | null): void {
    this.settings.pianoName = name;
    this.save();
    this.midi.select();
  }
}

export const app = new AppState();

export function pianoLabel(status: MidiStatus, name: string | null): string {
  switch (status) {
    case "connected": return name ?? "Piano";
    case "starting": return "Looking for the piano…";
    case "unsupported": return "No MIDI in this browser";
    case "denied": return "MIDI not allowed";
    default: return "No piano connected";
  }
}
