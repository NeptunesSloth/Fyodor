/**
 * TOKEN MATH: the numbers behind Scute Swarm, landfall and token-doubler turns, worked out before you play the land.
 * Read-only: nothing here is sent to the server; it reads the public board you can already see.
 *
 * Rules used (Comprehensive Rules effective 2026-09-25):
 * - 603.2c: an ability triggers once for each time its trigger event occurs, so a land entering is one landfall
 *   event per land; Scapeshift or Lumra putting 12 lands in at once triggers each Scute Swarm 12 times.
 * - 603.2d: "triggers an additional time" (Ancient Greenwarden, Traveling Chocobo, Yarok) adds one trigger per
 *   effect, so two of them make three triggers.
 * - 603.4 / 608.2b: Scute Swarm's "if you control six or more lands" is checked as each trigger resolves, so
 *   lands that entered with it count.
 * - 603.6a, 603.10: a permanent that wasn't on the battlefield when the land entered doesn't trigger, so copies
 *   made by those triggers start triggering at the next land.
 * - 616.1: each token doubler applies once to a creation, in the order the creating player chooses; doublers multiply,
 *   and an "additional tokens" effect such as Chatterfang's is best applied first, so the doublers double those too.
 */
import type { CardData } from "../types/cards";
import { isVisible, type GameView, type VisibleCard } from "../types/game";

/** A token doubler ("twice that many", "three times that many"). */
export interface TokenFactor {
  name: string;
  factor: number;
  /** Only creature tokens (Ojer Taq). */
  creatureOnly: boolean;
}

/** A permanent with a landfall ability the calculator counts. */
export interface LandfallMaker {
  name: string;
  /** How many of it you control (a token stack counts each token). */
  count: number;
  kind: "tokens" | "mana" | "plant_counters" | "double_power" | "other";
  /** Tokens per trigger (kind "tokens"). */
  amount: number;
  creature: boolean;
  /** What it makes, for the table: "4/4 Beast", "Food or Treasure", "Insect". */
  label: string;
  /** Field of the Dead: needs seven or more lands with different names (checked by the caller). */
  needsSevenNames?: boolean;
  /** "you may": counted as if you say yes. */
  optional?: boolean;
}

export interface Board {
  lands: number;
  /** Lands you control with different names (Field of the Dead). */
  landNames: number;
  swarms: number;
  /** Times each landfall ability triggers per land (1 + the "additional time" effects). */
  triggers: number;
  triggerSources: string[];
  factors: TokenFactor[];
  /** Chatterfang-style "those tokens plus that many Squirrels" effects. */
  extras: string[];
  makers: LandfallMaker[];
  /** Plants you control (Avenger of Zendikar's counters). */
  plants: number;
  /** Ashaya: your nontoken creatures are lands too. */
  creaturesAreLands: boolean;
  copiers: SelfCopier[];
}

export const emptyBoard = (): Board => ({
  lands: 0, landNames: 0, swarms: 0, triggers: 1, triggerSources: [], factors: [], extras: [], makers: [], plants: 0, creaturesAreLands: false, copiers: [],
});

const NUMBER_WORDS: Record<string, number> = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
const TIMES: Record<string, number> = { twice: 2, "three times": 3, "four times": 4 };

/** The sentences of a rules text, lower-cased, reminder text removed. */
export function sentences(text: string): string[] {
  return text
    .replace(/\([^)]*\)/g, "")
    .toLowerCase()
    .split(/\n|(?<=\.)\s+/)
    .map((s) => s.replace(/^[a-z ]+—\s*/, "").trim()) // "Landfall — Whenever…" → "whenever…"
    .filter(Boolean);
}

