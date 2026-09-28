<script lang="ts">
  // Song library, for Free Play (arch §3 screen 7, §6.8, §10.1): library-ready songs can be
  // played; songs further along the map show "Coming soon" with the skills still to reach. Grouped
  // by level, with a favorites heart. Progress is sample data until M5; parent mode opens every
  // song for review.
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { handsLabel, loadContent, type Content } from "../lib/content";
  import { libraryState, sampleProgress } from "../lib/progress";
  import type { PieceSummary } from "../lib/types";

  const FAV_KEY = "pm.favorites.v1";   // per student, on this device until M10 stores favorites

  let content = $state<Content | null>(null);
  let error = $state("");
  let filter = $state<"all" | "favorites">("all");
  let favs = $state<Record<string, string[]>>(readFavs());

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the songs from the piano server (${(e as Error).message}).`; }
  });

  function readFavs(): Record<string, string[]> {
    try { return JSON.parse(localStorage.getItem(FAV_KEY) ?? "{}"); } catch { return {}; }
  }
  const who = $derived(app.student?.id ?? "parent");
  const mine = $derived(new Set(favs[who] ?? []));
  function toggleFav(id: string): void {
    const next = mine.has(id) ? [...mine].filter((x) => x !== id) : [...mine, id];
    favs = { ...favs, [who]: next };
    try { localStorage.setItem(FAV_KEY, JSON.stringify(favs)); } catch { /* not saved */ }
  }

  const progress = $derived(content ? sampleProgress(content.map) : new Map());
  const rows = $derived.by(() => {
    if (!content) return [];
    const c = content;
    const level = (p: PieceSummary) => c.map.skills.find((s) => s.id === p.skillId)?.level ?? "Other";
    const seq = (p: PieceSummary) => c.map.skills.find((s) => s.id === p.skillId)?.sequence ?? 1e9;
    return c.pieces
      .filter((p) => filter === "all" || mine.has(p.id))
      .map((p) => ({ p, level: level(p), seq: seq(p), ...libraryState(p, c.map, progress) }))
      .sort((a, b) => a.seq - b.seq || a.p.title.localeCompare(b.p.title));
  });
  const levels = $derived([...new Set(rows.map((r) => r.level))]);
  const openCount = $derived(rows.filter((r) => r.ready).length);
</script>

<div class="screen">
  <Status title="Songs">
    {#if content}<span class="muted">{openCount} of {rows.length} open</span>{/if}
    <span class="sample">sample progress</span>
  </Status>

  <main class="body">
    {#if error}<p class="notice error">{error}</p>{/if}
    <div class="filters">
      <button class="quiet" class:sel={filter === "all"} onclick={() => { filter = "all"; }}>All songs</button>
      <button class="quiet" class:sel={filter === "favorites"} onclick={() => { filter = "favorites"; }}>♥ Favorites</button>
      {#if app.parentMode}<span class="muted">Parent mode: every song opens.</span>{/if}
    </div>
    {#each levels as lv (lv)}
      <section class="panel">
        <h2>{lv}</h2>
        <div class="cards grid">
          {#each rows.filter((r) => r.level === lv) as r (r.p.id)}
            {@const playable = r.ready || app.parentMode}
            <div class="song" class:locked={!playable}>
              <button class="card" class:locked={!playable} disabled={!playable} onclick={() => app.openPiece(r.p.id, "library")}>
                <span class="card-title">{r.p.title}</span>
                <span class="card-meta">{handsLabel(r.p.hands)} · {r.p.timeSig}{r.p.hasMedia ? " · with singing" : ""}</span>
                {#if !r.ready}
                  <span class="soon">Coming soon · learn {r.toReach.map((s) => s.name).join(", then ")}</span>
                {/if}
              </button>
              <button class="heart" class:on={mine.has(r.p.id)} onclick={() => toggleFav(r.p.id)} aria-label="Favorite">♥</button>
            </div>
          {/each}
        </div>
      </section>
    {:else}
      {#if content}<p class="muted">{filter === "favorites" ? "Tap ♥ on a song to add it to your favorites." : "No songs yet."}</p>{/if}
    {/each}
  </main>

  <TabBar current="library" />
</div>

<style>
  .filters { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
  .sel { background: var(--accent) !important; color: var(--accent-fg) !important; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); margin-top: 12px; }
  .song { position: relative; }
  .song .card { width: 100%; min-height: 96px; padding-right: 64px; }
  .card:disabled { opacity: 1; }
  .soon { font-size: 14px; font-weight: 650; color: #8a5a00; }
  .heart {
    position: absolute; right: 8px; top: 8px; width: 48px; height: 48px; padding: 0; border-radius: 50%;
    background: transparent; color: #cfcbc0; font-size: 26px;
  }
  .heart.on { color: #e0457b; }
</style>
