/**
 * Controls that travel with a card (Tabletop Simulator's card-attached buttons): the selection toolbar sits just above
 * the card it acts on, with a notch pointing at it, and flips below when there's no room above. The 2D table places it
 * from the card's DOM box; the 3D table calls `placeAnchored` from its frame loop (the camera can move every frame).
 */
export interface ClientBox { left: number; top: number; right: number; bottom: number }

/** The one anchored toolbar and the card it belongs to (set by SelectionBar, read by the 3D frame loop). */
export const selectionAnchor: { node: HTMLElement | null; card: string | null } = { node: null, card: null };

const GAP = 10;
const TOP_CHROME = 52; // the top bar
/** Fixed controls the toolbar must never cover (it tries the other side of its card first). */
const OBSTACLES = ".turn-dial-wrap, .response-bar, .rules-stack-wrap, .stack-widget.open, .t3d-cams";

let obstacles: ClientBox[] = [];
let measuredAt = 0;
function fixedControls(): ClientBox[] {
  const now = performance.now();
  if (now - measuredAt > 250) { // the 3D table calls this every frame: measure a few times a second, not 60
    obstacles = [...document.querySelectorAll(OBSTACLES)].map((n) => n.getBoundingClientRect());
    measuredAt = now;
  }
  return obstacles;
}
const overlaps = (a: ClientBox, b: ClientBox) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

export function placeAnchored(node: HTMLElement, box: ClientBox | null): void {
  // off screen (the 3D camera turned away): hide rather than point at nothing from the edge
  if (!box || box.right < 0 || box.bottom < TOP_CHROME || box.left > window.innerWidth || box.top > window.innerHeight) {
    node.style.visibility = "hidden";
    return;
  }
  const w = node.offsetWidth;
  const h = node.offsetHeight;
  const cx = (box.left + box.right) / 2;
  const x = Math.max(8, Math.min(window.innerWidth - w - 8, cx - w / 2));
  const fit = (top: number) => Math.max(TOP_CHROME, Math.min(window.innerHeight - h - 8, top));
  const clear = (top: number) => !fixedControls().some((o) => overlaps({ left: x, top, right: x + w, bottom: top + h }, o));
  const above = fit(box.top - h - GAP);
  const under = fit(box.bottom + GAP);
  const below = box.top - h - GAP < TOP_CHROME || (!clear(above) && clear(under));
  const y = below ? under : above;
  node.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  node.style.setProperty("--notch-x", `${Math.round(Math.max(14, Math.min(w - 14, cx - x)))}px`);
  node.dataset.side = below ? "below" : "above";
  node.style.visibility = "visible";
}

/** The 2D table: the card's box straight from the DOM. */
export function domBoxOf(cardId: string): ClientBox | null {
  const el = document.querySelector(`.battlefield [data-card-id="${CSS.escape(cardId)}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
}
