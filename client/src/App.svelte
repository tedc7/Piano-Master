<script lang="ts">
  import { onMount } from "svelte";
  import Home from "./screens/Home.svelte";
  import Play from "./screens/Play.svelte";
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
