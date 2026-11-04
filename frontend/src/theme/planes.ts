/**
 * Table themes inspired by famous Magic planes. One definition drives everything a theme
 * controls: the UI accent palette (CSS tokens), the 3D environment's light and table (fog,
 * lighting, table surface, felt) and the ambient audio; the room built around the table, its
 * props and particles are the plane's set (table3d/env/sets.ts). Cards, counters and prompts
 * never change with the theme; the room stays dimmer than the table so the game state reads first.
 *
 * Everything is procedural (no downloaded art), so themes work offline and weigh nothing.
 */

export type PlaneId =
  | "dominaria" | "ravnica" | "innistrad" | "theros" | "zendikar"
  | "kamigawa" | "amonkhet" | "ixalan" | "phyrexia" | "lorwyn";

export type Surface = "oak" | "marble" | "slate" | "weathered" | "stone" | "lacquer" | "sandstone" | "jungle" | "oilmetal" | "meadow";
export type Particles = "dust" | "embers" | "fog" | "motes" | "stars" | "fireflies" | "petals" | "sand" | "spores" | "oil" | "pollen";
export type Ambience = "hearth" | "city" | "night" | "temple" | "wilds" | "shrine" | "desert" | "jungle" | "machine" | "meadow";

export interface PlaneTheme {
  id: PlaneId;
  name: string;
  tagline: string;
  wave: 1 | 2;
  /** Four swatches for the picker. */
  swatches: [string, string, string, string];
  ui: {
    bg: string; bg2: string; panelRgb: [number, number, number];
    line: string; line2: string; frame: string; frameHi: string;
    text: string; textDim: string; textFaint: string;
    accent: string; accent2: string; accentDeep: string; accentInk: string;
    select: string;
  };
  env: {
    skyTop: string; skyBottom: string; fog: string; fogDensity: number;
    ambient: string; ambientIntensity: number;
    key: string; keyIntensity: number;
    rim: string; rimIntensity: number;
    /** The colour and strength of the flames and lamps on the table and in the room, and how much they flicker. */
    glow: string; glowIntensity: number; flicker: number;
    surface: Surface; surfaceBase: string; surfaceGrain: string; inlay: string;
    rail: string;
    /** The cloth of each seat's playmat (base and the lighter nap), set into the table surface. */
    felt: string; feltNap: string;
  };
  ambience: Ambience;
}

