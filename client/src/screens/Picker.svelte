<script lang="ts">
  // Student picker (arch §3 screen 1): one large card per child, and a small Parent button that
  // asks for the PIN. The students are placeholders until the server holds them (M4).
  import Status from "../components/Status.svelte";
  import { app, SAMPLE_STUDENTS } from "../lib/app.svelte.js";
  import { go } from "../lib/route";
</script>

<div class="screen">
  <Status title="Piano Master" />
  <main class="body">
    {#if app.needsFullScreen}
      <p class="notice">Turn on full screen in MIDIWeb Browser to hide the address bar.</p>
    {/if}
    <h1>Who's playing?</h1>
    <div class="students">
      {#each SAMPLE_STUDENTS as s (s.id)}
        <button class="student" onclick={() => app.chooseStudent(s)}>
          <span class="avatar">{s.avatar}</span>
          <span class="name">{s.name}</span>
        </button>
      {/each}
    </div>
    <p class="muted">Placeholder players <span class="sample">sample</span> — the parent adds the real students in Parent mode once they are stored on the piano server (M4).</p>
  </main>
  <footer class="foot">
    <button class="quiet" onclick={() => go("parent")}>{app.parentMode ? "Parent ✓" : "Parent"}</button>
  </footer>
</div>

<style>
  .students { display: flex; flex-wrap: wrap; gap: 24px; margin: 10px 0 24px; }
  .student {
    display: flex; flex-direction: column; align-items: center; gap: 10px;
    width: 220px; padding: 26px 12px 20px; border-radius: 24px;
    background: var(--panel); color: var(--fg); border: 2px solid var(--line);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
  }
  .avatar { font-size: 84px; line-height: 1; }
  .name { font-size: 24px; font-weight: 750; }
  .foot { display: flex; justify-content: flex-end; padding: 10px 16px; }
</style>
