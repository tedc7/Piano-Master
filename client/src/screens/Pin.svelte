<script lang="ts">
  // The parent's PIN (arch §3 "Parent mode", §11.1), checked by the piano server: 5 wrong tries
  // lock parent login for 5 minutes, doubling with each further lockout. On a new piano server
  // the parent first chooses a PIN (4 to 8 digits, entered twice).
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import { ApiError } from "../lib/api";
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";

  let pin = $state("");
  let first = $state<string | null>(null);     // choosing a PIN: the first entry, waiting for the repeat
  let message = $state("");
  let busy = $state(false);

  onMount(() => { if (app.pinSet === null) void app.loadStudents(); });

  const choosing = $derived(app.pinSet === false);
  const title = $derived(!choosing ? "🔑 Parent PIN" : first === null ? "🔑 Choose a parent PIN" : "🔑 Enter it again");

  function digit(d: string): void {
    message = "";
    if (pin.length < 8) pin += d;
  }

  async function ok(): Promise<void> {
    if (pin.length < 4 || busy) return;
    const entered = pin;
    pin = "";
    if (choosing && first === null) {
      first = entered;
      return;
    }
    if (choosing && first !== entered) {
      first = null;
      message = "Those two didn't match. Choose a PIN again.";
      return;
    }
    busy = true;
    try {
      if (choosing) await app.setFirstPin(entered); else await app.enterParent(entered);
    } catch (e) {
      message = reason(e);
    } finally {
      busy = false;
    }
  }

  function reason(e: unknown): string {
    if (!(e instanceof ApiError)) return "Can't reach the piano server.";
    const d = e.detail as { triesLeft?: number; lockedUntil?: string } | null;
    if (e.status === 401) return `That PIN didn't work. ${d?.triesLeft ?? ""} ${d?.triesLeft === 1 ? "try" : "tries"} left before a short lock.`;
    if (e.status === 423 && d?.lockedUntil) {
      const t = new Date(d.lockedUntil).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
      return `Too many wrong PINs. Parent login opens again at ${t}.`;
    }
    if (e.status === 409) { app.pinSet = false; return "Choose a parent PIN first."; }
    return e.message;
  }
</script>

<div class="screen">
  <Status title="Parent" />
  <main class="body pin-body">
    <div class="pin">
      <h1>{title}</h1>
      <div class="dots">{#each Array(Math.max(4, pin.length)) as _, i}<span class:on={i < pin.length}></span>{/each}</div>
      {#if message}<p class="bad">{message}</p>{/if}
      <div class="pad">
        {#each ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as d}<button class="quiet" onclick={() => digit(d)}>{d}</button>{/each}
        <button class="quiet" onclick={() => { pin = pin.slice(0, -1); }} aria-label="Delete">⌫</button>
        <button class="quiet" onclick={() => digit("0")}>0</button>
        <button class="okbtn" disabled={pin.length < 4 || busy} onclick={ok}>OK</button>
      </div>
      <button class="quiet cancel" onclick={() => go("")}>Cancel</button>
      {#if choosing}<p class="muted small">4 to 8 digits. The piano server keeps only a scrambled copy of it.</p>{/if}
    </div>
  </main>
</div>

<style>
  .pin-body { display: flex; justify-content: center; }
  .pin { width: 340px; text-align: center; }
  .dots { display: flex; gap: 16px; justify-content: center; margin: 8px 0 16px; }
  .dots span { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--muted); }
  .dots span.on { background: var(--fg); border-color: var(--fg); }
  .bad { color: var(--wrong); font-weight: 650; }
  .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .pad button { min-height: 68px; font-size: 26px; }
  .okbtn { font-size: 22px !important; }
  .cancel { margin-top: 14px; font-size: 17px; }
  .small { font-size: 14px; }
</style>
