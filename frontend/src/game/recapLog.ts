import type { GameView, LogEntryView } from "../types/game";
import { partText } from "./HistoryDialog";

/**
 * -- turn recap -- what the other players did since my last turn, from the log in my own view (public lines only: the server already
 * left out what I may not read). One section per finished turn: "Bob · Turn 3: played Forest · cast Llanowar Elves · attacks Alice
 * with Grizzly Bears · Combat damage: Alice takes 2", and my life change over it.
 */
export interface RecapSection { turn: number; who: string; lines: string[]; life: number }

/** Log kinds that are bookkeeping, not something a player did. */
const SKIP_KINDS = new Set(["phase", "turn", "mana", "minor", "chat"]);
/** Lines that say nothing new (the draw step's card, an attacker tapping, combat ending, a spell resolving after its cast line). */
const NOISE = /drew a card$|cleared combat$| tapped [^,]+$|^Resolved |passed priority|passes priority/;

const lineText = (e: LogEntryView) => e.parts.map(partText).join("");

/** Who took each turn, from the log's "Turn 3: Bob" lines. */
export function turnTakers(log: LogEntryView[]): Map<number, string> {
  const out = new Map<number, string>();
  for (const e of log) {
    if (e.kind !== "turn") continue;
    const m = /^Turn (\d+): (.+)$/.exec(lineText(e).trim());
    if (m) out.set(Number(m[1]), m[2]!);
  }
  return out;
}

/** The finished turns of other players since my last one (and after `after`, what I already dismissed), oldest first. */
export function recapSections(view: GameView, me: string, after = 0): RecapSection[] {
  const myName = view.players.find((p) => p.id === me)?.name;
  if (!myName) return [];
  const now = view.turn.number;
  const takers = turnTakers(view.log);
  let since = after;
  for (const [t, who] of takers) if (who === myName && t < now) since = Math.max(since, t);
  const life = view.players.find((p) => p.id === me)?.life_history ?? [];
  const out: RecapSection[] = [];
  for (const [t, who] of [...takers].sort((a, b) => a[0] - b[0])) {
    if (t <= since || t >= now || who === myName) continue;
    const lines: string[] = [];
    for (const e of view.log) {
      if (e.turn !== t || e.actor === me || SKIP_KINDS.has(e.kind)) continue;
      const text = lineText(e).trim();
      if (!text || NOISE.test(text)) continue;
      lines.push(text.startsWith(`${who} `) ? text.slice(who.length + 1) : text);
    }
    const delta = life.filter((h) => h.turn === t).reduce((n, h) => n + h.after - h.before, 0);
    if (lines.length || delta) out.push({ turn: t, who, lines, life: delta });
  }
  return out;
}
