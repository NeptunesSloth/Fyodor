/**
 * -- Teach Fyodor -- the script on the workspace: the thing being taught (a keyword, or one card's line) and its abilities as
 * stacks of pieces. Every piece on the workspace carries a uid (for keys, focus and drag); ``toEntry`` strips them into the
 * entry the backend checks and stores (app/rules/taught.clean_entry refuses anything else).
 */

import type { Ability, Block, Entry, Kind, Piece, Value, Vocabulary } from "./types";

export interface Node {
  uid: string;
  id: string;
  values: Record<string, Value>;
  body?: Node[];
}

export interface ScriptAbility { uid: string; hat: Node | null; body: Node[] }

export interface Script {
  kind: Kind;
  name: string;
  param: boolean;
  reminder: string;
  card: { oracle_id: string; line: string; card_name: string; type_line: string } | null;
  abilities: ScriptAbility[];
}

/** Where a piece sits: which ability, then the indexes down through containers (``[]``: the hat). */
export interface Path { ability: number; index: number[] }

let counter = 0;
export const uid = (): string => `b${++counter}-${Math.random().toString(36).slice(2, 7)}`;

export const CONTAINERS = new Set(["may", "ifdo", "optional_cost"]);
export const HATS = new Set(["trigger", "activated", "static_hat", "action_hat"]);
export const ACTION_HAT = "action";

export function defaults(piece: Piece): Record<string, Value> {
  const out: Record<string, Value> = {};
  for (const [k, slot] of Object.entries(piece.slots ?? {})) out[k] = slot.default;
  return out;
}

export function newNode(piece: Piece): Node {
  const node: Node = { uid: uid(), id: piece.id, values: defaults(piece) };
  if (CONTAINERS.has(piece.role)) node.body = [];
  return node;
}

export function newAbility(hat: Node | null = null): ScriptAbility {
  return { uid: uid(), hat, body: [] };
}

/** The one hat of a taught action (no settings: the page puts it there, the palette doesn't offer it). */
export const actionHat = (): Node => ({ uid: uid(), id: ACTION_HAT, values: {} });

export function emptyScript(kind: Kind = "keyword"): Script {
  return { kind, name: "", param: false, reminder: "", card: null, abilities: [newAbility(kind === "action" ? actionHat() : null)] };
}

/** The same thing being taught as another kind: an action keeps only its name, since its stack starts with the action hat. */
export function asKind(script: Script, kind: Kind): Script {
  if (kind === script.kind) return script;
  if (kind === "action" || script.kind === "action") return { ...emptyScript(kind), name: script.name, param: script.param, reminder: script.reminder };
  return { ...script, kind };
}

// ------------------------------------------------------------------------------------------------------------ to / from
function toBlock(n: Node, piece: Piece | undefined): Block {
  const out: Block = { id: n.id };
  const slots = piece?.slots ?? {};
  const values: Record<string, Value> = {};
  for (const k of Object.keys(slots)) if (k in n.values) values[k] = n.values[k]!;
  if (Object.keys(values).length) out.values = values;
  if (n.body) out.body = n.body.map((c) => toBlock(c, undefined));
  return out;
}

/** The entry the backend checks and saves: only ids, values and bodies (uids and empty hats stripped). */
export function toEntry(script: Script, voc?: Vocabulary): Entry {
  const byId = voc ? Object.fromEntries(voc.pieces.map((p) => [p.id, p])) : {};
  const fix = (n: Node): Block => {
    const b = toBlock(n, byId[n.id]);
    if (!voc && Object.keys(n.values).length) b.values = { ...n.values };
    if (n.body) b.body = n.body.map(fix);
    return b;
  };
  const abilities: Ability[] = script.abilities.filter((a) => a.hat).map((a) => ({ hat: fix(a.hat!), body: a.body.map(fix) }));
  if (script.kind === "action") return { kind: "action", name: script.name.trim().toLowerCase(), param: script.param, reminder: script.reminder.trim(), abilities };
  if (script.kind === "card") {
    const c = script.card ?? { oracle_id: "", line: "", card_name: "", type_line: "" };
    return { kind: "card", oracle_id: c.oracle_id, line: c.line, card_name: c.card_name, type_line: c.type_line, name: c.card_name, abilities };
  }
  return { kind: "keyword", name: script.name.trim(), param: script.param, reminder: script.reminder.trim(), abilities };
}

function fromBlock(b: Block): Node {
  const n: Node = { uid: uid(), id: b.id, values: { ...(b.values ?? {}) } };
  if (b.body) n.body = b.body.map(fromBlock);
  return n;
}

