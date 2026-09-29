/** Apply the active profile's display settings to the whole page. */
import { useEffect } from "react";
import { usePrefs } from "./prefs";

export function useApplyPrefs(): void {
  const p = usePrefs();
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("zoom", String(p.uiScale));
    root.style.setProperty("--anim-scale", String(p.reducedMotion ? 0 : 1 / p.animationSpeed));
    const body = document.body.classList;
    body.toggle("high-contrast", p.highContrast);
    body.toggle("reduced-motion", p.reducedMotion || p.graphics === "low");
    body.toggle("cb-markers", p.colorblindMarkers);
    body.toggle("inspect-large", p.inspectSize === "large");
    body.toggle("perf-low", p.graphics === "low");
    body.toggle("perf-medium", p.graphics === "medium");
  }, [p.uiScale, p.reducedMotion, p.animationSpeed, p.highContrast, p.colorblindMarkers, p.inspectSize, p.graphics]);
}

/** What each graphics preset changes (shown in Settings). */
export const GRAPHICS_NOTES: Record<string, string> = {
  low: "No shadows or animations, small card images, identical tokens collapse above 5.",
  medium: "Light shadows, shorter animations.",
  high: "Full shadows and animations, full-size card images.",
};