export const PLANES: PlaneTheme[] = [
  {
    id: "dominaria", name: "Dominaria", wave: 1,
    tagline: "Where it began. A scholar's study: walnut and baize, books to the ceiling, a fire in the hearth.",
    swatches: ["#d4a55a", "#3b2117", "#21434c", "#eee5d3"],
    ui: { bg: "#0b0c0d", bg2: "#121416", panelRgb: [19, 21, 23], line: "#2a2d31", line2: "#3e4247", frame: "#8a6a3f", frameHi: "#dcb46a",
      text: "#eee5d3", textDim: "#b5ad9e", textFaint: "#857e72", accent: "#d4a55a", accent2: "#f0ca7e", accentDeep: "#93682c", accentInk: "#231605", select: "#7fb6ff" },
    env: { skyTop: "#14110f", skyBottom: "#070607", fog: "#0d0b0a", fogDensity: 0.028, ambient: "#ffe2b8", ambientIntensity: 0.35,
      key: "#ffe6c4", keyIntensity: 1.5, rim: "#6f8fd0", rimIntensity: 0.25, glow: "#ffae52", glowIntensity: 1.6, flicker: 0.25,
      surface: "oak", surfaceBase: "#3b2117", surfaceGrain: "#1d0f0a", inlay: "#c9a15a", rail: "#1c100b", felt: "#152c33", feltNap: "#21434c" },
    ambience: "hearth",
  },
  {
    id: "ravnica", name: "Ravnica", wave: 1,
    tagline: "The city of guilds. A guildhall of slate and silver, lanterns swinging in its arches.",
    swatches: ["#b7c3d9", "#3a4660", "#5fc4c4", "#8d5ac8"],
    ui: { bg: "#080a10", bg2: "#0e1119", panelRgb: [18, 22, 32], line: "#232a3a", line2: "#3a4560", frame: "#5d6b8a", frameHi: "#c7d2ea",
      text: "#e9edf6", textDim: "#a6afc4", textFaint: "#6a7288", accent: "#b7c3d9", accent2: "#e2e9f7", accentDeep: "#6c7897", accentInk: "#0b0f18", select: "#5fe0e0" },
    env: { skyTop: "#161b2a", skyBottom: "#07080d", fog: "#0c0f18", fogDensity: 0.032, ambient: "#b8c6e8", ambientIntensity: 0.32,
      key: "#dfe6ff", keyIntensity: 1.3, rim: "#9a6be0", rimIntensity: 0.45, glow: "#ffcf7a", glowIntensity: 1.2, flicker: 0.12,
      surface: "slate", surfaceBase: "#262b36", surfaceGrain: "#171a22", inlay: "#aeb9d2", rail: "#14171e", felt: "#1c2236", feltNap: "#2a334e" },
    ambience: "city",
  },
  {
    id: "innistrad", name: "Innistrad", wave: 1,
    tagline: "Gothic horror under a pale moon. A chapel crypt of candles, tombs and mist.",
    swatches: ["#c9d3e0", "#2c3442", "#8e1c24", "#5a6b82"],
    ui: { bg: "#07090c", bg2: "#0d1015", panelRgb: [17, 20, 26], line: "#232833", line2: "#3a4250", frame: "#5d6878", frameHi: "#cfd8e6",
      text: "#e7ebf1", textDim: "#a2abb9", textFaint: "#66707e", accent: "#c3ccda", accent2: "#eef2f8", accentDeep: "#6e7a8c", accentInk: "#0a0c10", select: "#e05a5a" },
    env: { skyTop: "#1a2230", skyBottom: "#05070a", fog: "#1a212c", fogDensity: 0.05, ambient: "#9fb3d6", ambientIntensity: 0.28,
      key: "#c9d8ff", keyIntensity: 1.1, rim: "#a8c0ff", rimIntensity: 0.55, glow: "#ffb060", glowIntensity: 0.9, flicker: 0.35,
      surface: "weathered", surfaceBase: "#2f2a26", surfaceGrain: "#1a1714", inlay: "#b8c2d0", rail: "#15120f", felt: "#2a1619", feltNap: "#3d2226" },
    ambience: "night",
  },
  {
    id: "theros", name: "Theros", wave: 1,
    tagline: "Where gods walk. A marble temple open to the stars of Nyx, its braziers burning.",
    swatches: ["#e8c46a", "#f2ede2", "#3b2a6e", "#1c2a5a"],
    ui: { bg: "#0a0a14", bg2: "#11111f", panelRgb: [22, 20, 36], line: "#2b2944", line2: "#46426a", frame: "#8f7a45", frameHi: "#f0d27e",
      text: "#f5f1e6", textDim: "#bdb6a2", textFaint: "#7a7466", accent: "#e8c46a", accent2: "#f8e2a0", accentDeep: "#a88630", accentInk: "#1d1605", select: "#b69bff" },
    env: { skyTop: "#241a4a", skyBottom: "#07061a", fog: "#141130", fogDensity: 0.022, ambient: "#d6ccff", ambientIntensity: 0.35,
      key: "#fff4de", keyIntensity: 1.5, rim: "#8a6bff", rimIntensity: 0.6, glow: "#ffd27a", glowIntensity: 1.1, flicker: 0.1,
      surface: "marble", surfaceBase: "#c9c1b0", surfaceGrain: "#8f8574", inlay: "#d6b25a", rail: "#b9b1a2", felt: "#17213f", feltNap: "#24325a" },
    ambience: "temple",
  },
  {
    id: "zendikar", name: "Zendikar", wave: 1,
    tagline: "A wild, restless world. Broken rock and roots among drifting hedrons.",
    swatches: ["#6fcf97", "#5a5040", "#e0873a", "#2a4a3a"],
    ui: { bg: "#070d0a", bg2: "#0d1611", panelRgb: [15, 26, 20], line: "#1f3328", line2: "#35533f", frame: "#5d7a5a", frameHi: "#9fe3b8",
      text: "#ecf3ea", textDim: "#a9bba8", textFaint: "#6c7f6a", accent: "#6fcf97", accent2: "#aef0c6", accentDeep: "#3d8e61", accentInk: "#06130b", select: "#ffb055" },
    env: { skyTop: "#1d3a36", skyBottom: "#060c0a", fog: "#12211c", fogDensity: 0.03, ambient: "#cdeedd", ambientIntensity: 0.34,
      key: "#fff0d8", keyIntensity: 1.4, rim: "#5fe0a8", rimIntensity: 0.4, glow: "#7dffc0", glowIntensity: 0.9, flicker: 0.05,
      surface: "stone", surfaceBase: "#5a5446", surfaceGrain: "#3a352b", inlay: "#7fe0ac", rail: "#2e2a22", felt: "#1c2d22", feltNap: "#2a4231" },
    ambience: "wilds",
  },
  {
    id: "kamigawa", name: "Kamigawa", wave: 2,
    tagline: "Shrines and neon. Tatami, paper screens and lanterns, petals on the air.",
    swatches: ["#e0463c", "#1a1418", "#ff7ad9", "#f2e8d8"],
    ui: { bg: "#0c0809", bg2: "#140d0f", panelRgb: [28, 17, 20], line: "#3a2227", line2: "#5a343b", frame: "#8a3a3a", frameHi: "#ff8b7a",
      text: "#f6ece6", textDim: "#c4aaa5", textFaint: "#836d69", accent: "#e8574a", accent2: "#ff9a8a", accentDeep: "#9c2a22", accentInk: "#190605", select: "#ff7ad9" },
    env: { skyTop: "#2a1422", skyBottom: "#08050a", fog: "#1a0f16", fogDensity: 0.03, ambient: "#ffd6e0", ambientIntensity: 0.3,
      key: "#ffe8e0", keyIntensity: 1.3, rim: "#ff5fc8", rimIntensity: 0.55, glow: "#ff9a5a", glowIntensity: 1.3, flicker: 0.15,
      surface: "lacquer", surfaceBase: "#5a1612", surfaceGrain: "#2c0a08", inlay: "#e8c36a", rail: "#1a0907", felt: "#191b23", feltNap: "#272b37" },
    ambience: "shrine",
  },
  {
    id: "amonkhet", name: "Amonkhet", wave: 2,
    tagline: "The trials under two suns. A sandstone dais among obelisks and braziers.",
    swatches: ["#e3b04b", "#c9a26a", "#2a4fa0", "#f3e2b8"],
    ui: { bg: "#0f0b06", bg2: "#18120a", panelRgb: [34, 25, 14], line: "#3e2f1a", line2: "#62492a", frame: "#9a7a3a", frameHi: "#f2c865",
      text: "#f7ecd4", textDim: "#c9b48b", textFaint: "#8a7656", accent: "#e3b04b", accent2: "#f7d58a", accentDeep: "#a3761f", accentInk: "#1e1403", select: "#5a8cff" },
    env: { skyTop: "#5a3a1a", skyBottom: "#120b05", fog: "#2a1d0f", fogDensity: 0.025, ambient: "#ffe0a8", ambientIntensity: 0.42,
      key: "#fff0c8", keyIntensity: 1.7, rim: "#ffae52", rimIntensity: 0.4, glow: "#ffcf6a", glowIntensity: 1.0, flicker: 0.08,
      surface: "sandstone", surfaceBase: "#b08a55", surfaceGrain: "#7a5c34", inlay: "#2a4fa0", rail: "#6a4f2c", felt: "#1b2a48", feltNap: "#283b66" },
    ambience: "desert",
  },
  {
    id: "ixalan", name: "Ixalan", wave: 2,
    tagline: "Jungle, gold and the sea. A temple overgrown with vines, torches and fireflies.",
    swatches: ["#e8b53a", "#1f5a3a", "#2a8aa0", "#6a4a2a"],
    ui: { bg: "#060d0a", bg2: "#0c1611", panelRgb: [16, 28, 21], line: "#1f3629", line2: "#34583f", frame: "#8a7a3a", frameHi: "#f0cc5a",
      text: "#eef3e4", textDim: "#afbd9d", textFaint: "#6f7d5f", accent: "#e8b53a", accent2: "#f7d77a", accentDeep: "#a17a16", accentInk: "#1a1303", select: "#4fd0e0" },
    env: { skyTop: "#1a3a2a", skyBottom: "#050c08", fog: "#10231a", fogDensity: 0.035, ambient: "#d8f0c8", ambientIntensity: 0.34,
      key: "#fff2d0", keyIntensity: 1.4, rim: "#4fd0e0", rimIntensity: 0.35, glow: "#ffc84a", glowIntensity: 1.0, flicker: 0.1,
      surface: "jungle", surfaceBase: "#4a4a36", surfaceGrain: "#2a2c1e", inlay: "#e8b53a", rail: "#26261a", felt: "#132f2d", feltNap: "#1f4542" },
    ambience: "jungle",
  },
  {
    id: "phyrexia", name: "New Phyrexia", wave: 2,
    tagline: "All will be one. A cathedral of bone-white ribs over glowing oil.",
    swatches: ["#c8d8c0", "#1a1c1a", "#6a8a5a", "#8a1a2a"],
    ui: { bg: "#070807", bg2: "#0d0f0d", panelRgb: [18, 21, 18], line: "#242a24", line2: "#3a443a", frame: "#5a6a58", frameHi: "#d8e8d0",
      text: "#eaf0e6", textDim: "#a4ae9e", textFaint: "#687264", accent: "#c8d8c0", accent2: "#eef6ea", accentDeep: "#6e8068", accentInk: "#0a0c0a", select: "#ff4a6a" },
    env: { skyTop: "#1a221a", skyBottom: "#050605", fog: "#0e130e", fogDensity: 0.04, ambient: "#c8e0c0", ambientIntensity: 0.26,
      key: "#e8f4e0", keyIntensity: 1.2, rim: "#7aff8a", rimIntensity: 0.4, glow: "#9aff6a", glowIntensity: 0.8, flicker: 0.2,
      surface: "oilmetal", surfaceBase: "#1c201e", surfaceGrain: "#0c0e0d", inlay: "#c8d8c0", rail: "#0a0b0a", felt: "#161a17", feltNap: "#232924" },
    ambience: "machine",
  },
  {
    id: "lorwyn", name: "Lorwyn", wave: 2,
    tagline: "Endless summer at dusk. A meadow ringed by willows and glowing mushrooms.",
    swatches: ["#f0c060", "#6a9a4a", "#7a5ab0", "#e8f0c8"],
    ui: { bg: "#0b0d08", bg2: "#12160d", panelRgb: [24, 30, 18], line: "#2c3522", line2: "#475838", frame: "#7a8a4a", frameHi: "#f2d27a",
      text: "#f4f2e0", textDim: "#bdbb98", textFaint: "#7c7a5c", accent: "#f0c060", accent2: "#fbe0a0", accentDeep: "#a88426", accentInk: "#1c1504", select: "#b690ff" },
    env: { skyTop: "#3a3a5a", skyBottom: "#0a0a10", fog: "#1a1a24", fogDensity: 0.028, ambient: "#fff0d0", ambientIntensity: 0.4,
      key: "#fff2c8", keyIntensity: 1.5, rim: "#a88aff", rimIntensity: 0.45, glow: "#ffd07a", glowIntensity: 1.0, flicker: 0.12,
      surface: "meadow", surfaceBase: "#5a6a3a", surfaceGrain: "#3a4526", inlay: "#f0c060", rail: "#2e3520", felt: "#232f1c", feltNap: "#33452a" },
    ambience: "meadow",
  },
];

