import { useCallback, useEffect, useMemo, useState } from "react";
import { Modal } from "../components/Modal";
import { ResultForm, draftValid, type ResultDraft } from "../components/ResultForm";
import { toast, toastError } from "../components/Toasts";
import { lanInfo } from "../services/games";
import {
  RESULT_LABEL,
  deleteResult,
  duration,
  editResult,
  pct,
  podPlayer,
  podPlayers,
  podResults,
  shortDate,
  type DeckStats,
  type GameResult,
  type PodPlayer,
  type PodPlayerDetail,
  type ResultPlayer,
} from "../services/pod";
import type { LobbySeat } from "../types/game";
import { CommanderArt, useCommanderPrinting } from "./CommanderArt";
import { EliminationOrder, FinalBoard } from "./GameRecap";
import { OUTCOME_WORD, groupByNight, podSummary, signatureCommanders } from "./podStatsBits";
import "./podstats.css";

const NO_SEATS: LobbySeat[] = [];

/** A commander's art in a frame (looked up by name, as the lobby's score sheet does), or the player's initial on felt. */
function Art({ commander, fallback, className }: { commander: string | null | undefined; fallback: string; className: string }) {
  const id = useCommanderPrinting(commander ?? null, NO_SEATS);
  return (
    <span className={`ps-frame ${className}`}>
      {id ? <CommanderArt id={id} /> : <span className="ps-blank" aria-hidden>{fallback.slice(0, 1).toUpperCase()}</span>}
    </span>
  );
}

const time = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

/**
 * POD STATS: our group's history — who played what and who won, game night by game night, with each seat's commander art.
 * Players are listed by name; there are no ranks, ratings or medals. Corrections happen on the host computer.
 */
