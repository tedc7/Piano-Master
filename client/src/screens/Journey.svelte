<script lang="ts">
  // Journey map (arch §3 screen 3, "Journey maps"): the branching skill map as a path of bubbles,
  // left to right like the music, with a lightbulb (concept lesson) before each skill. Each
  // bubble shows locked, current, passed or mastered, and two star rows. Tapping one shows its
  // lesson and songs. In parent mode every bubble opens (the content preview).
  import { onMount } from "svelte";
  import Stars from "../components/Stars.svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { handsLabel, loadContent, type Content } from "../lib/content";
  import { isPassed, sampleProgress, type Progress } from "../lib/progress";
  import { go } from "../lib/route";
  import type { PieceSummary, Skill } from "../lib/types";

  const COL = 250, ROW = 190, X0 = 150, Y0 = 20, BUBBLE = 92;

  let content = $state<Content | null>(null);
  let error = $state("");
  let open = $state<Skill | null>(null);

  onMount(async () => {
    try { content = await loadContent(); } catch (e) { error = `Can't load the skill map (${(e as Error).message}).`; }
  });

  const progress = $derived<Progress>(content ? sampleProgress(content.map) : new Map());

  // columns by depth (the longest prerequisite chain), rows in sequence order within a column
  const placed = $derived.by(() => {
    if (!content) return [];
    const skills = [...content.map.skills].sort((a, b) => a.sequence - b.sequence);
    const byId = new Map(skills.map((s) => [s.id, s]));
    const depth = new Map<string, number>();
    const d = (s: Skill): number => {
      if (!depth.has(s.id)) depth.set(s.id, 1 + Math.max(-1, ...s.prerequisites.map((p) => byId.get(p)).filter((x): x is Skill => !!x).map(d)));
      return depth.get(s.id)!;
    };
    const rows = new Map<number, number>();
    return skills.map((s) => {
      const col = d(s);
      const row = rows.get(col) ?? 0;
      rows.set(col, row + 1);
      return { skill: s, x: X0 + col * COL, y: Y0 + row * ROW };
    });
  });
  const width = $derived(Math.max(...placed.map((p) => p.x), 0) + COL);
  const height = $derived(Math.max(...placed.map((p) => p.y), 0) + ROW);
  const links = $derived.by(() => {
    const at = new Map(placed.map((p) => [p.skill.id, p]));
    return placed.flatMap((p) => p.skill.prerequisites.map((q) => at.get(q)).filter((a) => !!a).map((a) => ({ from: a!, to: p })));
  });

  function curve(a: { x: number; y: number }, b: { x: number; y: number }): string {
    const x1 = a.x + BUBBLE / 2, y1 = a.y + BUBBLE / 2, x2 = b.x - 22, y2 = b.y + BUBBLE / 2, xm = (x1 + x2) / 2;
    return `M${x1},${y1} C${xm},${y1} ${xm},${y2} ${x2},${y2}`;
  }

  const icon = { locked: "🔒", current: "▶", passed: "✓", mastered: "🏆" };
  const statusText = { locked: "Locked", current: "Learning now", passed: "Passed", mastered: "Mastered" };

  function piecesOf(s: Skill): PieceSummary[] {
    return (s.pieces ?? []).map((id) => content?.pieces.find((p) => p.id === id)).filter((p): p is PieceSummary => !!p);
  }
  function canOpen(s: Skill): boolean {
    return app.parentMode || progress.get(s.id)?.status !== "locked";
  }
  function needs(s: Skill): string {
    const names = s.prerequisites.filter((p) => !isPassed(progress.get(p))).map((p) => content?.map.skills.find((k) => k.id === p)?.name ?? p);
    return names.join(" and ");
  }
</script>

