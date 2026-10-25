// A recording for tuning the microphone input (arch §4 "Microphone input"): what the microphone
// hears and what the app played meanwhile, with the keys the app heard, sent to the piano
// server's client log in 5-second parts for tools/mic_recording.py and tools/mic_replay.ts. Made
// from the piano check, or from the Play screen's settings sheet while a song plays; it carries on
// when the sheet closes.
import { api } from "./api";
import { app } from "./app.svelte.js";

export const RECORD_S = 60;

/** 16-bit at half the rate (24 kHz from 48 kHz: plenty for a piano's keys), base64, by part. */
function encode(samples: Float32Array, half: boolean): Int16Array {
  const n = half ? Math.floor(samples.length / 2) : samples.length;
  const pcm = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    const x = half ? (samples[2 * i] + samples[2 * i + 1]) / 2 : samples[i];
    pcm[i] = Math.max(-32768, Math.min(32767, Math.round(x * 32767)));
  }
  return pcm;
}

function base64(pcm: Int16Array, from: number, count: number): string {
  const bytes = new Uint8Array(pcm.buffer, from * 2, count * 2);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

class MicRecorder {
  state = $state<"" | "recording" | "sending" | "sent" | "failed">("");
  progress = $state(0);
  note = $state("");

  get busy(): boolean {
    return this.state === "recording" || this.state === "sending";
  }

  /** Record RECORD_S seconds and send them; `context` says where (the piano check, a song). */
  async start(context: Record<string, unknown>): Promise<void> {
    if (this.busy) return;
    this.state = "recording";
    this.note = "";
    this.progress = 0;
    const rec = await app.mic.record(RECORD_S, (f) => { this.progress = f; });
    if (!rec) { this.state = "failed"; this.note = "The microphone isn't on."; return; }
    this.state = "sending";
    const half = rec.rate >= 44100, rate = half ? rec.rate / 2 : rec.rate;
    const mic = encode(rec.samples, half), out = encode(rec.output, half);
    const id = crypto.randomUUID?.() ?? String(Date.now());
    const per = rate * 5, parts = Math.ceil(mic.length / per);
    for (let k = 0; k < parts; k++) {
      const count = Math.min(per, mic.length - k * per);
      const ok = await api.logNow("mic recording", {
        id, part: k, parts, rate, pcm16: base64(mic, k * per, count), out16: base64(out, k * per, Math.min(count, out.length - k * per)),
        ...(k === 0 && { keys: rec.keys, settings: rec.settings, context }),
      });
      if (!ok) { this.state = "failed"; this.note = `Sending part ${k + 1} of ${parts} failed: try again.`; return; }
      this.progress = (k + 1) / parts;
    }
    this.state = "sent";
    this.note = `Sent (recording ${id.slice(0, 8)}, ${rec.keys.filter((e) => e.type === "on").length} keys heard).`;
  }

  get label(): string {
    return this.state === "recording" ? `Recording… ${Math.ceil(RECORD_S * (1 - this.progress))} s`
      : this.state === "sending" ? `Sending… ${Math.round(this.progress * 100)}%` : "Record and send";
  }
}

export const micRecorder = new MicRecorder();
