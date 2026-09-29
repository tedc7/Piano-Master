<script lang="ts">
  // Parent > App status: versions, the piano server's health, the outbox, and recent problems
  // from the client log (arch §11.3).
  import { onMount } from "svelte";
  import { api, CLIENT_VERSION } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";
  import { loadContent } from "../../lib/content";

  interface LogRow { time: string; level: string; message: string; deviceId?: string }

  let health = $state<{ ok: boolean; version: string; schema: number; contentVersion: string | null } | null>(null);
  let healthError = $state("");
  let contentVersion = $state("");
  let problems = $state<LogRow[] | null>(null);
  let pending = $state(api.pending);

  onMount(() => {
    const off = api.onChange(() => { pending = api.pending; });
    void (async () => {
      try {
        const r = await fetch("/api/health");
        health = await r.json();
      } catch (e) { healthError = (e as Error).message; }
      try { contentVersion = (await loadContent()).version; } catch { /* shown as unknown */ }
      try {
        const r = await fetch("/api/logs?level=error&limit=10");
        if (r.ok) problems = (await r.json()).logs ?? [];
      } catch { /* shown as unknown */ }
    })();
    return off;
  });
</script>

<div class="cols">
  <section class="panel">
    <h2>Versions</h2>
    <div class="grid">
      <span>App</span><b>{CLIENT_VERSION}</b>
      <span>Content</span><b>{contentVersion || "unknown"}{health && health.contentVersion !== contentVersion ? ` · the server plans from ${health.contentVersion ?? "no content"}` : ""}</b>
      <span>Piano server</span>
      <b>{health ? `${health.ok ? "✓ running" : "problem"} · API ${health.version} · database ${health.schema}` : healthError ? `not reachable (${healthError})` : "checking…"}</b>
      <span>This device</span><span class="mono">{api.deviceId}</span>
      <span>Plays to send</span><b>{pending}{pending ? " (sent when the server is reachable)" : ""}</b>
      <span>Full screen</span><b>{app.isIPad ? (app.needsFullScreen ? "off" : "on") : "not an iPad"}</b>
    </div>
    <p><a href="/api/" target="_blank" rel="noopener">Open the API status page</a></p>
  </section>
  <section class="panel">
    <h2>Recent problems</h2>
    {#if problems === null}
      <p class="muted">Not available.</p>
    {:else if !problems.length}
      <p class="muted">No errors logged.</p>
    {:else}
      {#each problems as p, i (i)}
        <div class="problem"><span class="muted small">{new Date(p.time).toLocaleString()}</span><div>{p.message}</div></div>
      {/each}
    {/if}
  </section>
</div>

<style>
  .cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 14px; }
  .grid { display: grid; grid-template-columns: 140px 1fr; gap: 8px 14px; margin: 10px 0; }
  .mono { font: 13px ui-monospace, Menlo, monospace; word-break: break-all; }
  .problem { border-top: 1px solid var(--line); padding: 6px 0; }
  .small { font-size: 13px; }
</style>
