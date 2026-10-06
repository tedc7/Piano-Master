// App-wide state shared by the screens: this device's settings, the audio engine, the MIDI input,
// who is playing (a student, or the parent after the PIN), and the student's state from the lesson
// engine on the piano server (skills, today's session, today's practice time, favorites).
//
// The server decides; the client keeps a copy of each student's last state in this browser and
// updates it straight away when an item is finished, so a Wi-Fi drop never stops practice. The
// copy is replaced by the server's as soon as every attempt in the outbox has been sent.
import { api, ApiError } from "./api";
import { AudioEngine } from "./audio";
import { MidiInput, type MidiStatus } from "./midi";
import type { ItemResult, Progress, Session, SessionItem, SkillProgress, StudentState } from "./progress";
import { go } from "./route";
import {
  loadDevice, loadParentSettings, saveDevice, saveParentSettings, toggleIn, withDefaults,
  type DeviceSettings, type Settings, type StudentSettings,
} from "./settings";
import type { Preset } from "./types";

/** Full-screen reminder threshold (arch §2.2): 87 px of app bars on the iPad A16, 0 in full
 *  screen. */
export const FULL_SCREEN_GAP_PX = 40;

export interface Student { id: string; name: string; avatar: string; status?: string; settings: StudentSettings; targetMinutes?: number }

const STUDENTS_KEY = "pm.students.v1";
const STATE_KEY = "pm.state.v1";
const FAV_KEY = "pm.parent-favorites.v1";
const PING_MS = 60 * 1000;

function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not kept over a reload */ }
}

class AppState {
  device = $state<DeviceSettings>(loadDevice());
  /** The current player's settings: the student's, from the server, or the parent's own. */
  prefs = $state<StudentSettings>(loadParentSettings());
  midiStatus = $state<MidiStatus>("starting");
  pianoName = $state<string | null>(null);
  midiNames = $state<string[]>([]);
  screenGap = $state(0);
  students = $state<Student[]>(read<Student[]>(STUDENTS_KEY, []));
  studentsStatus = $state<"loading" | "ok" | "offline">("loading");
  student = $state<Student | null>(null);
  parentMode = $state(false);
  pinSet = $state<boolean | null>(null);
  autoLogoutMinutes = $state(10);
  // the student's state from the lesson engine
  progress = $state<Progress>(new Map());
  session = $state<Session | null>(null);
  day = $state<StudentState["day"] | null>(null);
  favorites = $state<string[]>([]);
  stateStatus = $state<"none" | "loading" | "ok" | "offline">("none");
  stateError = $state("");
  /** Where the Play screen's Back button goes: the screen that opened the song. */
  returnTo = "session";
  /** Set by Back: the screen it returns to puts back how it was left (lib/keep.ts). */
  private returning: string | null = null;
  private lastTouch = 0;
  private lastPing = 0;
  private refreshTimer = 0;
  readonly isIPad = /iPad|iPhone|Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1;
  readonly audio = new AudioEngine();
  readonly midi: MidiInput;

