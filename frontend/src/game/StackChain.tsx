/**
 * The stack as a chain (Master Duel): one row per object, numbered from the bottom (1 is the first
 * thing cast), the top row marked "Resolves next", with targets, X, modes and copies. Repeated
 * identical triggers in a row collapse into one "3×" row. Shared by the manual stack panel and the
 * rules engine's stack, so both read the same way.
 */
import type { ReactNode } from "react";
import { playerName, useGame } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { GameCardFace } from "./GameCardFace";

export function stackTypeLine(cardId: string | null | undefined): string {
  const data = cardId ? useCardCache.getState().cards[cardId] : undefined;
  return data?.type_line?.split("—")[0]?.trim() ?? "";
}

export function targetName(view: GameView, id: string): string {
  if (view.players.some((p) => p.id === id)) return playerName(view, id);
  const c = view.cards[id];
  return c && !c.hidden ? c.name : "a card";
}

function title(c: GameCard | undefined): string {
  if (!c) return "?";
  if (!isVisible(c)) return "Face-down spell";
  return c.ability ? c.ability.source_name ? `${c.ability.source_name} ability` : "Ability" : c.name;
}

function kindOf(c: GameCard | undefined): string {
  if (!c || !isVisible(c)) return "";
  if (c.ability) return c.ability.kind === "triggered" ? "Triggered ability" : c.ability.kind === "activated" ? "Activated ability" : "Ability";
  return stackTypeLine(c.card_id);
}

export interface ChainEntry {
  /** The top-most id of the group (what hover, drag and hold act on). */
  id: string;
  ids: string[];
  /** Chain number of the top-most object (1 = bottom of the stack). */
  no: number;
}

/** Top first; consecutive objects that read the same (same source, same text, no targets) share a row. */
export function chainEntries(view: GameView): ChainEntry[] {
  const out: ChainEntry[] = [];
  const stack = view.stack;
  const sig = (id: string) => {
    const c = view.cards[id];
    if (!c || !isVisible(c) || !c.ability) return `solo:${id}`;
    const targeted = (view.arrows ?? []).some((a) => a.source === id);
    return targeted ? `solo:${id}` : `${c.ability.source_name}|${c.ability.text}|${c.controller}`;
  };
  for (let i = stack.length - 1; i >= 0; i--) {
    const id = stack[i]!;
    const last = out[out.length - 1];
    if (last && !sig(id).startsWith("solo:") && sig(id) === sig(last.ids[0]!)) last.ids.push(id);
    else out.push({ id, ids: [id], no: i + 1 });
  }
  return out;
}

export function ChainRow({ entry, top, view, children, ...rest }: {
  entry: ChainEntry; top: boolean; view: GameView; children?: ReactNode;
} & React.HTMLAttributes<HTMLLIElement>) {
  const c = view.cards[entry.id];
  const visible = !!c && isVisible(c);
  const targets = (view.arrows ?? []).filter((a) => a.source === entry.id).flatMap((a) => a.targets);
  const info = visible ? c.stack_info : undefined;
  const count = entry.ids.length;
  return (
    <li
      className={`chain-row ${top ? "top" : ""}`}
      data-testid="stack-entry"
      data-card-id={entry.id}
      onPointerEnter={() => useGame.getState().setHover(entry.id)}
      onPointerLeave={() => useGame.getState().setHover(null)}
      {...rest}
    >
      <span className="chain-no" aria-label={count > 1 ? `Chain ${entry.no - count + 1} to ${entry.no}` : `Chain ${entry.no}`}>{entry.no}</span>
      <span className="chain-thumb">{c && <GameCardFace card={c} size="small" />}</span>
      <span className="chain-body">
        {top && <span className="chain-next">Resolves next</span>}
        <b className="chain-name">{count > 1 ? `${count}× ` : ""}{title(c)}{visible && c.copy_of ? " (copy)" : ""}</b>
        <span className="chain-who">{c ? playerName(view, c.controller) : ""}{kindOf(c) ? ` · ${kindOf(c)}` : ""}</span>
        {visible && c.ability?.text && <span className="chain-text">{c.ability.text}</span>}
        {targets.length > 0 && <span className="chain-tgt">→ {targets.map((t) => targetName(view, t)).join(", ")}</span>}
        {info && (info.x != null || info.tags.length > 0 || info.modes.length > 0) && (
          <span className="chain-notes">
            {info.x != null && <b className="stack-x">X = {info.x}</b>}
            {info.tags.map((t) => <span key={t} className="stack-tag">{t}</span>)}
            {info.modes.map((m) => <span key={m} className="stack-mode">✓ {m}</span>)}
          </span>
        )}
      </span>
      {children}
    </li>
  );
}
