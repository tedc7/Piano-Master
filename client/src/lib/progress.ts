// Skill states, song readiness and today's session, as the lesson engine on the piano server
// reports them (arch §6.8, §8.1, §8.5). The server is the one that decides; the client shows it
// and keeps its own copy up to date between requests.
import type { PieceSummary, Skill, SkillMap } from "./types";

export type SkillStatus = "locked" | "current" | "passed" | "mastered";

export interface SkillProgress {
  skillId: string;
  status: SkillStatus;
  lessonOpen: boolean;            // the lightbulb opens when the prerequisites are passed
  conceptDone: boolean;
  hold: boolean;                  // needs a capability this setup lacks, e.g. a pedal
  mastery: number | null;
  bestMastery: number | null;
  accuracyStars: number | null;   // best, after practice-aid scaling (arch §3 "Journey map star display")
  timingStars: number | null;
  stuck: boolean;
  due: boolean;                   // due for review: the refresh badge
  today: boolean;                 // in today's session
  attemptsWithoutPass: number;
  tryAnotherWay: boolean;
  refresher: boolean;
  nextReview: string | null;
}

export type Progress = Map<string, SkillProgress>;

export const isPassed = (p: SkillProgress | undefined) => p?.status === "passed" || p?.status === "mastered" || !!p?.hold;

/** The skills a piece needs. Until song analysis (M3), a piece needs its assigned skill. */
export function requiredSkills(piece: PieceSummary): string[] {
  return piece.requiredSkills ?? (piece.skillId ? [piece.skillId] : []);
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

export type SessionReason = "Review" | "New" | "Tricky spot" | "Polish" | "Support" | "Your pick";

export interface ItemResult { accuracyStars: number | null; timingStars: number | null; title?: string }

export interface SessionItem {
  id: string;
  kind: "lesson" | "piece" | "pick";   // pick: the student chooses from the library
  reason: SessionReason;
  skillId: string | null;
  pieceId: string | null;
  title: string;
  preset: string | null;               // suggested tempo preset (a stuck skill, one slower)
  section: number | null;              // a phrase to loop (a tricky spot)
  est: number;                         // estimated seconds
  done: boolean;
  result: ItemResult | null;
  tries: number;                       // completed attempts without passing the skill
  skipped?: boolean;
}

export interface Session { date: string; targetMinutes: number; items: SessionItem[]; endOfContent: boolean }

export interface Day { date: string; guidedSec: number; freeSec: number; targetMinutes: number; streak: number; completed: boolean }

/** GET /api/students/{id}/state */
export interface StudentState {
  student: { id: string; name: string; avatar: string; settings: unknown };
  contentVersion: string;
  skills: SkillProgress[];
  session: Session;
  day: Day;
  favorites: string[];
}

export const TRY_ANOTHER_WAY = 3;