  constructor() {
    this.midi = new MidiInput(() => this.device.pianoName);
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
    window.addEventListener("pointerdown", () => this.touched(), { capture: true });
    // start the audio on the first tap anywhere (iPadOS only starts it from one), so a lesson that opens
    // after it can read its first card aloud
    for (const ev of ["touchend", "click"]) window.addEventListener(ev, () => this.audio.unlock(), { capture: true });
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.leaveParent(); });
    setInterval(() => {
      if (this.parentMode && performance.now() - this.lastTouch > this.autoLogoutMinutes * 60000) this.leaveParent();
    }, 15000);
    // an attempt reached the server: its state now includes it
    api.onStored(() => {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = window.setTimeout(() => void this.refresh(), 300);
    });
    this.applyMix();
  }

  /** This device's settings and the player's, as the Play screen and the player read them. */
  get settings(): Settings {
    return { ...this.device, ...this.prefs };
  }

  // ------------------------------------------------------------------ players

  async loadStudents(): Promise<void> {
    try {
      const r = await api.request<{ students: Student[] }>("/students");
      this.students = r.students.map((s) => ({ ...s, settings: withDefaults(s.settings) }));
      this.studentsStatus = "ok";
      write(STUDENTS_KEY, this.students);
    } catch {
      this.studentsStatus = "offline";
    }
    try {
      const p = await api.request<{ pinSet: boolean; autoLogoutMinutes: number }>("/parent");
      this.pinSet = p.pinSet;
      this.autoLogoutMinutes = p.autoLogoutMinutes;
    } catch { /* asked again on the PIN screen */ }
  }

  chooseStudent(s: Student): void {
    this.leaveParent(false);
    this.student = s;
    this.prefs = withDefaults(s.settings);
    api.studentId = s.id;
    this.applyMix();
    const cached = read<Record<string, StudentState>>(STATE_KEY, {})[s.id];
    if (cached && cached.day?.date === new Date().toLocaleDateString("en-CA")) this.apply(cached, false);
    else this.clearState();
    go("session");
    void this.refresh();
  }

  /** Back to the player picker; the parent is logged out. */
  switchPlayer(): void {
    this.leaveParent(false);
    this.student = null;
    api.studentId = null;
    this.clearState();
    go("");
  }

  /** Parent login (arch §11.1): the server checks the PIN. Throws ApiError with the reason. */
  async enterParent(pin: string): Promise<void> {
    const r = await api.request<{ token: string; autoLogoutMinutes: number }>("/parent/login", "POST", { pin });
    this.startParent(r.token, r.autoLogoutMinutes);
  }

  /** The first PIN, on a new piano server: it also logs the parent in. */
  async setFirstPin(pin: string): Promise<void> {
    const r = await api.request<{ token: string; autoLogoutMinutes: number }>("/parent/pin", "POST", { pin });
    this.pinSet = true;
    this.startParent(r.token, r.autoLogoutMinutes);
  }

  private startParent(token: string, minutes: number): void {
    this.student = null;
    api.studentId = null;
    this.clearState();
    api.parentToken = token;
    this.autoLogoutMinutes = minutes;
    this.parentMode = true;
    this.prefs = loadParentSettings();
    this.applyMix();
    this.lastTouch = this.lastPing = performance.now();
    api.log("info", "parent mode on");
    go("config");
  }

  /** Log the parent out (after the idle time, when the device sleeps, or on Switch player). */
  leaveParent(toPicker = true): void {
    if (!this.parentMode) return;
    this.parentMode = false;
    void api.request("/parent/logout", "POST").catch(() => {});
    api.parentToken = null;
    api.log("info", "parent mode off");
    if (toPicker) go("");
  }

  private touched(): void {
    this.lastTouch = performance.now();
    // keep the server's parent session alive while the parent is using Config
    if (this.parentMode && this.lastTouch - this.lastPing > PING_MS) {
      this.lastPing = this.lastTouch;
      api.request("/parent/ping", "POST").catch((e) => { if (e instanceof ApiError && e.status === 401) this.leaveParent(); });
    }
  }

  /** A parent request refused because the server's session ended: log out here too. */
  parentRefused(e: unknown): boolean {
    if (e instanceof ApiError && e.status === 401 && this.parentMode) {
      this.leaveParent();
      return true;
    }
    return false;
  }

  openPiece(id: string, from: string): void {
    this.returnTo = from;
    go(`play/${id}`);
  }

  /** The Play screen's Back: to the screen that opened the song, as it was left. */
  back(): void {
    this.returning = this.returnTo;
    go(this.returnTo);
  }

  /** Whether the screen at `key` is being returned to by Back (asked once, as it opens). */
  takeReturn(key: string): boolean {
    const yes = this.returning === key;
    if (yes) this.returning = null;
    return yes;
  }

  // ------------------------------------------------------------------ the student's state

  private clearState(): void {
    this.progress = new Map();
    this.session = null;
    this.day = null;
    this.favorites = this.parentMode ? read<string[]>(FAV_KEY, []) : [];
    this.stateStatus = "none";
    this.stateError = "";
  }

  private apply(st: StudentState, fresh: boolean): void {
    this.progress = new Map(st.skills.map((k) => [k.skillId, k]));
    this.session = st.session;
    this.day = st.day;
    this.favorites = st.favorites;
    this.stateStatus = fresh ? "ok" : "offline";
    if (fresh) this.cache();
  }

  private cache(): void {
    if (!this.student || !this.session || !this.day) return;
    const all = read<Record<string, StudentState>>(STATE_KEY, {});
    all[this.student.id] = {
      student: $state.snapshot(this.student) as StudentState["student"], contentVersion: "",
      skills: [...this.progress.values()].map((p) => $state.snapshot(p) as SkillProgress),
      session: $state.snapshot(this.session) as Session, day: $state.snapshot(this.day) as StudentState["day"],
      favorites: [...this.favorites],
    };
    write(STATE_KEY, all);
  }

  /** The server's state for the student, once the outbox is empty (so nothing played is lost). */
  async refresh(): Promise<void> {
    const s = this.student;
    if (!s) return;
    if (this.stateStatus === "none") this.stateStatus = "loading";
    await api.flush();
    if (api.pending > 0) {
      this.stateStatus = this.session ? "offline" : "none";
      this.stateError = "The piano server can't be reached; plays are kept and sent later.";
      return;
    }
    try {
      const st = await api.request<StudentState>(`/students/${s.id}/state?device_id=${api.deviceId}`);
      if (this.student?.id !== s.id) return;
      this.apply(st, true);
      this.stateError = "";
    } catch (e) {
      this.stateStatus = this.session ? "offline" : "none";
      this.stateError = `Can't reach the piano server (${(e as Error).message}).`;
    }
  }

  get sessionItem(): SessionItem | null {
    return this.session?.items.find((i) => !i.done) ?? null;
  }

  item(id: string | null | undefined): SessionItem | null {
    return (id && this.session?.items.find((i) => i.id === id)) || null;
  }

  /** Item finished: a song played to the end (or once round its section), or a concept lesson.
   *  It is checked off straight away, however the student leaves the screen; the server does the
   *  same when the attempt reaches it. Playing it again keeps the better stars. */
  completeItem(id: string, r: ItemResult | null): void {
    const it = this.item(id);
    if (!it) return;
    it.done = true;
    if (r && (!it.result || (r.accuracyStars ?? 0) >= (it.result.accuracyStars ?? 0))) it.result = r;
    const skill = it.skillId ? this.progress.get(it.skillId) : undefined;
    if (r && skill && skill.status === "current" && (r.accuracyStars ?? 0) < 3) it.tries++;
    this.cache();
  }

  /** Skip once: the item moves to the end of the queue (§8.5). */
  skipItem(id: string): void {
    const s = this.session;
    const i = s?.items.findIndex((x) => x.id === id && !x.done) ?? -1;
    if (!s || i < 0) return;
    const [it] = s.items.splice(i, 1);
    it.skipped = true;
    s.items.push(it);
    this.cache();
    if (this.student) {
      api.request(`/students/${this.student.id}/session/skip`, "POST", { itemId: id }).catch(() => {});
    }
  }

  /** A concept lesson gone through: its skill becomes Current (§8.1). Parent reviews record nothing. */
  /** `check`: the lesson's Check and Echo cards (arch §7.8), kept on the server; a theory skill
   *  passes on them. */
  lessonDone(skillId: string, itemId: string | null, seconds: number, check?: { questions: number; points: number }): void {
    if (!this.student) return;
    if (itemId) this.completeItem(itemId, null);
    const p = this.progress.get(skillId);
    if (p) {
      p.conceptDone = true;
      if (p.status === "locked" && p.lessonOpen) p.status = "current";
    }
    this.addPractice(seconds, !!itemId);
    const sid = this.student.id;
    api.request(`/students/${sid}/lessons/${encodeURIComponent(skillId)}/done`, "POST",
      { itemId, seconds: Math.round(seconds), deviceId: api.deviceId, ...(check ? { check } : {}) })
      .then(() => this.refresh()).catch(() => {});
  }

  /** Practice time today, shown straight away (the server adds it when the attempt arrives). */
  addPractice(seconds: number, guided: boolean): void {
    if (!this.day) return;
    if (guided) this.day.guidedSec += seconds; else this.day.freeSec += seconds;
    this.cache();
  }

  toggleFavorite(pieceId: string): void {
    const on = !this.favorites.includes(pieceId);
    this.favorites = toggleIn(this.favorites, pieceId, on);
    if (this.student) {
      api.request(`/students/${this.student.id}/favorites/${pieceId}`, on ? "PUT" : "DELETE").catch(() => {});
      this.cache();
    } else {
      write(FAV_KEY, this.favorites);
    }
  }

  // ------------------------------------------------------------------ settings

  /** A choice on the Play screen, remembered for this player (arch §3): vocals and the tempo preset
   *  for this song; the metronome (`click`) for every song (v0.29). */
  setSongPref(pieceId: string, p: { vocalsOff?: boolean; click?: boolean; chords?: boolean; preset?: Preset }): void {
    if (p.vocalsOff !== undefined) this.prefs.vocalsOff = toggleIn(this.prefs.vocalsOff, pieceId, p.vocalsOff);
    if (p.click !== undefined) this.prefs.metronome = p.click;
    if (p.chords !== undefined) this.prefs.chords = p.chords;
    if (p.preset !== undefined) this.prefs.presets = { ...this.prefs.presets, [pieceId]: p.preset };
    if (this.student) {
      this.student.settings = $state.snapshot(this.prefs) as StudentSettings;
      api.request(`/students/${this.student.id}/prefs`, "PATCH", { pieceId, ...p }).catch(() => {});
    } else {
      saveParentSettings($state.snapshot(this.prefs) as StudentSettings);
    }
  }

  /** The lesson screen's Auto-read, remembered for this player for every lesson (v0.34). */
  setAutoRead(on: boolean): void {
    this.prefs.autoRead = on;
    if (this.student) {
      this.student.settings = $state.snapshot(this.prefs) as StudentSettings;
      api.request(`/students/${this.student.id}/prefs`, "PATCH", { autoRead: on }).catch(() => {});
    } else {
      saveParentSettings($state.snapshot(this.prefs) as StudentSettings);
    }
  }

  /** The parent's own playing settings (auto-rewind, rewind bars, backing volume). */
  setParentPrefs(p: Partial<StudentSettings>): void {
    Object.assign(this.prefs, p);
    saveParentSettings($state.snapshot(this.prefs) as StudentSettings);
    this.applyMix();
  }

  /** This device's settings (parent only): kept here and copied to the DeviceProfile. */
  setDevice(p: Partial<DeviceSettings>): void {
    Object.assign(this.device, p);
    const snap = $state.snapshot(this.device) as DeviceSettings;
    saveDevice(snap);
    if (this.parentMode) {
      api.request(`/devices/${api.deviceId}`, "PUT", { profile: { ...snap, fullScreenGapPx: FULL_SCREEN_GAP_PX } })
        .catch((e) => this.parentRefused(e));
    }
  }

  choosePiano(name: string | null): void {
    this.setDevice({ pianoName: name });
    this.midi.select();
  }

  applyMix(): void {
    this.audio.mix.backingVolume = this.prefs.backingVolume;
    this.audio.applyMix();
  }

  get needsFullScreen(): boolean {
    return this.isIPad && this.screenGap > FULL_SCREEN_GAP_PX;
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

export const AVATARS = ["🦊", "🐢", "🐼", "🦁", "🐸", "🦉", "🐙", "🦄", "🐝", "🐬", "🐯", "🐨"];
