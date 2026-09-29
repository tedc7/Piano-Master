<script lang="ts">
  // My Progress (arch §3 screen 8, §8.11): the student's own report in kid-friendly words, from
  // the same data the parent sees.
  import ProgressReport from "../components/ProgressReport.svelte";
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
</script>

<div class="screen">
  <Status title="My Progress" />
  <main class="body">
    {#if app.student}
      {#key app.student.id}<ProgressReport studentId={app.student.id} />{/key}
    {/if}
  </main>
  <TabBar current="progress" />
</div>
