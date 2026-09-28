<script lang="ts">
  import { onMount } from "svelte";
  import Config from "./screens/Config.svelte";
  import Journey from "./screens/Journey.svelte";
  import Lesson from "./screens/Lesson.svelte";
  import Library from "./screens/Library.svelte";
  import Picker from "./screens/Picker.svelte";
  import Pin from "./screens/Pin.svelte";
  import Play from "./screens/Play.svelte";
  import Progress from "./screens/Progress.svelte";
  import Session from "./screens/Session.svelte";
  import { api } from "./lib/api";
  import { app } from "./lib/app.svelte.js";
  import { go, parse, type Route } from "./lib/route";

  let route = $state(parse(location.hash));

  // Who may see what: a student's own screens need a student; the map, songs and lessons need
  // a student or the parent; Config needs the parent. Without a player (a reload, a bookmark)
  // the app starts at the picker. The Play screen opens for anyone (the browser check uses it).
  const studentOnly = new Set(["session", "progress"]);
  const anyPlayer = new Set(["journey", "library", "lesson"]);

  function allowed(r: Route): string | null {
    if (studentOnly.has(r.screen) && !app.student) return app.parentMode ? "config" : "";
    if (anyPlayer.has(r.screen) && !app.student && !app.parentMode) return "";
    if (r.screen === "config" && !app.parentMode) return "pin";
    return null;
  }

  onMount(() => {
    const onHash = () => {
      const r = parse(location.hash);
      const redirect = allowed(r);
      if (redirect !== null) { go(redirect); return; }
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
{:else if route.screen === "pin"}
  <Pin />
{:else if route.screen === "config"}
  <Config page={route.page} />
{:else}
  <Picker />
{/if}
