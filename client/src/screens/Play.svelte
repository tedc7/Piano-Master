<script lang="ts">
  // The Play screen (arch §3): status strip (display only), moving staff with the play line and
  // lyrics, control strip, on-screen keyboard. Play mode needs the MIDI piano; Listen doesn't.
  import { onMount, tick } from "svelte";
  import { app, pianoLabel } from "../lib/app.svelte.js";
  import { KeyboardView, keyboardRange, noteName, type Target } from "../lib/keyboard";
  import { Player, type AttemptResult, type Mode, type State } from "../lib/player";
  import { toggleIn } from "../lib/settings";
  import { LYRIC_FILL, renderStaff, xAt, type StaffLayout } from "../lib/staff";
  import { buildTimeline, type Timeline } from "../lib/timeline";
  import { PRESETS, type Piece, type Preset } from "../lib/types";
  import type { MidiNote, MidiPedal } from "../lib/midi";

  let { id }: { id: string } = $props();

  const LINE_FRAC = 0.25;       // the play line sits a quarter of the way across the staff

  let piece = $state<Piece | null>(null);
  let error = $state("");
  let uiState = $state<State>("idle");
  let mode = $state<Mode>("play");
  let preset = $state<Preset>("100");
  let loadingFrac = $state(0);
  let result = $state<AttemptResult | null>(null);
  let sheet = $state(false);
  let countIn = $state<{ total: number; current: number } | null>(null);
  let wrongText = $state("");
  let recent = $state<{ text: string; key: number }[]>([]);
  let stats = $state({ fps: 0, worst: 0, over25: 0, renderMs: 0, problems: 0, measures: 0 });

  let stageEl: HTMLDivElement;
  let stripEl: HTMLDivElement;
  let kbHost: HTMLDivElement;
  let progressEl: HTMLDivElement;

  let tl: Timeline;
  let layout: StaffLayout | null = null;
  let player: Player | null = null;
  let kb: KeyboardView | null = null;
  let litLyric: SVGTextElement | null = null;
  let glowing: Element[] = [];
  let wrongTimer = 0;
  let lastStageH = 0;
  let recentKey = 0;

  const hasMedia = $derived(!!piece?.media);
  const vocalsOn = $derived(piece ? !app.settings.vocalsOff.includes(piece.id) : true);
  // songs with singing default to no click during play; the count-in always clicks
  const clickOn = $derived(piece ? app.settings.click[piece.id] ?? !piece.media : true);
  const running = $derived(uiState === "countin" || uiState === "playing" || uiState === "gliding");
  const needPiano = $derived(mode === "play" && app.midiStatus !== "connected");
  const flats = $derived((piece?.notation.header.keySig ?? 0) < 0);

  onMount(() => {
    let raf = 0;
    let lastFrame = 0;
    const frames: number[] = [];
    let alive = true;
    const offMidi = app.midi.onEvent(onMidi);
    const onVis = () => { if (document.hidden) player?.pause(); };
    const onResize = () => { if (!player?.running && stageEl && Math.abs(stageEl.clientHeight - lastStageH) > 20) drawStaff(); };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("resize", onResize);

    (async () => {
      try {
        const r = await fetch(`content/pieces/${id}.json`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        piece = await r.json();
      } catch (e) {
        error = `Can't load this song (${(e as Error).message}).`;
        return;
      }
      const p = piece!;
      tl = buildTimeline(p.notation);
      const saved = app.settings.presets[p.id];
      preset = saved && (!p.media || p.media.presets[saved]) ? saved : "100";
      applyMix();
      await tick();
      if (!alive) return;
      drawStaff();
      const [lo, hi] = keyboardRange(p.notation.header.range[0], p.notation.header.range[1]);
      kb = new KeyboardView(kbHost, lo, hi);
      player = new Player(p, tl, app.audio, () => app.settings, {
        state: (s) => {
          uiState = s;
          if (s === "playing") clearGlow();
        },
        verdict: (v, pitch) => {
          if (v.kind === "hit") {
            layout?.noteEls[v.noteId]?.classList.add(v.onTime ? "pm-ok" : "pm-late");
            kb?.press(pitch, v.onTime ? "ok" : "late");
          } else if (v.kind === "wrong") {
            kb?.press(pitch, "wrong");
            showWrong(pitch);
          }
        },
        keyDown: (pitch) => kb?.press(pitch, "neutral"),
        keyUp: (pitch) => kb?.release(pitch),
        missed: () => {},
        pass: (from, phrase) => {
          for (const n of tl.notes) if (n.beat >= from - 1e-6) layout?.noteEls[n.id]?.classList.remove("pm-ok", "pm-late");
          clearGlow();
          if (phrase !== null && layout) {
            // the first note of the phrase glows softly through the glide and count-in
            const ids = tl.phrases[phrase].noteIds;
            const first = Math.min(...ids.map((i) => tl.notes[i].beat));
            glowing = ids.filter((i) => tl.notes[i].beat === first).map((i) => layout!.noteEls[i]).filter((e): e is Element => !!e);
            for (const e of glowing) e.classList.add("pm-glow");
          }
          result = null;
        },
        finished: (r) => { result = r; },
        loading: (f) => { loadingFrac = f; },
        error: (m) => { error = m; },
      }, preset);
      void player.preload();
      (window as unknown as { __pm: unknown }).__pm = { player, tl, get layout() { return layout; } };

      const loop = (now: number) => {
        raf = requestAnimationFrame(loop);
        if (!player || !layout) return;
        const f = player.frame(now);
        place(f.beat);
        if (player.running) {
          if (lastFrame) frames.push(now - lastFrame);
          lastFrame = now;
          if (frames.length >= 60) {
            const total = frames.reduce((a, b) => a + b, 0);
            stats.fps = Math.round(frames.length / (total / 1000));
            stats.worst = Math.max(stats.worst, ...frames);
            stats.over25 += frames.filter((d) => d > 25).length;
            frames.length = 0;
          }
        } else {
          lastFrame = 0;
        }
        countIn = f.countIn;
        highlight(f.beat, f.logicBeat);
        progressEl.style.width = `${Math.max(0, Math.min(1, f.beat / tl.length)) * 100}%`;
      };
      raf = requestAnimationFrame(loop);
    })();

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      offMidi();
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("resize", onResize);
      player?.stop();
      kb?.destroy();
      delete (window as unknown as { __pm?: unknown }).__pm;
    };
  });

  function drawStaff(): void {
    if (!piece) return;
    lastStageH = stageEl.clientHeight;
    layout = renderStaff(stripEl, tl, piece.notation, stageEl.clientHeight);
    stripEl.style.top = `${Math.max(0, (stageEl.clientHeight - layout.height) / 2)}px`;
    stats.renderMs = Math.round(layout.renderMs);
    stats.problems = layout.problems.length;
    stats.measures = tl.entries.length;
    litLyric = null;
    if (layout.problems.length) console.warn("staff problems", layout.problems);
    place(-tl.barLength);
  }

  function place(beat: number): void {
    if (!layout) return;
    const lineX = stageEl.clientWidth * LINE_FRAC;
    const x = xAt(layout.map, beat) * layout.scale;
    stripEl.style.transform = `translate3d(${(lineX - x).toFixed(2)}px,0,0)`;
  }

  function highlight(beat: number, logicBeat: number): void {
    if (!layout || !kb || !player) return;
    // the lyric syllable being sung
    let ly: SVGTextElement | null = null;
    for (const l of layout.lyrics) {
      if (l.beat > beat) break;
      if (beat < l.end + 0.25) ly = l.el;
    }
    if (ly !== litLyric) {
      if (litLyric) { litLyric.setAttribute("fill", LYRIC_FILL); litLyric.removeAttribute("font-weight"); }
      if (ly) { ly.setAttribute("fill", "#d05a00"); ly.setAttribute("font-weight", "bold"); }
      litLyric = ly;
    }
    // keys: in Listen, the notes sounding; in Play, the next notes to play
    let targets: Target[] = [];
    if (mode === "listen" && player.running) {
      targets = tl.notes.filter((n) => n.beat <= beat && beat < n.beat + n.duration)
        .map((n) => ({ pitch: n.pitch, hand: n.hand, finger: n.finger }));
    } else if (mode === "play" && uiState !== "finished") {
      // while gliding back, show the notes play resumes on, not the ones sliding past
      const from = player.resumeBeat ?? (uiState === "idle" || uiState === "paused" ? Math.max(0, beat) : logicBeat - 0.25);
      const next = player.nextTargets(from);
      targets = next.map((n) => ({ pitch: n.pitch, hand: n.hand, finger: n.finger }));
    }
    kb.setTargets(targets);
  }

  function clearGlow(): void {
    for (const e of glowing) e.classList.remove("pm-glow");
    glowing = [];
  }

  function showWrong(pitch: number): void {
    wrongText = noteName(pitch, flats);
    clearTimeout(wrongTimer);
    wrongTimer = window.setTimeout(() => { wrongText = ""; }, 700);
  }

  function onMidi(ev: MidiNote | MidiPedal): void {
    player?.onMidi(ev);
    if (sheet) {
      const text = ev.type === "pedal" ? `pedal ${ev.value}` :
        `${ev.type === "on" ? "▼" : "▲"} ${noteName(ev.pitch, flats)}${Math.floor(ev.pitch / 12) - 1}` +
        (ev.type === "on" ? `  vel ${ev.velocity}  delay ${ev.delayMs.toFixed(1)} ms` : "");
      recent = [{ text, key: recentKey++ }, ...recent].slice(0, 8);
    }
  }

  function applyMix(): void {
    if (!piece) return;
    app.audio.mix.vocals = vocalsOn;
    app.audio.mix.backing = true;
    app.audio.mix.backingVolume = app.settings.backingVolume;
    app.audio.applyMix();
  }

  // ------------------------------------------------------------------ controls
  function playPause(): void {
    if (!player) return;
    if (running) player.pause(); else void player.play();
  }
  function startOver(): void { void player?.restart(); }
  function setMode(m: Mode): void {
    mode = m;
    player?.setMode(m);
    result = null;
  }
  function setPreset(p: Preset): void {
    if (!piece || !player) return;
    preset = p;
    app.settings.presets = { ...app.settings.presets, [piece.id]: p };
    app.save();
    void player.setPreset(p);
  }
  function toggleVocals(): void {
    if (!piece) return;
    app.settings.vocalsOff = toggleIn(app.settings.vocalsOff, piece.id, vocalsOn);
    app.save();
    applyMix();
  }
  function toggleClick(): void {
    if (!piece) return;
    app.settings.click = { ...app.settings.click, [piece.id]: !clickOn };
    app.save();
  }
  function nudge(key: "displayOffsetMs" | "latencyOffsetMs", by: number): void {
    app.settings[key] += by;
    app.save();
  }
  function backing(by: number): void {
    app.settings.backingVolume = Math.max(0, Math.min(3, Math.round((app.settings.backingVolume + by) * 4) / 4));
    app.save();
  }
  function back(): void {
    player?.stop();
    location.hash = "";
  }
  function delayStats(): string {
    const d = [...app.midi.delays].sort((a, b) => a - b);
    if (!d.length) return "no notes yet";
    return `median ${d[d.length >> 1].toFixed(1)} ms, worst ${d[d.length - 1].toFixed(1)} ms (${d.length} notes)`;
  }

  const playLabel = $derived(
    uiState === "loading" ? `Loading ${Math.round(loadingFrac * 100)}%` :
    running ? "Pause" : uiState === "paused" ? "Resume" : uiState === "finished" ? "Play again" : "Play",
  );
