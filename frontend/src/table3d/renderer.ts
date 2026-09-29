/** Which table renderer to use: the player's choice, with the 2D table as the fallback. */
import { webglAvailable } from "./TableScene";

let webgl: boolean | null = null;

export function resolveRenderer(pref: "auto" | "3d" | "2d"): "3d" | "2d" {
  webgl ??= webglAvailable();
  if (pref === "2d" || !webgl) return "2d";
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
