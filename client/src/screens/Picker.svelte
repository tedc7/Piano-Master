<script lang="ts">
  // Player picker (arch §3 screen 1): one large card per child, and the parent, who is a player
  // of their own behind the PIN. The parent adds the students under Config > Students.
  import { onMount } from "svelte";
  import Status from "../components/Status.svelte";
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";

  onMount(() => { void app.loadStudents(); });
</script>

<div class="screen">
  <Status title="Piano Master" />
  <main class="body">
    {#if app.needsFullScreen}
      <p class="notice">Turn on full screen in MIDIWeb Browser to hide the address bar.</p>
    {/if}
    <h1>Who's playing?</h1>
    <div class="students">
      {#each app.students as s (s.id)}
        <button class="student" onclick={() => app.chooseStudent(s)}>
          <span class="avatar">{s.avatar}</span>
          <span class="name">{s.name}</span>
        </button>
      {/each}
      <button class="student parent" onclick={() => go("pin")}>
        <span class="avatar">🔑</span>
        <span class="name">Parent</span>
      </button>
    </div>
    {#if app.studentsStatus === "offline"}
      <p class="notice error">Can't reach the piano server{app.students.length ? "; these are the players from last time" : ""}.</p>
    {:else if app.studentsStatus === "ok" && !app.students.length}
      <p class="notice">No players yet. A parent adds them: tap <b>Parent</b>, then <b>Students</b>.</p>
    {/if}
  </main>
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
  .parent { border-style: dashed; background: #fffaf0; }
</style>
