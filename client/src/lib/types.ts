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
}

export interface Measure {
  number: number;
  start: number;
  duration: number;
  keySig?: number;
  timeSig?: string;
  repeatStart?: boolean;
  repeatEnd?: boolean;
  volta?: number[];
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
  playbackOrder: { measure: number; verse: number }[];
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

export interface Piece {
  id: string;
  title: string;
  composer?: string;
  kind: "core" | "library";
  genre?: string;
  level?: string;
  hands: "R" | "L" | "RL";
  skillId?: string | null;
  contentVersion?: string;
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
  map: string;
  level: string;
  placeholder: boolean;
}

export interface SkillMap {
  placeholder: boolean;
  maps: { map: string; level: string; file: string }[];
  skills: Skill[];
}
