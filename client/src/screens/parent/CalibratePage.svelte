<script lang="ts">
  // Latency calibration (arch §2.6.1, the tap-along offset): the app counts in 4 clicks, then
  // plays 24 more; the parent taps one key on the piano with each of the 24. Each tap is timed on
  // the same clock the Play screen scores with (the heard audio time of the MIDI event), so the
  // average of tap minus click is exactly the offset the evaluator subtracts from every note (§7).
  // The spread (standard deviation) says whether the setup is steady: under about 20 ms passes.
  // Needs the piano: there is no on-screen tapping, as it would not measure the MIDI input.
  import { onMount } from "svelte";
  import { app } from "../../lib/app.svelte.js";
  import type { MidiNote, MidiPedal } from "../../lib/midi";
  import { calibrate, type Calibration } from "../../lib/calibrate";

  const COUNT_IN = 4, CLICKS = 24, BPM = 90;
  const spb = 60 / BPM;

  let phase = $state<"ready" | "running" | "done">("ready");
  let beat = $state(-1);                   // the click being heard, for the pulse
  let taps = $state<(number | null)[]>([]);   // ms per test click, null when missed
  let result = $state<Calibration | null>(null);
  let applied = $state(false);
  let clicks: number[] = [];               // context times of the test clicks
  let timer = 0;
  let raf = 0;

  onMount(() => {
    const off = app.midi.onEvent(onEvent);
    (window as unknown as { __calib: unknown }).__calib = {
      get clicks() { return clicks; }, get state() { return phase; }, get result() { return result; },
      heardNow: () => app.audio.outputTimeAt(performance.now()),    // for the browser check's scripted taps
    };
    return () => { off(); clearTimeout(timer); cancelAnimationFrame(raf); };
  });

  async function start(): Promise<void> {
    const ctx = await app.audio.ensure();
    const t0 = ctx.currentTime + 0.3;
    clicks = [];
    for (let i = 0; i < COUNT_IN + CLICKS; i++) {
      const t = t0 + i * spb;
      app.audio.click(t, i === 0 || i === COUNT_IN, i < COUNT_IN ? 0.7 : 1);
      if (i >= COUNT_IN) clicks.push(t);
    }
    taps = clicks.map(() => null);
    result = null;
    applied = false;
    phase = "running";
    const pulse = () => {
      const heard = app.audio.outputTimeAt(performance.now());
      beat = Math.floor((heard - t0) / spb + 0.05);
      if (phase === "running") raf = requestAnimationFrame(pulse);
    };
    raf = requestAnimationFrame(pulse);
    timer = window.setTimeout(finish, ((t0 - ctx.currentTime) + (COUNT_IN + CLICKS) * spb + 0.6) * 1000);
  }

  function onEvent(ev: MidiNote | MidiPedal): void {
    if (phase !== "running" || ev.type !== "on" || !app.audio.ctx) return;
    const heard = app.audio.outputTimeAt(ev.timeMs);
    // the nearest test click, within half a beat; a second tap for the same click is ignored
    let best = -1;
    for (let i = 0; i < clicks.length; i++) {
      if (Math.abs(heard - clicks[i]) < spb / 2 && (best < 0 || Math.abs(heard - clicks[i]) < Math.abs(heard - clicks[best]))) best = i;
    }
    if (best >= 0 && taps[best] === null) {
      taps[best] = (heard - clicks[best]) * 1000;
    }
  }

  function finish(): void {
    phase = "done";
    cancelAnimationFrame(raf);
    beat = -1;
    result = calibrate(taps);
  }

  function apply(): void {
    if (!result?.ok) return;
    app.setDevice({ latencyOffsetMs: result.offsetMs, latencySpreadMs: result.spreadMs, latencyCheckedAt: new Date().toISOString() });
    applied = true;
  }

  const counting = $derived(phase === "running" && beat >= 0 && beat < COUNT_IN);
  const tapped = $derived(taps.filter((t) => t !== null).length);
</script>

<div class="calib">
  <section class="panel intro">
    <p>Sit at the piano as a child would. The app counts in <b>4 clicks</b>, then plays <b>24</b>: tap any one key
      with each of the 24, as evenly as you can. The average gap between the clicks and your taps becomes this device's
      latency offset, which the app takes off every note before it scores timing.</p>
    <p class="muted small">Now: {app.device.latencyOffsetMs} ms{app.device.latencyCheckedAt
      ? `, calibrated ${new Date(app.device.latencyCheckedAt).toLocaleDateString()} (spread ${app.device.latencySpreadMs} ms)`
      : " (the default, not calibrated yet)"}.</p>
  </section>

  {#if app.midiStatus !== "connected"}
    <p class="notice">No piano connected. Plug the piano in with the USB cable; calibration measures its keys, so it needs the piano.</p>
  {:else}
    <div class="stage panel">
      <div class="dots">
        {#each Array(COUNT_IN + CLICKS) as _, i (i)}
          <span class="dot" class:ci={i < COUNT_IN} class:now={i === beat}
                class:hit={i >= COUNT_IN && taps[i - COUNT_IN] !== null}></span>
        {/each}
      </div>
      <p class="big">
        {#if phase === "ready"}Ready when you are.
        {:else if counting}Listen… {beat + 1}
        {:else if phase === "running"}Tap with the clicks · {tapped} of {CLICKS}
        {:else if result}{result.ok ? `Offset ${result.offsetMs} ms · spread ${result.spreadMs} ms` : result.message}{/if}
      </p>
      {#if phase === "done" && result}
        <div class="strip" aria-label="Each tap, early to the left and late to the right">
          <span class="zero"></span>
          {#each taps as t, i (i)}
            {#if t !== null}<span class="tap" class:out={result.outliers.includes(i)} style="left: {50 + Math.max(-48, Math.min(48, t / 4))}%"></span>{/if}
          {/each}
        </div>
        <p class="muted small">{result.used} taps used{result.outliers.length ? `, ${result.outliers.length} left out as stray` : ""}{result.missed ? `, ${result.missed} clicks without a tap` : ""}.
          {result.ok ? (result.steady ? "✓ Steady: the spread is under 20 ms." : "The spread is over 20 ms: try again, tapping one key straight down.") : ""}</p>
      {/if}
      <div class="actions">
        <button onclick={start} disabled={phase === "running"}>{phase === "done" ? "Try again" : "Start"}</button>
        {#if phase === "done" && result?.ok}
          <button onclick={apply} disabled={applied}>{applied ? "✓ Saved to this device" : `Use ${result.offsetMs} ms`}</button>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .calib { max-width: 860px; margin: 0 auto; }
  .small { font-size: 14px; }
  .stage { text-align: center; }
  .dots { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 8px 0 14px; }
  .dot { width: 18px; height: 18px; border-radius: 50%; background: var(--line); transition: transform 60ms; }
  .dot.ci { background: #d8d4ca; }
  .dot.hit { background: var(--ok); }
  .dot.now { transform: scale(1.5); outline: 3px solid var(--accent); }
  .big { font-size: 22px; font-weight: 700; margin: 8px 0; }
  .strip { position: relative; height: 34px; margin: 10px auto; max-width: 520px; background: #f2f0ea; border-radius: 8px; }
  .zero { position: absolute; left: 50%; top: 4px; bottom: 4px; width: 2px; background: var(--muted); }
  .tap { position: absolute; top: 9px; width: 8px; height: 16px; margin-left: -4px; border-radius: 3px; background: var(--accent); }
  .tap.out { background: #c9a36b; opacity: 0.6; }
  .actions { display: flex; gap: 12px; justify-content: center; margin-top: 10px; }
</style>
