// The moving staff: the whole piece in playback order rendered once by VexFlow into one wide SVG
// (arch §3; tested at 60 fps with glides on the iPad A16). Ported from the sync probe.
import {
  Accidental, Articulation, Beam, Dot, Formatter, FretHandFinger, Modifier, Renderer, Stave,
  StaveConnector, StaveNote, StaveTie, Voice, type RenderContext, type Tickable,
} from "vexflow/bravura";
import type { Notation } from "./types";
import type { Timeline, TimelineNote } from "./timeline";

export interface StaffLayout {
  svg: SVGSVGElement;
  scale: number;
  width: number;
  height: number;
  map: [number, number][];                     // beat -> x in VexFlow units (note-head centres)
  noteEls: (Element | null)[];                  // by timeline note id: its note-head group
  lyrics: { beat: number; end: number; el: SVGTextElement }[];
  problems: string[];
  renderMs: number;
}

const DUR: [number, string, number][] = [[6, "w", 1], [4, "w", 0], [3, "h", 1], [2, "h", 0], [1.5, "q", 1], [1, "q", 0],
  [0.75, "8", 1], [0.5, "8", 0], [0.375, "16", 1], [0.25, "16", 0], [0.125, "32", 0]];
const ACC: Record<string, string> = { "-2": "bb", "-1": "b", "0": "", "1": "#", "2": "##" };
const MAJOR = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"];
const SVG_NS = "http://www.w3.org/2000/svg";
const TOP = 70;
const GAP = 175;
export const LYRIC_FILL = "#2a2a2e";

function durPieces(d: number): [number, string, number][] {
  const out: [number, string, number][] = [];
  let guard = 0;
  while (d > 1e-6 && guard++ < 12) {
    const p = DUR.find((e) => e[0] <= d + 1e-6) ?? DUR[DUR.length - 1];
    out.push(p);
    d -= p[0];
  }
  return out;
}

const vexKey = (n: TimelineNote) => n.spelled.step.toLowerCase() + ACC[String(n.spelled.alter)] + "/" + n.spelled.octave;
const keySpec = (fifths: number) => MAJOR[fifths + 7];

function centerX(n: StaveNote): number {
  try { return (n.getNoteHeadBeginX() + n.getNoteHeadEndX()) / 2; } catch { return n.getAbsoluteX() + 6; }
}

export function xAt(map: [number, number][], beat: number): number {
  let lo = 0;
  let hi = map.length - 1;
  if (beat <= map[0][0]) return map[0][1] + (beat - map[0][0]) * slope(map, 0);
  if (beat >= map[hi][0]) return map[hi][1];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (map[mid][0] <= beat) lo = mid; else hi = mid;
  }
  const a = map[lo];
  const b = map[hi];
  return a[1] + (b[1] - a[1]) * (beat - a[0]) / (b[0] - a[0]);
}

function slope(map: [number, number][], i: number): number {
  return map.length > i + 1 ? (map[i + 1][1] - map[i][1]) / Math.max(map[i + 1][0] - map[i][0], 1e-6) : 40;
}

interface MeasureDraw {
  e: Timeline["entries"][number];
  perStaff: { voice: Voice; beams: Beam[] }[][];
  fmt: Formatter;
  all: Voice[];
  width: number;
  first: boolean;
  change: boolean;
}

