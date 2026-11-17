/**
 * -- Teach Fyodor -- where a piece may snap. The workspace offers slots (between rows, inside containers, the hat); a piece
 * dragged or picked from the palette is allowed into the slots whose place reads as English, so the backend's shape check
 * (app/rules/taught._ability) rarely has anything to say. Target and Value chips snap onto a row's settings instead.
 */

import { CONTAINERS, HATS, type Node, type Path, type Script } from "./script";
import type { Piece, Slot, Value, Vocabulary } from "./types";

export interface Slots { pieces: Record<string, Piece> }

const byId = (voc: Vocabulary): Record<string, Piece> => Object.fromEntries(voc.pieces.map((p) => [p.id, p]));

/** The roles a body may hold under each kind of hat. */
function bodyRoles(hatRole: string | null): Set<string> {
  if (hatRole === "activated") return new Set(["cost", "limit", "effect", "may", "ifdo", "then"]);
  if (hatRole === "static_hat") return new Set(["condition", "static"]);
  if (hatRole === "action_hat") return new Set(["effect", "may", "ifdo", "then", "optional_cost"]); // (no If: the card's words say when)
  return new Set(["condition", "effect", "may", "ifdo", "then", "optional_cost"]);
}

/** May ``piece`` go into ``ability``'s body at ``index`` (top level), given what is already there? */
export function allowsInBody(piece: Piece, hat: Piece | null, body: Node[], index: number, voc: Vocabulary): boolean {
  const pieces = byId(voc);
  const roles = body.map((n) => pieces[n.id]?.role ?? "");
  const hatRole = hat?.role ?? null;
  if (!bodyRoles(hatRole).has(piece.role)) return false;
  if (piece.role === "condition") {
    if (roles.includes("condition")) return false;
    if (piece.trigger_only && hatRole === "static_hat") return false;
    return index === 0;
  }
  const after = roles.includes("condition") ? 1 : 0; // (an If piece stays first)
  if (index < after) return false;
  if (piece.role === "static") return !roles.includes("static") && !(piece.needs_condition && !roles.includes("condition"))
    && !(piece.no_condition && roles.includes("condition"));
  if (piece.role === "cost") {
    const costs = roles.filter((r) => r === "cost").length;
    if ((piece.id === "cost_tap" || piece.id === "cost_sac_self") && body.some((n) => n.id === piece.id)) return false;
    return index <= costs;
  }
  if (piece.role === "limit") {
    const limits = roles.filter((r) => r === "limit").length;
    return index >= roles.length - limits;
  }
  const costs = roles.filter((r) => r === "cost").length;
  const limits = roles.filter((r) => r === "limit").length;
  if (index < costs || index > roles.length - limits) return false;
  if (piece.role === "ifdo") return roles[index - 1] === "may";
  if (piece.role === "then") return ["effect", "may"].includes(roles[index - 1] ?? "") && ["effect", "may"].includes(roles[index] ?? "");
  if (piece.after) {
    const before = body.slice(0, index).filter((n) => pieces[n.id]?.role !== "then");
    return before[before.length - 1]?.id === piece.after;
  }
  return true;
}

/** May ``piece`` go inside a container (You may / If you do / You may pay …)? */
export function allowsInside(piece: Piece, container: Piece, body: Node[], voc: Vocabulary, before: Node | null = null): boolean {
  const pieces = byId(voc);
  if (container.role === "may") {
    // one Do piece you do yourself; one that follows another piece ("Keep one of the milled cards") needs it right above the You may
    return piece.role === "effect" && !!piece.may && body.length === 0 && (!piece.after || before?.id === piece.after);
  }
  if (piece.role === "effect") return !piece.after || body.some((n) => n.id === piece.after);
  if (piece.role === "may") return true;
  if (piece.role === "then") return body.length > 0 && ["effect", "may"].includes(pieces[body[body.length - 1]!.id]?.role ?? "");
  return false;
}

export interface DropSpot { path: Path; kind: "hat" | "body" | "inside" }

/** Every place on the script where the piece would snap, for the highlights while it is dragged. */
export function spots(piece: Piece, script: Script, voc: Vocabulary): DropSpot[] {
  const pieces = byId(voc);
  const out: DropSpot[] = [];
  const alreadyStatic = (ab: Script["abilities"][number]) => ab.body.some((n) => pieces[n.id]?.role === "static");
  script.abilities.forEach((ab, a) => {
    const hat = ab.hat ? pieces[ab.hat.id] ?? null : null;
    if (HATS.has(piece.role)) {
      // a hat may always be set or swapped, unless the body no longer fits under it
      const fits = ab.body.every((n) => bodyRoles(piece.role).has(pieces[n.id]?.role ?? ""));
      if (fits && (!hat || hat.id !== piece.id)) out.push({ path: { ability: a, index: [] }, kind: "hat" });
      return;
    }
    if (!hat) return;
    if (piece.role === "static" && alreadyStatic(ab)) return;
    for (let i = 0; i <= ab.body.length; i++) {
      if (allowsInBody(piece, hat, ab.body, i, voc)) out.push({ path: { ability: a, index: [i] }, kind: "body" });
    }
    const walk = (list: Node[], prefix: number[]) => {
      list.forEach((n, i) => {
        const p = pieces[n.id];
        if (!p || !CONTAINERS.has(p.role)) return;
        const before = list.slice(0, i).filter((x) => pieces[x.id]?.role !== "then").pop() ?? null;
        if (allowsInside(piece, p, n.body ?? [], voc, before)) out.push({ path: { ability: a, index: [...prefix, i, (n.body ?? []).length] }, kind: "inside" });
        if (p.role !== "may") walk(n.body ?? [], [...prefix, i]);
      });
    };
    walk(ab.body, []);
  });
  return out;
}

/** Where a click on the palette puts the piece: the first open spot in the active ability, else anywhere. */
export function firstSpot(piece: Piece, script: Script, voc: Vocabulary, active: number): DropSpot | null {
  const all = spots(piece, script, voc);
  const pref = all.filter((s) => s.path.ability === active);
  const pick = (list: DropSpot[]) => list.length ? list[list.length - 1]! : null; // (the last spot: the bottom of the stack)
  if (HATS.has(piece.role)) return pref[0] ?? all[0] ?? null;
  const waiting = pref.find((s) => s.kind === "inside" && s.path.index[s.path.index.length - 1] === 0); // an empty You may / If you do
  const own = pref.filter((s) => s.kind === "body" && s.path.index.length === 1);
  return waiting ?? pick(own) ?? pick(pref) ?? pick(all);
}

// ------------------------------------------------------------------------------------------------------------ chips on slots
/** A Target chip (an option id) may land on a choice setting that offers it; a Value chip on a number setting. */
export function chipFits(chip: Value, slot: Slot, param: boolean): boolean {
  if (slot.kind === "choice") return typeof chip === "string" && slot.options.includes(chip);
  if (slot.kind === "mana") return false;
  if (chip === "N") return param && slot.param;
  return typeof chip === "number" && chip >= slot.min && chip <= slot.max;
}

/** The settings of a row a chip fits, for the highlights. */
export function chipSlots(chip: Value, piece: Piece, param: boolean): string[] {
  return Object.entries(piece.slots ?? {}).filter(([, s]) => chipFits(chip, s, param)).map(([k]) => k);
}
