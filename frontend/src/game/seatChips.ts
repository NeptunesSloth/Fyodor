/**
 * The seat buttons' colours: each button is a round chip (a plain bevelled rim, a brass inlay round its
 * face) in its own muted jewel tone, so the row reads at a glance on the dark wood. Colour is never the only cue: every
 * chip keeps its glyph, its tooltip and its accessible name (game/seatActions.ts). Pure data, shared by the 2D buttons
 * (game/seatIcons.ts, as images) and the 3D table's chips (table3d/seatProps.ts, their edges).
 */
import type { SeatIconId } from "./seatIcons";

export interface ChipColor {
  /** The chip's body: its face and edge. */
  base: string;
  /** The lit side (the top left) of its bevel. */
  light: string;
  /** The shaded side (the lower right) and the edge's dark. */
  dark: string;
  /** What it means, for the code reader (never shown alone). */
  why: string;
}

/** The glyph and the typed count on every chip: warm ivory, the table's card-stock white. */
export const CHIP_INK = "#f6ecd4";

export const SEAT_CHIPS: Record<SeatIconId, ChipColor> = {
  untap: { base: "#56606a", light: "#7d8892", dark: "#2c3238", why: "pewter: a neutral reset of the board" },
  draw: { base: "#2f5b8c", light: "#4f7fb3", dark: "#183251", why: "sapphire: blue, the colour of card draw" },
  scry: { base: "#5d3f86", light: "#8063ab", dark: "#33204e", why: "amethyst: foresight" },
  mill: { base: "#3e5a4b", light: "#5f7f6c", dark: "#1f3027", why: "grave moss: the graveyard" },
  reveal: { base: "#94601e", light: "#ad7a30", dark: "#553409", why: "amber: shown to the table, a lamp" },
  mulligan: { base: "#226b69", light: "#3f918d", dark: "#0f3a39", why: "teal: a fresh hand, swapped" },
  extras: { base: "#7b3b2c", light: "#a45b47", dark: "#431c13", why: "garnet leather: the bag" },
  importer: { base: "#6b5a3a", light: "#917c55", dark: "#3a301d", why: "brass-brown: the card importer" },
};

/** WCAG relative luminance of a #rrggbb colour. */
export function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
}

/** WCAG contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p) as [number, number];
  return (x + 0.05) / (y + 0.05);
}

/** The chip colour as a three.js colour number (0xrrggbb). */
export const chipHex = (c: string): number => parseInt(c.slice(1), 16);