export const DEFAULT_PLANE: PlaneId = "dominaria";

export function plane(id: string | null | undefined): PlaneTheme {
  return PLANES.find((p) => p.id === id) ?? PLANES[0]!;
}

const rgba = ([r, g, b]: [number, number, number], a: number) => `rgba(${r}, ${g}, ${b}, ${a})`;
const hexRgb = (hex: string): [number, number, number] => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const luminance = ([r, g, b]: [number, number, number]) => {
  const lin = (c: number) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};
/** WCAG contrast ratio of two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(hexRgb(a)), luminance(hexRgb(b))];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
const hex = ([r, g, b]: [number, number, number]) => `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;

/**
 * The darkest stop of the brass button gradient: as close to accentDeep as dark ink on it still
 * reads at 4.5:1 (the critique measured 3.6:1 with accentDeep itself).
 */
export function accentLow(p: PlaneTheme): string {
  const a = hexRgb(p.ui.accent);
  const d = hexRgb(p.ui.accentDeep);
  for (let t = 1; t > 0; t -= 0.05) {
    const c = hex([a[0] + (d[0] - a[0]) * t, a[1] + (d[1] - a[1]) * t, a[2] + (d[2] - a[2]) * t]);
    if (contrast(c, p.ui.accentInk) >= 4.5) return c;
  }
  return p.ui.accent;
}

