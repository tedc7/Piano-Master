// The content index and skill map (written by tools/build_content.py), loaded once per page load
// and shared by the screens that list songs and skills.
import type { PieceSummary, SkillMap } from "./types";

export interface Content { map: SkillMap; pieces: PieceSummary[]; version: string }

let loading: Promise<Content> | null = null;

export function loadContent(): Promise<Content> {
  loading ??= Promise.all([
    fetch("content/skillmap.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    fetch("content/index.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
  ]).then(([map, idx]) => ({ map, pieces: idx.pieces, version: idx.contentVersion ?? "" }))
    .catch((e) => { loading = null; throw e; });
  return loading;
}

export const handsLabel = (h: string) => (h === "RL" ? "Both hands" : h === "L" ? "Left hand" : "Right hand");
