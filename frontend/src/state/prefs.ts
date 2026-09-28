/**
 * Per-browser preferences (no account, no server): kept in localStorage and safe to lose.
 * Player profiles build on this (see profiles).
 */
import { create } from "zustand";

export interface Prefs {
  showTokenSources: boolean;
  hud: "full" | "minimal";
}

const KEY = "fyodor.prefs";
const DEFAULTS: Prefs = { showTokenSources: false, hud: "full" };

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export const usePrefs = create<Prefs & { set: (patch: Partial<Prefs>) => void }>((set, get) => ({
  ...load(),
  set: (patch) => {
    set(patch);
    try {
      const { set: _omit, ...rest } = { ...get(), ...patch };
      localStorage.setItem(KEY, JSON.stringify(rest));
    } catch {
      /* not remembered */
    }
  },
}));
