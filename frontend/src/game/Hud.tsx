/**
 * The tabletop HUD: small floating pieces instead of a dashboard sidebar. The table is the
 * interface; these only appear when they have something to say.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { askNumber } from "../components/Prompt";
import { ManaText } from "../cards/ManaText";
import { useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, type GameView } from "../types/game";
import { gameEnded } from "./nightEnding";
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
import { groupText } from "./logGroups";

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
/** The least the preview's card picture shrinks to, wide, before its rules text scrolls instead. */
const PREVIEW_ART_MIN = 120;
/** How long a preview whose rules text scrolls stays after the pointer leaves its card: time to reach the panel. */
const PREVIEW_LINGER = 450;

/**
 * Where the preview stands, for which card (and whether its words had arrived): `art`, its picture's width when it
 * shrinks to fit; `scroll`, the height its rules text scrolls in when even a small picture leaves too little room.
 */
type PreviewPlace = { key: string; side: "left" | "right"; left: number; top: number; maxH: number; art: number | null; scroll: number | null };

/**
 * The large card preview, docked at the right edge under the top bar while you hover a card. It never follows the
 * pointer: it moves to the left only while the hovered card itself lies under it, and then into the battlefield's gutter,
 * clear of the plates. Narrow, its picture over its words and only as tall as they are; it never covers the turn panel
 * or other chrome: in a short space its picture shrinks, and only past that does its rules text scroll (the panel then
 * stays a moment after the pointer leaves the card and holds while the pointer is on it, so the text can be read).
 * It goes when the hover ends (the pointer leaves the card, or the card goes away), on Esc, or with its close button,
 * until the next hover. skipHand: on the 3D table a hovered hand card already lifts out of the fan at full size.
 */
export function CardPreview({ skipHand = false }: { skipHand?: boolean }) {
  const hover = useGame((s) => s.hover);
  const panel = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<PreviewPlace | null>(null);
  const [held, setHeld] = useState<string | null>(null); // a scrolling preview the pointer is on
  const [linger, setLinger] = useState<string | null>(null); // a scrolling preview just left by the pointer
  const lastScroll = useRef<{ id: string; scroll: boolean } | null>(null);
  const shown = hover ?? held ?? linger;
  const inHand = useGame((s) => !!shown && !!s.view?.cards[shown]?.zone.endsWith(":hand"));
  const printId = useGame((s) => {
    if (!shown) return null;
    if (shown.startsWith("print:")) return shown.slice(6);
    return (s.view?.cards[shown] as { card_id?: string } | undefined)?.card_id ?? null;
  });
  const ready = useCardCache((c) => !!printId && !!c.cards[printId]); // (its text arrives with the card's data: measured again)
  useEffect(() => {
    const close = () => { setHeld(null); setLinger(null); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      void previewKey(e);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("fyodor:preview-close", close);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("fyodor:preview-close", close); };
  }, []);
  // the hover ended on a preview whose text scrolls: it stays a moment, for the pointer to reach it
  useEffect(() => {
    if (hover) { setLinger(null); return; }
    const last = lastScroll.current;
    if (!last?.scroll || held) return;
    setLinger(last.id);
    const t = window.setTimeout(() => setLinger(null), PREVIEW_LINGER);
    return () => window.clearTimeout(t);
  }, [hover]); // eslint-disable-line react-hooks/exhaustive-deps
  // placed once per card (and again when its words arrive), before it shows: a hidden render at full size is measured,
  // then the panel goes where it is clear, its picture as large as the room lets it be
  const key = `${shown}|${ready}`;
  const measuring = !place || place.key !== key;
  useLayoutEffect(() => {
    const node = panel.current;
    if (!shown || !node || !measuring) return;
    const w = node.offsetWidth;
    const naturalH = node.offsetHeight;
    const art = node.querySelector(".insp-image") as HTMLElement | null;
    const artW = art?.offsetWidth || 230;
    const artH = art?.offsetHeight || (artW * 88) / 63;
    const oracle = node.querySelector(".insp-oracle") as HTMLElement | null;
    const oracleH = oracle?.offsetHeight ?? 0;
    const obstacles = [...document.querySelectorAll(PREVIEW_CLEAR)].map((n) => n.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const top = Math.max(96, ...[...document.querySelectorAll(".game-top, .t3d-cams")].map((n) => n.getBoundingClientRect().bottom + 8));
    const minArtH = (PREVIEW_ART_MIN * 88) / 63;
    const shortest = naturalH - artH + minArtH; // with the smallest picture
    const p = placePreview({ vw: window.innerWidth, vh: window.innerHeight, w, minH: Math.min(shortest, 300), top, naturalH: Math.min(naturalH, shortest), card: cardBox(shown), obstacles });
    let fitArt: number | null = null;
    let scroll: number | null = null;
    const slack = 6; // (rounding, and the bezel's outset)
    if (naturalH + slack > p.maxH) {
      const room = p.maxH - slack - (naturalH - artH); // what is left for the picture
      if (room >= minArtH) fitArt = Math.floor((room * 63) / 88);
      else {
        fitArt = PREVIEW_ART_MIN;
        scroll = Math.max(60, Math.floor(oracleH - (shortest + slack - p.maxH)));
      }
    }
    lastScroll.current = { id: shown, scroll: scroll !== null };
    setPlace({ key, ...p, art: fitArt, scroll });
  });
  if (!shown || (skipHand && inHand)) return null;
  const style: React.CSSProperties = measuring || !place
    ? { left: 0, top: 0, visibility: "hidden" }
    : {
      left: place.left, top: place.top, maxHeight: place.maxH,
      ...(place.art ? { ["--insp-w" as string]: `${place.art}px` } : {}),
      ...(place.scroll ? { ["--insp-scroll" as string]: `${place.scroll}px` } : {}),
    };
  const side = !measuring && place ? place.side : "right";
  const scrolls = !measuring && !!place?.scroll;
  return (
    <div ref={panel} className={`card-preview ${side}${scrolls ? " scrolls" : ""}`} data-testid="card-preview" data-dock={side} style={style}
      onPointerEnter={() => scrolls && setHeld(shown)} onPointerLeave={() => setHeld(null)}
      onScrollCapture={(e) => {
        const t = e.target as HTMLElement;
        panel.current?.toggleAttribute("data-at-end", t.scrollTop + t.clientHeight >= t.scrollHeight - 2);
      }}>
      <button type="button" className="card-preview-close" onClick={() => { setHeld(null); setLinger(null); clearHover(); }} aria-label="Close the card preview (Esc)" title="Close (Esc)"
        data-testid="card-preview-close">
        <img src={toyIconUrl("close")} alt="" draggable={false} />
      </button>
      <Inspector id={shown} />
      <span className="card-preview-more" aria-hidden>
        More
        <svg viewBox="0 0 10 10"><path d="M2 3.5 L5 6.5 L8 3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
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
  const entryText = (e: (typeof log)[number]) => e.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : groupText(p.group))).join("");
  const last = [...log].reverse().find((e) => !entryText(e).trim().startsWith("—"));
  const text = last ? last.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : groupText(p.group))).join("") : "";
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

