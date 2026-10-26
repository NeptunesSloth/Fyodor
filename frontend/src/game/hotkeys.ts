/**
 * The single table of keyboard shortcuts. Every binding is declared here once, so the help
 * screen lists them and a unit test guarantees that no two actions share a key.
 * A key string is `[ctrl+][shift+]key` with `key` = KeyboardEvent.key lower-cased
 * ("ctrl" also matches ⌘ on macOS).
 */
export type HotkeyId =
  | "undo"
  | "redo"
  | "tap"
  | "draw"
  | "next_step"
  | "next_turn"
  | "untap_all"
  | "turn_over"
  | "to_graveyard"
  | "cancel"
  | "help"
  | "respond"
  | "pass"
  | "auto_pass"
  | "hud"
  | "cam_seat"
  | "cam_player"
  | "cam_table"
  | "cam_focus"
  | "cam_reset"
  | "cam_names";

export interface Hotkey {
  id: HotkeyId;
  keys: string[];
  label: string;
}

export const HOTKEYS: Hotkey[] = [
  { id: "undo", keys: ["ctrl+z"], label: "Undo" },
  { id: "redo", keys: ["ctrl+shift+z", "ctrl+y"], label: "Redo" },
  { id: "tap", keys: ["t", " "], label: "Tap / untap selected or hovered" },
  { id: "draw", keys: ["d"], label: "Draw a card" },
  { id: "next_step", keys: ["n"], label: "Next step" },
  { id: "next_turn", keys: ["shift+n"], label: "Next turn" },
  { id: "untap_all", keys: ["u"], label: "Untap all your permanents" },
  { id: "turn_over", keys: ["f"], label: "Turn over (double-faced card)" },
  { id: "to_graveyard", keys: ["delete", "backspace"], label: "Put selected into their owner's graveyard" },
  { id: "cancel", keys: ["escape"], label: "Clear selection / close views" },
  { id: "help", keys: ["shift+?", "?"], label: "Show shortcuts" },
  { id: "respond", keys: ["r"], label: "Respond (keep priority)" },
  { id: "pass", keys: ["p"], label: "Pass priority (manual play: the dial's main button)" },
  { id: "auto_pass", keys: ["shift+p"], label: "Auto-pass for the rest of this turn" },
  { id: "hud", keys: ["h"], label: "Hide / show player counters & tools" },
  { id: "cam_seat", keys: ["1"], label: "3D table: look from your seat" },
  { id: "cam_player", keys: ["2", "3", "4", "5", "6"], label: "3D table: look at the next players' sides, in seat order" },
  { id: "cam_table", keys: ["0"], label: "3D table: look down on the whole table" },
  { id: "cam_focus", keys: ["c"], label: "3D table: zoom to the hovered card (C or Esc to return)" },
  { id: "cam_reset", keys: ["home"], label: "3D table: back to your seat" },
  { id: "cam_names", keys: ["v"], label: "3D table: show / hide the names of all cards on the table" },
];

export function comboOf(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey">): string {
  const key = e.key.toLowerCase();
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("ctrl");
  if (e.shiftKey && key !== "shift") parts.push("shift");
  parts.push(key);
  return parts.join("+");
}

/** The effective table: defaults with the profile's remapped keys applied. */
export function effectiveHotkeys(keymap: Record<string, string[]> = {}): Hotkey[] {
  return HOTKEYS.map((h) => (keymap[h.id]?.length ? { ...h, keys: keymap[h.id]! } : h));
}

let cacheKey = "";
let byCombo = new Map<string, HotkeyId>();

export function matchHotkey(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey">, keymap: Record<string, string[]> = {}): HotkeyId | null {
  const key = JSON.stringify(keymap);
  if (key !== cacheKey) {
    cacheKey = key;
    byCombo = new Map(effectiveHotkeys(keymap).flatMap((h) => h.keys.map((k) => [k, h.id] as [string, HotkeyId])));
  }
  return byCombo.get(comboOf(e)) ?? null;
}

/** Bookmarks are fixed: Ctrl+1…9 recalls a view, Ctrl+Shift+1…9 saves it (matched by physical key). */
export function bookmarkSlot(e: Pick<KeyboardEvent, "code" | "ctrlKey" | "metaKey" | "shiftKey">): { slot: number; save: boolean } | null {
  const m = /^Digit([1-9])$/.exec(e.code);
  if (!m || !(e.ctrlKey || e.metaKey)) return null;
  return { slot: Number(m[1]), save: e.shiftKey };
}

/** Every key bound to more than one action (must be empty). */
export function collisions(list: Hotkey[] = HOTKEYS): string[] {
  const seen = new Map<string, string>();
  const out: string[] = [];
  for (const h of list) for (const k of h.keys) {
    if (seen.has(k)) out.push(`${k}: ${seen.get(k)} / ${h.id}`);
    seen.set(k, h.id);
  }
  return out;
}
