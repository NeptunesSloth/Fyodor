import { useSyncExternalStore } from "react";
import { linkedCheck } from "./linkedAsset";

/**
 * The real mana and card symbols ({W}, {2/U}, {T} …). The host fetches Scryfall's SVGs with the card database (they're
 * never shipped with Fyodor; backend/app/cards/linked.py) and lists the ones it has at /api/symbols. Until a symbol is
 * there, cards/ManaText.tsx draws its letter circle instead, so offline before the first download nothing is missing.
 */
export const SYMBOLS_URL = "/api/symbols";

export interface SymbolInfo {
  /** Its SVG's name: served at /api/symbols/{svg}.svg. */
  svg: string;
  /** What it means in words ("one white mana"), for its alt text. */
  english: string;
}

type Symbols = Readonly<Record<string, SymbolInfo>>;
let symbols: Symbols = {};
const listeners = new Set<() => void>();

function publish(next: Symbols): void {
  symbols = next;
  for (const l of [...listeners]) l();
}

/** Does the host have the symbols? Loads their list, and sets `has-symbols` on the page when it does. */
export const checkSymbols = linkedCheck("has-symbols", async () => {
  const res = await fetch(SYMBOLS_URL);
  if (!res.ok) return false;
  const body = (await res.json()) as { symbols?: Record<string, SymbolInfo> };
  const next = body.symbols && typeof body.symbols === "object" ? body.symbols : {};
  if (JSON.stringify(next) !== JSON.stringify(symbols)) publish(next);
  return Object.keys(next).length > 0;
});

/** Replaces the known symbols (the tests; the check does this itself). */
export function setSymbols(next: Symbols): void {
  publish(next);
}

/** A symbol's text without braces ("W", "2/U", "T") -> where its SVG is, if the host has it. */
export function symbolInfo(map: Symbols, text: string): SymbolInfo | undefined {
  return map[text] ?? map[text.toUpperCase()];
}

export function symbolUrl(info: SymbolInfo): string {
  return `${SYMBOLS_URL}/${encodeURIComponent(info.svg)}.svg`;
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};
const snapshot = () => symbols;

/** The symbols the host has (re-renders when they arrive). */
export function useSymbols(): Symbols {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
