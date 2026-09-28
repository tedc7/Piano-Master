<script lang="ts">
  // Home (arch §3 screen 2): the two ways to play, "Today's Practice" (Guided) and "Free Play",
  // today's session as cards, and the progress ring toward today's target minutes. The session,
  // streak and stars are sample data until the lesson engine (M5).
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent, type Content } from "../lib/content";
  import { sampleProgress, sampleSession, type SessionItem } from "../lib/progress";
  import { go } from "../lib/route";

  const TARGET_MIN = 15;
  const minutesToday = 0;

  let content = $state<Content | null>(null);
  let error = $state("");

  onMount(async () => {
    if (!app.student) { go(""); return; }
    try { content = await loadContent(); } catch (e) { error = `Can't load the songs from the piano server (${(e as Error).message}).`; }
  });

  const items = $derived.by((): SessionItem[] => {
    if (!content) return [];
    return app.session?.items ?? sampleSession(content.map, content.pieces, sampleProgress(content.map));
  });
  const doneCount = $derived(app.session?.index ?? 0);
  const ring = $derived(Math.min(1, minutesToday / TARGET_MIN));
  const reasonIcon: Record<string, string> = { Review: "🔁", New: "✨", Practice: "🎯", "Your pick": "🎁" };

  function start(): void {
    if (app.session && app.session.index < app.session.items.length) go("session");
    else app.startSession(items);
  }
</script>

<div class="screen">
  <Status title={app.student ? `${app.student.avatar} ${app.student.name}` : "Piano Master"}>
    <span>🔥 3 days</span>
    <span>★ 12 this week</span>
    <span class="sample">sample</span>
  </Status>

  <main class="body">
    {#if app.needsFullScreen}
      <p class="notice">Turn on full screen in MIDIWeb Browser to hide the address bar.</p>
    {/if}
    {#if error}<p class="notice error">{error}</p>{/if}

    <div class="top">
      <div class="big-buttons">
        <button class="big guided" onclick={start} disabled={!items.length}>
          <span class="big-icon">▶</span>
          <span><span class="big-title">Today's Practice</span><span class="big-sub">{app.session ? `${doneCount} of ${items.length} done` : `${items.length} things to play`}</span></span>
        </button>
        <button class="big free" onclick={() => go("library")}>
          <span class="big-icon">🎵</span>
          <span><span class="big-title">Free Play</span><span class="big-sub">Pick any song you've unlocked</span></span>
        </button>
      </div>
      <div class="ring" style:--p={ring} aria-label="{minutesToday} of {TARGET_MIN} minutes today">
        <div class="ring-inner"><b>{minutesToday}</b><span>of {TARGET_MIN} min</span></div>
      </div>
    </div>

    <h2>Today <span class="sample">sample session</span></h2>
    <div class="today">
      {#each items as it, i (i)}
        <div class="item" class:done={i < doneCount}>
          <span class="reason">{reasonIcon[it.reason]} {it.reason}</span>
          <span class="item-title">{it.kind === "lesson" ? `Lesson: ${it.title}` : it.title}</span>
          {#if i < doneCount}<span class="check">✓</span>{/if}
        </div>
      {/each}
    </div>
  </main>

  <TabBar current="home" />
</div>

<style>
  .top { display: flex; gap: 24px; align-items: center; margin-bottom: 22px; }
  .big-buttons { display: flex; gap: 18px; flex: 1; flex-wrap: wrap; }
  .big {
    flex: 1; min-width: 260px; min-height: 120px; display: flex; align-items: center; gap: 18px;
    padding: 18px 24px; border-radius: 22px; text-align: left; box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  }
  .big > span:last-child { display: flex; flex-direction: column; gap: 4px; }
  .guided { background: var(--accent); }
  .free { background: #8a4fd0; }
  .big-icon { font-size: 40px; }
  .big-title { font-size: 28px; font-weight: 800; }
  .big-sub { font-size: 16px; font-weight: 500; opacity: 0.9; }
  .ring {
    flex: 0 0 130px; height: 130px; border-radius: 50%;
    background: conic-gradient(var(--ok) calc(var(--p) * 360deg), #e4e2da 0);
    display: grid; place-items: center;
  }
  .ring-inner { width: 100px; height: 100px; border-radius: 50%; background: var(--bg); display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .ring-inner b { font-size: 30px; line-height: 1; }
  .ring-inner span { font-size: 13px; color: var(--muted); }
  h2 { margin-bottom: 10px !important; }
  .today { display: flex; gap: 12px; flex-wrap: wrap; }
  .item {
    position: relative; display: flex; flex-direction: column; gap: 6px; min-width: 200px; flex: 1;
    background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px;
  }
  .item.done { opacity: 0.55; }
  .reason { font-size: 14px; font-weight: 700; color: var(--muted); }
  .item-title { font-size: 18px; font-weight: 700; }
  .check { position: absolute; right: 14px; top: 10px; color: var(--ok); font-size: 22px; font-weight: 800; }
</style>
