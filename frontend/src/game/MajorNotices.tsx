import { useEffect, useRef } from "react";
import { toast } from "../components/Toasts";
import { perspective, useGame } from "../state/gameStore";
import { SPECTATOR } from "../types/game";
import { EventTracker, tableNotices } from "./eliminationHub";

/**
 * Major public events at the live table, briefly, for everyone (docs/ELIMINATION_HUB.md): "Bob was eliminated.",
 * "Final two players remain: …". Each one once; nothing that was already true when you arrived. Toasts sit above
 * dialogs, so a player who is out sees them over the opening-hand practice or Deck Lab too.
 */
export function MajorNotices() {
  const events = useGame((s) => s.view?.game.events);
  const tracker = useRef(new EventTracker());
  useEffect(() => {
    const { view, actingAs } = useGame.getState();
    const fresh = tracker.current.take(events);
    if (!view || view.game.practice || !fresh.length) return;
    const me = view.viewer === SPECTATOR ? null : perspective(view, actingAs);
    for (const e of tableNotices(fresh, me)) toast(e.text);
  }, [events]);
  return null;
}
