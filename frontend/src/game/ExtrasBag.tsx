import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { addCounter, changeResource, send } from "./actions";
import { BAG_DICE, CARD_COUNTERS, COMMON_TOKENS, deckTokenIds, PLAYER_COUNTERS } from "./bags";
import { isOut } from "./outOfGame";
import "./dice.css";
import "./tabletoys.css";

const COUNTS = [1, 2, 3, 5] as const;

/**
 * -- table toys -- the Bag of Extras, by your seat (a seat button on both tables, game/seatActions.ts): an infinite bag of the
 * common extras, opened where you clicked it. Your deck's tokens, Treasure, Clue, Food, Blood and 1/1s, counters for the
 * selected cards and for you, and dice. Pulling one out sends the table's ordinary action (create a token, a counter, a
 * resource, a roll): nothing new for the rules engine, and a player who is out of the game has no bag (the server refuses
 * their objects). It stays open to pull several; Esc or a click elsewhere closes it.
 */
export function ExtrasBag({ me, anchor, onClose }: { me: string; anchor: string | null; onClose: () => void }) {
  const view = useGame((s) => s.view);
  const selection = useGame((s) => s.selection);
  const cache = useCardCache((s) => s.cards);
  const panel = useRef<HTMLDivElement>(null);
  const [count, setCount] = useState<number>(1);
  const related = (id: string) => cache[id]?.related_tokens?.map((t) => t.id);
  const deck = useMemo(() => (view ? deckTokenIds(view, me, related) : []), [view, me, cache]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => requestCards(deck), [deck]);
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
  if (!view || isOut(view, me)) return null;
  const onTable = selection.filter((id) => view.cards[id]?.zone.endsWith(":battlefield"));
  const make = (token: Record<string, unknown>) => void send({ type: "create_token", player: me, token, count });
  // opened where it was clicked (above the point), or by the seat buttons' corner
  const at = anchor?.split(",").map(Number);
  const style: CSSProperties = at && at.length === 2 && at.every(Number.isFinite)
    ? { left: Math.max(8, Math.min(window.innerWidth - 344, at[0]! - 168)), bottom: Math.max(8, window.innerHeight - at[1]! + 14) }
    : { right: 16, bottom: 72 };
  return (
    <div className="extras-panel" ref={panel} role="dialog" aria-label="Bag of Extras" style={style} data-testid="extras-panel">
      <div className="extras-head">
        <span className="extras-title">Bag of Extras</span>
        <span className="spacer" />
        <div className="seg" role="group" aria-label="How many">
          {COUNTS.map((n) => (
            <button key={n} type="button" className={count === n ? "on" : ""} aria-pressed={count === n} onClick={() => setCount(n)}>×{n}</button>
          ))}
        </div>
      </div>
      {deck.length > 0 && (
        <section className="extras-group" aria-label="Your deck's tokens">
          <div className="extras-group-head">Your deck's tokens</div>
          <div className="extras-items">
            {deck.map((id) => {
              const card = cache[id];
              return (
                <button key={id} type="button" className="extras-item" onClick={() => make({ card_id: id })} title={card ? `${card.name} — ${card.type_line ?? ""}` : "Token"}>
                  <span className="chip" aria-hidden>{(card?.name ?? "?").slice(0, 1)}</span>
                  {card?.power != null && <span className="pt">{card.power}/{card.toughness}</span>}
                  {card?.name ?? "…"}
                </button>
              );
            })}
          </div>
        </section>
      )}
      <section className="extras-group" aria-label="Common tokens">
        <div className="extras-group-head">Tokens</div>
        <div className="extras-items">
          {COMMON_TOKENS.map((t) => (
            <button key={t.id} type="button" className="extras-item" onClick={() => make(t.token)} style={{ ["--tint" as string]: t.tint }}
              title={`${t.token.type_line as string}${t.token.text ? `: ${t.token.text as string}` : ""}`} data-testid={`extras-${t.id}`}>
              <span className="chip" aria-hidden>{t.label.slice(0, 1)}</span>
              {t.pt && <span className="pt">{t.pt}</span>}
              {t.label}
            </button>
          ))}
        </div>
      </section>
      <section className="extras-group" aria-label="Counters">
        <div className="extras-group-head">Counters {onTable.length ? `on ${onTable.length === 1 ? "the selected card" : `${onTable.length} selected cards`}` : "(select cards on the battlefield)"}</div>
        <div className="extras-items">
          {CARD_COUNTERS.map((k) => (
            <button key={k} type="button" className="extras-item" disabled={!onTable.length} onClick={() => void addCounter(onTable, k, count)}>
              <span className="chip" aria-hidden>{k.startsWith("+") || k.startsWith("-") ? k.slice(0, 2) : k.slice(0, 1).toUpperCase()}</span>{k}
            </button>
          ))}
          {PLAYER_COUNTERS.map((k) => (
            <button key={k} type="button" className="extras-item" onClick={() => void changeResource(me, k, count)} title={`Give yourself ${count} ${k}`}>
              <span className="chip" aria-hidden>{k.slice(0, 1).toUpperCase()}</span>Your {k}
            </button>
          ))}
        </div>
      </section>
      <section className="extras-group" aria-label="Dice">
        <div className="extras-group-head">Dice</div>
        <div className="extras-items">
          {BAG_DICE.map((sides) => (
            <button key={sides} type="button" className="extras-item" onClick={() => void send({ type: "roll", sides, count })}>
              <span className="chip" aria-hidden>{sides}</span>Roll {count > 1 ? count : ""}d{sides}
            </button>
          ))}
        </div>
      </section>
      <p className="extras-note">It never runs out. Each pull is the table's own action: a token appears on your battlefield, and Ctrl+Z takes it back.</p>
    </div>
  );
}
