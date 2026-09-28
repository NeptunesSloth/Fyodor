import { useCallback, useEffect, useState } from "react";
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
  type GameResult,
  type PodPlayer,
  type PodPlayerDetail,
} from "../services/pod";
import "./podstats.css";

const OUTCOME: Record<string, string> = { win: "WIN", loss: "LOSS", draw: "DRAW", none: "—" };

/**
 * POD STATS: our group's history — who played what and who won. Players are listed by name;
 * there are no ranks, ratings or medals. Corrections happen on the host computer.
 */
export function PodStatsPage() {
  const [players, setPlayers] = useState<PodPlayer[] | null>(null);
  const [results, setResults] = useState<GameResult[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PodPlayerDetail | null>(null);
  const [editing, setEditing] = useState<GameResult | null>(null);
  const [host, setHost] = useState(false);

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
  return (
    <div className="page pod-stats" data-testid="pod-stats">
      <header className="pod-head">
        <h1>Pod stats</h1>
        <span className="hint">Our games, as recorded at the end of each one. Not a ranking.</span>
        <span className="spacer" />
        {host && <a className="tt-btn ghost" href="/api/pod/export" download="pod-stats.json">Export (backup)</a>}
      </header>

      <div className="pod-grid">
        <section className="pod-panel">
          {players === null ? null : counted.length === 0 ? (
            <p className="hint">No results yet. At the end of a game the host chooses <b>End game</b> and records who won.</p>
          ) : (
            <table className="pod-table" data-testid="pod-table">
              <thead>
                <tr><th>Player</th><th>Games</th><th>Wins</th><th>Losses</th><th>Draws</th><th>Win %</th></tr>
              </thead>
              <tbody>
                {counted.map((p) => (
                  <tr key={p.id} className={selected === p.id ? "on" : ""} onClick={() => setSelected(selected === p.id ? null : p.id)} data-testid={`pod-row-${p.name}`}>
                    <td className="name">{p.name}</td>
                    <td>{p.games}</td>
                    <td>{p.wins}</td>
                    <td>{p.losses}</td>
                    <td>{p.draws}</td>
                    <td>{pct(p.win_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {detail && (
          <section className="pod-panel pod-player" data-testid="pod-player">
            <h2>{detail.name}</h2>
            <p className="pod-line">Games played: <b>{detail.games}</b> · Wins: <b>{detail.wins}</b> · Win rate: <b>{pct(detail.win_pct)}</b></p>
            {detail.decks.length > 0 && (
              <>
                <h3>Decks</h3>
                <table className="pod-table small">
                  <thead><tr><th>Deck</th><th>Games</th><th>Wins</th><th>Win %</th></tr></thead>
                  <tbody>
                    {detail.decks.map((d) => (
                      <tr key={d.deck_key}>
                        <td className="name">{d.deck_name ?? "Unnamed deck"}{d.commanders.length ? <span className="hint"> · {d.commanders.join(" & ")}</span> : null}</td>
                        <td>{d.games}</td><td>{d.wins}</td><td>{pct(d.win_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            <h3>Recent games</h3>
            <ul className="pod-recent">
              {detail.recent.map((g) => (
                <li key={g.id}>
                  <span className="hint">{shortDate(g.recorded_at)}</span>
                  <span>{g.commanders.length ? g.commanders.join(" & ") : g.deck_name ?? "—"}</span>
                  <b className={`outcome ${g.outcome}`}>{OUTCOME[g.outcome]}</b>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <section className="pod-panel">
        <h2>Game history</h2>
        {results.length === 0 && <p className="hint">Nothing recorded yet.</p>}
        {results.map((r) => (
          <article key={r.id} className={`pod-game ${r.result_type}`} data-testid="pod-game">
            <header>
              <b>Game #{r.number}</b>
              <span className="hint">{shortDate(r.recorded_at)}{r.table_name ? ` · ${r.table_name}` : ""}{r.turns ? ` · ${r.turns} turn${r.turns === 1 ? "" : "s"}` : ""}{r.duration_seconds ? ` · ${duration(r.duration_seconds)}` : ""}</span>
              <span className="spacer" />
              {host && (
                <>
                  <button className="tt-btn ghost" onClick={() => setEditing(r)} data-testid="edit-result">Edit result</button>
                  <button className="tt-btn ghost danger" onClick={async () => {
                    if (!window.confirm(`Delete Game #${r.number}'s result? Statistics are recomputed without it.`)) return;
                    await deleteResult(r.id).then(() => toast("Result deleted"), toastError);
                    refresh();
                  }}>Delete</button>
                </>
              )}
            </header>
            <ul className="pod-seats">
              {r.players.map((p) => (
                <li key={p.seat} className={p.outcome}>
                  {p.name}{p.commanders.length ? ` — ${p.commanders.join(" & ")}` : p.deck_name ? ` — ${p.deck_name}` : ""}
                </li>
              ))}
            </ul>
            <p className="pod-winner">
              {r.result_type === "single" || r.result_type === "multiple" ? <>Winner{r.winners.length > 1 ? "s" : ""}: <b>{r.winners.join(" + ")}</b></> : RESULT_LABEL[r.result_type]}
            </p>
            {r.notes && <p className="hint pod-note">“{r.notes}”</p>}
          </article>
        ))}
      </section>

      {editing && <EditResult result={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
    </div>
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
