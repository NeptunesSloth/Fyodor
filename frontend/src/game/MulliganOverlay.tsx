import { useEffect, useMemo, useState } from "react";
import { perspective, playerName, useGame } from "../state/gameStore";
import type { GameView, MulliganPolicy, PregameSeat } from "../types/game";
import { send } from "./actions";
import { GameCardFace } from "./GameCardFace";
import { useHoverCard } from "./hoverCard";

const toBottom = (policy: MulliganPolicy, mulligans: number) => Math.max(0, mulligans - policy.free_mulligans) * policy.cards_to_bottom;

const nameOf = (card: GameView["cards"][string] | undefined): string => (card && "name" in card && card.name ? card.name : "Exile hand");

function describe(seat: PregameSeat): string {
  if (seat.status === "kept") return seat.to_bottom ? "Kept" : `Kept ${seat.kept ?? ""}`.trim();
  if (seat.status === "bottoming") return `Choosing ${seat.to_bottom} for the bottom`;
  return seat.mulligans ? `Deciding · ${seat.mulligans} mulligan${seat.mulligans > 1 ? "s" : ""}` : "Deciding";
}

/**
 * Opening hands: keep or mulligan, then choose exactly N cards for the bottom. Every player
 * decides at the same time; the game proper starts when all have kept (or the host overrides).
 */
export function MulliganOverlay() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const [collapsed, setCollapsed] = useState(false);
  if (!view?.pregame || view.pregame.finished) return null;
  const policy = view.game.settings.mulligan;
  if (!policy) return null;
  const me = perspective(view, actingAs);
  const mySeat = view.viewer === "__spectator__" ? undefined : view.pregame.seats[me];
  const isHost = view.game.mode === "local" || view.game.host_seat === view.viewer;

  if (collapsed) {
    return (
      <button className="mull-pill tt-btn" onClick={() => setCollapsed(false)} data-testid="mulligan-reopen">
        Opening hands · {mySeat ? describe(mySeat) : "in progress"}
      </button>
    );
  }
  return (
    <div className="mull-overlay" data-testid="mulligan">
      <div className="mull-panel">
        <header className="mull-head">
          <div>
            <h2>Opening hand</h2>
            <span className="hint">{policy.display_name}{policy.free_mulligans ? ` · first ${policy.free_mulligans > 1 ? `${policy.free_mulligans} mulligans are` : "mulligan is"} free` : ""}</span>
          </div>
          <span className="spacer" />
          <button className="tt-btn ghost" onClick={() => setCollapsed(true)} title="Look at the table">Hide</button>
        </header>
        {mySeat && <MyDecision view={view} me={me} seat={mySeat} policy={policy} />}
        <div className="mull-seats">
          {view.seat_order.map((pid) => {
            const seat = view.pregame!.seats[pid];
            if (!seat) return null;
            return (
              <div key={pid} className={`mull-seat ${seat.status}`} data-testid={`mull-seat-${pid}`}>
                <b>{playerName(view, pid)}{pid === me ? " (you)" : ""}</b>
                <span>{describe(seat)}</span>
              </div>
            );
          })}
        </div>
        {isHost && (
          <footer className="mull-foot">
            <span className="hint">Everyone decides at the same time. The game starts when all have kept.</span>
            <span className="spacer" />
            <button className="tt-btn" data-testid="mulligan-override" onClick={() => {
              if (window.confirm("Start the game now? Anyone still deciding keeps the hand they hold.")) void send({ type: "mulligan_finish" });
            }}>Start now</button>
          </footer>
        )}
      </div>
    </div>
  );
}

