<script lang="ts">
  // A player's settings (arch §5 Student.settings): auto-rewind, how far the Rewind button goes,
  // the backing volume, and whether the app plays the other hand in one-hand practice. Config > Students sets them for each child; the Play screen's test
  // sheet sets the parent's own. Rows for a two-column grid.
  import type { StudentSettings } from "../lib/settings";

  let { settings, backing = true, onchange }: {
    settings: Pick<StudentSettings, "autoRewind" | "rewindBars" | "backingVolume" | "otherHand">;
    backing?: boolean;
    onchange: (p: Partial<StudentSettings>) => void;
  } = $props();

  const bars = (by: number) => onchange({ rewindBars: Math.max(1, Math.min(8, settings.rewindBars + by)) });
  const volume = (by: number) => onchange({ backingVolume: Math.max(0, Math.min(3, Math.round((settings.backingVolume + by) * 4) / 4)) });
</script>

<span>Auto-rewind</span>
<span><button class="toggle" class:off={!settings.autoRewind} onclick={() => onchange({ autoRewind: !settings.autoRewind })}>{settings.autoRewind ? "On" : "Off"}</button></span>
<span>Rewind button</span>
<span><button class="quiet" onclick={() => bars(-1)} aria-label="Fewer bars">−</button> <b>{settings.rewindBars} bar{settings.rewindBars > 1 ? "s" : ""}</b> <button class="quiet" onclick={() => bars(1)} aria-label="More bars">+</button></span>
<span>Other hand</span>
<span><button class="toggle" class:off={!settings.otherHand} onclick={() => onchange({ otherHand: !settings.otherHand })}>{settings.otherHand ? "App plays it" : "Silent"}</button></span>
{#if backing}
  <span>Backing volume</span>
  <span><button class="quiet" onclick={() => volume(-0.25)} aria-label="Quieter">−</button> <b>{Math.round(settings.backingVolume * 100)}%</b> <button class="quiet" onclick={() => volume(0.25)} aria-label="Louder">+</button></span>
{/if}
