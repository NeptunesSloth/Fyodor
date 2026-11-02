/**
 * The tabletop HUD: small floating pieces instead of a dashboard sidebar. The table is the
 * interface; these only appear when they have something to say.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { askNumber } from "../components/Prompt";
import { useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible } from "../types/game";
import { addCounter, send, tapCards } from "./actions";
import { cardMenu } from "./cardMenu";
import { damageMenu } from "./marksMenu";
import { typeLine } from "./selection";
import { keyLabel } from "./hotkeys";
import { HAND_SORTS, HAND_SORT_LABEL } from "./handSort";
import { domBoxOf, placeAnchored, selectionAnchor } from "./anchors";
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
  // the last real entry (step dividers like "— Precombat main —" read as empty)
  const entryText = (e: (typeof log)[number]) => e.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : p.group.map((g) => g.card.name).join(", "))).join("");
  const last = [...log].reverse().find((e) => !entryText(e).trim().startsWith("—"));
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
  const diceOpen = useGame((s) => s.dialog === "dice");
  const keymap = usePrefs((s) => s.keymap);
  const sort = usePrefs((s) => s.handSort);
  const sortMenu = (e: React.MouseEvent) => openMenu(e, [
    ...HAND_SORTS.map((m) => ({
      label: `${m === sort ? "✓ " : ""}${HAND_SORT_LABEL[m][0]!.toUpperCase()}${HAND_SORT_LABEL[m].slice(1)}`,
      onClick: () => usePrefs.getState().set({ handSort: m }),
    })),
    "separator" as const,
    // the scripted tables' hand menu: the server picks the card
    { label: "Discard a card at random", onClick: () => void send({ type: "discard_random", count: 1 }) },
    { label: "Discard at random…", onClick: async () => { const n = await askNumber("Discard how many cards at random?", 2, { min: 1, max: 20 }); if (n) void send({ type: "discard_random", count: n }); } },
  ], "Your hand (S sorts)");
  return (
    <div className="tool-tray" data-testid="tool-tray">
      <button className="tt-btn" onClick={() => openDialog("tokens")} title="Create tokens">Tokens</button>
      <button className={`tt-btn${diceOpen ? " on" : ""}`} onClick={() => openDialog(diceOpen ? null : "dice")} title={`Roll dice or flip a coin (${keyLabel("dice", keymap) ?? "Shift+R"})`}
        aria-expanded={diceOpen} data-dice-toggle data-testid="dice-button">Dice</button>
      <button className="tt-btn" onClick={sortMenu} title="Sort your hand: as drawn, mana value, colour, type or name (S)" data-testid="hand-sort">
        Hand: {sort === "drawn" ? "as drawn" : HAND_SORT_LABEL[sort].replace("by ", "")}
      </button>
    </div>
  );
}

/** Contextual toolbar for the current selection on the battlefield, attached to the card it acts on. */
export function SelectionBar() {
  const selection = useGame((s) => s.selection);
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const ref = useRef<HTMLDivElement>(null);
  const onTable = view ? selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield")) : [];
  const anchor = onTable[0] ?? null;
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || !anchor) return;
    selectionAnchor.node = node;
    selectionAnchor.card = anchor;
    const three = !!document.querySelector("[data-drop3d]"); // the 3D frame loop places it there
    const place = () => { if (!three) placeAnchored(node, domBoxOf(anchor)); };
    place();
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("resize", place);
      if (selectionAnchor.node === node) {
        selectionAnchor.node = null;
        selectionAnchor.card = null;
      }
    };
  });
  if (!view || !anchor) return null;
  const me = perspective(view, actingAs);
  const first = view.cards[anchor]!;
  const anyUntapped = onTable.some((id) => !view.cards[id]?.tapped);
  // what fits these cards (one primary row, the rest under More…): creatures get +1/+1 and damage, the others counters
  const creatures = onTable.every((id) => /\bCreature\b/.test(typeLine(view.cards[id]!)));
  const cardData = onTable.length === 1 && isVisible(first) && first.card_id ? useCardCache.getState().cards[first.card_id] : undefined;
  const turnable = !!cardData && (cardData.double_faced || cardData.faces.length > 1);
  const full = cardMenu(first, view, me);
  const sub = (label: string) => (full.items.find((i) => i !== "separator" && i.label === label) as Exclude<MenuItem, "separator"> | undefined)?.submenu;
  const counters = sub("Add counter");
  const damage = damageMenu(onTable, first) as Exclude<MenuItem, "separator">;
  const keymap = usePrefs.getState().keymap;
  const chip = (id: Parameters<typeof keyLabel>[0]) => { const k = keyLabel(id, keymap); return k ? <kbd className="key-chip" aria-hidden>{k}</kbd> : null; };
  return (
    <div className="selection-bar anchored" data-testid="selection-bar" ref={ref} role="toolbar" aria-label="Selected card actions">
      <span className="sel-count">{onTable.length === 1 && isVisible(first) ? first.name : `${onTable.length} selected`}</span>
      <button className="tt-btn" title="Tap or untap (or double-click the card)" onClick={() => void tapCards(onTable, anyUntapped)}>{anyUntapped ? "Tap" : "Untap"}{chip("tap")}</button>
      {creatures ? (
        <>
          <button className="tt-btn" title="Add a +1/+1 counter (right-click removes one)" onClick={() => void addCounter(onTable, "+1/+1", 1)}
            onContextMenu={(e) => { e.preventDefault(); void addCounter(onTable, "+1/+1", -1); }}>+1/+1 counter</button>
          <button className="tt-btn" title="Mark damage" onClick={(e) => openMenu(e, damage.submenu ?? [], damage.label)}>{damage.label}…</button>
        </>
      ) : counters ? (
        <button className="tt-btn" title="Add a counter" onClick={(e) => openMenu(e, counters, "Add counter")}>Counter…</button>
      ) : null}
      {/* the encoder's counter steppers: click +1, right-click −1, one chip per counter on the card */}
      {onTable.length === 1 && Object.entries(first.counters ?? {}).filter(([, n]) => n > 0).map(([kind, n]) => (
        <button key={kind} className="tt-btn counter-step" data-testid={`step-${kind}`} title={`${kind} counters: click adds one, right-click removes one`}
          onClick={() => void addCounter([first.id], kind, 1)} onContextMenu={(e) => { e.preventDefault(); void addCounter([first.id], kind, -1); }}>
          {kind} <b>{n}</b>
        </button>
      ))}
      {turnable && <button className="tt-btn" title="Turn over" onClick={() => void send({ type: "set_face", card_id: first.id })}>Turn over{chip("turn_over")}</button>}
      <button className="tt-btn ghost" title="Every action for this card (right-click)" onClick={(e) => openMenu(e, full.items, full.title)}>More…</button>
      <span className="sel-ping" aria-hidden>{chip("ping")} ping</span>
      <button className="tt-icon" title="Clear selection (Esc)" aria-label="Clear selection" onClick={() => useGame.getState().clearSelection()}>✕</button>
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
