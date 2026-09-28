<script lang="ts">
  // The parent's PIN (arch §3 "Parent mode", §11.1). PLACEHOLDER: any 4 digits until the piano
  // server checks the PIN, with lockout after failed tries (M4).
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";

  let pin = $state("");
  let wrong = $state(false);

  function digit(d: string): void {
    wrong = false;
    pin = (pin + d).slice(0, 4);
    if (pin.length === 4) {
      if (!app.enterParent(pin)) wrong = true;
      pin = "";
    }
  }
</script>

<div class="screen">
  <Status title="Parent" />
  <main class="body pin-body">
    <div class="pin">
      <h1>🔑 Parent PIN</h1>
      <div class="dots">{#each [0, 1, 2, 3] as i}<span class:on={i < pin.length}></span>{/each}</div>
      {#if wrong}<p class="bad">That PIN didn't work.</p>{/if}
      <div class="pad">
        {#each ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as d}<button class="quiet" onclick={() => digit(d)}>{d}</button>{/each}
        <button class="quiet cancel" onclick={() => go("")}>Cancel</button>
        <button class="quiet" onclick={() => digit("0")}>0</button>
        <button class="quiet" onclick={() => { pin = pin.slice(0, -1); }} aria-label="Delete">⌫</button>
      </div>
      <p class="muted small"><span class="sample">placeholder</span> Any 4 digits log in until the piano server checks the PIN (M4).</p>
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
  .pad .cancel { font-size: 17px; }
  .small { font-size: 14px; }
</style>
