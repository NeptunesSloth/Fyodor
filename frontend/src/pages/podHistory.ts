import type { EliminationEntry, FinalBoardSeat } from "../services/pod";

/*
 * -- pod history -- words for a recorded game's elimination order and final board (docs/GAME_NIGHT_FLOW.md, "Pod session and
 * game are different objects"), shared by Pod stats and the lobby's session recap. Everything here is public: the server
 * builds both from what a spectator could see.
 */

export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

const HOW: Record<string, string> = {
  life: "0 life",
  poison: "poison",
  commander_damage: "commander damage",
  empty_library: "drew from an empty library",
  effect: "an effect",
  conceded: "conceded",
  left: "left the table",
};

/** How a player went out, in a few words ("commander damage", "conceded"); the engine's own words when nothing shorter fits. */
export function howText(e: Pick<EliminationEntry, "how" | "reason">): string {
  return HOW[e.how] ?? (e.reason || "out");
}

function names(list: string[]): string {
  return list.length <= 1 ? (list[0] ?? "") : `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

/**
 * One line per place: "1st out: Bob (turn 7, commander damage)". Players out in the same action share their place:
 * "3rd out: Ann and Ben together (turn 9, 0 life)", or each with their own reason when those differ. Each line also comes in
 * parts for styling, `${head} ${who}${rest}` being its text ("1st out:", "Bob", " (turn 7, commander damage)").
 */
export function eliminationLines(list: EliminationEntry[] | undefined): { place: number; text: string; head: string; who: string; rest: string }[] {
  const groups: EliminationEntry[][] = [];
  for (const e of list ?? []) {
    const last = groups[groups.length - 1];
    if (last && last[0]!.place === e.place) last.push(e);
    else groups.push([e]);
  }
  return groups.map((group) => {
    const first = group[0]!;
    const turn = first.turn != null && group.every((e) => e.turn === first.turn) ? `turn ${first.turn}` : null;
    const head = `${ordinal(first.place)} out:`;
    const line = (who: string, rest: string) => ({ place: first.place, text: `${head} ${who}${rest}`, head, who, rest });
    if (group.length === 1) return line(first.name, ` (${[turn, howText(first)].filter(Boolean).join(", ")})`);
    const hows = new Set(group.map(howText));
    if (hows.size === 1) return line(`${names(group.map((e) => e.name))} together`, ` (${[turn, howText(first)].filter(Boolean).join(", ")})`);
    return line(`${names(group.map((e) => `${e.name} (${howText(e)})`))} together`, turn ? `, ${turn}` : "");
  });
}

const counted = (p: { name: string; count: number }) => (p.count > 1 ? `${p.name} ×${p.count}` : p.name);

/** One player's final table in a few short lines. */
export function boardLines(seat: FinalBoardSeat): { stats: string; permanents: string; lands: string; zones: string } {
  const perms = seat.permanents.filter((p) => !p.land).map(counted);
  const lands = seat.permanents.filter((p) => p.land).map(counted);
  const more = seat.more > 0 ? ` and ${seat.more} more` : "";
  return {
    stats: [`${seat.life} life`, seat.poison > 0 ? `${seat.poison} poison` : null].filter(Boolean).join(" · "),
    permanents: perms.length ? perms.join(", ") + (lands.length ? "" : more) : lands.length ? "" : seat.more > 0 ? `${seat.more} permanents` : "No permanents",
    lands: lands.length ? `Lands: ${lands.join(", ")}${more}` : "",
    zones: `Graveyard ${seat.graveyard} · Exile ${seat.exile}`,
  };
}
