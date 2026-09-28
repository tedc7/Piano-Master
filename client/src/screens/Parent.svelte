<script lang="ts">
  // Parent mode (arch §3 "Parent mode", §10.1): a PIN pad, then the Parental Controls hub and its
  // pages. Built so far: the piano check, device settings, app status and the content preview;
  // the rest are placeholders that say what they will do and in which milestone.
  import Status from "../components/Status.svelte";
  import { app, PARENT_IDLE_MS } from "../lib/app.svelte.js";
  import { go } from "../lib/route";
  import AppStatus from "./parent/AppStatus.svelte";
  import ContentPreview from "./parent/ContentPreview.svelte";
  import DevicePage from "./parent/DevicePage.svelte";
  import MidiTest from "./parent/MidiTest.svelte";

  let { page }: { page: string | null } = $props();

  interface Tile { id: string; icon: string; name: string; what: string; milestone?: string; to?: string }
  const GROUPS: { name: string; tiles: Tile[] }[] = [
    { name: "Family", tiles: [
      { id: "students", icon: "👧", name: "Students", what: "Add, edit, archive or delete students; avatars; per-student settings such as hints, auto-rewind and default tempo.", milestone: "M4" },
      { id: "rules", icon: "🛡️", name: "Songs and genres", what: "Allow or block genres and single songs for each child. Lesson pieces are always allowed; other genres start blocked.", milestone: "M7" },
      { id: "reports", icon: "📈", name: "Progress reports", what: "Each child's skills, star trends, practice days, stuck skills and what the app suggests next.", milestone: "M4–M7" },
    ] },
    { name: "Songs and lessons", tiles: [
      { id: "content", icon: "📚", name: "Content preview", what: "Every skill and song in sequence order, open for review." },
      { id: "journey", icon: "🗺️", name: "Journey map", what: "The children's map, with every bubble open in parent mode.", to: "journey" },
      { id: "library", icon: "🎵", name: "Song library", what: "The children's song library, with every song open in parent mode.", to: "library" },
      { id: "review", icon: "📥", name: "Review list", what: "Songs and media staged by the Claude skills, waiting for approval. Nothing staged reaches a child.", milestone: "M7" },
      { id: "requests", icon: "📝", name: "Work requests", what: "Ask the Claude skills on the dev box to find songs, import a file, change a vocal style or find a concept video.", milestone: "M7" },
      { id: "videos", icon: "🎬", name: "Concept videos", what: "Upcoming concepts for each child, with a suggested search, and the approved videos.", milestone: "M8" },
      { id: "analysis", icon: "🔎", name: "Content and analysis", what: "Load content, re-run song analysis, the coverage report (skills with fewer than 3 ready pieces) and the content runway.", milestone: "M3" },
    ] },
    { name: "This device", tiles: [
      { id: "midi", icon: "🎹", name: "Piano check", what: "Keys, chords, velocity, pedal and MIDI delay (the device qualification test)." },
      { id: "calibrate", icon: "⏱", name: "Latency calibration", what: "The app plays 24 clicks and you tap one key in time; it sets the latency offset from the average and checks the spread is under about 20 ms.", milestone: "M0" },
      { id: "device", icon: "⚙️", name: "Device settings", what: "Display and latency offsets, auto-rewind, backing volume and the piano input." },
      { id: "status", icon: "🩺", name: "App status", what: "Versions, the piano server, plays waiting to send, and recent problems." },
    ] },
    { name: "Settings", tiles: [
      { id: "pin", icon: "🔑", name: "PIN and log out", what: "Change the parent PIN (checked by the server, with lockout after failed tries) and the auto-logout time.", milestone: "M4" },
      { id: "ai", icon: "🤖", name: "AI settings", what: "Turn the optional AI advisor on or off.", milestone: "M9" },
    ] },
  ];
  const BUILT: Record<string, true> = { content: true, journey: true, library: true, midi: true, device: true, status: true };
  const tile = $derived(page ? GROUPS.flatMap((g) => g.tiles).find((t) => t.id === page) ?? null : null);

  let pin = $state("");
  let wrong = $state(false);
  function digit(d: string): void {
    wrong = false;
    pin = (pin + d).slice(0, 4);
    if (pin.length === 4) {
      if (!app.enterParent(pin)) wrong = true;
      pin = "";
    }
  }
  function leave(): void {
    app.leaveParent();
    go(app.student ? "home" : "");
  }
