<script lang="ts">
  // Parent > Students (arch §3 "Parent mode", §5 Student): add, edit, archive and delete
  // students, and each student's settings. The Play screen's choices (vocals and tempo for each song,
  // the metronome for every song) are remembered as the student plays; the parent can clear them.
  import { onMount } from "svelte";
  import PlayerSettings from "../../components/PlayerSettings.svelte";
  import { api } from "../../lib/api";
  import { app, AVATARS, type Student } from "../../lib/app.svelte.js";
  import { withDefaults, type StudentSettings } from "../../lib/settings";

  let list = $state<Student[]>([]);
  let error = $state("");
  let editing = $state<string | null>(null);          // student id, or "new"
  let name = $state("");
  let avatar = $state(AVATARS[0]);
  let confirmDelete = $state<string | null>(null);

  onMount(load);

  async function load(): Promise<void> {
    try {
      const r = await api.request<{ students: Student[] }>("/students?all=true");
      list = r.students.map((s) => ({ ...s, settings: withDefaults(s.settings) }));
      error = "";
    } catch (e) {
      if (!app.parentRefused(e)) error = `Can't reach the piano server (${(e as Error).message}).`;
    }
  }

  async function call(path: string, method: string, body?: unknown): Promise<void> {
    try {
      await api.request(path, method, body);
      await load();
      void app.loadStudents();
    } catch (e) {
      if (!app.parentRefused(e)) error = (e as Error).message;
    }
  }

  function startEdit(s: Student | null): void {
    editing = s ? s.id : "new";
    name = s?.name ?? "";
    avatar = s?.avatar ?? AVATARS[list.length % AVATARS.length];
  }

  async function save(): Promise<void> {
    if (!name.trim()) return;
    if (editing === "new") await call("/students", "POST", { name: name.trim(), avatar });
    else await call(`/students/${editing}`, "PATCH", { name: name.trim(), avatar });
    editing = null;
  }

  const setSettings = (s: Student, p: Partial<StudentSettings>) => call(`/students/${s.id}`, "PATCH", { settings: p });
  const songChoices = (s: Student) => s.settings.vocalsOff.length + (s.settings.metronome === null ? 0 : 1) + Object.keys(s.settings.presets).length;
</script>

{#if error}<p class="notice error">{error}</p>{/if}

<div class="bar">
  <button onclick={() => startEdit(null)}>＋ Add a student</button>
</div>

{#if editing}
  <section class="panel edit">
    <h2>{editing === "new" ? "New student" : "Edit student"}</h2>
    <label class="field">Name <input bind:value={name} maxlength="40" placeholder="First name" /></label>
    <div class="avatars">
      {#each AVATARS as a (a)}
        <button class="av" class:sel={a === avatar} onclick={() => { avatar = a; }} aria-label="Avatar {a}">{a}</button>
      {/each}
    </div>
    <div class="row">
      <button onclick={save} disabled={!name.trim()}>Save</button>
      <button class="quiet" onclick={() => { editing = null; }}>Cancel</button>
    </div>
  </section>
{/if}

{#each list as s (s.id)}
  <section class="panel student" class:archived={s.status === "archived"}>
    <div class="head">
      <span class="avatar">{s.avatar}</span>
      <div class="who">
        <h2>{s.name}</h2>
        <span class="muted">Since {new Date(`${(s as Student & { startDate?: string }).startDate}T12:00`).toLocaleDateString()}{s.status === "archived" ? " · archived" : ""} · target {s.targetMinutes ?? 15} min a day</span>
      </div>
      <span class="spacer"></span>
      <button class="quiet" onclick={() => startEdit(s)}>Edit</button>
      <button class="quiet" onclick={() => call(`/students/${s.id}`, "PATCH", { status: s.status === "archived" ? "active" : "archived" })}>
        {s.status === "archived" ? "Restore" : "Archive"}
      </button>
      {#if confirmDelete === s.id}
        <button class="danger" onclick={() => { confirmDelete = null; void call(`/students/${s.id}`, "DELETE"); }}>Delete {s.name} and all their progress</button>
        <button class="quiet" onclick={() => { confirmDelete = null; }}>Keep</button>
      {:else}
        <button class="quiet" onclick={() => { confirmDelete = s.id; }}>Delete…</button>
      {/if}
    </div>
    <div class="grid">
      <PlayerSettings settings={s.settings} onchange={(p) => setSettings(s, p)} />
      <span>Song choices</span>
      <span>{songChoices(s)} remembered (vocals and tempo for each song{s.settings.metronome === null ? "" : `; metronome ${s.settings.metronome ? "on" : "off"} for every song`})
        {#if songChoices(s)}<button class="quiet" onclick={() => setSettings(s, { resetSongChoices: true } as never)}>Clear</button>{/if}</span>
    </div>
  </section>
{:else}
  {#if !error}<p class="muted">No students yet. Add each child who will play.</p>{/if}
{/each}

<style>
  .bar { margin-bottom: 12px; }
  .edit { max-width: 720px; }
  .field { display: flex; align-items: center; gap: 12px; font-weight: 650; margin: 10px 0; }
  .field input { font: inherit; font-size: 20px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); flex: 1; }
  .avatars { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 12px; }
  .av { font-size: 34px; width: 64px; height: 64px; padding: 0; background: #f4f2ec; }
  .av.sel { outline: 3px solid var(--accent); background: #eef3fd; }
  .row { display: flex; gap: 10px; }
  .student.archived { opacity: 0.7; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .avatar { font-size: 48px; }
  .who h2 { margin: 0 !important; }
  .spacer { flex: 1; }
  .danger { background: var(--wrong); color: #fff; }
  .grid { display: grid; grid-template-columns: 190px 1fr; gap: 10px 16px; align-items: center; margin-top: 12px; }
</style>
