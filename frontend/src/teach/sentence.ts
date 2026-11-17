/**
 * -- Teach Fyodor -- reading a script back as the Oracle sentences the engine will read. A faithful port of
 * app/rules/taught.py (render, ability_text, compile_entry): backend/tests/fixtures/teach_sentences.json holds every piece's
 * sentences from the backend, and sentence.test.ts checks this file says exactly the same words.
 */

import type { Ability, Block, Entry, Piece, Value, Vocabulary } from "./types";

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
  "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
const TOKEN = /\{(self|[a-z]+)(?::([a-z]+))?\}/g;

export interface Voice { n?: number | null; me?: string }

/** How an ability names its own object ("this creature"), from the card's type line. */
export function selfWord(typeLine: string | null | undefined): string {
  for (const t of ["Creature", "Land", "Artifact", "Enchantment", "Planeswalker", "Battle"]) {
    if (new RegExp(`\\b${t}\\b`).test(typeLine ?? "")) return `this ${t.toLowerCase()}`;
  }
  if (/\b(Instant|Sorcery)\b/.test(typeLine ?? "")) return "this spell";
  return "this permanent";
}

function number(value: Value, n: number | null): number | null {
  if (value === "N") return n;
  if (value === "-N") return n === null ? null : -n;
  return typeof value === "number" ? value : parseInt(value, 10);
}

const word = (v: number) => (v >= 0 && v < WORDS.length ? WORDS[v]! : String(v));

/** One piece's words. */
export function render(template: string, values: Record<string, Value>, voc: Vocabulary, voice: Voice = {}): string {
  const n = voice.n ?? null;
  const me = voice.me ?? "this creature";
  return template.replace(TOKEN, (whole, key: string, form: string | undefined) => {
    if (key === "self") return me;
    if (!(key in values)) return whole;
    const raw = values[key]!;
    if (typeof raw === "string" && raw in voc.options) {
      const opt = voc.options[raw]!;
      if (form === "vs") return opt.plural ? "" : "s";
      return opt.text.replace("{self}", me);
    }
    if (typeof raw === "string" && raw.startsWith("{")) return raw.replace("{N}", n === null ? "{N}" : `{${n}}`);
    const v = number(raw, n);
    const unbound = v === null;
    const sign = raw === "-N" ? "-" : "+";
    if (form === "word") return unbound ? "N" : word(v);
    if (form === "a") return unbound ? "N" : v === 1 ? "a" : word(v);
    if (form === "s") return unbound || v !== 1 ? "s" : "";
    if (form === "signed") return unbound ? `${sign}N` : v >= 0 ? `+${v}` : String(v);
    if (form === "mana") return unbound ? "{N}" : `{${v}}`;
    return unbound ? "N" : String(v);
  });
}

const cap = (s: string) => s.slice(0, 1).toUpperCase() + s.slice(1);
const may = (text: string) => "you may " + (text.startsWith("you ") ? text.slice(4) : text);

function pieceOf(voc: Vocabulary, id: string): Piece {
  const p = voc.pieces.find((x) => x.id === id);
  if (!p) throw new Error(`unknown piece ${id}`);
  return p;
}

const pieceText = (b: Block, voc: Vocabulary, voice: Voice) => render(pieceOf(voc, b.id).text, b.values ?? {}, voc, voice);

function sentences(stmts: Block[], voc: Vocabulary, voice: Voice): string[] {
  const out: string[] = [];
  let join = false;
  for (const st of stmts) {
    const role = pieceOf(voc, st.id).role;
    if (role === "then") {
      join = true;
      continue;
    }
    let s: string;
    if (role === "effect") s = pieceText(st, voc, voice);
    else if (role === "may") s = may(pieceText(st.body![0]!, voc, voice));
    else if (role === "ifdo") s = "if you do, " + sentences(st.body ?? [], voc, voice).join(", then ");
    else if (role === "optional_cost") {
      out.push(pieceText(st, voc, voice));
      s = "if you do, " + sentences(st.body ?? [], voc, voice).join(", then ");
      join = false;
    } else continue;
    if (join && out.length) out[out.length - 1] += ", then " + s;
    else out.push(s);
    join = false;
  }
  return out;
}

/** One ability as an Oracle sentence ("When this creature enters, mill two cards. …"). */
export function abilityText(ability: Ability, voc: Vocabulary, voice: Voice = {}): string {
  const hat = pieceOf(voc, ability.hat.id);
  const body = [...(ability.body ?? [])];
  const cond = body.length && pieceOf(voc, body[0]!.id).role === "condition" ? body.shift()! : null;
  if (hat.role === "static_hat") {
    const stat = body.find((b) => pieceOf(voc, b.id).role === "static");
    if (stat && !cond && pieceOf(voc, stat.id).bare) return cap(render(pieceOf(voc, stat.id).bare!, stat.values ?? {}, voc, voice));
    const words = stat ? pieceText(stat, voc, voice) : "…";
    return cap(cond ? `as long as ${pieceText(cond, voc, voice)}, ${words}` : words) + ".";
  }
  if (hat.role === "activated") {
    const costs = body.filter((b) => pieceOf(voc, b.id).role === "cost").map((b) => pieceText(b, voc, voice));
    const limits = body.filter((b) => pieceOf(voc, b.id).role === "limit").map((b) => pieceText(b, voc, voice));
    const rest = body.filter((b) => !["cost", "limit"].includes(pieceOf(voc, b.id).role));
    const said = sentences(rest, voc, voice).map((s) => cap(s) + ".").join(" ") || "…";
    return [`${costs.map(cap).join(", ") || "…"}: ${said}`, ...limits].join(" ");
  }
  let head = pieceText(ability.hat, voc, voice);
  if (cond) head += `, if ${pieceText(cond, voc, voice)}`;
  const said = sentences(body, voc, voice);
  if (!said.length) return head + ", …";
  return `${head}, ${said[0]}.` + said.slice(1).map((s) => ` ${cap(s)}.`).join("");
}

/** The Oracle lines that stand for a taught keyword (with its number ``n``) or card line. */
export function compileEntry(entry: Pick<Entry, "abilities">, voc: Vocabulary, voice: Voice = {}): string[] {
  return entry.abilities.map((a) => abilityText(a, voc, voice));
}

/** The keyword line as it would be printed ("Dive 2 (When this creature enters, …)") */
export function keywordLine(name: string, param: boolean, lines: string[], n = 2): string {
  const head = param ? `${name} ${n}` : name;
  return lines.length ? `${head} (${lines.join(" ")})` : head;
}
