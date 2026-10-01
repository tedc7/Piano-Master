// The moving staff: the whole piece in playback order rendered once by VexFlow into one wide SVG
// (arch §3; tested at 60 fps with glides on the iPad A16). Ported from the sync probe.
import {
  Accidental, Articulation, Beam, Dot, Formatter, FretHandFinger, GraceNote, GraceNoteGroup, Modifier, Renderer, Stave,
  StaveConnector, StaveNote, StaveTie, Tuplet, Voice, type RenderContext, type Tickable,
} from "vexflow/bravura";
import type { Grace, Notation, Spelled } from "./types";
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
  graces: number;                               // grace notes drawn
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
const LETTER_FILL = "#1d5fa8";       // letter names under pre-staff note heads (finger numbers are black)

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

const vexKey = (n: { spelled: Spelled }) => n.spelled.step.toLowerCase() + ACC[String(n.spelled.alter)] + "/" + n.spelled.octave;
const keySpec = (fifths: number) => MAJOR[fifths + 7];

/** The alteration a key signature gives a step (F -> 1 in G major). */
function keyAlter(fifths: number, step: string): number {
  const sharps = "FCGDAEB", flats = "BEADGCF";
  if (fifths > 0) return sharps.indexOf(step) < fifths && sharps.includes(step) ? 1 : 0;
  if (fifths < 0) return flats.indexOf(step) < -fifths && flats.includes(step) ? -1 : 0;
  return 0;
}

/** A length that only a triplet can write (a third of a beat and its multiples). */
const isTriplet = (len: number) => Math.abs(len * 3 - Math.round(len * 3)) < 1e-6 && Math.abs(len * 32 - Math.round(len * 32)) > 1e-6;

type Clef = "treble" | "bass";

function centerX(n: StaveNote): number {
  try { return (n.getNoteHeadBeginX() + n.getNoteHeadEndX()) / 2; } catch { return n.getAbsoluteX() + 6; }
}

/** Before the first note (the count-in bar) the staff moves no faster than this, so a first bar
 *  packed with short notes can't push bar 1 off the screen while the Play screen waits. */
const LEAD_IN_SLOPE = 90;

