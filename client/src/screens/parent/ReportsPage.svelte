<script lang="ts">
  // Parent > Progress reports (arch §8.11): each child's full report, with stuck skills and the
  // content runway. Error patterns and suggested remedies come with Diagnostics (M6).
  import { onMount } from "svelte";
  import ProgressReport from "../../components/ProgressReport.svelte";
  import { app } from "../../lib/app.svelte.js";

  let chosen = $state<string | null>(null);

  onMount(async () => {
    await app.loadStudents();
    chosen = app.students[0]?.id ?? null;
  });
</script>

<div class="bar">
  {#each app.students as s (s.id)}
    <button class="quiet" class:sel={chosen === s.id} onclick={() => { chosen = s.id; }}>{s.avatar} {s.name}</button>
  {:else}
    <p class="muted">No students yet: add them under Students.</p>
  {/each}
</div>
{#if chosen}
  {#key chosen}<ProgressReport studentId={chosen} full />{/key}
{/if}

<style>
  .bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
  .sel { outline: 3px solid var(--accent); background: #eef3fd; }
</style>
