<script lang="ts">
  // Bottom navigation. It sits at the bottom because the top of the screen ignores taps in full
  // screen (arch §3). Students get their practice, map, songs and progress; the parent (a player
  // of their own, after the PIN) gets the map, songs and Config.
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";

  type Tab = "session" | "journey" | "library" | "progress" | "config";
  let { current }: { current: Tab } = $props();
  const STUDENT: { id: Tab; label: string; icon: string }[] = [
    { id: "session", label: "Today's Practice", icon: "▶️" },
    { id: "journey", label: "Journey", icon: "🗺️" },
    { id: "library", label: "Songs", icon: "🎵" },
    { id: "progress", label: "My Progress", icon: "⭐" },
  ];
  const PARENT: { id: Tab; label: string; icon: string }[] = [
    { id: "journey", label: "Journey", icon: "🗺️" },
    { id: "library", label: "Songs", icon: "🎵" },
    { id: "config", label: "Config", icon: "⚙️" },
  ];
  const tabs = $derived(app.parentMode ? PARENT : STUDENT);
</script>

<nav class="tabbar">
  {#each tabs as t (t.id)}
    <button class="tab" class:sel={current === t.id} onclick={() => go(t.id)}>
      <span class="icon">{t.icon}</span><span>{t.label}</span>
      {#if t.id === "progress" && (app.rewards?.unseen ?? 0) > 0}
        <span class="new" aria-label="{app.rewards?.unseen} new medals">{app.rewards?.unseen}</span>
      {/if}
    </button>
  {/each}
  <span class="spacer"></span>
  <button class="quiet small" onclick={() => app.switchPlayer()}>Switch player</button>
</nav>

<style>
  .tabbar {
    flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 8px 14px;
    background: var(--panel); border-top: 1px solid var(--line);
  }
  .tab { position: relative; display: flex; align-items: center; gap: 8px; background: transparent; color: var(--fg); min-width: 120px; min-height: 56px; }
  .tab.sel { background: #eef3fd; color: var(--accent); box-shadow: inset 0 0 0 2px #cfdcf6; }
  .icon { font-size: 22px; }
  .spacer { flex: 1; }
  .new { min-width: 24px; height: 24px; border-radius: 999px; background: #d19a12; color: #fff; font-size: 14px; font-weight: 800;
         display: grid; place-items: center; padding: 0 6px; }
  .small { font-size: 15px; font-weight: 600; }
</style>
