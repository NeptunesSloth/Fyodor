import { Icon } from "../components/Icon";
import type { LobbySeat, LobbyView } from "../types/game";
import { CommanderArt, useCommanderPrinting } from "./CommanderArt";
import { EliminationOrder, FinalBoard } from "./GameRecap";
import { rollsText } from "./seating";

type NightGame = NonNullable<LobbyView["night"]>[number];

/**
 * Tonight so far (TABLETOP_QOL_MILESTONE #17): the night's score sheet between games, one line per game with the winner's
 * commander, who went out in what order and the final board on request. A casual recap, never a ranking.
 */
export function SessionRecap({ games, seats }: { games: NonNullable<LobbyView["night"]>; seats: LobbySeat[] }) {
  const wins = new Map<string, number>();
  for (const g of games) if (g.result_type === "single" || g.result_type === "multiple") for (const w of g.winner_names) wins.set(w, (wins.get(w) ?? 0) + 1);
  const minutes = games.reduce((n, g) => n + (g.minutes ?? 0), 0);
  const colour = (name: string) => seats.find((s) => s.claimed && s.name === name)?.color;
  return (
    <section className="ledger" data-testid="session-recap" aria-label="Tonight so far">
      <header className="ledger-head">
        <h2>Tonight so far</h2>
        <p className="ledger-sum">
          <span>{games.length} game{games.length === 1 ? "" : "s"}</span>
          {minutes > 0 && <span>about {minutes} min</span>}
        </p>
        <a className="tt-btn ledger-stats" href="#/stats"><Icon name="crown" size={15} />Pod stats</a>
      </header>
      {wins.size > 0 && (
        <ul className="ledger-tally" aria-label="Wins tonight">
          {[...wins].sort((a, b) => b[1] - a[1]).map(([name, n]) => (
            <li key={name}>
              <i className="tally-dot" style={{ background: colour(name) ?? "var(--line-2)" }} aria-hidden />
              {name} <b>{n}</b> {n === 1 ? "win" : "wins"}
            </li>
          ))}
        </ul>
      )}
      <ol className="ledger-games">
        {games.map((g) => <GameLine key={g.number} game={g} seats={seats} />)}
      </ol>
    </section>
  );
}

function GameLine({ game: g, seats }: { game: NightGame; seats: LobbySeat[] }) {
  const won = g.result_type === "single" || g.result_type === "multiple";
  const winner = g.winner_names.length === 1 ? g.winner_names[0]! : null;
  const cmdr = winner ? g.commanders?.[winner]?.join(" & ") : null;
  const art = useCommanderPrinting(won ? g.commanders?.[g.winner_names[0] ?? ""]?.[0] ?? null : null, seats);
  return (
    <li className={`lg-game ${won ? "won" : g.result_type}`}>
      <span className="lg-n">Game {g.number}</span>
      <span className="lg-art">
        {art ? <CommanderArt id={art} /> : <span className="lg-art-none" aria-hidden>{g.result_type === "draw" ? "Draw" : "—"}</span>}
      </span>
      <div className="lg-main">
        <p className="lg-result">
          {g.result_type === "draw" ? "Draw" : g.result_type === "no_result" ? "No result" : (
            <>
              <b>{g.winner_names.join(" & ")}</b>{" won"}
              {cmdr ? <>{" with "}<span className="lg-cmdr">{cmdr}</span></> : null}
            </>
          )}
          {g.agreed ? <span className="lg-agreed">{" (agreed)"}</span> : null}
        </p>
        <EliminationOrder list={g.eliminations} />
        {g.rolls && g.rolls.length > 0 && <p className="lg-rolls" data-testid="recap-rolls">d20 {rollsText(g.rolls)}</p>}
        {g.result_id && <FinalBoard resultId={g.result_id} eliminations={g.eliminations} />}
      </div>
      <span className="lg-len">
        {g.turns} turn{g.turns === 1 ? "" : "s"}
        {g.minutes ? <><br />{g.minutes} min</> : null}
      </span>
    </li>
  );
}
