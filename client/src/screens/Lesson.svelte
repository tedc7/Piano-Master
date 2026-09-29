<script lang="ts">
  // Concept lesson (arch §3 screen 4, "Teaching concepts"): a short sequence of cards the student
  // taps through, from content/lessons/ (built into content/lessons/<skill>.json):
  //  - Explain: a few sentences, read aloud (tap to replay);
  //  - Show: the keys light up in order with their finger numbers, and the notes on a small staff;
  //  - Hear: the app plays the example, then a contrast;
  //  - Try: the student plays it on the piano; each note is confirmed, with the next key lit as a hint;
  //  - Check: tap the right key on screen or play it; a wrong answer goes back to Show;
  //  - Watch: a parent-approved video, if one has been added.
  // Going through it makes the skill Current (arch §8.1); in parent mode nothing is recorded, and
  // the parent can skip the Try and Check cards to review the rest.
  import { onMount, tick, untrack } from "svelte";
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent } from "../lib/content";
  import { KeyboardView, keyboardRange, noteName } from "../lib/keyboard";
  import type { MidiNote, MidiPedal } from "../lib/midi";
  import { go } from "../lib/route";
  import { renderMini, type MiniNote } from "../lib/staff";
  import type { Hand, Skill } from "../lib/types";

  let { skillId }: { skillId: string } = $props();

  interface Card {
    kind: "explain" | "show" | "hear" | "try" | "check" | "watch";
    text: string;
    notes?: MiniNote[];
    fingers?: number[] | null;
    hand?: "R" | "L" | "RL";
    clef?: "treble" | "bass" | "grand";
    play?: MiniNote[];
    tempo?: number;
    contrast?: { text: string; play: MiniNote[] };
    questions?: { text: string; answer: MiniNote }[];
    video?: string;
  }
  interface Lesson { skill: string; title: string; cards: Card[] }

  const NAMES: Record<Card["kind"], [string, string]> = {
    explain: ["Explain", "💬"], show: ["Show", "👀"], hear: ["Hear", "👂"], try: ["Try", "🎹"], check: ["Check", "✅"], watch: ["Watch", "🎬"],
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

  // fixed when the screen opens, like the Play screen's session item
  const itemId = untrack(() => app.session?.items.find((i) => !i.done && i.kind === "lesson" && i.skillId === skillId)?.id ?? null);
  const inSession = itemId !== null;
  const opened = performance.now();

  onMount(() => {
    const off = app.midi.onEvent(onMidi);
    (window as unknown as { __lesson: unknown }).__lesson = { get card() { return card; }, get progress() { return progress; },
                                                             get step() { return step; }, get done() { return done[step]; } };
    void (async () => {
      try { skill = (await loadContent()).map.skills.find((s) => s.id === skillId) ?? null; } catch { /* title only */ }
      try {
        const r = await fetch(`content/lessons/${encodeURIComponent(skillId)}.json`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        lesson = await r.json();
        done = lesson!.cards.map((c) => c.kind !== "try" && c.kind !== "check");
        await enter();
      } catch (e) {
        error = `This lesson isn't ready yet (${(e as Error).message}).`;
      }
    })();
    return () => {
      off(); clearTimers(); kb?.destroy();
      delete (window as unknown as { __lesson?: unknown }).__lesson;
      try { speechSynthesis.cancel(); } catch { /* none */ }
    };
  });

  const card = $derived(lesson?.cards[step] ?? null);
  const last = $derived(!!lesson && step === lesson.cards.length - 1);
  const canNext = $derived(!!card && (done[step] || app.parentMode));

  function clearTimers(): void {
    timers.forEach((t) => clearTimeout(t));
    timers = [];
  }

  /** Set up the card on screen: its staff, its keyboard, and what it does straight away. */
  async function enter(): Promise<void> {
    clearTimers();
    feedback = "";
    progress = 0;
    kb?.destroy();
    kb = null;
    await tick();
    const c = card;
    if (!c) return;
    if (c.text) speak(c.text);
    const all = [...(c.notes ?? []), ...(c.play ?? []), ...(c.questions ?? []).map((q) => q.answer), ...(c.contrast?.play ?? [])];
    if (kbHost && all.length) {
      const ps = all.flatMap((n) => n.pitches);
      const [lo, hi] = keyboardRange(Math.min(...ps), Math.max(...ps));
      kb = new KeyboardView(kbHost, lo, hi);
      if (c.kind === "check") kb.onTap((p) => answer(p));
    }
    if (staffHost && c.notes) heads = renderMini(staffHost, c.notes, c.clef ?? "treble");
    if (c.kind === "show") showMe();
    if (c.kind === "try") hint();
  }

  const handOf = (c: Card, i: number): Hand => (c.hand === "RL" ? (Math.min(...c.notes![i].pitches) < 60 ? "L" : "R") : (c.hand ?? "R") as Hand);

  function light(i: number | null): void {
    const c = card!;
    heads.flat().forEach((h) => h.classList.remove("pm-glow"));
    if (i === null) { kb?.setTargets([]); return; }
    heads[i]?.forEach((h) => h.classList.add("pm-glow"));
    kb?.setTargets(c.notes![i].pitches.map((p) => ({ pitch: p, hand: handOf(c, i), finger: c.fingers?.[i] })));
  }

  /** Show: each key in turn, with its finger number and its note on the staff. */
  function showMe(): void {
    clearTimers();
    const c = card!;
    const gap = 700;
    c.notes!.forEach((_, i) => timers.push(window.setTimeout(() => light(i), 400 + i * gap)));
    timers.push(window.setTimeout(() => light(null), 400 + c.notes!.length * gap + 600));
  }

  /** Hear: the notes on the app's tone, at the card's tempo. */
  async function hear(notes: MiniNote[], tempo = 90): Promise<void> {
    const ctx = await app.audio.ensure();
    const spb = 60 / tempo;
    let t = ctx.currentTime + 0.1;
    for (const n of notes) {
      for (const p of n.pitches) app.audio.tone(p, t, n.beats * spb * 0.95);
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
        feedback = progress < c.notes!.length ? "Yes!" : "You did it! 🎉";
        if (progress >= c.notes!.length) { done[step] = true; speak("You did it!"); }
        hint();
      }
    } else {
      kb?.press(pitch, "wrong");
      const flats = want.some((p) => [1, 3, 6, 8, 10].includes(p % 12)) && c.notes![progress].spelled.some((x) => x.alter < 0);
      feedback = `Not quite: find the lit key, ${want.map((p) => noteName(p, flats)).join(" + ")}.`;
    }
  }

  /** Check: the answer is a tapped or played key (a chord needs all its keys). */
  function answer(pitch: number): void {
    const c = card!;
    if (done[step] || !c.questions) return;
    const q = c.questions[progress];
    if (q.answer.pitches.includes(pitch)) {
      kb?.press(pitch, "ok");
      if (q.answer.pitches.length > 1 && !q.answer.pitches.every((p) => held.has(p) || p === pitch)) return;
      progress++;
      if (progress >= c.questions.length) { done[step] = true; feedback = "All right! 🎉"; speak("All right!"); }
      else { feedback = "Yes!"; timers.push(window.setTimeout(() => { kb?.release(pitch); speak(c.questions![progress].text); }, 600)); }
    } else {
      kb?.press(pitch, "wrong");
      feedback = "Let's look at it again.";
      speak("Let's look at it again.");
      const show = lesson!.cards.findIndex((x) => x.kind === "show");
      if (show >= 0) timers.push(window.setTimeout(() => { step = show; void enter(); }, 1200));
    }
  }

  function speak(text: string): void {
    try {
      speechSynthesis.cancel();
      speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    } catch { /* no speech on this device */ }
  }

  function move(by: number): void {
    const next = step + by;
    if (next < 0) { leave(); return; }
    step = next;
    void enter();
  }

  function finish(): void {
    app.lessonDone(skillId, itemId, (performance.now() - opened) / 1000);
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
          <div class="head"><span class="icon">{NAMES[card.kind][1]}</span><h1>{NAMES[card.kind][0]}</h1></div>
          {#if card.text}<p class="text">{card.text}</p>{/if}
          {#if card.kind === "check" && card.questions && !done[step]}
            <p class="text question">{card.questions[progress].text}</p>
          {/if}
          {#if card.notes}<div class="mini" bind:this={staffHost}></div>{/if}
          {#if card.kind === "watch" && card.video}
            <!-- svelte-ignore a11y_media_has_caption -->
            <video src={card.video} controls controlslist="nodownload noplaybackrate" disablepictureinpicture></video>
          {/if}
          {#if feedback}<p class="feedback" class:good={feedback.startsWith("Yes") || feedback.includes("🎉")}>{feedback}</p>{/if}
          <div class="actions">
            <button class="quiet" onclick={() => speak(card.kind === "check" && card.questions && !done[step] ? card.questions[progress].text : card.text)}>🔊 Read it to me</button>
            {#if card.kind === "show"}<button class="quiet" onclick={showMe}>👀 Show me again</button>{/if}
            {#if card.kind === "hear"}
              <button onclick={() => hear(card.play ?? [], card.tempo)}>▶ Play it</button>
              {#if card.contrast}<button class="quiet" onclick={() => { feedback = card.contrast!.text; speak(card.contrast!.text); void hear(card.contrast!.play, card.tempo); }}>▶ Now listen to this</button>{/if}
            {/if}
            {#if card.kind === "try" && app.midiStatus !== "connected"}<span class="muted">Connect the piano to try it.</span>{/if}
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
  .icon { font-size: 40px; }
  .text { font-size: 21px; line-height: 1.45; margin: 10px 0; }
  .question { font-weight: 700; }
  .mini { display: flex; justify-content: center; margin: 4px 0; }
  .feedback { font-size: 20px; font-weight: 700; color: #8a5a00; margin: 6px 0; }
  .feedback.good { color: var(--ok); }
  .actions { display: flex; gap: 10px; justify-content: center; align-items: center; flex-wrap: wrap; margin-top: 8px; }
  video { max-width: 100%; max-height: 320px; border-radius: 12px; }
  .keys { position: relative; height: 170px; background: #2a2a2e; margin-top: 12px; border-radius: 10px; }
  .row { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; gap: 12px; }
  .next { min-width: 180px; min-height: 60px; font-size: 20px; }
  .next:disabled { opacity: 0.45; }
</style>
