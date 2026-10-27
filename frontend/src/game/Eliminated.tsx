import { useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { toastError } from "../components/Toasts";
import { ownDeck, type OwnDeckCard } from "../services/night";
import { requestCards, useCardCache } from "../state/cardCache";
import { usePrefs } from "../state/prefs";
import type { GameView } from "../types/game";

/*
 * ELIMINATED (3D_DIRECTION.md §7a, ELIMINATION_HUB.md): only the eliminated player sees it. A short
 * dark pulse, "Eliminated — the game continues", then a small hub: keep watching (the same public
 * view everyone else has; elimination grants nothing hidden), practise opening hands with your own
 * deck (local to this browser, never part of the live game), or leave the table.
 */
export function Eliminated({ view, me, sceneOn }: { view: GameView; me: string; sceneOn: boolean }) {
  const key = `fyodor.night.out.${view.game.id}.${view.game.night?.number ?? 1}.${me}`;
  const [stage, setStage] = useState<"scene" | "hub" | "pill">(() => {
    try {
      if (sessionStorage.getItem(key) === "1") return "pill";
    } catch {
      /* show it */
    }
    return sceneOn ? "scene" : "hub";
  });
  const [practice, setPractice] = useState(false);
  const speed = usePrefs((s) => s.animationSpeed) || 1;
  useEffect(() => {
    if (stage !== "scene") return;
    const t = window.setTimeout(() => setStage("hub"), 1600 / speed);
    return () => window.clearTimeout(t);
  }, [stage, speed]);
  const settle = () => {
    try {
      sessionStorage.setItem(key, "1");
    } catch {
      /* fine */
    }
    setStage("pill");
  };
  const local = view.game.mode === "local";

  return (
    <>
      {stage === "scene" && (
        <div className="night-spot eliminated" role="status" aria-live="polite" data-testid="eliminated-scene" onClick={() => setStage("hub")}>
          <div className="night-spot-inner">
            <div className="night-word">Eliminated</div>
            <div className="night-rule" aria-hidden />
            <div className="night-winner">The game continues</div>
          </div>
        </div>
      )}
      {stage === "hub" && (
        <div className="night-result plaque-wrap" data-testid="eliminated-hub">
          <div className="plaque night-result-body">
            <div className="night-result-head">
              <span className="night-result-word defeat">Eliminated</span>
              <span className="night-result-line">The game goes on. You still see the table as everyone else does.</span>
            </div>
            <div className="night-actions">
              {!local && <a className="tt-btn" href="#/play">Leave table</a>}
              <button className="tt-btn" onClick={() => { settle(); setPractice(true); }}>Practise opening hands</button>
              <button className="tt-btn brass" onClick={settle}>Keep watching</button>
            </div>
          </div>
        </div>
      )}
      {stage === "pill" && !practice && (
        <button className="night-pill tt-btn" onClick={() => setPractice(true)} title="Draw opening hands from your deck while the game goes on">
          You're out · Practise opening hands
        </button>
      )}
      {practice && <HandSimulator gameId={view.game.id} viewer={local ? me : undefined} onClose={() => setPractice(false)} />}
    </>
  );
}

function shuffled<T>(xs: T[]): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

/** DRAW 7 · MULLIGAN · DRAW A CARD · RESET, with your own deck. Nothing here touches the live game. */
function HandSimulator({ gameId, viewer, onClose }: { gameId: string; viewer?: string; onClose: () => void }) {
  const [deck, setDeck] = useState<OwnDeckCard[] | null>(null);
  const [library, setLibrary] = useState<OwnDeckCard[]>([]);
  const [hand, setHand] = useState<OwnDeckCard[]>([]);
  const [mulligans, setMulligans] = useState(0);
  useEffect(() => {
    ownDeck(gameId, viewer).then((d) => {
      setDeck(d.cards);
      requestCards(d.cards.flatMap((c) => (c.printing_id ? [c.printing_id] : [])));
    }, (e) => {
      toastError(e);
      onClose();
    });
  }, [gameId, viewer, onClose]);
  const cards = useMemo(() => (deck ?? []).filter((c) => c.section === "main").flatMap((c) => Array.from({ length: c.quantity }, () => c)), [deck]);
  const deal = (mull: number) => {
    const lib = shuffled(cards);
    setHand(lib.slice(0, 7));
    setLibrary(lib.slice(7));
    setMulligans(mull);
  };
  useEffect(() => {
    if (cards.length) deal(0);
  }, [cards]); // eslint-disable-line react-hooks/exhaustive-deps
  const draw = () => {
    if (!library.length) return;
    setHand((h) => [...h, library[0]!]);
    setLibrary((l) => l.slice(1));
  };
  return (
    <Modal wide title="Opening hand practice" onClose={onClose} footer={
      <>
        <span className="hint">{deck ? `${library.length} cards in library${mulligans ? ` · mulligan ${mulligans}` : ""}` : "Loading your deck…"}</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={() => deal(0)} disabled={!cards.length}>Reset</button>
        <button className="tt-btn" onClick={draw} disabled={!library.length}>Draw a card</button>
        <button className="tt-btn" onClick={() => deal(mulligans + 1)} disabled={!cards.length}>Mulligan</button>
        <button className="tt-btn brass" onClick={() => deal(0)} disabled={!cards.length}>New 7</button>
      </>
    }>
      <p className="hint">Your own deck, shuffled in this browser only. Nothing here reaches the live game.</p>
      <div className="sim-hand" data-testid="hand-sim">
        {hand.map((c, i) => <SimCard key={`${i}-${c.name}`} card={c} />)}
      </div>
    </Modal>
  );
}

function SimCard({ card }: { card: OwnDeckCard }) {
  const data = useCardCache((s) => (card.printing_id ? s.cards[card.printing_id] : undefined));
  return (
    <div className="sim-card">
      <CardFace card={data} custom={data ? undefined : { name: card.name }} />
    </div>
  );
}
