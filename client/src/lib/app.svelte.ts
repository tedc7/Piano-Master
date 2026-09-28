// App-wide state shared by the screens: settings, the audio engine and the MIDI input.
import { api } from "./api";
import { AudioEngine } from "./audio";
import { MidiInput, type MidiStatus } from "./midi";
import { loadSettings, saveSettings, type Settings } from "./settings";

/** Full-screen reminder threshold (arch §2.2): 87 px of app bars on the iPad A16, 0 in full
 *  screen. Moves to the DeviceProfile with M4. */
export const FULL_SCREEN_GAP_PX = 40;

class AppState {
  settings = $state<Settings>(loadSettings());
  midiStatus = $state<MidiStatus>("starting");
  pianoName = $state<string | null>(null);
  midiNames = $state<string[]>([]);
  screenGap = $state(0);
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
