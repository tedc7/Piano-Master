<script lang="ts">
  // Parent > Content preview (arch §3 "Parent mode"): every skill in sequence order with its
  // prerequisites and songs, all open. Plays from here are for review.
  import { onMount } from "svelte";
  import { app } from "../../lib/app.svelte.js";
  import { handsLabel, loadContent, type Content } from "../../lib/content";
  import { keepView } from "../../lib/keep";
  import { go } from "../../lib/route";
  import type { PieceSummary, Skill } from "../../lib/types";

  let content = $state<Content | null>(null);
  let error = $state("");
  keepView("config/content", () => document.querySelector<HTMLElement>("main.body"));   // back from a song: where it was

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the content (${(e as Error).message}).`; }
  });

  const byId = $derived(new Map((content?.pieces ?? []).map((p) => [p.id, p])));
  const skillName = $derived(new Map((content?.map.skills ?? []).map((s) => [s.id, s.name])));
  const skills = $derived(content ? [...content.map.skills].sort((a, b) => a.sequence - b.sequence) : []);
  const unassigned = $derived((content?.pieces ?? []).filter((p) => !p.skillId));
  const piecesOf = (s: Skill) => (s.pieces ?? []).map((id) => byId.get(id)).filter((p): p is PieceSummary => !!p);
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if content}
  <p class="muted">
    {content.map.placeholder ? `Placeholder skill map (${content.map.maps.map((m) => m.level).join(", ")}), for testing. ` : ""}Content version {content.version}.
  </p>
  {#each skills as s (s.id)}
    <section class="panel">
      <div class="skill-head">
        <h2>{s.sequence} · {s.name}</h2>
        <span class="muted">{s.track} · {s.staff} staff</span>
        <span class="spacer"></span>
        <button class="quiet" onclick={() => go(`lesson/${encodeURIComponent(s.id)}`)}>💡 Lesson</button>
      </div>
      <p class="needs">{#if s.prerequisites.length}Needs: {s.prerequisites.map((p) => skillName.get(p) ?? p).join(" + ")}{:else}First skill{/if}</p>
      <div class="cards">
        {#each piecesOf(s) as p (p.id)}
          <button class="card" onclick={() => app.openPiece(p.id, "config/content")}>
            <span class="card-title">{p.title}</span>
            <span class="card-meta">{handsLabel(p.hands)} · {p.timeSig} · {p.tempo} bpm · {p.measures} bars{p.hasMedia ? " · with singing" : ""}</span>
          </button>
        {/each}
      </div>
    </section>
  {/each}
  {#if unassigned.length}
    <section class="panel">
      <h2>Other songs</h2>
      <div class="cards">
        {#each unassigned as p (p.id)}
          <button class="card" onclick={() => app.openPiece(p.id, "config/content")}>
            <span class="card-title">{p.title}</span>
            <span class="card-meta">{handsLabel(p.hands)} · {p.timeSig}</span>
          </button>
        {/each}
      </div>
    </section>
  {/if}
{/if}

<style>
  .skill-head { display: flex; align-items: center; gap: 12px; }
  .spacer { flex: 1; }
  .needs { margin: 4px 0 12px; color: var(--muted); font-size: 15px; }
</style>