export function renderStaff(host: HTMLElement, tl: Timeline, nota: Notation, boxHeight: number): StaffLayout {
  const h = nota.header;
  const staves = h.staves;
  const grand = staves.length > 1;
  const H = grand ? 400 : 250;
  const ts = h.timeSig;
  const key = keySpec(h.keySig);
  const t0 = performance.now();
  const problems: string[] = [];
  const byEntry: number[][] = tl.entries.map(() => []);
  tl.notes.forEach((x) => byEntry[x.entry].push(x.id));
  const tickInfo: { vf: StaveNote; beat: number }[] = [];
  const splitTies: { a: StaveNote; b: StaveNote; idx: number[] }[] = [];
  const vfFirst: (StaveNote | null)[] = tl.notes.map(() => null);
  const vfLast: (StaveNote | null)[] = tl.notes.map(() => null);
  const keyIdx: number[] = tl.notes.map(() => 0);
  const measures: MeasureDraw[] = [];

  // pass 1: notes, voices and widths
  tl.entries.forEach((e, k) => {
    const entryNotes = byEntry[k].map((i) => tl.notes[i]);
    const perStaff = staves.map((clef, s) => {
      const voices = new Map<number, TimelineNote[]>();
      for (const x of entryNotes) {
        if (x.staff !== s) continue;
        if (!voices.has(x.voice)) voices.set(x.voice, []);
        voices.get(x.voice)!.push(x);
      }
      let voiceNums = [...voices.keys()].sort((a, b) => a - b);
      if (!voiceNums.length) { voiceNums = [1]; voices.set(1, []); }
      const multi = voiceNums.length > 1;
      return voiceNums.map((v, vi) => {
        const groups = new Map<string, TimelineNote[]>();
        const starts: number[] = [];
        for (const x of voices.get(v)!) {
          const g = x.beat.toFixed(4);
          if (!groups.has(g)) { groups.set(g, []); starts.push(x.beat); }
          groups.get(g)!.push(x);
        }
        starts.sort((a, b) => a - b);
        const tick: StaveNote[] = [];
        let cursor = e.start;
        const end = e.start + e.duration;
        const dir = multi ? (vi === 0 ? 1 : -1) : 0;
        const restKey = clef === "bass" ? (vi ? "f/2" : "d/3") : (vi ? "e/4" : "b/4");
        const rest = (len: number) => {
          for (const p of durPieces(len)) {
            const r = new StaveNote({ keys: [restKey], duration: p[1] + "r", dots: p[2], clef });
            if (p[2]) Dot.buildAndAttach([r], { all: true });
            tick.push(r);
            tickInfo.push({ vf: r, beat: cursor });
            cursor += p[0];
          }
        };
        starts.forEach((s0, gi) => {
          if (s0 > cursor + 1e-6) rest(s0 - cursor);
          if (s0 < cursor - 1e-6) { problems.push(`m${e.m.number} ${clef} voice ${v}: overlapping notes`); return; }
          const g = groups.get(s0.toFixed(4))!;
          const next = gi + 1 < starts.length ? starts[gi + 1] : end;
          const len = Math.min(Math.min(...g.map((x) => x.duration)), next - s0, end - s0);
          const keys = g.slice().sort((a, b) => a.pitch - b.pitch);
          let prev: StaveNote | null = null;
          durPieces(len).forEach((p, pi) => {
            const opts: ConstructorParameters<typeof StaveNote>[0] = {
              keys: keys.map(vexKey), duration: p[1], dots: p[2], clef,
            };
            if (dir) opts.stem_direction = dir; else opts.auto_stem = true;
            const n = new StaveNote(opts);
            if (p[2]) Dot.buildAndAttach([n], { all: true });
            if (pi === 0) {
              if (keys.some((x) => x.fermata)) n.addModifier(new Articulation("a@a").setPosition(dir < 0 ? 4 : 3), 0);
              keys.forEach((x, ki) => {
                if (x.finger) {
                  const f = new FretHandFinger(String(x.finger));
                  f.setPosition(x.hand === "L" ? Modifier.Position.BELOW : Modifier.Position.ABOVE);
                  n.addModifier(f, ki);
                }
                vfFirst[x.id] = n;
                keyIdx[x.id] = ki;
              });
            }
            tick.push(n);
            tickInfo.push({ vf: n, beat: cursor });
            if (prev) splitTies.push({ a: prev, b: n, idx: keys.map((_, i) => i) });
            prev = n;
            cursor += p[0];
          });
          for (const x of keys) vfLast[x.id] = prev;
        });
        if (cursor < end - 1e-6 && (vi === 0 || starts.length)) rest(end - cursor);
        const voice = new Voice({ num_beats: Math.max(1, Math.round(e.duration * 8)), beat_value: 32 }).setMode(Voice.Mode.SOFT);
        voice.addTickables(tick as Tickable[]);
        let beams: Beam[] = [];
        try {
          const notes = tick.filter((t) => !t.isRest());
          beams = Beam.generateBeams(notes, dir
            ? { groups: Beam.getDefaultBeamGroups(ts), stem_direction: dir, maintain_stem_directions: true }
            : { groups: Beam.getDefaultBeamGroups(ts) });
        } catch (err) { problems.push(`m${e.m.number} beams: ${(err as Error).message}`); }
        return { voice, beams };
      });
    });
    const all = perStaff.flatMap((vs) => vs.map((v) => v.voice));
    try { Accidental.applyAccidentals(all, key); } catch (err) { problems.push(`m${e.m.number} accidentals: ${(err as Error).message}`); }
    const fmt = new Formatter();
    for (const vs of perStaff) fmt.joinVoices(vs.map((v) => v.voice));
    let minW = 60;
    try { minW = fmt.preCalculateMinTotalWidth(all); } catch (err) { problems.push(`m${e.m.number} width: ${(err as Error).message}`); }
    let lyricW = 0;
    for (const x of entryNotes) {
      if (!x.isMelody) continue;
      const tail = x.lyric && (x.lyric.syllabic === "begin" || x.lyric.syllabic === "middle") ? 2 : 0;
      lyricW += Math.max(30, (x.lyric ? x.lyric.text.length + tail : 0) * 9 + 16);
    }
    const first = k === 0;
    const change = !first && (e.m.keySig !== undefined || e.m.timeSig !== undefined);
    const extra = first ? (grand ? 95 : 85) + Math.abs(h.keySig) * 10 : (change ? 50 : 0);
    const width = Math.max(minW * 1.35 + 40, lyricW + 20, 100) + extra;
    measures.push({ e, perStaff, fmt, all, width, first, change });
  });

  // pass 2: draw
  const PAD = 30;
  const total = PAD * 2 + measures.reduce((a, m) => a + m.width, 0);
  const scale = Math.min(boxHeight / H, 1.5);
  host.innerHTML = "";
  const renderer = new Renderer(host as HTMLDivElement, Renderer.Backends.SVG);
  renderer.resize(Math.ceil(total * scale), Math.ceil(H * scale));
  const ctx: RenderContext = renderer.getContext();
  ctx.scale(scale, scale);
  let x = PAD;
  let lastVerse: number | null = null;
  const verses = new Set(tl.entries.map((e) => e.verse)).size;
  for (const m of measures) {
    const treble = new Stave(x, TOP, m.width);
    const bass = grand ? new Stave(x, TOP + GAP, m.width) : null;
    const st = bass ? [treble, bass] : [treble];
    st.forEach((s, i) => {
      if (m.first) s.addClef(staves[i]).addKeySignature(key).addTimeSignature(ts);
      else if (m.change) {
        if (m.e.m.keySig !== undefined) s.addKeySignature(keySpec(m.e.m.keySig));
        if (m.e.m.timeSig !== undefined) s.addTimeSignature(m.e.m.timeSig);
      }
      s.setContext(ctx).draw();
    });
    if (bass) {
      if (m.first) {
        new StaveConnector(treble, bass).setType(StaveConnector.type.BRACE).setContext(ctx).draw();
        new StaveConnector(treble, bass).setType(StaveConnector.type.SINGLE_LEFT).setContext(ctx).draw();
      }
      new StaveConnector(treble, bass).setType(StaveConnector.type.SINGLE_RIGHT).setContext(ctx).draw();
    }
    if (verses > 1 && m.e.verse !== lastVerse) {
      ctx.save();
      ctx.setFont("Arial", 12, "bold");
      ctx.fillText("verse " + m.e.verse, x + 4, TOP - 44);
      ctx.restore();
      lastVerse = m.e.verse;
    }
    try {
      m.perStaff.forEach((vs, i) => vs.forEach((v) => v.voice.setStave(st[i])));
      m.fmt.format(m.all, m.width - (treble.getNoteStartX() - x) - 14);
      m.perStaff.forEach((vs, i) => vs.forEach((v) => {
        v.voice.draw(ctx, st[i]);
        v.beams.forEach((b) => b.setContext(ctx).draw());
      }));
    } catch (err) { problems.push(`m${m.e.m.number} draw: ${(err as Error).message}`); }
    x += m.width;
  }
  // ties: split pieces, then written ties to the next note of the same pitch, staff and voice
  for (const t of splitTies) {
    try { new StaveTie({ first_note: t.a, last_note: t.b, first_indices: t.idx, last_indices: t.idx }).setContext(ctx).draw(); }
    catch (err) { problems.push(`tie: ${(err as Error).message}`); }
  }
  const prevOf = new Map<string, TimelineNote>();
  for (const n of tl.notes) {
    if (!vfFirst[n.id]) continue;
    const k = `${n.staff}/${n.voice}/${n.pitch}`;
    const prev = prevOf.get(k);
    if (prev && prev.tieToNext && Math.abs(prev.beat + prev.duration - n.beat) < 1e-6) {
      try {
        new StaveTie({ first_note: vfLast[prev.id]!, last_note: vfFirst[n.id]!, first_indices: [keyIdx[prev.id]], last_indices: [keyIdx[n.id]] })
          .setContext(ctx).draw();
      } catch (err) { problems.push(`tie: ${(err as Error).message}`); }
    }
    prevOf.set(k, n);
  }

  // beat -> x through the note-head centres
  const pts: [number, number][] = [];
  for (const t of tickInfo) { try { pts.push([t.beat, centerX(t.vf)]); } catch { /* not drawn */ } }
  pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const map: [number, number][] = [];
  for (const p of pts) {
    const last = map[map.length - 1];
    if (last && (Math.abs(last[0] - p[0]) < 1e-6 || p[1] <= last[1])) continue;
    map.push(p);
  }
  map.push([tl.length, x - 6]);

  const svg = host.querySelector("svg") as SVGSVGElement;
  const addText = (txt: string, tx: number, ty: number, size: number, weight?: string, fill = LYRIC_FILL) => {
    const el = document.createElementNS(SVG_NS, "text");
    el.setAttribute("x", String(tx));
    el.setAttribute("y", String(ty));
    el.setAttribute("font-size", String(size));
    el.setAttribute("font-family", "-apple-system, 'Segoe UI', Roboto, sans-serif");
    el.setAttribute("text-anchor", "middle");
    if (weight) el.setAttribute("font-weight", weight);
    el.setAttribute("fill", fill);
    el.textContent = txt;
    svg.appendChild(el);
    return el;
  };
  // lyrics under the upper staff, each syllable its own element so it can light up
  const lyricY = TOP + 150;
  const lyrics: StaffLayout["lyrics"] = [];
  for (const n of tl.melody) {
    const vf = vfFirst[n.id];
    if (!n.lyric || !vf) continue;
    let tx: number;
    try { tx = centerX(vf); } catch { continue; }
    const txt = n.lyric.text + (n.lyric.syllabic === "begin" || n.lyric.syllabic === "middle" ? " -" : "");
    lyrics.push({ beat: n.beat, end: n.beat + n.duration, el: addText(txt, tx, lyricY, 15) });
  }
  for (const c of nota.chordSymbols ?? []) {
    for (const e of tl.entries) {
      if (c.beat >= e.m.start - 1e-6 && c.beat < e.m.start + e.m.duration - 1e-6) {
        addText(c.symbol, xAt(map, e.start + c.beat - e.m.start), TOP - 22, 13, "bold", "#6b5a2e");
      }
    }
  }
  const noteEls = tl.notes.map((n) => {
    const vf = vfFirst[n.id];
    if (!vf) return null;
    return vf.noteHeads[keyIdx[n.id]]?.getSVGElement() ?? null;
  });
  return {
    svg, scale, map, noteEls, lyrics, problems,
    width: Math.round(total * scale), height: Math.round(H * scale),
    renderMs: performance.now() - t0,
  };
}
