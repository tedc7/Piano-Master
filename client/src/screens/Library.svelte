<script lang="ts">
  // Song library, for Free Play (arch §3 screen 7, §6.8, §10.1): library-ready songs can be
  // played; songs further along the map show "Coming soon" with the skill that unlocks them (the
  // last one still to reach, v0.29: the map leads there), and
  // songs that need more than the map covers yet show "Coming later". Grouped by the level of
  // their map point (song analysis), or their own level when beyond the map, with a favorites
  // heart (kept per student on the piano server). A song with several arrangements is one card,
  // placed where its easiest version opens, with a button for each version; the card opens the
  // most advanced version that is ready. Parent mode opens every song for review. A search narrows
  // the list to songs with the text in their title or words, and a genre choice to one genre
  // (v0.35); both stay with Back from a song, as the filter does.
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { allowed, genreLabel, handsLabel, loadContent, rulesFor, searchText, type Content, type Rules } from "../lib/content";
  import { keepView } from "../lib/keep";
  import { libraryState } from "../lib/progress";
  import type { PieceSummary } from "../lib/types";

  let content = $state<Content | null>(null);
  let rules = $state<Rules | null>(null);        // the child's genre and song rules; the parent sees everything
  let error = $state("");
  let filter = $state<"all" | "favorites">("all");
  let query = $state("");                         // the search: title or words
  let genre = $state("");                         // one genre, or "" for every genre
  let bodyEl = $state<HTMLElement>();
  type View = { filter: "all" | "favorites"; query: string; genre: string };
  keepView<View>("library", () => bodyEl, { get: () => ({ filter, query, genre }),
                                            set: (v) => { ({ filter, query, genre } = v); } });

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the songs from the piano server (${(e as Error).message}).`; }
    if (app.student && !app.parentMode) rules = await rulesFor(app.student.id, true);
    void app.refresh();
  });

  const mine = $derived(new Set(app.favorites));
  const progress = $derived(app.progress);
  const allowedPieces = $derived(content ? content.pieces.filter((p) => allowed(p, rules)) : []);
  const rows = $derived.by(() => {
    if (!content) return [];
    const c = content;
    const atPoint = (p: PieceSummary) => c.map.skills.find((s) => s.sequence === p.mapPoint);
    const later = (p: PieceSummary) => !!p.beyondMap?.length || p.mapPoint == null;
    const level = (p: PieceSummary) => (later(p) ? p.level ?? "Later" : atPoint(p)?.level ?? p.level ?? "Other");
    // beyond the map: after everything on it, ordered by the piece's own level ("Level 2" < "Level 10")
    const seq = (p: PieceSummary) => (later(p) ? 1e6 + (Number(p.level?.match(/\d+/)?.[0]) || 99) : p.mapPoint ?? 0);
    const versions = allowedPieces
      .map((p) => ({ p, level: level(p), seq: seq(p), ...libraryState(p, c.map, progress) }))
      .sort((a, b) => a.seq - b.seq || a.p.title.localeCompare(b.p.title));
    const songs = new Map<string, typeof versions>();
    for (const v of versions) {
      const key = v.p.song ?? v.p.id;
      songs.set(key, [...(songs.get(key) ?? []), v]);
    }
    const q = searchText(query);
    const found = (p: PieceSummary) => [p.title, p.songTitle, p.words].some((t) => searchText(t).includes(q));
    return [...songs.entries()]
      .map(([song, vs]) => {
        const ready = vs.filter((v) => v.ready);
        const easiest = vs[0];
        return { song, vs, easiest, best: ready[ready.length - 1] ?? easiest, ready: ready.length > 0,
                 title: easiest.p.songTitle ?? easiest.p.title, level: easiest.level };
      })
      .filter((r) => filter === "all" || mine.has(r.song) || r.vs.some((v) => mine.has(v.p.id)))
      .filter((r) => !genre || r.vs.some((v) => v.p.genre === genre))
      .filter((r) => !q || r.vs.some((v) => found(v.p)));
  });
  // the genres this child can see, for the genre choice
  const genres = $derived([...new Set(allowedPieces.map((p) => p.genre ?? "").filter(Boolean))]
    .sort((a, b) => genreLabel(a).localeCompare(genreLabel(b))));
  const narrowed = $derived(!!searchText(query) || !!genre);
  const levels = $derived([...new Set(rows.map((r) => r.level))]);
  const openCount = $derived(rows.filter((r) => r.ready).length);
</script>

<div class="screen">
  <Status title="Songs">
    {#if content}<span class="muted">{openCount} of {rows.length} open</span>{/if}
  </Status>

  <main class="body" bind:this={bodyEl}>
    {#if error}<p class="notice error">{error}</p>{/if}
    <div class="filters">
      <button class="quiet" class:sel={filter === "all"} onclick={() => { filter = "all"; }}>All songs</button>
      <button class="quiet" class:sel={filter === "favorites"} onclick={() => { filter = "favorites"; }}>♥ Favorites</button>
      <input type="search" bind:value={query} placeholder="Find a song or its words" aria-label="Find a song or its words" />
      {#if genres.length > 1 || genre}
        <select bind:value={genre} aria-label="Genre">
          <option value="">Every genre</option>
          {#each genres as g (g)}<option value={g}>{genreLabel(g)}</option>{/each}
        </select>
      {/if}
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
                <span class="card-title">{r.title}{#if r.vs.some((v) => v.p.new)} <span class="new">New</span>{/if}</span>
                <span class="card-meta">{b.p.version ? `${b.p.version} · ` : ""}{handsLabel(b.p.hands)} · {b.p.timeSig}{b.p.hasMedia ? " · with singing" : ""}</span>
                {#if !r.ready && r.easiest.beyond.length}
                  <span class="soon">Coming later{app.parentMode ? ` · beyond the map: ${r.easiest.beyond.join(", ")}` : ""}</span>
                {:else if !r.ready}
                  <span class="soon">Coming soon · unlocks with {r.easiest.toReach[r.easiest.toReach.length - 1]?.name}</span>
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
      {#if content}
        <p class="muted">{narrowed ? "No songs match." : filter === "favorites" ? "Tap ♥ on a song to add it to your favorites." : "No songs yet."}</p>
        {#if narrowed}<button class="quiet" onclick={() => { query = ""; genre = ""; }}>Show every song</button>{/if}
      {/if}
    {/each}
  </main>

  <TabBar current="library" />
</div>

<style>
  .filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
  .filters input, .filters select { font: inherit; min-height: 44px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--line); background: #fff; }
  .filters input { flex: 0 1 280px; min-width: 0; }
  .sel { background: var(--accent) !important; color: var(--accent-fg) !important; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); margin-top: 12px; }
  .song { position: relative; }
  .song .card { width: 100%; min-height: 96px; padding-right: 64px; }
  .card:disabled { opacity: 1; }
  .soon { font-size: 14px; font-weight: 650; color: #8a5a00; }
  .new { font-size: 13px; font-weight: 700; color: #fff; background: #2f7d4f; border-radius: 999px; padding: 1px 8px; vertical-align: middle; }
  .versions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .version { font-size: 14px; padding: 4px 10px; min-height: 36px; }
  .heart {
    position: absolute; right: 8px; top: 8px; width: 48px; height: 48px; padding: 0; border-radius: 50%;
    background: transparent; color: #cfcbc0; font-size: 26px;
  }
  .heart.on { color: #e0457b; }
</style>
