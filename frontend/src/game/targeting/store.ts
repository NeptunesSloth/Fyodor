import { create } from "zustand";

/** One chosen candidate of a multi-choice (choose_cards): the option to answer with and the card or player it is. */
export interface Pick {
  opt: string;
  ref: string;
}

/**
 * What the chooser is doing with a targeting decision on this screen only (display state, never sent until Done):
 * the candidates chosen so far, the one under the pointer in the tray, the one with keyboard focus.
 */
interface TargetingStore {
  decision: string | null;
  picked: Pick[];
  /** The candidate (card or player id) hovered in the tray. */
  hot: string | null;
  /** The candidate with keyboard focus (its tray thumbnail is focused): a focus ring on the board. */
  focus: string | null;
  /** -- sweep B2 -- the tray's candidates in their order, and the last one clicked: Shift+click chooses the run between them. */
  order: Pick[];
  anchor: string | null;
  reset: (decision: string | null) => void;
  /** Choose or un-choose; at most ``max`` (with one allowed, a new pick replaces the old). */
  toggle: (decision: string, pick: Pick, max: number) => void;
  /** Shift+click: choose every candidate from the last one clicked to this one, in tray order (at most ``max`` in all). */
  range: (decision: string, pick: Pick, max: number) => void;
  /** "Select all": the first ``max`` candidates in tray order (none: clear). */
  fill: (decision: string, max: number) => void;
  setOrder: (order: Pick[]) => void;
  setHot: (ref: string | null) => void;
  setFocus: (ref: string | null) => void;
}

export const useTargeting = create<TargetingStore>((set) => ({
  decision: null,
  picked: [],
  hot: null,
  focus: null,
  order: [],
  anchor: null,
  reset: (decision) => set({ decision, picked: [], hot: null, focus: null, anchor: null }),
  toggle: (decision, pick, max) => set((s) => {
    const picked = s.decision === decision ? s.picked : [];
    if (picked.some((p) => p.ref === pick.ref)) return { decision, picked: picked.filter((p) => p.ref !== pick.ref), anchor: pick.ref };
    if (picked.length >= max) return max === 1 ? { decision, picked: [pick], anchor: pick.ref } : { decision, picked };
    return { decision, picked: [...picked, pick], anchor: pick.ref };
  }),
  range: (decision, pick, max) => set((s) => {
    const picked = s.decision === decision ? s.picked : [];
    const from = s.order.findIndex((p) => p.ref === s.anchor);
    const to = s.order.findIndex((p) => p.ref === pick.ref);
    if (from < 0 || to < 0) return {}; // (nothing clicked yet: a plain click's toggle, below)
    const run = s.order.slice(Math.min(from, to), Math.max(from, to) + 1).filter((p) => !picked.some((q) => q.ref === p.ref));
    return { decision, picked: [...picked, ...run].slice(0, Math.max(max, picked.length)), anchor: pick.ref };
  }),
  fill: (decision, max) => set((s) => ({ decision, picked: s.order.slice(0, max), anchor: null })),
  setOrder: (order) => set({ order }),
  setHot: (hot) => set((s) => (s.hot === hot ? s : { hot })),
  setFocus: (focus) => set((s) => (s.focus === focus ? s : { focus })),
}));

/** The order a card or player was chosen in (1-based), 0 when it isn't. */
export const pickNumber = (picked: readonly Pick[], ref: string): number => picked.findIndex((p) => p.ref === ref) + 1;
