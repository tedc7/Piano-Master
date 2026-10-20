import { describe, expect, it } from "vitest";
import { FRAME, NoteDetector, fft, hzOf, type DetectedNote } from "../src/lib/pitch";

const SR = 48000;
const HOP = 480;     // 10 ms, as the microphone input runs it

interface Tone { pitch: number; start: number; dur: number; amp?: number }

/** A piano-like tone: a fast attack, harmonics falling off as 1/h, an exponential decay, and a
 *  short release when the key comes up. */
function piano(t: number, n: Tone): number {
  const dt = t - n.start;
  if (dt < 0) return 0;
  const attack = Math.min(1, dt / 0.005);
  const release = dt > n.dur ? Math.max(0, 1 - (dt - n.dur) / 0.05) : 1;
  if (release === 0) return 0;
  const f = hzOf(n.pitch);
  let s = 0;
  for (let h = 1; h <= 10 && f * h < SR / 2; h++) s += Math.sin(2 * Math.PI * f * h * dt) / h;
  return (n.amp ?? 0.1) * attack * release * Math.exp(-dt / 1.2) * s;
}

/** A seeded random source, so the noise is the same every run. */
function rng(seed = 1): () => number {
  let x = seed;
  return () => ((x = (x * 1103515245 + 12345) % 2147483648) / 2147483648) * 2 - 1;
}

/** Render `seconds` of audio from a sample function and run the detector over it every 10 ms. */
function listen(seconds: number, at: (t: number, i: number) => number,
                opts: { sensitivity?: 1 | 2 | 3; masked?: (p: number) => boolean; output?: (t: number) => number } = {}): DetectedNote[] {
  const total = Math.round(seconds * SR);
  const audio = new Float32Array(total + FRAME);
  for (let i = 0; i < total; i++) audio[FRAME + i] = at(i / SR, i);
  const output = opts.output ? new Float32Array(total + FRAME) : null;
  if (output) for (let i = 0; i < total; i++) output[FRAME + i] = opts.output!(i / SR);
  const d = new NoteDetector(SR, 36, 96, opts.sensitivity ?? 2);
  const out: DetectedNote[] = [];
  for (let end = FRAME + HOP; end <= audio.length; end += HOP) {
    out.push(...d.process(audio.subarray(end - FRAME, end), ((end - FRAME) / SR) * 1000, opts.masked, output?.subarray(end - FRAME, end)));
  }
  return out;
}

const ons = (ev: DetectedNote[]) => ev.filter((e) => e.type === "on");

/** A small keyboard heard through the iPad (as reported from the family's JK-825, Oct 2026): the
 *  speakers roll off below about 180 Hz, so the low keys have almost no fundamental; the top keys
 *  are nearly pure tones; and the tuning is stretched a little at both ends. */
function smallKeyboard(t: number, n: Tone): number {
  const dt = t - n.start;
  if (dt < 0) return 0;
  const release = dt > n.dur ? Math.max(0, 1 - (dt - n.dur) / 0.05) : 1;
  if (release === 0) return 0;
  const stretch = n.pitch > 72 ? (n.pitch - 72) * 0.6 : n.pitch < 48 ? (n.pitch - 48) * 0.5 : 0;   // cents
  const f = hzOf(n.pitch) * Math.pow(2, stretch / 1200);
  const speaker = (hz: number) => { const r = (hz / 180) ** 2; return r / (1 + r); };
  const bright = n.pitch > 76 ? 3 : 1;      // the top keys' harmonics fall away fast
  let s = 0;
  for (let h = 1; h <= 10 && f * h < SR / 2; h++) s += (speaker(f * h) * Math.sin(2 * Math.PI * f * h * dt)) / Math.pow(h, bright);
  return (n.amp ?? 0.1) * Math.min(1, dt / 0.005) * release * Math.exp(-dt / (n.pitch > 76 ? 0.5 : 1.2)) * s;
}
const room = rng(7);
/** A quiet room: hiss and mains hum. */
const background = (t: number) => 0.003 * room() + 0.004 * Math.sin(2 * Math.PI * 60 * t);

