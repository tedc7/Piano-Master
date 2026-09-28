<script lang="ts">
  import { onMount } from "svelte";
  import Home from "./screens/Home.svelte";
  import Journey from "./screens/Journey.svelte";
  import Lesson from "./screens/Lesson.svelte";
  import Library from "./screens/Library.svelte";
  import Parent from "./screens/Parent.svelte";
  import Picker from "./screens/Picker.svelte";
  import Play from "./screens/Play.svelte";
  import Progress from "./screens/Progress.svelte";
  import Session from "./screens/Session.svelte";
  import { api } from "./lib/api";
  import { app } from "./lib/app.svelte.js";
  import { go, parse } from "./lib/route";

  let route = $state(parse(location.hash));

  // student screens need a player; without one (a reload, or a bookmark) start at the picker
  const needsStudent = new Set(["home", "session", "journey", "library", "progress"]);

  onMount(() => {
    const onHash = () => {
      const r = parse(location.hash);
      if (needsStudent.has(r.screen) && !app.student && !app.parentMode) { go(""); return; }
      route = r;
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    void app.midi.start();
    void api.start();
    // client errors go to the server's client log (arch §11.3)
    window.addEventListener("error", (e) => api.log("error", e.message, { source: e.filename, line: e.lineno }));
    window.addEventListener("unhandledrejection", (e) => api.log("error", String(e.reason)));
    return () => window.removeEventListener("hashchange", onHash);
  });
</script>

{#if route.screen === "play"}
  {#key route.id}
    <Play id={route.id} />
  {/key}
{:else if route.screen === "home"}
  <Home />
{:else if route.screen === "session"}
  <Session />
{:else if route.screen === "journey"}
  <Journey />
{:else if route.screen === "lesson"}
  {#key route.skillId}
    <Lesson skillId={route.skillId} />
  {/key}
{:else if route.screen === "library"}
  <Library />
{:else if route.screen === "progress"}
  <Progress />
{:else if route.screen === "parent"}
  <Parent page={route.page} />
{:else}
  <Picker />
{/if}
