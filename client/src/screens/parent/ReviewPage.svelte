<script lang="ts">
  // Config > Review list (arch §10.7, v0.23): every song the Claude skills submitted and the parent
  // hasn't decided on, in one list, in the order they arrived. Each opens in the Play screen to hear
  // it with its vocal and backing, and has its own decision:
  //   Approve            - into the library: it follows each child's genre rules, marked New;
  //   Needs improvement  - back to the skills with what to change (typed here, kept on the server);
  //                        the fixed song comes back to this list with that note beside it;
  //   Never allow        - deleted: the skills can't offer it again.
  // An update to a live song (v0.27: the parent's Needs improvement on a library song, fixed and
  // resubmitted under the same id) shows what changed and plays the live version beside it; it's
  // approved (replacing the live song in place), sent back again, or discarded (the live one stays).
  // A song stays here until the parent decides. Nothing on this list reaches a child. Below the
  // waiting list: songs sent back for changes, and the deleted songs (never allowed here, or deleted
  // from the library in Songs and genres), which can go back to review, be sent for improvement
  // (to be corrected), or be forgotten (the skills may then offer them again).
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";
  import { handsLabel, loadContent, reloadContent } from "../../lib/content";

  interface Checks {
    notesOnPitch?: number; wordsOff?: number; pass?: boolean; reasons?: string[]; flags?: string[];
    grid100?: { median_ms?: number }; grid50?: { median_ms?: number };
  }
  interface Item {
    id: string; pieceId: string; song: string; title: string; composer: string | null; genre: string; hasMedia: boolean;
    package?: string; submitted?: string; feedback?: string | null; decidedAt?: string | null;
    deletedFrom?: "review" | "library" | null; deletedReason?: string | null; hasFiles?: boolean;
    previousFeedback?: { feedback: string; decidedAt: string };
    live?: string;                    // the library song this updates
    changes?: { bars: number[]; tempo: [number, number]; lyrics: boolean; media: boolean;
                requiredSkills: [string[], string[]]; beyondMap: [string[], string[]] };
    info: {
      level?: string; hands?: string; source?: { site?: string; url?: string }; license?: { composition?: string; edition?: string; evidence?: string };
      tempoSource?: string; notes?: string[]; flags?: string[]; lyrics?: string; checks?: Checks | null;
      backing?: { style?: string; parts?: { name: string }[] } | null; engine?: string;
    };
    report: { errors?: string[]; warnings?: string[] };
    summary: { timeSig?: string; tempo?: number; beats?: number };
  }

  let items = $state<Item[]>([]);
  let sentBack = $state<Item[]>([]);
  let deleted = $state<Item[]>([]);
  let loaded = $state(false);
  let error = $state("");
  let done = $state("");
  let open = $state<{ id: string; kind: "improve" | "never" } | null>(null);   // the decision being written
  let feedback = $state("");
  let busy = $state(false);
  let skillNames = $state<Record<string, string>>({});

  onMount(() => {
    void load();
    loadContent().then((c) => { skillNames = Object.fromEntries(c.map.skills.map((s) => [s.id, s.name])); }).catch(() => {});
  });

  async function load(): Promise<void> {
    try {
      const r = await api.request<{ items: Item[]; sentBack: Item[]; deleted: Item[] }>("/review");
      items = r.items;
      sentBack = r.sentBack;
      deleted = r.deleted;
      error = "";
    } catch (e) {
      if (!app.parentRefused(e)) error = `Can't reach the piano server (${(e as Error).message}).`;
    }
    loaded = true;
  }

  async function decide(it: Item, action: "approve" | "improve" | "never" | "restore" | "forget" | "discard"): Promise<void> {
    busy = true;
    try {
      const body = action === "improve" ? { feedback: feedback.trim() } : action === "never" ? {} : undefined;
      await api.request(`/review/items/${it.id}/${action}`, "POST", body);
      done = action === "approve" && it.live
        ? `${it.title} is updated: the children play the new version from now on, with their stars and progress kept.`
        : action === "discard" ? `${it.title} stays as it was: the update is gone.`
        : action === "approve"
        ? `${it.title} is in the library. Each child sees it once its genre is allowed (Config › Songs and genres).`
        : action === "improve" ? `${it.title} went back with your note; it will come back to this list once it's changed.`
        : action === "restore" ? `${it.title} is waiting for you again.`
        : action === "forget" ? `${it.title} is forgotten: the skills may offer it again.`
        : `${it.title} is deleted and won't be offered again (see Deleted songs, below).`;
      if (action === "approve") reloadContent();
      open = null;
      feedback = "";
      await load();
    } catch (e) {
      if (!app.parentRefused(e)) error = (e as Error).message;
    }
    busy = false;
  }

  let forgetting = $state<string | null>(null);

  function start(it: Item, kind: "improve" | "never"): void {
    open = { id: it.id, kind };
    feedback = "";
  }

  const pct = (x?: number) => (x == null ? "–" : `${Math.round(x * 100)}%`);
  const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");
  const seconds = (it: Item) => (it.summary.beats && it.summary.tempo ? Math.round((it.summary.beats * 60) / it.summary.tempo) : null);
  const listen = (it: Item) => app.openPiece(`staged--${it.id}`, "config/review");
  const names = (ids: string[]) => ids.map((id) => skillNames[id] ?? id).join(", ") || "nothing";
  function changeText(ch: NonNullable<Item["changes"]>): string {
    const out = [ch.bars.length ? `notes in bar${ch.bars.length > 1 ? "s" : ""} ${ch.bars.join(", ")}` : "the same notes"];
    if (ch.tempo[0] !== ch.tempo[1]) out.push(`tempo ${ch.tempo[0]} → ${ch.tempo[1]}`);
    if (ch.lyrics) out.push("the words");
    if (ch.media) out.push("a new vocal or backing");
    return out.join(" · ");
  }
  const skillsChanged = (ch: NonNullable<Item["changes"]>) =>
    names(ch.requiredSkills[0]) !== names(ch.requiredSkills[1]) || ch.beyondMap[0].join() !== ch.beyondMap[1].join();
