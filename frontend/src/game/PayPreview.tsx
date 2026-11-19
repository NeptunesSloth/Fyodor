import { useEffect, useState } from "react";
import { create } from "zustand";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { useGame } from "../state/gameStore";
import type { GameView } from "../types/game";
import { pingPoint, type ScreenPoint } from "./ping";
import "./ease.css";

/**
 * -- pay preview -- pointing at (or focusing) a card in my hand that I can cast now lights the lands the automatic payer would tap for it:
 * the server's own solver answers (GET /pay-preview, read-only, my own hand only), once per card per view. 2D: a brass ring and "tap" on
 * those cards; 3D: a ring over each, placed once (no per-frame work).
 */
const usePay = create<{ ids: string[] }>(() => ({ ids: [] }));
const cache = new WeakMap<GameView, Map<string, string[]>>();
let timer = 0;
let want: string | null = null;

/** Show (id) or clear (null) the preview for a hand card of `me`. */
export function previewPay(id: string | null, me: string): void {
  window.clearTimeout(timer);
  want = id;
  const view = useGame.getState().view;
  const hints = view?.rules && !view.rules.paused ? view.rules.hints : undefined;
  if (!view || !id || !hints?.castable?.includes(id) || view.cards[id]?.zone !== `${me}:hand`) {
    if (usePay.getState().ids.length) usePay.setState({ ids: [] });
    return;
  }
  const known = cache.get(view)?.get(id);
  if (known) return usePay.setState({ ids: known });
  timer = window.setTimeout(() => {
    const q = view.game.mode === "local" ? `?viewer=${encodeURIComponent(me)}` : "";
    const t = seatToken(view.game.id);
    api.get<{ tapped: string[] | null }>(`/games/${view.game.id}/pay-preview/${encodeURIComponent(id)}${q}`, t ? { "X-Seat-Token": t } : {}).then((r) => {
      const ids = r.tapped ?? [];
      if (!cache.has(view)) cache.set(view, new Map());
      cache.get(view)!.set(id, ids);
      if (want === id && useGame.getState().view === view) usePay.setState({ ids });
    }, () => undefined);
  }, 120);
}

/** Follows the hovered card (mounted once, with my hand) and marks the lands. */
export function PayPreview({ me }: { me: string }) {
  useEffect(() => useGame.subscribe((s, prev) => {
    if (s.hover !== prev.hover) {
      if (s.hover && s.view?.cards[s.hover]?.zone === `${me}:hand`) previewPay(s.hover, me);
      else if (prev.hover && want === prev.hover) previewPay(null, me);
    } else if (s.view !== prev.view && want) previewPay(want, me); // (the table changed: ask again)
  }), [me]);
  const ids = usePay((s) => s.ids);
  const view = useGame((s) => s.view);
  const [marks, setMarks] = useState<ScreenPoint[]>([]);
  useEffect(() => {
    const els = ids.flatMap((id) => [...document.querySelectorAll<HTMLElement>(`.battlefield .table-card[data-card-id="${CSS.escape(id)}"]`)]);
    els.forEach((el) => el.classList.add("pay-preview"));
    const place = () => setMarks(document.querySelector("[data-drop3d]") ? ids.map((id) => pingPoint({ card: id })).filter((p): p is ScreenPoint => !!p) : []);
    place();
    window.addEventListener("resize", place);
    return () => { els.forEach((el) => el.classList.remove("pay-preview")); window.removeEventListener("resize", place); };
  }, [ids, view]);
  if (!marks.length) return null;
  return (
    <div className="pay-marks" aria-hidden data-testid="pay-marks">
      {marks.map((p, i) => <div key={i} className="pay-mark" style={{ left: p.x, top: p.y }}><span>tap</span></div>)}
    </div>
  );
}
