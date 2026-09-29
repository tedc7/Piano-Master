<script lang="ts">
  // Parent > PIN and log out (arch §11.1): change the parent PIN (the current PIN is needed) and
  // the auto-logout time. A forgotten PIN is cleared on the piano server (README).
  import { api, ApiError } from "../../lib/api";
  import { app } from "../../lib/app.svelte.js";

  let current = $state("");
  let pin = $state("");
  let again = $state("");
  let message = $state("");
  let ok = $state(false);

  const valid = (p: string) => /^\d{4,8}$/.test(p);

  async function change(): Promise<void> {
    ok = false;
    if (!valid(pin)) { message = "A PIN is 4 to 8 digits."; return; }
    if (pin !== again) { message = "The new PIN and its repeat don't match."; return; }
    try {
      await api.request("/parent/pin", "POST", { pin, currentPin: current });
      message = "PIN changed.";
      ok = true;
      current = pin = again = "";
    } catch (e) {
      if (app.parentRefused(e)) return;
      message = e instanceof ApiError && e.status === 403 ? "The current PIN isn't right." : (e as Error).message;
    }
  }

  async function setMinutes(m: number): Promise<void> {
    try {
      const r = await api.request<{ autoLogoutMinutes: number }>("/parent/settings", "PUT", { autoLogoutMinutes: m });
      app.autoLogoutMinutes = r.autoLogoutMinutes;
    } catch (e) {
      app.parentRefused(e);
    }
  }
</script>

<div class="cols">
  <section class="panel">
    <h2>Change the PIN</h2>
    <label class="field">Current PIN <input type="password" inputmode="numeric" maxlength="8" bind:value={current} /></label>
    <label class="field">New PIN <input type="password" inputmode="numeric" maxlength="8" bind:value={pin} /></label>
    <label class="field">New PIN again <input type="password" inputmode="numeric" maxlength="8" bind:value={again} /></label>
    <button onclick={change} disabled={!current || !pin}>Change PIN</button>
    {#if message}<p class:good={ok} class:bad={!ok}>{message}</p>{/if}
    <p class="muted small">5 wrong PINs lock parent login for 5 minutes, doubling each time. Forgot the PIN? Clear it on the piano
      server with <code>python -m app.admin reset-pin</code> in the API container; the app then asks for a new one.</p>
  </section>
  <section class="panel">
    <h2>Log out after</h2>
    <div class="wrap">
      {#each [5, 10, 15, 30] as m (m)}
        <button class="quiet" class:sel={app.autoLogoutMinutes === m} onclick={() => setMinutes(m)}>{m} minutes</button>
      {/each}
    </div>
    <p class="muted small">without a touch. Parent mode also ends when the device sleeps and on Switch player.</p>
  </section>
</div>

<style>
  .cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 14px; }
  .field { display: grid; grid-template-columns: 150px 1fr; align-items: center; gap: 12px; margin: 8px 0; font-weight: 650; }
  .field input { font: inherit; font-size: 20px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--line); }
  .wrap { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
  .sel { outline: 3px solid var(--accent); }
  .good { color: var(--ok); font-weight: 650; }
  .bad { color: var(--wrong); font-weight: 650; }
  .small { font-size: 14px; }
</style>
