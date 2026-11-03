import type { LobbyDeckBody, MyDeck } from "../services/games";
import type {
  LiveSummary,
  Market,
  PredictionRecap,
  PredictionsView,
  QueuedDeck,
  SandboxBoard,
  SandboxResult,
  Scenario,
  ScenarioCreature,
} from "../services/spectate";

/*
 * Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md): the logic behind the practice table's live corner,
 * the damage sandbox, predictions and the next-game queue. The server builds every payload from the public view; nothing
 * here sends a game action.
 */

// --------------------------------------------------------------------------- live summary

/** "Turn 7 · Bob's turn · 3 still in" */
export function pipHeadline(s: LiveSummary): string {
  const left = s.players.filter((p) => !p.out).length;
  return [`Turn ${s.turn}`, `${s.active_name}'s turn`, `${left} still in`].join(" · ");
}

/** "Stack 2 · Lightning Bolt on top", or null when the stack is empty. */
export function pipStack(s: LiveSummary): string | null {
  if (!s.stack.count) return null;
  return `Stack ${s.stack.count}${s.stack.top ? ` · ${s.stack.top} on top` : ""}`;
}

export const LETHAL_COMMANDER = 21;

export interface PipRow {
  id: string;
  name: string;
  color: string | null;
  life: number;
  poison: number;
  out: boolean;
  active: boolean;
  /** The most commander damage this player has taken from one commander, if any. */
  commander: { name: string; damage: number } | null;
}

/** One row per player, in seat order: life, poison and the heaviest commander damage taken. */
export function pipRows(s: LiveSummary): PipRow[] {
  return s.players.map((p) => {
    const top = [...p.commander_damage].sort((a, b) => b.damage - a.damage)[0];
    return {
      id: p.id, name: p.name, color: p.color, life: p.life, poison: p.poison, out: !!p.out, active: p.id === s.active,
      commander: top ? { name: top.name, damage: top.damage } : null,
    };
  });
}

// --------------------------------------------------------------------------- damage sandbox

export interface SandboxState {
  players: Scenario["players"];
  creatures: ScenarioCreature[];
  commanders: Record<string, string>;
}

/**
 * The sandbox as it starts: the public board, with its current public combat copied (COPY CURRENT PUBLIC COMBAT).
 * Players who are out of the game are left out, and so is a combat role that no longer adds up.
 */
export function fromBoard(board: SandboxBoard): SandboxState {
  const players = board.players.filter((p) => !p.out)
    .map((p) => ({ id: p.id, name: p.name, life: p.life, poison: p.poison, commander_damage: { ...p.commander_damage } }));
  const ids = new Set(players.map((p) => p.id));
  const creatures: ScenarioCreature[] = board.creatures.filter((c) => ids.has(c.controller)).map((c) => ({
    id: c.id, name: c.name, controller: c.controller, power: c.power, toughness: c.toughness, damage: c.damage,
    keywords: [...c.keywords], commander: c.commander,
    attacking: c.attacking && ids.has(c.attacking) && c.attacking !== c.controller ? c.attacking : null,
    blocking: c.blocking,
  }));
  return tidy({ players, creatures, commanders: { ...board.commanders } });
}

/** A blocker must block an attacker that attacks its controller (509.1a); anything else is dropped. */
function tidy(st: SandboxState): SandboxState {
  const byId = new Map(st.creatures.map((c) => [c.id, c]));
  const creatures = st.creatures.map((c) => {
    if (!c.blocking) return c;
    const att = byId.get(c.blocking);
    return att && att.attacking === c.controller && !c.attacking ? c : { ...c, blocking: null };
  });
  return { ...st, creatures };
}

/** Attack ``target`` (a player), or stop attacking (null). An attacker can't also block. */
export function setAttack(st: SandboxState, id: string, target: string | null): SandboxState {
  return tidy({ ...st, creatures: st.creatures.map((c) => (c.id === id ? { ...c, attacking: target, blocking: target ? null : c.blocking } : c)) });
}

/** Block ``attacker``, or stop blocking (null). A blocker can't also attack. */
export function setBlock(st: SandboxState, id: string, attacker: string | null): SandboxState {
  return tidy({ ...st, creatures: st.creatures.map((c) => (c.id === id ? { ...c, blocking: attacker, attacking: attacker ? null : c.attacking } : c)) });
}

