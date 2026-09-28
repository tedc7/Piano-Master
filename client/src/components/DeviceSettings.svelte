<script lang="ts">
  // The per-device settings (arch §5 DeviceProfile, kept in this browser until M4): offsets,
  // auto-rewind, backing volume and which MIDI input is the piano. Used by Parent > Device
  // settings and the Play screen's test sheet.
  import { app } from "../lib/app.svelte.js";

  let { backing = true }: { backing?: boolean } = $props();

  function nudge(key: "displayOffsetMs" | "latencyOffsetMs", by: number): void {
    app.settings[key] += by;
    app.save();
  }
  function volume(by: number): void {
    app.settings.backingVolume = Math.max(0, Math.min(3, Math.round((app.settings.backingVolume + by) * 4) / 4));
    app.save();
  }
</script>

<span>Auto-rewind</span>
<span><button class="toggle" class:off={!app.settings.autoRewind} onclick={() => { app.settings.autoRewind = !app.settings.autoRewind; app.save(); }}>{app.settings.autoRewind ? "On" : "Off"}</button></span>
<span>Display offset</span>
<span><button class="quiet" onclick={() => nudge("displayOffsetMs", -10)}>−10</button> <b>{app.settings.displayOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("displayOffsetMs", 10)}>+10</button></span>
<span>Latency offset</span>
<span><button class="quiet" onclick={() => nudge("latencyOffsetMs", -10)}>−10</button> <b>{app.settings.latencyOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("latencyOffsetMs", 10)}>+10</button></span>
{#if backing}
  <span>Backing volume</span>
  <span><button class="quiet" onclick={() => volume(-0.25)}>−</button> <b>{Math.round(app.settings.backingVolume * 100)}%</b> <button class="quiet" onclick={() => volume(0.25)}>+</button></span>
{/if}
<span>Piano input</span>
<span class="wrap">
  <button class="quiet" class:sel={!app.settings.pianoName} onclick={() => app.choosePiano(null)}>Automatic</button>
  {#each app.midiNames as n}
    <button class="quiet" class:sel={app.settings.pianoName === n} onclick={() => app.choosePiano(n)}>{n}</button>
  {/each}
</span>

<style>
  .wrap { display: flex; flex-wrap: wrap; gap: 8px; }
  .sel { outline: 3px solid var(--accent); }
</style>
