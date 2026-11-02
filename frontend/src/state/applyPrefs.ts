/** Apply the active profile's display settings to the whole page. */
import { useEffect, useState } from "react";
import { usePrefs } from "./prefs";
import { applyPlane } from "../theme/planes";

/** The system's "reduce motion" setting (WCAG 2.3.3), followed as it changes. */
function useSystemReducedMotion(): boolean {
  const [query] = useState(() => (typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null));
  const [reduced, setReduced] = useState(!!query?.matches);
  useEffect(() => {
    if (!query) return;
    const update = () => setReduced(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, [query]);
  return reduced;
}

export function useApplyPrefs(): void {
  const p = usePrefs();
  const system = useSystemReducedMotion();
  useEffect(() => applyPlane(p.plane), [p.plane]);
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("zoom", String(p.uiScale));
    root.style.setProperty("--anim-scale", String(p.reducedMotion ? 0 : 1 / p.animationSpeed));
    const body = document.body.classList;
    body.toggle("high-contrast", p.highContrast);
    body.toggle("reduced-motion", p.reducedMotion || p.graphics === "low" || system); // (the table motion and CSS read this class)
    body.toggle("cb-markers", p.colorblindMarkers);
    body.toggle("inspect-large", p.inspectSize === "large");
    body.toggle("perf-low", p.graphics === "low");
    body.toggle("perf-medium", p.graphics === "medium");
  }, [p.uiScale, p.reducedMotion, p.animationSpeed, p.highContrast, p.colorblindMarkers, p.inspectSize, p.graphics, system]);
}

/** What each graphics preset changes (shown in Settings). */
export const GRAPHICS_NOTES: Record<string, string> = {
  low: "No shadows or animations, small card images, identical tokens collapse above 5.",
  medium: "Light shadows, shorter animations.",
  high: "Full shadows and animations, full-size card images.",
};
