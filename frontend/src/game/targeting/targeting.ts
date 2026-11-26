/**
 * Targeting, where the board is the picker: which pending decision the table answers by clicking cards and players,
 * what it is for (the source and the words), and how each candidate reads in the tray. Pure functions over the chooser's
 * own view: nothing here knows more than the decision already shows them.
 */
import { useCardCache } from "../../state/cardCache";
import { isVisible, type DecisionOptionView, type DecisionView, type GameCard, type GameView } from "../../types/game";

export interface Candidate {
  option: DecisionOptionView;
  /** The card or player it stands for. */
  ref: string;
  kind: "card" | "player";
  /** The seat it sits with: a card's controller (its owner's, out of play), or the player. */
  seat: string | null;
  /** Where a card is ("battlefield", "graveyard", "hand", "stack" …), null for a player. */
  where: string | null;
  /** The name shown (the option's own label for a player or a hidden card). */
  label: string;
  /** What tells it apart from candidates with the same name ("2/2 · tapped", "in graveyard", "3"), or "". */
  note: string;
}

export interface Targeting {
  decision: DecisionView;
  /** choose_cards: click to toggle, then Done. choose_one: a click answers. */
  multi: boolean;
  min: number;
  max: number;
  /** A cost of N objects (601.2h): none or all N. */
  exactly?: number;
  candidates: Candidate[];
  /** Answers that are neither a card nor a player ("No target"): plain buttons in the bar. */
  others: DecisionOptionView[];
  /** The card the choice is for (the spell being cast, the permanent whose ability it is), when the chooser can see it. */
  source: string | null;
  sourceName: string;
  /** "Choose target creature", "Sacrifice a creature". */
  instruction: string;
}

const NOT_ON_BOARD = new Set(["payment", "tap_mana", "divide", "optional_cost", "looked"]); // (looked: the cards looked at, in the panel)

/** The decision the table answers by clicking, or null (someone else's, a list of words, a payment, the wheel's). */
export function targetingOf(view: GameView | null | undefined, me: string, selection: readonly string[] = []): Targeting | null {
  const d = view?.rules?.decision;
  if (!view || !d || d.player !== me || !d.options?.length) return null;
  if (d.kind !== "choose_one" && d.kind !== "choose_cards") return null;
  if (d.rememberable || (d.display && NOT_ON_BOARD.has(String(d.display.kind)))) return null;
  if (d.options.some((o) => o.group === "seen" || o.id.startsWith("__"))) return null; // card names, numbers: the panel asks
  const seats = new Set(view.players.map((p) => p.id));
  const candidates: Candidate[] = [];
  const others: DecisionOptionView[] = [];
  for (const o of d.options) {
    if (o.id === "cancel") continue;
    const card = o.card_id ? view.cards[o.card_id] : undefined;
    if (o.card_id) {
      const where = card ? zoneName(card.zone) : null;
      const seat = card ? (where === "battlefield" || where === "stack" ? card.controller : card.owner) : null;
      candidates.push({ option: o, ref: o.card_id, kind: "card", seat, where, label: card && isVisible(card) && card.name ? card.name : o.label, note: "" });
    } else if (seats.has(o.id)) {
      candidates.push({ option: o, ref: o.id, kind: "player", seat: o.id, where: null, label: o.label, note: "" });
    } else {
      others.push(o);
    }
  }
  if (!candidates.length || others.length > 3) return null;
  if (librarySearch(view, d)) return null; // -- library search -- a card grid in the panel (RulesHud SearchGrid), not the tray
  const multi = d.kind === "choose_cards";
  const exactly = typeof d.display?.exactly === "number" ? d.display.exactly : undefined;
  const source = sourceOf(view, d, me, selection);
  const sourceCard = source ? view.cards[source] : undefined;
  const sourceName = sourceCard && isVisible(sourceCard) ? sourceCard.ability?.source_name ?? sourceCard.name : promptSource(d.prompt) ?? "";
  notes(candidates, view);
  return {
    decision: d, multi, min: multi ? d.min_choices ?? 1 : 1, max: multi ? d.max_choices ?? 1 : 1, ...(exactly !== undefined ? { exactly } : {}),
    candidates, others, source, sourceName, instruction: instruction(d, candidates, view, promptSource(d.prompt)),
  };
}

