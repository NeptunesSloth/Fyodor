import type { ResultType } from "../services/pod";
import { RESULT_LABEL } from "../services/pod";

export interface ResultDraft {
  result_type: ResultType;
  winners: string[];
  notes: string;
}

/** Pick the result: type, then winner(s). Shared by End game and Edit result. */
export function ResultForm({ players, value, onChange }: {
  players: { seat: string; name: string }[];
  value: ResultDraft;
  onChange: (v: ResultDraft) => void;
}) {
  const multi = value.result_type === "multiple";
  const pickWinners = value.result_type === "single" || multi;
  const toggle = (seat: string) =>
    onChange({
      ...value,
      winners: multi ? (value.winners.includes(seat) ? value.winners.filter((s) => s !== seat) : [...value.winners, seat]) : [seat],
    });
  return (
    <div className="result-form">
      <div className="result-types" role="radiogroup">
        {(Object.keys(RESULT_LABEL) as ResultType[]).map((t) => (
          <button key={t} role="radio" aria-checked={value.result_type === t} className={`tt-tab ${value.result_type === t ? "on" : ""}`}
            data-testid={`result-${t}`}
            onClick={() => onChange({ ...value, result_type: t, winners: t === "single" ? value.winners.slice(0, 1) : t === "multiple" ? value.winners : [] })}>
            {RESULT_LABEL[t]}
          </button>
        ))}
      </div>
      {pickWinners ? (
        <>
          <p className="hint">{multi ? "Who won? (choose all winners)" : "Who won?"}</p>
          <div className="winner-picks">
            {players.map((p) => (
              <button key={p.seat} className={`tt-btn ${value.winners.includes(p.seat) ? "on" : ""}`} data-testid={`winner-${p.seat}`}
                aria-pressed={value.winners.includes(p.seat)} onClick={() => toggle(p.seat)}>
                {p.name}
              </button>
            ))}
          </div>
        </>
      ) : (
        <p className="hint">
          {value.result_type === "draw" ? "Nobody wins; the game counts as played for everyone." : "The game was abandoned. It won't affect anyone's statistics."}
        </p>
      )}
      <label className="field">Note (optional)
        <input value={value.notes} maxLength={500} placeholder="“Mike killed everyone with 84 Goblins.”" data-testid="result-notes"
          onChange={(e) => onChange({ ...value, notes: e.target.value })} />
      </label>
    </div>
  );
}

export const draftValid = (d: ResultDraft) =>
  d.result_type === "single" ? d.winners.length === 1 : d.result_type === "multiple" ? d.winners.length >= 2 : true;
