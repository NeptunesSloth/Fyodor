import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { rememberMyDeck, rememberSeat } from "../services/games";
import { deckLabCopy, openPractice, ownDeck, type OwnDeckCard } from "../services/night";
import { getDeck } from "../services/decks";
import { requestCards, useCardCache } from "../state/cardCache";
import type { GameView } from "../types/game";
import { commandersOf, openGameLog, rememberPractice } from "./eliminationHub";
import { compareDecks, deckLines, type DeckComparison } from "./deckCompare";
import { DeckChanges } from "./DeckChanges";
import { playEndScene, type EndPlay } from "./motion/endScene";
import { SideActivityDialog, type SideActivity } from "./SpectatorHub";
import "./elimination.css";

/*
 * ELIMINATED (3D_DIRECTION.md §7a, ELIMINATION_HUB.md): only the eliminated player sees it. A short
 * dark pulse, "Eliminated — the game continues", then a small hub: keep watching (the same public
 * view everyone else has; elimination grants nothing hidden), a private practice table with your own
 * deck (a separate game only you see; the live game is untouched), opening-hand practice (local to this
 * browser), Deck Lab (a copy of your deck for the next game), dice & toys (local to this browser), the game log (the table's
 * own log drawer), pod stats and the
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
  // the table's short, quiet reaction (motion/endScene.ts), for this player only; a key, a click or its end opens the hub
  const scene = useRef<EndPlay | null>(null);
  useEffect(() => {
    if (stage !== "scene") return;
    const play = playEndScene("eliminated", () => setStage("hub"));
    scene.current = play;
    return () => play.stop();
  }, [stage]);
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
        <div className="night-spot eliminated" role="status" aria-live="polite" data-testid="eliminated-scene" onClick={() => {
          scene.current?.stop();
          setStage("hub");
        }}>
          <div className="night-spot-inner">
            <div className="night-word">Eliminated</div>
            <div className="night-rule" aria-hidden />
            <div className="night-winner">The game continues</div>
          </div>
        </div>
      )}
      {stage === "hub" && (
        <div className="night-result plaque-wrap elim-hub" data-testid="eliminated-hub">
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
              <button className="elim-link" data-testid="open-game-log" onClick={() => { settle(); openGameLog(); }}
                title="The game log: every public action and the table's chat, as everyone at the table reads it">
                Game log
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
      {activity === "lab" && <DeckLab gameId={view.game.id} viewer={viewer} seat={me} night={view.game.night?.number ?? 1} onClose={closeActivity} />}
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

type LabCopy = Awaited<ReturnType<typeof deckLabCopy>>;
/** Deck Lab as this tab left it: the copy (its library deck on the host computer) and, elsewhere, the list being edited. */
interface LabState { copy: LabCopy; name: string; text: string }
const labKey = (gameId: string, night: number, seat: string) => `fyodor.decklab.${gameId}.${night}.${seat}`;

function readLab(key: string): LabState | null {
  try {
    const raw = sessionStorage.getItem(key);
    const lab = raw ? (JSON.parse(raw) as LabState) : null;
    return lab && typeof lab.text === "string" && typeof lab.copy?.text === "string" ? lab : null;
  } catch {
    return null;
  }
}

function keepLab(key: string, lab: LabState): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(lab));
  } catch {
    /* this tab only: fine without */
  }
}

/**
 * DECK LAB: a copy of the deck you brought, for the next game. On the host computer the copy is a new deck in the
 * library, opened in the deck editor in a new tab (this table keeps your seat). On another computer it is the list,
 * to edit here and keep in this browser's My decks. The deck in this game is never changed; the lobby is where the
 * next deck is chosen. Compare shows what the next-game version brings in and takes out (deckCompare.ts). Reopened,
 * Deck Lab comes back to the same copy (and list), so the library gets one copy per game.
 */
function DeckLab({ gameId, viewer, seat, night, onClose }: { gameId: string; viewer?: string; seat: string; night: number; onClose: () => void }) {
  const key = labKey(gameId, night, seat);
  const [copy, setCopy] = useState<LabCopy | null>(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [library, setLibrary] = useState<DeckComparison | null>(null);
  useEffect(() => {
    let gone = false;
    const open = async (): Promise<LabState> => {
      const kept = readLab(key);
      if (kept && !kept.copy.deck_id) return kept;
      if (kept?.copy.deck_id) {
        try {
          await getDeck(kept.copy.deck_id);
          return kept;
        } catch {
          /* deleted from the library: a new copy */
        }
      }
      const c = await deckLabCopy(gameId, viewer);
      return { copy: c, name: c.name, text: c.text };
    };
    open().then((lab) => {
      if (gone) return;
      keepLab(key, lab);
      setCopy(lab.copy);
      setName(lab.name);
      setText(lab.text);
    }, (e) => {
      toastError(e);
      onClose();
    });
    return () => {
      gone = true;
    };
  }, [gameId, viewer, key, onClose]);
  const edit = (next: { name?: string; text?: string }) => {
    if (next.name !== undefined) setName(next.name);
    if (next.text !== undefined) setText(next.text);
    setSaved(false);
    if (copy) keepLab(key, { copy, name: next.name ?? name, text: next.text ?? text });
  };
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
  // the list being edited here, or (host computer) the library copy as the deck editor last saved it, read again on each Compare
  const listed = useMemo(() => (copy && !editor && comparing ? compareDecks(deckLines(copy.text), deckLines(text)) : null), [copy, editor, comparing, text]);
  const compare = async () => {
    if (comparing) {
      setComparing(false);
      return;
    }
    if (copy?.deck_id) {
      try {
        setLibrary(compareDecks(deckLines(copy.text), (await getDeck(copy.deck_id)).entries));
      } catch (e) {
        toastError(e);
        return;
      }
    }
    setComparing(true);
  };
  const cmp = editor ? library : listed;
  return (
    <Modal wide title="Deck Lab" onClose={onClose} footer={
      <>
        <span className="hint">The deck in this game never changes. Choose the next deck in the lobby.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={onClose}>Close</button>
        <button className="tt-btn" disabled={!copy} aria-pressed={comparing} onClick={() => void compare()} data-testid="deck-lab-compare"
          title="What your next-game version brings in and takes out, against the deck you brought">
          {comparing ? (editor ? "Back" : "Back to the list") : "Compare"}
        </button>
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
      ) : comparing && cmp ? (
        <DeckChanges cmp={cmp} />
      ) : editor ? (
        <p>A copy of your deck is in the deck library as <b>{copy.name}</b>. Edit it in the deck editor (a new tab, so you
          keep your seat here) and pick it in the lobby for the next game. Compare shows what your edits change.</p>
      ) : (
        <>
          <p className="hint">A copy of the list you brought to this game. Edit it, then keep it in this browser's My decks.</p>
          <label className="deck-lab-name">Name <input value={name} maxLength={120} onChange={(e) => edit({ name: e.target.value })} /></label>
          <textarea className="deck-lab-text" aria-label="Deck list" spellCheck={false} value={text}
            onChange={(e) => edit({ text: e.target.value })} />
        </>
      )}
    </Modal>
  );
}