const zoneName = (zone: string) => zone.slice(zone.indexOf(":") + 1);

/** -- library search -- a pick of cards that are all in a library (a tutor's or fetch's legal finds, shown to the chooser only). */
export function librarySearch(view: GameView, d: DecisionView): boolean {
  if (d.kind !== "choose_cards") return false;
  const cards = (d.options ?? []).filter((o) => o.card_id);
  return cards.length > 0 && cards.every((o) => view.cards[o.card_id!]?.zone.endsWith(":library"));
}

/** The name a prompt says the choice is for: "Choose a target for Swords to Plowshares", "Contagion Engine: choose a target". */
export function promptSource(prompt: string): string | null {
  const m = /^Choose (?:a target|(?:up to )?\d+ targets?|any number of targets) for (.+?)(?: \((?:mode|group) [^)]*\))?(?:\s*[—(].*)?$/.exec(prompt);
  if (m) return m[1]!.trim();
  const c = /^([^:]{2,80}):\s/.exec(prompt);
  return c ? c[1]!.trim() : null;
}

/**
 * The card the choice is for: the decision's own source when the server names it, else the card the prompt names, looked
 * for where a choice comes from (the card I just selected to cast, my hand, the stack, the battlefield). Display only.
 */
export function sourceOf(view: GameView, d: DecisionView, me: string, selection: readonly string[] = []): string | null {
  if (d.source_id && view.cards[d.source_id]) return d.source_id;
  const name = promptSource(d.prompt);
  if (!name) return null;
  const named = (c: GameCard | undefined): boolean => {
    if (!c || !isVisible(c)) return false;
    if (c.ability) return c.ability.source_name === name;
    return c.name === name || c.name.split(" // ").includes(name);
  };
  const zone = (z: string): string[] => {
    const ids = view.zones[z];
    return Array.isArray(ids) ? ids : [];
  };
  const order = [
    ...selection,
    ...zone(`${me}:hand`),
    ...[...view.stack].reverse(),
    ...zone(`${me}:battlefield`),
    ...view.seat_order.filter((p) => p !== me).flatMap((p) => zone(`${p}:battlefield`)),
    ...view.seat_order.flatMap((p) => zone(`${p}:command`)),
    ...zone(`${me}:graveyard`),
    ...zone(`${me}:exile`),
  ];
  const hit = order.find((id) => named(view.cards[id]));
  if (!hit) return null;
  const c = view.cards[hit];
  // an ability on the stack stands for its source on the table, when that is still there
  const from = c && isVisible(c) ? c.ability?.source_id : null;
  return from && view.cards[from] && !view.stack.includes(hit) ? from : hit;
}

const COUNT_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const countWord = (n: number) => COUNT_WORDS[n] ?? String(n);
const PERMANENT_TYPES = ["creature", "planeswalker", "artifact", "enchantment", "land", "battle"];

/** What a candidate set is, in the words of the rules: "creature", "player", "card in a graveyard", "permanent", "spell". */
function noun(candidates: Candidate[], view: GameView, plural: boolean): string {
  const s = (w: string) => (plural ? `${w}s` : w);
  const players = candidates.filter((c) => c.kind === "player");
  const cards = candidates.filter((c) => c.kind === "card");
  if (!cards.length) return s("player");
  const wheres = new Set(cards.map((c) => c.where));
  if (wheres.size === 1 && wheres.has("battlefield")) {
    const kinds = new Set(cards.map((c) => {
      const t = view.rules?.stats?.[c.ref]?.creature ? "creature" : typeLine(view, c.ref);
      return PERMANENT_TYPES.find((k) => t.includes(k)) ?? "permanent";
    }));
    if (players.length) return kinds.size === 1 && kinds.has("creature") ? `${s("creature")} or ${s("player")}` : "any target";
    return kinds.size === 1 ? s([...kinds][0]!) : s("permanent");
  }
  if (players.length) return "any target";
  if (wheres.size === 1 && wheres.has("graveyard")) {
    const owners = new Set(cards.map((c) => c.seat));
    return `${s("card")} in ${owners.size === 1 && owners.has(view.viewer) ? "your graveyard" : plural ? "graveyards" : "a graveyard"}`;
  }
  if (wheres.size === 1 && wheres.has("stack")) return s("spell");
  if (wheres.size === 1 && wheres.has("hand")) return `${s("card")} in your hand`;
  if (wheres.size === 1 && wheres.has("exile")) return `${s("card")} in exile`;
  return s("card");
}

