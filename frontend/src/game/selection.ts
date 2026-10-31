/** Quick selection filters for busy boards, from card metadata the client already has. */
import type { MenuItem } from "../components/ContextMenu";
import { useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { isVisible, type GameCard } from "../types/game";
import { send } from "./actions";
import { toast } from "../components/Toasts";
import { tidyLandMoves, type LandFacts } from "./tidy";

export function typeLine(c: GameCard): string {
  if (!isVisible(c)) return "";
  if (c.token && !c.card_id) return c.token.type_line;
  const data = c.card_id ? useCardCache.getState().cards[c.card_id] : undefined;
  const line = data?.type_line ?? c.token?.type_line ?? "";
  return line.split("//")[0] ?? "";
}

export type Filter = (c: GameCard, me: string) => boolean;

const mine: Filter = (c, me) => c.controller === me;
export const FILTERS: [string, Filter][] = [
  ["My creatures", (c, me) => mine(c, me) && /Creature/.test(typeLine(c))],
  ["My lands", (c, me) => mine(c, me) && /Land/.test(typeLine(c))],
  ["My tokens", (c, me) => mine(c, me) && isVisible(c) && c.is_token],
  ["My artifacts", (c, me) => mine(c, me) && /Artifact/.test(typeLine(c))],
  ["My enchantments", (c, me) => mine(c, me) && /Enchantment/.test(typeLine(c))],
  ["My tapped permanents", (c, me) => mine(c, me) && !!c.tapped],
  ["My untapped permanents", (c, me) => mine(c, me) && !c.tapped],
  ["All tokens", (c) => isVisible(c) && c.is_token],
  ["Everything I control", mine],
];

export function selectWhere(filter: Filter): number {
  const s = useGame.getState();
  const view = s.view;
  if (!view) return 0;
  const me = perspective(view, s.actingAs);
  const ids = Object.values(view.cards).filter((c) => c.zone.endsWith(":battlefield") && filter(c, me)).map((c) => c.id);
  s.select(ids);
  return ids.length;
}

export function invertSelection(): void {
  const s = useGame.getState();
  const view = s.view;
  if (!view) return;
  const me = perspective(view, s.actingAs);
  const current = new Set(s.selection);
  s.select(Object.values(view.cards).filter((c) => c.zone === `${me}:battlefield` && !current.has(c.id)).map((c) => c.id));
}

export function selectMenu(): MenuItem {
  return {
    label: "Select",
    submenu: [
      ...FILTERS.map(([label, f]) => ({ label, onClick: () => void selectWhere(f) })),
      "separator",
      { label: "Invert selection", onClick: invertSelection },
      { label: "Clear selection", hint: "Esc", onClick: () => useGame.getState().clearSelection() },
    ],
  };
}

export function cleanupMenu(): MenuItem {
  const clean = (what: string[]) => () => void send({ type: "cleanup", what });
  return {
    label: "Clean up",
    submenu: [
      { label: "Clear combat", hint: "attackers, blockers, combat arrows", onClick: clean(["combat"]) },
      { label: "Clear damage", onClick: clean(["damage"]) },
      { label: "Clear temporary effects", onClick: clean(["effects"]) },
      { label: "Clear arrows", onClick: clean(["arrows"]) },
      { label: "Clear mana pools", onClick: clean(["mana"]) },
      { label: "Reset response state", onClick: clean(["response"]) },
      "separator",
      {
        label: "Delete all tokens…",
        danger: true,
        onClick: () => {
          if (window.confirm("Delete every (unprotected) token on the table? Undo brings them back.")) clean(["tokens"])();
        },
      },
    ],
  };
}

/** "Tidy my lands" (game/tidy.ts): pile my identical lands along my edge, as one undoable move. */
export function tidyMyLands(): void {
  const s = useGame.getState();
  const view = s.view;
  if (!view) return;
  const me = perspective(view, s.actingAs);
  const lands: LandFacts[] = [];
  for (const id of (view.zones[`${me}:battlefield`] as string[] | undefined) ?? []) {
    const c = view.cards[id];
    if (!isVisible(c) || c.controller !== me || c.attached_to) continue;
    lands.push({ id, name: c.name, typeLine: typeLine(c) });
  }
  const moves = tidyLandMoves(lands);
  if (!moves.length) {
    toast("No lands of yours to tidy");
    return;
  }
  void send({ type: "set_position", moves });
}

/** Right-click on empty table: the table's own actions (Tabletop Simulator style). */
export function tableMenu(): MenuItem[] {
  return [
    { label: "Tidy my lands", hint: "pile identical lands by your edge · Undo puts them back", onClick: tidyMyLands },
    selectMenu(),
    cleanupMenu(),
  ];
}
