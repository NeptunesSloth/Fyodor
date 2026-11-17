import { SPECTATOR, type GameView, type NightProposal } from "../types/game";

/*
 * How the end of a game reads at this seat (docs/GAME_NIGHT_FLOW.md §4-5). Every fact comes from the server's view: who is
 * still in the game, the proposal on the table, and whether the rules engine has ended the game. The client only decides
 * what to show and which buttons this seat gets.
 */

/** -- target dummy -- the rules' ending of a test with only target dummies left in the game (app/rules/dummy_ending.py: their win). */
export const DUMMIES_WIN = "Only target dummies are left in the game: the dummies win";
/** -- test opponent -- the same, with an opponent the server plays for among them (app/rules/dummy_ending.py OPPONENTS_WIN). */
export const OPPONENTS_WIN = "Only the test opponents are left in the game: they win";

/** Players still in the game: not removed from the table, not conceded or lost (800.4a). */
export function stillIn(view: GameView): string[] {
  const r = view.rules;
  return view.seat_order.filter((pid) => !view.players.find((p) => p.id === pid)?.left && !(r && (r.conceded.includes(pid) || pid in r.lost)));
}

/** The rules engine has ended the game (a winner, 104.2, or a draw, 104.4): the result flow takes over from here. */
export function overByRules(view: GameView): boolean {
  return !!view.rules && (!!view.rules.winner || !!view.rules.draw_reason);
}

/**
 * The eliminated player's own moment ("Eliminated — the game continues" and its hub): for a seated player who conceded or
 * lost while the game goes on. Gone once the game has a result, and once the rules have ended the game (the last player to
 * lose then confirms the result instead of being told the game continues).
 */
export function showEliminated(view: GameView, me: string): boolean {
  const r = view.rules;
  return view.viewer !== SPECTATOR && !!r && (r.conceded.includes(me) || me in r.lost) && !view.game.night?.result && !overByRules(view)
    && !testEnding(view, me); // (a test table has its own ending: no hub to watch dummies from)
}

/**
 * -- test-table ending -- how a test with target dummies ended at this seat (they have no pod result to confirm, so the night's
 * result flow never opens): "lost" (this seat lost or conceded), "won" (every dummy is out), or "draw". Null while the test goes
 * on, for a spectator, and at a table with no dummy. ``key`` changes with each new ending (a second loss after Take it back).
 */
export interface TestEnding { kind: "lost" | "won" | "draw"; title: string; line: string; key: string }

export function testEnding(view: GameView, me: string): TestEnding | null {
  const r = view.rules;
  if (!r || view.viewer === SPECTATOR || !view.seat_order.includes(me)) return null;
  // -- test opponent -- the seats nobody sits in: target dummies, and opponents the server plays for
  const dummies = view.players.filter((p) => (p.dummy || p.bot) && !p.left);
  if (!dummies.length) return null;
  const bots = dummies.some((p) => p.bot);
  const name = (pid: string) => view.players.find((p) => p.id === pid)?.name ?? pid;
  const key = (kind: string, why: string) => `${kind}|${r.winner ?? ""}|${why}|${view.turn?.number ?? 0}`;
  const out = r.conceded.includes(me) ? "You conceded" : me in r.lost ? `You lost: ${r.lost[me]}` : null;
  if (out) {
    const then = r.winner ? ` ${name(r.winner)} wins.` : r.draw_reason ? ` ${r.draw_reason}.`
      : bots ? " Your opponents are still standing." : " The dummies are still standing.";
    return { kind: "lost", title: "You lost", line: `${out}.${then}`, key: key("lost", out) };
  }
  if (r.winner === me) {
    const title = dummies.length > 1 ? (bots ? "Opponents defeated" : "Target dummies defeated") : `${dummies[0]!.name} defeated`;
    const line = bots ? "Every opponent is out. Start over deals a new game." : "Every dummy is out. Reset dummy (Solo tools) brings one back.";
    return { kind: "won", title, line, key: key("won", "") };
  }
  if (r.draw_reason) return { kind: "draw", title: "A draw", line: `${r.draw_reason}.`, key: key("draw", r.draw_reason) };
  return null;
}

export interface ProposalSeat {
  /** "Alice wins", "Alice and Bob win", "a draw", "no result". */
  what: string;
  /** The rules engine's result (with why), rather than a player's proposal. */
  rules: string | null;
  /** Who still has to answer (seats). */
  waiting: string[];
  /** This seat answers now (Agree / Decline, or Confirm / Not yet for the rules result). */
  mustAnswer: boolean;
  /** This seat made the proposal and may take it back. */
  canWithdraw: boolean;
}

export function describeResult(p: Pick<NightProposal, "result_type" | "winner_names">): string {
  if (p.result_type === "single" || p.result_type === "multiple") return `${p.winner_names.join(" and ")} ${p.winner_names.length === 1 ? "wins" : "win"}`;
  return p.result_type === "draw" ? "a draw" : "no result";
}

/** What the proposal bar shows this seat (`me`: the seat it acts as), or null when there's nothing to show. */
export function proposalSeat(view: GameView, me: string): ProposalSeat | null {
  const night = view.game.night;
  const p = night?.proposal;
  if (!p || night?.result) return null;
  const local = view.game.mode === "local";
  const seated = view.viewer !== SPECTATOR;
  if (p.rules) {
    const voters = p.voters ?? [];
    const waiting = voters.filter((pid) => !p.agreed.includes(pid));
    // one person runs a hot-seat table: their click settles it, whichever seat they look from
    const mustAnswer = seated && (local ? view.seat_order.includes(me) : voters.includes(me) && !p.agreed.includes(me));
    return { what: describeResult(p), rules: p.rules, waiting, mustAnswer, canWithdraw: false };
  }
  const live = stillIn(view);
  return {
    what: describeResult(p),
    rules: null,
    waiting: live.filter((pid) => !p.agreed.includes(pid)),
    mustAnswer: seated && live.includes(me) && !p.agreed.includes(me),
    canWithdraw: p.by === me,
  };
}
