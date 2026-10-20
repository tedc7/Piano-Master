<script lang="ts">
  // This device's settings (arch §5 DeviceProfile), set by the parent: the offsets, the keyboard
  // size, and how the app hears the piano: a MIDI input, or for now the microphone (v0.38), with
  // its sensitivity, the app's music while playing, and a level meter. Used by Config > Device
  // settings and the Play screen's test sheet. Rows for a two-column grid.
  import { onMount } from "svelte";
  import { app, pianoLabel } from "../lib/app.svelte.js";
  import type { InputMode } from "../lib/input";

  const MODES: [InputMode, string][] = [["midi", "MIDI Input"], ["mic", "Microphone Input (external noise sensitive)"]];
  const SENSITIVITY: [1 | 2 | 3, string][] = [[1, "Low (noisy room)"], [2, "Medium"], [3, "High (soft playing)"]];

  let levelDb = $state(-100);
  let floorDb = $state(-100);
  onMount(() => {
    let raf = 0;
    const read = () => { levelDb = app.mic.levelDb; floorDb = app.mic.floorDb; raf = requestAnimationFrame(read); };
    raf = requestAnimationFrame(read);
    return () => cancelAnimationFrame(raf);
  });
  /** -80 dB to 0 dB as 0 to 100%. */
  const pct = (db: number) => Math.max(0, Math.min(100, ((db + 80) / 80) * 100));

  function nudgeDisplay(by: number): void {
    app.setDevice({ displayOffsetMs: app.device.displayOffsetMs + by });
  }
  function nudgeLatency(by: number): void {
    app.setLatency(app.latency.offsetMs + by);
  }
</script>

<span>Listen to the piano with</span>
<span class="modes" role="radiogroup" aria-label="Piano input">
  {#each MODES as [m, label] (m)}
    <label class="mode"><input type="radio" name="piano-input" value={m} checked={app.device.inputMode === m}
      onchange={() => app.chooseInput(m)} /> {label}</label>
  {/each}
  <span class="muted note">{pianoLabel(app.inputStatus, app.pianoName, app.micMode)}</span>
</span>

{#if app.micMode}
  <span>Microphone sensitivity</span>
  <span class="wrap">
    {#each SENSITIVITY as [v, label] (v)}
      <button class="quiet" class:sel={app.device.micSensitivity === v} onclick={() => app.setMicSensitivity(v)}>{label}</button>
    {/each}
  </span>
  <span>Microphone level</span>
  <span class="meter-row">
    <span class="meter" title="the bar is what the microphone hears; the line is the room's steady noise">
      <span class="level" style:width="{pct(levelDb)}%"></span>
      <span class="floor" style:left="{pct(floorDb)}%"></span>
    </span>
    <span class="muted note">{app.micMode && app.inputStatus === "connected" ? `room ${Math.round(floorDb)} dB · now ${Math.round(levelDb)} dB` : "not listening"}</span>
  </span>
  <span>Voice processing</span>
  <span>
    <label class="mode"><input type="checkbox" checked={app.device.micVoiceProcessing}
      onchange={(e) => app.setMicVoiceProcessing(e.currentTarget.checked)} />
      The device's echo cancellation (on iPad it is tuned for speech, and may miss the lowest and highest keys)</label>
  </span>
  <span>App music while playing</span>
  <span>
    <label class="mode"><input type="checkbox" checked={app.device.micQuietMusic}
      onchange={(e) => app.setDevice({ micQuietMusic: e.currentTarget.checked })} />
      No vocals or backing in Play mode (only if keys nobody played show up while the music plays)</label>
  </span>
{/if}
<span>Display offset</span>
<span><button class="quiet" onclick={() => nudgeDisplay(-10)}>−10</button> <b>{app.device.displayOffsetMs} ms</b> <button class="quiet" onclick={() => nudgeDisplay(10)}>+10</button></span>
<span>Latency offset{app.micMode ? " (microphone)" : ""}</span>
<span><button class="quiet" onclick={() => nudgeLatency(-10)}>−10</button> <b>{app.latency.offsetMs} ms</b> <button class="quiet" onclick={() => nudgeLatency(10)}>+10</button>
  <span class="muted note">{app.latency.checkedAt ? `calibrated, spread ${app.latency.spreadMs} ms` : "not calibrated: Config › Latency calibration"}</span></span>
<span>Keyboard size</span>
<span class="wrap">
  {#each [61, 88] as k (k)}
    <button class="quiet" class:sel={app.device.keyboardSize === k} onclick={() => { app.setDevice({ keyboardSize: k as 61 | 88 }); void app.mic.restart(); }}>{k} keys</button>
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
{#if !app.micMode}
  <span>MIDI input</span>
  <span class="wrap">
    <button class="quiet" class:sel={!app.device.pianoName} onclick={() => app.choosePiano(null)}>Automatic</button>
    {#each app.midiNames as n}
      <button class="quiet" class:sel={app.device.pianoName === n} onclick={() => app.choosePiano(n)}>{n}</button>
    {/each}
  </span>
{/if}

<style>
  .wrap { display: flex; flex-wrap: wrap; gap: 8px; }
  .modes { display: flex; flex-direction: column; gap: 6px; }
  .mode { display: flex; align-items: center; gap: 8px; font-weight: 600; }
  .mode input { width: 20px; height: 20px; margin: 0; accent-color: var(--accent); }
  .meter-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
  .meter { position: relative; width: 220px; height: 14px; border-radius: 7px; background: var(--line); overflow: hidden; }
  .level { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
  .floor { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--fg); }
  .sel { outline: 3px solid var(--accent); }
  .note { font-size: 13px; margin-left: 6px; }
</style>
