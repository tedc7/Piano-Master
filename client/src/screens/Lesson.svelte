<script lang="ts">
  // Concept lesson (arch §3 screen 4, "Teaching concepts"): a short sequence of cards the student
  // taps through, from content/lessons/ (built into content/lessons/<skill>.json):
  //  - Explain: a few sentences, read aloud;
  //  - Show: the keys light up in order with their finger numbers, and the notes on a small staff;
  //  - Hear: the app plays the example, then a contrast;
  //  - Try: the student plays it on the piano; each note is confirmed, with the next key lit as a hint;
  //  - Check: tap the right key on screen or play it, or tap one of the answers (after listening,
  //    for an "identify" question); a wrong answer goes back to Show;
  //  - Echo: the app plays a short phrase and the student plays it back (ear training);
  //  - Watch: a parent-approved video, if one has been added.
  // Going through it makes the skill Current (arch §8.1); in parent mode nothing is recorded, and
  // the parent can skip the Try, Check and Echo cards to review the rest. Check questions score 1
  // right first time and 0.5 the second; Echo scores by edit distance, 10% less per replay; the
  // total goes to the server with the lesson (§7.8), where it passes a theory skill.
  // Reading aloud (v0.34): the lesson voice's recordings (lib/lessonVoice). With Auto-read on (the
  // student's choice for every lesson, remembered like Metro), each card is read a moment after it
  // appears, so the child sees the page and its words first, and the praise is spoken; then a Show
  // card says "I'll show you" and plays its keys (Show me again says it too), and a Hear or Echo card
  // says "Here it is" and plays its tune (a contrast is read before it plays, too). Read it to me reads the
  // card again at any time, and becomes Stop reading while anything is being read.
  import { onMount, tick, untrack } from "svelte";
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { conceptType, loadContent } from "../lib/content";
  import { KeyboardView, keyboardRange, noteName } from "../lib/keyboard";
  import type { MidiNote, MidiPedal } from "../lib/midi";
  import { go } from "../lib/route";
  import { renderMini, type MiniNote } from "../lib/staff";
  import { stars } from "../lib/scoring";
  import { echoScore, MAX_REPLAYS, questionPoints } from "../lib/theory";
  import { SAY } from "../lib/lessonPhrases";
  import { LessonVoice } from "../lib/lessonVoice.svelte";
  import Stars from "../components/Stars.svelte";
  import type { Hand, Skill } from "../lib/types";

  let { skillId }: { skillId: string } = $props();

  interface Question { text: string; answer: MiniNote | string; choices?: string[]; hear?: MiniNote[] }
  interface Card {
    kind: "explain" | "show" | "hear" | "try" | "check" | "echo" | "watch";
    text: string;
    notes?: MiniNote[];
    fingers?: number[] | null;
    hand?: "R" | "L" | "RL";
    clef?: "treble" | "bass" | "grand";
    play?: MiniNote[];
    tempo?: number;
    contrast?: { text: string; play: MiniNote[]; level?: number };
    level?: number;                  // how hard the app's piano plays a Hear card: loud and soft
    questions?: Question[];
    video?: string;
  }
  interface Lesson { skill: string; title: string; cards: Card[] }

  const READ_DELAY_MS = 800;       // a new card shows this long before it is read aloud

  const NAMES: Record<Card["kind"], [string, string]> = {
    explain: ["Explain", "💬"], show: ["Show", "👀"], hear: ["Hear", "👂"], try: ["Try", "🎹"], check: ["Check", "✅"], echo: ["Echo", "🦜"], watch: ["Watch", "🎬"],
  };

  let skill = $state<Skill | null>(null);
  let lesson = $state<Lesson | null>(null);
  let error = $state("");
  let step = $state(0);
  let done = $state<boolean[]>([]);            // Try and Check cards completed
  let progress = $state(0);                    // notes played on Try, questions answered on Check
  let feedback = $state("");
  let staffHost = $state<HTMLDivElement | null>(null);
  let kbHost = $state<HTMLDivElement | null>(null);
  let kb: KeyboardView | null = null;
  let heads: Element[][] = [];
  let timers: number[] = [];
  // scoring (§7.8): wrong answers so far and the points of the first right answer, per question
  let wrongTries: Record<string, number> = {};
  let points: Record<string, number> = {};
  let echoPlayed = $state<number[]>([]);
  let replays = $state(0);
  let echoResult = $state<number | null>(null);
  let echoTimer = 0;
  let hearingUntil = 0;
  let intro = 0;                               // the reading-then-action under way; a newer one, or leaving, cancels it
  let heardIn = -1;                            // the visit to a card in which its tune was last played
  let entry = 0;                               // which visit to a card this is
  const voice = new LessonVoice(app.audio);
  const autoRead = $derived(app.prefs.autoRead ?? true);

  // fixed when the screen opens, like the Play screen's session item
  const itemId = untrack(() => app.session?.items.find((i) => !i.done && i.kind === "lesson" && i.skillId === skillId)?.id ?? null);
  const inSession = itemId !== null;
  const opened = performance.now();

  onMount(() => {
    const off = app.midi.onEvent(onMidi);
    (window as unknown as { __lesson: unknown }).__lesson = { get card() { return card; }, get progress() { return progress; },
                                                             get step() { return step; }, get done() { return done[step]; },
                                                             get echo() { return { played: echoPlayed, result: echoResult }; },
                                                             get points() { return points; },
                                                             get voice() { return { speaking: voice.speaking, log: voice.log, autoRead }; },
                                                             get heard() { return { thisCard: heardIn === entry, until: hearingUntil }; } };
    void (async () => {
      try { skill = (await loadContent()).map.skills.find((s) => s.id === skillId) ?? null; } catch { /* title only */ }
      try {
        const r = await fetch(`content/lessons/${encodeURIComponent(skillId)}.json`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        lesson = await r.json();
        done = lesson!.cards.map((c) => c.kind !== "try" && c.kind !== "check" && c.kind !== "echo");
        void voice.preload([...lesson!.cards.flatMap((c) => [c.text, ...(c.questions ?? []).map((q) => q.text), c.contrast?.text ?? ""]),
                            ...Object.values(SAY)]);
        await enter();
      } catch (e) {
        error = `This lesson isn't ready yet (${(e as Error).message}).`;
      }
    })();
    return () => {
      off(); clearTimers(); kb?.destroy();
      delete (window as unknown as { __lesson?: unknown }).__lesson;
      voice.stop();
    };
  });

  const card = $derived(lesson?.cards[step] ?? null);
  const last = $derived(!!lesson && step === lesson.cards.length - 1);
  const canNext = $derived(!!card && (done[step] || app.parentMode));
  /** What Read it to me reads: a Check card's current question, otherwise the card's words. */
  const reading = () => (card?.kind === "check" && card.questions && !done[step] ? card.questions[progress].text : card?.text ?? "");

  function clearTimers(): void {
    timers.forEach((t) => clearTimeout(t));
    timers = [];
  }

  /** Set up the card on screen: its staff, its keyboard, and what it does straight away. `keepVoice`
   *  lets a line being read finish (until this card's own reading starts). */
  async function enter(keepVoice = false): Promise<void> {
    clearTimers();
    entry++;
    intro++;
    if (!keepVoice) voice.stop();
    feedback = "";
    progress = 0;
    kb?.destroy();
    kb = null;
    await tick();
    const c = card;
    if (!c) return;
    const acts = c.kind === "show" || c.kind === "echo" || (c.kind === "hear" && autoRead);
    if (autoRead && !acts) timers.push(window.setTimeout(() => void voice.speak(reading()), READ_DELAY_MS));
    const answers = (c.questions ?? []).flatMap((q) => [...(typeof q.answer === "string" ? [] : [q.answer]), ...(q.hear ?? [])]);
    const all = [...(c.notes ?? []), ...(c.play ?? []), ...answers, ...(c.contrast?.play ?? [])];
    if (kbHost && all.length) {
      const ps = all.flatMap((n) => n.pitches);
      const [lo, hi] = keyboardRange(Math.min(...ps), Math.max(...ps));
      kb = new KeyboardView(kbHost, lo, hi);
      if (c.kind === "check") kb.onTap((p) => answer(p));
    }
    if (staffHost && c.notes) heads = renderMini(staffHost, c.notes, c.clef ?? "treble");
    if (c.kind === "show") void readThen(true, SAY.showYou, showMe);
    if (c.kind === "hear" && autoRead) void readThen(true, SAY.hereItIs, () => void hear(c.play ?? [], c.tempo, c.level));
    if (c.kind === "try") hint();
    if (c.kind === "echo") {
      echoPlayed = [];
      replays = 0;
      echoResult = null;
      if (autoRead) void readThen(true, SAY.hereItIs, () => void hear(c.play ?? [], c.tempo));
      else timers.push(window.setTimeout(() => void hear(c.play ?? [], c.tempo), 900));
    }
  }

  const handOf = (c: Card, i: number): Hand => (c.hand === "RL" ? (Math.min(...c.notes![i].pitches) < 60 ? "L" : "R") : (c.hand ?? "R") as Hand);

  function light(i: number | null): void {
    const c = card!;
    heads.flat().forEach((h) => h.classList.remove("pm-glow"));
    if (i === null) { kb?.setTargets([]); return; }
    heads[i]?.forEach((h) => h.classList.add("pm-glow"));
    kb?.setTargets(c.notes![i].pitches.map((p) => ({ pitch: p, hand: handOf(c, i), finger: c.fingers?.[i] })));
  }

  /** With Auto-read on: read the card (on arriving, after the pause), say `cue` ("I'll show you",
   *  "Here it is"), then do what the card does (`act`: its keys or its tune). Stop reading skips straight
   *  to `act`; leaving the card, or a tap that does `act` itself, cancels the rest. With Auto-read off,
   *  `act` at once. */
  async function readThen(readCard: boolean, cue: string, act: () => void): Promise<void> {
    const at = ++intro;
    if (autoRead) {
      if (readCard) {
        await new Promise((r) => timers.push(window.setTimeout(r, READ_DELAY_MS)));
        if (at !== intro) return;
        const read = await voice.speak(reading());
        if (at !== intro) return;
        if (!read) { act(); return; }
      }
      await voice.speak(cue);
      if (at !== intro) return;
    }
    act();
  }

  /** A tap that plays or shows something now: whatever reading-then-action was under way stops. */
  function now(): void {
    intro++;
    voice.stop();
  }

  /** Show me again: the keys again ("I'll show you" first with Auto-read on), replacing what was under way. */
  function showAgain(): void {
    clearTimers();
    light(null);
    void readThen(false, SAY.showYou, showMe);
  }

  /** Now listen to this: the contrast, read first with Auto-read on, then played. */
  function contrast(): void {
    const k = card!.contrast!;
    feedback = k.text;
    now();
    const at = intro;
    const play = () => { if (at === intro) void hear(k.play, card!.tempo, k.level); };
    if (autoRead) void voice.speak(k.text).then(play); else play();
  }

  /** Show: each key in turn, with its finger number and its note on the staff. */
  function showMe(): void {
    clearTimers();
    const c = card!;
    const gap = 700;
    c.notes!.forEach((_, i) => timers.push(window.setTimeout(() => light(i), 400 + i * gap)));
    timers.push(window.setTimeout(() => light(null), 400 + c.notes!.length * gap + 600));
  }

  /** Hear: the notes on the app's piano, at the card's tempo. */
  async function hear(notes: MiniNote[], tempo = 90, level = 1): Promise<void> {
    const ctx = await app.audio.ensure();
    await app.audio.loadPiano(notes.flatMap((n) => n.pitches));
    const spb = 60 / tempo;
    let t = ctx.currentTime + 0.1;
    hearingUntil = performance.now() + (0.1 + notes.reduce((n, x) => n + x.beats, 0) * spb) * 1000;
    heardIn = entry;
    for (const n of notes) {
      for (const p of n.pitches) app.audio.piano(p, t, n.beats * spb * 0.95, level);
      const at = t;
      timers.push(window.setTimeout(() => {
        for (const p of n.pitches) { kb?.press(p, "neutral"); timers.push(window.setTimeout(() => kb?.release(p), n.beats * spb * 900)); }
      }, (at - ctx.currentTime) * 1000));
      t += n.beats * spb;
    }
  }

  /** Try: the next note to play is lit. */
  function hint(): void {
    const c = card!;
    if (progress < c.notes!.length) light(progress); else light(null);
  }

  const held = new Set<number>();
  function onMidi(ev: MidiNote | MidiPedal): void {
    if (ev.type === "pedal" || !card) return;
    if (ev.type === "off") { held.delete(ev.pitch); kb?.release(ev.pitch); return; }
    held.add(ev.pitch);
    if (card.kind === "try") tryKey(ev.pitch);
    else if (card.kind === "check") answer(ev.pitch);
    else if (card.kind === "echo") echoKey(ev.pitch);
    else kb?.press(ev.pitch, "neutral");
  }

  function tryKey(pitch: number): void {
    const c = card!;
    if (done[step]) { kb?.press(pitch, "neutral"); return; }
    const want = c.notes![progress].pitches;
    if (want.includes(pitch)) {
      kb?.press(pitch, "ok");
      if (want.every((p) => held.has(p))) {
        progress++;
        feedback = progress < c.notes!.length ? "Yes!" : `${SAY.tryDone} 🎉`;
        if (progress >= c.notes!.length) { done[step] = true; say(SAY.tryDone); }
        hint();
      }
    } else {
      kb?.press(pitch, "wrong");
      const flats = want.some((p) => [1, 3, 6, 8, 10].includes(p % 12)) && c.notes![progress].spelled.some((x) => x.alter < 0);
      feedback = `Not quite: find the lit key, ${want.map((p) => noteName(p, flats)).join(" + ")}.`;
    }
  }

  /** Check: the answer is a tapped or played key (a chord needs all its keys)... */
  function answer(pitch: number): void {
    const c = card!;
    if (done[step] || !c.questions) return;
    const q = c.questions[progress];
    if (typeof q.answer === "string") return;           // a question answered with the buttons
    if (q.answer.pitches.includes(pitch)) {
      kb?.press(pitch, "ok");
      if (q.answer.pitches.length > 1 && !q.answer.pitches.every((p) => held.has(p) || p === pitch)) return;
      rightAnswer(() => kb?.release(pitch));
    } else {
      kb?.press(pitch, "wrong");
      wrongAnswer();
    }
  }

  /** ...or one of the answers on the buttons. */
  function choose(choice: string): void {
    const c = card!;
    if (done[step] || !c.questions) return;
    if (choice === c.questions[progress].answer) rightAnswer(); else wrongAnswer();
  }

  const qKey = () => `${step}/${progress}`;

  function rightAnswer(after?: () => void): void {
    const c = card!;
    const k = qKey();
    if (!(k in points)) points[k] = questionPoints(wrongTries[k] ?? 0);   // the first time it is got right
    progress++;
    if (progress >= c.questions!.length) { done[step] = true; feedback = `${SAY.checkDone} 🎉`; say(SAY.checkDone); }
    else { feedback = "Yes!"; timers.push(window.setTimeout(() => { after?.(); say(c.questions![progress].text); }, 600)); }
  }

  function wrongAnswer(): void {
    const k = qKey();
    wrongTries[k] = (wrongTries[k] ?? 0) + 1;
    feedback = SAY.lookAgain;
    say(SAY.lookAgain);
    const show = lesson!.cards.findIndex((x) => x.kind === "show");
    if (show >= 0) timers.push(window.setTimeout(() => { step = show; void enter(true); }, 1200));   // "Let's look…" finishes
  }

  /** Echo: the student plays the phrase back; it is scored when they have played as many notes,
   *  or stop for 2.5 seconds. Keys pressed while the app is still playing it don't count. */
  function echoKey(pitch: number): void {
    kb?.press(pitch, "neutral");
    if (echoResult !== null || heardIn !== entry || performance.now() < hearingUntil) return;   // not yet heard, or still playing
    echoPlayed = [...echoPlayed, pitch];
    clearTimeout(echoTimer);
    if (echoPlayed.length >= echoWant().length) finishEcho();
    else echoTimer = window.setTimeout(finishEcho, 2500);
  }

  const echoWant = () => (card?.play ?? []).flatMap((n) => n.pitches);

  function finishEcho(): void {
    clearTimeout(echoTimer);
    echoResult = echoScore(echoWant(), echoPlayed, replays);
    const k = `${step}/echo`;
    if (!(k in points)) points[k] = echoResult;          // the first play-back counts; more are practice
    done[step] = true;
    const line = echoResult >= 0.99 ? SAY.perfect : echoResult >= 0.74 ? SAY.nice : SAY.goodTry;
    feedback = line === SAY.goodTry ? line : `${line} 🎉`;
    say(line);
  }

  function echoReplay(): void {
    if (echoPlayed.length || replays >= MAX_REPLAYS) return;
    now();
    replays++;
    void hear(card!.play ?? [], card!.tempo);
  }

  function echoAgain(): void {
    echoPlayed = [];
    echoResult = null;
    feedback = "";
    now();
    void hear(card!.play ?? [], card!.tempo);
  }

  /** Something the lesson says by itself (praise, the next question): only with Auto-read on. */
  function say(text: string): void {
    if (autoRead) void voice.speak(text);
  }

  /** Read it to me, or Stop reading. */
  function readButton(): void {
    if (voice.speaking) voice.stop(); else void voice.speak(reading());
  }

  /** Auto-read on or off, for every lesson; turned on, it reads this card now. */
  function toggleAutoRead(): void {
    const on = !autoRead;
    app.setAutoRead(on);
    if (on) void voice.speak(reading()); else voice.stop();
  }

  function move(by: number): void {
    const next = step + by;
    if (next < 0) { leave(); return; }
    step = next;
    void enter();
  }

  function finish(): void {
    const questions = lesson!.cards.reduce((n, c) => n + (c.kind === "check" ? c.questions?.length ?? 0 : c.kind === "echo" ? 1 : 0), 0);
    const got = Object.values(points).reduce((a, b) => a + b, 0);
    app.lessonDone(skillId, itemId, (performance.now() - opened) / 1000, questions ? { questions, points: got } : undefined);
    if (inSession) go("session"); else leave();
  }

  function leave(): void {
    if (inSession) go("session"); else if (history.length > 1) history.back(); else go("journey");
  }
</script>

<div class="screen">
  <Status title={`💡 ${lesson?.title ?? skill?.name ?? "Concept lesson"}`}>
    {#if lesson}<span class="muted">Card {step + 1} of {lesson.cards.length}</span>{/if}
  </Status>
  <main class="body center">
    <div class="lesson">
      {#if error}<p class="notice error">{error}</p>{/if}
      {#if lesson && card}
        <div class="steps">
          {#each lesson.cards as c, i (i)}
            <span class="dot" class:on={i === step} class:past={i < step}>{NAMES[c.kind][0]}</span>
          {/each}
        </div>
        <div class="card-big">
          <div class="head"><span class="icon">{NAMES[card.kind][1]}</span><h1>{NAMES[card.kind][0]}</h1>
            <!-- the kind of idea this lesson teaches: Notes, Rhythm, Technique, Theory, Musicianship -->
            {#if card.kind === "explain" && skill}<span class="type" style:background={conceptType(skill.track).color}>{conceptType(skill.track).label}</span>{/if}
          </div>
          {#if card.text}<p class="text">{card.text}</p>{/if}
          {#if card.kind === "check" && card.questions && !done[step]}
            {@const q = card.questions[progress]}
            <p class="text question">{q.text}</p>
            {#if q.hear}<button class="quiet" onclick={() => hear(q.hear ?? [], 90)}>▶ Listen</button>{/if}
            {#if q.choices}
              <div class="choices">
                {#each q.choices as ch (ch)}<button class="choice" onclick={() => choose(ch)}>{ch}</button>{/each}
              </div>
            {/if}
          {/if}
          {#if card.kind === "echo"}
            <p class="muted">{echoResult !== null ? `${echoPlayed.length} note${echoPlayed.length === 1 ? "" : "s"} played` : echoPlayed.length ? `${echoPlayed.length} of ${echoWant().length}…` : "Listen, then play it back."}</p>
            {#if echoResult !== null}<Stars label="♪" value={stars(echoResult)} />{/if}
          {/if}
          {#if card.notes}<div class="mini" bind:this={staffHost}></div>{/if}
          {#if card.kind === "watch" && card.video}
            <!-- svelte-ignore a11y_media_has_caption -->
            <video src={card.video} controls controlslist="nodownload noplaybackrate" disablepictureinpicture></video>
          {/if}
          {#if feedback}<p class="feedback" class:good={feedback.startsWith("Yes") || feedback.includes("🎉")}>{feedback}</p>{/if}
          <div class="actions">
            <button class="quiet read" onclick={readButton}>{voice.speaking ? "⏹ Stop reading" : "🔊 Read it to me"}</button>
            <button class="toggle autoread" class:off={!autoRead} onclick={toggleAutoRead} aria-pressed={autoRead}
                    title="Read each card aloud by itself, in every lesson">Auto-read</button>
            {#if card.kind === "show"}<button class="quiet" onclick={showAgain}>👀 Show me again</button>{/if}
            {#if card.kind === "hear"}
              <button onclick={() => { now(); void hear(card.play ?? [], card.tempo, card.level); }}>▶ Play it</button>
              {#if card.contrast}<button class="quiet" onclick={contrast}>▶ Now listen to this</button>{/if}
            {/if}
            {#if card.kind === "echo"}
              {#if echoResult === null}
                <button class="quiet" onclick={echoReplay} disabled={!!echoPlayed.length || replays >= MAX_REPLAYS}>▶ Play it again{replays ? ` (${MAX_REPLAYS - replays} left)` : ""}</button>
              {:else}
                <button class="quiet" onclick={echoAgain}>🔁 Try again</button>
              {/if}
            {/if}
            {#if (card.kind === "try" || card.kind === "echo") && app.midiStatus !== "connected"}<span class="muted">Connect the piano to try it.</span>{/if}
          </div>
        </div>
        {#if card.notes || card.play || card.questions}<div class="keys" bind:this={kbHost}></div>{/if}
        <div class="row">
          <button class="quiet" onclick={() => move(-1)}>‹ Back</button>
          {#if !done[step] && app.parentMode}<span class="muted">Parent mode: you can skip this card.</span>{/if}
          {#if !last}
            <button class="next" disabled={!canNext} onclick={() => move(1)}>Next ›</button>
          {:else}
            <button class="next" disabled={!canNext} onclick={finish}>{inSession ? "Next ›" : "Done"}</button>
          {/if}
        </div>
      {/if}
    </div>
  </main>
</div>

<style>
  .center { display: flex; justify-content: center; }
  .lesson { width: min(860px, 100%); }
  .steps { display: flex; gap: 8px; justify-content: center; margin-bottom: 12px; flex-wrap: wrap; }
  .dot { padding: 4px 12px; border-radius: 999px; background: #ecebe6; color: var(--muted); font-weight: 650; font-size: 14px; }
  .dot.past { background: #d7ecdf; color: var(--ok); }
  .dot.on { background: var(--accent); color: #fff; }
  .card-big {
    background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 18px 26px;
    text-align: center; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  }
  .head { display: flex; align-items: center; justify-content: center; gap: 12px; }
  .head h1 { margin: 0 !important; }
  .type { color: #fff; border-radius: 999px; padding: 3px 12px; font-size: 15px; font-weight: 800; }
  .icon { font-size: 40px; }
  .text { font-size: 21px; line-height: 1.45; margin: 10px 0; }
  .question { font-weight: 700; }
  .choices { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin: 8px 0; }
  .choice { min-width: 110px; min-height: 60px; font-size: 22px; }
  .mini { display: flex; justify-content: center; margin: 4px 0; }
  .feedback { font-size: 20px; font-weight: 700; color: #8a5a00; margin: 6px 0; }
  .feedback.good { color: var(--ok); }
  .read { min-width: 190px; }
  .actions { display: flex; gap: 10px; justify-content: center; align-items: center; flex-wrap: wrap; margin-top: 8px; }
  video { max-width: 100%; max-height: 320px; border-radius: 12px; }
  .keys { position: relative; height: 170px; background: #2a2a2e; margin-top: 12px; border-radius: 10px; }
  .row { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; gap: 12px; }
  .next { min-width: 180px; min-height: 60px; font-size: 20px; }
  .next:disabled { opacity: 0.45; }
</style>
