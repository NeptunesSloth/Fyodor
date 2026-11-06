/** A long list of plain options (a creature type out of ~300) gets a type-to-filter box above this many. */
export const FILTER_MIN = 12;

/** Options whose label contains the typed text, case-insensitively; blank text keeps them all. */
export function filterOptions<T extends { label: string }>(options: T[], text: string): T[] {
  const q = text.trim().toLowerCase();
  return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
}
