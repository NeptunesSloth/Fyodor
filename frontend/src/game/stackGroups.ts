import type { TableArrow } from "../types/game";

/**
 * Batches of identical stack objects (400 landfall triggers from one Scute Swarm): consecutive objects with the same group key share one
 * row, "Scute Swarm — landfall ×400", that opens to show each. Pure and linear, so a stack of thousands stays cheap to lay out.
 *
 * Only *consecutive* identical objects group (a different object between two batches keeps them apart), the order is kept, and the
 * top of the stack stays first. An object with a null key (a spell, anything a player must still answer) always has a row of its own; a
 * targeted ability groups only with ones that target exactly the same (its targets are part of its key).
 */

export interface StackGroup {
  /** The top-most object of the group (what resolves first of them; hover, drag and "stop after" act on it). */
  id: string;
  /** The group's objects, top first. */
  ids: string[];
  /** Chain number of the top-most object (1 = bottom of the stack). */
  no: number;
}

/**
 * Group the stack (`stack` bottom first, as the server sends it) into rows, top first. `keyOf` gives an object's group key, or null when
 * it must stay on its own; it is called once per object.
 */
export function groupStack(stack: readonly string[], keyOf: (id: string) => string | null): StackGroup[] {
  const out: StackGroup[] = [];
  let lastKey: string | null = null;
  for (let i = stack.length - 1; i >= 0; i--) {
    const id = stack[i]!;
    const key = keyOf(id);
    const last = out[out.length - 1];
    if (last && key !== null && key === lastKey) last.ids.push(id);
    else out.push({ id, ids: [id], no: i + 1 });
    lastKey = key;
  }
  return out;
}

/** The group key of a triggered or activated ability on the stack: its source's name, its text and its controller (and anything noted
 * on it, so two objects that read differently never merge). */
export function abilityKey(sourceName: string | null | undefined, text: string, controller: string, notes = ""): string {
  return JSON.stringify([sourceName ?? "", text, controller, notes]);
}

/** A short name for an ability: its ability word ("Landfall — Whenever …" → "landfall"), else "trigger" / "ability". */
export function abilityShortName(text: string, kind?: string | null): string {
  const word = /^([A-Za-z][A-Za-z' -]{0,38}?)\s+—\s/.exec(text.trim());
  if (word) return word[1]!.toLowerCase();
  if (kind === "triggered" || /^(when|whenever|at)\b/i.test(text.trim())) return "trigger";
  return "ability";
}

/** A batch row's title: "Scute Swarm — landfall ×400" (a single object: "Scute Swarm — landfall"). */
export function batchTitle(sourceName: string | null | undefined, text: string, kind: string | null | undefined, count: number): string {
  const name = `${sourceName || "Ability"} — ${abilityShortName(text, kind)}`;
  return count > 1 ? `${name} ×${count.toLocaleString("en-US")}` : name;
}

/** How many rows to draw at once: past this the list ends in "Show N more" (a thousand different objects stay quick to draw). */
export const ROW_LIMIT = 150;

/** How many target arrows from stack objects the table draws at most (the top of the stack first): a board wipe under Blood Artist put
 * 154 targeted triggers on the stack, and 130 dashed arrows covered the table (playtest B3). */
export const STACK_ARROW_CAP = 24;

/** One arrow line on the table: from a stack row (or a permanent, or a player) to one target, standing for `count` arrows. */
export interface ArrowLine {
  key: string;
  source: string;
  target: string;
  kind: TableArrow["kind"];
  label?: string | undefined;
  count: number;
}

/**
 * The table's arrows, one line per (source, target, kind): the arrows of a batch of identical stack objects (`groups`, chainEntries)
 * leave from the batch's row as one line marked ×N, and at most `cap` lines leave from the stack, top of the stack first. Arrows from
 * anything else (an attack, an arrow a player drew) are all kept.
 */
export function arrowLines(arrows: readonly TableArrow[], groups: readonly StackGroup[], cap = STACK_ARROW_CAP): ArrowLine[] {
  const topOf = new Map<string, string>();
  const rank = new Map<string, number>();
  groups.forEach((g, i) => {
    rank.set(g.id, i);
    for (const id of g.ids) topOf.set(id, g.id);
  });
  const lines = new Map<string, ArrowLine>();
  for (const a of arrows) {
    const source = topOf.get(a.source) ?? a.source;
    a.targets.forEach((target, i) => {
      const key = `${source}|${target}|${a.kind}`;
      const line = lines.get(key);
      if (line) line.count += 1;
      else lines.set(key, { key, source, target, kind: a.kind, label: i === 0 && a.label ? a.label : undefined, count: 1 });
    });
  }
  const all = [...lines.values()];
  const fromStack = all.filter((l) => rank.has(l.source)).sort((x, y) => rank.get(x.source)! - rank.get(y.source)!).slice(0, cap);
  const out = [...all.filter((l) => !rank.has(l.source)), ...fromStack];
  for (const l of out) if (l.count > 1) l.label = `${l.label ? `${l.label} ` : ""}×${l.count.toLocaleString("en-US")}`;
  return out;
}
