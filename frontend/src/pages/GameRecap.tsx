import { useState, type SyntheticEvent } from "react";
import { podResult, type EliminationEntry, type FinalBoardSeat } from "../services/pod";
import { boardLines, eliminationLines, ordinal } from "./podHistory";
import "./gamerecap.css";

/** -- pod history -- the order players went out of one game ("1st out: Bob (turn 7, commander damage)"). */
export function EliminationOrder({ list }: { list: EliminationEntry[] | undefined }) {
  const lines = eliminationLines(list);
  if (!lines.length) return null;
  return (
    <ol className="elim-order" data-testid="elim-order" aria-label="Elimination order">
      {lines.map((l) => (
        <li key={l.place}>
          <span className="eo-head">{l.head}</span>{" "}<b className="eo-who">{l.who}</b><span className="eo-rest">{l.rest}</span>
        </li>
      ))}
    </ol>
  );
}

function Seats({ board, eliminations }: { board: FinalBoardSeat[]; eliminations?: EliminationEntry[] }) {
  const out = new Map((eliminations ?? []).map((e) => [e.seat, e.place]));
  return (
    <ul className="fb-seats">
      {board.map((seat) => {
        const l = boardLines(seat);
        const place = out.get(seat.seat);
        const [life, ...rest] = l.stats.split(" life");
        return (
          <li key={seat.seat} className={place ? "out" : "standing"}>
            <div className="fb-head">
              <b className="fb-name">{seat.name}</b>
              <span className="fb-stats">
                <span className="fb-life">{life}</span>{" life"}{rest.join(" life")}
                {place ? <span className="fb-out">{` · out ${ordinal(place)}`}</span> : null}
              </span>
            </div>
            {seat.commanders.length > 0 && <p className="fb-cmdr">{seat.commanders.join(" & ")}</p>}
            {l.permanents && <p className="fb-perms">{l.permanents}</p>}
            {l.lands && <p className="fb-lands">{l.lands}</p>}
            <p className="fb-zones">{l.zones}</p>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * "Final board": a closed disclosure with each player's public table when the result was recorded. ``board`` when it is known
 * already (Pod stats); ``resultId`` to fetch it from pod stats the first time it is opened (the session recap keeps payloads small).
 */
export function FinalBoard({ board, resultId, eliminations }: { board?: FinalBoardSeat[]; resultId?: string; eliminations?: EliminationEntry[] }) {
  const [loaded, setLoaded] = useState<FinalBoardSeat[] | null | "error">(board ?? null);
  if (board && board.length === 0) return null;
  if (!board && !resultId) return null;
  const onToggle = (e: SyntheticEvent<HTMLDetailsElement>) => {
    if (!e.currentTarget.open || loaded !== null || !resultId) return;
    podResult(resultId).then((r) => setLoaded(r.final_board ?? []), () => setLoaded("error"));
  };
  const seats = board ?? (Array.isArray(loaded) ? loaded : null);
  return (
    <details className="final-board" data-testid="final-board" onToggle={onToggle}>
      <summary>Final board</summary>
      {seats && seats.length > 0 ? (
        <Seats board={seats} eliminations={eliminations} />
      ) : (
        <p className="fb-note">{loaded === "error" || (seats && !seats.length) ? "No final board was kept for this game." : "Opening…"}</p>
      )}
    </details>
  );
}
