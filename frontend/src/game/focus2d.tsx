/**
 * Focus on the 2D table (TABLETOP_QOL_MILESTONE #10): the 2D form of the 3D camera's C / K / X keys. C looks at the
 * hovered card's board (the Look view, as keys 2–6 do) and marks the card; C again or Esc goes back to the board you
 * were looking at. K opens the stack panel, X brings the combat strip into view, each marked for a moment.
 * Display only: nothing here touches game state.
 */
import { useEffect } from "react";
import { useGame } from "../state/gameStore";
import type { GameView } from "../types/game";

/** The seat whose board shows this card on the 2D table (its battlefield or command zone), or null. */
export function boardOf(view: Pick<GameView, "cards">, id: string | null): string | null {
  const zone = id ? view.cards[id]?.zone : undefined;
  const at = zone?.indexOf(":") ?? -1;
  if (!zone || at < 0) return null;
  const where = zone.slice(at + 1);
  return where === "battlefield" || where === "command" ? zone.slice(0, at) : null;
}

/** C on the 2D table: the board to look at and the one to come back to, or null when C does nothing here. */
export function focusStep(view: Pick<GameView, "cards">, hover: string | null, current: string | null, open: { seat: string; back: string | null } | null):
  { focus: string | null; open: { seat: string; back: string | null } | null } | null {
  if (open && current === open.seat) return { focus: open.back, open: null }; // C again: back
  const seat = boardOf(view, hover);
  if (!seat) return null;
  return { focus: seat, open: { seat, back: current } };
}

/** A brief brass outline on what was focused (static with reduced motion). */
function mark(el: Element | null) {
  if (!el) return;
  el.classList.remove("focus-flash");
  void (el as HTMLElement).offsetWidth; // restart the fade when pressed twice
  el.classList.add("focus-flash");
  el.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  window.setTimeout(() => el.classList.remove("focus-flash"), 1400);
}

export function FocusKeys2D() {
  useEffect(() => {
    let open: { seat: string; back: string | null } | null = null;
    const onCam = (e: Event) => {
      const { id, hover } = (e as CustomEvent<{ id: string; hover: string | null }>).detail;
      const s = useGame.getState();
      const view = s.view;
      if (!view) return;
      if (id === "cam_focus") {
        const step = focusStep(view, hover, s.focus, open);
        if (!step) return;
        open = step.open;
        s.setLayout({ focus: step.focus });
        if (open && hover) requestAnimationFrame(() => mark(document.querySelector(`.battlefield [data-card-id="${CSS.escape(hover)}"], .command-zone [data-card-id="${CSS.escape(hover)}"]`)));
      } else if (id === "cam_stack") {
        if (!view.stack.length) return;
        if (!document.querySelector(".rules-stack-wrap")) s.setLayout({ stackOpen: true });
        requestAnimationFrame(() => mark(document.querySelector(".rules-stack-wrap, .stack-widget")));
      } else if (id === "cam_combat") {
        mark(document.querySelector(".combat-strip"));
      } else {
        open = null; // another camera key chose the view
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !open) return;
      const s = useGame.getState();
      if (s.focus === open.seat) s.setLayout({ focus: open.back });
      open = null;
    };
    window.addEventListener("fyodor:camera", onCam);
    window.addEventListener("keydown", onEsc);
    return () => {
      window.removeEventListener("fyodor:camera", onCam);
      window.removeEventListener("keydown", onEsc);
    };
  }, []);
  return null;
}
