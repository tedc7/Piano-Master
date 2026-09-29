<script lang="ts">
  // Song library, for Free Play (arch §3 screen 7, §6.8, §10.1): library-ready songs can be
  // played; songs further along the map show "Coming soon" with the skills still to reach, and
  // songs that need more than the map covers yet show "Coming later". Grouped by the level of
  // their map point (song analysis), or their own level when beyond the map, with a favorites
  // heart (kept per student on the piano server). A song with several arrangements is one card,
  // placed where its easiest version opens, with a button for each version; the card opens the
  // most advanced version that is ready. Parent mode opens every song for review.
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { handsLabel, loadContent, type Content } from "../lib/content";
  import { libraryState } from "../lib/progress";
  import type { PieceSummary } from "../lib/types";

  let content = $state<Content | null>(null);
  let error = $state("");
  let filter = $state<"all" | "favorites">("all");

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the songs from the piano server (${(e as Error).message}).`; }
    void app.refresh();
  });

  const mine = $derived(new Set(app.favorites));
  const progress = $derived(app.progress);
  const rows = $derived.by(() => {
    if (!content) return [];
    const c = content;
    const atPoint = (p: PieceSummary) => c.map.skills.find((s) => s.sequence === p.mapPoint);
    const later = (p: PieceSummary) => !!p.beyondMap?.length || p.mapPoint == null;
    const level = (p: PieceSummary) => (later(p) ? p.level ?? "Later" : atPoint(p)?.level ?? p.level ?? "Other");
    // beyond the map: after everything on it, ordered by the piece's own level ("Level 2" < "Level 10")
    const seq = (p: PieceSummary) => (later(p) ? 1e6 + (Number(p.level?.match(/\d+/)?.[0]) || 99) : p.mapPoint ?? 0);
    const versions = c.pieces
      .map((p) => ({ p, level: level(p), seq: seq(p), ...libraryState(p, c.map, progress) }))
      .sort((a, b) => a.seq - b.seq || a.p.title.localeCompare(b.p.title));
    const songs = new Map<string, typeof versions>();
    for (const v of versions) {
      const key = v.p.song ?? v.p.id;
      songs.set(key, [...(songs.get(key) ?? []), v]);
    }
    return [...songs.entries()]
      .map(([song, vs]) => {
        const ready = vs.filter((v) => v.ready);
        const easiest = vs[0];
        return { song, vs, easiest, best: ready[ready.length - 1] ?? easiest, ready: ready.length > 0,
                 title: easiest.p.songTitle ?? easiest.p.title, level: easiest.level };
      })
      .filter((r) => filter === "all" || mine.has(r.song) || r.vs.some((v) => mine.has(v.p.id)));
  });
  const levels = $derived([...new Set(rows.map((r) => r.level))]);
  const openCount = $derived(rows.filter((r) => r.ready).length);
</script>

<div class="screen">
  <Status title="Songs">
    {#if content}<span class="muted">{openCount} of {rows.length} open</span>{/if}
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
          {#each rows.filter((r) => r.level === lv) as r (r.song)}
            {@const playable = r.ready || app.parentMode}
            {@const b = r.best}
            <div class="song" class:locked={!playable}>
              <button class="card" class:locked={!playable} disabled={!playable} onclick={() => app.openPiece(b.p.id, "library")}>
                <span class="card-title">{r.title}</span>
                <span class="card-meta">{b.p.version ? `${b.p.version} · ` : ""}{handsLabel(b.p.hands)} · {b.p.timeSig}{b.p.hasMedia ? " · with singing" : ""}</span>
                {#if !r.ready && r.easiest.beyond.length}
                  <span class="soon">Coming later{app.parentMode ? ` · beyond the map: ${r.easiest.beyond.join(", ")}` : ""}</span>
                {:else if !r.ready}
                  <span class="soon">Coming soon · learn {r.easiest.toReach.map((s) => s.name).join(", then ")}</span>
                {/if}
              </button>
              {#if r.vs.length > 1}
                <div class="versions">
                  {#each r.vs as v (v.p.id)}
                    <button class="quiet version" disabled={!v.ready && !app.parentMode} onclick={() => app.openPiece(v.p.id, "library")}
                            title={v.ready ? "" : v.beyond.length ? "Coming later" : "Coming soon"}>{v.p.version ?? v.p.title}{v.ready ? "" : " 🔒"}</button>
                  {/each}
                </div>
              {/if}
              <button class="heart" class:on={mine.has(r.song)} onclick={() => app.toggleFavorite(r.song)} aria-label="Favorite">♥</button>
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
  .versions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .version { font-size: 14px; padding: 4px 10px; min-height: 36px; }
  .heart {
    position: absolute; right: 8px; top: 8px; width: 48px; height: 48px; padding: 0; border-radius: 50%;
    background: transparent; color: #cfcbc0; font-size: 26px;
  }
  .heart.on { color: #e0457b; }
</style>