export function xAt(map: [number, number][], beat: number): number {
  let lo = 0;
  let hi = map.length - 1;
  if (beat <= map[0][0]) return map[0][1] + (beat - map[0][0]) * Math.min(slope(map, 0), LEAD_IN_SLOPE);
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
  perStaff: { voice: Voice; beams: Beam[]; tuplets: Tuplet[] }[][];
  fmt: Formatter;
  clefs: Clef[];
  clefChange: boolean[];
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
  // the clef of each staff in each written bar (clef changes carry on until the next)
  const clefAt: Clef[][] = [];
  let cur: Clef[] = [...staves];
  for (const m of nota.measures) {
    if (m.clefs) { cur = [...cur]; for (const [st, c] of Object.entries(m.clefs)) cur[Number(st)] = c; }
    clefAt.push(cur);
  }
  const graceAt = new Map<string, Grace[]>();
  for (const g of nota.graces ?? []) {
    const k = `${g.staff}/${g.voice}/${Number(g.start).toFixed(4)}`;
    graceAt.set(k, [...(graceAt.get(k) ?? []), g]);
  }
  let drawnClefs: Clef[] = [...staves];
  let graceCount = 0;

  // pass 1: notes, voices and widths
  tl.entries.forEach((e, k) => {
    const entryNotes = byEntry[k].map((i) => tl.notes[i]);
    const clefs = clefAt[e.measure] ?? [...staves];
    const clefChange = clefs.map((c, i) => k > 0 && c !== drawnClefs[i]);
    drawnClefs = clefs;
    const perStaff = staves.map((_, s) => {
      const clef = clefs[s];
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
        // tuplets: consecutive tuplet notes grouped until they fill their span (3 eighths in a beat)
        const tuplets: Tuplet[] = [];
        let run: { notes: StaveNote[]; acc: number; base: number; tup: [number, number] } | null = null;
        const flush = () => {
          if (run) tuplets.push(new Tuplet(run.notes, { num_notes: run.tup[0], notes_occupied: run.tup[1] }));
          run = null;
        };
        const inTuplet = (n: StaveNote, actual: number, written: number, tup: [number, number]) => {
          run ??= { notes: [], acc: 0, base: written, tup };
          run.notes.push(n);
          run.acc += actual;
          run.base = Math.min(run.base, written);
          if (run.acc >= run.base * run.tup[1] - 1e-6) flush();
        };
        const rest = (len: number) => {
          const tup: [number, number] | null = isTriplet(len) ? [3, 2] : null;
          const f = tup ? 2 / 3 : 1;
          for (const p of durPieces(len / f)) {
            const r = new StaveNote({ keys: [restKey], duration: p[1] + "r", dots: p[2], clef });
            if (p[2]) Dot.buildAndAttach([r], { all: true });
            tick.push(r);
            tickInfo.push({ vf: r, beat: cursor });
            cursor += p[0] * f;
            if (tup) inTuplet(r, p[0] * f, p[0], tup); else flush();
          }
        };
        starts.forEach((s0, gi) => {
          if (s0 > cursor + 1e-6) rest(s0 - cursor);
          if (s0 < cursor - 1e-6) { problems.push(`m${e.m.number} ${clef} voice ${v}: overlapping notes`); return; }
          const g = groups.get(s0.toFixed(4))!;
          const next = gi + 1 < starts.length ? starts[gi + 1] : end;
          const len = Math.min(Math.min(...g.map((x) => x.duration)), next - s0, end - s0);
          const keys = g.slice().sort((a, b) => a.pitch - b.pitch);
          const tup = keys[0].tuplet ?? (isTriplet(len) ? [3, 2] as [number, number] : null);
          const f = tup ? tup[1] / tup[0] : 1;
          let prev: StaveNote | null = null;
          durPieces(len / f).forEach((p, pi) => {
            const opts: ConstructorParameters<typeof StaveNote>[0] = {
              keys: keys.map(vexKey), duration: p[1], dots: p[2], clef,
            };
            if (dir) opts.stem_direction = dir; else opts.auto_stem = true;
            const n = new StaveNote(opts);
            if (p[2]) Dot.buildAndAttach([n], { all: true });
            if (pi === 0) {
              const gs = graceAt.get(`${s}/${v}/${keys[0].start.toFixed(4)}`);
              if (gs) {
                const gn = gs.sort((a, b) => a.order - b.order).map((x) => {
                  const q = new GraceNote({ keys: [vexKey(x)], duration: "8", slash: x.slash, clef });
                  if (x.spelled.alter !== keyAlter(h.keySig, x.spelled.step)) q.addModifier(new Accidental(ACC[String(x.spelled.alter)] || "n"), 0);
                  return q;
                });
                graceCount += gn.length;
                const group = new GraceNoteGroup(gn, true);
                if (gn.length > 1) group.beamNotes();
                n.addModifier(group, 0);
              }
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
            cursor += p[0] * f;
            if (tup) inTuplet(n, p[0] * f, p[0], tup); else flush();
          });
          for (const x of keys) vfLast[x.id] = prev;
        });
        if (cursor < end - 1e-6 && (vi === 0 || starts.length)) rest(end - cursor);
        flush();
        const voice = new Voice({ num_beats: Math.max(1, Math.round(e.duration * 8)), beat_value: 32 }).setMode(Voice.Mode.SOFT);
        voice.addTickables(tick as Tickable[]);
        let beams: Beam[] = [];
        try {
          const notes = tick.filter((t) => !t.isRest());
          beams = Beam.generateBeams(notes, dir
            ? { groups: Beam.getDefaultBeamGroups(ts), stem_direction: dir, maintain_stem_directions: true }
            : { groups: Beam.getDefaultBeamGroups(ts) });
        } catch (err) { problems.push(`m${e.m.number} beams: ${(err as Error).message}`); }
        return { voice, beams, tuplets };
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
    const extra = (first ? (grand ? 95 : 85) + Math.abs(h.keySig) * 10 : (change ? 50 : 0)) + (clefChange.some(Boolean) ? 40 : 0);
    const width = Math.max(minW * 1.35 + 40, lyricW + 20, 100) + extra;
    measures.push({ e, perStaff, fmt, all, width, first, change, clefs, clefChange });
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
      if (m.first) s.addClef(m.clefs[i]).addKeySignature(key).addTimeSignature(ts);
      else if (m.clefChange[i]) s.addClef(m.clefs[i]);
      if (!m.first && m.change) {
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
        v.tuplets.forEach((t) => t.setContext(ctx).draw());
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
  // dynamic marks (f, mf, p...) under the upper staff at the note they start from, in the bold
  // italic of printed music; between the lyrics and the bass staff on a grand staff
  for (const d of nota.dynamics ?? []) {
    for (const e of tl.entries) {
      if (d.beat >= e.m.start - 1e-6 && d.beat < e.m.start + e.m.duration - 1e-6) {
        const t = addText(d.mark, xAt(map, e.start + d.beat - e.m.start) - 8, grand ? TOP + 182 : TOP + 120, 22, "bold");
        t.setAttribute("font-family", "'Times New Roman', Georgia, serif");
        t.setAttribute("font-style", "italic");
        t.classList.add("dynamic");
      }
    }
  }
  const noteEls = tl.notes.map((n) => {
    const vf = vfFirst[n.id];
    if (!vf) return null;
    return vf.noteHeads[keyIdx[n.id]]?.getSVGElement() ?? null;
  });
  // a pre-staff piece: each white key's letter name just under its note head, so the heads look the
  // same with or without it and a half note still reads as a half note. The right hand's finger
  // number is above the head; the left hand's is below it, so there the letter goes under the
  // finger number. Two notes at once in one hand stack their letters under the lower head, high to
  // low like the heads. (Black keys have no letter at this level: their names come with sharps and flats.)
  if (h.letters) {
    const under = new Map<StaveNote, Map<string, TimelineNote[]>>();
    for (const n of tl.notes) {
      const vf = vfFirst[n.id];
      if (!vf || n.tieContinuation || n.spelled.alter) continue;
      const byHand = under.get(vf) ?? new Map<string, TimelineNote[]>();
      byHand.set(n.hand, [...(byHand.get(n.hand) ?? []), n]);
      under.set(vf, byHand);
    }
    for (const [vf, byHand] of under) {
      for (const [hand, ns] of byHand) {
        try {
          ns.sort((a, b) => b.pitch - a.pitch);
          const lowest = Math.max(...ns.map((n) => vf.getYs()[keyIdx[n.id]]));
          const base = lowest + (hand === "L" && ns.some((n) => n.finger) ? 29 : 18);
          const dx = vf.getStemDirection() < 0 ? 4 : 0;      // a stem down the head's left side: clear of it
          ns.forEach((n, i) => {
            const el = addText(n.spelled.step.toUpperCase(), centerX(vf) + dx, base + i * 13, 13, "bold", LETTER_FILL);
            el.setAttribute("pointer-events", "none");
            el.classList.add("note-letter");
          });
        } catch { /* not laid out */ }
      }
    }
  }
  return {
    svg, scale, map, noteEls, lyrics, problems, graces: graceCount,
    width: Math.round(total * scale), height: Math.round(H * scale),
    renderMs: performance.now() - t0,
  };
}


export interface MiniNote { pitches: number[]; spelled: Spelled[]; beats: number }

const MINI_DUR: Record<number, [string, number]> = { 0.5: ["8", 0], 1: ["q", 0], 1.5: ["q", 1], 2: ["h", 0], 3: ["h", 1], 4: ["w", 0] };

/** A small staff for a concept lesson's Show card: the notes in order, on the treble, bass or
 *  grand staff (a note goes on the bass staff below middle C). Returns each note's note-head
 *  group, to light up in turn. */
export function renderMini(host: HTMLElement, notes: MiniNote[], clef: "treble" | "bass" | "grand"): Element[][] {
  host.innerHTML = "";
  const grand = clef === "grand";
  const width = Math.max(260, 90 + notes.length * 62);
  const renderer = new Renderer(host as HTMLDivElement, Renderer.Backends.SVG);
  renderer.resize(width, grand ? 250 : 150);
  const ctx = renderer.getContext();
  const staves = grand ? [new Stave(10, 10, width - 20), new Stave(10, 120, width - 20)] : [new Stave(10, 20, width - 20)];
  const clefs: ("treble" | "bass")[] = grand ? ["treble", "bass"] : [clef];
  staves.forEach((st, i) => st.addClef(clefs[i]).setContext(ctx).draw());
  if (grand) new StaveConnector(staves[0], staves[1]).setType(StaveConnector.type.BRACE).setContext(ctx).draw();
  const staffOf = (n: MiniNote) => (grand ? (Math.min(...n.pitches) < 60 ? 1 : 0) : 0);
  const voices = staves.map((_, si) => {
    const tick: StaveNote[] = notes.map((n) => {
      const [d, dots] = MINI_DUR[n.beats] ?? ["q", 0];
      const mine = staffOf(n) === si;
      const vn = mine
        ? new StaveNote({ keys: n.spelled.map((x) => vexKey({ spelled: x })), duration: d, dots, clef: clefs[si], auto_stem: true })
        : new StaveNote({ keys: [clefs[si] === "bass" ? "d/3" : "b/4"], duration: d + "r", dots, clef: clefs[si] });
      if (dots) Dot.buildAndAttach([vn], { all: true });
      if (mine) n.spelled.forEach((x, i) => { if (x.alter) vn.addModifier(new Accidental(ACC[String(x.alter)]), i); });
      return vn;
    });
    const v = new Voice({ num_beats: 4, beat_value: 4 }).setMode(Voice.Mode.SOFT);
    v.addTickables(tick as Tickable[]);
    return { v, tick };
  });
  new Formatter().joinVoices(voices.map((x) => x.v)).format(voices.map((x) => x.v), width - 100);
  voices.forEach((x, i) => x.v.draw(ctx, staves[i]));
  return notes.map((n, i) => {
    const vn = voices[staffOf(n)].tick[i];
    return vn.noteHeads.map((h) => h.getSVGElement()).filter((e): e is SVGElement => !!e);
  });
}
