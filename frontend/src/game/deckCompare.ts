/*
 * DECK LAB · Compare (docs/ELIMINATION_HUB.md, Deck Lab: "compare changes"): what the next-game version changes against the
 * deck brought to this game. Cards are matched by name within their section (a new printing of the same card is not a
 * change), so the comparison reads like a pod would say it: "+1 Swords to Plowshares, −1 Opt". Pure, local to the browser.
 */
import type { Section } from "../types/decks";

export interface DeckLine {
  section: Section;
  name: string;
  quantity: number;
}

export interface DeckChange {
  section: Section;
  name: string;
  /** How many more (added) or fewer (removed) copies, always positive. */
  n: number;
}

export interface DeckComparison {
  added: DeckChange[];
  removed: DeckChange[];
  /** Commander + deck cards, before and after (a Commander deck is 100). */
  before: number;
  after: number;
}

// the deck text headers Fyodor's importer reads (backend app/decks/parser.py _HEADER_ALIASES), by section
const HEADERS: Record<string, Section> = {
  commander: "commander", commanders: "commander", "command zone": "commander", companion: "companion", companions: "companion",
  deck: "main", main: "main", maindeck: "main", "main deck": "main", mainboard: "main", creatures: "main", creature: "main",
  lands: "main", land: "main", spells: "main", instants: "main", sorceries: "main", artifacts: "main", enchantments: "main",
  planeswalkers: "main", battles: "main", other: "main", sideboard: "sideboard", side: "sideboard", sb: "sideboard",
  maybeboard: "maybeboard", maybe: "maybeboard", considering: "maybeboard", tokens: "tokens", token: "tokens",
  stickers: "stickers", "sticker sheets": "stickers", "sticker sheet": "stickers", attractions: "attractions", "attraction deck": "attractions",
};
const ORDER: Section[] = ["commander", "companion", "main", "sideboard", "maybeboard", "tokens", "attractions", "stickers"];
const QTY = /^(\d{1,4})\s*[xX]?\s+(.+)$/;
const QTY_SUFFIX = /^(.+?)\s+[xX](\d{1,4})$/;

function header(line: string): Section | null {
  const text = line.replace(/^[/#\s]+/, "").replace(/\s*\(\d+\)\s*$/, "").replace(/:$/, "").trim().toLowerCase();
  return HEADERS[text] ?? null;
}

/** A deck list in Fyodor's text format ("Commander" / "Deck" / "Sideboard" headers, "1 Name (SET) 123" lines) as lines. */
export function deckLines(text: string): DeckLine[] {
  const out: DeckLine[] = [];
  let section: Section = "main";
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const h = header(line);
    if (h) {
      section = h;
      continue;
    }
    if (line.startsWith("//") || line.startsWith("#")) continue;
    let rest = line;
    let quantity = 1;
    const m = QTY.exec(line) ?? null;
    const s = m ? null : QTY_SUFFIX.exec(line);
    if (m) [quantity, rest] = [Number(m[1]), m[2]!];
    else if (s) [rest, quantity] = [s[1]!, Number(s[2])];
    const name = rest
      .replace(/\s+\{[^}]*\}/g, "") // category flags
      .replace(/\s+\*[A-Za-z]+\*/g, "") // *F* foil markers
      .replace(/\s+[([][A-Za-z0-9]{2,6}[)\]](\s+\S+)?\s*$/, "") // (SET) 123
      .trim();
    if (name && quantity > 0) out.push({ section, name, quantity });
  }
  return out;
}

const keyOf = (l: Pick<DeckLine, "section" | "name">) => `${l.section}|${l.name.toLowerCase()}`;

function tally(lines: DeckLine[]): Map<string, DeckLine> {
  const out = new Map<string, DeckLine>();
  for (const l of lines) {
    const k = keyOf(l);
    const had = out.get(k);
    out.set(k, { ...l, quantity: (had?.quantity ?? 0) + l.quantity });
  }
  return out;
}

const deckSize = (lines: DeckLine[]) => lines.reduce((n, l) => n + (l.section === "commander" || l.section === "main" ? l.quantity : 0), 0);

/** What ``after`` adds to and takes out of ``before``, by section then name. */
export function compareDecks(before: DeckLine[], after: DeckLine[]): DeckComparison {
  const was = tally(before);
  const now = tally(after);
  const added: DeckChange[] = [];
  const removed: DeckChange[] = [];
  for (const [k, l] of now) {
    const d = l.quantity - (was.get(k)?.quantity ?? 0);
    if (d > 0) added.push({ section: l.section, name: l.name, n: d });
  }
  for (const [k, l] of was) {
    const d = l.quantity - (now.get(k)?.quantity ?? 0);
    if (d > 0) removed.push({ section: l.section, name: now.get(k)?.name ?? l.name, n: d });
  }
  const sort = (a: DeckChange, b: DeckChange) => ORDER.indexOf(a.section) - ORDER.indexOf(b.section) || a.name.localeCompare(b.name);
  return { added: added.sort(sort), removed: removed.sort(sort), before: deckSize(before), after: deckSize(after) };
}
