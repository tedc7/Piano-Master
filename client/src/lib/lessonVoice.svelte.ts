// The lesson voice (arch §10.5, v0.34): every line the lesson screen reads is recorded ahead of time
// (tools/voice, Kokoro's Heart at 80% speed) and played through the audio engine, like a song's
// vocal. The build's lessons/voice.json maps each line shown to its recording; a line with none (a
// new lesson not recorded yet) is read by the device's own voice, as before v0.34.
import type { AudioEngine } from "./audio";

let index: Promise<Record<string, string>> | null = null;
function voiceIndex(): Promise<Record<string, string>> {
  index ??= fetch("content/lessons/voice.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => { index = null; return {}; });
  return index;
}

/** Waits for the audio to be running, but not for ever: before the first tap it can't start. */
async function running(audio: AudioEngine, ms: number): Promise<boolean> {
  const ctx = audio.create();
  if (ctx.state === "running") return true;
  await Promise.race([audio.ensure(), new Promise((r) => setTimeout(r, ms))]);
  return (ctx.state as AudioContextState) === "running";   // it may have changed while waiting
}

export class LessonVoice {
  /** Something is being read aloud now (the Read it to me button becomes Stop reading). */
  speaking = $state(false);
  /** What was read, and how, for the browser check. */
  readonly log: { text: string; by: "recording" | "device" }[] = [];
  private turn = 0;
  private stopClip: (() => void) | null = null;
  private ended: ((finished: boolean) => void) | null = null;

  constructor(private audio: AudioEngine) {}

  /** Fetch and decode these lines' recordings now, so reading starts at once. */
  async preload(texts: string[]): Promise<void> {
    const files = await voiceIndex();
    for (const t of texts) if (files[t]) this.audio.loadClip(`content/lessons/${files[t]}`).catch(() => {});
  }

  /** Read a line aloud, stopping whatever was being read. Resolves true when it has been read to
   *  the end, false when it was stopped (Stop reading, another line, leaving the card). */
  speak(text: string): Promise<boolean> {
    this.stop();
    if (!text) return Promise.resolve(false);
    const turn = ++this.turn;
    this.speaking = true;
    const ended = new Promise<boolean>((r) => { this.ended = r; });
    void this.start(text, turn);
    return ended;
  }

  private async start(text: string, turn: number): Promise<void> {
    const files = await voiceIndex();
    if (turn !== this.turn) return;
    if (files[text]) {
      try {
        const buf = await this.audio.loadClip(`content/lessons/${files[text]}`);
        if (turn !== this.turn) return;
        if (await running(this.audio, 1500)) {
          if (turn !== this.turn) return;
          this.stopClip = this.audio.playClip(buf, () => { if (turn === this.turn) this.done(); });
          this.log.push({ text, by: "recording" });
          return;
        }
      } catch { /* the device's voice reads it */ }
      if (turn !== this.turn) return;
    }
    this.device(text, turn);
  }

  /** Stop reading. */
  stop(): void {
    this.turn++;
    this.stopClip?.();
    this.stopClip = null;
    try { speechSynthesis.cancel(); } catch { /* no speech on this device */ }
    this.speaking = false;
    this.settle(false);
  }

  private done(): void {
    this.stopClip = null;
    this.speaking = false;
    this.settle(true);
  }

  private settle(finished: boolean): void {
    const e = this.ended;
    this.ended = null;
    e?.(finished);
  }

  private device(text: string, turn: number): void {
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.onend = u.onerror = () => { if (turn === this.turn) this.done(); };
      speechSynthesis.speak(u);
      this.log.push({ text, by: "device" });
    } catch {
      this.done();             // no speech on this device
    }
  }
}
