// The skill map (written by tools/build_content.py, deployed with the app) and the songs, loaded once
// per page load and shared by the screens that list songs and skills. Every song is in the piano
// server's library (v0.27, arch §10.7), whatever made it; the content version is "<map>+<library>".
// Each child sees the songs the map uses for practice, and the others their genre and song rules
// allow (§10.1); the parent sees everything.
import { api } from "./api";
import type { PieceSummary, SkillMap } from "./types";

export interface Content { map: SkillMap; pieces: PieceSummary[]; version: string }

/** What kind of idea a concept is (its track, arch §6.6), in the words the Journey map and the
 *  concept lesson show, and its colour. */
export const CONCEPT_TYPE: Record<string, { label: string; color: string }> = {
  reading: { label: "Notes", color: "#2f6fdb" },
  rhythm: { label: "Rhythm", color: "#c0561a" },
  technique: { label: "Technique", color: "#2f7d4f" },
  theory: { label: "Theory", color: "#7a4fc9" },
  musicianship: { label: "Musicianship", color: "#b0287a" },
  repertoire: { label: "Pieces", color: "#6b5a2e" },
};
export const conceptType = (track: string) => CONCEPT_TYPE[track] ?? { label: track, color: "#6b6b6b" };
export interface Rules { curriculum: string[]; genres: Record<string, boolean>; songs: Record<string, boolean> }

let loading: Promise<Content> | null = null;

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export function loadContent(): Promise<Content> {
  loading ??= Promise.all([
    json<SkillMap>("content/skillmap.json"),
    json<{ version: string; pieces: PieceSummary[] }>("/api/library")
      .catch((e) => { throw new Error(`can't reach the piano server for the songs: ${(e as Error).message}`); }),
  ]).then(([map, lib]) => ({ map, pieces: lib.pieces, version: `${map.contentVersion ?? ""}+${lib.version}` }))
    .catch((e) => { loading = null; throw e; });
  return loading;
}

/** Forget the loaded content (after the parent approves or deletes songs). */
export function reloadContent(): void {
  loading = null;
}

const rulesCache = new Map<string, Promise<Rules>>();

/** A child's genre and song rules (the piano server's; none offline, which shows only lesson pieces). */
export function rulesFor(studentId: string, fresh = false): Promise<Rules> {
  if (fresh) rulesCache.delete(studentId);
  let r = rulesCache.get(studentId);
  if (!r) {
    r = api.request<Rules>(`/students/${studentId}/rules`).catch(() => ({ curriculum: [], genres: {}, songs: {} }));
    rulesCache.set(studentId, r);
  }
  return r;
}

/** Whether a child may see a song: a song rule overrides everything; the songs the map uses for
 *  practice are allowed; any genre is blocked until the parent allows it (arch §10.1). */
export function allowed(p: PieceSummary, rules: Rules | null): boolean {
  if (!rules) return true;
  const song = p.song ?? p.id;
  if (song in rules.songs) return rules.songs[song];
  return rules.curriculum.includes(song) || rules.genres[p.genre ?? ""] === true;
}

export const handsLabel = (h: string) => (h === "RL" ? "Both hands" : h === "L" ? "Left hand" : "Right hand");

/** A genre as the family reads it: "kids" is Kids' songs, "lesson-pieces" Lesson pieces, "christmas" Christmas. */
export const genreLabel = (g: string) => (g === "kids" ? "Kids' songs" : g.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()));

/** Text as the song search compares it: lower case, letters and digits only ("Twinkle, twinkle" ~ "twinkle twinkle"). */
export const searchText = (s: string | null | undefined) => (s ?? "").toLowerCase().replace(/['’]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
