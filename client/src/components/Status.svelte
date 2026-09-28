<script lang="ts">
  // The status strip at the top of every screen (arch §3 layout rule): things to read only.
  // Taps near the top are lost in MIDIWeb Browser's full screen, so nothing here is a button, and
  // the left end stays empty because the browser's full-screen button floats over it.
  import type { Snippet } from "svelte";
  import { app, pianoLabel } from "../lib/app.svelte.js";

  let { title, children }: { title: string; children?: Snippet } = $props();
</script>

<header class="status">
  <span class="title">{title}</span>
  {@render children?.()}
  <span class="spacer"></span>
  {#if app.parentMode}
    <span class="player parent">🔑 Parent</span>
  {:else if app.student}
    <span class="player">{app.student.avatar} {app.student.name}</span>
  {/if}
  <span class="muted"><span class="piano-dot" class:on={app.midiStatus === "connected"}></span>{pianoLabel(app.midiStatus, app.pianoName)}</span>
</header>

<style>
  .player { font-weight: 700; background: #eef3fd; border: 1px solid #cfdcf6; border-radius: 999px; padding: 2px 12px; }
  .player.parent { background: #fff1d6; color: #8a5a00; border-color: #efcf8a; }
</style>