export function PodStatsPage() {
  const [players, setPlayers] = useState<PodPlayer[] | null>(null);
  const [results, setResults] = useState<GameResult[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PodPlayerDetail | null>(null);
  const [editing, setEditing] = useState<GameResult | null>(null);
  const [host, setHost] = useState(false);
  const [found, setFound] = useState<string | null>(null);

  const refresh = useCallback(() => {
    podPlayers().then(setPlayers, toastError);
    podResults().then(setResults, toastError);
  }, []);
  useEffect(() => {
    refresh();
    lanInfo().then(() => setHost(true), () => setHost(false));
  }, [refresh]);
  useEffect(() => {
    if (selected) podPlayer(selected).then(setDetail, toastError);
    else setDetail(null);
  }, [selected, results]);

  const counted = (players ?? []).filter((p) => p.games > 0 || results.some((r) => r.players.some((x) => x.player_id === p.id)));
  const signature = useMemo(() => signatureCommanders(results), [results]);
  const nights = useMemo(() => groupByNight(results), [results]);
  const summary = podSummary(results);

  /** A recent game in a player's sheet: its entry in the history, scrolled to, with its final board open. */
  const openGame = (id: string) => {
    const el = document.getElementById(`pod-game-${id}`);
    if (!el) return;
    const fb = el.querySelector<HTMLDetailsElement>("details.final-board");
    if (fb) fb.open = true;
    setFound(id);
    const still = document.body.classList.contains("reduced-motion") || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    el.querySelector<HTMLElement>("h3")?.focus({ preventScroll: true });
  };

  return (
    <div className="page pod-stats" data-testid="pod-stats">
      <header className="ps-head">
        <div className="ps-title">
          <h1>Pod stats</h1>
          <p>Our games, as recorded at the end of each one. Not a ranking.</p>
        </div>
        {results.length > 0 && (
          <p className="ps-sum">
            <span>{summary.games}</span>
            <span>{summary.players} player{summary.players === 1 ? "" : "s"}</span>
            {summary.last && <span>Last played {shortDate(summary.last)}</span>}
          </p>
        )}
        {host && <a className="tt-btn ghost ps-export" href="/api/pod/export" download="pod-stats.json">Export (backup)</a>}
      </header>

      {players === null ? null : counted.length === 0 && results.length === 0 ? (
        <section className="ps-empty" aria-labelledby="ps-empty-title">
          <span className="ps-empty-seats" aria-hidden><i /><i /><i /><i /></span>
          <h2 id="ps-empty-title">No games recorded yet</h2>
          <p>At the end of a game the host chooses <b>End game</b> and records who won. Each game then shows up here: who played which commander, who won, who went out when, and the final board.</p>
          <a className="tt-btn brass ps-empty-go" href="#/play">Start a game</a>
        </section>
      ) : (
        <>
          <div className={`ps-grid ${detail || results.length ? "two" : ""}`}>
            <section className="ps-pod" aria-labelledby="ps-pod-title">
              <div className="ps-pod-head">
                <h2 id="ps-pod-title">The pod</h2>
                <p>Choose a player for their decks and recent games.</p>
              </div>
              <table className="pod-table" data-testid="pod-table">
                <thead>
                  <tr><th scope="col">Player</th><th scope="col">Games</th><th scope="col">Wins</th><th scope="col">Losses</th><th scope="col">Draws</th><th scope="col">Win %</th></tr>
                </thead>
                <tbody>
                  {counted.map((p) => {
                    const cmdrs = signature.get(p.id);
                    const on = selected === p.id;
                    return (
                      <tr key={p.id} className={on ? "on" : ""} onClick={() => setSelected(on ? null : p.id)} data-testid={`pod-row-${p.name}`}>
                        <td className="name">
                          {/* (the row takes the click; the button makes it reachable by keyboard and says what it does) */}
                          <button type="button" className="ps-who" aria-expanded={on} aria-controls={on ? "pod-player" : undefined}>
                            <Art commander={cmdrs?.[0]} fallback={p.name} className="ps-who-art" />
                            <span className="ps-who-text">
                              <b>{p.name}</b>
                              {cmdrs && <span>{cmdrs.join(" & ")}</span>}
                            </span>
                          </button>
                        </td>
                        <td>{p.games}</td>
                        <td>{p.wins}</td>
                        <td>{p.losses}</td>
                        <td>{p.draws}</td>
                        <td>{pct(p.win_pct)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>

            {detail ? <PlayerSheet detail={detail} results={results} onClose={() => setSelected(null)} onOpenGame={openGame} />
              : results[0] ? <LastGame result={results[0]} onOpen={openGame} /> : null}
          </div>

          <section className="ps-history" aria-labelledby="ps-history-title">
            <h2 id="ps-history-title">Game history</h2>
            {results.length === 0 && <p className="ps-none">Nothing recorded yet.</p>}
            {nights.map((night) => (
              <section key={night.key} className="ps-night" aria-label={night.label}>
                <header className="ps-night-head">
                  <h3>{night.label}</h3>
                  <p className="ps-tally">
                    <span>{night.games.length} game{night.games.length === 1 ? "" : "s"}</span>
                    {night.tally.map(([name, n]) => <span key={name}><b>{name}</b> {n} {n === 1 ? "win" : "wins"}</span>)}
                  </p>
                </header>
                <div className="ps-night-games">
                  {night.games.map((r) => (
                    <GameEntry key={r.id} result={r} host={host} found={found === r.id} onEdit={() => setEditing(r)} onDeleted={refresh} />
                  ))}
                </div>
              </section>
            ))}
          </section>
        </>
      )}

      {editing && <EditResult result={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
    </div>
  );
}

/** The most recent game, in the spotlight beside the pod until a player is chosen: the winner's commander, big. */
function LastGame({ result: r, onOpen }: { result: GameResult; onOpen: (id: string) => void }) {
  const won = r.result_type === "single" || r.result_type === "multiple";
  const winners = r.players.filter((p) => p.outcome === "win");
  const lead = (won ? winners[0] : undefined) ?? r.players[0];
  const cmdr = winners.length === 1 && winners[0]!.commanders.length ? winners[0]!.commanders.join(" & ") : null;
  return (
    <section className="ps-spot" aria-labelledby="ps-spot-title">
      <Art commander={lead?.commanders[0]} fallback={lead?.name ?? "?"} className="ps-spot-art" />
      <div className="ps-spot-text">
        <h2 id="ps-spot-title">The last game</h2>
        <p className="ps-spot-result">
          {won ? <><b>{r.winners.join(" & ")}</b>{" won"}{cmdr ? <>{" with "}<span className="ps-spot-cmdr">{cmdr}</span></> : null}</>
            : <b>{RESULT_LABEL[r.result_type]}</b>}
        </p>
        <p className="ps-meta">
          <span>Game #{r.number}</span>
          <span>{shortDate(r.recorded_at)}</span>
          {r.table_name ? <span>{r.table_name}</span> : null}
          {r.turns ? <span>{r.turns} turn{r.turns === 1 ? "" : "s"}</span> : null}
        </p>
        <button type="button" className="tt-btn ps-spot-go" onClick={() => onOpen(r.id)}>Open its recap</button>
      </div>
    </section>
  );
}

/** One player's sheet: their record, their decks with commander art, their recent games (each opens its recap below). */
function PlayerSheet({ detail, results, onClose, onOpenGame }: { detail: PodPlayerDetail; results: GameResult[]; onClose: () => void; onOpenGame: (id: string) => void }) {
  const known = new Set(results.map((r) => r.id));
  return (
    <section className="ps-sheet" id="pod-player" data-testid="pod-player" aria-labelledby="ps-sheet-title">
      <header className="ps-sheet-head">
        <h2 id="ps-sheet-title">{detail.name}</h2>
        <button type="button" className="tt-icon ps-close" onClick={onClose} aria-label={`Close ${detail.name}'s sheet`}>✕</button>
      </header>
      <p className="ps-line">
        <span>Games played: <b>{detail.games}</b></span>
        <span>Wins: <b>{detail.wins}</b></span>
        <span>Win rate: <b>{pct(detail.win_pct)}</b></span>
      </p>
      {detail.decks.length > 0 && (
        <>
          <h3>Decks</h3>
          <ul className="ps-decks">
            {detail.decks.map((d) => <DeckLine key={d.deck_key} deck={d} />)}
          </ul>
        </>
      )}
      <h3>Recent games</h3>
      <ol className="ps-recent">
        {detail.recent.map((g) => (
          <li key={g.id}>
            {known.has(g.id) ? (
              <button type="button" className="tt-link ps-recent-n" onClick={() => onOpenGame(g.id)} title="Show this game in the history, with its final board">Game #{g.number}</button>
            ) : <span className="ps-recent-n">Game #{g.number}</span>}
            <span className="ps-recent-date">{shortDate(g.recorded_at)}</span>
            <span className="ps-recent-cmdr">{g.commanders.length ? g.commanders.join(" & ") : g.deck_name ?? "—"}</span>
            <b className={`outcome ${g.outcome}`}>{OUTCOME_WORD[g.outcome]}</b>
          </li>
        ))}
      </ol>
    </section>
  );
}

function DeckLine({ deck: d }: { deck: DeckStats }) {
  return (
    <li className="ps-deck">
      <Art commander={d.commanders[0]} fallback={d.deck_name ?? "?"} className="ps-deck-art" />
      <span className="ps-deck-text">
        <b>{d.commanders.length ? d.commanders.join(" & ") : d.deck_name ?? "Unnamed deck"}</b>
        {d.commanders.length > 0 && <span className="ps-deck-name">{d.deck_name ?? "Unnamed deck"}</span>}
        <span className="ps-deck-rec">
          <span>{d.games} game{d.games === 1 ? "" : "s"}</span>
          <span>{d.wins} win{d.wins === 1 ? "" : "s"}</span>
          <span>{pct(d.win_pct)}</span>
        </span>
      </span>
    </li>
  );
}

function SeatTile({ player: p }: { player: ResultPlayer }) {
  const what = p.commanders.length ? p.commanders.join(" & ") : p.deck_name ?? "";
  return (
    <li className={`ps-seat ${p.outcome}`}>
      <span className="ps-seat-frame">
        <Art commander={p.commanders[0]} fallback={p.name} className="ps-seat-art" />
        {p.outcome === "win" && <span className="ps-won">Won</span>}
      </span>
      <b className="ps-seat-name">{p.name}</b>
      {what && <span className="ps-seat-cmdr" title={what}>{what}</span>}
    </li>
  );
}

function GameEntry({ result: r, host, found, onEdit, onDeleted }: { result: GameResult; host: boolean; found: boolean; onEdit: () => void; onDeleted: () => void }) {
  return (
    <article id={`pod-game-${r.id}`} className={`ps-game ${r.result_type} ${found ? "found" : ""}`} data-testid="pod-game">
      <header className="ps-game-head">
        <h3 tabIndex={-1}>Game #{r.number}</h3>
        <p className="ps-meta">
          <span>{time(r.recorded_at)}</span>
          {r.table_name ? <span>{r.table_name}</span> : null}
          {r.turns ? <span>{r.turns} turn{r.turns === 1 ? "" : "s"}</span> : null}
          {r.duration_seconds ? <span>{duration(r.duration_seconds)}</span> : null}
        </p>
        {host && (
          <span className="ps-game-acts">
            <button className="tt-btn ghost" onClick={onEdit} data-testid="edit-result">Edit result</button>
            <button className="tt-btn ghost ps-delete" onClick={async () => {
              if (!window.confirm(`Delete Game #${r.number}'s result? Statistics are recomputed without it.`)) return;
              await deleteResult(r.id).then(() => toast("Result deleted"), toastError);
              onDeleted();
            }}>Delete</button>
          </span>
        )}
      </header>
      <div className="ps-game-body">
        <ul className="ps-seats">
          {r.players.map((p) => <SeatTile key={p.seat} player={p} />)}
        </ul>
        <div className="ps-result">
          <p className="ps-winner">
            {r.result_type === "single" || r.result_type === "multiple"
              ? <>Winner{r.winners.length > 1 ? "s" : ""}: <b>{r.winners.join(" + ")}</b></>
              : <b>{RESULT_LABEL[r.result_type]}</b>}
          </p>
          {r.notes && <p className="ps-note">“{r.notes}”</p>}
          <EliminationOrder list={r.eliminations} />
        </div>
      </div>
      {r.final_board && r.final_board.length > 0 && <FinalBoard board={r.final_board} eliminations={r.eliminations} />}
    </article>
  );
}

function EditResult({ result, onClose, onSaved }: { result: GameResult; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<ResultDraft>({
    result_type: result.result_type,
    winners: result.players.filter((p) => p.outcome === "win").map((p) => p.seat),
    notes: result.notes,
  });
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`Edit Game #${result.number}`} onClose={onClose} footer={
      <>
        <button className="tt-btn" onClick={onClose}>Cancel</button>
        <span className="spacer" />
        <button className="tt-btn brass" data-testid="save-result" disabled={busy || !draftValid(draft)} onClick={async () => {
          setBusy(true);
          try {
            await editResult(result.id, draft);
            toast("Result corrected — statistics recomputed");
            onSaved();
          } catch (e) {
            toastError(e);
          } finally {
            setBusy(false);
          }
        }}>Save</button>
      </>
    }>
      <ResultForm players={result.players.map((p) => ({ seat: p.seat, name: p.name }))} value={draft} onChange={setDraft} />
    </Modal>
  );
}
