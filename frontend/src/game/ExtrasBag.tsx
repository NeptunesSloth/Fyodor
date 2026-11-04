import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { CardFace } from "../cards/CardFace";
import { api } from "../services/api";
import { getPrintings, searchCards } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import type { CardData } from "../types/cards";
import { addCounter, changeResource, send } from "./actions";
import { BAG_DICE, CARD_COUNTERS, COMMON_TOKENS, commonBesidesDeck, deckTokenIds, matchesToken, PLAYER_COUNTERS, type ExtraToken } from "./bags";
import { keyLabel } from "./hotkeys";
import { isOut } from "./outOfGame";
import { dieIconUrl, seatIconUrl, tokenCardUrl, toyIconUrl, whenIconFontReady, type TokenEmblemId, type ToyIconId } from "./seatIcons";
import "./dice.css";
import "./tabletoys.css";

const COUNTS = [1, 2, 3, 5] as const;
/** From the click (a seat button's middle) to the panel's bottom: half the largest button and 8 px more. */
const BUTTON_CLEAR = 30;

/** The counters' names as the bag shows them. */
const COUNTER_LABEL: Record<string, string> = {
  "+1/+1": "+1/+1", "-1/-1": "−1/−1", loyalty: "Loyalty", charge: "Charge", shield: "Shield", stun: "Stun", energy: "Energy", experience: "Experience",
};

// -- the common tokens' printings ----------------------------------------------------------------------------------------

/** Found once a session: each common token's printing in the local card database, one with art when any printing has it. */
let found: Record<string, CardData> = {};
let finding: Promise<Record<string, CardData>> | null = null;
let askedForArt = false;
const listeners = new Set<(cards: Record<string, CardData>) => void>();

function commonTokenPrintings(): Promise<Record<string, CardData>> {
  finding ??= (async () => {
    const out: Record<string, CardData> = {};
    await Promise.all(COMMON_TOKENS.map(async (t) => {
      const name = t.token.name as string;
      const hits = await searchCards(`!${name}`, { tokens: "true", limit: 60 }).then((r) => r.results, () => [] as CardData[]);
      const match = hits.find((c) => matchesToken(c, t));
      if (!match) return;
      // the usual printing may have no art cached: another printing of the same token may
      const art = match.has_image ? match : (await getPrintings(match.id).catch(() => [] as CardData[])).find((c) => c.has_image && matchesToken(c, t));
      out[t.id] = art ?? match;
    }));
    useCardCache.getState().put(Object.values(out));
    found = out;
    if (!Object.keys(out).length) finding = null; // (no card database yet: ask again next time)
    else void askForArt(out);
    return out;
  })();
  return finding;
}

/**
 * Art for the common tokens that have none cached, fetched by the host the way it fetches a deck's (linked from Scryfall,
 * cached, never shipped), once a session. Only the host may, and only while online: anywhere else the request is
 * refused and the tokens keep their emblem cards. When it is done, the printings are looked up again.
 */
async function askForArt(cards: Record<string, CardData>): Promise<void> {
  const ids = Object.values(cards).filter((c) => !c.has_image).map((c) => c.id);
  if (askedForArt || !ids.length) return;
  askedForArt = true;
  const job = await api.post<{ id: string; state: string }>("/cards/cache-art", { ids }).catch(() => null);
  if (!job) return;
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => window.setTimeout(r, 2000));
    const state = await api.get<{ state: string }>(`/jobs/${job.id}`).catch(() => null);
    if (!state || state.state !== "running") break;
  }
  finding = null;
  const again = await commonTokenPrintings();
  for (const l of listeners) l(again);
}

function useCommonTokenPrintings(): Record<string, CardData> {
  const [cards, setCards] = useState(found);
  useEffect(() => {
    let live = true;
    const hear = (r: Record<string, CardData>) => live && setCards(r);
    listeners.add(hear);
    void commonTokenPrintings().then(hear);
    return () => { live = false; listeners.delete(hear); };
  }, []);
  return cards;
}

// -- tiles ------------------------------------------------------------------------------------------------------------

/**
 * A token in the bag: its card (the printing's art; a common token without art cached shows its emblem card instead), its
 * name and P/T; a click pulls `count` of it onto the table.
 */
function TokenTile({ card, emblem, name, pt, count, title, testId, onPull }: {
  card?: CardData | undefined; emblem?: string | undefined; name: string; pt?: string | null | undefined; count: number; title: string; testId?: string; onPull: () => void;
}) {
  const [pulls, setPulls] = useState(0);
  return (
    <button type="button" className="bag-tile" title={title} data-testid={testId} aria-label={`Create ${count} ${name}${pt ? ` ${pt}` : ""}`}
      onClick={() => { setPulls((n) => n + 1); onPull(); }}>
      <span className="bag-tile-card">
        {emblem && !card?.has_image ? <span className="card-face"><img src={emblem} alt={name} draggable={false} /></span> : <CardFace card={card} size="small" />}
      </span>
      <span className="bag-tile-cap">
        <span className="bag-tile-name">{name}</span>
        {pt && <span className="bag-tile-pt">{pt}</span>}
      </span>
      {pulls > 0 && <span key={pulls} className="bag-tile-pulled" aria-hidden>+{count}</span>}
    </button>
  );
}