export function fromEntry(entry: Entry): Script {
  const abilities = entry.abilities.map((a) => ({ uid: uid(), hat: fromBlock(a.hat), body: a.body.map(fromBlock) }));
  if (entry.kind === "card") {
    return { kind: "card", name: entry.card_name, param: false, reminder: "",
      card: { oracle_id: entry.oracle_id, line: entry.line, card_name: entry.card_name, type_line: entry.type_line ?? "" },
      abilities: abilities.length ? abilities : [newAbility()] };
  }
  if (entry.kind === "action") {
    return { kind: "action", name: entry.name, param: entry.param, reminder: entry.reminder ?? "", card: null,
      abilities: abilities.length ? abilities : [newAbility(actionHat())] };
  }
  return { kind: "keyword", name: entry.name, param: entry.param, reminder: entry.reminder ?? "", card: null,
    abilities: abilities.length ? abilities : [newAbility()] };
}

// ------------------------------------------------------------------------------------------------------------ editing
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

/** The list a path's last index points into (the ability body, or a container's body). */
function listAt(script: Script, path: Path): Node[] {
  let list = script.abilities[path.ability]!.body;
  for (const i of path.index.slice(0, -1)) {
    const node = list[i]!;
    node.body ??= [];
    list = node.body;
  }
  return list;
}

export function nodeAt(script: Script, path: Path): Node | null {
  const ab = script.abilities[path.ability];
  if (!ab) return null;
  if (!path.index.length) return ab.hat;
  let list = ab.body;
  let node: Node | undefined;
  for (const i of path.index) {
    node = list[i];
    if (!node) return null;
    list = node.body ?? [];
  }
  return node ?? null;
}

/** Put ``node`` at ``path`` (as the hat when the path has no index; otherwise inserted before that index). */
export function insert(script: Script, path: Path, node: Node): Script {
  const out = clone(script);
  while (out.abilities.length <= path.ability) out.abilities.push(newAbility());
  if (!path.index.length) {
    out.abilities[path.ability]!.hat = node;
    return out;
  }
  const list = listAt(out, path);
  const at = Math.min(Math.max(path.index[path.index.length - 1]!, 0), list.length);
  list.splice(at, 0, node);
  return out;
}

export function remove(script: Script, path: Path): Script {
  const out = clone(script);
  const ab = out.abilities[path.ability];
  if (!ab) return out;
  if (!path.index.length) ab.hat = null;
  else listAt(out, path).splice(path.index[path.index.length - 1]!, 1);
  return out;
}

/** Find a node by uid: its path, or null. */
export function find(script: Script, id: string): Path | null {
  const walk = (list: Node[], prefix: number[], ability: number): Path | null => {
    for (const [i, n] of list.entries()) {
      if (n.uid === id) return { ability, index: [...prefix, i] };
      if (n.body) {
        const deep = walk(n.body, [...prefix, i], ability);
        if (deep) return deep;
      }
    }
    return null;
  };
  for (const [a, ab] of script.abilities.entries()) {
    if (ab.hat?.uid === id) return { ability: a, index: [] };
    const got = walk(ab.body, [], a);
    if (got) return got;
  }
  return null;
}

/** Move a node to another place (the destination path counts positions as they are before the node leaves). */
export function move(script: Script, from: Path, to: Path): Script {
  const node = nodeAt(script, from);
  if (!node) return script;
  if (!to.index.length) return insert(remove(script, from), to, node);
  // the same list, moving down: the gap closes, so the target slips one up
  const sameList = from.ability === to.ability && from.index.length === to.index.length
    && from.index.slice(0, -1).every((v, i) => v === to.index[i]);
  const dest: Path = { ability: to.ability, index: [...to.index] };
  if (sameList && to.index[to.index.length - 1]! > from.index[from.index.length - 1]!) dest.index[dest.index.length - 1]! -= 1;
  // moving into one's own body is not a move
  if (from.ability === to.ability && to.index.length > from.index.length && from.index.every((v, i) => v === to.index[i])) return script;
  return insert(remove(script, from), dest, node);
}

export function setValue(script: Script, path: Path, key: string, value: Value): Script {
  const out = clone(script);
  const node = nodeAt(out, path);
  if (node) node.values[key] = value;
  return out;
}

export function removeAbility(script: Script, index: number): Script {
  const out = clone(script);
  out.abilities.splice(index, 1);
  if (!out.abilities.length) out.abilities.push(newAbility());
  return out;
}

export function addAbility(script: Script): Script {
  return { ...clone(script), abilities: [...script.abilities, newAbility()] };
}

/** Every uid in the script, top to bottom (keyboard order). */
export function order(script: Script): { uid: string; path: Path }[] {
  const out: { uid: string; path: Path }[] = [];
  const walk = (list: Node[], prefix: number[], ability: number) => {
    list.forEach((n, i) => {
      out.push({ uid: n.uid, path: { ability, index: [...prefix, i] } });
      if (n.body) walk(n.body, [...prefix, i], ability);
    });
  };
  script.abilities.forEach((ab, a) => {
    if (ab.hat) out.push({ uid: ab.hat.uid, path: { ability: a, index: [] } });
    walk(ab.body, [], a);
  });
  return out;
}

/** A script that holds something worth checking (a hat and at least one piece under it). */
export const hasWork = (script: Script): boolean => script.abilities.some((a) => a.hat && a.body.length);
