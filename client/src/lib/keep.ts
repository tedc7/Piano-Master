// Back from a song to the screen that opened it, as it was left (arch §3, v0.29): its scroll
// position and what it had open (the Journey's skill pop-up, the library's filter). A screen keeps
// its view here as it changes; the view is put back only when the Play screen's Back returns to
// that screen, so the tab bar still opens every screen fresh.
import { onMount } from "svelte";
import { app } from "./app.svelte.js";

interface View { top: number; left: number; extra: unknown }
const views = new Map<string, View>();

/** Call while the screen's component starts. `key` is the route the screen is at (as given to
 *  app.openPiece); `scroller` is the element that scrolls; `extra` the screen's own state. */
export function keepView<T>(key: string, scroller: () => HTMLElement | null | undefined,
                            extra?: { get: () => T; set: (v: T) => void }): void {
  const back = app.takeReturn(key);
  const saved = back ? views.get(key) : undefined;
  if (saved && saved.extra !== undefined) extra?.set(saved.extra as T);
  if (!back) views.delete(key);
  onMount(() => {
    const el = scroller();
    const view = (): View => ({ top: el?.scrollTop ?? 0, left: el?.scrollLeft ?? 0, extra: extra?.get() });
    let restoring = !!saved;
    if (saved && el) {
      // the screen's content arrives after it opens: keep trying until it's long (or wide) enough
      let tries = 0;
      const put = () => {
        el.scrollTop = saved.top;
        el.scrollLeft = saved.left;
        const there = Math.abs(el.scrollTop - saved.top) <= 1 && Math.abs(el.scrollLeft - saved.left) <= 1;
        if (!there && ++tries < 180) requestAnimationFrame(put); else restoring = false;
      };
      put();
    }
    // the scroll is read as it changes: once the screen is gone, its element no longer has one
    const onScroll = () => { if (!restoring) views.set(key, view()); };
    el?.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el?.removeEventListener("scroll", onScroll);
      views.set(key, { ...(views.get(key) ?? view()), extra: extra?.get() });
    };
  });
}