</script>

<div class="play">
  <header class="status">
    <span class="title">{piece?.title ?? "…"}</span>
    <div class="progress"><div class="bar" bind:this={progressEl}></div></div>
    <span>{mode === "play" ? "Play" : "Listen"} · {preset}%</span>
    <span class="muted"><span class="piano-dot" class:on={app.midiStatus === "connected"}></span>{pianoLabel(app.midiStatus, app.pianoName)}</span>
  </header>

  <div class="stage" bind:this={stageEl}>
    <div class="strip" bind:this={stripEl}></div>
    <div class="fade" style:width="{LINE_FRAC * 100}%"></div>
    <div class="playline" style:left="{LINE_FRAC * 100}%"></div>
    {#if countIn}
      <div class="countin" style:left="{LINE_FRAC * 100}%">
        {#each Array(countIn.total) as _, i}
          <span class="dot" class:on={i <= countIn.current}></span>
        {/each}
      </div>
    {/if}
    {#if wrongText}
      <div class="wrong" style:left="{LINE_FRAC * 100}%">{wrongText}</div>
    {/if}
    {#if error}
      <div class="message error">{error}</div>
    {:else if needPiano && !running && !result}
      <div class="message">Connect the piano to play along, or choose Listen.</div>
    {/if}
    {#if result}
      <div class="result">
        <h2>{result.missed + result.wrong === 0 ? "Beautiful!" : result.hits >= result.expected * 0.8 ? "Well played!" : "Nice work, keep going!"}</h2>
        <p>Notes played: <b>{result.hits}</b> of {result.expected} · on time: <b>{result.onTime}</b></p>
        <p>Wrong notes: {result.wrong} · rewinds: {result.rewinds}{result.tricky ? ` · tricky spot: bars ${result.tricky.bars[0]}–${result.tricky.bars[1]}` : ""}</p>
        <p class="muted">Stars and the practice tools come in M2.</p>
        <div class="row">
          <button onclick={startOver}>Play again</button>
          <button class="quiet" onclick={back}>Songs</button>
        </div>
      </div>
    {/if}
  </div>

  <div class="controls">
    <button class="quiet" onclick={back}>‹ Songs</button>
    <button class="main" onclick={playPause} disabled={!piece || uiState === "loading" || (needPiano && !running && uiState !== "paused")}>{playLabel}</button>
    <button class="quiet" onclick={startOver} disabled={!piece || uiState === "idle" || needPiano} aria-label="Start over">⟲</button>
    <div class="seg">
      <button class:sel={mode === "play"} onclick={() => setMode("play")}>Play</button>
      <button class:sel={mode === "listen"} onclick={() => setMode("listen")}>Listen</button>
    </div>
    <div class="seg">
      {#each PRESETS as p}
        <button class:sel={preset === p} onclick={() => setPreset(p)}>{p}%</button>
      {/each}
    </div>
    {#if hasMedia}
      <button class="toggle" class:off={!vocalsOn} onclick={toggleVocals}>Vocals</button>
    {/if}
    <button class="toggle" class:off={!clickOn} onclick={toggleClick}>Click</button>
    <button class="quiet" onclick={() => { sheet = !sheet; }} aria-label="Settings">⚙</button>
  </div>

  <div class="keys" bind:this={kbHost}></div>

  {#if sheet}
    <div class="sheet">
      <div class="sheet-head"><h2>Test settings</h2><button onclick={() => { sheet = false; }}>Close</button></div>
      <div class="grid">
        <span>Auto-rewind</span>
        <span><button class="toggle" class:off={!app.settings.autoRewind} onclick={() => { app.settings.autoRewind = !app.settings.autoRewind; app.save(); }}>{app.settings.autoRewind ? "On" : "Off"}</button></span>
        <span>Display offset</span>
        <span><button class="quiet" onclick={() => nudge("displayOffsetMs", -10)}>−10</button> <b>{app.settings.displayOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("displayOffsetMs", 10)}>+10</button></span>
        <span>Latency offset</span>
        <span><button class="quiet" onclick={() => nudge("latencyOffsetMs", -10)}>−10</button> <b>{app.settings.latencyOffsetMs} ms</b> <button class="quiet" onclick={() => nudge("latencyOffsetMs", 10)}>+10</button></span>
        {#if hasMedia}
          <span>Backing volume</span>
          <span><button class="quiet" onclick={() => backing(-0.25)}>−</button> <b>{Math.round(app.settings.backingVolume * 100)}%</b> <button class="quiet" onclick={() => backing(0.25)}>+</button></span>
        {/if}
        <span>Piano input</span>
        <span class="wrap">
          <button class="quiet" class:sel={!app.settings.pianoName} onclick={() => app.choosePiano(null)}>Automatic</button>
          {#each app.midiNames as n}
            <button class="quiet" class:sel={app.settings.pianoName === n} onclick={() => app.choosePiano(n)}>{n}</button>
          {/each}
        </span>
        <span>MIDI delivery delay</span>
        <span>{delayStats()}</span>
        <span>Last MIDI events</span>
        <span class="mono">{#each recent as r (r.key)}<div>{r.text}</div>{:else}press a key{/each}</span>
        <span>Staff</span>
        <span>{stats.measures} bars, rendered in {stats.renderMs} ms{stats.problems ? `, ${stats.problems} problems` : ""}</span>
        <span>Frames</span>
        <span>{stats.fps} fps, worst {Math.round(stats.worst)} ms, {stats.over25} over 25 ms</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .play { display: flex; flex-direction: column; height: 100%; }
  .progress { flex: 1; height: 8px; background: #ebe9e3; border-radius: 4px; overflow: hidden; min-width: 120px; }
  .bar { height: 100%; width: 0; background: var(--accent); }
  .stage { position: relative; flex: 1 1 auto; min-height: 200px; overflow: hidden; background: var(--staff-bg); touch-action: none; }
  .strip { position: absolute; left: 0; top: 0; will-change: transform; }
  .fade { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(255, 255, 255, 0.55); pointer-events: none; }
  .playline { position: absolute; top: 0; bottom: 0; width: 4px; margin-left: -2px; background: var(--accent); opacity: 0.55; pointer-events: none; }
  .countin { position: absolute; top: 14px; transform: translateX(-50%); display: flex; gap: 10px; pointer-events: none; }
  .dot { width: 18px; height: 18px; border-radius: 50%; background: #dfe6f5; }
  .dot.on { background: var(--accent); }
  .wrong { position: absolute; bottom: 14px; transform: translateX(-50%); color: var(--wrong); font-weight: 800; font-size: 30px; pointer-events: none; }
  .message { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); background: #fff4d6; border: 1px solid #efd58a; border-radius: 12px; padding: 10px 16px; }
  .message.error { background: #fde8e6; border-color: #f0b3ac; }
  .result {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -40%);
    background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px 26px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12); text-align: center; min-width: 420px;
  }
  .result h2 { margin: 0 0 8px; }
  .result p { margin: 6px 0; }
  .muted { color: var(--muted); }
  .row { display: flex; gap: 12px; justify-content: center; margin-top: 12px; }
  .controls {
    flex: 0 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
    padding: 10px 14px; background: var(--panel); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  }
  .controls .main { min-width: 130px; }
  .seg { display: flex; border-radius: 12px; overflow: hidden; }
  .seg button { border-radius: 0; background: #ecebe6; color: var(--fg); padding: 8px 14px; }
  .seg button.sel { background: var(--accent); color: var(--accent-fg); }
  .keys { position: relative; flex: 0 0 28%; min-height: 150px; background: #2a2a2e; margin: 0 10px 10px; }
  .sheet {
    position: fixed; left: 50%; top: var(--deadzone); transform: translateX(-50%);
    width: min(820px, 96vw); max-height: calc(100% - var(--deadzone) - 16px); overflow: auto;
    background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 14px 20px 20px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18); z-index: 10; touch-action: pan-y;
  }
  .sheet-head { display: flex; justify-content: space-between; align-items: center; }
  .sheet-head h2 { margin: 0; font-size: 20px; }
  .grid { display: grid; grid-template-columns: 190px 1fr; gap: 10px 16px; align-items: center; margin-top: 10px; }
  .wrap { display: flex; flex-wrap: wrap; gap: 8px; }
  .sel { outline: 3px solid var(--accent); }
  .mono { font: 14px/1.4 ui-monospace, Menlo, monospace; }
</style>
