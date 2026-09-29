<script lang="ts">
  // Piano check (arch §2.6 checks 1-4, §2.6.1): which piano is connected, every key heard, chords,
  // velocity, pedal, fast repeats, and the browser's MIDI delivery delay. A key can also click,
  // for the slow-motion video measurement of key-to-screen and key-to-sound delay. The results go
  // to the client log until the DeviceProfile is stored on the server (M4).
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";
  import { isVirtualPort, type MidiNote, type MidiPedal } from "../../lib/midi";
  import { KeyboardView, noteName } from "../../lib/keyboard";

  const LOW = 21, HIGH = 108;   // A0..C8, the 88 keys

  let kbHost: HTMLDivElement;
  let kb: KeyboardView | null = null;
  let heard = $state(new Set<number>());
  let held = new Set<number>();
  let maxHeld = $state(0);
  let noteOns = $state(0);
  let velocities = $state<number[]>([]);
  let pedal = $state<number | null>(null);
  let pedalSeen = $state(false);
  let delays = $state<number[]>([]);
  let fastestRepeat = $state<number | null>(null);
  let lastOn = new Map<number, number>();
  let log = $state<{ key: number; text: string }[]>([]);
  let logKey = 0;
  let clickOn = $state(false);
  let saved = $state("");

  const full = (p: number) => `${noteName(p)}${Math.floor(p / 12) - 1}`;

  onMount(() => {
    kb = new KeyboardView(kbHost, LOW, HIGH);
    const off = app.midi.onEvent(onEvent);
    return () => { off(); kb?.destroy(); };
  });

  function onEvent(ev: MidiNote | MidiPedal): void {
    let text: string;
    if (ev.type === "pedal") {
      pedal = ev.value;
      pedalSeen = true;
      text = `pedal ${ev.value}`;
    } else if (ev.type === "on") {
      noteOns++;
      held.add(ev.pitch);
      maxHeld = Math.max(maxHeld, held.size);
      if (!heard.has(ev.pitch)) { heard = new Set(heard).add(ev.pitch); kb?.mark(ev.pitch, "kb-heard"); }
      velocities = [...velocities, ev.velocity].slice(-500);
      delays = [...delays, ev.delayMs].slice(-500);
      const prev = lastOn.get(ev.pitch);
      if (prev !== undefined) fastestRepeat = Math.min(fastestRepeat ?? Infinity, ev.timeMs - prev);
      lastOn.set(ev.pitch, ev.timeMs);
      kb?.press(ev.pitch, "neutral");
      if (clickOn && app.audio.ctx?.state === "running") app.audio.click(app.audio.ctx.currentTime, true);
      text = `on  ${full(ev.pitch).padEnd(4)} velocity ${String(ev.velocity).padStart(3)}   delay ${ev.delayMs.toFixed(1)} ms`;
    } else {
      held.delete(ev.pitch);
      kb?.release(ev.pitch);
      text = `off ${full(ev.pitch)}`;
    }
    log = [{ key: logKey++, text }, ...log].slice(0, 14);
  }

  function reset(): void {
    for (const p of heard) kb?.mark(p, "kb-heard", false);
    heard = new Set();
    held.clear();
    maxHeld = 0; noteOns = 0; velocities = []; pedal = null; pedalSeen = false; delays = [];
    fastestRepeat = null; lastOn = new Map(); log = []; saved = "";
  }

  async function toggleClick(): Promise<void> {
    if (!clickOn) await app.audio.ensure();
    clickOn = !clickOn;
  }

  const sorted = $derived([...delays].sort((a, b) => a - b));
  const pct = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  const lowest = $derived(heard.size ? Math.min(...heard) : null);
  const highest = $derived(heard.size ? Math.max(...heard) : null);
  const velMin = $derived(velocities.length ? Math.min(...velocities) : null);
  const velMax = $derived(velocities.length ? Math.max(...velocities) : null);
  const velocitySensitive = $derived(velMin !== null && velMax! - velMin >= 30);
  const audioLatency = $derived(app.audio.ctx
    ? `base ${(app.audio.ctx.baseLatency * 1000).toFixed(1)} ms, output ${((app.audio.ctx.outputLatency ?? 0) * 1000).toFixed(1)} ms`
    : "starts with the first sound");

  const summary = $derived({
    input: app.pianoName,
    inputs: app.midiNames,
    keysHeard: heard.size,
    lowest: lowest !== null ? full(lowest) : null,
    highest: highest !== null ? full(highest) : null,
    maxHeld,
    noteOns,
    velocity: velMin !== null ? [velMin, velMax] : null,
    velocitySensitive,
    pedalSeen,
    fastestRepeatMs: fastestRepeat !== null ? Math.round(fastestRepeat) : null,
    delayMs: sorted.length ? { median: +pct(0.5).toFixed(1), p95: +pct(0.95).toFixed(1), worst: +sorted[sorted.length - 1].toFixed(1), notes: sorted.length } : null,
    audioLatency,
  });

  function save(): void {
    api.log("info", "piano check", summary);
    saved = `Saved to the piano server's log at ${new Date().toLocaleTimeString()}.`;
  }
