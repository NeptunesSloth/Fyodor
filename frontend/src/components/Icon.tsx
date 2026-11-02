/**
 * Fyodor's icon set: one drawn family (24px grid, 1.6 stroke, round joins, currentColor), so menus
 * and table markers never fall back to Unicode glyphs. Purely decorative unless given a `label`.
 */
const PATHS = {
  // two crossed blades: start a game, attacking
  swords: "M5 3l9.5 9.5M3 5l2-2M13 14l2 2-2 2-2-2M19 3l-9.5 9.5M21 5l-2-2M11 14l-2 2 2 2 2-2M7 18l-3 3M17 18l3 3",
  // a card turning back: resume
  resume: "M4 12a8 8 0 1 0 2.4-5.7M4 4v4.5h4.5M12 8v4l3 2",
  // a round table with four seats: the LAN lobby
  table: "M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zM12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5",
  // a fanned pair of cards: decks
  cards: "M8.5 3.5h9a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1zM5.5 6.5v13a1 1 0 0 0 1 1h9",
  // a crown: commanders, pod stats
  crown: "M3.5 8l4 4 4.5-6.5 4.5 6.5 4-4-1.5 10h-14zM5.5 20.5h13",
  // a cog: settings
  gear: "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM12 2.5l1.6 2.7 3.1-.6.6 3.1L20 9.3l-1.4 2.7 1.4 2.7-2.7 1.6-.6 3.1-3.1-.6L12 21.5l-1.6-2.7-3.1.6-.6-3.1L4 14.7l1.4-2.7L4 9.3l2.7-1.6.6-3.1 3.1.6z",
  // a mana gem
  gem: "M12 3l7 9-7 9-7-9zM5 12h14",
  close: "M6 6l12 12M18 6L6 18",
  plus: "M12 5v14M5 12h14",
  check: "M5 12.5l4.5 4.5L19 7.5",
  // chevrons and a grip: arranging seats in the lobby
  left: "M14.5 5.5L8 12l6.5 6.5",
  right: "M9.5 5.5L16 12l-6.5 6.5",
  grip: "M9 6.5h.01M15 6.5h.01M9 12h.01M15 12h.01M9 17.5h.01M15 17.5h.01",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, label, className }: { name: IconName; size?: number; label?: string; className?: string }) {
  return (
    <svg className={`icon ${className ?? ""}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <path d={PATHS[name]} />
    </svg>
  );
}
