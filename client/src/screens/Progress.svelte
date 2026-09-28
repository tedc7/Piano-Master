<script lang="ts">
  // My Progress (arch §3 screen 8, §8.11): the student's own report in kid-friendly words. The
  // skills, practice days and "working on" are sample data until M4 and M5; the recent plays are
  // real attempts from the piano server (all players until attempts are stored per student, M4).
  import { onMount } from "svelte";
  import Stars from "../components/Stars.svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { loadContent, type Content } from "../lib/content";
  import { sampleProgress } from "../lib/progress";

  interface AttemptSummary {
    id: string; pieceId: string; mode: string; completed: boolean; startedAt: string;
    tempoPreset: string; accuracyStars: number | null; timingStars: number | null;
  }

  let content = $state<Content | null>(null);
  let recent = $state<AttemptSummary[] | null>(null);
  let recentError = $state("");

  onMount(async () => {
    try { content = await loadContent(); } catch { /* skills section stays empty */ }
    try {
      const r = await fetch("/api/attempts?limit=12");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      recent = (await r.json()).attempts;
    } catch (e) {
      recentError = `Can't reach the piano server (${(e as Error).message}).`;
    }
  });

  const progress = $derived(content ? sampleProgress(content.map) : new Map());
  const count = (st: string) => [...progress.values()].filter((p) => p.status === st).length;
  const skills = $derived(content ? [...content.map.skills].sort((a, b) => a.sequence - b.sequence) : []);
  const title = (id: string) => content?.pieces.find((p) => p.id === id)?.title ?? id;
  // the last 14 days, oldest first; sample practice pattern
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(Date.now() - (13 - i) * 86400000);
    return { label: d.toLocaleDateString(undefined, { weekday: "narrow" }), practised: [0, 1, 2, 4, 5, 8, 9, 10, 11, 12].includes(i) };
  });
  const when = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
</script>

<div class="screen">
  <Status title="My Progress">
    {#if app.student}<span>{app.student.avatar} {app.student.name}</span>{/if}
  </Status>

  <main class="body">
    <div class="grid">
      <section class="panel">
        <h2>My skills <span class="sample">sample</span></h2>
        <div class="counts">
          <div><b>{count("mastered")}</b><span>🏆 mastered</span></div>
          <div><b>{count("passed")}</b><span>✓ passed</span></div>
          <div><b>{count("current")}</b><span>▶ learning now</span></div>
        </div>
        {#each skills as s (s.id)}
          {@const p = progress.get(s.id)}
          {#if p && p.status !== "locked"}
            <div class="skill-row">
              <span class="skill-name">{s.name}</span>
              <Stars compact size={17} label="♪" value={p.accuracyStars} />
              <Stars compact size={17} label="⏱" value={p.timingStars} />
            </div>
          {/if}
        {/each}
      </section>

      <section class="panel">
        <h2>Practice days <span class="sample">sample</span></h2>
        <div class="days">
          {#each days as d, i (i)}
            <div class="day" class:on={d.practised}><span>{d.practised ? "🔥" : ""}</span><small>{d.label}</small></div>
          {/each}
        </div>
        <h2 class="gap">Great at <span class="sample">sample</span></h2>
        <p>Keeping a steady beat, and reading notes in C position.</p>
        <h2 class="gap">Working on</h2>
        <p>Reaching up to A with finger 5.</p>
      </section>
    </div>

    <section class="panel">
      <h2>Recent plays</h2>
      <p class="muted small">From the piano server. Everyone's plays show here until each play is saved to a player (M4).</p>
      {#if recentError}
        <p class="notice error">{recentError}</p>
      {:else if recent && !recent.length}
        <p class="muted">No plays yet. Plays are saved once the piano is connected.</p>
      {:else if recent}
        <table>
          <tbody>
            {#each recent as a (a.id)}
              <tr>
                <td class="muted">{when(a.startedAt)}</td>
                <td><b>{title(a.pieceId)}</b></td>
                <td class="muted">{a.mode} · {a.tempoPreset}%{a.completed ? "" : " · stopped"}</td>
                <td><Stars compact size={17} label="♪" value={a.accuracyStars} /></td>
                <td><Stars compact size={17} label="⏱" value={a.timingStars} /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>
  </main>

  <TabBar current="progress" />
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; }
  .grid .panel { margin-bottom: 0; }
  .grid + .panel { margin-top: 14px; }
  .counts { display: flex; gap: 12px; margin: 12px 0; }
  .counts div { flex: 1; background: #f4f2ec; border-radius: 12px; padding: 10px; text-align: center; display: flex; flex-direction: column; }
  .counts b { font-size: 28px; }
  .counts span { font-size: 14px; color: var(--muted); }
  .skill-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-top: 1px solid var(--line); }
  .skill-name { flex: 1; font-weight: 650; }
  .days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-top: 10px; }
  .day { display: flex; flex-direction: column; align-items: center; background: #f4f2ec; border-radius: 10px; padding: 6px 0; min-height: 52px; }
  .day.on { background: #ffe9c7; }
  .day small { color: var(--muted); }
  .gap { margin-top: 16px !important; }
  .small { font-size: 14px; margin: 4px 0 8px; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: 6px 8px; border-top: 1px solid var(--line); }
</style>
