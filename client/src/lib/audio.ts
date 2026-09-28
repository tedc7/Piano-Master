// Audio Engine (arch §4): stems, metronome and count-in clicks, and a simple tone for Listen
// mode. Plain Web Audio, the API the feasibility tests proved in MIDIWeb Browser.
import type { Media, Preset } from "./types";

export interface StemBuffers { vocals: AudioBuffer; accompaniment: AudioBuffer }

interface Playing { src: AudioBufferSourceNode; gain: GainNode }

export class AudioEngine {
  ctx: AudioContext | null = null;
  private master!: GainNode;
  private vocalBus!: GainNode;
  private backingBus!: GainNode;
  private clickBus!: GainNode;
  private toneBus!: GainNode;
  private stems = new Map<string, StemBuffers>();
  private loading = new Map<string, Promise<StemBuffers>>();
  private playing: Playing[] = [];
  mix = { vocals: true, backing: true, backingVolume: 2 };

  /** Create or resume the audio context; call from a tap (iPadOS starts it suspended). */
  async ensure(): Promise<AudioContext> {
    const ctx = this.create();
    if (ctx.state !== "running") await ctx.resume();
    return ctx;
  }

  /** Create the context without resuming it: enough for decoding, and safe without a tap
   *  (resume() before a tap can stay pending on iPadOS). */
  create(): AudioContext {
    if (!this.ctx) {
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AC({ latencyHint: "interactive" });
      this.ctx = ctx;
      this.master = ctx.createGain();
      this.master.connect(ctx.destination);
      this.vocalBus = this.bus();
      this.backingBus = this.bus();
      this.clickBus = this.bus(0.5);
      this.toneBus = this.bus(0.35);
      this.applyMix();
      // after a lock or app switch iPadOS marks the context "interrupted"; resume on return
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden && this.ctx && this.ctx.state !== "running") void this.ctx.resume();
      });
    }
    return this.ctx;
  }

  private bus(gain = 1): GainNode {
    const g = this.ctx!.createGain();
    g.gain.value = gain;
    g.connect(this.master);
    return g;
  }

  applyMix(): void {
    if (!this.ctx) return;
    this.vocalBus.gain.value = this.mix.vocals ? 1 : 0;
    this.backingBus.gain.value = this.mix.backing ? this.mix.backingVolume : 0;
  }

  /** The audio-context time being heard at performance time `perfMs`. Uses the output time
   *  stamp only when fresh: after a sleep a stale one once jumped the clock minutes ahead. */
  outputTimeAt(perfMs: number): number {
    const ctx = this.ctx!;
    const now = performance.now();
    if (typeof ctx.getOutputTimestamp === "function") {
      const ts = ctx.getOutputTimestamp();
      if (ts.performanceTime && ts.contextTime !== undefined && ts.performanceTime > 0 &&
          now - ts.performanceTime < 250 && ctx.state === "running") {
        return ts.contextTime + (perfMs - ts.performanceTime) / 1000;
      }
    }
    return ctx.currentTime - (ctx.outputLatency || 0) - (ctx.baseLatency || 0) + (perfMs - now) / 1000;
  }

  hasStems(pieceId: string, preset: Preset): boolean {
    return this.stems.has(pieceId + "/" + preset);
  }

  /** Fetch and decode one tempo version's stems; `onProgress` gets 0..1. */
  loadStems(pieceId: string, media: Media, preset: Preset, onProgress?: (f: number) => void): Promise<StemBuffers> {
    const key = pieceId + "/" + preset;
    const done = this.stems.get(key);
    if (done) return Promise.resolve(done);
    const busy = this.loading.get(key);
    if (busy) return busy;
    const st = media.presets[preset];
    if (!st) return Promise.reject(new Error(`no ${preset}% stems`));
    const total = st.vocals.bytes + st.accompaniment.bytes;
    let got = 0;
    const fetchOne = async (url: string) => {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
      if (!r.body) return r.arrayBuffer();
      const reader = r.body.getReader();
      const chunks: Uint8Array[] = [];
      let n = 0;
      for (;;) {
        const { done: end, value } = await reader.read();
        if (end) break;
        chunks.push(value);
        n += value.length;
        got += value.length;
        onProgress?.(Math.min(0.99, got / total));
      }
      const out = new Uint8Array(n);
      let o = 0;
      for (const c of chunks) { out.set(c, o); o += c.length; }
      return out.buffer;
    };
    const p = (async () => {
      const ctx = this.create();
      const [v, a] = await Promise.all([fetchOne(st.vocals.url), fetchOne(st.accompaniment.url)]);
      const [vocals, accompaniment] = await Promise.all([ctx.decodeAudioData(v), ctx.decodeAudioData(a)]);
      const bufs = { vocals, accompaniment };
      this.stems.set(key, bufs);
      onProgress?.(1);
      return bufs;
    })();
    this.loading.set(key, p);
    p.finally(() => this.loading.delete(key)).catch(() => {});
    return p;
  }

  /** Start both stems so that stem time `offset` sounds at context time `when`, fading in over
   *  `fade` seconds just before it. */
  startStems(bufs: StemBuffers, offset: number, when: number, fade: number): void {
    const ctx = this.ctx!;
    for (const [buf, bus] of [[bufs.vocals, this.vocalBus], [bufs.accompaniment, this.backingBus]] as const) {
      const src = ctx.createBufferSource();
      const gain = ctx.createGain();
      src.buffer = buf;
      src.connect(gain);
      gain.connect(bus);
      let start = when - fade;
      let from = offset - fade;
      if (from < 0) { start -= from; from = 0; }     // before the stem's own start: wait for it
      const t = Math.max(start, ctx.currentTime);
      gain.gain.setValueAtTime(fade > 0 ? 0 : 1, t);
      if (fade > 0) gain.gain.linearRampToValueAtTime(1, Math.max(t + 0.005, when));
      if (from < buf.duration) src.start(t, from + (t - start));
      this.playing.push({ src, gain });
    }
  }

  stopStems(fade: number): void {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    for (const p of this.playing) {
      try {
        p.gain.gain.cancelScheduledValues(now);
        p.gain.gain.setValueAtTime(p.gain.gain.value, now);
        p.gain.gain.linearRampToValueAtTime(0, now + fade);
        p.src.stop(now + fade + 0.02);
      } catch { /* not started or already stopped */ }
    }
    this.playing = [];
  }

  /** A metronome click; `level` 1 = normal, lower for the soft pulse during a rewind glide. */
  click(when: number, accent: boolean, level = 1): void {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = accent ? 1760 : 1320;
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, level), when + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.04);
    o.connect(g);
    g.connect(this.clickBus);
    o.start(when);
    o.stop(when + 0.05);
  }

  /** A soft piano-like tone for Listen mode (not a piano sample; the choir voice and chord pad
   *  for songs without stems come in M8). */
  tone(pitch: number, when: number, seconds: number, level = 1): void {
    const ctx = this.ctx!;
    const f = 440 * Math.pow(2, (pitch - 69) / 12);
    const g = ctx.createGain();
    const end = when + Math.max(0.15, seconds);
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(0.6 * level, when + 0.01);
    g.gain.exponentialRampToValueAtTime(0.25 * level, when + 0.25);
    g.gain.setValueAtTime(0.25 * level, Math.max(when + 0.25, end - 0.08));
    g.gain.exponentialRampToValueAtTime(0.0001, end);
    g.connect(this.toneBus);
    for (const [type, mult, amp] of [["triangle", 1, 1], ["sine", 2, 0.3]] as const) {
      const o = ctx.createOscillator();
      const og = ctx.createGain();
      o.type = type;
      o.frequency.value = f * mult;
      og.gain.value = amp;
      o.connect(og);
      og.connect(g);
      o.start(when);
      o.stop(end + 0.02);
    }
  }
}
