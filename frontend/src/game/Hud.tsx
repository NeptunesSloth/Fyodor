/**
 * The tabletop HUD: small floating pieces instead of a dashboard sidebar. The table is the
 * interface; these only appear when they have something to say.
 */
import { useEffect, useRef, useState } from "react";
import { openMenu } from "../components/ContextMenu";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible } from "../types/game";
import { addCounter, send, tapCards } from "./actions";
import { cardMenu } from "./cardMenu";
import { EFFECT_PRESETS } from "./marksMenu";
import { Inspector, LogPanel, StackPanel } from "./SidePanels";

/** Large card preview that floats at the edge of the table while you hover a card. */
/** skipHand: on the 3D table a hovered hand card already lifts out of the fan at full size. */
export function CardPreview({ skipHand = false }: { skipHand?: boolean }) {
  const hover = useGame((s) => s.hover);
  const inHand = useGame((s) => !!s.hover && !!s.view?.cards[s.hover]?.zone.endsWith(":hand"));
  const side = useRef<"left" | "right">("right");
  const [pos, setPos] = useState<"left" | "right">("right");
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const next = e.clientX > window.innerWidth * 0.62 ? "left" : "right";
      if (next !== side.current) {
        side.current = next;
        setPos(next);
      }
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);
  const stackBusy = useGame((s) => (s.view?.stack.length ?? 0) > 0);
  if (!hover || (skipHand && inHand)) return null;
  // keep clear of the stack widget (top-right) while something is on the stack
  const place = stackBusy ? "left" : pos;
  return (
    <div className={`card-preview ${place}`} data-testid="card-preview">
      <Inspector />
    </div>
  );
}

/** The stack as a compact indicator; it opens up while something is on it. */
export function StackWidget({ me }: { me: string }) {
  const count = useGame((s) => s.view?.stack.length ?? 0);
  const open = useGame((s) => s.stackOpen);
  const setOpen = (v: boolean) => useGame.getState().setLayout({ stackOpen: v });
  const rulesOn = useGame((s) => !!s.view?.rules && !s.view.rules.paused);
  if (rulesOn && count > 0) return null; // the rules engine's STACK panel shows it
  return (
    <div className={`stack-widget below-hud ${count ? "busy" : "idle"} ${open && count ? "open" : ""}`} data-testid="stack-widget">
      {count > 0 && open ? (
        <>
          <StackPanel me={me} onCollapse={() => setOpen(false)} />
        </>
      ) : (
        <button className="stack-pill" data-drop="stack" onClick={() => setOpen(true)} title="Drag a spell here to cast it">
          Stack{count ? ` · ${count}` : ""}
        </button>
      )}
    </div>
  );
}

/** The log, collapsed to its latest line; open it for the full history and chat. */
export function LogDrawer() {
  const log = useGame((s) => s.view?.log ?? []);
  const open = useGame((s) => s.logOpen);
  const setOpen = (v: boolean) => useGame.getState().setLayout({ logOpen: v });
  const last = log[log.length - 1];
  const text = last ? last.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : p.group.map((g) => g.card.name).join(", "))).join("") : "";
  return (
    <div className={`log-drawer ${open ? "open" : ""}`} data-testid="log-drawer">
      {open ? (
        <>
          <button className="tt-icon log-close" title="Close log" onClick={() => setOpen(false)}>–</button>
          <LogPanel />
        </>
      ) : (
        <button className="log-pill" onClick={() => setOpen(true)} title="Game log and chat">
          <span className="log-pill-label">Log</span>
          <span className="log-pill-last">{text}</span>
        </button>
      )}
    </div>
  );
}

/** A few physical tools within reach, bottom-left. */
export function ToolTray() {
  const openDialog = useGame((s) => s.openDialog);
  return (
    <div className="tool-tray" data-testid="tool-tray">
      <button className="tt-btn" onClick={() => openDialog("tokens")} title="Create tokens">Tokens</button>
      <button className="tt-btn" onClick={() => openDialog("dice")} title="Dice and coins">Dice</button>
    </div>
  );
}

/** Contextual toolbar for the current selection on the battlefield. */
export function SelectionBar() {
  const selection = useGame((s) => s.selection);
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  if (!view) return null;
  const onTable = selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield"));
  if (onTable.length < 1) return null;
  const me = perspective(view, actingAs);
  const first = view.cards[onTable[0]!]!;
  const anyUntapped = onTable.some((id) => !view.cards[id]?.tapped);
  return (
    <div className="selection-bar" data-testid="selection-bar">
      <span className="sel-count">{onTable.length === 1 && isVisible(first) ? first.name : `${onTable.length} selected`}</span>
      <button className="tt-btn" onClick={() => void tapCards(onTable, anyUntapped)}>{anyUntapped ? "Tap" : "Untap"}</button>
      <button className="tt-btn" onClick={() => void addCounter(onTable, "+1/+1", 1)}>+1/+1</button>
      <button className="tt-btn" onClick={(e) => openMenu(e, EFFECT_PRESETS.map((p) => ({ label: p.name, onClick: () => void send({ type: "add_effect", card_ids: onTable, name: p.name, ...(p.value ? { value: p.value } : {}), ...(p.color ? { color: p.color } : {}) }) })), "Add effect")}>Effect</button>
      <button className="tt-btn" onClick={() => void send({ type: "set_damage", card_ids: onTable, delta: 1 })}>Damage +1</button>
      <button className="tt-btn ghost" title="All actions" onClick={(e) => { const m = cardMenu(first, view, me); openMenu(e, m.items, m.title); }}>More…</button>
      <button className="tt-icon" title="Clear selection (Esc)" onClick={() => useGame.getState().clearSelection()}>✕</button>
    </div>
  );
}

/** Minimal / full HUD (H). Minimal hides the secondary details on plates and tools. */
export function useHudClass(): void {
  const hud = usePrefs((s) => s.hud);
  useEffect(() => {
    document.body.classList.toggle("hud-minimal", hud === "minimal");
    return () => document.body.classList.remove("hud-minimal");
  }, [hud]);
}
