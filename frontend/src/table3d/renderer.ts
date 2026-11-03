/** Which table renderer to use: the player's choice, with the 2D table as the fallback. */

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}

let webgl: boolean | null = null;

/** WebGL support, checked once per page: each check creates a throwaway context, which costs most of a second on a
 *  software renderer (a laptop without a GPU driver, headless CI). */
export function hasWebgl(): boolean {
  webgl ??= webglAvailable();
  return webgl;
}

export function resolveRenderer(pref: "auto" | "3d" | "2d"): "3d" | "2d" {
  if (pref === "2d" || !hasWebgl()) return "2d";
  if (pref === "3d") return "3d";
  // AUTO: a per-device override (Settings on a slow laptop, or the 3D browser tests), else 3D.
  // Automated browsers (the 2D E2E suite) default to the 2D table unless they opt in.
  let forced: string | null = null;
  try {
    forced = localStorage.getItem("fyodor.renderer");
  } catch {
    forced = null;
  }
  if (forced === "2d" || forced === "3d") return forced;
  return navigator.webdriver ? "2d" : "3d";
}
