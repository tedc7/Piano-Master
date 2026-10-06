// The lesson screen's own spoken lines (arch §10.5, v0.34). tools/voice records them with the lessons'
// words, reading this file: keep each one on its own line, as `key: "text",`.
export const SAY = {
  tryDone: "You did it!",
  checkDone: "All right!",
  lookAgain: "Let's look at it again.",
  perfect: "Perfect!",
  nice: "Nice listening!",
  goodTry: "Good try! Listen again and play it back.",
  showYou: "I'll show you.",
  hereItIs: "Here it is.",
} as const;