/** A counter (or one of yours): a brass medallion with its name under it, like the dice. */
function CounterChip({ kind, label, disabled, title, onPull }: { kind: ToyIconId; label: string; disabled?: boolean; title: string; onPull: () => void }) {
  return (
    <button type="button" className="bag-chip" disabled={disabled} title={title} onClick={onPull} data-testid={`extras-counter-${kind}`}>
      <img src={toyIconUrl(kind)} alt="" draggable={false} />
      <span>{label}</span>
    </button>
  );
}

/**
 * -- table toys -- the Bag of Extras, by your seat (a seat button on both tables, game/seatActions.ts): an infinite bag of
 * the common extras, opened where you clicked it. Your deck's tokens and the common ones (Treasure, Clue, Food, Blood,
 * 1/1s) as cards with their art, the search for any other token, counters for the selected cards and for you, and dice
 * (and the roll panel, for a coin, the dice cannon and any other dice). Pulling one out sends the table's ordinary action
 * (create a token, a counter, a resource, a roll): nothing new for the rules engine, and a player who is out of the game
 * has no bag (the server refuses their objects). It stays open to pull several; Esc, its close button or a click
 * elsewhere closes it.
 */
export function ExtrasBag({ me, anchor, onClose }: { me: string; anchor: string | null; onClose: () => void }) {
  const view = useGame((s) => s.view);
  const selection = useGame((s) => s.selection);
  const cache = useCardCache((s) => s.cards);
  const keymap = usePrefs((s) => s.keymap);
  const panel = useRef<HTMLDivElement>(null);
  const [count, setCount] = useState<number>(1);
  const [place, setPlace] = useState<CSSProperties>({ visibility: "hidden" });
  const [, iconsReady] = useState(0);
  const common = useCommonTokenPrintings();
  const related = (id: string) => cache[id]?.related_tokens?.map((t) => t.id);
  const deck = useMemo(() => (view ? deckTokenIds(view, me, related, (id) => cache[id]) : []), [view, me, cache]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => requestCards(deck), [deck]);
  useEffect(() => { void whenIconFontReady().then(() => iconsReady(1)); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose();
    };
    const onDown = (e: PointerEvent) => {
      if (panel.current?.contains(e.target as Node)) return;
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [onClose]);
  // opened where it was clicked, its bottom clear of the button's top (the click is the button's middle), always whole on
  // screen, below the top bar and (on the 2D table) the opponents' strips, and beside my rail rather than over my plate
  useLayoutEffect(() => {
    const node = panel.current;
    if (!node) return;
    node.style.maxHeight = "";
    const [w, h] = [node.offsetWidth, node.offsetHeight];
    const at = anchor?.split(",").map(Number);
    const ok = !!at && at.length === 2 && at.every(Number.isFinite);
    const boxes = (sel: string) => [...document.querySelectorAll(sel)].map((n) => n.getBoundingClientRect()).filter((r) => r.width > 0);
    let x = ok ? at[0]! - w / 2 : window.innerWidth - w - 16;
    x = Math.max(8, Math.min(window.innerWidth - w - 8, x));
    for (const r of boxes(".player-area.mine .area-side")) if (x < r.right && x + w > r.left && r.right + 8 + w <= window.innerWidth - 8) x = r.right + 8;
    for (const r of boxes(".turn-dial-wrap")) if (x + w > r.left - 8 && x < r.right && r.left - 8 - w >= 8) x = r.left - 8 - w; // (and clear of the turn panel)
    // above the button when over it; moved aside (beside my rail), it may come down to the screen's foot
    const overButton = ok && at[0]! > x - 8 && at[0]! < x + w + 8;
    const bottom = overButton ? at[1]! - BUTTON_CLEAR : window.innerHeight - 8;
    const ceiling = Math.max(54, ...boxes(".game-top, .opponents .seat-strip, .t3d-cams").filter((r) => r.left < x + w && r.right > x && r.bottom < bottom).map((r) => r.bottom + 8));
    const room = Math.max(320, bottom - ceiling);
    const top = overButton ? Math.max(ceiling, Math.min(window.innerHeight - Math.min(h, room) - 8, bottom - h)) : ceiling;
    setPlace({ left: x, top, maxHeight: room });
  }, [anchor, deck.length]);
  if (!view || isOut(view, me)) return null;
  const onTable = selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield"));
  const make = (token: Record<string, unknown>) => void send({ type: "create_token", player: me, token, count });
  const emblemOf = (t: ExtraToken) => tokenCardUrl(t.id as TokenEmblemId, {
    name: t.label, type: t.token.type_line as string, pt: t.pt, colors: (t.token.colors as string[] | undefined) ?? [],
  });
  const commons = commonBesidesDeck(COMMON_TOKENS, common, deck.map((id) => cache[id]).filter((c): c is CardData => !!c));
  const target = onTable.length === 1 ? "the selected card" : `${onTable.length} selected cards`;
  const diceKey = keyLabel("dice", keymap);
  // (on the page itself, so it stands over the table's floating layers, such as the dice results on the 2D table)
  return createPortal(
    <div className="extras-panel" ref={panel} role="dialog" aria-label="Bag of Extras" style={place} data-testid="extras-panel">
      <div className="extras-inner">
      <header className="extras-head">
        <img className="extras-mark" src={seatIconUrl("extras")} alt="" draggable={false} />
        <h2 className="extras-title">Bag of Extras</h2>
        <div className="extras-count" role="group" aria-label="How many each pull makes">
          {COUNTS.map((n) => (
            <button key={n} type="button" className={count === n ? "on" : ""} aria-pressed={count === n} onClick={() => setCount(n)}>×{n}</button>
          ))}
        </div>
        <button type="button" className="extras-close" onClick={onClose} aria-label="Close the Bag of Extras (Esc)" title="Close (Esc)">
          <img src={toyIconUrl("close")} alt="" draggable={false} />
        </button>
      </header>
      <div className="extras-body">
        <div className="extras-tokens">
          {deck.length > 0 && (
            <section className="extras-group" aria-label="Your deck's tokens">
              <h3 className="extras-group-head">Your deck's tokens</h3>
              <div className="bag-tiles">
                {deck.map((id) => {
                  const card = cache[id];
                  const pt = card?.power != null ? `${card.power}/${card.toughness}` : null;
                  return <TokenTile key={id} card={card} name={card?.name ?? "…"} pt={pt} count={count} title={card ? `${card.name} — ${card.type_line ?? ""}` : "Token"}
                    onPull={() => make({ card_id: id })} />;
                })}
              </div>
            </section>
          )}
          <section className="extras-group" aria-label="Common tokens">
            <h3 className="extras-group-head">Tokens</h3>
            <div className="bag-tiles">
              {commons.map((t) => {
                const card = common[t.id];
                return <TokenTile key={t.id} card={card} emblem={emblemOf(t)} name={t.label} pt={t.pt} count={count} testId={`extras-${t.id}`}
                  title={`${t.token.type_line as string}${t.token.text ? `: ${t.token.text as string}` : ""}`}
                  onPull={() => make(card ? { card_id: card.id } : t.token)} />;
              })}
              <button type="button" className="bag-tile bag-find" onClick={() => useGame.getState().openDialog("tokens")} data-testid="extras-find-token"
                title="Search every token in the card database, or make a custom one">
                <span className="bag-tile-card bag-find-slot"><img src={toyIconUrl("search")} alt="" draggable={false} /></span>
                <span className="bag-tile-cap"><span className="bag-tile-name">Find any token…</span></span>
              </button>
            </div>
          </section>
        </div>
        <div className="extras-side">
          <section className="extras-group" aria-label="Counters">
            <h3 className="extras-group-head">Counters</h3>
            <p className={`extras-for ${onTable.length ? "" : "idle"}`}>{onTable.length ? `On ${target}` : "Select cards on the battlefield first"}</p>
            <div className="bag-chips">
              {CARD_COUNTERS.map((k) => (
                <CounterChip key={k} kind={k} label={COUNTER_LABEL[k] ?? k} disabled={!onTable.length}
                  title={onTable.length ? `Put ${count} ${k} counter${count > 1 ? "s" : ""} on ${target}` : "Select cards on the battlefield first"}
                  onPull={() => void addCounter(onTable, k, count)} />
              ))}
            </div>
            <p className="extras-for">On you</p>
            <div className="bag-chips">
              {PLAYER_COUNTERS.map((k) => (
                <CounterChip key={k} kind={k} label={COUNTER_LABEL[k] ?? k} title={`Give yourself ${count} ${k}`} onPull={() => void changeResource(me, k, count)} />
              ))}
            </div>
          </section>
          <section className="extras-group" aria-label="Dice">
            <h3 className="extras-group-head">Dice</h3>
            <div className="bag-dice">
              {BAG_DICE.map((sides) => (
                <button key={sides} type="button" className="bag-die" onClick={() => void send({ type: "roll", sides, count })}
                  title={`Roll ${count > 1 ? count : ""}d${sides}`} aria-label={`Roll ${count > 1 ? count : "a"} d${sides}`} data-testid={`extras-d${sides}`}>
                  <img src={dieIconUrl(sides)} alt="" draggable={false} />
                  <span>d{sides}</span>
                </button>
              ))}
            </div>
            <button type="button" className="bag-more" onClick={() => useGame.getState().openDialog("dice")} data-testid="dice-button"
              title={`The roll panel: any dice, a coin, the dice cannon and the draw bag${diceKey ? ` (${diceKey})` : ""}`}>
              <span>Coin, cannon &amp; more…</span>
              {diceKey && <kbd>{diceKey}</kbd>}
            </button>
          </section>
        </div>
      </div>
      <p className="extras-note">The bag never runs out. Each pull is the table's own action; Ctrl+Z takes it back.</p>
      </div>
    </div>,
    document.body,
  );
}
