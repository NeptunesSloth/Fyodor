/**
 * Names for counters and keyword abilities, shared by the 2D chips and the 3D card badges.
 * Keyword counters are the 122.1b set the server recognises (rules_state.KEYWORD_COUNTERS).
 */
export const KEYWORDS = [
  "flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink",
  "menace", "reach", "shadow", "trample", "vigilance", "exalted", "decayed",
] as const;

const KEYWORD_SET = new Set<string>(KEYWORDS);

export function isKeyword(kind: string): boolean {
  return KEYWORD_SET.has(kind.toLowerCase());
}

/** A keyword's coin on a card tile: distinct codes ("De" was both deathtouch and defender). */
const CODE: Record<string, string> = {
  flying: "FLY", "first strike": "1ST", "double strike": "2X", deathtouch: "DTH", haste: "HST", hexproof: "HEX", indestructible: "IND",
  lifelink: "LL", menace: "MEN", reach: "RCH", shadow: "SHD", trample: "TRM", vigilance: "VIG", exalted: "EXL", decayed: "DCY",
  defender: "DEF", flash: "FSH", ward: "WRD", protection: "PRO", shroud: "SHR", infect: "INF", wither: "WTH", prowess: "PRW",
};
export const keywordCode = (kind: string): string => CODE[kind.toLowerCase()] ?? kind.slice(0, 3).toUpperCase();

/** Every keyword a permanent has now: its keyword counters and what effects gave it, less what they took away (Title Case). */
export function keywordsNow(counters: Record<string, number> | undefined, gained: string[] = [], lost: string[] = []): string[] {
  const out = new Set<string>();
  for (const [k, n] of Object.entries(counters ?? {})) if (n > 0 && isKeyword(k)) out.add(k.toLowerCase());
  for (const k of gained) out.add(k.toLowerCase());
  for (const k of lost) out.delete(k.toLowerCase());
  return [...out].map((k) => k.replace(/^./, (c) => c.toUpperCase()));
}

const SHORT: Record<string, string> = {
  "first strike": "1st strike",
  "double strike": "2× strike",
  indestructible: "indestr.",
  "+1/+1": "+1/+1",
  "-1/-1": "−1/−1",
};

/** A compact chip label that never cuts a word in half ("first st" → "1st strike"). */
export function counterShort(kind: string): string {
  return SHORT[kind.toLowerCase()] ?? (kind.length > 9 ? `${kind.slice(0, 8)}.` : kind);
}

/** Full sentence-case name for tooltips and the card preview. */
export function counterName(kind: string, n: number): string {
  return `${n} ${kind} counter${n === 1 ? "" : "s"}`;
}
