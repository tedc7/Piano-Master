<script lang="ts">
  // Config, the parent's Parental Controls hub (arch §3 "Parent mode", §10.1), and its pages.
  // Built so far: students, songs and genres, progress reports, the review list, the PIN, the
  // piano check, device settings, app status and the content preview; the rest are placeholders
  // that say what they will do and in which milestone.
  import Status from "../components/Status.svelte";
  import TabBar from "../components/TabBar.svelte";
  import { app } from "../lib/app.svelte.js";
  import { go } from "../lib/route";
  import AnalysisPage from "./parent/AnalysisPage.svelte";
  import AppStatus from "./parent/AppStatus.svelte";
  import CalibratePage from "./parent/CalibratePage.svelte";
  import DevBoxPage from "./parent/DevBoxPage.svelte";
  import ContentPreview from "./parent/ContentPreview.svelte";
  import DevicePage from "./parent/DevicePage.svelte";
  import MidiTest from "./parent/MidiTest.svelte";
  import PinPage from "./parent/PinPage.svelte";
  import ReportsPage from "./parent/ReportsPage.svelte";
  import ReviewPage from "./parent/ReviewPage.svelte";
  import RulesPage from "./parent/RulesPage.svelte";
  import StudentsPage from "./parent/StudentsPage.svelte";

  let { page }: { page: string | null } = $props();

  interface Tile { id: string; icon: string; name: string; what: string; milestone?: string }
  const GROUPS: { name: string; tiles: Tile[] }[] = [
    { name: "Family", tiles: [
      { id: "students", icon: "👧", name: "Students", what: "Add, edit, archive or delete students; avatars; each student's auto-rewind, rewind distance and backing volume." },
      { id: "rules", icon: "🛡️", name: "Songs and genres", what: "Allow or block genres and single songs for each child, delete songs, and the deleted-songs list. Lesson pieces are always allowed; other genres start blocked." },
      { id: "reports", icon: "📈", name: "Progress reports", what: "Each child's skills, star trends, practice days, stuck skills and the content runway." },
    ] },
    { name: "Songs and lessons", tiles: [
      { id: "content", icon: "📚", name: "Content preview", what: "Every skill and song in sequence order, open for review." },
      { id: "review", icon: "📥", name: "Review list", what: "New songs waiting for you: listen, then approve each, send it back with what needs to change, or never allow it. Nothing here reaches a child." },
      { id: "requests", icon: "📝", name: "Work requests", what: "Ask the Claude skills on the dev box to find songs, import a file, change a vocal style or find a concept video.", milestone: "a later version" },
      { id: "videos", icon: "🎬", name: "Concept videos", what: "Upcoming concepts for each child, with a suggested search, and the approved videos.", milestone: "a later version" },
      { id: "analysis", icon: "🔎", name: "Content and analysis", what: "The coverage report (each skill's core pieces and library songs; every skill needs at least 2 core practice pieces) and each piece's song analysis: required and featured skills, map point, anything beyond the map." },
    ] },
    { name: "This device", tiles: [
      { id: "midi", icon: "🎹", name: "Piano check", what: "Keys, chords, velocity, pedal and MIDI delay (the device qualification test)." },
      { id: "calibrate", icon: "⏱", name: "Latency calibration", what: "The app plays 24 clicks and you tap one key in time; it sets the latency offset from the average and checks the spread is under about 20 ms." },
      { id: "device", icon: "⚙️", name: "Device settings", what: "Display and latency offsets, keyboard size and the piano input." },
      { id: "journey-test", icon: "🗺️", name: "Journey render test", what: "A 200-bubble Journey map that scrolls by itself and reports its frame times (M5)." },
      { id: "status", icon: "🩺", name: "App status", what: "Versions, the piano server, plays waiting to send, and recent problems." },
    ] },
    { name: "Settings", tiles: [
      { id: "devbox", icon: "🔌", name: "Dev box connection", what: "The tokens that let the Claude skills on the dev box submit new songs to the Review list and read your notes. Made once per dev box." },
      { id: "pin", icon: "🔑", name: "PIN and log out", what: "Change the parent PIN (checked by the server, with lockout after failed tries) and the auto-logout time." },
      { id: "ai", icon: "🤖", name: "AI settings", what: "Turn the optional AI advisor on or off.", milestone: "a later version" },
    ] },
  ];
  const BUILT: Record<string, true> = {
    content: true, analysis: true, rules: true, review: true, devbox: true, midi: true, calibrate: true, device: true, status: true, students: true, reports: true, pin: true, "journey-test": true,
  };
  function openTile(id: string): void {
    if (id === "journey-test") go("journey/test"); else go(`config/${id}`);
  }
  const tile = $derived(page ? GROUPS.flatMap((g) => g.tiles).find((t) => t.id === page) ?? null : null);
</script>

<div class="screen">
  <Status title={tile ? `Config · ${tile.name}` : "Config"} />

  <main class="body">
    <div class="bar">
      {#if page}<button class="quiet" onclick={() => go("config")}>‹ Config</button>{/if}
      <span class="spacer"></span>
      <span class="muted small">Switch player logs the parent out; so do {app.autoLogoutMinutes} minutes without a touch.</span>
    </div>

    {#if !page}
      {#each GROUPS as g (g.name)}
        <h2 class="group">{g.name}</h2>
        <div class="tiles">
          {#each g.tiles as t (t.id)}
            <button class="tile" class:todo={!BUILT[t.id]} onclick={() => openTile(t.id)}>
              <span class="tile-head"><span class="tile-icon">{t.icon}</span><span class="tile-name">{t.name}</span></span>
              <span class="tile-what">{t.what}</span>
              {#if !BUILT[t.id]}<span class="soon">Coming in {t.milestone}</span>{/if}
            </button>
          {/each}
        </div>
      {/each}
    {:else if page === "students"}
      <StudentsPage />
    {:else if page === "reports"}
      <ReportsPage />
    {:else if page === "review"}
      <ReviewPage />
    {:else if page === "rules"}
      <RulesPage />
    {:else if page === "devbox"}
      <DevBoxPage />
    {:else if page === "pin"}
      <PinPage />
    {:else if page === "midi"}
      <MidiTest />
    {:else if page === "calibrate"}
      <CalibratePage />
    {:else if page === "device"}
      <DevicePage />
    {:else if page === "status"}
      <AppStatus />
    {:else if page === "analysis"}
      <AnalysisPage />
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

  <TabBar current="config" />
</div>

<style>
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
