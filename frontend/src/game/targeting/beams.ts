import { useGame } from "../../state/gameStore";
import type { GameView } from "../../types/game";
import { useTargeting } from "./store";
import { targetingOf } from "./targeting";

/**
 * What the 3D table draws while I choose targets: the source, the candidates (lifted; the rest darkens), the one under
 * the pointer (on the table or in the tray) or keyboard focus, and the ones chosen so far (in order). Null when no
 * targeting bar is up.
 */
export function targetBeams(view: GameView, me: string): { source: string | null; cands: Set<string>; hot: string | null; picked: string[]; targets: string[] } | null {
  const rules = view.rules;
  if (!rules || rules.paused || rules.options?.highlights === "off") return null;
  const t = targetingOf(view, me, useGame.getState().selection);
  if (!t) return null;
  const s = useTargeting.getState();
  const picked = s.decision === t.decision.id ? s.picked.map((p) => p.ref) : [];
  const hover = useGame.getState().hover;
  const hot = s.hot ?? s.focus ?? (hover && t.candidates.some((c) => c.ref === hover) ? hover : null);
  return { source: t.source, cands: new Set(t.candidates.map((c) => c.ref)), hot, picked, targets: [...picked, ...(hot && !picked.includes(hot) ? [hot] : [])] };
}
