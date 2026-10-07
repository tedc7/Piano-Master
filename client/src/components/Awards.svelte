<script lang="ts">
  // The trophy case (arch §3 "Rewards", M10), on My Progress and in the parent's progress report:
  // the star collection, the milestone medals with how far it is to the next one, and each level
  // and unit of the map with its bronze (every skill passed), silver (every one mastered) and gold
  // (every one mastered with 5 stars) medals. When the student opens it, their new medals are
  // marked seen; the parent looking doesn't change that.
  import { onMount } from "svelte";
  import Medal from "./Medal.svelte";
  import { api } from "../lib/api";
  import { app } from "../lib/app.svelte.js";
  import { starText, TIER_NAME, topStep, type AwardsReport, type Series, type Tally } from "../lib/awards";

  let { studentId, parent = false }: { studentId: string; parent?: boolean } = $props();

  let r = $state<AwardsReport | null>(null);
  let error = $state("");

  onMount(async () => {
    try {
      await api.flush();
      r = await api.request<AwardsReport>(`/students/${studentId}/awards`);
      if (!parent && r.unseen) {
        await api.request(`/students/${studentId}/awards/seen`, "POST").catch(() => {});
        if (app.rewards) app.rewards.unseen = 0;
      }
    } catch (e) {
      error = `Can't reach the piano server (${(e as Error).message}).`;
    }
  });

  const stars = $derived(r?.series.find((s) => s.kind === "stars") ?? null);
  const fresh = $derived((r?.recent ?? []).filter((a) => a.new));

  /** Where the student is now on a row of medals. */
  function value(s: Series): string {
    const v = s.value, n = (one: string, many: string) => `${v} ${v === 1 ? one : many}`;
    switch (s.kind) {
      case "stars": return n("star", "stars");
      case "streak": return `${n("day", "days")} in a row now`;
      case "mastered": return n("skill mastered", "skills mastered");
      case "fivestar": return `${n("song", "songs")} at 5 stars`;
      case "songs": return n("song played", "songs played");
      case "hours": return v < 1 ? `${Math.round(v * 60)} minutes` : n("hour", "hours");
    }
  }
  /** How far from the last medal earned (or the start) to the next one, 0..1. */
  function toNext(s: Series): number {
    if (!s.next) return 1;
    const from = topStep(s)?.at ?? 0;
    return Math.max(0, Math.min(1, (s.value - from) / (s.next.at - from)));
  }
  const pct = (n: number, of: number) => (of ? Math.round((100 * n) / of) : 0);
  const unitName = (u: string) => u.replace(/^Unit \d+ · /, "");
  const unitNo = (u: string) => u.match(/^Unit (\d+)/)?.[1] ?? "";
  const kindOf = (t: Tally & { level?: string }) => ("level" in t && t.level ? "level" : "unit") as "level" | "unit";
  const when = (d: string) => new Date(`${d}T12:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if r}
  <section class="panel trophy">
    <div class="collection">
      <div class="total">
        <span class="star">★</span>
        <div><b>{starText(r.stars.total)}</b><span>{parent ? "stars in the collection" : "stars in your collection"}</span></div>
      </div>
      <div class="growth">
        <span>+{starText(r.stars.today)} today</span><span>+{starText(r.stars.week)} this week</span>
      </div>
      {#if stars?.next}
        <div class="aim">
          <div class="bar"><span style:width="{toNext(stars) * 100}%"></span></div>
          <small>{starText(stars.next.at - stars.value)} more to the {stars.next.at}-star medal. Each song counts its best play, so beating your best adds stars.</small>
        </div>
      {/if}
    </div>

    {#if fresh.length}
      <div class="fresh">
        <h2>New medals</h2>
        <div class="fresh-row">
          {#each fresh as a (a.id)}
            <div class="fresh-one"><Medal kind={a.kind} tier={a.tier} size={52} /><div><b>{a.title}</b><span>{a.detail}</span></div></div>
          {/each}
        </div>
      </div>
    {/if}

    <h2>Milestones</h2>
    <div class="series">
      {#each r.series as s (s.kind)}
        {@const top = topStep(s)}
        <div class="medal-card" class:none={!top}>
          <Medal kind={s.kind} tier={top?.tier ?? null} size={60} label="{s.name}: {top ? `${TIER_NAME[top.tier]}, ${top.label}` : 'none yet'}" />
          <div class="mc-text">
            <b>{s.name}</b>
            <span class="muted">{value(s)}{top ? ` · ${TIER_NAME[top.tier]} medal` : ""}</span>
            {#if s.next}
              <div class="bar small"><span style:width="{toNext(s) * 100}%"></span></div>
              <small class="muted">Next: {s.next.label} ({TIER_NAME[s.next.tier]})</small>
            {:else}
              <small class="muted">Every medal earned!</small>
            {/if}
            <div class="pips" aria-hidden="true">
              {#each s.steps as st (st.at)}<span class="pip {st.earned ? st.tier : ''}" title={st.label}></span>{/each}
            </div>
          </div>
        </div>
      {/each}
    </div>

    <h2>Levels and units</h2>
    <p class="muted key">Bronze: every skill passed · Silver: every skill mastered · Gold: every skill mastered with 5 stars</p>
    {#each r.levels as lv (lv.level)}
      <div class="group level">
        <div class="g-name"><b>{lv.level}</b><span class="muted">{lv.passed} of {lv.skills} skills passed · {lv.mastered} mastered</span>
          <div class="bar"><span style:width="{pct(lv.passed, lv.skills)}%"></span></div></div>
        <div class="g-medals">
          {#each lv.medals as m (m.key)}
            <span title="{m.label}{m.earned ? ` · ${when(m.earned.date)}` : ''}"><Medal kind={kindOf(lv)} tier={m.earned ? m.tier : null} size={40} label="{lv.level} {m.label}: {m.earned ? 'earned' : 'not yet'}" /></span>
          {/each}
        </div>
      </div>
      {#each lv.units as u (u.unit)}
        <div class="group">
          <span class="u-no">{unitNo(u.unit)}</span>
          <div class="g-name"><b>{unitName(u.unit)}</b><span class="muted">{u.passed} of {u.skills} passed · {u.mastered} mastered{u.fivestar ? ` · ${u.fivestar} at 5 stars` : ""}</span>
            <div class="bar small"><span style:width="{pct(u.passed, u.skills)}%"></span></div></div>
          <div class="g-medals">
            {#each u.medals as m (m.key)}
              <span title="{m.label}{m.earned ? ` · ${when(m.earned.date)}` : ''}"><Medal kind="unit" tier={m.earned ? m.tier : null} size={34} label="{u.unit} {m.label}: {m.earned ? 'earned' : 'not yet'}" /></span>
            {/each}
          </div>
        </div>
      {/each}
    {/each}
  </section>
{:else if !error}
  <p class="muted">Loading…</p>
{/if}

<style>
  .trophy { margin-bottom: 14px; }
  .trophy h2 { margin-top: 18px; }
  .collection { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 28px; }
  .total { display: flex; align-items: center; gap: 12px; }
  .total .star { font-size: 52px; color: #f2b01e; line-height: 1; }
  .total div { display: flex; flex-direction: column; }
  .total b { font-size: 40px; line-height: 1; }
  .total span { color: var(--muted); font-weight: 650; }
  .growth { display: flex; flex-direction: column; font-weight: 700; color: #8a6200; }
  .aim { flex: 1 1 260px; display: flex; flex-direction: column; gap: 6px; }
  .bar { height: 10px; border-radius: 999px; background: #ecebe6; overflow: hidden; }
  .bar span { display: block; height: 100%; background: linear-gradient(90deg, #f2c94c, #d19a12); border-radius: 999px; }
  .bar.small { height: 7px; }
  .fresh { background: #fff8e4; border: 1px solid #f1dc9c; border-radius: 16px; padding: 4px 14px 12px; margin-top: 14px; }
  .fresh h2 { margin: 8px 0 !important; color: #8a6200; }
  .fresh-row { display: flex; flex-wrap: wrap; gap: 10px 22px; }
  .fresh-one { display: flex; align-items: center; gap: 10px; }
  .fresh-one div { display: flex; flex-direction: column; }
  .fresh-one span { color: var(--muted); font-size: 15px; }
  .series { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
  .medal-card { display: flex; gap: 12px; align-items: center; background: #f8f7f3; border: 1px solid var(--line); border-radius: 16px; padding: 10px 12px; }
  .mc-text { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .mc-text .muted { font-size: 15px; }
  .pips { display: flex; gap: 4px; margin-top: 2px; }
  .pip { width: 10px; height: 10px; border-radius: 50%; background: #e2e0d8; }
  .pip.bronze { background: #b8743a; }
  .pip.silver { background: #a3acb6; }
  .pip.gold { background: #d9a520; }
  .pip.platinum { background: #7fa6bf; }
  .key { font-size: 14px; margin: -4px 0 8px; }
  .group { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--line); }
  .group.level { border-top: 2px solid var(--line); }
  .u-no { flex: 0 0 30px; height: 30px; border-radius: 8px; background: #eef3fd; color: var(--accent); font-weight: 800; display: grid; place-items: center; }
  .g-name { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .g-name .muted { font-size: 14px; }
  .g-medals { display: flex; gap: 4px; }
</style>