/** A token doubler in this text, or null. `mine`: the permanent is yours (an "under your control" doubler counts only then). */
export function tokenFactor(name: string, text: string, mine: boolean): TokenFactor | null {
  for (const s of sentences(text)) {
    const m = /^if (?:an effect would create one or more (creature )?tokens( under your control)?, it creates|one or more (creature )?tokens would be created( under your control)?,) (twice|three times|four times) that many (?:of those )?tokens/.exec(s);
    if (!m) continue;
    const yours = !!(m[2] || m[4]);
    if (yours && !mine) return null;
    return { name, factor: TIMES[m[5]!]!, creatureOnly: !!(m[1] || m[3]) };
  }
  return null;
}

/** "That ability triggers an additional time" for a land entering (Ancient Greenwarden, Traveling Chocobo, Yarok). */
export function landTriggerDoubler(text: string): boolean {
  return sentences(text).some((s) => {
    const m = /^if an? ([a-z ]+?) entering(?: the battlefield)? causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time/.exec(s);
    return !!m && /\b(land|permanent)\b/.test(m[1]!);
  });
}

/** Chatterfang: "those tokens plus that many … tokens are created instead". */
export const extraTokens = (text: string): boolean =>
  sentences(text).some((s) => /^if one or more tokens would be created under your control, those tokens plus that many .* tokens are created instead/.test(s));

const isScute = (name: string) => name.toLowerCase() === "scute swarm";

