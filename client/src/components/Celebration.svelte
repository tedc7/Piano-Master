<script lang="ts">
  // Big moments (arch §3 "Rewards", M10): a unit or level medal, or what a concept lesson earned,
  // shown over whatever screen is open, one at a time; the student taps Continue. Smaller moments
  // (a skill passed in a song, a new best, the stars added) stay on the Play screen's result card.
  import Medal from "./Medal.svelte";
  import { app } from "../lib/app.svelte.js";
  import { TIER_NAME } from "../lib/awards";

  const m = $derived(app.celebrations[0] ?? null);
  const left = $derived(app.celebrations.length);

  function next(): void {
    app.celebrations = app.celebrations.slice(1);
  }
</script>

{#if m}
  {#key m}
    <div class="veil" role="presentation">
      <div class="card" role="dialog" aria-modal="true" aria-label={m.headline}>
        <div class="medal">
          {#if m.kind}
            <Medal kind={m.kind} tier={m.tier} size={120} label="{m.tier ? TIER_NAME[m.tier] : ''} medal" />
          {:else}
            <span class="tick" aria-hidden="true">✓</span>
          {/if}
        </div>
        <p class="headline">{m.headline}</p>
        <h1>{m.title}</h1>
        {#if m.detail}<p class="detail">{m.detail}</p>{/if}
        {#if m.tier}<p class="tier {m.tier}">{TIER_NAME[m.tier]}</p>{/if}
        <button class="go" onclick={next}>{left > 1 ? `Next (${left - 1} more)` : "Continue"}</button>
      </div>
    </div>
  {/key}
{/if}

<style>
  .veil {
    position: fixed; inset: 0; z-index: 50; display: grid; place-items: center;
    background: rgba(31, 31, 36, 0.45); padding: var(--deadzone) 16px 16px;
  }
  .card {
    width: min(440px, 100%); background: var(--panel); border-radius: 24px; padding: 28px 28px 22px;
    text-align: center; box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25); animation: rise 0.35s ease-out;
  }
  .medal { display: flex; justify-content: center; margin-bottom: 10px; animation: turn 0.7s ease-out; }
  .tick { width: 120px; height: 120px; border-radius: 50%; background: var(--ok); color: #fff; font-size: 64px; font-weight: 800;
          display: grid; place-items: center; }
  .headline { margin: 0; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; font-size: 15px; color: var(--accent); }
  h1 { margin: 6px 0 4px !important; font-size: 28px !important; }
  .detail { margin: 0; font-size: 18px; color: var(--muted); }
  .tier { display: inline-block; margin: 10px 0 0; padding: 2px 12px; border-radius: 999px; font-size: 14px; font-weight: 800; }
  .tier.bronze { background: #f6e1cf; color: #7a420f; }
  .tier.silver { background: #e9edf1; color: #3d4650; }
  .tier.gold { background: #fff0c2; color: #6b4a00; }
  .tier.platinum { background: #e2eff7; color: #1f4459; }
  .go { display: block; width: 100%; margin-top: 20px; min-height: 60px; font-size: 20px; border-radius: 16px; }
  @keyframes rise { from { transform: translateY(18px); opacity: 0; } to { transform: none; opacity: 1; } }
  @keyframes turn { from { transform: scale(0.6) rotateY(90deg); } to { transform: none; } }
  @media (prefers-reduced-motion: reduce) { .card, .medal { animation: none; } }
</style>
