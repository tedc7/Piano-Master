// Recorded-performance fixtures (arch §7.10, §11.4): each fixture is a performance and the
// result it should get. Pieces come from the content build (tools/build_content.py).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { replay, type ReplayNote } from "../src/lib/replay";
import { buildTimeline, type Timeline } from "../src/lib/timeline";
import type { Notation, Note, Piece, Preset } from "../src/lib/types";

const HERE = import.meta.dirname;
const CONTENT = join(HERE, "..", "public", "content", "pieces");

interface Generated {
  offsetMs?: number;
  jitterMs?: number;
  seed?: number;
  rollMs?: number;
  skipBeats?: number[];
  wrong?: { beat: number; pitch: number }[];
  extra?: { beat: number; pitch: number }[];
  stopAtBeat?: number;
  playHands?: "both" | "R" | "L";
}

interface Fixture {
  description: string;
  piece?: string;
  chords?: { timeSig: string; tempo: number; level: string; events: [number, number[], number][] };
  preset: Preset;
  hands: "both" | "R" | "L";
  section?: { phrases: [number, number] };
  passes?: Generated[];
  events?: ReplayNote[][];          // explicit key presses per pass (real recordings)
  expect: {
    rewinds: { reason?: string; phrase?: number; targetBeat?: number }[];
    completed: boolean;
    matched?: number;
    extra?: number;
    accuracyStars?: number;
    timingStars?: number | null;
    tendency?: string | null;
    aids?: string[];
    tricky?: { phrase: number; bars: [number, number] } | null;
  };
}

function chordPiece(c: NonNullable<Fixture["chords"]>): Piece {
  const [num, den] = c.timeSig.split("/").map(Number);
  const bar = num * 4 / den;
  const notes: Note[] = c.events.flatMap(([beat, pitches, dur]) => pitches.map((pitch) => ({
    pitch, start: beat, duration: dur, staff: 0, hand: "R" as const, voice: 1,
    spelled: { step: "C", alter: 0, octave: 4 },
  })));
  const length = Math.ceil(Math.max(...c.events.map(([b, , d]) => b + d)) / bar) * bar;
  const measures = Array.from({ length: length / bar }, (_, i) => ({ number: i + 1, start: i * bar, duration: bar }));
  const notation: Notation = {
    header: { keySig: 0, timeSig: c.timeSig, barLength: bar, tempo: c.tempo, pickupBeats: 0, range: [40, 80], staves: ["treble"] },
    measures, notes, lyrics: [], chordSymbols: [],
    playbackOrder: measures.map((_, i) => ({ measure: i, verse: 1 })), phrases: [0], length,
  };
  return { id: "chords", title: "chords", kind: "core", level: c.level, hands: "R", notation, media: null };
}

function loadPiece(f: Fixture): Piece {
  if (f.chords) return chordPiece(f.chords);
  const path = join(CONTENT, `${f.piece}.json`);
  if (!existsSync(path)) throw new Error(`${path} missing: run tools/build_content.py first`);
  return JSON.parse(readFileSync(path, "utf8"));
}

/** Seeded random numbers, so a jittered fixture always plays the same way. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Key presses for one pass, made from the score by the fixture's recipe. */
function generate(tl: Timeline, spb: number, g: Generated): ReplayNote[] {
  const rnd = mulberry32(g.seed ?? 1);
  const ms = (x: number) => x / 1000 / spb;
  const hands = g.playHands ?? "both";
  const out: ReplayNote[] = [];
  const rollIndex = new Map<number, number>();
  for (const n of tl.notes) {
    if (n.tieContinuation || (hands !== "both" && n.hand !== hands)) continue;
    if (g.stopAtBeat !== undefined && n.beat >= g.stopAtBeat) continue;
    if (g.skipBeats?.some((b) => Math.abs(b - n.beat) < 1e-6)) continue;
    const k = rollIndex.get(n.beat) ?? 0;
    rollIndex.set(n.beat, k + 1);
    const jitter = g.jitterMs ? (rnd() * 2 - 1) * g.jitterMs : 0;
    out.push({ beat: n.beat + ms((g.offsetMs ?? 0) + jitter + k * (g.rollMs ?? 0)), pitch: n.pitch,
               durMs: Math.max(60, n.duration * spb * 900) });
  }
  for (const x of [...(g.wrong ?? []), ...(g.extra ?? [])]) out.push({ beat: x.beat, pitch: x.pitch, durMs: 200 });
  return out.sort((a, b) => a.beat - b.beat);
}

const files = readdirSync(join(HERE, "fixtures")).filter((f) => f.endsWith(".json")).sort();

describe("performance fixtures", () => {
  for (const file of files) {
    const f: Fixture = JSON.parse(readFileSync(join(HERE, "fixtures", file), "utf8"));
    it(`${file.replace(".json", "")}: ${f.description}`, () => {
      const piece = loadPiece(f);
      const tl = buildTimeline(piece.notation);
      const tempo = piece.media?.bpm ?? piece.notation.header.tempo;
      const spb = 60 / (tempo * Number(f.preset) / 100);
      const section = f.section
        ? { start: tl.phrases[f.section.phrases[0]].start, end: tl.phrases[f.section.phrases[1]].end }
        : null;
      const passes = f.events ?? (f.passes ?? [{}]).map((g) => generate(tl, spb, g));
      const out = replay(tl, tempo, { hands: f.hands, handsWritten: piece.hands, section, level: piece.level, preset: f.preset }, passes);
      const e = out.result.evaluation;
      const x = f.expect;
      // each expected rewind lists only the fields it cares about
      expect(out.rewinds.map((r, i) => pick(r, x.rewinds[i] ?? r))).toEqual(x.rewinds);
      expect(out.result.completed).toBe(x.completed);
      if (x.matched !== undefined) expect(e.matched).toBe(x.matched);
      if (x.extra !== undefined) expect(e.extra).toBe(x.extra);
      if (x.accuracyStars !== undefined) expect(e.accuracyStars).toBe(x.accuracyStars);
      if (x.timingStars !== undefined) expect(e.timingStars).toBe(x.timingStars);
      if (x.tendency !== undefined) expect(e.tendency).toBe(x.tendency);
      if (x.aids !== undefined) expect(e.aids.map((a) => a.id)).toEqual(x.aids);
      if (x.tricky !== undefined) expect(out.result.tricky).toEqual(x.tricky);
    });
  }
});

function pick<T extends object>(obj: T, like: object): Partial<T> {
  return Object.fromEntries(Object.keys(like).map((k) => [k, (obj as Record<string, unknown>)[k]])) as Partial<T>;
}
