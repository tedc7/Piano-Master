<script lang="ts">
  // A Guided session (arch §8.5): an "Up next" card before each item, with the reason and a big
  // Start button, so there are no surprises; then a finish card. The queue is sample data until
  // the server builds it (M5).
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent, type Content } from "../lib/content";
  import { go } from "../lib/route";

  let content = $state<Content | null>(null);

  onMount(async () => {
    if (!app.session) { go("home"); return; }
    try { content = await loadContent(); } catch { /* the card still shows the title */ }
  });

  const s = $derived(app.session);
  const item = $derived(s && s.index < s.items.length ? s.items[s.index] : null);
  const skill = $derived(item?.skillId ? content?.map.skills.find((k) => k.id === item.skillId) ?? null : null);
  const why: Record<string, string> = {
    Review: "Warm up with a song you already know.",
    New: "Something new today!",
    Practice: "Let's make this one even better.",
    "Your pick": "You choose! Pick any song you've unlocked.",
  };

  function start(): void {
    if (!item) return;
    if (item.kind === "lesson" && item.skillId) go(`lesson/${encodeURIComponent(item.skillId)}`);
    else if (item.kind === "piece" && item.pieceId) app.openPiece(item.pieceId, "session");
    else go("library");
  }

  function skip(): void {
    if (!s || !item) return;
    // skip once: the item moves to the end of the queue (§8.5)
    s.items = [...s.items.slice(0, s.index), ...s.items.slice(s.index + 1), item];
  }
</script>

<div class="screen">
  <Status title="Today's Practice">
    {#if s}<span class="muted">{Math.min(s.index + 1, s.items.length)} of {s.items.length}</span>{/if}
  </Status>
  <main class="body center">
    {#if item && s}
      <div class="upnext">
        <p class="label">Up next · {item.reason}</p>
        <h1>{item.kind === "lesson" ? `New idea: ${item.title}` : item.title}</h1>
        {#if skill && item.kind !== "lesson"}<p class="muted">Skill: {skill.name}</p>{/if}
        <p class="why">{why[item.reason]}</p>
        <button class="start" onclick={start}>{item.kind === "pick" ? "Choose a song" : "Start"}</button>
        <div class="row">
          {#if s.index < s.items.length - 1}<button class="quiet" onclick={skip}>Skip for now</button>{/if}
          <button class="quiet" onclick={() => go("home")}>Home</button>
        </div>
      </div>
    {:else if s}
      <div class="upnext">
        <p class="big">🎉</p>
        <h1>All done for today!</h1>
        <p class="why">You played {s.items.length} things. See you tomorrow!</p>
        <button class="start" onclick={() => { app.session = null; go("home"); }}>Home</button>
      </div>
    {/if}
  </main>
</div>

<style>
  .center { display: flex; align-items: flex-start; justify-content: center; }
  .upnext {
    width: min(640px, 100%); text-align: center; background: var(--panel); border: 1px solid var(--line);
    border-radius: 24px; padding: 26px 30px 24px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  }
  .label { margin: 0 0 6px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.04em; font-size: 15px; }
  h1 { font-size: 32px !important; margin: 0 0 8px !important; }
  .why { font-size: 19px; margin: 10px 0 20px; }
  .start { font-size: 24px; min-width: 240px; min-height: 72px; border-radius: 18px; }
  .row { display: flex; gap: 12px; justify-content: center; margin-top: 16px; }
  .big { font-size: 64px; margin: 0; }
</style>