export function patchCreature(st: SandboxState, id: string, patch: Partial<ScenarioCreature>): SandboxState {
  return tidy({ ...st, creatures: st.creatures.map((c) => (c.id === id ? { ...c, ...patch } : c)) });
}

export function patchPlayer(st: SandboxState, id: string, patch: Partial<Scenario["players"][number]>): SandboxState {
  return { ...st, players: st.players.map((p) => (p.id === id ? { ...p, ...patch } : p)) };
}

/** Who a creature may attack: its controller's opponents still in the game. */
export function attackTargets(st: SandboxState, c: ScenarioCreature): Scenario["players"] {
  return st.players.filter((p) => p.id !== c.controller);
}

/** What a creature may block: the attackers attacking its controller (509.1a). */
export function blockTargets(st: SandboxState, c: ScenarioCreature): ScenarioCreature[] {
  return st.creatures.filter((a) => a.attacking === c.controller && a.id !== c.id);
}

/** The scenario the server works out: the players and the creatures in this combat. */
export function toScenario(st: SandboxState): Scenario {
  const clean = tidy(st);
  return { players: clean.players, creatures: clean.creatures.filter((c) => c.attacking || c.blocking) };
}

export const ROUND_LABEL: Record<SandboxResult["rounds"][number]["round"], string> = {
  only: "Combat damage",
  first: "First-strike damage",
  second: "Regular damage",
};

export interface ResultText {
  rounds: { label: string; lines: string[] }[];
  players: string[];
  creatures: string[];
  losers: string[];
}

/** The result in words, with names instead of ids. */
export function describeResult(st: SandboxState, res: SandboxResult): ResultText {
  const creature = new Map(st.creatures.map((c) => [c.id, c.name]));
  const player = new Map(st.players.map((p) => [p.id, p.name]));
  const name = (id: string) => creature.get(id) ?? player.get(id) ?? id;
  const cmd = (key: string) => st.commanders[key] ?? "a commander";
  const rounds = res.rounds.map((r) => ({
    label: ROUND_LABEL[r.round],
    lines: r.dealt.length ? r.dealt.map((d) => `${name(d.source)} → ${name(d.target)}: ${d.amount}`) : ["No damage"],
  }));
  const players = res.players.map((p) => {
    const parts = [`${name(p.id)}: ${p.life_before} → ${p.life} life`];
    if (p.poison !== p.poison_before) parts.push(`${p.poison_before} → ${p.poison} poison`);
    for (const [key, n] of Object.entries(p.commander_damage)) parts.push(`${n} commander damage from ${cmd(key)}`);
    return parts.join(" · ");
  });
  const creatures = res.creatures.filter((c) => c.died).map((c) => `${name(c.id)} dies (${c.died})`);
  const losers = res.players.filter((p) => p.loses.length)
    .map((p) => `${name(p.id)} loses: ${p.loses.map((why) => why.replace(/\(([^)]+)\)$/, (_, key: string) => `(${cmd(key)})`)).join(", ")}`);
  return { rounds, players, creatures, losers };
}

// --------------------------------------------------------------------------- predictions

export const MARKET_LABEL: Record<Market, string> = {
  winner: "Who wins the game?",
  next_out: "Who is eliminated next?",
};

/** The stakes you can put on ``market`` now (changing a pick frees its old stake first). */
export function stakeOptions(v: PredictionsView, market: Market): number[] {
  const free = v.available + (v.picks[market] && v.picks[market]!.outcome === null ? v.picks[market]!.stake : 0);
  return v.stakes.filter((s) => s <= free);
}

/** "Spectator predictions — Carol 575 · Dana 390" */
export function recapLine(r: PredictionRecap): string {
  return `Spectator predictions — ${r.standings.map((s) => `${s.name} ${s.balance}`).join(" · ")}`;
}

// --------------------------------------------------------------------------- next-game queue

/** What to send for one of My decks: its saved list (an Archidekt link alone is fetched in the lobby, not here). */
export function queueBody(d: Pick<MyDeck, "name" | "body">): LobbyDeckBody | null {
  const { text, json } = d.body;
  if (!(text && text.trim()) && !json) return null;
  return { name: d.body.name ?? d.name, ...(text ? { text } : {}), ...(json ? { json } : {}) };
}

/** "Muldrotha, the Gravetide" (the commanders), else the deck's name. */
export function queuedLabel(q: Pick<QueuedDeck, "name" | "commanders">): string {
  return q.commanders.length ? q.commanders.join(" & ") : q.name;
}