/** The landfall ability of a permanent (not Scute Swarm, which the calculator models itself), or null. */
export function landfallMaker(name: string, text: string, count = 1): LandfallMaker | null {
  if (isScute(name)) return null;
  const line = sentences(text).join(" ");
  const at = line.search(/whenever (?:a land you control enters|this land or another land you control enters)/);
  if (at < 0) return null;
  const body = line.slice(at).split(/whenever (?!a land you control enters|this land or another land you control enters)/)[0]!;
  const base = { name, count, amount: 0, creature: false, label: "", optional: /\byou may\b/.test(body.split(".")[0] ?? "") };
  // every "create …" clause; a copy clause is a choice we don't count (Springheart Nantuko: count its Insect)
  const creates = [...body.matchAll(/create ([a-z]+) ([^.]*?)tokens?\b(?: or an? ([^.]*?)token\b)?/g)].filter((c) => !/copy/.test(c[2]!));
  if (creates.length) {
    const [, word, what, alt] = creates[creates.length - 1]!;
    const amount = NUMBER_WORDS[word!] ?? 0;
    if (amount) {
      const clean = (x: string) => x.replace(/\b(creature|token|green|black|white|blue|red|colorless)\b/g, "").replace(/\s+/g, " ").trim();
      const label = alt ? `${clean(what!)} or ${clean(alt)}` : clean(what!);
      return {
        ...base,
        kind: "tokens",
        amount,
        creature: /\bcreature\b/.test(what!),
        label: label.replace(/(^|\s)([a-z])/g, (_, sp: string, c: string) => sp + c.toUpperCase()).replace(" Or ", " or "),
        needsSevenNames: /seven or more lands with different names/.test(body),
        optional: false,
      };
    }
  }
  if (/\badd (?:one|1) mana\b|\badd \{/.test(body)) return { ...base, kind: "mana", amount: 1, label: "mana" };
  if (/put a \+1\/\+1 counter on each plant/.test(body)) return { ...base, kind: "plant_counters", amount: 1, label: "+1/+1 on each Plant" };
  if (/double [a-z ,'’]*power/.test(body)) return { ...base, kind: "double_power", amount: 1, label: "power doubled" };
  return { ...base, kind: "other", amount: 0, label: "other" };
}

/** The product of the doublers that apply to a creation of creature (or other) tokens. */
export function factorFor(factors: TokenFactor[], creature: boolean): number {
  return factors.reduce((p, f) => (f.creatureOnly && !creature ? p : p * f.factor), 1);
}

/**
 * One creation of `n` tokens with every replacement applied (616.1): the tokens and the extra ones
 * (Chatterfang's Squirrels, applied first so the doublers double them too).
 */
export function createTokens(n: number, creature: boolean, factors: TokenFactor[], extras = 0): { tokens: number; extra: number } {
  let extra = 0;
  for (let i = 0; i < extras; i++) extra += n + extra;
  return { tokens: n * factorFor(factors, creature), extra: extra * factorFor(factors, true) };
}

/** "Create N tokens" (or N token copies of a creature) with your doublers: how many you get. */
export const createCount = (n: number, factors: TokenFactor[], creature = true): number => createTokens(n, creature, factors).tokens;

/** One row of a projection: the board after lands entered (one land, or several at once). */
export interface Step {
  /** Lands that entered in this step. */
  entered: number;
  lands: number;
  /** Landfall triggers that went on the stack. */
  triggers: number;
  swarms: number;
  /** Scute Swarm copies made in this step. */
  newSwarms: number;
  /** Insects made in this step (Scute Swarm below six lands). */
  insects: number;
  /** Other tokens made in this step, by label. */
  tokens: Record<string, number>;
  /** Chatterfang-style extra tokens made in this step. */
  extra: number;
  mana: number;
  /** +1/+1 counters put on each Plant. */
  plantCounters: number;
  /** Times a "double its power" landfall doubled. */
  doublings: number;
}

export interface Plan {
  lands: number;
  /** All at once (Scapeshift, Lumra, Splendid Reclamation) or one land at a time. */
  together: boolean;
  /** Makers left out by the player (by name). */
  skip?: string[];
}

/** The steps of a plan: one per land, or one for all of them at once. */
export function project(board: Board, plan: Plan): Step[] {
  const steps: Step[] = [];
  const t = Math.max(1, board.triggers);
  const extras = board.extras.length;
  let lands = board.lands;
  let swarms = board.swarms;
  const batches = plan.together ? [plan.lands] : Array.from({ length: Math.max(0, plan.lands) }, () => 1);
  for (const k of batches) {
    if (k <= 0) continue;
    lands += k;
    const step: Step = { entered: k, lands, triggers: 0, swarms, newSwarms: 0, insects: 0, tokens: {}, extra: 0, mana: 0, plantCounters: 0, doublings: 0 };
    // Scute Swarm: the swarms on the battlefield as the lands entered each trigger k × t times
    const swarmTriggers = swarms * k * t;
    step.triggers += swarmTriggers;
    const made = createTokens(swarmTriggers, true, board.factors, extras);
    if (lands >= 6) step.newSwarms = made.tokens;
    else step.insects = made.tokens;
    step.extra += made.extra;
    for (const m of board.makers) {
      if (plan.skip?.includes(m.name)) continue;
      if (m.needsSevenNames && board.landNames < 7) continue;
      const n = m.count * k * t;
      step.triggers += n;
      if (m.kind === "tokens") {
        const r = createTokens(n * m.amount, m.creature, board.factors, extras);
        step.tokens[m.label] = (step.tokens[m.label] ?? 0) + r.tokens;
        step.extra += r.extra;
      } else if (m.kind === "mana") step.mana += n;
      else if (m.kind === "plant_counters") step.plantCounters += n; // each trigger puts one on each Plant
      else if (m.kind === "double_power") step.doublings += n;
    }
    swarms += step.newSwarms;
    step.swarms = swarms;
    steps.push(step);
  }
  return steps;
}

/** Totals of a projection. */
export function totals(steps: Step[]): { triggers: number; newSwarms: number; insects: number; tokens: Record<string, number>; extra: number; mana: number } {
  const out = { triggers: 0, newSwarms: 0, insects: 0, tokens: {} as Record<string, number>, extra: 0, mana: 0 };
  for (const s of steps) {
    out.triggers += s.triggers;
    out.newSwarms += s.newSwarms;
    out.insects += s.insects;
    out.extra += s.extra;
    out.mana += s.mana;
    for (const [k, v] of Object.entries(s.tokens)) out.tokens[k] = (out.tokens[k] ?? 0) + v;
  }
  return out;
}

/** Lands to play one at a time until you control at least `target` Scute Swarms (null: never, or more than `max`). */
export function landsUntil(board: Board, target: number, max = 200): number | null {
  if (board.swarms >= target) return 0;
  if (board.swarms <= 0) return null;
  let b = board;
  for (let n = 1; n <= max; n++) {
    const [s] = project(b, { lands: 1, together: false });
    if (!s) return null;
    if (s.swarms >= target) return n;
    b = { ...b, lands: s.lands, swarms: s.swarms };
  }
  return null;
}

/** "1,234", "1.23e+21", "∞". */
export function fmt(n: number): string {
  if (!Number.isFinite(n)) return "∞";
  return n < 1e15 ? Math.round(n).toLocaleString("en-US") : n.toExponential(2);
}

// --- reading the board -------------------------------------------------------------------------------------------

type Lookup = (cardId: string) => CardData | undefined;

/** A visible permanent's current rules text and type line (its face, or the token's own). */
export function textOf(c: VisibleCard, lookup: Lookup): { text: string; type: string } {
  if (c.is_token && c.token && !c.token.card_id) return { text: c.token.text ?? "", type: c.token.type_line ?? "" };
  const data = lookup(c.card_id ?? c.token?.card_id ?? "");
  if (!data) return { text: c.token?.text ?? "", type: c.token?.type_line ?? "" };
  const face = data.faces?.[c.face] ?? (data.oracle_text == null ? data.faces?.[0] : undefined);
  return { text: face?.oracle_text ?? data.oracle_text ?? "", type: face?.type_line ?? data.type_line ?? "" };
}

const qty = (c: VisibleCard) => Math.max(1, c.quantity ?? 1);

/** What the calculator needs from `player`'s battlefield (public information only). */
export function readBoard(view: GameView, player: string, lookup: Lookup): Board {
  const board = emptyBoard();
  const names = new Set<string>();
  const perms: { c: VisibleCard; text: string; type: string }[] = [];
  for (const [zone, ids] of Object.entries(view.zones)) {
    if (!zone.endsWith(":battlefield") || !Array.isArray(ids)) continue;
    for (const id of ids) {
      const c = view.cards[id];
      if (!c || !isVisible(c)) continue;
      perms.push({ c, ...textOf(c, lookup) });
    }
  }
  for (const { c, text } of perms) {
    const mine = c.controller === player;
    const f = tokenFactor(c.name, text, mine);
    if (f) for (let i = 0; i < qty(c); i++) board.factors.push(f);
    if (!mine) continue;
    if (landTriggerDoubler(text)) for (let i = 0; i < qty(c); i++) { board.triggers += 1; board.triggerSources.push(c.name); }
    if (extraTokens(text)) for (let i = 0; i < qty(c); i++) board.extras.push(c.name);
    if (/^ashaya\b/i.test(c.name) || /nontoken creatures you control are forest lands/i.test(text)) board.creaturesAreLands = true;
  }
  const makers = new Map<string, LandfallMaker>();
  const copiers = new Map<string, SelfCopier>();
  for (const { c, text, type } of perms) {
    if (c.controller !== player) continue;
    const creature = /\bcreature\b/i.test(type) || !!view.rules?.stats?.[c.id]?.creature;
    const land = /\bland\b/i.test(type) || (board.creaturesAreLands && creature && !c.is_token);
    if (land) {
      board.lands += qty(c);
      names.add(c.name);
    }
    if (isScute(c.name) || isScute(c.copy_of?.source_name ?? "")) board.swarms += qty(c);
    if (/\bplant\b/i.test(type) && creature) board.plants += qty(c);
    const m = landfallMaker(c.name, text, qty(c));
    if (m) {
      const had = makers.get(c.name);
      makers.set(c.name, had ? { ...had, count: had.count + m.count } : m);
    }
    const sc = selfCopier(c.name, text, qty(c));
    if (sc) {
      const had = copiers.get(c.name);
      copiers.set(c.name, had ? { ...had, count: had.count + sc.count } : sc);
    }
  }
  board.copiers = [...copiers.values()];
  board.landNames = names.size;
  board.makers = [...makers.values()];
  return board;
}

/** Your tokens on the battlefield, by name: how many, and their total power (derived when the engine gives it). */
export function tokenCensus(view: GameView, player: string): { name: string; count: number; power: number; untapped: number }[] {
  const by = new Map<string, { name: string; count: number; power: number; untapped: number }>();
  for (const [zone, ids] of Object.entries(view.zones)) {
    if (!zone.endsWith(":battlefield") || !Array.isArray(ids)) continue;
    for (const id of ids) {
      const c = view.cards[id];
      if (!c || !isVisible(c) || !c.is_token || c.controller !== player) continue;
      const n = qty(c);
      const pt = view.rules?.stats?.[id]?.pt;
      const p = pt ? pt[0] : Number(c.token?.power ?? 0) || 0;
      const row = by.get(c.name) ?? { name: c.name, count: 0, power: 0, untapped: 0 };
      row.count += n;
      row.power += Math.max(0, p) * n;
      if (!c.tapped) row.untapped += n;
      by.set(c.name, row);
    }
  }
  return [...by.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/** A permanent that makes token copies of itself (Biowaste Blob, Council of Reeds, Giant Adephage): each copy has the
 * same ability, so the count grows each time they trigger. Scute Swarm is the landfall calculator's. */
export interface SelfCopier {
  name: string;
  count: number;
  /** When it triggers, in its own words ("at the beginning of your upkeep"). */
  when: string;
}

export function selfCopier(name: string, text: string, count = 1): SelfCopier | null {
  if (isScute(name)) return null;
  const n = name.toLowerCase();
  for (const s of sentences(text)) {
    const m = /^(at the beginning of [^,]+|whenever [^,]+),(?: if [^,]+,)? create a token that's a copy of (this creature|this permanent|this artifact|this enchantment|[^,.]+?)(?:,|\.|$)/.exec(s);
    if (m && (m[2]!.startsWith("this ") || m[2] === n || m[2] === n.split(",")[0])) return { name, count, when: m[1]! };
  }
  return null;
}

/** How many there are after the self-copiers trigger `rounds` times (each one on the battlefield triggers once a round). */
export function selfCopyGrowth(count: number, factor: number, rounds: number): number[] {
  const out: number[] = [];
  let n = count;
  for (let i = 0; i < rounds; i++) {
    n += n * factor;
    out.push(n);
  }
  return out;
}

/** Your creatures on the battlefield (a stack counts each token): how many, and their total power. */
export function creatureCensus(view: GameView, player: string, lookup: Lookup): { count: number; power: number; untapped: number; untappedPower: number } {
  const out = { count: 0, power: 0, untapped: 0, untappedPower: 0 };
  for (const [zone, ids] of Object.entries(view.zones)) {
    if (!zone.endsWith(":battlefield") || !Array.isArray(ids)) continue;
    for (const id of ids) {
      const c = view.cards[id];
      if (!c || !isVisible(c) || c.controller !== player) continue;
      const stats = view.rules?.stats?.[id];
      const { type } = textOf(c, lookup);
      if (!(stats?.creature ?? /\bcreature\b/i.test(type))) continue;
      const n = qty(c);
      const p = Math.max(0, stats?.pt ? stats.pt[0] : Number(c.token?.power ?? lookup(c.card_id ?? "")?.power ?? 0) || 0);
      out.count += n;
      out.power += p * n;
      if (!c.tapped) {
        out.untapped += n;
        out.untappedPower += p * n;
      }
    }
  }
  return out;
}

/** With automation on, the engine keeps each token copy (Scute Swarm) as its own object and resolves each trigger
 * one by one; past these it gets slow (docs/CURRENT_STATE.md "Big boards", docs/TOKEN_STACKS.md). */
export const SLOW_TRIGGERS = 100;
export const SLOW_OBJECTS = 256;
