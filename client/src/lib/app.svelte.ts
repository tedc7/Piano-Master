// App-wide state shared by the screens: settings, the audio engine, the MIDI input, who is
// playing (a student, or the parent after the PIN) and today's session.
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

/** Stars earned by a finished session item (null for a concept lesson). */
export interface ItemResult { accuracyStars: number | null; timingStars: number | null; title?: string }

/** Today's Guided session for one student (arch §8.5). Kept in this browser for the day until
 *  the server holds the queue (M5), so a reload resumes where the student stopped. */
export interface Session {
  studentId: string;
  date: string;
  items: SessionItem[];
  index: number;                      // the next item to play; items before it are done
  results: (ItemResult | null)[];     // parallel to items
  seconds: number;                    // practice time today (play and loop attempts)
}

const SESSION_KEY = "pm.session.v1";
const today = () => new Date().toLocaleDateString("en-CA");

function loadSession(studentId: string): Session | null {
  try {
    const all = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "{}") as Record<string, Session>;
    const s = all[studentId];
    return s && s.date === today() ? s : null;
  } catch {
    return null;
  }
}

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
  returnTo = "session";
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
    this.leaveParent(false);
    this.student = s;
    this.session = loadSession(s.id);
    go("session");
  }

  /** Back to the player picker; the parent is logged out. */
  switchPlayer(): void {
    this.leaveParent(false);
    this.student = null;
    this.session = null;
    go("");
  }

  /** The parent is a player of their own, behind the PIN. PLACEHOLDER: any 4 digits until the
   *  server checks the PIN (M4, arch §11.1). */
  enterParent(pin: string): boolean {
    if (!/^\d{4}$/.test(pin)) return false;
    this.student = null;
    this.session = null;
    this.parentMode = true;
    this.lastTouch = performance.now();
    api.log("info", "parent mode on");
    go("config");
    return true;
  }

  /** Log the parent out (after 10 idle minutes, when the device sleeps, or on Switch player). */
  leaveParent(toPicker = true): void {
    if (!this.parentMode) return;
    this.parentMode = false;
    api.log("info", "parent mode off");
    if (toPicker) go("");
  }

  openPiece(id: string, from: string): void {
    this.returnTo = from;
    go(`play/${id}`);
  }

  /** Today's session, built from `items` the first time it is needed today. */
  ensureSession(items: () => SessionItem[]): Session | null {
    if (!this.student) return null;
    if (!this.session) {
      const list = items();
      this.session = { studentId: this.student.id, date: today(), items: list, index: 0, results: list.map(() => null), seconds: 0 };
      this.saveSession();
    }
    return this.session;
  }

  get sessionItem(): SessionItem | null {
    const s = this.session;
    return s && s.index < s.items.length ? s.items[s.index] : null;
  }

  /** The current item's result; a replay keeps the better stars. */
  itemResult(r: ItemResult): void {
    const s = this.session;
    if (!s || s.index >= s.items.length) return;
    const old = s.results[s.index];
    if (!old || (r.accuracyStars ?? 0) >= (old.accuracyStars ?? 0)) s.results[s.index] = r;
    this.saveSession();
  }

  /** After an item: move to the next one ("Next", arch §8.5). */
  nextItem(): void {
    if (this.session) {
      this.session.index++;
      this.saveSession();
    }
    go("session");
  }

  /** Skip once: the item moves to the end of the queue (§8.5). */
  skipItem(): void {
    const s = this.session;
    if (!s || s.index >= s.items.length - 1) return;
    const move = <T>(a: T[]) => [...a.slice(0, s.index), ...a.slice(s.index + 1), a[s.index]];
    s.items = move(s.items);
    s.results = move(s.results);
    this.saveSession();
  }

  addPractice(seconds: number): void {
    if (!this.session) return;
    this.session.seconds += seconds;
    this.saveSession();
  }

  private saveSession(): void {
    if (!this.session) return;
    try {
      const all = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "{}") as Record<string, Session>;
      all[this.session.studentId] = $state.snapshot(this.session) as Session;
      localStorage.setItem(SESSION_KEY, JSON.stringify(all));
    } catch { /* not kept over a reload */ }
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
