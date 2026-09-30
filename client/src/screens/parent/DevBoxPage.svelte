<script lang="ts">
  // Config > Settings > Dev box connection (arch §10.9): the tokens that let the Claude skills on
  // the dev box talk to this piano server. With one, a skill can read the library (to avoid
  // duplicates), read the parent's "needs improvement" notes, and submit songs to the review list.
  // It can't approve anything, change the children's rules, delete songs or read their progress.
  // Made once when a dev box is set up; revoke one if that machine is replaced or lost.
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";

  interface Token { id: string; name: string; created: string; lastUsed: string | null }

  let tokens = $state<Token[]>([]);
  let name = $state("dev box");
  let made = $state("");
  let error = $state("");

  onMount(load);

  async function load(): Promise<void> {
    try { tokens = (await api.request<{ tokens: Token[] }>("/skill-tokens")).tokens; error = ""; } catch (e) {
      if (!app.parentRefused(e)) error = `Can't reach the piano server (${(e as Error).message}).`;
    }
  }

  async function make(): Promise<void> {
    try {
      made = (await api.request<{ token: string }>("/skill-tokens", "POST", { name: name.trim() || "dev box" })).token;
      await load();
    } catch (e) { if (!app.parentRefused(e)) error = (e as Error).message; }
  }

  async function revoke(t: Token): Promise<void> {
    try { await api.request(`/skill-tokens/${t.id}`, "DELETE"); await load(); } catch (e) { app.parentRefused(e); }
  }

  const when = (iso: string) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
</script>

{#if error}<p class="notice error">{error}</p>{/if}

<section class="panel">
  <h2>What this is</h2>
  <p>New songs are prepared by the Claude skills on the dev box (the computer with the graphics card), which send them to
    this piano server for your review. Each dev box needs a <b>token</b>, a password just for that job. With it, a skill can:</p>
  <ul>
    <li>see which songs are already in the library, so it doesn't bring duplicates;</li>
    <li>read the notes you write with <b>Needs improvement</b>, to fix those songs;</li>
    <li>submit songs to the Review list.</li>
  </ul>
  <p>It can't approve songs, change the children's rules, delete anything or see their progress. You only need to make a
    token once, when a dev box is set up. Revoke it if that computer is replaced or lost.</p>
</section>

<section class="panel">
  <h2>Tokens</h2>
  {#each tokens as t (t.id)}
    <div class="token">
      <span><b>{t.name}</b> · made {when(t.created)} · {t.lastUsed ? `last used ${when(t.lastUsed)}` : "not used yet"}</span>
      <button class="quiet" onclick={() => revoke(t)}>Revoke</button>
    </div>
  {:else}
    <p class="muted">None yet.</p>
  {/each}
  <div class="token">
    <input bind:value={name} maxlength="40" aria-label="Which dev box" />
    <button class="quiet" onclick={make}>Make a token</button>
  </div>
  {#if made}
    <p class="notice">Copy this into <code>~/.config/piano-master/skill-token</code> on the dev box. It won't be shown again:<br />
      <code class="tok">{made}</code></p>
  {/if}
</section>

<style>
  .token { display: flex; gap: 10px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
  .token input { font: inherit; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); }
  .tok { word-break: break-all; user-select: all; }
</style>