describe("fft", () => {
  it("finds a sine at its bin", () => {
    const n = 64, re = new Float64Array(n), im = new Float64Array(n);
    for (let i = 0; i < n; i++) re[i] = Math.cos((2 * Math.PI * 5 * i) / n);
    fft(re, im);
    expect(Math.hypot(re[5], im[5])).toBeCloseTo(n / 2, 6);
    expect(Math.hypot(re[6], im[6])).toBeCloseTo(0, 6);
  });
});

describe("NoteDetector", () => {
  it("hears one key: one key-down soon after it is struck, and a key-up after it is let go", () => {
    const n: Tone = { pitch: 60, start: 0.5, dur: 0.6 };
    const ev = listen(2, (t) => piano(t, n) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([60]);
    const on = ons(ev)[0];
    expect(on.timeMs).toBeGreaterThanOrEqual(485);   // timed from the rise, to about 5 ms
    expect(on.timeMs).toBeLessThan(560);
    expect(on.sure).toBe(true);
    const off = ev.find((e) => e.type === "off" && e.pitch === 60)!;
    expect(off.timeMs).toBeGreaterThan(1100);
    expect(off.timeMs).toBeLessThan(1300);
  });

  it("hears each key of a chord, not the chord's octaves and fifths", () => {
    const chord = [60, 64, 67].map((pitch): Tone => ({ pitch, start: 0.4, dur: 0.8 }));
    const ev = listen(1.6, (t) => chord.reduce((s, n) => s + piano(t, n), 0) + background(t));
    expect(ons(ev).map((e) => e.pitch).sort()).toEqual([60, 64, 67]);
    expect(ons(ev).every((e) => e.sure)).toBe(true);
  });

  it("hears two hands a tenth apart", () => {
    const both = [48, 64].map((pitch): Tone => ({ pitch, start: 0.4, dur: 0.8 }));
    const ev = listen(1.6, (t) => both.reduce((s, n) => s + piano(t, n), 0) + background(t));
    expect(ons(ev).map((e) => e.pitch).sort()).toEqual([48, 64]);
  });

  it.each([[43], [48], [55], [72], [79], [84]])("hears key %i alone", (pitch) => {
    const n: Tone = { pitch, start: 0.3, dur: 0.5 };
    const ev = listen(1.2, (t) => piano(t, n) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([pitch]);
  });

  it("follows a melody, and hears the same key struck twice in a row", () => {
    const tune: Tone[] = [[60, 0.3], [62, 0.7], [64, 1.1], [64, 1.5], [60, 1.9]].map(([pitch, start]) => ({ pitch, start, dur: 0.35 }));
    const ev = listen(2.6, (t) => tune.reduce((s, n) => s + piano(t, n), 0) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([60, 62, 64, 64, 60]);
  });

  it("follows a legato melody, each key held until the next is struck", () => {
    const tune: Tone[] = [60, 62, 64, 65, 67, 65, 64, 62, 60].map((pitch, i) => ({ pitch, start: 0.3 + i * 0.3, dur: 0.32 }));
    const ev = listen(3.4, (t) => tune.reduce((s, n) => s + piano(t, n), 0) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([60, 62, 64, 65, 67, 65, 64, 62, 60]);
  });

  it("hears a key struck again while it still rings", () => {
    const a: Tone = { pitch: 67, start: 0.3, dur: 1.5 }, b: Tone = { pitch: 67, start: 0.9, dur: 0.6, amp: 0.15 };
    const ev = listen(2.2, (t) => (t < 0.9 ? piano(t, a) : piano(t, a) * 0.3 + piano(t, b)) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([67, 67]);
  });

  it("hears every key of a small keyboard through the iPad, lowest to highest, each once", () => {
    const keys = Array.from({ length: 61 }, (_, i) => 36 + i);
    const tune = keys.map((pitch, i): Tone => ({ pitch, start: 0.3 + i * 0.5, dur: 0.4 }));
    const ev = ons(listen(0.3 + keys.length * 0.5 + 0.3, (t) => {
      const i = Math.floor((t - 0.3) / 0.5);
      return [i - 1, i].reduce((s, k) => (k >= 0 && k < tune.length ? s + smallKeyboard(t, tune[k]) : s), 0) + background(t);
    }));
    const heard = ev.map((e) => e.pitch);
    const missed = keys.filter((k) => !heard.includes(k));
    const extra = heard.filter((p, i) => heard.indexOf(p) !== i || !keys.includes(p));
    expect({ missed, extra }).toEqual({ missed: [], extra: [] });
    expect(heard).toEqual(keys);
  });

  describe("the family's keyboard through the iPad, as recorded (Oct 2026)", () => {
    // Measured from a recording of every key: the sound is strongest around 550 Hz and falls
    // away steeply below it (C3's fundamental is gone, G3's is 9 dB down) and above it to about
    // -22 dB, so low keys are heard by their overtones, and the top keys as nearly pure tones;
    // the partials are stretched by the strings' stiffness.
    const heardAt = (hz: number) => {
      const o = Math.log2(hz / 550);
      return Math.max(o > 0 ? 0.08 : 0, Math.exp(-(o * o) / (o > 0 ? 0.5 : 1.28)));
    };
    const ipadKey = (t: number, n: Tone) => {
      const dt = t - n.start;
      if (dt < 0) return 0;
      const release = dt > n.dur ? Math.max(0, 1 - (dt - n.dur) / 0.05) : 1;
      if (release === 0) return 0;
      const f0 = hzOf(n.pitch);
      let s = 0;
      for (let h = 1; h <= 30; h++) {
        const hz = h * f0 * Math.sqrt(1 + 8e-5 * h * h);
        if (hz > 6000) break;
        s += (heardAt(hz) * Math.sin(2 * Math.PI * hz * dt)) / h;
      }
      return (n.amp ?? 0.1) * Math.min(1, dt / 0.005) * release * Math.exp(-dt / (n.pitch > 76 ? 0.4 : 1.0)) * s;
    };
    const play = (tones: Tone[], seconds: number) =>
      ons(listen(seconds, (t) => tones.reduce((s, n) => (t >= n.start - 0.01 && t < n.start + n.dur + 0.1 ? s + ipadKey(t, n) : s), 0) + background(t)));

    it("hears every key from C2 to C7, each once (below C2 the overtones are too close to tell apart in 85 ms)", () => {
      const keys = Array.from({ length: 61 }, (_, i) => 36 + i);
      const ev = play(keys.map((pitch, i) => ({ pitch, start: 0.3 + i * 0.45, dur: 0.38 })), 0.6 + keys.length * 0.45);
      const heard = ev.map((e) => e.pitch);
      expect({ missed: keys.filter((k) => !heard.includes(k)), extra: heard.filter((p, i) => heard.indexOf(p) !== i || !keys.includes(p)) })
        .toEqual({ missed: [], extra: [] });
    });

    it("hears the left hand's low keys as themselves, not the octave above", () => {
      const left: Tone[] = [48, 43, 45, 48, 41, 40, 38, 36].map((pitch, i) => ({ pitch, start: 0.3 + i * 0.5, dur: 0.42 }));
      expect(play(left, 4.6).map((e) => e.pitch)).toEqual([48, 43, 45, 48, 41, 40, 38, 36]);
    });

    it("hears a chord as its keys, not as a low key whose overtones they are", () => {
      const chord = [60, 64, 67].map((pitch): Tone => ({ pitch, start: 0.3, dur: 0.8 }));
      expect(play(chord, 1.4).map((e) => e.pitch).sort()).toEqual([60, 64, 67]);
      const tenth = [48, 64].map((pitch): Tone => ({ pitch, start: 0.3, dur: 0.8 }));
      expect(play(tenth, 1.4).map((e) => e.pitch).sort()).toEqual([48, 64]);
    });
  });

  it("ignores the steady background of the room", () => {
    const fan = rng(3);
    const ev = listen(3, (t) => 0.02 * fan() + 0.02 * Math.sin(2 * Math.PI * 120 * t) + background(t));
    expect(ons(ev)).toEqual([]);
  });

  it("ignores a bang, a clap or a door: loud and short, with no pitch", () => {
    const burst = rng(11);
    const ev = listen(2, (t) => ((t > 0.5 && t < 0.56) || (t > 1.2 && t < 1.22) ? 0.5 * burst() : 0) + background(t));
    expect(ons(ev)).toEqual([]);
  });

  it("ignores a voice sliding between keys", () => {
    // a voice-like tone gliding from 180 to 300 Hz: harmonic, but never steady on a key
    let phase = 0;
    const ev = listen(2, (t) => {
      const f = 180 + 120 * (t / 2) + 15 * Math.sin(2 * Math.PI * 5.5 * t);
      phase += (2 * Math.PI * f) / SR;
      let s = 0;
      for (let h = 1; h <= 8; h++) s += Math.sin(h * phase) / h;
      return 0.08 * s + background(t);
    });
    expect(ons(ev).length).toBeLessThanOrEqual(1);
  });

  it("still hears the key through a noisy room", () => {
    const fan = rng(5);
    const n: Tone = { pitch: 65, start: 1.0, dur: 0.5 };
    const ev = listen(2, (t) => piano(t, n) + 0.03 * fan() + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([65]);
  });

  it("times every key alike, so one latency offset fits all", () => {
    const tune: Tone[] = [55, 60, 64, 67, 72, 67, 64, 60].map((pitch, i) => ({ pitch, start: 0.3 + i * 0.27, dur: 0.25 }));
    const ev = ons(listen(2.8, (t) => tune.reduce((s, n) => s + piano(t, n), 0) + background(t)));
    expect(ev.map((e) => e.pitch)).toEqual(tune.map((n) => n.pitch));
    expect(ev.every((e) => e.sure)).toBe(true);
    const late = ev.map((e, i) => e.timeMs - tune[i].start * 1000);
    expect(Math.max(...late) - Math.min(...late)).toBeLessThan(20);
    for (const ms of late) expect(Math.abs(ms)).toBeLessThan(30);
  });

  it("hears a keyboard a little out of tune", () => {
    const tune: Tone[] = [60, 64, 67].map((pitch, i) => ({ pitch: pitch + 0.15, start: 0.3 + i * 0.4, dur: 0.35 }));
    const ev = listen(1.6, (t) => tune.reduce((s, n) => s + piano(t, n), 0) + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([60, 64, 67]);
  });

  it("follows legato through a noisy room", () => {
    const fan = rng(9);
    const tune: Tone[] = [64, 65, 67, 65, 64, 62, 60].map((pitch, i) => ({ pitch, start: 0.5 + i * 0.3, dur: 0.32 }));
    const ev = listen(3, (t) => tune.reduce((s, n) => s + piano(t, n), 0) + 0.02 * fan() + background(t));
    expect(ons(ev).map((e) => e.pitch)).toEqual([64, 65, 67, 65, 64, 62, 60]);
  });

  // Talking as loud as the piano, in a voice as plain as a piano tone, is this detector's worst
  // case: a syllable starting on a key's pitch looks like a struck key. The parent's guidance
  // asks for no talking while a child plays.
  it("rarely takes talking for keys (1 syllable in 6 at most), and rarely surely", () => {
    // syllables: a voice starting and stopping, its pitch falling through each one
    let phase = 0;
    const ev = listen(4, (t) => {
      const syl = Math.floor(t / 0.22), at = t - syl * 0.22;
      const f = 140 + 60 * Math.sin(syl * 1.7) - 120 * at;
      phase += (2 * Math.PI * f) / SR;
      const env = at < 0.17 ? Math.min(1, at / 0.03) : 0;
      let s = 0;
      for (let h = 1; h <= 10; h++) s += Math.sin(h * phase) / h;
      return 0.1 * env * s + background(t);
    });
    expect(ons(ev).length).toBeLessThanOrEqual(3);     // of 18 syllables
    expect(ons(ev).filter((e) => e.sure).length).toBeLessThanOrEqual(2);     // of 18
  });

  it("keeps up: a frame takes well under the 10 ms between frames", () => {
    const chord = [48, 60, 64, 67].map((pitch): Tone => ({ pitch, start: 0.1, dur: 2 }));
    const t0 = performance.now();
    listen(2, (t) => chord.reduce((s, n) => s + piano(t, n), 0) + background(t));
    const perFrame = (performance.now() - t0) / 200;
    expect(perFrame).toBeLessThan(3);
  });

  describe("with the app's vocals and backing playing", () => {
    // the song: a sung melody (with vibrato) over a soft backing, as the app plays it; the
    // microphone hears it back from the speakers, late and with the room's echo, with no help from
    // the browser's echo cancellation
    const melody: Tone[] = [60, 60, 67, 67, 69, 69, 67].map((pitch, i) => ({ pitch, start: 0.6 + i * 0.4, dur: 0.36 }));
    const backing: Tone[] = [[48, 0.6], [55, 0.6], [53, 1.4], [48, 2.2]].map(([pitch, start]) => ({ pitch, start, dur: 0.75, amp: 0.05 }));
    const sing = (t: number) => {
      const n = melody.find((m) => t >= m.start && t < m.start + m.dur);
      if (!n) return 0;
      const dt = t - n.start, f = hzOf(n.pitch) * (1 + 0.006 * Math.sin(2 * Math.PI * 5.5 * dt));
      let s = 0;
      for (let h = 1; h <= 8; h++) s += Math.sin(2 * Math.PI * f * h * dt) / h;
      return 0.1 * Math.min(1, dt / 0.04) * s;
    };
    // the count-in: the app's clicks, from which the detector learns how loud its sound comes back
    const click = (t: number) => [0, 0.15, 0.3, 0.45].reduce((s, c) => s + (t >= c && t < c + 0.04 ? 0.3 * Math.sin(2 * Math.PI * 1320 * (t - c)) : 0), 0);
    const song = (t: number) => click(t) + sing(t) + backing.reduce((s, n) => s + piano(t, n), 0);
    const heard = (t: number) => 0.3 * song(t - 0.03) + 0.1 * song(t - 0.08) + background(t);

    it("does not take the app's own singing and backing for keys", () => {
      expect(ons(listen(3.6, heard, { output: song }))).toEqual([]);
    });

    it("hears the child playing the tune along with the singing", () => {
      const child = melody.map((n) => ({ ...n, start: n.start + 0.01 }));
      const ev = listen(3.6, (t) => heard(t) + child.reduce((s, n) => s + piano(t, n), 0), { output: song });
      expect(ons(ev).map((e) => e.pitch)).toEqual(melody.map((n) => n.pitch));
    });

    it("hears the child's wrong keys over the music, surely", () => {
      const child: Tone[] = [[62, 0.62], [64, 1.42], [65, 2.22]].map(([pitch, start]) => ({ pitch, start, dur: 0.35 }));
      const ev = ons(listen(3.6, (t) => heard(t) + child.reduce((s, n) => s + piano(t, n), 0), { output: song }));
      expect(ev.map((e) => e.pitch)).toEqual([62, 64, 65]);
      expect(ev.every((e) => e.sure)).toBe(true);
    });

    it("without the app's output to compare, the singing would be heard as keys", () => {
      expect(ons(listen(3.6, heard)).length).toBeGreaterThan(0);
    });
  });

  it("does not report keys the app is sounding itself", () => {
    const n: Tone = { pitch: 60, start: 0.3, dur: 0.5 };
    const ev = listen(1.2, (t) => piano(t, n) + background(t), { masked: (p) => p === 60 });
    expect(ons(ev)).toEqual([]);
  });

  it("hears a soft key only at a higher sensitivity", () => {
    const n: Tone = { pitch: 62, start: 0.3, dur: 0.5, amp: 0.006 };
    const sig = (t: number) => piano(t, n) + 0.3 * background(t);
    expect(ons(listen(1.2, sig, { sensitivity: 1 }))).toEqual([]);
    expect(ons(listen(1.2, sig, { sensitivity: 3 })).map((e) => e.pitch)).toEqual([62]);
  });

  it("gives louder keys a higher velocity", () => {
    const vel = (amp: number) => ons(listen(1, (t) => piano(t, { pitch: 60, start: 0.3, dur: 0.4, amp }) + background(t)))[0].velocity;
    expect(vel(0.2)).toBeGreaterThan(vel(0.03));
  });
});
