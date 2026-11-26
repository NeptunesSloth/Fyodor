/** Which table renderer to use: the player's choice, with the 2D table as the fallback. */

/** A WebGL renderer name drawn by the CPU, not a graphics card: Chrome's SwiftShader, Windows' WARP ("Microsoft Basic
 *  Render Driver"), Mesa's llvmpipe / softpipe. */
export function isSoftwareRendererName(name: string): boolean {
  return /swiftshader|basic render driver|\bwarp\b|llvmpipe|softpipe|software/i.test(name);
}

let webgl: boolean | null = null;
let software = false;

/** Whether WebGL works (and, while the throwaway context is there, whether it is drawn in software). */
export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") ?? c.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    try {
      const info = gl.getExtension("WEBGL_debug_renderer_info");
      software = isSoftwareRendererName(String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER) ?? ""));
    } catch {
      software = false;
    }
    gl.getExtension("WEBGL_lose_context")?.loseContext(); // (the browser keeps only so many contexts)
    return true;
  } catch {
    return false;
  }
}

/** WebGL support, checked once per page: each check creates a throwaway context, which costs most of a second on a
 *  software renderer (a laptop without a GPU driver, headless CI). */
export function hasWebgl(): boolean {
  webgl ??= webglAvailable();
  return webgl;
}

/** -- software 3D -- the 3D table would be drawn by the CPU (a computer or virtual machine without a graphics driver). */
export function softwareWebgl(): boolean {
  return hasWebgl() && software;
}

const SOFTWARE_KEY = "fyodor.softwareGraphics";

/**
 * -- software 3D -- the graphics preset to switch to the first time this device opens the 3D table drawn in software:
 * Low (the High preset draws a late-game board at about one frame a second there; Low, several times that). Asked once
 * per device: a player who then picks Medium or High in Settings keeps it. Null: nothing to change. (Automated browsers,
 * the 3D browser tests on software WebGL, keep the preset they ask for.)
 */
export function softwareGraphicsDefault(current: string, isSoftware = softwareWebgl() && !navigator.webdriver): "low" | null {
  if (!isSoftware) return null;
  try {
    if (localStorage.getItem(SOFTWARE_KEY)) return null;
    localStorage.setItem(SOFTWARE_KEY, "1");
  } catch {
    return null; // (nowhere to remember it: never switch on every visit)
  }
  return current === "low" ? null : "low";
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
