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
  reset: (decision: string | null) => void;
  /** Choose or un-choose; at most ``max`` (with one allowed, a new pick replaces the old). */
  toggle: (decision: string, pick: Pick, max: number) => void;
  setHot: (ref: string | null) => void;
  setFocus: (ref: string | null) => void;
}

export const useTargeting = create<TargetingStore>((set) => ({
  decision: null,
  picked: [],
  hot: null,
  focus: null,
  reset: (decision) => set({ decision, picked: [], hot: null, focus: null }),
  toggle: (decision, pick, max) => set((s) => {
    const picked = s.decision === decision ? s.picked : [];
    if (picked.some((p) => p.ref === pick.ref)) return { decision, picked: picked.filter((p) => p.ref !== pick.ref) };
    if (picked.length >= max) return max === 1 ? { decision, picked: [pick] } : { decision, picked };
    return { decision, picked: [...picked, pick] };
  }),
  setHot: (hot) => set((s) => (s.hot === hot ? s : { hot })),
  setFocus: (focus) => set((s) => (s.focus === focus ? s : { focus })),
}));

/** The order a card or player was chosen in (1-based), 0 when it isn't. */
export const pickNumber = (picked: readonly Pick[], ref: string): number => picked.findIndex((p) => p.ref === ref) + 1;