/** Its type line, lower case: a token's own, else the card database's (as the client has it). */
function typeLine(view: GameView, id: string): string {
  const card = view.cards[id];
  if (!card || !isVisible(card)) return "";
  if (card.token?.type_line) return card.token.type_line.toLowerCase();
  return (card.card_id ? useCardCache.getState().cards[card.card_id]?.type_line ?? "" : "").toLowerCase();
}

/** The printed power/toughness the card database gave the client. */
function basePt(view: GameView, id: string): [string, string] | null {
  const card = view.cards[id];
  const data = card && isVisible(card) && card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
  return data?.power != null && data.toughness != null ? [data.power, data.toughness] : null;
}

/** The bar's words: what to choose, without the source's name (the bar shows its art and name beside them). */
export function instruction(d: DecisionView, candidates: Candidate[], view: GameView, sourceName: string | null): string {
  const p = d.prompt;
  const suffix = /\((mode \d+|group \d+ of \d+)\)/.exec(p)?.[1];
  const tail = suffix ? ` (${suffix})` : "";
  if (/^Choose a target for /.test(p) || /: choose a target$/i.test(p)) return `Choose ${anyOr(noun(candidates, view, false))}${tail}`;
  const many = /^Choose (up to )?(\d+) targets? for /.exec(p);
  if (many) {
    const n = Number(many[2]);
    const what = noun(candidates, view, n !== 1);
    return `Choose ${many[1] ? "up to " : ""}${countWord(n)} ${what === "any target" ? "targets" : `target ${what}`}${tail}`;
  }
  const sac = /^(?:.+?:\s)?sacrifice (\d+) \(([^)]+)\)$/i.exec(p); // "Fleshbag Marauder: sacrifice 1 (creature)"
  if (sac) {
    const n = Number(sac[1]);
    return n === 1 ? `Sacrifice ${/^[aeiou]/i.test(sac[2]!) ? "an" : "a"} ${sac[2]}` : `Sacrifice ${countWord(n)} ${sac[2]}s`;
  }
  let words = sourceName && p.startsWith(`${sourceName}: `) ? p.slice(sourceName.length + 2) : p;
  words = words.charAt(0).toUpperCase() + words.slice(1);
  return words;
}

const anyOr = (what: string) => (what === "any target" ? "any target" : `target ${what}`);

/** "Goblin · 1/1 · tapped": for candidates that share a name, the facts that differ between them, else their place in line. */
function notes(candidates: Candidate[], view: GameView): void {
  const byName = new Map<string, Candidate[]>();
  for (const c of candidates) byName.set(c.label, [...(byName.get(c.label) ?? []), c]);
  for (const same of byName.values()) {
    if (same.length < 2) continue;
    const facts = same.map((c) => factsOf(c, view));
    const keys = [...new Set(facts.flatMap((f) => Object.keys(f)))];
    const differing = keys.filter((k) => new Set(facts.map((f) => f[k] ?? "")).size > 1);
    same.forEach((c, i) => {
      const f = facts[i]!;
      const told = differing.map((k) => f[k]).filter((x): x is string => !!x);
      c.note = told.length ? told.join(" · ") : String(i + 1);
    });
    // still alike after the facts: number the alike ones
    const seen = new Map<string, Candidate[]>();
    for (const c of same) seen.set(c.note, [...(seen.get(c.note) ?? []), c]);
    for (const [note, group] of seen) {
      if (group.length < 2 || /^\d+$/.test(note)) continue;
      group.forEach((c, i) => { c.note = `${note} · ${i + 1}`; });
    }
  }
}

