<script lang="ts">
  // Today's Practice (arch §3, §8.5): the student's start screen. The whole session is shown as a
  // path of bubbles, like the Journey map, so it is clear how many items finish it: done items
  // are checked off with the stars they earned, and the next one has an "Up next" card with the
  // reason and a big Start button. The ring shows today's practice minutes toward the target.
  // The queue is sample data until the server builds it (M5).
  import { onMount } from "svelte";
  import Stars from "../components/Stars.svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent, type Content } from "../lib/content";
  import { sampleProgress, sampleSession, type SessionItem } from "../lib/progress";
  import { go } from "../lib/route";

  const TARGET_MIN = 15;              // per student in M5 (§8.6)
  const STEP = 200, BUBBLE = 84, X0 = 30, Y0 = 30, WAVE = 56;

  let content = $state<Content | null>(null);
  let error = $state("");

  onMount(async () => {
    try {
      const c = await loadContent();
      content = c;
      app.ensureSession(() => sampleSession(c.map, c.pieces, sampleProgress(c.map)));
    } catch (e) {
      error = `Can't load today's practice from the piano server (${(e as Error).message}).`;
    }
  });

  const s = $derived(app.session);
  const item = $derived(app.sessionItem);
  const skill = $derived(item?.skillId ? content?.map.skills.find((k) => k.id === item.skillId) ?? null : null);
  const minutes = $derived(Math.floor((s?.seconds ?? 0) / 60));
  const ring = $derived(Math.min(1, minutes / TARGET_MIN));
  const starsToday = $derived((s?.results ?? []).reduce((n, r) => n + (r?.accuracyStars ?? 0), 0));
  const pos = (i: number) => ({ x: X0 + i * STEP, y: Y0 + (i % 2 ? WAVE : 0) });
  const width = $derived(X0 * 2 + Math.max(0, (s?.items.length ?? 1) - 1) * STEP + 170);

  const reasonIcon: Record<string, string> = { Review: "🔁", New: "✨", Practice: "🎯", "Your pick": "🎁" };
  const why: Record<string, string> = {
    Review: "Warm up with a song you already know.",
    New: "Something new today!",
    Practice: "Let's make this one even better.",
    "Your pick": "You choose! Pick any song you've unlocked.",
  };
  const label = (it: SessionItem) => (it.kind === "lesson" ? `💡 ${it.title}` : it.title);

  function curve(i: number): string {
    const a = pos(i), b = pos(i + 1), h = BUBBLE / 2;
    const x1 = a.x + h, y1 = a.y + h, x2 = b.x + h, y2 = b.y + h, xm = (x1 + x2) / 2;
    return `M${x1},${y1} C${xm},${y1} ${xm},${y2} ${x2},${y2}`;
  }

  function start(): void {
    if (!item) return;
    if (item.kind === "lesson" && item.skillId) go(`lesson/${encodeURIComponent(item.skillId)}`);
    else if (item.kind === "piece" && item.pieceId) app.openPiece(item.pieceId, "session");
    else go("library");
  }
</script>

