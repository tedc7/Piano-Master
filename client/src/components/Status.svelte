<script lang="ts">
  // The status strip at the top of every screen (arch §3 layout rule): things to read only.
  // Taps near the top are lost in MIDIWeb Browser's full screen, so nothing here is a button.
  import type { Snippet } from "svelte";
  import { app, pianoLabel } from "../lib/app.svelte.js";

  let { title, children }: { title: string; children?: Snippet } = $props();
</script>

<header class="status">
  <span class="title">{title}</span>
  {#if app.parentMode}<span class="parent-badge">Parent mode</span>{/if}
  {@render children?.()}
  <span class="spacer"></span>
  <span class="muted"><span class="piano-dot" class:on={app.midiStatus === "connected"}></span>{pianoLabel(app.midiStatus, app.pianoName)}</span>
</header>

<style>
  .parent-badge { background: #fff1d6; color: #8a5a00; border: 1px solid #efcf8a; border-radius: 999px; padding: 2px 12px; font-weight: 700; font-size: 15px; }
</style>
