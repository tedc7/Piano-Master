import { describe, expect, it } from "vitest";
import { libraryState, type Progress, type SkillProgress, type SkillStatus } from "../src/lib/progress";
import type { PieceSummary, Skill, SkillMap } from "../src/lib/types";

const skill = (id: string, sequence: number, prerequisites: string[] = []): Skill =>
  ({ id, name: id, sequence, track: "reading", staff: "treble", prerequisites, map: "basic", level: "Prep A", placeholder: false });
const map: SkillMap = { placeholder: false, maps: [], skills: [skill("a", 10), skill("b", 20, ["a"]), skill("c", 30, ["b"])] };
const piece = (requiredSkills: string[]): PieceSummary => ({ id: "p", title: "P", kind: "song", hands: "R", requiredSkills } as PieceSummary);
const progress = (states: Record<string, SkillStatus>): Progress =>
  new Map(Object.entries(states).map(([id, status]) => [id, { skillId: id, status } as SkillProgress]));

describe("library-ready (arch §6.8)", () => {
  it("opens what Today's Practice may ask for: one skill still being learned (v0.47)", () => {
    expect(libraryState(piece(["a", "b"]), map, progress({ a: "passed", b: "current" })).ready).toBe(true);
    expect(libraryState(piece(["a", "b"]), map, progress({ a: "passed", b: "passed" })).ready).toBe(true);
  });

  it("stays closed with a locked skill, or two still being learned", () => {
    expect(libraryState(piece(["a", "b"]), map, progress({ a: "passed", b: "locked" })).ready).toBe(false);
    expect(libraryState(piece(["b", "c"]), map, progress({ a: "passed", b: "current", c: "current" })).ready).toBe(false);
  });

  it("names the skills still to reach", () => {
    const s = libraryState(piece(["c"]), map, progress({ a: "passed", b: "current", c: "locked" }));
    expect(s.ready).toBe(false);
    expect(s.toReach.map((k) => k.id)).toEqual(["b", "c"]);
  });
});
