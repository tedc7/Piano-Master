<script lang="ts">
  // Parent > Content and analysis (arch §6.8, §6.10): the coverage report (skills with fewer than
  // 3 core pieces featuring them) and every piece's song analysis: required and featured skills,
  // map point, and anything beyond the map. The analysis runs in every content build, so each
  // deploy is analysed against the skill map it ships with.
  import { onMount } from "svelte";
  import { loadContent, type Content } from "../../lib/content";
  import type { PieceSummary } from "../../lib/types";

  let content = $state<Content | null>(null);
  let error = $state("");
  let show = $state<"all" | "beyond">("all");

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the content (${(e as Error).message}).`; }
  });

  const skills = $derived(content ? [...content.map.skills].sort((a, b) => a.sequence - b.sequence) : []);
  const skillName = (id: string) => content?.map.skills.find((s) => s.id === id)?.name ?? id;
  const atPoint = (p: PieceSummary) => content?.map.skills.find((s) => s.sequence === p.mapPoint)?.name ?? "–";
  const featuring = (id: string, kind: string) => (content?.pieces ?? []).filter((p) => p.featuredSkills?.includes(id) && (p.kind ?? "core") === kind);
  const pieces = $derived((content?.pieces ?? [])
    .filter((p) => show === "all" || p.beyondMap?.length)
    .sort((a, b) => (a.mapPoint ?? 1e9) - (b.mapPoint ?? 1e9) || a.title.localeCompare(b.title)));
  const beyondCount = $derived((content?.pieces ?? []).filter((p) => p.beyondMap?.length).length);
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if content}
  <p class="muted">Content version {content.version}. Song analysis runs in every content build: each piece's required skills
    decide when it unlocks; the map point places it in the library; featured skills are what it practises (arch §6.8).</p>

  <section class="panel">
    <h2>Coverage</h2>
    <p class="muted small">Every skill needs at least 3 core pieces featuring it, so each Current skill always has pieces to practise (§6.8).</p>
    <table>
      <thead><tr><th>Skill</th><th>Core pieces</th><th>Library songs</th></tr></thead>
      <tbody>
        {#each skills as s (s.id)}
          {@const core = featuring(s.id, "core")}
          {@const lib = featuring(s.id, "library")}
          <tr class:short={core.length < 3}>
            <td><b>{s.sequence}</b> · {s.name}</td>
            <td>{core.length}{core.length < 3 ? " — needs 3" : ""} <span class="muted">{core.map((p) => p.title).join(", ")}</span></td>
            <td>{lib.length} <span class="muted">{lib.map((p) => p.title).join(", ")}</span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>

  <section class="panel">
    <div class="head">
      <h2>Pieces</h2>
      <span class="spacer"></span>
      <button class="quiet" class:sel={show === "all"} onclick={() => { show = "all"; }}>All ({content.pieces.length})</button>
      <button class="quiet" class:sel={show === "beyond"} onclick={() => { show = "beyond"; }}>Beyond the map ({beyondCount})</button>
    </div>
    <table>
      <thead><tr><th>Piece</th><th>Map point</th><th>Featured</th><th>Required</th></tr></thead>
      <tbody>
        {#each pieces as p (p.id)}
          <tr>
            <td><b>{p.title}</b><br /><span class="muted small">{p.kind}{p.level ? ` · ${p.level}` : ""}{p.keyboardSize === 88 ? " · 88 keys" : ""}</span></td>
            {#if p.beyondMap?.length}
              <td colspan="3" class="beyond">Beyond the map: {p.beyondMap.join(", ")}</td>
            {:else}
              <td>{atPoint(p)}</td>
              <td>{(p.featuredSkills ?? []).map(skillName).join(", ")}</td>
              <td class="muted">{(p.requiredSkills ?? []).map((id) => `${skillName(id)} (bars ${(p.skillMeasures?.[id] ?? []).length})`).join(", ")}</td>
            {/if}
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
{/if}

<style>
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 14px; color: var(--muted); padding: 4px 8px; }
  td { padding: 6px 8px; border-top: 1px solid var(--line); vertical-align: top; }
  tr.short td:first-child { color: #8a5a00; }
  .beyond { color: #8a5a00; font-weight: 650; }
  .small { font-size: 13px; }
  .head { display: flex; align-items: center; gap: 8px; }
  .spacer { flex: 1; }
  .sel { outline: 3px solid var(--accent); }
</style>
