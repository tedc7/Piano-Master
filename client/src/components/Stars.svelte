<script lang="ts">
  // A row of 5 stars in half-star steps (arch §3 "Journey map star display", §7.6).
  let { value, label, size = 30, compact = false }: { value: number | null; label: string; size?: number; compact?: boolean } = $props();
  const fill = (i: number) => (value === null ? 0 : Math.max(0, Math.min(1, value - i)));
</script>

<div class="row" class:compact aria-label={value === null ? `${label}: not shown` : `${label}: ${value} of 5 stars`}>
  <span class="label">{label}</span>
  {#if value === null}
    <span class="none" style:font-size="{size * 0.8}px">–</span>
  {:else}
    {#each [0, 1, 2, 3, 4] as i}
      <span class="star" style:font-size="{size}px">
        <span class="bg">★</span>
        <span class="fg" style:width="{fill(i) * 100}%">★</span>
      </span>
    {/each}
  {/if}
</div>

<style>
  .row { display: flex; align-items: center; gap: 4px; justify-content: center; }
  .label { min-width: 90px; text-align: right; margin-right: 10px; color: var(--muted); font-weight: 600; }
  .star { position: relative; display: inline-block; line-height: 1; }
  .bg { color: #e3e0d6; }
  .fg { position: absolute; left: 0; top: 0; overflow: hidden; color: #f2b01e; white-space: nowrap; }
  .none { color: var(--muted); min-width: 170px; text-align: left; }
  .compact { gap: 1px; }
  .compact .label { min-width: 0; margin-right: 4px; }
  .compact .none { min-width: 0; }
</style>
