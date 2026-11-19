/**
 * -- mulligan helper -- my opening hand at a glance: how many lands, a mini curve of the rest (mana value 0–6, 7+), and whether the
 * lands in hand make each colour the spells ask for ("G ✓ R ✗"). Reads only the printed data of cards I hold.
 */
export interface CheckCard { type_line?: string | null; cmc?: number | null; mana_cost?: string | null; oracle_text?: string | null }
export interface OpeningCheck { lands: number; curve: number[]; colors: { color: string; ok: boolean }[] }

const BASIC: Record<string, string> = { Plains: "W", Island: "U", Swamp: "B", Mountain: "R", Forest: "G" };
const WUBRG = ["W", "U", "B", "R", "G"];

/** The colours a land makes: its basic land types, and the {W}…{G} its "Add …" text names ("any color": all five). */
export function landColors(c: CheckCard): string[] {
  const out = new Set<string>();
  const type = (c.type_line ?? "").split("//")[0]!;
  for (const [sub, m] of Object.entries(BASIC)) if (new RegExp(`\\b${sub}\\b`).test(type)) out.add(m);
  for (const add of (c.oracle_text ?? "").match(/Add [^.]*/g) ?? []) {
    if (/any colou?r/i.test(add)) WUBRG.forEach((m) => out.add(m));
    for (const m of add.matchAll(/\{([WUBRG])\}/g)) out.add(m[1]!);
  }
  return [...out];
}

export function openingCheck(cards: CheckCard[]): OpeningCheck {
  const isLand = (c: CheckCard) => /\bLand\b/.test((c.type_line ?? "").split("//")[0]!);
  const lands = cards.filter(isLand);
  const spells = cards.filter((c) => !isLand(c));
  const curve = [0, 0, 0, 0, 0, 0, 0, 0];
  for (const c of spells) curve[Math.min(7, Math.max(0, Math.floor(c.cmc ?? 0)))]!++;
  const have = new Set(lands.flatMap(landColors));
  const need = new Set(spells.flatMap((c) => [...(c.mana_cost ?? "").matchAll(/\{([WUBRG])\}/g)].map((m) => m[1]!)));
  return { lands: lands.length, curve, colors: WUBRG.filter((m) => need.has(m)).map((color) => ({ color, ok: have.has(color) })) };
}
