<script lang="ts">
  // Journey map (arch §3 screen 3, "Journey maps"): the branching skill map as a path of bubbles,
  // left to right like the music: one concept per bubble (v0.25), labelled with its type (Notes,
  // Rhythm, Technique, Theory). Each bubble shows locked, ready to learn (its concept lesson open),
  // current, passed or mastered, and two star rows; a refresh badge when it is due for review, and
  // "Today" when it is in today's session. Tapping one shows its concept lesson and practice songs
  // (v0.29: the lesson opens from there; the map has no separate lightbulb); a tap anywhere else
  // closes it. In parent mode every bubble opens (the content preview). `test` draws a generated
  // 200-bubble map, the M5 render test.
  import { onMount, untrack } from "svelte";
  import Medal from "../components/Medal.svelte";
  import Stars from "../components/Stars.svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { allowed, conceptType, handsLabel, loadContent, rulesFor, type Content, type Rules } from "../lib/content";
  import { isPassed, type Progress, type SkillProgress } from "../lib/progress";
  import { keepView } from "../lib/keep";
  import { go } from "../lib/route";
  import type { PieceSummary, Skill, SkillMap } from "../lib/types";

  let { test = false }: { test?: boolean } = $props();

  const COL = 250, ROW = 215, X0 = 150, Y0 = 20, BUBBLE = 92;

  let content = $state<Content | null>(null);
  let error = $state("");
  let openId = $state<string | null>(null);       // the bubble whose pop-up is showing
  const open = $derived(openId ? content?.map.skills.find((s) => s.id === openId) ?? null : null);
  let bodyEl = $state<HTMLElement>();
  // back from a song: the map scrolled where it was, with the same pop-up open
  keepView<string | null>(untrack(() => (test ? "journey/test" : "journey")), () => bodyEl, { get: () => openId, set: (v) => { openId = v; } });

  /** A tap outside the pop-up and the bubbles closes the pop-up (a bubble opens its own). */
  function tapOutside(e: MouseEvent): void {
    if (openId && !(e.target as Element).closest?.(".sheet, .bubble")) openId = null;
  }

  let frame = $state("");

  onMount(async () => {
    if (test) {
      content = testContent(200);
      measureScroll();
      return;
    }
    try { content = await loadContent(); } catch (e) { error = `Can't load the skill map (${(e as Error).message}).`; }
    if (app.student && !app.parentMode) rules = await rulesFor(app.student.id);
    void app.refresh();
  });
  let rules = $state<Rules | null>(null);        // the child's genre and song rules (arch §10.1)

  /** The render test (arch §3 "Journey maps", M5): a generated map of `n` bubbles on 3 branches
   *  that join every 9 skills, with every state shown. */
  function testContent(n: number): Content {
    const tracks = ["reading", "technique", "rhythm"], last: Record<string, string> = {};
    const skills: Skill[] = [];
    for (let i = 0; i < n; i++) {
      const track = tracks[i % 3];
      let pre = last[track] ? [last[track]] : [];
      if (i && i % 9 === 0) pre = [...new Set([...pre, ...Object.values(last)])];
      skills.push({ id: `test.${i}`, name: `Skill ${i + 1}`, sequence: 10 * (i + 1), track, staff: "treble", prerequisites: pre,
                    map: "basic", level: `Level ${Math.floor(i / 50) + 1}`, placeholder: true, pieces: [] });
      last[track] = `test.${i}`;
    }
    const map: SkillMap = { placeholder: true, maps: [{ map: "basic", level: "Render test", file: "" }], skills };
    return { map, pieces: [], version: "test" };
  }

  /** Frame times while the map scrolls by itself for 3 seconds. */
  function measureScroll(): void {
    const el = document.querySelector(".map-body") as HTMLElement | null;
    if (!el) { requestAnimationFrame(measureScroll); return; }
    const times: number[] = [];
    let last = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      if (last) times.push(now - last);
      last = now;
      el.scrollLeft = ((now - t0) / 3000) * (el.scrollWidth - el.clientWidth);
      if (now - t0 < 3000) requestAnimationFrame(step);
      else {
        const sorted = [...times].sort((a, b) => a - b);
        frame = `${Math.round(1000 / (times.reduce((a, b) => a + b, 0) / times.length))} fps, worst ${Math.round(sorted[sorted.length - 1])} ms, ` +
          `${times.filter((d) => d > 25).length} frames over 25 ms`;
        (window as unknown as { __journeyTest: string }).__journeyTest = frame;
      }
    };
    requestAnimationFrame(step);
  }

  /** The test map shows every state; parent mode shows the content with no progress. */
  const progress = $derived<Progress>(test && content ? testProgress(content.map) : app.parentMode ? new Map() : app.progress);
  function testProgress(map: SkillMap): Progress {
    const states = ["mastered", "passed", "current", "locked"] as const;
    return new Map(map.skills.map((s, i) => {
      const status = states[Math.min(3, Math.floor(i / 50))];
      const p: SkillProgress = { skillId: s.id, status, lessonOpen: status !== "locked" || i % 7 === 0, conceptDone: status !== "locked",
        hold: false, mastery: null, bestMastery: null, accuracyStars: status === "locked" ? null : 3 + (i % 5) / 2,
        timingStars: status === "locked" ? null : 2.5 + (i % 4) / 2, stuck: false, due: status === "mastered" && i % 5 === 0,
        today: status === "current" && i % 3 === 0, attemptsWithoutPass: 0, tryAnotherWay: false, refresher: false, nextReview: null };
      return [s.id, p];
    }));
  }
  type Shown = "locked" | "open" | "current" | "passed" | "mastered";
  /** Locked, but with its concept lesson open: ready to learn. */
  const shown = (p: SkillProgress | undefined): Shown => (p?.status === "locked" && p.lessonOpen ? "open" : p?.status ?? "locked");

  // columns by depth (the longest prerequisite chain); within a column, rows follow the average row
  // of each skill's prerequisites (then sequence), so the paths cross as little as they can
  const placed = $derived.by(() => {
    if (!content) return [];
    const skills = [...content.map.skills].sort((a, b) => a.sequence - b.sequence);
    const byId = new Map(skills.map((s) => [s.id, s]));
    const depth = new Map<string, number>();
    const d = (s: Skill): number => {
      if (!depth.has(s.id)) depth.set(s.id, 1 + Math.max(-1, ...s.prerequisites.map((p) => byId.get(p)).filter((x): x is Skill => !!x).map(d)));
      return depth.get(s.id)!;
    };
    const cols = new Map<number, Skill[]>();
    for (const s of skills) cols.set(d(s), [...(cols.get(d(s)) ?? []), s]);
    const rowOf = new Map<string, number>();
    const out: { skill: Skill; x: number; y: number }[] = [];
    for (const col of [...cols.keys()].sort((a, b) => a - b)) {
      const mean = (s: Skill) => {
        const rs = s.prerequisites.map((q) => rowOf.get(q)).filter((r): r is number => r !== undefined);
        return rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 0;
      };
      cols.get(col)!.sort((a, b) => mean(a) - mean(b) || a.sequence - b.sequence).forEach((s, row) => {
        rowOf.set(s.id, row);
        out.push({ skill: s, x: X0 + col * COL, y: Y0 + row * ROW });
      });
    }
    return out;
  });
  const width = $derived(Math.max(...placed.map((p) => p.x), 0) + COL);
  const height = $derived(Math.max(...placed.map((p) => p.y), 0) + ROW);
  const links = $derived.by(() => {
    const at = new Map(placed.map((p) => [p.skill.id, p]));
    return placed.flatMap((p) => p.skill.prerequisites.map((q) => at.get(q)).filter((a) => !!a).map((a) => ({ from: a!, to: p })));
  });

  function curve(a: { x: number; y: number }, b: { x: number; y: number }): string {
    const x1 = a.x + BUBBLE / 2, y1 = a.y + BUBBLE / 2, x2 = b.x + 10, y2 = b.y + BUBBLE / 2, xm = (x1 + x2) / 2;
    return `M${x1},${y1} C${xm},${y1} ${xm},${y2} ${x2},${y2}`;
  }

  const icon: Record<Shown, string> = { locked: "🔒", open: "✨", current: "▶", passed: "✓", mastered: "🏆" };
  const statusText: Record<Shown, string> = { locked: "Locked", open: "Ready to learn", current: "Learning now", passed: "Passed", mastered: "Mastered" };

  function piecesOf(s: Skill): PieceSummary[] {
    return (s.pieces ?? []).map((id) => content?.pieces.find((p) => p.id === id))
      .filter((p): p is PieceSummary => !!p && allowed(p, rules));
  }
  function canOpen(s: Skill): boolean {
    return app.parentMode || shown(progress.get(s.id)) !== "locked";
  }
  /** How far the student is through a skill's unit (M10: every skill passed earns the unit's medal). */
  function unitTally(s: Skill): { passed: number; mastered: number; n: number } {
    const us = (content?.map.skills ?? []).filter((k) => k.level === s.level && k.unit === s.unit);
    return { n: us.length, passed: us.filter((k) => isPassed(progress.get(k.id))).length,
             mastered: us.filter((k) => progress.get(k.id)?.status === "mastered").length };
  }
  function needs(s: Skill): string {
    const names = s.prerequisites.filter((p) => !isPassed(progress.get(p))).map((p) => content?.map.skills.find((k) => k.id === p)?.name ?? p);
    return names.join(" and ");
  }
