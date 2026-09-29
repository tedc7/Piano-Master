<script lang="ts">
  // A student's progress report (arch §8.11), from the lesson engine: skills, star trends,
  // practice days, strengths by track and "working on". The student sees it in kid-friendly words
  // (My Progress); the parent sees the full detail (Config > Progress reports): mastery, stuck
  // skills, Guided and Free Play minutes, the target length, the content runway (§8.10) and what
  // Diagnostics found (§8.8), with stuck patterns highlighted.
  import { onMount } from "svelte";
  import Stars from "./Stars.svelte";
  import { api } from "../lib/api";
  import { loadContent, type Content } from "../lib/content";
  import type { SkillProgress } from "../lib/progress";

  let { studentId, full = false }: { studentId: string; full?: boolean } = $props();

  interface Report {
    skills: SkillProgress[];
    counts: Record<string, number>;
    days: { date: string; guidedSec: number; freeSec: number; practiced: boolean; sessionCompleted: boolean }[];
    streak: number;
    starsThisWeek: number;
    weeks: { from: string; plays: number; accuracyStars: number | null; timingStars: number | null }[];
    tracks: { track: string; mastery: number; skills: number }[];
    greatAt: string[];
    workingOn: string[];
    stuck: string[];
    masteredThisWeek: string[];
    targetMinutes: number;
    guidedMinutes28: number;
    freeMinutes28: number;
    runway: { remaining: number; passedLast28Days: number; daysLeft: number | null; alert: boolean; heldBy: string[] };
    patterns: Pattern[];
    recent: { startedAt: string; pieceId: string; mode: string; completed: boolean; tempoPreset: string;
              accuracyStars: number | null; timingStars: number | null; context: string }[];
  }

  interface Pattern {
    id: string; kind: string; details: { text?: string }; occurrences: number; firstSeen: string; lastSeen: string;
    remediesTried: string[]; goodDays: string[]; status: "active" | "improving" | "resolved" | "stuck"; resolvedDate: string | null;
  }
  const KIND: Record<string, string> = {
    note: "Note mix-up", rhythm: "Rhythm", hands: "Hands together", shift: "Hand moves", tempo: "Speed step",
  };

  let report = $state<Report | null>(null);
  let content = $state<Content | null>(null);
  let error = $state("");

  onMount(async () => {
    try { content = await loadContent(); } catch { /* names fall back to ids */ }
    try {
      await api.flush();
      report = await api.request<Report>(`/students/${studentId}/progress`);
    } catch (e) {
      error = `Can't reach the piano server (${(e as Error).message}).`;
    }
  });

  const skillName = (id: string) => content?.map.skills.find((s) => s.id === id)?.name ?? id;
  const title = (id: string) => (id.startsWith("drill-") ? "Practice game" : content?.pieces.find((p) => p.id === id)?.title ?? id);
  const day = (d: string) => new Date(`${d}T12:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const seq = (id: string) => content?.map.skills.find((s) => s.id === id)?.sequence ?? 0;
  const shownSkills = $derived((report?.skills ?? []).filter((s) => s.status !== "locked").sort((a, b) => seq(a.skillId) - seq(b.skillId)));
  const last14 = $derived((report?.days ?? []).slice(-14));
  const weekday = (d: string) => new Date(`${d}T12:00`).toLocaleDateString(undefined, { weekday: "narrow" });
  const when = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  const trackWords: Record<string, string> = {
    reading: "reading notes", rhythm: "keeping the beat", technique: "finger skills", theory: "music ideas",
    repertoire: "playing songs", musicianship: "listening",
  };
  const list = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0] ?? "");
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if report}
  {@const r = report}
  <div class="grid">
    <section class="panel">
      <h2>{full ? "Skills" : "My skills"}</h2>
      <div class="counts">
        <div><b>{r.counts.mastered}</b><span>🏆 mastered</span></div>
        <div><b>{r.counts.passed}</b><span>✓ passed</span></div>
        <div><b>{r.counts.current}</b><span>▶ learning now</span></div>
      </div>
      {#each shownSkills as s (s.skillId)}
        <div class="skill-row">
          <span class="skill-name">{skillName(s.skillId)}{#if s.stuck && full} <span class="flag">stuck</span>{/if}</span>
          {#if full}<span class="muted mono">{s.mastery === null ? "–" : `${Math.round(s.mastery * 100)}%`}</span>{/if}
          <Stars compact size={17} label="♪" value={s.accuracyStars} />
          <Stars compact size={17} label="⏱" value={s.timingStars} />
        </div>
      {:else}
        <p class="muted">{full ? "No skills started yet." : "Your first skill starts in Today's Practice."}</p>
      {/each}
    </section>

    <section class="panel">
      <h2>{full ? "Practice days" : "My practice days"}</h2>
      <div class="days">
        {#each last14 as d (d.date)}
          <div class="day" class:on={d.practiced} title={d.date}><span>{d.practiced ? (d.sessionCompleted ? "🔥" : "✓") : ""}</span><small>{weekday(d.date)}</small></div>
        {/each}
      </div>
      <p class="line">🔥 {r.streak} day{r.streak === 1 ? "" : "s"} in a row · ★ {r.starsThisWeek} stars this week</p>
      {#if full}
        <p class="line muted">Last 4 weeks: {r.guidedMinutes28} min Guided, {r.freeMinutes28} min Free Play. Today's target: {r.targetMinutes} min.</p>
        <div class="weeks">
          {#each r.weeks as w (w.from)}
            <div><small>from {new Date(`${w.from}T12:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small>
              <b>{w.accuracyStars === null ? "–" : w.accuracyStars.toFixed(1)}</b><span class="muted">♪</span>
              <b>{w.timingStars === null ? "–" : w.timingStars.toFixed(1)}</b><span class="muted">⏱</span>
              <small>{w.plays} plays</small></div>
          {/each}
        </div>
      {/if}
      <h2 class="gap">{full ? "Strongest" : "Great at"}</h2>
      {#if full}
        {#each r.tracks as t (t.track)}<p class="line">{t.track}: {Math.round(t.mastery * 100)}% best mastery over {t.skills} skill{t.skills === 1 ? "" : "s"}</p>{:else}<p class="muted">Not enough plays yet.</p>{/each}
      {:else if r.greatAt.length}
        <p>{list(r.greatAt)}{r.tracks[0] ? `, and ${trackWords[r.tracks[0].track] ?? r.tracks[0].track}` : ""}.</p>
      {:else}
        <p class="muted">Keep playing: your best skills show up here.</p>
      {/if}
      <h2 class="gap">Working on</h2>
      <p>{r.workingOn.length ? list(r.workingOn) : full ? "Nothing current." : "Your next new skill!"}</p>
      {#if full && r.stuck.length}<p class="notice">Stuck: {list(r.stuck)}. The sessions add support practice around it (arch §8.1).</p>{/if}
      {#if full}
        <h2 class="gap">Content runway</h2>
        <p class:alert={r.runway.alert}>{r.runway.remaining} skill{r.runway.remaining === 1 ? "" : "s"} left in the authored map{r.runway.daysLeft !== null ? `, about ${r.runway.daysLeft} days at the current pace` : ""}{r.runway.alert ? " — time to add the next level" : ""}.</p>
        {#if r.runway.heldBy.length}<p class="muted">Some skills wait for: {list(r.runway.heldBy)}.</p>{/if}
      {/if}
    </section>
  </div>

  {#if full}
    <section class="panel">
      <h2>What Diagnostics found</h2>
      <p class="muted small">Patterns in the last 14 days of playing (arch §8.8). Each gets a short practice game or exercise
        in Today's Practice; it is resolved after two good days, and marked stuck after 3 tries or 2 weeks without one.</p>
      {#each r.patterns as p (p.id)}
        <div class="pattern" class:stuck={p.status === "stuck"}>
          <span class="chip {p.status}">{p.status}</span>
          <span class="ptext"><b>{KIND[p.kind] ?? p.kind}:</b> {p.details.text ?? p.kind}</span>
          <span class="muted small">since {day(p.firstSeen)} · {p.remediesTried.length} practice{p.remediesTried.length === 1 ? "" : "s"}{p.status === "resolved" && p.resolvedDate ? ` · resolved ${day(p.resolvedDate)}` : ""}</span>
        </div>
      {:else}
        <p class="muted">Nothing found. Patterns need a few days of playing to show up.</p>
      {/each}
    </section>
  {/if}

  <section class="panel">
    <h2>{full ? "Recent plays" : "My recent plays"}</h2>
    {#if !r.recent.length}
      <p class="muted">No plays yet.</p>
    {:else}
      <table>
        <tbody>
          {#each r.recent as a, i (i)}
            <tr>
              <td class="muted">{when(a.startedAt)}</td>
              <td><b>{title(a.pieceId)}</b></td>
              <td class="muted">{a.context === "guided" ? "Today's Practice" : "Free Play"} · {a.mode === "loop" ? "section" : "whole song"} · {a.tempoPreset}%{a.completed ? "" : " · stopped"}</td>
              <td><Stars compact size={17} label="♪" value={a.accuracyStars} /></td>
              <td><Stars compact size={17} label="⏱" value={a.timingStars} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
{:else if !error}
  <p class="muted">Loading…</p>
{/if}

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
  .flag { background: #fde8e6; color: var(--wrong); border-radius: 999px; padding: 0 8px; font-size: 13px; }
  .mono { font: 13px ui-monospace, Menlo, monospace; }
  .days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-top: 10px; }
  .day { display: flex; flex-direction: column; align-items: center; background: #f4f2ec; border-radius: 10px; padding: 6px 0; min-height: 52px; }
  .day.on { background: #ffe9c7; }
  .day small { color: var(--muted); }
  .line { margin: 8px 0 0; }
  .weeks { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 8px; }
  .weeks div { background: #f4f2ec; border-radius: 10px; padding: 6px; display: flex; flex-direction: column; align-items: center; font-size: 14px; }
  .gap { margin-top: 16px !important; }
  .alert { color: #8a5a00; font-weight: 650; }
  .small { font-size: 14px; }
  .pattern { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid var(--line); flex-wrap: wrap; }
  .pattern.stuck { background: #fff4e0; }
  .ptext { flex: 1; min-width: 240px; }
  .chip { border-radius: 999px; padding: 1px 10px; font-size: 13px; font-weight: 700; background: #ecebe6; }
  .chip.stuck { background: #fde8e6; color: var(--wrong); }
  .chip.improving { background: #e7f4e4; color: var(--ok); }
  .chip.resolved { background: #e7f4e4; color: var(--ok); }
  table { width: 100%; border-collapse: collapse; }
  td { padding: 6px 8px; border-top: 1px solid var(--line); }
</style>
