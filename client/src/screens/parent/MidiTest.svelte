<script lang="ts">
  // Piano check (arch §2.6 checks 1-4, §2.6.1): which piano is connected, every key heard, chords,
  // velocity, pedal, fast repeats, and the browser's MIDI delivery delay. A key can also click,
  // for the slow-motion video measurement of key-to-screen and key-to-sound delay. Save results
  // writes the full results to the client log and the detected pedal and touch sensitivity to this
  // device's DeviceProfile, which the lesson engine uses to hold pedal skills (§2.4).
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { app, pianoLabel } from "../../lib/app.svelte.js";
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
    const off = app.input.onEvent(onEvent);
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

  // ---- a recording for tuning the microphone input (v0.38): what the microphone hears, with the
  // keys heard, sent to the piano server's client log in 5-second parts (tools/mic_recording.py)
  const RECORD_S = 60;
  let recState = $state<"" | "recording" | "sending" | "sent" | "failed">("");
  let recProgress = $state(0);
  let recNote = $state("");

  async function recordAndSend(): Promise<void> {
    recState = "recording";
    recNote = "";
    const rec = await app.mic.record(RECORD_S, (f) => { recProgress = f; });
    if (!rec) { recState = "failed"; recNote = "The microphone isn't on."; return; }
    recState = "sending";
    // 16-bit, at half the rate (24 kHz from 48 kHz): plenty for a piano's keys
    const half = rec.rate >= 44100;
    const rate = half ? rec.rate / 2 : rec.rate;
    const n = half ? Math.floor(rec.samples.length / 2) : rec.samples.length;
    const pcm = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const x = half ? (rec.samples[2 * i] + rec.samples[2 * i + 1]) / 2 : rec.samples[i];
      pcm[i] = Math.max(-32768, Math.min(32767, Math.round(x * 32767)));
    }
    const id = crypto.randomUUID?.() ?? String(Date.now());
    const per = rate * 5, parts = Math.ceil(n / per);
    for (let k = 0; k < parts; k++) {
      const bytes = new Uint8Array(pcm.buffer, k * per * 2, Math.min(per, n - k * per) * 2);
      let bin = "";
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      const ok = await api.logNow("mic recording", { id, part: k, parts, rate, pcm16: btoa(bin),
        ...(k === 0 && { keys: rec.keys, settings: rec.settings }) });
      if (!ok) { recState = "failed"; recNote = `Sending part ${k + 1} of ${parts} failed: try again.`; return; }
      recProgress = (k + 1) / parts;
    }
    recState = "sent";
    recNote = `Sent (recording ${id.slice(0, 8)}, ${rec.keys.filter((e) => e.type === "on").length} keys heard).`;
  }

  function save(): void {
    api.log("info", "piano check", { ...summary, input: app.device.inputMode, ...(app.micMode && { mic: app.mic.applied }) });
    const found: { hasPedal?: boolean; velocitySensitive?: boolean } = {};
    if (pedalSeen) found.hasPedal = true;
    // the microphone's velocity is only loudness, not the keyboard's touch
    if (velocities.length >= 20 && !app.micMode) found.velocitySensitive = velocitySensitive;
    if (Object.keys(found).length) app.setDevice(found);
    saved = `Saved at ${new Date().toLocaleTimeString()}: results in the piano server's log` +
      (Object.keys(found).length ? "; pedal and touch in Device settings." : ".");
  }
</script>

<div class="midi">
  <div class="checks">
    <section class="panel">
      <h2>1 · Connect</h2>
      {#if app.micMode}
      <p class:ok={app.inputStatus === "connected"}>{app.inputStatus === "connected" ? "✓ Listening with the microphone (Config › Device settings). The pedal can't be heard, and velocity is only a guess from loudness." : pianoLabel(app.inputStatus, null, true)}</p>
      {:else}
      <p class:ok={app.inputStatus === "connected"}>{app.inputStatus === "connected" ? `✓ Using ${app.pianoName}` : app.inputStatus === "starting" ? "Looking for the piano…" : "No piano found. Plug it in with the USB cable."}</p>
      {/if}
      <div class="inputs" class:hidden={app.micMode}>
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

  {#if app.micMode}
    <section class="panel record">
      <h2>Send a recording for tuning</h2>
      <p>Records {RECORD_S} seconds of what the microphone hears, with the keys the app heard, and sends it to the piano server so the microphone's note detection can be tuned to this keyboard. Press <b>Record</b>, then play each key once, slowly, from the lowest to the highest (about one key every half second), then a few chords.</p>
      <div class="rec-row">
        <button onclick={recordAndSend} disabled={recState === "recording" || recState === "sending" || app.inputStatus !== "connected"}>
          {recState === "recording" ? `Recording… ${Math.ceil(RECORD_S * (1 - recProgress))} s` : recState === "sending" ? `Sending… ${Math.round(recProgress * 100)}%` : "Record and send"}</button>
        {#if recNote}<span class:ok={recState === "sent"} class="muted">{recNote}</span>{/if}
      </div>
    </section>
  {/if}

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
  .hidden { display: none; }
  .record { margin: 12px 0 0; }
  .rec-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
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
