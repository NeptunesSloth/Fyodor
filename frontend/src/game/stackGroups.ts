/**
 * Batches of identical stack objects (400 landfall triggers from one Scute Swarm): consecutive objects with the same group key share one
 * row, "Scute Swarm — landfall ×400", that opens to show each. Pure and linear, so a stack of thousands stays cheap to lay out.
 *
 * Only *consecutive* identical objects group (a different object between two batches keeps them apart), the order is kept, and the
 * top of the stack stays first. An object with a null key (a spell, a targeted ability, anything a player must still answer) always
 * has a row of its own.
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
