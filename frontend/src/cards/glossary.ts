import { useSyncExternalStore } from "react";

/**
 * Keyword help: a short reminder for each keyword and ability word ("flying", "landfall", "kicker"), from the host's card
 * database (/api/cards/glossary, backend/app/cards/glossary.py). Fetched once, on the first card text drawn. Card text marks
 * them with a dotted underline (cards/ManaText.tsx) and the table's tooltip shows the reminder (cards/symbolTip.ts).
 */
type Terms = Readonly<Record<string, string>>;
let terms: Terms = {};
let asked = false;
const listeners = new Set<() => void>();

export function setGlossary(next: Terms): void {
  terms = next;
  cache.clear();
  for (const l of [...listeners]) l();
}

function load(): void {
  if (asked || typeof fetch === "undefined") return;
  asked = true;
  fetch("/api/cards/glossary")
    .then((r) => (r.ok ? r.json() : null))
    .then((b: { terms?: Record<string, string> } | null) => b?.terms && setGlossary(b.terms))
    .catch(() => { asked = false; });
}

const subscribe = (l: () => void) => {
  load();
  listeners.add(l);
  return () => void listeners.delete(l);
};
const snapshot = () => terms;

export function useGlossary(): Terms {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const cache = new Map<string, RegExp | null>();

/**
 * Where keywords are in a piece of text. With the card's own keyword list (`own`, the card record's), each of them anywhere
 * ("creatures with flying"); without one (an ability on the stack, a prompt) a term only where a keyword stands: the start
 * of the text or after a comma, a full stop or a dash ("Flying, ward {2}", "Landfall — …"), so a "fight" in a sentence is
 * left alone.
 */
export function keywordRegex(glossary: Terms, own?: readonly string[]): RegExp | null {
  const key = own ? own.join("|").toLowerCase() : "*";
  if (cache.has(key)) return cache.get(key)!;
  const words = (own ? own.map((k) => k.toLowerCase()) : Object.keys(glossary)).filter((k) => glossary[k]);
  words.sort((a, b) => b.length - a.length);
  const alt = words.map(escape).join("|");
  const re = !alt ? null : own ? new RegExp(`\\b(${alt})\\b`, "gi") : new RegExp(`(?:^|(?<=[,.;:—•]\\s*))(${alt})\\b`, "gi");
  cache.set(key, re);
  return re;
}

/** Text split into plain runs and keyword runs ({ kw: reminder }). */
export function splitKeywords(text: string, glossary: Terms, own?: readonly string[]): (string | { word: string; tip: string })[] {
  const re = keywordRegex(glossary, own);
  if (!re) return [text];
  const out: (string | { word: string; tip: string })[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    const i = m.index ?? 0;
    if (i > last) out.push(text.slice(last, i));
    out.push({ word: m[0], tip: glossary[m[0].toLowerCase()]! });
    last = i + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
