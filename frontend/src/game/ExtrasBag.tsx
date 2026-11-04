import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { CardFace, type CustomFace } from "../cards/CardFace";
import { Icon } from "../components/Icon";
import { getPrintings, searchCards } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import type { CardData } from "../types/cards";
import { addCounter, changeResource, send } from "./actions";
import { BAG_DICE, CARD_COUNTERS, COMMON_TOKENS, deckTokenIds, matchesToken, PLAYER_COUNTERS, type ExtraToken } from "./bags";
import { keyLabel } from "./hotkeys";
import { isOut } from "./outOfGame";
import { dieIconUrl, seatIconUrl, toyIconUrl, whenIconFontReady, type ToyIconId } from "./seatIcons";
import "./dice.css";
import "./tabletoys.css";

const COUNTS = [1, 2, 3, 5] as const;

/** The counters' names as the bag shows them. */
const COUNTER_LABEL: Record<string, string> = {
  "+1/+1": "+1/+1", "-1/-1": "−1/−1", loyalty: "Loyalty", charge: "Charge", shield: "Shield", stun: "Stun", energy: "Energy", experience: "Experience",
};

// -- the common tokens' printings ----------------------------------------------------------------------------------------

/** Found once a session: each common token's printing in the local card database, one with art when any printing has it. */
let found: Record<string, CardData> = {};
let finding: Promise<Record<string, CardData>> | null = null;

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
    return out;
  })();
  return finding;
}

function useCommonTokenPrintings(): Record<string, CardData> {
  const [cards, setCards] = useState(found);
  useEffect(() => {
    let live = true;
    void commonTokenPrintings().then((r) => live && setCards(r));
    return () => { live = false; };
  }, []);
  return cards;
}

// -- tiles ------------------------------------------------------------------------------------------------------------

/** A token in the bag: its card (art, or the designed proxy), its name and P/T; a click pulls `count` of it onto the table. */
function TokenTile({ card, custom, name, pt, count, title, testId, onPull }: {
  card?: CardData | undefined; custom?: CustomFace; name: string; pt?: string | null | undefined; count: number; title: string; testId?: string; onPull: () => void;
}) {
  const [pulls, setPulls] = useState(0);
  return (
    <button type="button" className="bag-tile" title={title} data-testid={testId} aria-label={`Create ${count} ${name}${pt ? ` ${pt}` : ""}`}
      onClick={() => { setPulls((n) => n + 1); onPull(); }}>
      <span className="bag-tile-card"><CardFace card={card} custom={card ? undefined : custom} size="small" /></span>
      <span className="bag-tile-cap">
        <span className="bag-tile-name">{name}</span>
        {pt && <span className="bag-tile-pt">{pt}</span>}
      </span>
      {pulls > 0 && <span key={pulls} className="bag-tile-pulled" aria-hidden>+{count}</span>}
    </button>
  );
}

/** A counter (or one of yours): its medallion and name. */
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
  // opened where it was clicked, just above the point (or by the seat buttons' corner), always whole on screen
  useLayoutEffect(() => {
    const node = panel.current;
    if (!node) return;
    const [w, h] = [node.offsetWidth, node.offsetHeight];
    const at = anchor?.split(",").map(Number);
    const ok = !!at && at.length === 2 && at.every(Number.isFinite);
    const x = ok ? at[0]! - w / 2 : window.innerWidth - w - 16;
    const y = ok ? at[1]! - h - 14 : window.innerHeight - h - 72;
    setPlace({ left: Math.max(8, Math.min(window.innerWidth - w - 8, x)), top: Math.max(54, Math.min(window.innerHeight - h - 8, y)) });
  }, [anchor, deck.length]);
  if (!view || isOut(view, me)) return null;
  const onTable = selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield"));
  const make = (token: Record<string, unknown>) => void send({ type: "create_token", player: me, token, count });
  const commonFace = (t: ExtraToken): CustomFace => ({
    name: t.label, type_line: t.token.type_line as string, oracle_text: (t.token.text as string | undefined) ?? "",
    power: (t.token.power as string | undefined) ?? null, toughness: (t.token.toughness as string | undefined) ?? null, colors: (t.token.colors as string[] | undefined) ?? [],
  });
  const target = onTable.length === 1 ? "the selected card" : `${onTable.length} selected cards`;
  const diceKey = keyLabel("dice", keymap);
  return (
    <div className="extras-panel" ref={panel} role="dialog" aria-label="Bag of Extras" style={place} data-testid="extras-panel">
      <header className="extras-head">
        <img className="extras-mark" src={seatIconUrl("extras")} alt="" draggable={false} />
        <h2 className="extras-title">Bag of Extras</h2>
        <div className="extras-count" role="group" aria-label="How many each pull makes">
          {COUNTS.map((n) => (
            <button key={n} type="button" className={count === n ? "on" : ""} aria-pressed={count === n} onClick={() => setCount(n)}>×{n}</button>
          ))}
        </div>
        <button type="button" className="extras-close" onClick={onClose} aria-label="Close the Bag of Extras (Esc)" title="Close (Esc)"><Icon name="close" size={12} /></button>
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
              {COMMON_TOKENS.map((t) => {
                const card = common[t.id];
                return <TokenTile key={t.id} card={card} custom={commonFace(t)} name={t.label} pt={t.pt} count={count} testId={`extras-${t.id}`}
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
  );
}
