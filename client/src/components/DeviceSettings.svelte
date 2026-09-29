<script lang="ts">
  // This device's settings (arch §5 DeviceProfile), set by the parent: the offsets, the keyboard
  // size and which MIDI input is the piano. Used by Config > Device settings and the Play
  // screen's test sheet. Rows for a two-column grid.
  import { app } from "../lib/app.svelte.js";

  function nudge(key: "displayOffsetMs" | "latencyOffsetMs", by: number): void {
    app.setDevice({ [key]: app.device[key] + by });
  }
</script>

<span>Display offset</span>
<span><button class="quiet" onclick={() => nudge("displayOffsetMs", -10)}>−10</button> <b>{app.device.displayOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("displayOffsetMs", 10)}>+10</button></span>
<span>Latency offset</span>
<span><button class="quiet" onclick={() => nudge("latencyOffsetMs", -10)}>−10</button> <b>{app.device.latencyOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("latencyOffsetMs", 10)}>+10</button>
  <span class="muted note">{app.device.latencyCheckedAt ? `calibrated, spread ${app.device.latencySpreadMs} ms` : "not calibrated: Config › Latency calibration"}</span></span>
<span>Keyboard size</span>
<span class="wrap">
  {#each [61, 88] as k (k)}
    <button class="quiet" class:sel={app.device.keyboardSize === k} onclick={() => app.setDevice({ keyboardSize: k as 61 | 88 })}>{k} keys</button>
  {/each}
</span>
<span>Sustain pedal</span>
<span class="wrap">
  {#each [[true, "Plugged in"], [false, "No pedal"]] as [v, label] (label)}
    <button class="quiet" class:sel={app.device.hasPedal === v} onclick={() => app.setDevice({ hasPedal: v as boolean })}>{label}</button>
  {/each}
  {#if app.device.hasPedal === null}<span class="muted note">not checked</span>{/if}
</span>
<span>Touch-sensitive keys</span>
<span class="wrap">
  {#each [[true, "Yes"], [false, "No"]] as [v, label] (label)}
    <button class="quiet" class:sel={app.device.velocitySensitive === v} onclick={() => app.setDevice({ velocitySensitive: v as boolean })}>{label}</button>
  {/each}
  {#if app.device.velocitySensitive === null}<span class="muted note">not checked</span>{/if}
</span>
<span>Piano input</span>
<span class="wrap">
  <button class="quiet" class:sel={!app.device.pianoName} onclick={() => app.choosePiano(null)}>Automatic</button>
  {#each app.midiNames as n}
    <button class="quiet" class:sel={app.device.pianoName === n} onclick={() => app.choosePiano(n)}>{n}</button>
  {/each}
</span>

<style>
  .wrap { display: flex; flex-wrap: wrap; gap: 8px; }
  .sel { outline: 3px solid var(--accent); }
  .note { font-size: 13px; margin-left: 6px; }
</style>
