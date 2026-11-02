import { useCallback, useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { rememberMyDeck, rememberSeat } from "../services/games";
import { deckLabCopy, openPractice, ownDeck, type OwnDeckCard } from "../services/night";
import { requestCards, useCardCache } from "../state/cardCache";
import { usePrefs } from "../state/prefs";
import type { GameView } from "../types/game";
import { commandersOf, rememberPractice } from "./eliminationHub";
import { SideActivityDialog, type SideActivity } from "./SpectatorHub";
import "./elimination.css";

/*
 * ELIMINATED (3D_DIRECTION.md §7a, ELIMINATION_HUB.md): only the eliminated player sees it. A short
 * dark pulse, "Eliminated — the game continues", then a small hub: keep watching (the same public
 * view everyone else has; elimination grants nothing hidden), a private practice table with your own
 * deck (a separate game only you see; the live game is untouched), opening-hand practice (local to this
 * browser), Deck Lab (a copy of your deck for the next game), dice & toys (local to this browser), pod stats and the
 * card browser (new tabs, so the live game keeps its seat), or leave the table. The pill brings the hub back.
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
  const [activity, setActivity] = useState<null | "hands" | "lab" | SideActivity>(null);
  const [busy, setBusy] = useState(false);
  // stable: the live table re-renders this on every action, and a new onClose would reload (and reset) the activity
  const closeActivity = useCallback(() => setActivity(null), []);
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
  const viewer = local ? me : undefined;
  const open = (what: "hands" | "lab" | SideActivity) => {
    settle();
    setActivity(what);
  };
  const practiceTable = async () => {
    setBusy(true);
    try {
      const table = await openPractice(view.game.id, { viewer });
      rememberSeat(table.game_id, table.token);
      rememberPractice(table.game_id, { of: view.game.id, seat: me, game: view.game.night?.number ?? 1, local });
      settle();
      if (table.resumed) toast("Back at your practice table.");
      window.location.hash = `#/game/${encodeURIComponent(table.game_id)}`;
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

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
              <button className="tt-btn" disabled={busy} data-testid="open-practice" onClick={() => void practiceTable()}
                title="A private table with your own deck: shuffle, draw, mulligan, play, tokens, counters, undo. Only you see it.">
                Practice table
              </button>
              <button className="tt-btn" onClick={() => open("hands")} title="Draw 7, mulligan, reset: quick opening hands from your deck">Opening hands</button>
              <button className="tt-btn" data-testid="open-deck-lab" onClick={() => open("lab")}
                title="Edit a copy of your deck for the next game (the deck in this game never changes)">
                Deck Lab
              </button>
              <button className="tt-btn" data-testid="open-sandbox" onClick={() => open("sandbox")}
                title="Was that attack lethal? Try out a combat on the public board; the game never changes">
                Damage sandbox
              </button>
              {!local && (
                <button className="tt-btn" data-testid="open-next-game" onClick={() => open("next")}
                  title="Queue the deck you want for the next game; the lobby proposes it when the pod returns there">
                  Next game
                </button>
              )}
              <button className="tt-btn brass" onClick={settle}>Keep watching</button>
            </div>
            <div className="elim-links">
              {!local && <button className="elim-link" data-testid="open-predictions" onClick={() => open("predictions")}>Predictions</button>}
              <button className="elim-link" data-testid="open-toys" onClick={() => open("toys")}
                title="Roll some dice, spin for a random player, keep a tally: only in this browser, the game never changes">
                Dice & toys
              </button>
              <a href="#/stats" target="_blank" rel="noopener noreferrer">Pod stats ↗</a>
              <a href="#/cards" target="_blank" rel="noopener noreferrer">Card browser ↗</a>
              {!local && <a href="#/play">Leave table</a>}
            </div>
          </div>
        </div>
      )}
      {stage === "pill" && !activity && (
        <button className="night-pill tt-btn" data-testid="eliminated-pill" onClick={() => setStage("hub")}
          title="Practice table, damage sandbox, next game, predictions, Deck Lab, dice & toys: things to do while the game goes on">
          You're out · Things to do
        </button>
      )}
      {activity === "hands" && <HandSimulator gameId={view.game.id} viewer={viewer} onClose={closeActivity} />}
      {activity === "lab" && <DeckLab gameId={view.game.id} viewer={viewer} onClose={closeActivity} />}
      {activity !== "hands" && activity !== "lab" && <SideActivityDialog activity={activity} view={view} viewer={viewer} onClose={closeActivity} />}
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

/**
 * DECK LAB: a copy of the deck you brought, for the next game. On the host computer the copy is a new deck in the
 * library, opened in the deck editor in a new tab (this table keeps your seat). On another computer it is the list,
 * to edit here and keep in this browser's My decks. The deck in this game is never changed; the lobby is where the
 * next deck is chosen.
 */
function DeckLab({ gameId, viewer, onClose }: { gameId: string; viewer?: string; onClose: () => void }) {
  const [copy, setCopy] = useState<Awaited<ReturnType<typeof deckLabCopy>> | null>(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    deckLabCopy(gameId, viewer).then((c) => {
      setCopy(c);
      setName(c.name);
      setText(c.text);
    }, (e) => {
      toastError(e);
      onClose();
    });
  }, [gameId, viewer, onClose]);
  const save = () => {
    try {
      const deckName = name.trim() || copy?.name || "Deck";
      rememberMyDeck(deckName, { name: deckName, text }, commandersOf(text));
      setSaved(true);
      toast(`${deckName} is in My decks: pick it in the lobby for the next game.`);
    } catch (e) {
      toastError(e);
    }
  };
  const editor = copy?.deck_id ? `#/decks/${encodeURIComponent(copy.deck_id)}` : null;
  return (
    <Modal wide title="Deck Lab" onClose={onClose} footer={
      <>
        <span className="hint">The deck in this game never changes. Choose the next deck in the lobby.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={onClose}>Close</button>
        {editor ? (
          <a className="tt-btn brass" href={editor} target="_blank" rel="noopener noreferrer" data-testid="deck-lab-editor">Open in the deck editor ↗</a>
        ) : (
          <button className="tt-btn brass" disabled={!copy || !text.trim()} onClick={save} data-testid="deck-lab-save">
            {saved ? "Saved — save again" : "Save to My decks"}
          </button>
        )}
      </>
    }>
      {!copy ? (
        <p className="hint">Copying your deck…</p>
      ) : editor ? (
        <p>A copy of your deck is in the deck library as <b>{copy.name}</b>. Edit it in the deck editor (a new tab, so you
          keep your seat here) and pick it in the lobby for the next game.</p>
      ) : (
        <>
          <p className="hint">A copy of the list you brought to this game. Edit it, then keep it in this browser's My decks.</p>
          <label className="deck-lab-name">Name <input value={name} maxLength={120} onChange={(e) => { setName(e.target.value); setSaved(false); }} /></label>
          <textarea className="deck-lab-text" aria-label="Deck list" spellCheck={false} value={text}
            onChange={(e) => { setText(e.target.value); setSaved(false); }} />
        </>
      )}
    </Modal>
  );
}
