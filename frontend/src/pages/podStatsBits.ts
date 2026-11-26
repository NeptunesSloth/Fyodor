import type { GameResult, Outcome } from "../services/pod";

/*
 * Pod stats helpers: everything here is worked out from what the pod stats API already returns (the recorded results),
 * nothing new is asked of the server.
 */

/**
 * A recorded name, for display: pod stats record a LAN bot as "Bot (bot)" so it never counts as a person of the pod; the page
 * shows "Bot" with a small bot mark instead of saying it twice. The recorded history is unchanged.
 */
export function splitBot(name: string): { name: string; bot: boolean } {
  const m = /^(.*\S)\s+\(bot\)$/.exec(name);
  return m ? { name: m[1]!, bot: true } : { name, bot: false };
}

/** A recorded outcome in a word, for a player's recent games. */
export const OUTCOME_WORD: Record<Outcome, string> = { win: "Won", loss: "Lost", draw: "Draw", none: "—" };

/**
 * Each player's signature commander(s): the ones they played most often, in `results` (newest first; a tie goes to the
 * most recent). Keyed by pod player id; players who never had a commander recorded are left out.
 */
export function signatureCommanders(results: GameResult[]): Map<string, string[]> {
  const counts = new Map<string, Map<string, { n: number; first: number; commanders: string[] }>>();
  results.forEach((r, i) => {
    for (const p of r.players) {
      if (!p.commanders.length) continue;
      const key = p.commanders.join(" & ");
      const mine = counts.get(p.player_id) ?? new Map();
      const c = mine.get(key) ?? { n: 0, first: i, commanders: p.commanders };
      c.n += 1;
      mine.set(key, c);
      counts.set(p.player_id, mine);
    }
  });
  const out = new Map<string, string[]>();
  for (const [id, mine] of counts) {
    const best = [...mine.values()].sort((a, b) => b.n - a.n || a.first - b.first)[0]!;
    out.set(id, best.commanders);
  }
  return out;
}

/** The game night a result belongs to: its local date, a game recorded before 5 am counting for the night before. */
export function nightKey(iso: string): string {
  const d = new Date(iso);
  if (d.getHours() < 5) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export interface Night {
  key: string;
  /** "Sunday, November 2, 2026" */
  label: string;
  games: GameResult[];
  /** Wins that night, most first: [name, wins]. */
  tally: [string, number][];
}

/** Results (newest first) grouped into game nights, newest night first, each with its games in the same order. */
export function groupByNight(results: GameResult[]): Night[] {
  const nights: Night[] = [];
  for (const r of results) {
    const key = nightKey(r.recorded_at);
    let night = nights[nights.length - 1];
    if (!night || night.key !== key) {
      const [y, m, d] = key.split("-").map(Number) as [number, number, number];
      const label = new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
      night = { key, label, games: [], tally: [] };
      nights.push(night);
    }
    night.games.push(r);
  }
  for (const night of nights) {
    const wins = new Map<string, number>();
    for (const g of night.games) {
      if (g.result_type !== "single" && g.result_type !== "multiple") continue;
      for (const w of g.winners) wins.set(w, (wins.get(w) ?? 0) + 1);
    }
    night.tally = [...wins].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }
  return nights;
}

/** What the header says about the history: how many games, how many players, when the last one was. */
export function podSummary(results: GameResult[], limit = 100): { games: string; players: number; last: string | null } {
  const players = new Set(results.flatMap((r) => r.players.map((p) => p.player_id)));
  return {
    games: `${results.length}${results.length >= limit ? "+" : ""} game${results.length === 1 ? "" : "s"}`,
    players: players.size,
    last: results[0]?.recorded_at ?? null,
  };
}
