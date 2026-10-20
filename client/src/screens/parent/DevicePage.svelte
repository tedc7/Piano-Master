<script lang="ts">
  // Parent > Device settings: the per-device settings (arch §5 DeviceProfile) in one place.
  import DeviceSettings from "../../components/DeviceSettings.svelte";
  import { app } from "../../lib/app.svelte.js";
</script>

<section class="panel">
  <h2>This device</h2>
  <p class="muted">Kept in this browser, where they are measured, and copied to this device's profile on the piano server. The app hears the piano over MIDI, or through the microphone until a MIDI piano is used. The display offset lines the notes up with the play line (80 ms on the iPad A16); the latency offset is subtracted from key presses before timing is scored, and is set by the latency calibration (MIDI and the microphone each keep their own). Auto-rewind, rewind distance and backing volume belong to each student (Students).</p>
  <div class="grid"><DeviceSettings /></div>
</section>

{#if app.micMode}
  <section class="panel">
    <h2>Listening with the microphone</h2>
    <p class="muted">A stand-in until the MIDI piano arrives. The app hears each key through the microphone, so it works with a keyboard that has no MIDI, but it is easily confused by other sounds. For the best results:</p>
    <ul>
      <li>Put the iPad on the keyboard's music stand, close to its speakers, with the keyboard's volume at a medium-loud level and a plain piano sound (no echo or chorus effects).</li>
      <li>Keep the room quiet while a child plays: no TV or music, and no talking or singing along. A voice can be heard as keys. A sound the app isn't sure of can count as a right key, never as a wrong one.</li>
      <li>The vocals and backing play as usual: the app takes its own sound out of what the microphone hears, and counts only keys well above it. If keys nobody played show up while the music plays, turn on "No vocals or backing in Play mode" (Listen mode still plays everything). Use the iPad's own speakers: Bluetooth speakers add too much delay for the app to match its own sound.</li>
      <li>Run the <b>Latency calibration</b> once with the microphone: the microphone hears keys later than MIDI does, and keeps its own offset.</li>
      <li>Use the <b>Piano check</b> to see each key as the microphone hears it. If keys are missed, raise the sensitivity; if keys appear that nobody played, lower it.</li>
    </ul>
    <p class="muted">The sustain pedal can't be heard, and loudness is only a guess at how hard a key was played, so the pedal and how hard each key is played are not checked.</p>
  </section>
{/if}

<style>
  .grid { display: grid; grid-template-columns: 190px 1fr; gap: 10px 16px; align-items: center; margin-top: 10px; }
</style>
