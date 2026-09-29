<script lang="ts">
  // Parent > Device settings: the per-device settings (arch §5 DeviceProfile) in one place.
  import DeviceSettings from "../../components/DeviceSettings.svelte";
</script>

<section class="panel">
  <h2>This device</h2>
  <p class="muted">Kept in this browser, where they are measured, and copied to this device's profile on the piano server. The display offset lines the notes up with the play line (80 ms on the iPad A16); the latency offset is subtracted from key presses before timing is scored, and will be set by the latency calibration. Auto-rewind, rewind distance and backing volume belong to each student (Students).</p>
  <div class="grid"><DeviceSettings /></div>
</section>

<style>
  .grid { display: grid; grid-template-columns: 190px 1fr; gap: 10px 16px; align-items: center; margin-top: 10px; }
</style>
