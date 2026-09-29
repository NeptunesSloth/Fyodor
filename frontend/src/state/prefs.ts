/**
 * Local player profiles (no accounts, no passwords, no cloud). Each browser keeps a small list of
 * profiles in localStorage; one is active and its settings drive the UI. A profile can be
 * exported to / imported from a `<name>.json` file. Profile creation is never required: a
 * default profile always exists.
 *
 * The stored data is versioned; `migrateProfiles` upgrades anything older.
 */
import { DEFAULT_PLANE, type PlaneId } from "../theme/planes";
import { create } from "zustand";

export const PROFILE_VERSION = 2;

export type GraphicsPreset = "low" | "medium" | "high";

export interface Bookmark {
  name: string;
  /** Player whose side of the table is enlarged (null: everyone equal). */
  focus: string | null;
  stackOpen: boolean;
  logOpen: boolean;
}

export interface Prefs {
  /** Table theme (a Magic plane): environment, surface, lighting, ambience and UI accents. */
  plane: PlaneId;
  /** 3D table (three.js) or the flat 2D table. AUTO: 3D when WebGL works (see resolveRenderer). */
  renderer: "auto" | "3d" | "2d";
  /** Ambient environment audio (per theme). */
  ambience: boolean;
  showTokenSources: boolean;
  hud: "full" | "minimal";
  uiScale: number;
  inspectSize: "normal" | "large";
  highContrast: boolean;
  colorblindMarkers: boolean;
  reducedMotion: boolean;
  animationSpeed: number; // 0.5 … 2
  snap: boolean;
  graphics: GraphicsPreset;
  /** Identical tokens collapse into one stack above this count (0 = never). */
  tokenCollapse: 0 | 5 | 10 | 20;
  sound: { muted: boolean; master: number; cards: number; dice: number; ui: number; ambient: number };
  favoriteCounters: string[];
  favoriteTokens: string[];
  preferredSleeve: string | null;
  preferredPlaymat: string | null;
  preferredSeat: string | null;
  bookmarks: (Bookmark | null)[]; // slots 1–9
  /** Remapped shortcuts: action id → key combos (see game/hotkeys.ts). */
  keymap: Record<string, string[]>;
}

export interface Profile {
  id: string;
  name: string;
  avatar: string;
  prefs: Prefs;
}

export const DEFAULT_PREFS: Prefs = {
  plane: DEFAULT_PLANE,
  renderer: "auto",
  ambience: true,
  showTokenSources: false,
  hud: "full",
  uiScale: 1,
  inspectSize: "normal",
  highContrast: false,
  colorblindMarkers: false,
  reducedMotion: false,
  animationSpeed: 1,
  snap: true,
  graphics: "high",
  tokenCollapse: 5,
  sound: { muted: false, master: 0.6, cards: 0.8, dice: 0.8, ui: 0.6, ambient: 0 },
  favoriteCounters: ["+1/+1", "-1/-1", "Loyalty"],
  favoriteTokens: [],
  preferredSleeve: null,
  preferredPlaymat: null,
  preferredSeat: null,
  bookmarks: [],
  keymap: {},
};

const KEY = "fyodor.profiles";
const OLD_KEY = "fyodor.prefs"; // version 1: a single prefs object

interface Stored {
  version: number;
  active: string;
  profiles: Profile[];
}

const newId = () => Math.random().toString(36).slice(2, 10);

function withDefaults(p: Partial<Prefs> | undefined): Prefs {
  return { ...DEFAULT_PREFS, ...(p ?? {}), sound: { ...DEFAULT_PREFS.sound, ...(p?.sound ?? {}) } };
}

/** Upgrade stored profile data of any older version (or none) to the current shape. */
export function migrateProfiles(raw: unknown, legacyPrefs: unknown = null): Stored {
  const data = (raw && typeof raw === "object" ? raw : null) as Partial<Stored> | null;
  if (!data || !Array.isArray(data.profiles) || !data.profiles.length) {
    // v1 kept one prefs object; turn it into the default profile
    const prefs = withDefaults((legacyPrefs && typeof legacyPrefs === "object" ? legacyPrefs : {}) as Partial<Prefs>);
    const p: Profile = { id: newId(), name: "Player", avatar: "♠", prefs };
    return { version: PROFILE_VERSION, active: p.id, profiles: [p] };
  }
  const profiles = data.profiles
    .filter((p): p is Profile => !!p && typeof p === "object" && typeof (p as Profile).id === "string")
    .map((p) => ({ id: p.id, name: String(p.name || "Player").slice(0, 40), avatar: String(p.avatar || "♠").slice(0, 4), prefs: withDefaults(p.prefs) }));
  const active = profiles.some((p) => p.id === data.active) ? (data.active as string) : profiles[0]!.id;
  return { version: PROFILE_VERSION, active, profiles };
}

function load(): Stored {
  try {
    const raw = localStorage.getItem(KEY);
    const legacy = localStorage.getItem(OLD_KEY);
    return migrateProfiles(raw ? JSON.parse(raw) : null, legacy ? JSON.parse(legacy) : null);
  } catch {
    return migrateProfiles(null);
  }
}

function persist(s: Stored): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* not remembered; nothing else breaks */
  }
}

interface ProfileStore extends Prefs {
  profiles: Profile[];
  active: string;
  set: (patch: Partial<Prefs>) => void;
  switchTo: (id: string) => void;
  addProfile: (name: string) => string;
  updateProfile: (id: string, patch: Partial<Pick<Profile, "name" | "avatar">>) => void;
  removeProfile: (id: string) => void;
  importProfile: (json: unknown) => string;
  exportProfile: (id: string) => string;
}

const initial = load();
const activePrefs = (s: Stored) => s.profiles.find((p) => p.id === s.active)!.prefs;

export const usePrefs = create<ProfileStore>((set, get) => {
  const save = (profiles: Profile[], active: string) => {
    persist({ version: PROFILE_VERSION, active, profiles });
    set({ profiles, active, ...profiles.find((p) => p.id === active)!.prefs });
  };
  return {
    ...activePrefs(initial),
    profiles: initial.profiles,
    active: initial.active,
    set: (patch) => {
      const { profiles, active } = get();
      save(profiles.map((p) => (p.id === active ? { ...p, prefs: withDefaults({ ...p.prefs, ...patch }) } : p)), active);
    },
    switchTo: (id) => {
      if (get().profiles.some((p) => p.id === id)) save(get().profiles, id);
    },
    addProfile: (name) => {
      const p: Profile = { id: newId(), name: name.slice(0, 40) || "Player", avatar: "♠", prefs: withDefaults({}) };
      save([...get().profiles, p], p.id);
      return p.id;
    },
    updateProfile: (id, patch) => save(get().profiles.map((p) => (p.id === id ? { ...p, ...patch } : p)), get().active),
    removeProfile: (id) => {
      const rest = get().profiles.filter((p) => p.id !== id);
      if (!rest.length) return;
      save(rest, get().active === id ? rest[0]!.id : get().active);
    },
    importProfile: (json) => {
      const one = migrateProfiles({ profiles: [json], active: (json as Profile)?.id }).profiles[0]!;
      const p = { ...one, id: newId() };
      save([...get().profiles, p], p.id);
      return p.id;
    },
    exportProfile: (id) => {
      const p = get().profiles.find((x) => x.id === id);
      return JSON.stringify({ format: "fyodor-profile", version: PROFILE_VERSION, ...p }, null, 2);
    },
  };
});

export const activeProfile = () => {
  const s = usePrefs.getState();
  return s.profiles.find((p) => p.id === s.active)!;
};