/** What the selection bar's moment is: the stack and the open decision (either changing closes the bar). */
export function barMoment(view: GameView): string {
  return `${view.stack.join(",")}|${view.rules?.decision?.id ?? ""}`;
}

/** Contextual toolbar for the current selection on the battlefield, attached to the card it acts on. */
export function SelectionBar() {
  const selection = useGame((s) => s.selection);
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const ref = useRef<HTMLDivElement>(null);
  const onTable = view ? selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield")) : [];
  // -- playtest (nov 16) -- the bar is for the moment the card was picked: once the stack or a decision moves on (an activation from the
  // bar opens targets, then triggers, then choices) it closes, and it never stays over the ending (it sat over the Defeat screen); a click
  // on the card opens it again. The selection itself stays (a decision reads it).
  const moment = view ? barMoment(view) : "";
  const pickedAt = useRef<{ sel: string[]; at: string } | null>(null);
  if (pickedAt.current?.sel !== selection) pickedAt.current = { sel: selection, at: moment }; // (a fresh pick is a new array)
  const stale = !!view && (pickedAt.current.at !== moment || gameEnded(view, perspective(view, actingAs)));
  const anchor = stale ? null : onTable[0] ?? null;
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
  // one click per activated ability (the card menu's Abilities rows): cost in symbols, the effect and any reason in the tooltip
  const abilities = onTable.length === 1 ? full.items.filter((i): i is Exclude<MenuItem, "separator"> => i !== "separator" && !!i.ability) : [];
  const chip = (id: Parameters<typeof keyLabel>[0]) => { const k = keyLabel(id, keymap); return k ? <kbd className="key-chip" aria-hidden>{k}</kbd> : null; };
  return (
    <div className="selection-bar anchored" data-testid="selection-bar" ref={ref} role="toolbar" aria-label="Selected card actions">
      <span className="sel-count">{onTable.length === 1 && isVisible(first) ? first.name : `${onTable.length} selected`}</span>
      {abilities.map((a, i) => (
        <button key={i} className="tt-btn sel-ability" data-testid="sel-ability" disabled={a.disabled} onClick={() => a.onClick?.()}
          title={`${a.ability!.effect}${a.disabled && a.ability!.why ? `\n${a.ability!.why}` : ""}`} aria-label={a.label}>
          <ManaText text={a.ability!.cost} /> <span className="sel-ab-what">{a.ability!.effect.length > 22 ? `${a.ability!.effect.slice(0, 20)}…` : a.ability!.effect}</span>
        </button>
      ))}
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
