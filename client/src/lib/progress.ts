// Skill states, song readiness and today's session (arch §6.8, §8.1, §8.5).
//
// SAMPLE DATA: until the students (M4) and the lesson engine (M5) exist, every student gets the
// same made-up progress so the Journey map, Song library and Home show all their states: the
// first 40% of skills by sequence are passed (the first one mastered), the rest follow from the
// prerequisites. The readiness rules below are the real ones.
import type { PieceSummary, Skill, SkillMap } from "./types";

export type SkillStatus = "locked" | "current" | "passed" | "mastered";

export interface SkillProgress {
  status: SkillStatus;
  accuracyStars: number | null;   // best, after practice-aid scaling (arch §3 "Journey map star display")
  timingStars: number | null;
}

export type Progress = Map<string, SkillProgress>;

export const isPassed = (p: SkillProgress | undefined) => p?.status === "passed" || p?.status === "mastered";

export function sampleProgress(map: SkillMap): Progress {
  const skills = [...map.skills].sort((a, b) => a.sequence - b.sequence);
  const passedCount = Math.ceil(skills.length * 0.4);
  const out: Progress = new Map();
  skills.forEach((s, i) => {
    if (i === 0) out.set(s.id, { status: "mastered", accuracyStars: 5, timingStars: 4.5 });
    else if (i < passedCount) out.set(s.id, { status: "passed", accuracyStars: 3.5, timingStars: 3 });
  });
  for (const s of skills) {
    if (out.has(s.id)) continue;
    const ready = s.prerequisites.every((p) => isPassed(out.get(p)));
    out.set(s.id, { status: ready ? "current" : "locked", accuracyStars: null, timingStars: null });
  }
  return out;
}

/** The skills a piece needs. Until song analysis (M3), a piece needs its hand-assigned skill. */
export function requiredSkills(piece: PieceSummary): string[] {
  return piece.skillId ? [piece.skillId] : [];
}

/** Library-ready: every required skill passed (§6.8). Otherwise the skills still to reach. */
export function libraryState(piece: PieceSummary, map: SkillMap, progress: Progress): { ready: boolean; toReach: Skill[] } {
  const byId = new Map(map.skills.map((s) => [s.id, s]));
  const toReach = new Map<string, Skill>();
  const visit = (id: string) => {
    if (isPassed(progress.get(id)) || toReach.has(id)) return;
    const s = byId.get(id);
    if (!s) return;
    for (const p of s.prerequisites) visit(p);
    toReach.set(id, s);
  };
  requiredSkills(piece).forEach(visit);
  const list = [...toReach.values()].sort((a, b) => a.sequence - b.sequence);
  return { ready: list.length === 0, toReach: list };
}

export type SessionReason = "Review" | "New" | "Practice" | "Your pick";

export interface SessionItem {
  kind: "lesson" | "piece" | "pick";   // pick: the student chooses from the library
  reason: SessionReason;
  skillId: string | null;
  pieceId: string | null;
  title: string;
}

/** A sample session in the §8.5 slot order: warm-up review, new (concept lesson and a piece),
 *  practice, and the reward pick. The server builds the real queue in M5. */
export function sampleSession(map: SkillMap, pieces: PieceSummary[], progress: Progress): SessionItem[] {
  const skills = [...map.skills].sort((a, b) => a.sequence - b.sequence);
  const piecesOf = (s: Skill) => (s.pieces ?? []).map((id) => pieces.find((p) => p.id === id)).filter((p): p is PieceSummary => !!p);
  const items: SessionItem[] = [];
  const passed = skills.filter((s) => isPassed(progress.get(s.id)));
  const current = skills.filter((s) => progress.get(s.id)?.status === "current");
  const review = passed.map(piecesOf).flat()[0];
  if (review) items.push({ kind: "piece", reason: "Review", skillId: review.skillId ?? null, pieceId: review.id, title: review.title });
  current.forEach((s, i) => {
    if (i === 0) items.push({ kind: "lesson", reason: "New", skillId: s.id, pieceId: null, title: s.name });
    const p = piecesOf(s)[0];
    if (p) items.push({ kind: "piece", reason: i === 0 ? "New" : "Practice", skillId: s.id, pieceId: p.id, title: p.title });
  });
  items.push({ kind: "pick", reason: "Your pick", skillId: null, pieceId: null, title: "Any song you like" });
  return items;
}
