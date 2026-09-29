// On-screen keyboard (arch §3): 2 to 4 octaves around the piece's range. The next keys to play
// are shown in the hand's colour with the finger number; pressed keys light up live from MIDI.
import type { Hand } from "./types";

const BLACK = new Set([1, 3, 6, 8, 10]);
export const isBlack = (p: number) => BLACK.has(((p % 12) + 12) % 12);

const SHARP_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const FLAT_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
export function noteName(pitch: number, flats = false): string {
  return (flats ? FLAT_NAMES : SHARP_NAMES)[((pitch % 12) + 12) % 12];
}

/** Whole octaves C..B around [lo, hi], at least 2 and at most 4 (or the whole range if wider). */
export function keyboardRange(lo: number, hi: number): [number, number] {
  let a = lo - (((lo % 12) + 12) % 12);           // the C at or below lo
  let b = hi + (11 - (((hi % 12) + 12) % 12));    // the B at or above hi
  while ((b - a + 1) / 12 < 2) {
    // grow on the side with less room around the notes, so the notes sit near the middle
    if (lo - a <= b - hi) a -= 12; else b += 12;
  }
  return [a, b];
}

export type PressKind = "ok" | "late" | "wrong" | "neutral";

export interface Target { pitch: number; hand: Hand; finger?: number }

export class KeyboardView {
  readonly el: HTMLDivElement;
  private keys = new Map<number, HTMLDivElement>();
  private targets: Target[] = [];

  constructor(host: HTMLElement, readonly lo: number, readonly hi: number) {
    this.el = document.createElement("div");
    this.el.className = "kb";
    host.appendChild(this.el);
    const whites: number[] = [];
    for (let p = lo; p <= hi; p++) if (!isBlack(p)) whites.push(p);
    const ww = 100 / whites.length;
    whites.forEach((p, i) => {
      const k = this.key(p, "kb-w");
      k.style.left = `${i * ww}%`;
      k.style.width = `${ww}%`;
      if (p % 12 === 0) {
        const label = document.createElement("span");
        label.className = "kb-c";
        label.textContent = p === 60 ? "C·" : "C";
        k.appendChild(label);
      }
    });
    whites.forEach((p, i) => {
      if (p + 1 <= hi && isBlack(p + 1)) {
        const k = this.key(p + 1, "kb-b");
        k.style.left = `${(i + 1) * ww - ww * 0.3}%`;
        k.style.width = `${ww * 0.6}%`;
      }
    });
  }

  private key(p: number, cls: string): HTMLDivElement {
    const k = document.createElement("div");
    k.className = cls;
    k.dataset.pitch = String(p);
    const f = document.createElement("span");
    f.className = "kb-f";
    k.appendChild(f);
    this.el.appendChild(k);
    this.keys.set(p, k);
    return k;
  }

  setTargets(next: Target[]): void {
    const same = next.length === this.targets.length &&
      next.every((t, i) => t.pitch === this.targets[i].pitch && t.hand === this.targets[i].hand && t.finger === this.targets[i].finger);
    if (same) return;
    for (const t of this.targets) {
      const k = this.keys.get(t.pitch);
      if (!k) continue;
      k.classList.remove("kb-t-R", "kb-t-L");
      (k.querySelector(".kb-f") as HTMLElement).textContent = "";
    }
    this.targets = next;
    for (const t of next) {
      const k = this.keys.get(t.pitch);
      if (!k) continue;
      k.classList.add(`kb-t-${t.hand}`);
      (k.querySelector(".kb-f") as HTMLElement).textContent = t.finger ? String(t.finger) : "";
    }
  }

  press(pitch: number, kind: PressKind): void {
    const k = this.keys.get(pitch);
    if (!k) return;
    k.classList.remove("kb-ok", "kb-late", "kb-wrong", "kb-neutral");
    k.classList.add(`kb-${kind}`);
  }

  /** Add or remove an extra class on one key (the piano check marks the keys it has heard). */
  mark(pitch: number, cls: string, on = true): void {
    this.keys.get(pitch)?.classList.toggle(cls, on);
  }

  release(pitch: number): void {
    this.keys.get(pitch)?.classList.remove("kb-ok", "kb-late", "kb-wrong", "kb-neutral");
  }

  /** Taps on the on-screen keys (concept lessons' Check card: "tap the right key"). */
  onTap(fn: (pitch: number) => void): void {
    this.el.addEventListener("pointerdown", (e) => {
      const k = (e.target as HTMLElement).closest("[data-pitch]") as HTMLElement | null;
      if (k) fn(Number(k.dataset.pitch));
    });
  }

  destroy(): void {
    this.el.remove();
  }
}