function MyDecision({ view, me, seat, policy }: { view: GameView; me: string; seat: PregameSeat; policy: MulliganPolicy }) {
  const hover = useHoverCard();
  const handKey = `${me}:hand`;
  const zone = view.zones[handKey];
  const hand = useMemo(() => (Array.isArray(zone) ? zone : []), [zone]);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => setPicked((p) => p.filter((id) => hand.includes(id))), [hand]);
  useEffect(() => setPicked([]), [seat.status, seat.mulligans]);

  const act = async (action: Record<string, unknown>) => {
    setBusy(true);
    await send({ ...action, type: String(action.type) });
    setBusy(false);
  };
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  if (seat.status === "kept") {
    const waiting = Object.entries(view.pregame!.seats).filter(([, s]) => s.status !== "kept").map(([pid]) => playerName(view, pid));
    return <p className="mull-note">You kept {seat.kept} cards. Waiting for {waiting.join(", ") || "the table"}…</p>;
  }

  const bottoming = seat.status === "bottoming";
  const need = seat.to_bottom;
  const selectable = bottoming || policy.partial_hand_selection;
  const nextBottom = toBottom(policy, seat.mulligans + 1);
  const nextKeep = policy.draw_count - Math.min(policy.draw_count, nextBottom);
  const maxed = policy.max_mulligans != null && seat.mulligans >= policy.max_mulligans;
  const tooSmall = nextKeep < policy.minimum_hand_size;
  const keepNow = hand.length - Math.min(hand.length, toBottom(policy, seat.mulligans));

  return (
    <div className="mull-mine">
      <p className="mull-note">
        {bottoming ? (
          <>Choose <b>exactly {need}</b> card{need > 1 ? "s" : ""} to put on the bottom of your library. The last one you pick goes to the very bottom.</>
        ) : seat.mulligans === 0 ? (
          <>Keep these {hand.length} or take a mulligan.</>
        ) : (
          <>Mulligan #{seat.mulligans}. Keep {hand.length === keepNow ? hand.length : `${hand.length} and bottom ${hand.length - keepNow}`}, or go again.</>
        )}
        {!bottoming && policy.partial_hand_selection && <> Select cards to send back only those.</>}
      </p>
      <div className="mull-hand">
        {hand.map((id) => {
          const card = view.cards[id];
          if (!card) return null;
          const order = picked.indexOf(id);
          return (
            <button
              key={id}
              className={`mull-card ${order >= 0 ? "picked" : ""}`}
              disabled={!selectable || busy}
              onClick={() => toggle(id)}
              {...hover(id)}
              data-testid="mull-card"
            >
              <GameCardFace card={card} />
              {order >= 0 && <span className="mull-order">{order + 1}</span>}
            </button>
          );
        })}
      </div>
      <div className="mull-actions">
        {bottoming ? (
          <>
            <span className={`mull-count ${picked.length === need ? "ok" : ""}`} data-testid="mull-count">Selected {picked.length} / {need}</span>
            <span className="spacer" />
            <button className="tt-btn ghost" disabled={!picked.length || busy} onClick={() => setPicked([])}>Clear</button>
            <button className="tt-btn brass" data-testid="mull-confirm" disabled={picked.length !== need || busy}
              onClick={() => void act({ type: "mulligan_bottom", card_ids: picked })}>
              Put {need} on the bottom
            </button>
          </>
        ) : (
          <>
            <button className="tt-btn" data-testid="mull-take" disabled={busy || maxed || tooSmall || policy.needs_definition}
              title={policy.needs_definition ? "The host hasn't defined this mulligan rule yet" : maxed ? "No more mulligans" : tooSmall ? `Can't go below ${policy.minimum_hand_size}` : undefined}
              onClick={() => void act(picked.length ? { type: "mulligan_take", card_ids: picked } : { type: "mulligan_take" })}>
              {picked.length ? `Send back ${picked.length}` : "Mulligan"}
            </button>
            {(view.pregame?.mine?.powder ?? []).filter((id) => hand.includes(id)).map((id) => (
              // 103.5b: "any time you could mulligan" (Serum Powder): exile the hand and draw that many; not a mulligan
              <button key={id} className="tt-btn" data-testid="mull-powder" disabled={busy}
                title="Exile all the cards from your hand, then draw that many cards (not a mulligan)"
                onClick={() => void act({ type: "mulligan_powder", card_id: id })}>
                {nameOf(view.cards[id])}: exile hand, draw {hand.length}
              </button>
            ))}
            <span className="spacer" />
            <button className="tt-btn brass" data-testid="mull-keep" disabled={busy || picked.length > 0} onClick={() => void act({ type: "mulligan_keep" })}>
              Keep {hand.length}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
