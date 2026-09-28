<script lang="ts">
  // Concept lesson (arch §3 screen 4, "Teaching concepts"): a short sequence of cards the student
  // taps through. PLACEHOLDER: each card says what it will do; the lessons are authored in M3.
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent } from "../lib/content";
  import { go } from "../lib/route";
  import type { Skill } from "../lib/types";

  let { skillId }: { skillId: string } = $props();

  let skill = $state<Skill | null>(null);
  let step = $state(0);

  onMount(async () => {
    try { skill = (await loadContent()).map.skills.find((s) => s.id === skillId) ?? null; } catch { /* title only */ }
  });

  const cards = $derived([
    { name: "Explain", icon: "💬", text: skill?.description ?? "1 to 3 short sentences in kid-friendly words, read aloud by the device's voice.", speak: true },
    { name: "Show", icon: "👀", text: "An animated keyboard and staff: the keys light up and the notes appear on the staff.", speak: false },
    { name: "Hear", icon: "👂", text: "The app plays the example, then a contrast: \"Here is a wrong note, hear the difference?\"", speak: false },
    { name: "Try", icon: "🎹", text: "Play it on the piano. The app listens and gives hints until it's right.", speak: false },
    { name: "Check", icon: "✅", text: "One or two quick questions: tap the right keys on screen or on the piano.", speak: false },
    { name: "Watch", icon: "🎬", text: "A parent-approved video on this idea, if one has been added (optional).", speak: false },
  ]);
  const card = $derived(cards[step]);
  const inSession = $derived(app.sessionItem?.kind === "lesson" && app.sessionItem.skillId === skillId);

  function speak(text: string): void {
    try {
      speechSynthesis.cancel();
      speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    } catch { /* no speech on this device */ }
  }
  function done(): void {
    if (inSession) {
      app.itemResult({ accuracyStars: null, timingStars: null });
      app.nextItem();
    } else leave();
  }
  function leave(): void {
    if (inSession) go("session"); else if (history.length > 1) history.back(); else go("journey");
  }
</script>

<div class="screen">
  <Status title={skill ? `💡 ${skill.name}` : "💡 Concept lesson"}>
    <span class="muted">Card {step + 1} of {cards.length}</span>
    <span class="sample">placeholder lesson</span>
  </Status>
  <main class="body center">
    <div class="lesson">
      <div class="steps">
        {#each cards as c, i (c.name)}
          <span class="dot" class:on={i === step} class:past={i < step}>{c.name}</span>
        {/each}
      </div>
      <div class="card-big">
        <span class="icon">{card.icon}</span>
        <h1>{card.name}</h1>
        <p class="text">{card.text}</p>
        {#if card.speak}<button class="quiet" onclick={() => speak(card.text)}>🔊 Read it to me</button>{/if}
      </div>
      <div class="row">
        <button class="quiet" onclick={() => (step > 0 ? step-- : leave())}>‹ Back</button>
        {#if step < cards.length - 1}
          <button class="next" onclick={() => step++}>Next ›</button>
        {:else}
          <button class="next" onclick={done}>{inSession ? "Next ›" : "Done"}</button>
        {/if}
      </div>
    </div>
  </main>
</div>

<style>
  .center { display: flex; justify-content: center; }
  .lesson { width: min(760px, 100%); }
  .steps { display: flex; gap: 8px; justify-content: center; margin-bottom: 14px; flex-wrap: wrap; }
  .dot { padding: 4px 12px; border-radius: 999px; background: #ecebe6; color: var(--muted); font-weight: 650; font-size: 14px; }
  .dot.past { background: #d7ecdf; color: var(--ok); }
  .dot.on { background: var(--accent); color: #fff; }
  .card-big {
    background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 26px 30px;
    text-align: center; min-height: 260px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  }
  .icon { font-size: 56px; }
  h1 { margin: 6px 0 10px !important; }
  .text { font-size: 21px; line-height: 1.45; margin: 0 0 18px; }
  .row { display: flex; justify-content: space-between; margin-top: 16px; }
  .next { min-width: 180px; min-height: 60px; font-size: 20px; }
</style>
