// Per-device settings, kept in this browser until the server holds the DeviceProfile and the
// student settings (M4). Storage can be missing or cleared on iPadOS, so defaults always work.
import type { Preset } from "./types";

export interface Settings {
  displayOffsetMs: number;   // staff drawn this much behind the estimated audio clock (80 ms on the iPad A16)
  latencyOffsetMs: number;   // subtracted from played-note times before matching (tap-along calibration, M0)
  autoRewind: boolean;
  backingVolume: number;     // 2 = the 200% found right on the iPad
  pianoName: string | null;  // the MIDI input to use; null = the first real (non-virtual) input
  vocalsOff: string[];       // piece ids with vocals off (remembered per song, arch §3)
  click: Record<string, boolean>;  // metronome click during play, per piece (default: on unless the song has singing)
  presets: Record<string, Preset>;
}

const KEY = "pm.settings.v1";

export const DEFAULTS: Settings = {
  displayOffsetMs: 80,
  // Until the tap-along calibration exists, assume the key presses line up with what the child
  // sees and hears, which the display offset already measures on this device.
  latencyOffsetMs: 80,
  autoRewind: true,
  backingVolume: 2,
  pianoName: null,
  vocalsOff: [],
  click: {},
  presets: {},
};

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch { /* storage blocked or corrupt: use the defaults */ }
  return structuredClone(DEFAULTS);
}

export function saveSettings(s: Settings): void {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* not saved; still works */ }
}

export function toggleIn(list: string[], id: string, on: boolean): string[] {
  const rest = list.filter((x) => x !== id);
  return on ? [...rest, id] : rest;
}
