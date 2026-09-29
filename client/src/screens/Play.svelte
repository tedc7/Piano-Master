<script lang="ts">
  // The Play screen (arch §3): status strip (display only), moving staff with the play line and
  // lyrics, control strip, on-screen keyboard. Play and Loop need the MIDI piano; Listen doesn't.
  import { onMount, tick, untrack } from "svelte";
  import DeviceSettings from "../components/DeviceSettings.svelte";
  import PlayerSettings from "../components/PlayerSettings.svelte";
  import Stars from "../components/Stars.svelte";
  import Status from "../components/Status.svelte";
  import { api } from "../lib/api";
  import { app } from "../lib/app.svelte.js";
  import { KeyboardView, keyboardRange, noteName, type Target } from "../lib/keyboard";
  import { Player, type AttemptRecord, type Hands, type Mode, type State } from "../lib/player";
  import { STAR_MEANING } from "../lib/scoring";
  import { TRY_ANOTHER_WAY } from "../lib/progress";
  import { LYRIC_FILL, renderStaff, xAt, type StaffLayout } from "../lib/staff";
  import { go } from "../lib/route";
  import { buildTimeline, phraseIndexAt, type Timeline } from "../lib/timeline";
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
  let result = $state<AttemptRecord | null>(null);
  let loopNote = $state<{ text: string; stars: number } | null>(null);
  let hands = $state<Hands>("both");
  let section = $state<[number, number] | null>(null);   // null = all bars
  let phraseCount = $state(1);
  let pending = $state(api.pending);
  let sheet = $state(false);
  let another = $state(false);          // the "Try it another way" choices (arch §8.1)
  let countIn = $state<{ total: number; current: number } | null>(null);
  let wrongText = $state("");
  let recent = $state<{ text: string; key: number }[]>([]);
  let stats = $state({ fps: 0, worst: 0, over25: 0, renderMs: 0, problems: 0, measures: 0 });

  let stageEl: HTMLDivElement;
  let stripEl: HTMLDivElement;
  let kbHost: HTMLDivElement;
  let progressEl: HTMLDivElement;

  let tl!: Timeline;
  let layout: StaffLayout | null = null;
  let player: Player | null = null;
  let kb: KeyboardView | null = null;
  let litLyric: SVGTextElement | null = null;
  let glowing: Element[] = [];
  let wrongTimer = 0;
  let lastStageH = 0;
  let recentKey = 0;
  let loopTimer = 0;

  const hasMedia = $derived(!!piece?.media);
  const hasVocals = $derived(!!piece?.media && Object.values(piece.media.presets).some((p) => p?.vocals));
  const vocalsOn = $derived(piece ? !app.prefs.vocalsOff.includes(piece.id) : true);
  // songs with singing default to no click during play; the count-in always clicks
  let clickOverride = $state<boolean | null>(null);      // a remedy item's metronome, until the student changes it
  const clickOn = $derived(clickOverride ?? (piece ? app.prefs.click[piece.id] ?? !piece.media : true));
  const running = $derived(uiState === "countin" || uiState === "playing" || uiState === "gliding");
  const needPiano = $derived(mode !== "listen" && app.midiStatus !== "connected");
  const sectionLabel = $derived(section && tl && piece ? barsOf(section[0], section[1]) : "All bars");
  const flats = $derived((piece?.notation.header.keySig ?? 0) < 0);
  // In a Guided session, "Next" moves on after the result (arch §8.5); a reward pick counts too.
  // The session item this song was opened for is fixed when the screen opens: it stays the same
  // after the item is checked off, so "Play again" can still improve its stars.
  const opened = untrack(() => {
    const it = app.sessionItem;
    return it && app.student && (it.pieceId === id || it.kind === "pick") ? { ...it } : null;
  });
  const inSession = opened !== null;
  const sectionItem = (opened?.section !== null && opened?.section !== undefined) || !!opened?.bars;
  let itemSection: [number, number] | null = null;       // the phrases the item loops
  const itemNow = $derived(opened ? app.item(opened.id) : null);
  const itemSkill = $derived(opened?.skillId ?? piece?.skillId ?? null);
  const stillLearning = $derived(!!itemSkill && app.progress.get(itemSkill)?.status === "current");
  const offerAnother = $derived(inSession && stillLearning && (itemNow?.tries ?? 0) >= TRY_ANOTHER_WAY);

  onMount(() => {
    let raf = 0;
    let lastFrame = 0;
    const frames: number[] = [];
    let alive = true;
    const offMidi = app.midi.onEvent(onMidi);
    const offApi = api.onChange(() => { pending = api.pending; });
    const onVis = () => { if (document.hidden) player?.pause(); };
    const onResize = () => { if (!player?.running && stageEl && Math.abs(stageEl.clientHeight - lastStageH) > 20) drawStaff(); };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("resize", onResize);

    (async () => {
      try {
        if (id.startsWith("drill-")) {
          // a generated drill belongs to one student (arch §8.9)
          if (!app.student) throw new Error("drills are made for a student");
          piece = await api.request<Piece>(`/students/${app.student.id}/drills/${id}`);
        } else {
          const r = await fetch(`content/pieces/${id}.json`);
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          piece = await r.json();
        }
      } catch (e) {
        error = `Can't load this song (${(e as Error).message}).`;
        return;
      }
      const p = piece!;
      tl = buildTimeline(p.notation);
      phraseCount = tl.phrases.length;
      const saved = (opened?.preset as Preset | null) ?? app.prefs.presets[p.id];
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
        finished: (r) => {
          result = r;
          another = false;
          if (opened && !sectionItem) {
            const e = r.evaluation;
            app.completeItem(opened.id, { accuracyStars: e.accuracyStars, timingStars: e.timingStars, title: opened.kind === "pick" ? piece?.title : undefined });
          }
        },
        loopPass: (r) => {
          const e = r.evaluation;
          loopNote = { text: `${e.matched} of ${e.expected} notes`, stars: e.accuracyStars };
          clearTimeout(loopTimer);
          loopTimer = window.setTimeout(() => { loopNote = null; }, 3000);
          // a tricky-spot item is done once round its section
          if (opened && sectionItem && section && itemSection && section[0] === itemSection[0] && section[1] === itemSection[1]) {
            app.completeItem(opened.id, { accuracyStars: e.accuracyStars, timingStars: e.timingStars });
          }
        },
        save: (r) => {
          // the parent's plays are never recorded to a student (arch §3)
          api.saveAttempt({
            ...r, contentVersion: piece?.contentVersion, studentId: app.student?.id ?? null,
            skillId: itemSkill, itemId: opened?.id ?? null, context: opened ? "guided" : "free",
          });
          app.addPractice(r.durationSec, inSession);
        },
        loading: (f) => { loadingFrac = f; },
        error: (m) => { error = m; api.log("error", "play screen: " + m, { piece: id }); },
      }, preset);
      if (opened?.bars) itemSection = phrasesFor(opened.bars);
      else if (sectionItem && opened!.section! < tl.phrases.length) itemSection = [opened!.section!, opened!.section!];
      if (itemSection) {
        section = itemSection;
        player.setSection(section);
      }
      if (opened?.hands && opened.hands !== "both" && p.hands === "RL") {
        hands = opened.hands;
        player.setHands(hands);
        markHands();
      }
      if (opened?.click !== undefined) {
        clickOverride = opened.click;
        player.forceClick = opened.click;
      }
      void player.preload();
      (window as unknown as { __pm: unknown }).__pm = { player, tl, audio: app.audio, get layout() { return layout; } };

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
      offApi();
      clearTimeout(loopTimer);
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
    place(player ? player.position.display : -tl.barLength);
    markHands();
  }

  /** Practising one hand: the other hand's notes are shown faintly. */
  function markHands(): void {
    if (!layout) return;
    for (const n of tl.notes) layout.noteEls[n.id]?.classList.toggle("pm-other", hands !== "both" && n.hand !== hands);
  }

  function barsOf(a: number, b: number): string {
    const ph = tl.phrases;
    const inside = tl.entries.filter((e) => e.start >= ph[a].start - 1e-6 && e.start < ph[b].end - 1e-6);
    if (!inside.length) return "";
    const x = inside[0].m.number, y = inside[inside.length - 1].m.number;
    const verse = inside[0].verse > 1 ? ` (verse ${inside[0].verse})` : "";
    return (x === y ? `Bar ${x}` : `Bars ${x}–${y}`) + verse;
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
    } else if (mode !== "listen" && uiState !== "finished") {
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
    app.audio.mix.backingVolume = app.prefs.backingVolume;
    app.audio.applyMix();
  }

  // ------------------------------------------------------------------ controls
  /** Play and Listen each start and pause their own mode: tapping the current mode pauses or
   *  resumes it (or plays again after the end); tapping the other mode switches and starts it. */
  function tapMode(m: Mode): void {
    if (!player) return;
    if (m === mode) {
      if (running) player.pause(); else void player.play();
      return;
    }
    mode = m;
    result = null;
    loopNote = null;
    player.setMode(m);
    void player.play();
  }
  function rewind(): void { player?.rewindBars(app.prefs.rewindBars); }
  function playAgain(): void { another = false; void player?.play(); }
  function setHands(): void {
    const order: Hands[] = ["both", "R", "L"];
    hands = order[(order.indexOf(hands) + 1) % 3];
    player?.setHands(hands);
    markHands();
    result = null;
  }
  /** Step through "All bars" and each phrase's bars. */
  function moveSection(by: number): void {
    const cur = section ? section[0] : -1;
    const next = Math.max(-1, Math.min(tl.phrases.length - 1, cur + by));
    section = next < 0 ? null : [next, next];
    result = null;
    loopNote = null;
    player?.setSection(section);
  }
  async function practiceTricky(): Promise<void> {
    if (!player || !result?.tricky) return;
    const phrase = result.tricky.phrase;
    result = null;
    mode = "play";
    section = [phrase, phrase];
    preset = await player.practiceTricky(phrase);
  }
  function setPreset(p: Preset): void {
    if (!piece || !player) return;
    preset = p;
    app.setSongPref(piece.id, { preset: p });
    void player.setPreset(p);
  }
  function toggleVocals(): void {
    if (!piece) return;
    app.setSongPref(piece.id, { vocalsOff: vocalsOn });
    applyMix();
  }
  function toggleClick(): void {
    if (!piece) return;
    const on = !clickOn;
    clickOverride = null;
    if (player) player.forceClick = null;
    app.setSongPref(piece.id, { click: on });
  }
  /** The phrases covering written bars a..b (their first time through). */
  function phrasesFor([a, b]: [number, number]): [number, number] | null {
    const inBars = tl.entries.filter((e) => e.m.number >= a && e.m.number <= b);
    if (!inBars.length) return null;
    const from = inBars[0].start;
    const last = inBars.find((e, i) => i + 1 === inBars.length || inBars[i + 1].start !== e.start + e.duration) ?? inBars[inBars.length - 1];
    const to = last.start + last.duration;
    return [phraseIndexAt(tl.phrases, from), phraseIndexAt(tl.phrases, to - 1e-6)];
  }
  /** "Try it another way" (arch §8.1): gentle practice choices after 3 tries without passing. */
  function listenFirst(): void { result = null; another = false; tapMode("listen"); }
  function slower(): void {
    const next: Record<Preset, Preset> = { "100": "90", "90": "75", "75": "50", "50": "50" };
    result = null;
    another = false;
    setPreset(next[preset]);
    if (mode !== "play") tapMode("play"); else void player?.play();
  }
  function oneHand(): void { result = null; another = false; hands = "both"; setHands(); }
  /** Back to the screen that opened the song: the session, the song library, the map... */
  function back(): void {
    player?.stop();
    go(app.returnTo);
  }
  function next(): void {
    player?.stop();
    go("session");
  }
  function delayStats(): string {
    const d = [...app.midi.delays].sort((a, b) => a - b);
    if (!d.length) return "no notes yet";
    return `median ${d[d.length >> 1].toFixed(1)} ms, worst ${d[d.length - 1].toFixed(1)} ms (${d.length} notes)`;
  }

  const modeLabel = (m: Mode) => m !== mode ? (m === "play" ? "Play" : "Listen") :
    uiState === "loading" ? `Loading ${Math.round(loadingFrac * 100)}%` :
    running ? "Pause" : m === "play" ? "Play" : "Listen";
</script>

<div class="play">
  <Status title={piece?.title ?? "…"}>
    <div class="progress"><div class="bar" bind:this={progressEl}></div></div>
    <span>{mode === "play" ? "Play" : "Listen"} · {sectionLabel} · {preset}%{hands !== "both" ? (hands === "R" ? " · right hand" : " · left hand") : ""}</span>
    {#if pending}<span class="muted">{pending} to send</span>{/if}
  </Status>

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
    {#if loopNote}
      <div class="loopnote">{loopNote.text} · {"★".repeat(Math.floor(loopNote.stars))}{loopNote.stars % 1 ? "½" : ""}</div>
    {/if}
    {#if result}
      {@const e = result.evaluation}
      {@const tapping = piece?.drill?.anyKey !== undefined}
      {@const main = tapping ? e.timingStars ?? 0 : e.accuracyStars}
      <div class="result">
        <h2>{main >= 4.5 ? "Beautiful!" : main >= 3 ? "Well played!" : "Nice work, keep going!"}</h2>
        <!-- rhythm tapping scores timing only (§7.8) -->
        {#if !tapping}<Stars label="Notes" value={e.accuracyStars} />{/if}
        <Stars label="Timing" value={e.timingStars} />
        <p class="meaning">{STAR_MEANING[main]}{e.tendency === "early" ? " · a little rushed" : e.tendency === "late" ? " · a little behind the beat" : ""}</p>
        <p class="detail">{e.matched} of {e.expected} notes{e.extra ? ` · ${e.extra} extra` : ""}{result.conditions.rewinds ? ` · ${result.conditions.rewinds} rewind${result.conditions.rewinds > 1 ? "s" : ""}` : ""}{result.tricky ? ` · tricky spot: ${result.tricky.bars[0] === result.tricky.bars[1] ? `bar ${result.tricky.bars[0]}` : `bars ${result.tricky.bars[0]}–${result.tricky.bars[1]}`}` : ""}</p>
        {#if e.aids.length}
          <p class="chip">Practice mode: {e.aids.map((a) => a.label).join(", ")}</p>
          <p class="hint">{e.hint}</p>
        {/if}
        {#if another}
          <p class="meaning">This one's tricky! Want to try it another way?</p>
          <div class="choices">
            <button class="quiet" onclick={listenFirst}>👂 Listen first</button>
            {#if result.tricky}<button class="quiet" onclick={practiceTricky}>🎯 Practice the tricky part</button>{/if}
            {#if preset !== "50"}<button class="quiet" onclick={slower}>🐢 Slower</button>{/if}
            {#if piece?.hands === "RL"}<button class="quiet" onclick={oneHand}>✋ One hand at a time</button>{/if}
            {#if itemSkill}<button class="quiet" onclick={() => { player?.stop(); go(`lesson/${encodeURIComponent(itemSkill)}`); }}>💡 See the idea again</button>{/if}
            <button class="quiet" onclick={next}>🔀 Try something else</button>
            <button class="quiet" onclick={() => { player?.stop(); go("library"); }}>🎵 Free Play</button>
          </div>
        {:else}
          <div class="row">
            {#if offerAnother}
              <button onclick={() => { another = true; }}>Try it another way</button>
            {:else if result.tricky}
              <button onclick={practiceTricky}>Practice tricky part</button>
            {/if}
            <button class:quiet={!!result.tricky || inSession || offerAnother} onclick={playAgain}>Play again</button>
            {#if inSession}
              <button class:quiet={offerAnother} onclick={next}>Next ›</button>
            {:else}
              <button class="quiet" onclick={back}>Done</button>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="controls">
    <button class="quiet" onclick={back}>‹ Back</button>
    <div class="seg modes">
      <button class:sel={mode === "play"} onclick={() => tapMode("play")}
              disabled={!piece || (uiState === "loading" && mode !== "play") || (needPiano && !(mode === "play" && running))}>{modeLabel("play")}</button>
      <button class:sel={mode === "listen"} onclick={() => tapMode("listen")}
              disabled={!piece || (uiState === "loading" && mode !== "listen")}>{modeLabel("listen")}</button>
    </div>
    <button class="quiet" onclick={rewind} disabled={!piece || uiState === "idle" || uiState === "loading"} aria-label="Rewind">
      <svg class="restart" viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" /><path d="M4 3.5v4.2h4.2" /></svg>
    </button>
    <div class="seg">
      <button onclick={() => moveSection(-1)} disabled={!section} aria-label="Earlier bars">‹</button>
      <span class="loopbars">{sectionLabel}</span>
      <button onclick={() => moveSection(1)} disabled={!!section && section[0] >= phraseCount - 1} aria-label="Later bars">›</button>
    </div>
    {#if piece?.hands === "RL"}
      <button class="quiet hands" onclick={setHands}>{hands === "both" ? "Both hands" : hands === "R" ? "Right hand" : "Left hand"}</button>
    {/if}
    <div class="seg">
      {#each PRESETS as p}
        <button class:sel={preset === p} onclick={() => setPreset(p)}>{p}%</button>
      {/each}
    </div>
    {#if hasVocals}
      <button class="toggle" class:off={!vocalsOn} onclick={toggleVocals}>Vocals</button>
    {/if}
    <button class="toggle" class:off={!clickOn} onclick={toggleClick}>Metro</button>
    {#if app.parentMode}
      <button class="quiet" onclick={() => { sheet = !sheet; }} aria-label="Settings">⚙</button>
    {/if}
  </div>

  <div class="keys" bind:this={kbHost}></div>

  {#if sheet}
    <div class="sheet">
      <div class="sheet-head"><h2>Test settings</h2><button onclick={() => { sheet = false; }}>Close</button></div>
      <p class="muted small">For the parent. Students' own settings are under Config › Students.</p>
      <div class="grid">
        <DeviceSettings />
        <PlayerSettings settings={app.prefs} backing={hasMedia} onchange={(p) => { app.setParentPrefs(p); applyMix(); }} />
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
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
    max-height: calc(100% - 16px); overflow: auto; touch-action: pan-y;
    background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px 26px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12); text-align: center; min-width: 420px;
  }
  .result h2 { margin: 0 0 8px; }
  .result p { margin: 6px 0; }
  .meaning { font-weight: 650; }
  .detail { color: var(--muted); }
  .chip { display: inline-block; background: #eef3fd; border: 1px solid #cfdcf6; border-radius: 999px; padding: 3px 12px; font-size: 15px; }
  .hint { color: var(--muted); font-size: 15px; }
  .loopnote {
    position: absolute; right: 18px; bottom: 16px; background: var(--panel); border: 1px solid var(--line);
    border-radius: 12px; padding: 8px 14px; font-weight: 650; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1); pointer-events: none;
  }
  .loopbars { background: #ecebe6; display: flex; align-items: center; padding: 0 8px; font-weight: 650; min-width: 104px; justify-content: center; }
  .hands { min-width: 118px; }
  .muted { color: var(--muted); }
  .row { display: flex; gap: 12px; justify-content: center; margin-top: 12px; }
  .choices { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 10px; }
  .small { font-size: 14px; margin: 4px 0 0; }
  .controls {
    flex: 0 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 7px;
    padding: 10px 10px; background: var(--panel); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  }
  .modes button { min-width: 100px; }
  .controls > button { padding: 8px 13px; }
  .restart { width: 34px; height: 34px; display: block; fill: none; stroke: currentColor; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
  .seg { display: flex; border-radius: 12px; overflow: hidden; }
  .seg button { border-radius: 0; background: #ecebe6; color: var(--fg); padding: 8px 11px; }
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
  .sel { outline: 3px solid var(--accent); }
  .mono { font: 14px/1.4 ui-monospace, Menlo, monospace; }
</style>