<div class="screen">
  <Status title="Journey">
    {#if content}<span class="muted">{content.map.maps.map((m) => m.level).join(", ")}</span>{/if}
    <span class="sample">sample progress</span>
  </Status>

  <main class="body map-body">
    {#if error}<p class="notice error">{error}</p>{/if}
    {#if content?.map.placeholder}
      <p class="muted note">Placeholder skill map until the Faber books arrive.{app.parentMode ? " Parent mode: every bubble opens." : ""}</p>
    {/if}
    <div class="map" style:width="{width}px" style:height="{height}px">
      <div class="chapter">{content?.map.maps[0]?.level ?? ""}</div>
      <svg class="paths" width={width} height={height} aria-hidden="true">
        {#each links as l, i (i)}
          <path d={curve(l.from, l.to)} class:done={isPassed(progress.get(l.from.skill.id))} />
        {/each}
      </svg>
      {#each placed as p (p.skill.id)}
        {@const st = progress.get(p.skill.id)?.status ?? "locked"}
        {@const pr = progress.get(p.skill.id)}
        <div class="node" style:left="{p.x}px" style:top="{p.y}px">
          <button class="bulb" class:dim={st === "locked"} disabled={!canOpen(p.skill)}
                  onclick={() => go(`lesson/${encodeURIComponent(p.skill.id)}`)} aria-label="Concept lesson: {p.skill.name}">💡</button>
          <button class="bubble {st}" onclick={() => { open = p.skill; }} aria-label="{p.skill.name}: {statusText[st]}">
            <span>{icon[st]}</span>
          </button>
          {#if st === "current"}<span class="today">Today</span>{/if}
          <div class="name">{p.skill.name}</div>
          <div class="stars">
            <Stars compact size={15} label="♪" value={pr?.accuracyStars ?? null} />
            <Stars compact size={15} label="⏱" value={pr?.timingStars ?? null} />
          </div>
        </div>
      {/each}
    </div>
  </main>

  {#if open}
    {@const st = progress.get(open.id)?.status ?? "locked"}
    <div class="sheet">
      <div class="sheet-head">
        <h2>{open.name}</h2>
        <button class="quiet" onclick={() => { open = null; }}>Close</button>
      </div>
      <p class="muted">{statusText[st]} · {open.track} · {open.staff} staff</p>
      {#if open.description}<p>{open.description}</p>{/if}
      {#if st === "locked" && !app.parentMode}
        <p class="notice">Unlocks after: {needs(open)}</p>
      {/if}
      <div class="cards">
        <button class="card" disabled={!canOpen(open)} onclick={() => go(`lesson/${encodeURIComponent(open!.id)}`)}>
          <span class="card-title">💡 Concept lesson</span>
          <span class="card-meta">Learn the new idea</span>
        </button>
        {#each piecesOf(open) as p (p.id)}
          <button class="card" class:locked={!canOpen(open)} disabled={!canOpen(open)} onclick={() => app.openPiece(p.id, "journey")}>
            <span class="card-title">{p.title}</span>
            <span class="card-meta">{handsLabel(p.hands)} · {p.timeSig}{p.hasMedia ? " · with singing" : ""}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <TabBar current="journey" />
</div>

<style>
  .map-body { touch-action: pan-x pan-y; overflow: auto; }
  .note { margin: 0 0 8px; }
  .map { position: relative; }
  .chapter {
    position: absolute; left: 0; top: 40px; width: 110px; padding: 10px 0; text-align: center;
    background: #eef3fd; border: 1px solid #cfdcf6; border-radius: 14px; font-weight: 800; color: var(--accent);
  }
  .paths { position: absolute; left: 0; top: 0; pointer-events: none; }
  .paths path { fill: none; stroke: #d9d6cc; stroke-width: 8; stroke-linecap: round; stroke-dasharray: 2 14; }
  .paths path.done { stroke: #9cc9ae; stroke-dasharray: none; }
  .node { position: absolute; width: 92px; display: flex; flex-direction: column; align-items: center; }
  .bubble {
    width: 92px; height: 92px; border-radius: 50%; padding: 0; font-size: 34px; font-weight: 800;
    border: 4px solid #fff; box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15);
  }
  .bubble.locked { background: #d9d7d0; color: #fff; }
  .bubble.current { background: var(--accent); color: #fff; box-shadow: 0 0 0 6px rgba(47, 111, 219, 0.25), 0 6px 16px rgba(0, 0, 0, 0.15); }
  .bubble.passed { background: var(--ok); color: #fff; }
  .bubble.mastered { background: #f2b01e; color: #fff; }
  .bulb {
    position: absolute; left: -48px; top: 24px; width: 44px; height: 44px; min-width: 44px; min-height: 44px;
    padding: 0; border-radius: 50%; background: #fff7d1; border: 2px solid #efd58a; font-size: 20px;
  }
  .bulb.dim { filter: grayscale(1); opacity: 0.6; }
  .today { position: absolute; top: -12px; right: -26px; background: #ffe7a3; border-radius: 999px; padding: 1px 8px; font-size: 13px; font-weight: 800; }
  .name { width: 190px; text-align: center; font-weight: 700; font-size: 15px; margin-top: 6px; line-height: 1.2; }
  .stars { margin-top: 2px; }
  .sheet {
    position: fixed; right: 16px; top: var(--deadzone); bottom: 90px; width: min(460px, 92vw); overflow: auto;
    background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 14px 20px 20px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18); z-index: 10; touch-action: pan-y;
  }
  .sheet-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .sheet .card { min-width: 0; width: 100%; }
  .card:disabled { opacity: 0.6; }
</style>
