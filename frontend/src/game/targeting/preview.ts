/**
 * While choosing targets, the large card preview opens on the side of the screen away from the card it shows, so it
 * never covers the candidate being looked at (or its arrow). Null when not choosing or the card isn't on the table.
 */
export function previewSide(hover: string | null): "left" | "right" | null {
  if (!hover || typeof document === "undefined" || !document.body.classList.contains("targeting")) return null;
  const id = CSS.escape(hover);
  const r = document.querySelector(`.battlefield [data-card-id="${id}"], .command-zone [data-card-id="${id}"]`)?.getBoundingClientRect();
  if (!r || !r.width) return null;
  return r.left + r.width / 2 < window.innerWidth / 2 ? "right" : "left";
}
