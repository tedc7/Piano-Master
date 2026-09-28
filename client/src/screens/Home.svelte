<script lang="ts">
  // M1 start screen: the pieces, grouped by the (placeholder) skill map. The student picker,
  // Home with Guided / Free Play and the Journey map come in M4 and M5.
  import { onMount } from "svelte";
  import { app, pianoLabel } from "../lib/app.svelte.js";
  import type { PieceSummary, Skill, SkillMap } from "../lib/types";

  let map = $state<SkillMap | null>(null);
  let pieces = $state<PieceSummary[]>([]);
  let error = $state("");

  onMount(async () => {
    try {
      const [m, idx] = await Promise.all([
        fetch("content/skillmap.json").then((r) => r.json()),
        fetch("content/index.json").then((r) => r.json()),
      ]);
      map = m;
      pieces = idx.pieces;
    } catch (e) {
      error = `Can't load the songs from the piano server (${(e as Error).message}).`;
    }
  });

  const byId = $derived(new Map(pieces.map((p) => [p.id, p])));
  const skillName = $derived(new Map((map?.skills ?? []).map((s) => [s.id, s.name])));
  const unassigned = $derived(pieces.filter((p) => !p.skillId));
  const hands = (h: string) => (h === "RL" ? "Both hands" : h === "L" ? "Left hand" : "Right hand");
  const piecesOf = (s: Skill) => (s.pieces ?? []).map((id) => byId.get(id)).filter((p): p is PieceSummary => !!p);
  const open = (id: string) => { location.hash = `#/play/${id}`; };
</script>

<div class="home">
  <header class="status">
    <span class="title">Piano Master</span>
    <span class="muted">M1 test build</span>
    <span class="spacer"></span>
    <span><span class="piano-dot" class:on={app.midiStatus === "connected"}></span>{pianoLabel(app.midiStatus, app.pianoName)}</span>
  </header>

  <main>
    {#if app.needsFullScreen}
      <p class="notice">Turn on full screen in MIDIWeb Browser to hide the address bar.</p>
    {/if}
    {#if error}
      <p class="notice error">{error}</p>
    {/if}
    {#if map}
      {#if map.placeholder}
        <p class="note">Placeholder skill map ({map.maps.map((m) => m.level).join(", ")}), for testing until the Faber books arrive.</p>
      {/if}
      {#each map.skills as s (s.id)}
        <section class="skill">
          <div class="skill-head">
            <h2>{s.name}</h2>
            <span class="track">{s.track}</span>
          </div>
          <p class="needs">
            {#if s.prerequisites.length}Needs: {s.prerequisites.map((p) => skillName.get(p) ?? p).join(" + ")}{:else}First skill{/if}
          </p>
          <div class="cards">
            {#each piecesOf(s) as p (p.id)}
              <button class="card" onclick={() => open(p.id)}>
                <span class="card-title">{p.title}</span>
                <span class="card-meta">{hands(p.hands)} · {p.timeSig} · {p.tempo} bpm{p.hasMedia ? " · with singing" : ""}</span>
              </button>
            {/each}
          </div>
        </section>
      {/each}
      {#if unassigned.length}
        <section class="skill">
          <h2>Other songs</h2>
          <div class="cards">
            {#each unassigned as p (p.id)}
              <button class="card" onclick={() => open(p.id)}>
                <span class="card-title">{p.title}</span>
                <span class="card-meta">{hands(p.hands)} · {p.timeSig}</span>
              </button>
            {/each}
          </div>
        </section>
      {/if}
    {/if}
  </main>
</div>

<style>
  .home { display: flex; flex-direction: column; height: 100%; }
  main {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    touch-action: pan-y;
    /* keep the first tappable card clear of the full-screen dead zone */
    padding: calc(var(--deadzone) - var(--status-h)) 24px 40px;
  }
  .note { color: var(--muted); margin: 0 0 12px; }
  .notice { background: #fff4d6; border: 1px solid #efd58a; border-radius: 12px; padding: 12px 16px; margin: 0 0 16px; }
  .notice.error { background: #fde8e6; border-color: #f0b3ac; }
  .skill { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 14px 18px 18px; margin-bottom: 14px; }
  .skill-head { display: flex; align-items: baseline; gap: 12px; }
  h2 { font-size: 20px; margin: 0; }
  .track { font-size: 14px; color: var(--muted); text-transform: capitalize; }
  .needs { margin: 4px 0 12px; color: var(--muted); font-size: 15px; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; }
  .card {
    display: flex; flex-direction: column; align-items: flex-start; gap: 4px;
    min-width: 240px; padding: 14px 18px; text-align: left;
    background: #eef3fd; color: var(--fg); border: 1px solid #cfdcf6;
  }
  .card-title { font-size: 19px; font-weight: 700; }
  .card-meta { font-size: 14px; font-weight: 500; color: var(--muted); }
</style>
