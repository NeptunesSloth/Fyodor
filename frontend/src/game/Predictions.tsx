import { useCallback, useEffect, useState } from "react";
import { Modal } from "../components/Modal";
import { toastError } from "../components/Toasts";
import { getPredictions, placePrediction, withdrawPrediction, type Market, type PredictionRecap, type PredictionsView } from "../services/spectate";
import { activeProfile } from "../state/prefs";
import { MARKET_LABEL, recapLine, stakeOptions } from "./spectate";

const NAME_KEY = "fyodor.spectatorName";

function storedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) || (activeProfile().name === "Player" ? "" : activeProfile().name);
  } catch {
    return "";
  }
}

const OUTCOME: Record<string, string> = { won: "Right", lost: "Wrong", void: "No result" };

/**
 * PREDICTIONS (docs/SPECTATOR_ACTIVITIES_MILESTONE.md §5): fake points, just for game-night bragging rights. Two fixed
 * questions about the public game, fixed stakes, a small session balance. Picks stay hidden until the game ends; then
 * everyone's are revealed and scored. Nothing here is saved or touches the game.
 */
export function PredictionsDialog({ gameId, spectator, resultKey, onClose }: {
  gameId: string;
  spectator: boolean;
  /** changes when the game's result does: the reveal is fetched then */
  resultKey: string;
  onClose: () => void;
}) {
  const [v, setV] = useState<PredictionsView | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState(storedName);
  const load = useCallback(() => {
    getPredictions(gameId).then(setV, (e) => {
      toastError(e);
      onClose();
    });
  }, [gameId, onClose]);
  useEffect(load, [load, resultKey]);

  const run = async (fn: () => Promise<PredictionsView>) => {
    setBusy(true);
    try {
      setV(await fn());
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const saveName = (value: string) => {
    setName(value);
    try {
      localStorage.setItem(NAME_KEY, value);
    } catch {
      /* this page only */
    }
  };

  return (
    <Modal title="Predictions" onClose={onClose} footer={
      <>
        <span className="hint">Fake points, just for fun. Nothing here touches the game.</span>
        <span className="spacer" />
        <button className="tt-btn brass" onClick={onClose}>Close</button>
      </>
    }>
      {!v ? <p className="hint">Loading…</p> : (
        <div className="predictions" data-testid="predictions">
          {v.recap ? (
            <>
              <p className="predictions-recap">{recapLine(v.recap)}</p>
              <ul className="predictions-reveal">
                {v.recap.picks.map((p, i) => (
                  <li key={i} className={p.outcome}>
                    <b>{p.name}</b> · {MARKET_LABEL[p.market]} {p.choice_name} ({p.stake}) — {OUTCOME[p.outcome]}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <p className="predictions-balance">Your points: <b>{v.balance}</b>{v.available !== v.balance ? ` (${v.available} not staked)` : ""}</p>
              {!v.can_predict && <p className="hint">Predictions are for players who are out and spectators. Picks are revealed when the game ends.</p>}
              {v.can_predict && spectator && (
                <label className="predictions-name">Your name in the recap
                  <input value={name} maxLength={24} placeholder="Spectator" onChange={(e) => saveName(e.target.value)} />
                </label>
              )}
              {v.can_predict && v.markets.map((m) => <MarketRow key={m} v={v} market={m} busy={busy}
                pick={(choice, stake) => void run(() => placePrediction(gameId, { market: m, choice, stake, name: spectator ? name.trim() || undefined : undefined }))}
                withdraw={() => void run(() => withdrawPrediction(gameId, m))} />)}
              {v.can_predict && <p className="hint">Your picks stay hidden from everyone until the game ends.</p>}
            </>
          )}
          {v.standings.length > 0 && !v.recap && (
            <p className="hint">Tonight so far: {v.standings.map((s) => `${s.name} ${s.balance}`).join(" · ")}</p>
          )}
        </div>
      )}
    </Modal>
  );
}

function MarketRow({ v, market, busy, pick, withdraw }: {
  v: PredictionsView;
  market: Market;
  busy: boolean;
  pick: (choice: string, stake: number) => void;
  withdraw: () => void;
}) {
  const current = v.picks[market];
  const stakes = stakeOptions(v, market);
  const [stake, setStake] = useState(current?.stake ?? stakes[0] ?? 10);
  const [choice, setChoice] = useState(current?.choice ?? "");
  const changed = !current || current.choice !== choice || current.stake !== stake;
  return (
    <fieldset className="predictions-market">
      <legend>{MARKET_LABEL[market]}</legend>
      <div className="predictions-choices" role="radiogroup" aria-label={MARKET_LABEL[market]}>
        {v.candidates.map((c) => (
          <button key={c.id} type="button" role="radio" aria-checked={choice === c.id} className={`tt-btn ${choice === c.id ? "on" : ""}`}
            onClick={() => setChoice(c.id)}>{c.name}</button>
        ))}
      </div>
      <div className="predictions-stake">
        <label>Stake <select value={stake} onChange={(e) => setStake(Number(e.target.value))}>
          {v.stakes.map((s) => <option key={s} value={s} disabled={!stakes.includes(s)}>{s}</option>)}
        </select></label>
        <button className="tt-btn brass" disabled={busy || !choice || !stakes.includes(stake) || !changed} onClick={() => pick(choice, stake)}>
          {current ? "Change pick" : "Predict"}
        </button>
        {current && <button className="tt-btn ghost" disabled={busy} onClick={withdraw}>Withdraw</button>}
        {current && <span className="hint">You picked {current.choice_name} ({current.stake})</span>}
      </div>
    </fieldset>
  );
}

/** The reveal under the game's result, for the whole table: the standings, and everyone's picks on request. */
export function PredictionsRecap({ recap }: { recap: PredictionRecap }) {
  return (
    <details className="night-predictions" data-testid="predictions-recap">
      <summary>{recapLine(recap)}</summary>
      <ul>
        {recap.picks.map((p, i) => (
          <li key={i} className={p.outcome}>{p.name}: {p.market === "winner" ? "winner" : "next out"} {p.choice_name} ({p.stake}) — {OUTCOME[p.outcome]}</li>
        ))}
      </ul>
    </details>
  );
}