/** The facts a player can see about a candidate, keyed by kind (only the differing kinds are shown). */
export function factsOf(c: Candidate, view: GameView): Record<string, string> {
  if (c.kind === "player") return { seat: view.players.find((p) => p.id === c.ref)?.name ?? "" };
  const card = view.cards[c.ref];
  const out: Record<string, string> = {};
  if (!card) return out;
  if (c.where && c.where !== "battlefield") out.where = c.where === "stack" ? "on the stack" : `in ${c.where}`;
  const pt = ptOf(view, c.ref);
  if (pt) out.pt = pt;
  if (card.tapped) out.tapped = "tapped";
  if (card.damage) out.damage = `${card.damage} damage`;
  const counters = Object.entries(card.counters ?? {}).filter(([k]) => k !== "+1/+1" && k !== "-1/-1");
  if (counters.length) out.counters = counters.map(([k, n]) => `${n} ${k}`).join(", ");
  if (card.attacking || card.attacking_without_target) out.combat = "attacking";
  else if (card.blocking || card.blocking_without_attacker) out.combat = "blocking";
  if (isVisible(card) && card.commander_key) out.cmdr = "commander";
  if (isVisible(card) && card.copy_of) out.copy = "copy";
  if (card.face_down) out.fd = "face down";
  return out;
}

/** Its power/toughness as the rules see it now (counters and effects in), or as printed on a token. */
export function ptOf(view: GameView, id: string): string {
  const s = view.rules?.stats?.[id];
  if (s?.pt) return `${s.pt[0]}/${s.pt[1]}`;
  const card = view.cards[id];
  if (!card || !isVisible(card)) return "";
  const base = card.token && card.token.power != null && card.token.toughness != null ? [card.token.power, card.token.toughness] : basePt(view, id);
  if (!base) return "";
  const n = (card.counters?.["+1/+1"] ?? 0) - (card.counters?.["-1/-1"] ?? 0);
  const add = (v: string) => (/^-?\d+$/.test(v) ? String(Number(v) + n) : v);
  return `${add(String(base[0]))}/${add(String(base[1]))}`;
}

/** "1 of 2 chosen", "2 chosen" (any number), "Choose 2" (none or all two). */
export function progress(n: number, t: Pick<Targeting, "min" | "max" | "exactly">): string {
  // -- clearer targeting -- and what is still needed before Done ("1 of 3 chosen · 1 more needed")
  const need = (t.exactly ?? t.min) - n;
  const more = need > 0 ? ` · ${need} more needed` : "";
  if (t.exactly !== undefined) return `${n} of ${t.exactly} chosen${more}`;
  if (t.max >= 99) return `${n} chosen${more}`;
  return `${n} of ${t.max} chosen${more}`;
}

/** The next candidate along (wrapping), for Tab / arrow keys: from none, forward starts at the first and back at the last. */
export function step<T>(list: readonly T[], current: T | null, dir: 1 | -1): T | null {
  if (!list.length) return null;
  const i = current === null ? -1 : list.indexOf(current);
  if (i < 0) return dir > 0 ? list[0]! : list[list.length - 1]!;
  return list[(i + dir + list.length) % list.length]!;
}

/**
 * The candidates in tray order: each seat's together (the chooser's first, then around the table), players before cards.
 * Candidates nothing tells apart (six untapped 1/1 Goblin tokens) share a run, drawn as one fanned pile.
 */
export function traySeats(t: Targeting, view: GameView, me: string): { seat: string | null; runs: Candidate[][] }[] {
  const order = [me, ...view.seat_order.filter((p) => p !== me)];
  const groups = new Map<string | null, Candidate[]>();
  for (const c of t.candidates) groups.set(c.seat, [...(groups.get(c.seat) ?? []), c]);
  const rank = (p: string | null) => (p === null ? order.length : order.indexOf(p) < 0 ? order.length - 0.5 : order.indexOf(p));
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b))
    .map(([seat, cs]) => {
      const runs = new Map<string, Candidate[]>();
      for (const c of [...cs.filter((c) => c.kind === "player"), ...cs.filter((c) => c.kind === "card")]) {
        const key = c.kind === "card" && c.note ? `${c.label}|${JSON.stringify(factsOf(c, view))}` : c.ref;
        runs.set(key, [...(runs.get(key) ?? []), c]);
      }
      return { seat, runs: [...runs.values()] };
    });
}
