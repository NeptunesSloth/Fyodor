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
import { cardEditRefusal } from "./cardPermissions";
import { damageMenu } from "./marksMenu";
import { typeLine } from "./selection";
import { keyLabel } from "./hotkeys";
import { isOut } from "./outOfGame";
import { HAND_SORTS, HAND_SORT_LABEL } from "./handSort";
import { domBoxOf, placeAnchored, selectionAnchor } from "./anchors";
import { Inspector, LogPanel, StackPanel } from "./SidePanels";
import { clearHover, hoverElement, placePreview, previewKey, type Box } from "./hoverCard";
import { toyIconUrl } from "./seatIcons";

/** The hovered card's rectangle on screen: its picture on the page, or where the 3D table draws it. */
function cardBox(id: string): Box | null {
  const el = hoverElement(id) ?? document.querySelector(`[data-card-id="${CSS.escape(id)}"]`);
  const r = el?.getBoundingClientRect();
  if (r && r.width) return r;
  const p = window.__fyodor3d?.cardAt(id);
  return p ? { left: p.x - 40, right: p.x + 40, top: p.y - 56, bottom: p.y + 56 } : null;
}

/** What the preview keeps clear of: the plates and strips, the rail by my mat, the turn panel, the stack, my hand, panels. */
const PREVIEW_CLEAR = ".t3d-seat, .seat-strip, .area-side, .turn-dial-wrap, .rules-stack-wrap, .stack-widget, .resp-bar, .t3d-cams, .log-drawer, .tool-tray, .hand-cards, .selection-bar, .decision-panel";
/** The least the preview's card picture shrinks to (from its full 230 px, or 330 with the large inspector) to fit. */
const PREVIEW_IMG_MIN = 130;

/**
 * The large card preview, docked at the right edge under the top bar while you hover a card. It never follows the
 * pointer: it moves to the left only while the hovered card itself lies under it, and then into the battlefield's gutter,
 * clear of the plates. It never covers the turn panel or other chrome: in a short space its picture shrinks to fit. It
 * goes when the hover ends (the pointer leaves the card, or the card goes away), on Esc, or with its close button, until
 * the next hover. skipHand: on the 3D table a hovered hand card already lifts out of the fan at full size.
 */
export function CardPreview({ skipHand = false }: { skipHand?: boolean }) {
  const hover = useGame((s) => s.hover);
  const inHand = useGame((s) => !!s.hover && !!s.view?.cards[s.hover]?.zone.endsWith(":hand"));
  const printId = useGame((s) => {
    if (!s.hover) return null;
    if (s.hover.startsWith("print:")) return s.hover.slice(6);
    return (s.view?.cards[s.hover] as { card_id?: string } | undefined)?.card_id ?? null;
  });
  const ready = useCardCache((c) => !!printId && !!c.cards[printId]); // (its text arrives with the card's data: measured again)
  const panel = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ side: "left" | "right"; left: number; top: number; maxH: number; img: number } | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => void previewKey(e);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // placed once per hovered card, before it shows: measured at full size, then put where it is clear and fitted
  useLayoutEffect(() => {
    const node = panel.current;
    if (!hover || !node) return;
    node.style.removeProperty("--insp-w");
    node.style.maxHeight = "none";
    const w = node.offsetWidth;
    const naturalH = node.offsetHeight;
    const base = (node.querySelector(".insp-image") as HTMLElement | null)?.offsetWidth || 230;
    const obstacles = [...document.querySelectorAll(PREVIEW_CLEAR)].map((n) => n.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const top = Math.max(96, ...[...document.querySelectorAll(".game-top, .t3d-cams")].map((n) => n.getBoundingClientRect().bottom + 8));
    const p = placePreview({ vw: window.innerWidth, vh: window.innerHeight, w, minH: 300, top, naturalH, card: cardBox(hover), obstacles });
    // too tall for its room: the picture gives way first (the words never do)
    const imgH = base * 88 / 63;
    const img = naturalH <= p.maxH ? 0 : Math.max(PREVIEW_IMG_MIN, Math.floor((p.maxH - (naturalH - imgH)) * 63 / 88));
    node.style.removeProperty("max-height");
    setPlace({ ...p, img });
  }, [hover, ready]);
  if (!hover || (skipHand && inHand)) return null;
  const style = place
    ? { left: place.left, top: place.top, maxHeight: place.maxH, ...(place.img ? { ["--insp-w" as string]: `${place.img}px` } : {}) }
    : { visibility: "hidden" as const };
  return (
    <div ref={panel} className={`card-preview ${place?.side ?? "right"}`} data-testid="card-preview" data-dock={place?.side ?? "right"} style={style}>
      <button type="button" className="card-preview-close" onClick={clearHover} aria-label="Close the card preview (Esc)" title="Close (Esc)"
        data-testid="card-preview-close">
        <img src={toyIconUrl("close")} alt="" draggable={false} />
      </button>
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
  const out = useGame((s) => isOut(s.view, me)); // -- out of the game -- nothing to cast: just the stack
  if (rulesOn && count > 0) return null; // the rules engine's STACK panel shows it
  return (
    <div className={`stack-widget below-hud ${count ? "busy" : "idle"} ${open && count ? "open" : ""}`} data-testid="stack-widget">
      {count > 0 && open ? (
        <>
          <StackPanel me={me} onCollapse={() => setOpen(false)} />
        </>
      ) : (
        <button className="stack-pill" data-drop="stack" onClick={() => setOpen(true)} title={out ? "The stack" : "Drag a spell here to cast it"}>
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

/**
 * Bottom left: how your hand is sorted. (Tokens and dice live in the Bag of Extras by your seat, game/ExtrasBag.tsx;
 * Shift+R still opens the roll panel.)
 */
export function ToolTray() {
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
  const kept = cardEditRefusal(view, onTable); // -- table permissions -- another player's cards: no edit buttons, just why
  const sub = (label: string) => (full.items.find((i) => i !== "separator" && i.label === label) as Exclude<MenuItem, "separator"> | undefined)?.submenu;
  const counters = sub("Add counter");
  const damage = damageMenu(onTable, first) as Exclude<MenuItem, "separator">;
  const keymap = usePrefs.getState().keymap;
  const chip = (id: Parameters<typeof keyLabel>[0]) => { const k = keyLabel(id, keymap); return k ? <kbd className="key-chip" aria-hidden>{k}</kbd> : null; };
  return (
    <div className="selection-bar anchored" data-testid="selection-bar" ref={ref} role="toolbar" aria-label="Selected card actions">
      <span className="sel-count">{onTable.length === 1 && isVisible(first) ? first.name : `${onTable.length} selected`}</span>
      {kept ? <span className="hint" title={kept}>{kept.split(":")[0]}</span> : (<>
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
      </>)}
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
