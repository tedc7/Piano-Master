// The notation laid out in playback order (repeats and verses unrolled): what the Play screen
// scrolls, sounds and scores. Beats are quarter notes from the first measure's start.
import type { Lyric, Measure, Notation, Note } from "./types";

export interface Entry { start: number; measure: number; verse: number; duration: number; m: Measure }

export interface TimelineNote extends Note {
  id: number;          // index in Timeline.notes
  index: number;       // index in Notation.notes
  entry: number;       // index in Timeline.entries
  beat: number;        // start on the playback timeline
  lyric: Lyric | null;
  phrase: number;
  tieContinuation: boolean;   // held on from a tied note: not played again, not sounded again
}

export interface Phrase { index: number; start: number; end: number; noteIds: number[] }

export interface Timeline {
  entries: Entry[];
  notes: TimelineNote[];      // sorted by beat, then pitch
  melody: TimelineNote[];
  phrases: Phrase[];
  barLines: number[];         // entry starts, plus the end
  length: number;
  barLength: number;
  beatUnit: number;           // the counted beat: a quarter, or a dotted quarter in 6/8
}

const EPS = 1e-6;

export function beatUnit(timeSig: string): number {
  const [num, den] = timeSig.split("/").map(Number);
  return den === 8 && num % 3 === 0 ? 1.5 : 4 / den;
}

export function buildTimeline(n: Notation): Timeline {
  const ms = n.measures;
  const lyr = new Map<number, Map<number, Lyric>>();
  for (const l of n.lyrics) {
    if (!lyr.has(l.note)) lyr.set(l.note, new Map());
    lyr.get(l.note)!.set(l.verse, l);
  }
  const plays = new Map<number, number>();
  for (const p of n.playbackOrder) plays.set(p.measure, (plays.get(p.measure) ?? 0) + 1);
  const byMeasure: number[][] = ms.map(() => []);
  n.notes.forEach((x, i) => {
    const mi = ms.findIndex((m) => m.start <= x.start + EPS && x.start < m.start + m.duration - EPS);
    if (mi >= 0) byMeasure[mi].push(i);
  });

  let t = 0;
  const entries: Entry[] = [];
  const raw: Omit<TimelineNote, "id" | "phrase" | "tieContinuation">[] = [];
  n.playbackOrder.forEach((p, k) => {
    const m = ms[p.measure];
    entries.push({ start: t, measure: p.measure, verse: p.verse, duration: m.duration, m });
    for (const i of byMeasure[p.measure]) {
      const x = n.notes[i];
      const L = lyr.get(i);
      let ly = L?.get(p.verse) ?? null;
      if (!ly && L && L.size === 1 && plays.get(p.measure) === 1) ly = [...L.values()][0];
      raw.push({ ...x, index: i, entry: k, beat: t + x.start - m.start, lyric: ly });
    }
    t += m.duration;
  });
  raw.sort((a, b) => a.beat - b.beat || a.pitch - b.pitch);

  const starts = n.phrases.length ? n.phrases : [0];
  const phrases: Phrase[] = starts.map((s, i) => ({
    index: i, start: s, end: i + 1 < starts.length ? starts[i + 1] : t, noteIds: [],
  }));
  const tiedOpen = new Map<string, number>();   // staff/voice/pitch -> beat where a tie ends
  const notes: TimelineNote[] = raw.map((x, id) => {
    const k = `${x.staff}/${x.voice}/${x.pitch}`;
    const tieContinuation = Math.abs((tiedOpen.get(k) ?? -1) - x.beat) < EPS;
    tiedOpen.delete(k);
    if (x.tieToNext) tiedOpen.set(k, x.beat + x.duration);
    const phrase = phraseIndexAt(phrases, x.beat);
    if (!tieContinuation) phrases[phrase].noteIds.push(id);
    return { ...x, id, phrase, tieContinuation };
  });
  return {
    entries,
    notes,
    melody: notes.filter((x) => x.isMelody),
    phrases,
    barLines: [...entries.map((e) => e.start), t],
    length: t,
    barLength: n.header.barLength,
    beatUnit: beatUnit(n.header.timeSig),
  };
}

export function phraseIndexAt(phrases: { start: number }[], beat: number): number {
  let idx = 0;
  for (let i = 0; i < phrases.length; i++) if (phrases[i].start <= beat + EPS) idx = i;
  return idx;
}

/** The first bar line at or after `beat` (beats before the song map onto its bar grid). */
export function nextBarLine(tl: Timeline, beat: number): number {
  for (const b of tl.barLines) if (b >= beat - EPS) return b;
  return tl.length;
}

/** The first counted beat at or after `beat` (the beat grid is anchored at the pickup). */
export function gridBeat(tl: Timeline, pickup: number, beat: number): number {
  const u = tl.beatUnit;
  return pickup + Math.ceil((beat - pickup) / u - EPS) * u;
}

/** Notes starting at the next onset at or after `beat` (the keys to highlight next). */
export function nextOnset(tl: Timeline, beat: number): TimelineNote[] {
  const i = tl.notes.findIndex((x) => x.beat >= beat - EPS && !x.tieContinuation);
  if (i < 0) return [];
  const b = tl.notes[i].beat;
  const out: TimelineNote[] = [];
  for (let j = i; j < tl.notes.length && tl.notes[j].beat - b < EPS; j++) {
    if (!tl.notes[j].tieContinuation) out.push(tl.notes[j]);
  }
  return out;
}