</script>

<div class="screen">
  <Status title={tile ? `Parent · ${tile.name}` : "Parent"} />

  {#if !app.parentMode}
    <main class="body pin-body">
      <div class="pin">
        <h1>Parent PIN</h1>
        <div class="dots">{#each [0, 1, 2, 3] as i}<span class:on={i < pin.length}></span>{/each}</div>
        {#if wrong}<p class="bad">That PIN didn't work.</p>{/if}
        <div class="pad">
          {#each ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as d}<button class="quiet" onclick={() => digit(d)}>{d}</button>{/each}
          <button class="quiet" onclick={() => go(app.student ? "home" : "")}>Cancel</button>
          <button class="quiet" onclick={() => digit("0")}>0</button>
          <button class="quiet" onclick={() => { pin = pin.slice(0, -1); }} aria-label="Delete">⌫</button>
        </div>
        <p class="muted small"><span class="sample">placeholder</span> Any 4 digits open parent mode until the piano server checks the PIN (M4).</p>
      </div>
    </main>
  {:else}
    <main class="body">
      <div class="bar">
        {#if page}<button class="quiet" onclick={() => go("parent")}>‹ Parent</button>{/if}
        <span class="spacer"></span>
        <span class="muted small">Logs out after {PARENT_IDLE_MS / 60000} minutes without a touch.</span>
        <button class="quiet" onclick={leave}>Log out</button>
      </div>

      {#if !page}
        {#each GROUPS as g (g.name)}
          <h2 class="group">{g.name}</h2>
          <div class="tiles">
            {#each g.tiles as t (t.id)}
              <button class="tile" class:todo={!BUILT[t.id]} onclick={() => go(t.to ?? `parent/${t.id}`)}>
                <span class="tile-head"><span class="tile-icon">{t.icon}</span><span class="tile-name">{t.name}</span></span>
                <span class="tile-what">{t.what}</span>
                {#if !BUILT[t.id]}<span class="soon">Coming in {t.milestone}</span>{/if}
              </button>
            {/each}
          </div>
        {/each}
      {:else if page === "midi"}
        <MidiTest />
      {:else if page === "device"}
        <DevicePage />
      {:else if page === "status"}
        <AppStatus />
      {:else if page === "content"}
        <ContentPreview />
      {:else if tile}
        <div class="panel placeholder">
          <p class="big">{tile.icon}</p>
          <h1>{tile.name}</h1>
          <p>{tile.what}</p>
          <p class="soon">Placeholder page · coming in {tile.milestone}</p>
        </div>
      {:else}
        <p class="notice">No such page.</p>
      {/if}
    </main>
  {/if}
</div>

<style>
  .pin-body { display: flex; justify-content: center; }
  .pin { width: 340px; text-align: center; }
  .dots { display: flex; gap: 16px; justify-content: center; margin: 8px 0 16px; }
  .dots span { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--muted); }
  .dots span.on { background: var(--fg); border-color: var(--fg); }
  .bad { color: var(--wrong); font-weight: 650; }
  .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .pad button { min-height: 68px; font-size: 26px; }
  .pad button:nth-child(10) { font-size: 17px; }
  .small { font-size: 14px; }
  .bar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .spacer { flex: 1; }
  .group { margin: 18px 0 10px !important; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 12px; }
  .tile {
    display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left;
    background: var(--panel); color: var(--fg); border: 1px solid var(--line); padding: 14px 16px; border-radius: 16px;
  }
  .tile.todo { background: #f7f6f2; }
  .tile-head { display: flex; align-items: center; gap: 10px; }
  .tile-icon { font-size: 26px; }
  .tile-name { font-size: 19px; font-weight: 750; }
  .tile-what { font-size: 14px; font-weight: 500; color: var(--muted); }
  .soon { font-size: 13px; font-weight: 700; color: #8a5a00; }
  .placeholder { max-width: 640px; margin: 0 auto; text-align: center; }
  .placeholder .big { font-size: 56px; margin: 0; }
</style>
