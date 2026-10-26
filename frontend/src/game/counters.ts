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