<div class="screen">
  <Status title="Today's Practice">
    {#if s}<span class="muted">{Math.min(s.index, s.items.length)} of {s.items.length} done</span>{/if}
    <span>★ {starsToday} today</span>
    <span>🔥 3 days <span class="sample">sample</span></span>
  </Status>

  <main class="body">
    {#if app.needsFullScreen}
      <p class="notice">Turn on full screen in MIDIWeb Browser to hide the address bar.</p>
    {/if}
    {#if error}<p class="notice error">{error}</p>{/if}

    {#if s}
      <div class="top">
        <section class="panel path-panel">
          <div class="path" style:width="{width}px">
            <svg class="lines" width={width} height={Y0 * 2 + WAVE + BUBBLE} aria-hidden="true">
              {#each s.items.slice(0, -1) as _, i (i)}
                <path d={curve(i)} class:done={i < s.index} />
              {/each}
            </svg>
            {#each s.items as it, i (i)}
              {@const p = pos(i)}
              {@const r = s.results[i]}
              {@const st = i < s.index ? "done" : i === s.index ? "next" : "later"}
              <div class="node" style:left="{p.x}px" style:top="{p.y}px">
                <button class="bubble {st}" disabled={st !== "next"} onclick={start}
                        aria-label="{i + 1}. {label(it)}: {st === 'done' ? 'done' : st === 'next' ? 'up next' : 'later'}">
                  {st === "done" ? "✓" : reasonIcon[it.reason]}
                </button>
                {#if st === "next"}<span class="tag">Up next</span>{/if}
                <div class="name">{label(it)}</div>
                {#if st === "done" && r?.accuracyStars != null}
                  {#if r.title}<div class="picked">{r.title}</div>{/if}
                  <Stars compact size={15} label="♪" value={r.accuracyStars} />
                  <Stars compact size={15} label="⏱" value={r.timingStars} />
                {:else if st === "done"}
                  <div class="picked">Done</div>
                {:else}
                  <div class="reason">{it.reason}</div>
                {/if}
              </div>
            {/each}
          </div>
        </section>
        <div class="ring" style:--p={ring} aria-label="{minutes} of {TARGET_MIN} minutes today">
          <div class="ring-inner"><b>{minutes}</b><span>of {TARGET_MIN} min</span></div>
        </div>
      </div>

      {#if item}
        <div class="upnext">
          <div class="upnext-text">
            <p class="label">Up next · {item.reason}</p>
            <h1>{item.kind === "lesson" ? `New idea: ${item.title}` : item.title}</h1>
            <p class="why">{why[item.reason]}{skill && item.kind !== "lesson" ? ` Skill: ${skill.name}.` : ""}</p>
          </div>
          <div class="upnext-actions">
            <button class="start" onclick={start}>{item.kind === "pick" ? "Choose a song" : "Start"}</button>
            {#if s.index < s.items.length - 1}<button class="quiet" onclick={() => app.skipItem()}>Skip for now</button>{/if}
          </div>
        </div>
      {:else}
        <div class="upnext done">
          <div class="upnext-text">
            <p class="label">🎉 All done for today!</p>
            <h1>You played {s.items.length} things and earned {starsToday} stars.</h1>
            <p class="why">See you tomorrow! You can keep playing any song you like.</p>
          </div>
          <div class="upnext-actions"><button class="start" onclick={() => go("library")}>Songs</button></div>
        </div>
      {/if}
    {/if}
  </main>

  <TabBar current="session" />
</div>

<style>
  .top { display: flex; gap: 20px; align-items: center; margin-bottom: 18px; }
  .path-panel { flex: 1; overflow-x: auto; touch-action: pan-x; margin: 0; padding: 6px 10px; }
  .path { position: relative; height: 290px; }
  .lines { position: absolute; left: 0; top: 0; pointer-events: none; }
  .lines path { fill: none; stroke: #d9d6cc; stroke-width: 8; stroke-linecap: round; stroke-dasharray: 2 14; }
  .lines path.done { stroke: #9cc9ae; stroke-dasharray: none; }
  .node { position: absolute; width: 84px; display: flex; flex-direction: column; align-items: center; }
  .bubble {
    width: 84px; height: 84px; border-radius: 50%; padding: 0; font-size: 32px; font-weight: 800;
    border: 4px solid #fff; box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15);
  }
  .bubble:disabled { opacity: 1; }
  .bubble.done { background: var(--ok); color: #fff; }
  .bubble.next { background: var(--accent); color: #fff; box-shadow: 0 0 0 7px rgba(47, 111, 219, 0.25), 0 6px 16px rgba(0, 0, 0, 0.15); }
  .bubble.later { background: #fff; color: var(--fg); border-color: #e2dfd7; }
  .tag { position: absolute; top: -14px; right: -38px; background: #ffe7a3; border-radius: 999px; padding: 1px 8px; font-size: 13px; font-weight: 800; white-space: nowrap; }
  .name { width: 180px; text-align: center; font-weight: 700; font-size: 15px; margin-top: 6px; line-height: 1.2; }
  .reason, .picked { font-size: 13px; color: var(--muted); font-weight: 650; }
  .ring {
    flex: 0 0 130px; height: 130px; border-radius: 50%;
    background: conic-gradient(var(--ok) calc(var(--p) * 360deg), #e4e2da 0);
    display: grid; place-items: center;
  }
  .ring-inner { width: 100px; height: 100px; border-radius: 50%; background: var(--bg); display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .ring-inner b { font-size: 30px; line-height: 1; }
  .ring-inner span { font-size: 13px; color: var(--muted); }
  .upnext {
    display: flex; gap: 24px; align-items: center; background: var(--panel); border: 1px solid var(--line);
    border-radius: 22px; padding: 18px 24px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  }
  .upnext-text { flex: 1; }
  .label { margin: 0 0 4px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.04em; font-size: 15px; }
  .upnext.done .label { color: var(--ok); }
  .upnext h1 { font-size: 28px !important; margin: 0 0 6px !important; }
  .why { font-size: 18px; margin: 0; }
  .upnext-actions { display: flex; flex-direction: column; gap: 10px; align-items: stretch; }
  .start { font-size: 24px; min-width: 240px; min-height: 72px; border-radius: 18px; }
</style>
