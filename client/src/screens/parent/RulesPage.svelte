<script lang="ts">
  // Config > Songs and genres (arch §10.1): each child's genre rules (every genre starts blocked,
  // including genres and children added later), song rules that override everything for one song,
  // and deleting a song, which moves it to the Review list's Deleted songs (the library holds only
  // approved songs). The songs the Journey map uses for practice are allowed unless a song rule
  // blocks one (v0.27).
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";
  import { genreLabel as label, reloadContent } from "../../lib/content";

  interface Song { song: string; title: string; genre: string; pieces: string[]; curriculum: boolean }
  interface Kid { id: string; name: string; avatar: string; genres: Record<string, boolean>; songs: Record<string, boolean> }

  let genres = $state<string[]>([]);
  let songs = $state<Song[]>([]);
  let kids = $state<Kid[]>([]);
  let error = $state("");
  let confirm = $state<string | null>(null);          // song key about to be deleted
  let reason = $state("");
  let filter = $state("");
  let done = $state("");

  onMount(load);

  async function load(): Promise<void> {
    try {
      const r = await api.request<{ genres: string[]; songs: Song[]; students: Kid[] }>("/rules");
      genres = r.genres;
      songs = r.songs;
      kids = r.students;
      error = "";
    } catch (e) {
      if (!app.parentRefused(e)) error = `Can't reach the piano server (${(e as Error).message}).`;
    }
  }

  async function call(path: string, method: string, body?: unknown): Promise<void> {
    try {
      await api.request(path, method, body);
      await load();
    } catch (e) {
      if (!app.parentRefused(e)) error = (e as Error).message;
    }
  }

  const genreOn = (k: Kid, g: string) => k.genres[g] === true;
  const songRule = (k: Kid, s: Song) => (s.song in k.songs ? (k.songs[s.song] ? "allow" : "block") : "genre");
  function setSong(k: Kid, s: Song, v: string): void {
    void call(`/students/${k.id}/rules/songs/${encodeURIComponent(s.song)}`, "PUT", { allowed: v === "genre" ? null : v === "allow" });
  }
  async function remove(s: Song): Promise<void> {
    confirm = null;
    await call(`/library/songs/${encodeURIComponent(s.song)}/delete`, "POST", { reason: reason.trim() || null });
    reason = "";
    reloadContent();
    done = `${s.title} is out of the library. It's under Deleted songs in the Review list, where it can be sent back to review, improved or forgotten.`;
  }
  const shown = $derived(songs.filter((s) => !filter || s.title.toLowerCase().includes(filter.toLowerCase())));
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if done}<p class="notice">{done}</p>{/if}

<section class="panel">
  <h2>Genres</h2>
  <p class="muted">Every genre starts blocked for each child until you allow it, including new genres and new children.
    The songs the Journey map uses for practice are always allowed. A song rule below overrides both.</p>
  {#if kids.length}
    <table>
      <thead><tr><th>Genre</th>{#each kids as k (k.id)}<th>{k.avatar} {k.name}</th>{/each}</tr></thead>
      <tbody>
        {#each genres as g (g)}
          <tr>
            <td>{label(g)}</td>
            {#each kids as k (k.id)}
              <td><button class="toggle" class:on={genreOn(k, g)} onclick={() => call(`/students/${k.id}/rules/genres/${encodeURIComponent(g)}`, "PUT", { allowed: !genreOn(k, g) })}>
                {genreOn(k, g) ? "Allowed" : "Blocked"}</button></td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  {:else}
    <p class="muted">Add the children under Students first.</p>
  {/if}
</section>

<section class="panel">
  <div class="head">
    <h2>Songs</h2>
    <span class="spacer"></span>
    <input bind:value={filter} placeholder="Find a song" aria-label="Find a song" />
  </div>
  {#each shown as s (s.song)}
    <div class="song">
      <div class="name"><b>{s.title}</b> <span class="muted">{label(s.genre)}{s.pieces.length > 1 ? ` · ${s.pieces.length} arrangements` : ""}{s.curriculum ? " · practice song" : ""}</span></div>
      {#each kids as k (k.id)}
        <label class="rule">{k.avatar}
          <select value={songRule(k, s)} onchange={(e) => setSong(k, s, (e.currentTarget as HTMLSelectElement).value)}>
            <option value="genre">{s.curriculum ? "Practice song (allowed)" : `By genre (${genreOn(k, s.genre) ? "allowed" : "blocked"})`}</option>
            <option value="allow">Allow</option>
            <option value="block">Block</option>
          </select>
        </label>
      {/each}
      {#if confirm === s.song}
        {#if s.curriculum}<span class="warn">A practice song on the Journey map: its skill keeps only its other practice songs.</span>{/if}
        <input bind:value={reason} maxlength="200" placeholder="Why (optional)" aria-label="Reason" />
        <button class="danger" onclick={() => remove(s)}>Delete (to the Review list's Deleted songs)</button>
        <button class="quiet" onclick={() => { confirm = null; }}>Keep</button>
      {:else}
        <button class="quiet" onclick={() => { confirm = s.song; }}>Delete…</button>
      {/if}
    </div>
  {:else}
    <p class="muted">No songs in the library yet.</p>
  {/each}
</section>

<style>
  table { border-collapse: collapse; margin-top: 10px; }
  th, td { text-align: left; padding: 6px 14px 6px 0; }
  .toggle { min-width: 110px; background: #f1f0ec; color: var(--muted); }
  .toggle.on { background: #2f7d4f; color: #fff; }
  .head { display: flex; align-items: center; gap: 12px; }
  .spacer { flex: 1; }
  .head input, .song input { font: inherit; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); }
  .song { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; padding: 10px 0; border-top: 1px solid var(--line); }
  .name { flex: 1 1 260px; }
  .rule { display: flex; gap: 6px; align-items: center; }
  .rule select { font: inherit; padding: 6px 8px; border-radius: 10px; border: 1px solid var(--line); background: #fff; }
  .danger { background: var(--wrong); color: #fff; }
  .warn { flex-basis: 100%; color: #8a5a00; }
</style>
