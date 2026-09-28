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
  | "hud";

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
  { id: "respond", keys: ["r"], label: "Response check: RESPOND" },
  { id: "pass", keys: ["p"], label: "Response check: PASS" },
  { id: "auto_pass", keys: ["shift+p"], label: "Response check: AUTO-PASS this turn" },
  { id: "hud", keys: ["h"], label: "Minimal / full HUD" },
];

export function comboOf(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey">): string {
  const key = e.key.toLowerCase();
  const parts = [];
  if (e.ctrlKey || e.metaKey) parts.push("ctrl");
  if (e.shiftKey && key !== "shift") parts.push("shift");
  parts.push(key);
  return parts.join("+");
}

const BY_COMBO = new Map<string, HotkeyId>(HOTKEYS.flatMap((h) => h.keys.map((k) => [k, h.id] as [string, HotkeyId])));

export function matchHotkey(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey">): HotkeyId | null {
  return BY_COMBO.get(comboOf(e)) ?? null;
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
