// Replays a performance through the same Attempt logic the Play screen uses, without audio or a
// clock: the recorded-performance fixtures (arch §7.10, §11.4) and, later, re-scoring stored
// attempts after the numbers are tuned.
import { Attempt, type AttemptOptions, type AttemptResult } from "./attempt";
import type { RewindPlan } from "./rewind";
import type { Timeline } from "./timeline";

export interface ReplayNote {
  beat: number;         // latency-corrected playback beat
  pitch: number;
  velocity?: number;    // default 80
  durMs?: number;       // how long the key is held; default 200
}

export interface ReplayOutcome {
  result: AttemptResult;
  rewinds: RewindPlan[];
  passesUsed: number;
}

const STEP = 0.01;      // beats per simulated frame

/**
 * Play `passes` in order: the first from the start (or the section start); each later one from
 * wherever the previous rewind went back to. Stops at the end, or when a rewind happens and no
 * pass is left to replay it.
 */
export function replay(tl: Timeline, tempo: number, opts: AttemptOptions, passes: ReplayNote[][],
                       autoRewind = true): ReplayOutcome {
  const a = new Attempt(tl, opts);
  const spb = 60 / (tempo * Number(opts.preset) / 100);
  const rewinds: RewindPlan[] = [];
  let from = a.range.start;
  let clockMs = 0;
  let used = 0;
  for (let p = 0; p < passes.length; p++) {
    used = p + 1;
    a.beginPass(from, clockMs);
    const t0 = clockMs;
    const at = (beat: number) => t0 + (beat - from) * spb * 1000;
    const window = a.matcher.windows.matchMs / 1000 / spb;
    const notes = passes[p].filter((n) => n.beat >= from - window).sort((x, y) => x.beat - y.beat);
    const offs: { beat: number; pitch: number }[] = [];
    let i = 0;
    let plan: RewindPlan | null = null;
    for (let b = from - window; b <= a.range.end + 0.25 + 1e-9; b = Math.round((b + STEP) * 1e6) / 1e6) {
      while (i < notes.length && notes[i].beat <= b + 1e-9) {
        const n = notes[i++];
        const ms = at(n.beat);
        a.record({ t: ms, type: "on", pitch: n.pitch, velocity: n.velocity ?? 80, beat: n.beat });
        a.noteOn(n.pitch, n.beat, n.velocity ?? 80, spb, ms);
        offs.push({ beat: n.beat + (n.durMs ?? 200) / 1000 / spb, pitch: n.pitch });
      }
      offs.sort((x, y) => x.beat - y.beat);
      while (offs.length && offs[0].beat <= b + 1e-9) {
        const o = offs.shift()!;
        const ms = at(o.beat);
        a.record({ t: ms, type: "off", pitch: o.pitch, velocity: 0, beat: o.beat });
        a.noteOff(o.pitch, ms);
      }
      if (b < from) continue;
      plan = a.tick(b, spb, autoRewind).plan;
      if (plan) {
        clockMs = at(b) + 1500;          // the glide and count-in
        break;
      }
    }
    if (!plan) return { result: a.result(true), rewinds, passesUsed: used };
    rewinds.push(plan);
    from = plan.targetBeat;
  }
  return { result: a.result(false), rewinds, passesUsed: used };
}
