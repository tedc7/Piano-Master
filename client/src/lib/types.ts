// Content as written by tools/build_content.py: the arch §5 Arrangement notation plus piece metadata.

export type Hand = "R" | "L";
export type Preset = "100" | "90" | "75" | "50";
export const PRESETS: Preset[] = ["50", "75", "90", "100"];

export interface Spelled { step: string; alter: number; octave: number }

export interface Note {
  pitch: number;
  spelled: Spelled;
  start: number;       // beats (quarter notes) in the written score
  duration: number;
  staff: number;       // index into header.staves
  hand: Hand;
  voice: number;
  isMelody?: boolean;
  tieToNext?: boolean;
  finger?: number;
  fermata?: boolean;
  tuplet?: [number, number];   // [actual, normal]: 3 in the time of 2 for a triplet
}

/** A grace note: drawn before the note it leads into, never scored or counted. */
export interface Grace { pitch: number; spelled: Spelled; start: number; staff: number; voice: number; hand: Hand; slash: boolean; order: number }

export interface Measure {
  number: number;
  start: number;
  duration: number;
  keySig?: number;
  timeSig?: string;
  repeatStart?: boolean;
  repeatEnd?: boolean;
  volta?: number[];
  clefs?: Record<string, "treble" | "bass">;   // clef changes at the start of this bar, by staff
}

export interface Lyric { note: number; verse: number; text: string; syllabic: string }

export interface Notation {
  header: {
    keySig: number;
    timeSig: string;
    barLength: number;
    tempo: number;
    pickupBeats: number;
    range: [number, number];
    staves: ("treble" | "bass")[];
  };
  measures: Measure[];
  notes: Note[];
  lyrics: Lyric[];
  chordSymbols: { beat: number; symbol: string; derived?: boolean }[];
  graces?: Grace[];
  playbackOrder: { measure: number; verse: number; pass?: number }[];
  phrases: number[];   // phrase start beats on the playback timeline
  length: number;      // playback length in beats
}

export interface StemFile { url: string; bytes: number }

export interface Media {
  engine: string;
  take: string;
  padBeats: number;    // stem time 0 is this many beats before playback beat 0 (the muted lead-in)
  bpm: number;
  presets: Partial<Record<Preset, { ratio: number; vocals: StemFile; accompaniment: StemFile }>>;
  check?: {
    notesOnPitch: number;
    wordsOff: number;
    firstWordSung: boolean;
    wordStretches: string[];
    melodyStretches: string[];
  } | null;
}

/** A generated drill (arch §8.9): served by the piano server for one student. */
export interface DrillInfo {
  kind: string;               // reading, rhythm, scale…
  patternId?: string;         // the error pattern it remedies (§8.8)
  anyKey?: number;            // rhythm tapping: any key counts as this pitch; only timing matters
}

export interface Piece {
  id: string;
  title: string;
  composer?: string;
  kind: "core" | "library" | "drill";
  drill?: DrillInfo;
  genre?: string;
  level?: string;
  hands: "R" | "L" | "RL";
  skillId?: string | null;
  contentVersion?: string;
  keyboardSize?: 61 | 88;
  notation: Notation;
  media: Media | null;
}

export interface PieceSummary {
  id: string;
  title: string;
  composer?: string;
  kind: string;
  hands: "R" | "L" | "RL";
  skillId?: string | null;
  tempo: number;
  timeSig: string;
  measures: number;
  beats?: number;
  phrases?: number;
  requiredSkills?: string[];
  featuredSkills?: string[];
  mapPoint?: number | null;
  skillMeasures?: Record<string, number[]>;
  beyondMap?: string[];               // what no skill in the map covers yet (song analysis, §6.8)
  keyboardSize?: 61 | 88;
  level?: string;
  genre?: string;
  song?: string;                      // the song this is an arrangement of (several arrangements share it)
  songTitle?: string;
  version?: string | null;            // e.g. "Beginner", when a song has several arrangements
  hasMedia: boolean;
}

export interface Skill {
  id: string;
  name: string;
  sequence: number;
  track: string;
  staff: string;
  prerequisites: string[];
  description?: string;
  pieces?: string[];
  requiredCapabilities?: string[];
  conceptLesson?: boolean;
  map: string;
  level: string;
  placeholder: boolean;
}

export interface SkillMap {
  placeholder: boolean;
  maps: { map: string; level: string; file: string }[];
  skills: Skill[];
}
