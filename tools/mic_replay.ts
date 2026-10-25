// Replay a microphone recording through the note detector (client/src/lib/pitch.ts) and score it
// against the keys played, for tuning the microphone input to a real keyboard (arch §4).
//
//   export PATH="$PWD/.tools/node/bin:$PATH"
//   node --experimental-transform-types tools/mic_replay.ts <rec>.wav <rec>.keys.json|- [sensitivity] [-v] [-x]
//
// The recording comes from tools/mic_recording.py; when <rec>.out.wav is beside it (what the app
// played meanwhile), the detector gets it as it does in the app. The keys file maps each key played
// to when it was struck, in seconds ({"60": 23.47, ...}), labelled by hand from the recording's
// onsets and spectra; with "-" the keys heard are only listed. -v lists every key, -x the wrong
// key-downs. Recordings stay out of the repo (tests-output/mic/).
import { existsSync, readFileSync } from "node:fs";
import { FRAME, NoteDetector } from "../client/src/lib/pitch.ts";
const [wavPath, keysPath, sens] = process.argv.slice(2);
/** A 16-bit mono WAV, at 48 kHz as the iPad's audio runs (linear interpolation; the keys are well
 *  under 12 kHz), after FRAME samples of silence. */
function load(path: string): Float32Array {
  const buf = readFileSync(path);
  const rate = buf.readUInt32LE(24);
  const dataAt = buf.indexOf("data") + 8;
  const n = (buf.length - dataAt) / 2;
  const src = new Float32Array(n);
  for (let i = 0; i < n; i++) src[i] = buf.readInt16LE(dataAt + 2 * i) / 32768;
  const up = 48000 / rate, m = Math.floor(n * up);
  const x = new Float32Array(m + FRAME);
  for (let i = 0; i < m; i++) { const s = i / up, a = Math.floor(s), f = s - a; x[FRAME + i] = src[a] * (1 - f) + (src[Math.min(n - 1, a + 1)] ?? 0) * f; }
  return x;
}
const x = load(wavPath);
const outPath = wavPath.replace(/\.wav$/, ".out.wav");
const out = existsSync(outPath) ? load(outPath) : null;
const d = new NoteDetector(48000, 21, 108, (+sens || 2) as 1 | 2 | 3);
const ons: { pitch: number; t: number; sure: boolean }[] = [];
const t0 = performance.now();
for (let end = FRAME + 480; end <= x.length; end += 480) {
  const output = out && end <= out.length ? out.subarray(end - FRAME, end) : undefined;
  for (const e of d.process(x.subarray(end - FRAME, end), ((end - FRAME) / 48000) * 1000, undefined, output)) {
    if (e.type === "on") ons.push({ pitch: e.pitch, t: e.timeMs / 1000, sure: e.sure });
  }
}
const msPerFrame = (performance.now() - t0) / ((x.length - FRAME) / 480);
const N = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const nm = (p: number) => `${N[p % 12]}${Math.floor(p / 12) - 1}`;
if (keysPath === "-") {
  console.log(ons.map((o) => `${nm(o.pitch)}${o.sure ? "" : "?"}@${o.t.toFixed(2)}`).join(" "));
  console.log(`${ons.length} keys heard${out ? ", with the app's output" : ""}; ${msPerFrame.toFixed(2)} ms per frame`);
  process.exit(0);
}
const keys: Record<string, number> = JSON.parse(readFileSync(keysPath, "utf8"));
const used = new Set<number>();
const rows: string[] = [];
let hit = 0, total = 0;
const band = { low: [0, 0], mid: [0, 0], high: [0, 0] };
for (const [ps, t] of Object.entries(keys).sort((a, b) => +a[0] - +b[0])) {
  const p = +ps; total++;
  const near = ons.map((o, i) => ({ ...o, i })).filter((o) => o.t >= t - 0.06 && o.t < t + 0.4);
  const ok = near.find((o) => o.pitch === p);
  if (ok) { hit++; used.add(ok.i); }
  const b = p < 48 ? band.low : p > 83 ? band.high : band.mid; b[1]++; if (ok) b[0]++;
  rows.push(`${nm(p).padEnd(4)} ${ok ? "ok " : "-- "} ${near.filter((o) => o.pitch !== p).map((o) => nm(o.pitch) + (o.sure ? "" : "?")).join(" ")}`);
}
const extra = ons.filter((o, i) => !used.has(i));
if (process.argv.includes("-x")) console.log("wrong:", extra.map((o) => `${nm(o.pitch)}${o.sure ? "" : "?"}@${o.t.toFixed(2)}`).join(" "));
if (process.argv.includes("-v")) console.log(rows.join("\n"));
console.log(`heard ${hit}/${total} keys (below C3 ${band.low[0]}/${band.low[1]}, C3-B5 ${band.mid[0]}/${band.mid[1]}, C6 up ${band.high[0]}/${band.high[1]}); ` +
  `${extra.length} wrong key-downs (${extra.filter((o) => o.sure).length} sure); ${msPerFrame.toFixed(2)} ms per frame`);
