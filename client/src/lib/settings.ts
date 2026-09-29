// Settings by owner (arch §5, v0.18):
//  - Device (DeviceProfile; Config > Device settings, parent only): the offsets, the piano input
//    and the keyboard size. Kept in this browser, which is where they are measured, and copied to
//    the piano server's DeviceProfile when the parent changes them.
//  - Each student (Student.settings on the piano server; Config > Students): auto-rewind, rewind
//    bars and backing volume, set by the parent, and the Play screen's per-song choices (vocals,
//    metronome, tempo preset), remembered as the student makes them.
//  - The parent playing: the same student-style settings, kept in this browser.
// Storage can be missing or cleared on iPadOS, so defaults always work.
import type { Preset } from "./types";

export interface DeviceSettings {
  displayOffsetMs: number;   // staff drawn this much behind the estimated audio clock (80 ms on the iPad A16)
  latencyOffsetMs: number;   // subtracted from played-note times before matching (tap-along calibration, M0)
  pianoName: string | null;  // the MIDI input to use; null = the first real (non-virtual) input
  keyboardSize: 61 | 88 | null;   // parent-set (arch §5)
}

export interface StudentSettings {
  autoRewind: boolean;
  rewindBars: number;        // how far the Rewind button goes back while playing
  backingVolume: number;     // 2 = the 200% found right on the iPad
  vocalsOff: string[];       // piece ids with vocals off (remembered per song, arch §3)
  click: Record<string, boolean>;  // metronome during play, per piece (default: on unless the song has singing)
  presets: Record<string, Preset>;
}

/** What the Play screen and the player read: this device's settings and the player's. */
export type Settings = DeviceSettings & StudentSettings;

const DEVICE_KEY = "pm.device-settings.v1";
const PARENT_KEY = "pm.parent-settings.v1";
const OLD_KEY = "pm.settings.v1";          // before M4, everything was kept per device

export const DEVICE_DEFAULTS: DeviceSettings = {
  displayOffsetMs: 80,
  // Until the tap-along calibration exists, assume the key presses line up with what the child
  // sees and hears, which the display offset already measures on this device.
  latencyOffsetMs: 80,
  pianoName: null,
  keyboardSize: null,
};

export const STUDENT_DEFAULTS: StudentSettings = {
  autoRewind: true,
  rewindBars: 2,
  backingVolume: 2,
  vocalsOff: [],
  click: {},
  presets: {},
};

function read<T extends object>(key: string, defaults: T): T {
  try {
    const raw = localStorage.getItem(key) ?? localStorage.getItem(OLD_KEY);
    if (raw) {
      const all = JSON.parse(raw);
      return Object.fromEntries(Object.keys(defaults).map((k) => [k, k in all ? all[k] : (defaults as never)[k]])) as T;
    }
  } catch { /* storage blocked or corrupt: use the defaults */ }
  return structuredClone(defaults);
}

function write(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not saved; still works */ }
}

export const loadDevice = () => read(DEVICE_KEY, DEVICE_DEFAULTS);
export const saveDevice = (s: DeviceSettings) => write(DEVICE_KEY, s);
export const loadParentSettings = () => read(PARENT_KEY, STUDENT_DEFAULTS);
export const saveParentSettings = (s: StudentSettings) => write(PARENT_KEY, s);

export function withDefaults(s: Partial<StudentSettings> | undefined): StudentSettings {
  return { ...structuredClone(STUDENT_DEFAULTS), ...(s ?? {}) };
}

export function toggleIn(list: string[], id: string, on: boolean): string[] {
  const rest = list.filter((x) => x !== id);
  return on ? [...rest, id] : rest;
}