</script>

{#if error}<p class="notice error">{error}</p>{/if}
{#if done}<p class="notice">{done}</p>{/if}

<section class="panel">
  <h2>Waiting for you ({items.length})</h2>
  <p class="muted">Listen to each song, then approve it, send it back with what needs to change, or never allow it.
    A song stays here until you decide.</p>

  {#each items as it (it.id)}
    {@const c = it.info.checks}
    <div class="item">
      <div class="what">
        <div class="title-row">
          <span class="title">{it.title}</span>
          {#if it.live}<span class="badge">Update to a live song</span>{/if}
          <span class="muted">{it.composer ?? ""} · {it.genre} · {it.info.level ?? ""} · {handsLabel(it.info.hands ?? "R")}
            · {it.summary.timeSig}{#if seconds(it)} · about {seconds(it)} s{/if}</span>
        </div>
        {#if it.previousFeedback}
          <p class="changed">Changed after your note ({when(it.previousFeedback.decidedAt)}): “{it.previousFeedback.feedback}”</p>
        {/if}
        {#if it.changes}
          <p class="line">Changes from the live song: {changeText(it.changes)}</p>
          {#if skillsChanged(it.changes)}
            <p class="line warn">It now needs {it.changes.beyondMap[1].length ? `more than the map teaches (${it.changes.beyondMap[1].join(", ")})`
              : names(it.changes.requiredSkills[1])}, where the live song needs {names(it.changes.requiredSkills[0])}:
              a child who hasn't reached those skills won't see it after the update.</p>
          {/if}
        {/if}
        {#if c}
          <p class="line">Vocal: {pct(c.notesOnPitch)} of notes on pitch · {pct(c.wordsOff)} of words off the notes
            {#if c.grid100?.median_ms != null} · on the beat within {Math.round(c.grid100.median_ms)} ms{/if}
            · <b class:ok={c.pass} class:warn={!c.pass}>{c.pass ? "checks pass" : "checks: " + (c.reasons ?? []).join("; ")}</b></p>
        {/if}
        {#if it.info.backing?.parts}
          <p class="line">Backing: {it.info.backing.parts.map((x) => x.name).join(", ")}</p>
        {:else if !it.hasMedia}
          <p class="line muted">No vocal or backing: the app's piano plays the other hand.</p>
        {/if}
        {#if (c?.flags ?? []).length || (it.report.warnings ?? []).length}
          <ul class="flags">
            {#each [...(c?.flags ?? []).map((f) => "Listen for " + f), ...(it.report.warnings ?? [])] as f (f)}<li>{f}</li>{/each}
          </ul>
        {/if}
        <details>
          <summary>Source, license, tempo, lyrics and notes</summary>
          <p class="line">Source: {#if it.info.source?.url}<a href={it.info.source.url} target="_blank" rel="noreferrer">{it.info.source?.site}</a>{:else}{it.info.source?.site}{/if}
            <span class="muted">· from {it.package} · {when(it.submitted)}</span></p>
          <p class="line">License: composition {it.info.license?.composition}; edition {it.info.license?.edition}{#if it.info.license?.evidence} ({it.info.license.evidence}){/if}</p>
          {#if it.info.tempoSource}<p class="line">Tempo: {it.info.tempoSource}</p>{/if}
          {#if it.info.lyrics}<pre class="lyrics">{it.info.lyrics}</pre>{/if}
          {#each it.info.notes ?? [] as n (n)}<p class="line muted">{n}</p>{/each}
        </details>

        {#if open?.id === it.id && open.kind === "improve"}
          <div class="write">
            <label for="fb-{it.id}">What needs to change? The skills read this, fix the song and send it back here.</label>
            <textarea id="fb-{it.id}" bind:value={feedback} rows="3" maxlength="4000"
                      placeholder="For example: too fast, several words run together; try it slower."></textarea>
            <div class="buttons">
              <button onclick={() => decide(it, "improve")} disabled={busy || feedback.trim().length < 3}>Send back</button>
              <button class="quiet" onclick={() => { open = null; }}>Cancel</button>
            </div>
          </div>
        {:else if open?.id === it.id && open.kind === "never"}
          <div class="write">
            <p>Never allow <b>{it.title}</b>? It goes on the deleted list and won't be offered again.</p>
            <div class="buttons">
              <button class="danger" onclick={() => decide(it, "never")} disabled={busy}>Never allow</button>
              <button class="quiet" onclick={() => { open = null; }}>Cancel</button>
            </div>
          </div>
        {/if}
      </div>
      <div class="actions">
        <button class="quiet" onclick={() => listen(it)}>▶ Listen and play</button>
        {#if it.live}
          <button class="quiet" onclick={() => app.openPiece(it.live!, "config/review")}>▶ Live version</button>
          <button class="approve" onclick={() => decide(it, "approve")} disabled={busy}>Approve update</button>
          <button class="quiet" onclick={() => start(it, "improve")} disabled={busy}>Needs more work</button>
          <button class="quiet never" onclick={() => decide(it, "discard")} disabled={busy}>Discard update</button>
        {:else}
          <button class="approve" onclick={() => decide(it, "approve")} disabled={busy}>Approve</button>
          <button class="quiet" onclick={() => start(it, "improve")} disabled={busy}>Needs improvement</button>
          <button class="quiet never" onclick={() => start(it, "never")} disabled={busy}>Never allow</button>
        {/if}
      </div>
    </div>
  {:else}
    {#if loaded && !error}
      <p class="muted">Nothing waiting. Songs the Claude skills submit appear here for your approval; nothing reaches the children before that.</p>
    {/if}
  {/each}
</section>

{#if sentBack.length}
  <section class="panel">
    <h2>Sent back for changes ({sentBack.length})</h2>
    <p class="muted">Waiting for the Claude skills to fix these. Each comes back to the list above, with your note beside it.</p>
    {#each sentBack as it (it.id)}
      <div class="item">
        <div class="what">
          <span class="title">{it.title}</span>
          {#if it.live}<span class="badge">Live song: the children keep playing it</span>{/if}
          <span class="muted">· {it.live ? "asked" : "sent back"} {when(it.decidedAt)}</span>
          <p class="changed">“{it.feedback}”</p>
        </div>
        <div class="actions">
          {#if it.live}
            <button class="quiet" onclick={() => app.openPiece(it.live!, "config/review")}>▶ Play it</button>
            <button class="quiet never" onclick={() => decide(it, "discard")} disabled={busy}>Cancel request</button>
          {:else}
            <button class="quiet" onclick={() => listen(it)}>▶ Listen again</button>
          {/if}
        </div>
      </div>
    {/each}
  </section>
{/if}

{#if deleted.length}
  <section class="panel">
    <h2>Deleted songs ({deleted.length})</h2>
    <p class="muted">Songs you never allowed here, or deleted from the library in Songs and genres. The skills won't offer
      them again. Send one back to review, send it for improvement to have it corrected, or forget it, which removes it
      and lets the skills offer it again some day.</p>
    {#each deleted as it (it.id)}
      <div class="item">
        <div class="what">
          <span class="title">{it.title}</span>
          <span class="muted">· {it.deletedFrom === "library" ? "deleted from the library" : "never allowed"} {when(it.decidedAt)}{it.deletedReason ? ` · ${it.deletedReason}` : ""}</span>
          {#if open?.id === it.id && open.kind === "improve"}
            <div class="write">
              <label for="fb-{it.id}">What needs to change? The skills read this, fix the song and send it to the list above.</label>
              <textarea id="fb-{it.id}" bind:value={feedback} rows="3" maxlength="4000"></textarea>
              <div class="buttons">
                <button onclick={() => decide(it, "improve")} disabled={busy || feedback.trim().length < 3}>Send for improvement</button>
                <button class="quiet" onclick={() => { open = null; }}>Cancel</button>
              </div>
            </div>
          {:else if forgetting === it.id}
            <div class="write">
              <p>Forget <b>{it.title}</b>? Its files and record are removed, and the skills may offer it again.</p>
              <div class="buttons">
                <button class="danger" onclick={() => { forgetting = null; void decide(it, "forget"); }} disabled={busy}>Forget it</button>
                <button class="quiet" onclick={() => { forgetting = null; }}>Cancel</button>
              </div>
            </div>
          {/if}
        </div>
        <div class="actions">
          {#if it.hasFiles}
            <button class="quiet" onclick={() => listen(it)}>▶ Listen</button>
            <button class="quiet" onclick={() => decide(it, "restore")} disabled={busy}>Back to review</button>
            <button class="quiet" onclick={() => start(it, "improve")} disabled={busy}>Needs improvement</button>
          {/if}
          <button class="quiet never" onclick={() => { forgetting = it.id; }} disabled={busy}>Forget</button>
        </div>
      </div>
    {/each}
  </section>
{/if}

<style>
  .item { display: flex; gap: 16px; padding: 14px 0; border-top: 1px solid var(--line); flex-wrap: wrap; }
  .what { flex: 1 1 420px; min-width: 0; }
  .actions { display: flex; flex-direction: column; gap: 8px; flex: 0 0 210px; }
  .actions button { width: 100%; }
  .approve { background: #2f7d4f; color: #fff; }
  .never { color: var(--wrong); }
  .danger { background: var(--wrong); color: #fff; }
  .title-row { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
  .title { font-size: 19px; font-weight: 700; }
  .line { margin: 4px 0; }
  .ok { color: #2f7d4f; }
  .warn { color: #8a5a00; }
  .badge { font-size: 14px; font-weight: 700; color: #fff; background: var(--accent); border-radius: 8px; padding: 2px 8px; }
  .changed { margin: 6px 0; padding: 6px 10px; background: #eef3fd; border-radius: 10px; }
  .flags { margin: 4px 0; padding-left: 20px; color: #8a5a00; }
  .lyrics { white-space: pre-wrap; font: inherit; background: #f7f5f0; border-radius: 10px; padding: 8px 12px; }
  .write { margin-top: 10px; padding: 10px 12px; background: #f7f5f0; border-radius: 12px; }
  .write label { display: block; font-weight: 650; margin-bottom: 6px; }
  .write textarea { width: 100%; box-sizing: border-box; font: inherit; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); }
  .buttons { display: flex; gap: 10px; margin-top: 8px; }
</style>
