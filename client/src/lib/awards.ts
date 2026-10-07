// Rewards (arch §3 "Rewards", M10): the star collection and medals, from the App API (api/app/awards.py).
// The star collection is each song's best accuracy stars added up, so it grows only by playing a song
// better than before. Medals come in four tiers; milestone medals are steps along a measure (stars,
// streak, skills mastered, five-star songs, songs played, hours), and unit and level medals are
// bronze (every skill passed), silver (every one mastered) and gold (every one mastered with 5 stars).

export type Tier = "bronze" | "silver" | "gold" | "platinum";
export type SeriesKind = "stars" | "streak" | "mastered" | "fivestar" | "songs" | "hours";
export type AwardKind = SeriesKind | "unit" | "level";

export interface Award { id: string; kind: AwardKind; tier: Tier; title: string; detail: string; date: string; new?: boolean }

/** In the student's state: for Home, the song library and the tab bar. */
export interface Rewards { stars: number; starsToday: number; songStars: Record<string, number>; unseen: number }

/** What one attempt added (in its effects, after the server stores it). */
export interface AttemptRewards {
  awards: Award[];
  stars: { total: number; gained: number };
  best: { previous: number; now: number } | null;
}

export interface Earned { date: string; new: boolean }
export interface SeriesStep { at: number; tier: Tier; label: string; earned: Earned | null }
export interface Series { kind: SeriesKind; name: string; value: number; steps: SeriesStep[]; next: SeriesStep | null }
export interface GroupMedal { key: "complete" | "mastered" | "fivestar"; tier: Tier; label: string; earned: Earned | null }
export interface Tally { skills: number; passed: number; mastered: number; fivestar: number; medals: GroupMedal[] }
export interface UnitAwards extends Tally { unit: string }
export interface LevelAwards extends Tally { level: string; units: UnitAwards[] }

/** GET /api/students/{id}/awards: the trophy case. */
export interface AwardsReport {
  stars: { total: number; today: number; week: number };
  series: Series[];
  levels: LevelAwards[];
  recent: Award[];
  count: number;
  unseen: number;
}

export const TIER_NAME: Record<Tier, string> = { bronze: "Bronze", silver: "Silver", gold: "Gold", platinum: "Platinum" };

/** Stars in half steps as text: 4.5 -> "4½". */
export function starText(n: number): string {
  const whole = Math.floor(n + 1e-9);
  return `${whole || (n % 1 ? "" : "0")}${n - whole > 0.25 ? "½" : ""}`;
}

/** What a unit or level medal is called when it is earned. */
export function groupHeadline(a: Award): string {
  const what = a.kind === "level" ? "Level" : "Unit";
  return a.detail === "Complete" ? `${what} complete` : `${what}: ${a.detail.toLowerCase()}`;
}

/** The highest medal earned in a row of steps (null when none yet). */
export function topStep(s: Series): SeriesStep | null {
  return [...s.steps].reverse().find((x) => x.earned) ?? null;
}