/** Faint text, lifted toward textDim until it reads at 4.5:1 on the plane's panels. */
export function textFaint(p: PlaneTheme): string {
  const f = hexRgb(p.ui.textFaint);
  const d = hexRgb(p.ui.textDim);
  const panel = hex(p.ui.panelRgb);
  for (let t = 0; t <= 1; t += 0.05) {
    const c = hex([f[0] + (d[0] - f[0]) * t, f[1] + (d[1] - f[1]) * t, f[2] + (d[2] - f[2]) * t]);
    if (contrast(c, panel) >= 4.5 && contrast(c, p.ui.bg) >= 4.5) return c;
  }
  return p.ui.textDim;
}

/** The CSS custom properties for a plane (applied on <html>). */
export function cssTokens(p: PlaneTheme): Record<string, string> {
  const u = p.ui;
  const e = p.env;
  const accent = hexRgb(u.accent);
  const sel = hexRgb(u.select);
  const glow = hexRgb(e.glow);
  const panel = u.panelRgb;
  const panelHi: [number, number, number] = [panel[0] + 10, panel[1] + 10, panel[2] + 10];
  const steelHi: [number, number, number] = [panel[0] + 5, panel[1] + 5, panel[2] + 5];
  const steelLo: [number, number, number] = [panel[0] * 0.55, panel[1] * 0.55, panel[2] * 0.55];
  const scene = [
    `radial-gradient(ellipse 38% 30% at 8% 12%, ${rgba(glow, 0.16)}, transparent 70%)`,
    `radial-gradient(ellipse 30% 26% at 94% 18%, ${rgba(glow, 0.12)}, transparent 70%)`,
    `radial-gradient(ellipse 45% 35% at 50% 110%, ${rgba(glow, 0.12)}, transparent 70%)`,
    `radial-gradient(ellipse 80% 70% at 50% 45%, transparent 40%, rgba(0, 0, 0, 0.7) 100%)`,
    `linear-gradient(180deg, ${e.skyTop}, ${e.skyBottom})`,
  ].join(", ");
  // the 2D table is the same baize as the 3D mats, lit from above
  const surface = [
    `radial-gradient(ellipse 70% 60% at 50% 45%, ${rgba(hexRgb(e.feltNap), 0.9)}, transparent 75%)`,
    `radial-gradient(ellipse 95% 85% at 50% 50%, transparent 55%, rgba(0, 0, 0, 0.5) 100%)`,
    `linear-gradient(180deg, ${e.feltNap}, ${e.felt})`,
  ].join(", ");
  return {
    "--bg": u.bg, "--bg-2": u.bg2,
    "--panel": rgba(panel, 0.94), "--panel-2": rgba(panelHi, 0.96),
    "--panel-grad": `linear-gradient(180deg, ${rgba(panelHi, 0.95)}, ${rgba(panel, 0.97)})`,
    "--line": u.line, "--line-2": u.line2, "--frame": u.frame, "--frame-hi": u.frameHi,
    "--frame-inner": rgba(hexRgb(u.frameHi), 0.14),
    "--text": u.text, "--text-dim": u.textDim, "--text-faint": textFaint(p),
    "--accent": u.accent, "--accent-2": u.accent2, "--accent-ink": u.accentInk,
    "--accent-grad": `linear-gradient(180deg, ${u.accent2} 0%, ${u.accent} 50%, ${accentLow(p)} 100%)`,
    "--accent-glow": rgba(accent, 0.42),
    "--select": u.select, "--select-glow": rgba(sel, 0.55),
    "--felt": e.felt, "--felt-2": e.feltNap, "--wood": e.surfaceBase, "--wood-2": e.surfaceGrain,
    "--mat": "rgba(0, 0, 0, 0.22)", "--mat-line": rgba(hexRgb(e.inlay), 0.22),
    "--steel-hi": hex(steelHi), "--steel-lo": hex(steelLo),
    "--hud-surface": `linear-gradient(180deg, ${hex(steelHi)}, ${hex(steelLo)})`,
    "--scene": scene, "--table-surface": surface,
    "--room-charcoal": u.bg, "--room-charcoal-2": u.bg2, "--room-edge": u.line2,
    "--room-felt": e.felt, "--room-felt-deep": e.feltNap,
    "--room-bone": u.text, "--room-bone-dim": u.textDim, "--room-brass": u.accent, "--room-brass-hi": u.accent2,
  };
}

export function applyPlane(id: string | null | undefined): void {
  const p = plane(id);
  const root = document.documentElement;
  root.dataset.theme = p.id;
  for (const [k, v] of Object.entries(cssTokens(p))) root.style.setProperty(k, v);
}
