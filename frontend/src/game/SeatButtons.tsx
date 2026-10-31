import { useEffect, useRef, useState } from "react";
import { perspective, useGame } from "../state/gameStore";
import { runSeatAction, SEAT_ACTIONS, TypedCount, type SeatActionId } from "./seatActions";
import { seatIconUrl } from "./seatIcons";

/**
 * Your seat's buttons on the 2D table, by your mat as on the Oops tables: round Untap, Draw, Scry, Mill and Reveal
 * buttons. Click does one, right-click three, or hover one and type a number. (The 3D table has them as physical
 * buttons on the table: table3d/seatProps.ts.)
 */
export function SeatButtons() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const me = view ? perspective(view, actingAs) : null;
  const meRef = useRef(me);
  meRef.current = me;
  const [typed, setTyped] = useState<{ id: SeatActionId | null; n: string }>({ id: null, n: "" });
  const hovered = useRef<SeatActionId | null>(null);
  const counter = useRef<TypedCount | null>(null);
  useEffect(() => {
    const c = new TypedCount((id, n) => setTyped({ id, n }), (id, n) => meRef.current && runSeatAction(id, n, meRef.current));
    counter.current = c;
    // digits typed over a button go to it, not to the table's camera keys
    const onKey = (e: KeyboardEvent) => {
      if (c.key(hovered.current, e.key)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => { window.removeEventListener("keydown", onKey, true); c.dispose(); };
  }, []);
  if (!me || view?.viewer === "__spectator__") return null;
  return (
    <div className="seat-buttons" role="toolbar" aria-label="Your seat's buttons" data-testid="seat-buttons">
      {SEAT_ACTIONS.map((b) => (
        <button key={b.id} className={`seat-btn seat-${b.id}`} title={b.title} aria-label={b.title} data-testid={`seat-btn-${b.id}`}
          onPointerEnter={() => { hovered.current = b.id; }}
          onPointerLeave={() => { if (hovered.current === b.id) hovered.current = null; }}
          onClick={() => runSeatAction(b.id, 1, me)}
          onContextMenu={(e) => { e.preventDefault(); runSeatAction(b.id, 3, me); }}>
          <img src={seatIconUrl(b.id)} alt="" draggable={false} />
          {typed.id === b.id && <b className="seat-typed" aria-live="polite">{typed.n}</b>}
        </button>
      ))}
    </div>
  );
}