</script>

<div class="midi">
  <div class="checks">
    <section class="panel">
      <h2>1 · Connect</h2>
      <p class:ok={app.midiStatus === "connected"}>{app.midiStatus === "connected" ? `✓ Using ${app.pianoName}` : app.midiStatus === "starting" ? "Looking for the piano…" : "No piano found. Plug it in with the USB cable."}</p>
      <div class="inputs">
        <button class="quiet" class:sel={!app.device.pianoName} onclick={() => app.choosePiano(null)}>Automatic</button>
        {#each app.midiNames as n}
          <button class="quiet" class:sel={app.device.pianoName === n} onclick={() => app.choosePiano(n)}>{n}{isVirtualPort(n) ? " (virtual)" : ""}</button>
        {/each}
      </div>
    </section>
    <section class="panel">
      <h2>2 · Keys and chords</h2>
      <p>Play every key from lowest to highest, then 3- and 4-note chords.</p>
      <p><b>{heard.size}</b> of 88 keys heard{lowest !== null ? ` · ${full(lowest)} to ${full(highest!)}` : ""}</p>
      <p class:ok={maxHeld >= 4}>Most keys at once: <b>{maxHeld}</b>{maxHeld >= 4 ? " ✓" : ""}</p>
    </section>
    <section class="panel">
      <h2>3 · Touch, pedal, repeats</h2>
      <p class:ok={velocitySensitive}>Velocity: {velMin === null ? "play soft and loud" : `${velMin}–${velMax}${velocitySensitive ? " ✓ responds to touch" : " (play softer and louder)"}`}</p>
      <p class:ok={pedalSeen}>Pedal: {pedalSeen ? `✓ ${pedal! >= 64 ? "down" : "up"} (${pedal})` : "press the sustain pedal"}</p>
      <p>Notes played: <b>{noteOns}</b>{fastestRepeat !== null ? ` · fastest repeat ${Math.round(fastestRepeat)} ms` : ""}</p>
      <p class="muted small">Tap one key 10 times fast; the count should go up by 10.</p>
    </section>
    <section class="panel">
      <h2>4 · Delay</h2>
      <p>MIDI delivery: {sorted.length ? `median ${pct(0.5).toFixed(1)} ms, 95% ${pct(0.95).toFixed(1)} ms, worst ${sorted[sorted.length - 1].toFixed(1)} ms` : "play some notes"}</p>
      <p class="muted small">Audio: {audioLatency}</p>
      <button class="toggle" class:off={!clickOn} onclick={toggleClick}>Click on each key: {clickOn ? "on" : "off"}</button>
      <p class="muted small">For the slow-motion video: film the keys and the screen and count frames from key-down to the key lighting up, and to the click.</p>
    </section>
  </div>

  <div class="keys" bind:this={kbHost}></div>

  <div class="bottom">
    <section class="panel log">
      <h2>Last events</h2>
      <div class="mono">{#each log as l (l.key)}<div>{l.text}</div>{:else}<span class="muted">Press a key.</span>{/each}</div>
    </section>
    <div class="actions">
      <button onclick={save} disabled={!noteOns}>Save results</button>
      <button class="quiet" onclick={reset}>Start again</button>
      {#if saved}<p class="muted small">{saved}</p>{/if}
    </div>
  </div>
</div>

<style>
  .checks { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }
  .checks .panel { margin: 0; }
  .checks p { margin: 8px 0; }
  .ok { color: var(--ok); font-weight: 650; }
  .small { font-size: 14px; }
  .inputs { display: flex; flex-wrap: wrap; gap: 8px; }
  .sel { outline: 3px solid var(--accent); }
  .keys { position: relative; height: 150px; background: #2a2a2e; margin: 14px 0; }
  .bottom { display: flex; gap: 14px; align-items: flex-start; }
  .log { flex: 1; margin: 0; }
  .mono { font: 14px/1.45 ui-monospace, Menlo, monospace; white-space: pre; min-height: 120px; }
  .actions { display: flex; flex-direction: column; gap: 10px; width: 200px; }
</style>
