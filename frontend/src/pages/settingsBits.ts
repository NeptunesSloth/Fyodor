/**
 * Settings page helpers: its sections (one list for the headings and the side index) and how a key combo reads on a keycap.
 */

export interface SettingsSection {
  id: string;
  title: string;
  /** One line under the heading: what the section is for. */
  blurb: string;
  /** Only on the host computer (the one running Fyodor). */
  hostOnly?: boolean;
}

export const SETTINGS_SECTIONS: SettingsSection[] = [
  { id: "st-theme", title: "Table theme", blurb: "Each theme is a Magic plane: its table, lighting, props, ambient sound and accent colours. Cards and prompts always look the same." },
  { id: "st-table", title: "Table & 3D", blurb: "Which table this screen draws, and how much it draws." },
  { id: "st-hand", title: "Cards & hand", blurb: "Small helps while you play." },
  { id: "st-sound", title: "Sound", blurb: "Volumes for this screen only." },
  { id: "st-alerts", title: "Alerts & pings", blurb: "What other players can send you, and how the table calls you when it waits on you." },
  { id: "st-profile", title: "Profile", blurb: "Who you are at the table. Kept in this browser: there are no accounts." },
  { id: "st-display", title: "Display & accessibility", blurb: "Size, contrast and motion." },
  { id: "st-keys", title: "Keys", blurb: "Click a key, then press the new one. Esc keeps the old key." },
  { id: "card-data", title: "Card database", blurb: "The cards Fyodor knows, kept on the host computer so it plays offline." },
  { id: "backups", title: "Backup & restore", blurb: "Decks, saves, live tables, pod stats, macros and custom sleeves and playmats." },
  { id: "st-diag", title: "Diagnostics", blurb: "A troubleshooting file for when something goes wrong.", hostOnly: true },
];

/** The sections shown on this computer, in page order. */
export function settingsSections(host: boolean): SettingsSection[] {
  return SETTINGS_SECTIONS.filter((s) => host || !s.hostOnly);
}

export function sectionById(id: string): SettingsSection {
  const s = SETTINGS_SECTIONS.find((x) => x.id === id);
  if (!s) throw new Error(`No settings section ${id}`);
  return s;
}

/** The section the side index marks: the first one (in page order) in the reading band, else the last one marked. */
export function activeSection(order: string[], visible: ReadonlySet<string>, current: string): string {
  return order.find((id) => visible.has(id)) ?? current;
}

const KEY_NAMES: Record<string, string> = {
  " ": "Space",
  escape: "Esc",
  delete: "Delete",
  backspace: "Backspace",
  enter: "Enter",
  tab: "Tab",
  home: "Home",
  end: "End",
  pageup: "Page Up",
  pagedown: "Page Down",
  arrowup: "↑",
  arrowdown: "↓",
  arrowleft: "←",
  arrowright: "→",
  ctrl: "Ctrl",
  shift: "Shift",
  alt: "Alt",
  meta: "Meta",
};

/** A combo from the key table ("ctrl+shift+z", " ") as the keycaps it is pressed with: ["Ctrl", "Shift", "Z"], ["Space"]. */
export function keyCaps(combo: string): string[] {
  const caps: string[] = [];
  let rest = combo;
  for (;;) {
    const m = /^(ctrl|shift|alt|meta)\+(?=.)/.exec(rest);
    if (!m) break;
    caps.push(KEY_NAMES[m[1]!]!);
    rest = rest.slice(m[0].length);
  }
  caps.push(KEY_NAMES[rest] ?? (rest.length === 1 ? rest.toUpperCase() : rest.charAt(0).toUpperCase() + rest.slice(1)));
  return caps;
}

/** The same combo in words, for a screen reader ("Ctrl+Shift+Z"). */
export const keyWords = (combo: string) => keyCaps(combo).join("+");