</script>

<svelte:document onclick={tapOutside} />

<div class="screen">
  <Status title={test ? "Journey render test" : "Journey"}>
    {#if content}<span class="muted">{content.map.maps.map((m) => m.level).join(", ")}</span>{/if}
    {#if test}<span>{placed.length} bubbles{frame ? ` · ${frame}` : " · scrolling…"}</span>{/if}
  </Status>

  <main class="body map-body" bind:this={bodyEl}>
    {#if error}<p class="notice error">{error}</p>{/if}
    {#if content?.map.placeholder && !test}
      <p class="muted note">Placeholder skill map, for testing.{app.parentMode ? " Parent mode: every bubble opens." : ""}</p>
    {:else if app.parentMode && !test && content}
      <p class="muted note">Parent mode: every bubble opens. {content.map.maps.map((m) => `${m.level}${m.source ? ` follows ${m.source}` : ""}`).join("; ")}.</p>
    {/if}
    <div class="map" style:width="{width}px" style:height="{height}px">
      <div class="chapter">{content?.map.maps[0]?.level ?? ""}</div>
      <svg class="paths" width={width} height={height} aria-hidden="true">
        {#each links as l, i (i)}
          <path d={curve(l.from, l.to)} class:done={isPassed(progress.get(l.from.skill.id))} />
        {/each}
      </svg>
      {#each placed as p (p.skill.id)}
        {@const pr = progress.get(p.skill.id)}
        {@const st = shown(pr)}
        <div class="node" style:left="{p.x}px" style:top="{p.y}px">
          <button class="bubble {st}" onclick={() => { openId = p.skill.id; }} aria-label="{p.skill.name}: {statusText[st]}">
            <span>{icon[st]}</span>
          </button>
          {#if pr?.due}<span class="badge" title="Time to review">🔁</span>
          {:else if pr?.today}<span class="today">Today</span>{/if}
          {#if pr?.hold}<span class="hold">Needs {(p.skill.requiredCapabilities ?? []).join(", ")}</span>{/if}
          <div class="name">{p.skill.name}</div>
          <div class="unit">{p.skill.unit ? `${p.skill.unit.split(" · ")[0]} · ` : ""}<span style:color={conceptType(p.skill.track).color}>{conceptType(p.skill.track).label}</span></div>
          <div class="stars">
            <Stars compact size={15} label="♪" value={pr?.accuracyStars ?? null} />
            <Stars compact size={15} label="⏱" value={pr?.timingStars ?? null} />
          </div>
        </div>
      {/each}
    </div>
  </main>

  {#if open}
    {@const st = shown(progress.get(open.id))}
    <div class="sheet">
      <div class="sheet-head">
        <h2>{open.name}</h2>
        <button class="quiet" onclick={() => { openId = null; }}>Close</button>
      </div>
      <p class="muted"><span class="type" style:background={conceptType(open.track).color}>{conceptType(open.track).label}</span>
        {statusText[st]}{open.unit ? ` · ${open.unit}` : ""}</p>
      {#if open.unit && !app.parentMode}
        {@const u = unitTally(open)}
        <p class="unitline">
          <Medal kind="unit" tier={u.mastered === u.n ? "silver" : u.passed === u.n ? "bronze" : null} size={30} />
          <span>{open.unit.split(" · ")[0]}: {u.passed} of {u.n} skills passed{u.passed === u.n ? ` · ${u.mastered} mastered` : ""}</span>
        </p>
      {/if}
      {#if open.description}<p>{open.description}</p>{/if}
      {#if app.parentMode && open.bookRefs?.length}
        <!-- arch §6.2: the family's own book pages for this concept (from content/private/, never committed) -->
        <p class="refs">📖 {content?.map.maps.find((m) => m.level === open!.level)?.source ?? "Book"}:
          {open.bookRefs.map((r) => `${r.book} p.${r.pages.replace(/\s*~$/, "")}`).join(" · ")}</p>
      {/if}
      {#if st === "locked" && !app.parentMode}
        <p class="notice">Unlocks after: {needs(open)}</p>
      {:else if st === "open" && !app.parentMode}
        <p class="notice">Start with the concept lesson: it shows the new idea, then the songs open.</p>
      {/if}
      <div class="cards">
        <button class="card" disabled={!canOpen(open)} onclick={() => go(`lesson/${encodeURIComponent(open!.id)}`)}>
          <span class="card-title">💡 Concept lesson</span>
          <span class="card-meta">Learn the new idea</span>
        </button>
        {#if piecesOf(open).length}<p class="practice">Practice songs</p>{/if}
        {#each piecesOf(open) as p (p.id)}
          {@const playable = app.parentMode || st === "current" || st === "passed" || st === "mastered"}
          <button class="card" class:locked={!playable} disabled={!playable} onclick={() => app.openPiece(p.id, "journey")}>
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
  .bubble.open { background: #fff7d1; color: #b07a00; border-color: #efd58a; }
  .badge { position: absolute; top: -10px; right: -10px; background: #fff; border-radius: 50%; width: 34px; height: 34px;
           display: grid; place-items: center; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); font-size: 18px; }
  .hold { font-size: 12px; font-weight: 700; color: #8a5a00; }
  .today { position: absolute; top: -12px; right: -26px; background: #ffe7a3; border-radius: 999px; padding: 1px 8px; font-size: 13px; font-weight: 800; }
  .name { width: 190px; text-align: center; font-weight: 700; font-size: 15px; margin-top: 6px; line-height: 1.2; }
  .unit { width: 190px; text-align: center; white-space: nowrap; font-size: 12px; font-weight: 700; color: var(--muted); }
  .stars { margin-top: 2px; }
  .type { color: #fff; border-radius: 999px; padding: 2px 10px; font-size: 13px; font-weight: 800; margin-right: 6px; }
  .unitline { display: flex; align-items: center; gap: 8px; font-weight: 650; font-size: 15px; color: var(--muted); margin: 4px 0; }
  .practice { margin: 6px 0 0; font-weight: 800; color: var(--muted); }
  .refs { font-size: 14px; background: #f6f3ea; border-radius: 10px; padding: 8px 12px; }
  .sheet {
    position: fixed; right: 16px; top: var(--deadzone); bottom: 90px; width: min(460px, 92vw); overflow: auto;
    background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 14px 20px 20px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18); z-index: 10; touch-action: pan-y;
  }
  .sheet-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .sheet .card { min-width: 0; width: 100%; }
  .card:disabled { opacity: 0.6; }
</style>
