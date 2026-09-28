<script lang="ts">
  import { onMount } from "svelte";
  import Home from "./screens/Home.svelte";
  import Play from "./screens/Play.svelte";
  import { api } from "./lib/api";
  import { app } from "./lib/app.svelte.js";

  let route = $state(parse(location.hash));

  function parse(hash: string): { screen: "home" } | { screen: "play"; id: string } {
    const m = /^#\/play\/([\w-]+)$/.exec(hash);
    return m ? { screen: "play", id: m[1] } : { screen: "home" };
  }

  onMount(() => {
    const onHash = () => { route = parse(location.hash); };
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
{:else}
  <Home />
{/if}
