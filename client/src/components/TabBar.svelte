<script lang="ts">
  // Bottom navigation for the student screens. It sits at the bottom because the top of the
  // screen ignores taps in full screen (arch §3); Parent is small and asks for the PIN.
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";

  let { current }: { current: "home" | "journey" | "library" | "progress" } = $props();
  const tabs = [
    { id: "home", label: "Home", icon: "🏠" },
    { id: "journey", label: "Journey", icon: "🗺️" },
    { id: "library", label: "Songs", icon: "🎵" },
    { id: "progress", label: "My Progress", icon: "⭐" },
  ] as const;
</script>

<nav class="tabbar">
  {#each tabs as t (t.id)}
    <button class="tab" class:sel={current === t.id} onclick={() => go(t.id)}>
      <span class="icon">{t.icon}</span><span>{t.label}</span>
    </button>
  {/each}
  <span class="spacer"></span>
  {#if app.student}
    <button class="quiet small" onclick={() => go("")}>{app.student.avatar} Switch player</button>
  {/if}
  <button class="quiet small" onclick={() => go("parent")}>{app.parentMode ? "Parent ✓" : "Parent"}</button>
</nav>

<style>
  .tabbar {
    flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 8px 14px;
    background: var(--panel); border-top: 1px solid var(--line);
  }
  .tab { display: flex; align-items: center; gap: 8px; background: transparent; color: var(--fg); min-width: 120px; min-height: 56px; }
  .tab.sel { background: #eef3fd; color: var(--accent); box-shadow: inset 0 0 0 2px #cfdcf6; }
  .icon { font-size: 22px; }
  .spacer { flex: 1; }
  .small { font-size: 15px; font-weight: 600; }
</style>
