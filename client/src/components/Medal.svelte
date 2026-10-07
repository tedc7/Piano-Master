<script lang="ts" module>
  let uid = 0;
</script>

<script lang="ts">
  // A medal (arch §3 "Rewards", M10): a metal disc in its tier with a plain symbol for what it is
  // for. Kept simple and flat on purpose, so it suits an older student as well as a beginner.
  // `tier` null draws the medal not yet earned, in grey.
  import type { AwardKind, Tier } from "../lib/awards";

  let { kind, tier, size = 56, label = "" }: { kind: AwardKind; tier: Tier | null; size?: number; label?: string } = $props();

  const METAL: Record<Tier | "none", [string, string, string]> = {   // light, dark, symbol
    bronze: ["#f0b98a", "#a9622a", "#5b300c"],
    silver: ["#f4f6f8", "#98a2ad", "#38424d"],
    gold: ["#ffe596", "#cf9a12", "#664500"],
    platinum: ["#eef6fb", "#7fa6bf", "#1f4459"],
    none: ["#efeee9", "#d3d1c9", "#b4b2aa"],
  };
  const id = `medal-${uid++}`;
  const m = $derived(METAL[tier ?? "none"]);

  // a five-pointed star around (32, 32)
  function star(r: number, inner: number, cy = 32): string {
    const pts: string[] = [];
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? inner : r;
      pts.push(`${(32 + rr * Math.cos(a)).toFixed(1)},${(cy + rr * Math.sin(a)).toFixed(1)}`);
    }
    return pts.join(" ");
  }
</script>

<svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={label || `${tier ?? "not yet earned"} medal`}>
  <defs>
    <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color={m[0]} />
      <stop offset="1" stop-color={m[1]} />
    </linearGradient>
  </defs>
  <circle cx="32" cy="32" r="30" fill="url(#{id})" />
  <circle cx="32" cy="32" r="25.5" fill="none" stroke="#fff" stroke-opacity={tier ? 0.55 : 0.8} stroke-width="1.6" />
  <g fill={m[2]} stroke={m[2]} stroke-linecap="round" stroke-linejoin="round">
    {#if kind === "stars"}
      <polygon points={star(15, 6.4)} stroke="none" />
    {:else if kind === "fivestar"}
      <polygon points={star(16.5, 7.5, 33)} stroke="none" />
      <text x="32" y="38.2" text-anchor="middle" font-size="12" font-weight="800" fill={m[0]} stroke="none"
            font-family="-apple-system, Segoe UI, Roboto, sans-serif">5</text>
    {:else if kind === "streak"}
      <path d="M32 15c1.5 6 11 10 11 20.5a11 11 0 0 1-22 0c0-5.5 3.2-8.6 5.4-11.6.3 4 2 6.1 4.2 6.6-1-6.2.6-11.4 1.4-15.5z" stroke="none" />
    {:else if kind === "mastered"}
      <polyline points="21,33 29,41 44,24" fill="none" stroke-width="5.5" />
    {:else if kind === "songs"}
      <ellipse cx="27" cy="41" rx="6.5" ry="4.8" transform="rotate(-22 27 41)" stroke="none" />
      <rect x="31.4" y="17" width="3.4" height="24.5" stroke="none" />
      <path d="M34.6 17c4.5 2.2 9.5 5.4 9.5 11.6-1.8-3.4-5.3-5-9.5-5.6z" stroke="none" />
    {:else if kind === "hours"}
      <circle cx="32" cy="32" r="13.5" fill="none" stroke-width="3.6" />
      <polyline points="32,23.5 32,32 38.5,35.5" fill="none" stroke-width="3.6" />
    {:else if kind === "unit"}
      <line x1="24" y1="17" x2="24" y2="47" stroke-width="3.6" />
      <path d="M25.5 18.5h17l-4.4 6.5 4.4 6.5h-17z" stroke="none" />
    {:else}
      <path d="M18.5 41.5l-2.3-17 9.3 7.8L32 20l6.5 12.3 9.3-7.8-2.3 17z" stroke="none" />
      <rect x="18.5" y="43.5" width="27" height="4" rx="1.2" stroke="none" />
    {/if}
  </g>
</svg>

<style>
  svg { flex: 0 0 auto; display: block; }
</style>
