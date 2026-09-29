import type { MulliganPolicy } from "../types/game";

export const MULLIGAN_RULES: [string, string][] = [
  ["commander_london", "Commander London"],
  ["london", "London"],
  ["boston_custom", "Boston (Custom Pod)"],
  ["custom", "Custom"],
  ["none", "None (by hand)"],
];
export const CONFIGURABLE_RULES = new Set(["boston_custom", "custom"]);

const BASE: MulliganPolicy = {
  id: "custom",
  display_name: "Custom",
  starting_hand_size: 7,
  free_mulligans: 0,
  draw_count: 7,
  shuffle_between_mulligans: true,
  cards_to_bottom: 1,
  partial_hand_selection: false,
  set_aside_rejected_hands: false,
  final_shuffle: false,
  minimum_hand_size: 0,
  max_mulligans: null,
  needs_definition: false,
};

const storeKey = (rule: string) => `fyodor.mulligan.${rule}`;

/** The host's last definition of a configurable slot (kept in this browser). */
export function savedPolicy(rule: string): MulliganPolicy | null {
  try {
    const raw = localStorage.getItem(storeKey(rule));
    return raw ? { ...BASE, ...(JSON.parse(raw) as Partial<MulliganPolicy>), id: rule, needs_definition: false } : null;
  } catch {
    return null;
  }
}

export function rememberPolicy(rule: string, policy: MulliganPolicy): void {
  try {
    localStorage.setItem(storeKey(rule), JSON.stringify(policy));
  } catch {
    /* not remembered */
  }
}

export function draftPolicy(rule: string): MulliganPolicy {
  return savedPolicy(rule) ?? { ...BASE, id: rule, display_name: rule === "boston_custom" ? "Boston (Custom Pod)" : "Custom" };
}

/**
 * Every field of a mulligan policy, spelled out. Used to define the pod's "Boston" rule (which
 * the app deliberately does not guess) or a one-off custom rule. See docs/MULLIGAN_RULES.md.
 */
export function MulliganEditor({ value, onChange }: { value: MulliganPolicy; onChange: (p: MulliganPolicy) => void }) {
  const set = (patch: Partial<MulliganPolicy>) => onChange({ ...value, ...patch, needs_definition: false });
  const num = (key: keyof MulliganPolicy, label: string, hint: string, min = 0, max = 20) => (
    <label className="field" title={hint}>
      {label}
      <input type="number" min={min} max={max} value={(value[key] as number | null) ?? ""} placeholder="no limit"
        onChange={(e) => set({ [key]: e.target.value === "" ? (key === "max_mulligans" ? null : 0) : Math.max(min, Math.min(max, Number(e.target.value))) } as Partial<MulliganPolicy>)} />
    </label>
  );
  const flag = (key: keyof MulliganPolicy, label: string, hint: string) => (
    <label className="field row-check" title={hint}>
      <span><input type="checkbox" checked={Boolean(value[key])} onChange={(e) => set({ [key]: e.target.checked } as Partial<MulliganPolicy>)} /> {label}</span>
    </label>
  );
  return (
    <div className="mull-editor" data-testid="mulligan-editor">
      <label className="field">Name shown at the table
        <input value={value.display_name} maxLength={60} onChange={(e) => set({ display_name: e.target.value })} />
      </label>
      <div className="mull-editor-grid">
        {num("starting_hand_size", "Opening hand", "Cards in the first hand")}
        {num("draw_count", "Cards per new hand", "Cards drawn for each hand after a mulligan")}
        {num("free_mulligans", "Free mulligans", "Mulligans that don't count toward cards put on the bottom", 0, 10)}
        {num("cards_to_bottom", "Bottom per mulligan", "Cards put on the bottom for each counted mulligan, chosen after keeping", 0, 10)}
        {num("minimum_hand_size", "Minimum kept hand", "A mulligan may not leave a smaller hand")}
        {num("max_mulligans", "Max mulligans", "Leave empty for no limit")}
      </div>
      <div className="mull-editor-flags">
        {flag("shuffle_between_mulligans", "Shuffle the library for each mulligan", "Rejected cards are shuffled back before drawing")}
        {flag("partial_hand_selection", "Players choose which cards to send back", "Send back some cards and draw that many, instead of the whole hand")}
        {flag("set_aside_rejected_hands", "Set rejected cards aside (face down, private)", "Instead of returning them to the library")}
        {flag("final_shuffle", "After keeping, shuffle set-aside cards into the library", "")}
      </div>
    </div>
  );
}
