/**
 * The stack as a chain (Master Duel): one row per object, numbered from the bottom (1 is the first
 * thing cast), the top row marked "Resolves next", with targets, X, modes and copies. Repeated
 * identical triggers in a row collapse into one "3×" row. Shared by the manual stack panel and the
 * rules engine's stack, so both read the same way.
 */
import { useState, type ReactNode } from "react";
import { playerName } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { GameCardFace } from "./GameCardFace";
import { useHoverCard } from "./hoverCard";
import { abilityKey, batchTitle, groupStack, ROW_LIMIT, type StackGroup } from "./stackGroups";

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

export type ChainEntry = StackGroup;

/**
 * Top first; consecutive abilities that read the same (same source, same text, same controller, nothing noted on them, the same targets)
 * share a row (stackGroups.ts). Never grouped: spells, face-down objects, and the object a pending decision is about (a player must see
 * what they answer). -- playtest B3 -- 68 Blood Artist triggers all targeting Bob are one row "×68 → Bob", not 68 rows.
 */
export function chainEntries(view: GameView): ChainEntry[] {
  const targetsOf = new Map<string, string[]>();
  for (const a of view.arrows ?? []) targetsOf.set(a.source, [...(targetsOf.get(a.source) ?? []), ...a.targets]);
  const asked = view.rules?.decision?.source_id ?? null;
  return groupStack(view.stack, (id) => {
    const c = view.cards[id];
    if (!c || !isVisible(c) || !c.ability || id === asked) return null;
    const info = c.stack_info;
    const notes = info && (info.x != null || info.modes.length || info.tags.length) ? JSON.stringify(info) : "";
    const targets = targetsOf.get(id);
    return abilityKey(c.ability.source_name, c.ability.text ?? "", c.controller, targets ? `${notes}→${JSON.stringify(targets)}` : notes);
  });
}

/** The first ROW_LIMIT rows, then a "Show N more" control: a stack of a thousand different objects stays quick to draw. */
export function useChainRows(entries: ChainEntry[]): { rows: ChainEntry[]; more: ReactNode } {
  const [limit, setLimit] = useState(ROW_LIMIT);
  const rows = entries.length > limit ? entries.slice(0, limit) : entries;
  const hidden = entries.length - rows.length;
  const more = hidden > 0 ? (
    <li className="chain-more">
      <button className="tt-btn ghost" data-testid="stack-more" onClick={() => setLimit((n) => n + ROW_LIMIT * 4)}>
        Show {Math.min(hidden, ROW_LIMIT * 4).toLocaleString("en-US")} more ({hidden.toLocaleString("en-US")} below)
      </button>
    </li>
  ) : null;
  return { rows, more };
}

export function ChainRow({ entry, top, view, children, ...rest }: {
  entry: ChainEntry; top: boolean; view: GameView; children?: ReactNode;
} & React.HTMLAttributes<HTMLLIElement>) {
  const c = view.cards[entry.id];
  const visible = !!c && isVisible(c);
  const targets = (view.arrows ?? []).filter((a) => a.source === entry.id).flatMap((a) => a.targets);
  const info = visible ? c.stack_info : undefined;
  const count = entry.ids.length;
  const hover = useHoverCard();
  const [open, setOpen] = useState(false);
  const batch = count > 1 && visible && !!c.ability;
  return (
    <li
      className={`chain-row ${top ? "top" : ""}`}
      data-testid="stack-entry"
      data-card-id={entry.id}
      {...hover(entry.id)}
      {...rest}
    >
      <span className="chain-no" aria-label={count > 1 ? `Chain ${entry.no - count + 1} to ${entry.no}` : `Chain ${entry.no}`}>{entry.no}</span>
      <span className="chain-thumb">{c && <GameCardFace card={c} size="small" />}</span>
      <span className="chain-body">
        {top && <span className="chain-next">Resolves next</span>}
        {batch ? (
          // the count never truncates: a long source name gives way first
          <b className="chain-name chain-name-batch" title={batchTitle(c.ability!.source_name, c.ability!.text ?? "", c.ability!.kind, count)}>
            <span className="chain-name-text">{batchTitle(c.ability!.source_name, c.ability!.text ?? "", c.ability!.kind, 1)}</span>{" "}
            <span className="chain-batch-count">×{count.toLocaleString("en-US")}</span>
          </b>
        ) : (
          <b className="chain-name">{count > 1 ? `${count}× ` : ""}{title(c)}{visible && c.copy_of ? " (copy)" : ""}</b>
        )}
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
        {batch && (
          <button className="chain-batch-toggle" data-testid="stack-batch-toggle" aria-expanded={open}
            onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}>
            {open ? "Hide each" : `Show each (${count.toLocaleString("en-US")})`}
          </button>
        )}
        {batch && open && <BatchMembers entry={entry} />}
      </span>
      {children}
    </li>
  );
}

/** An opened batch: each of its objects by chain number, top first (in pages, so a batch of thousands opens at once). */
function BatchMembers({ entry }: { entry: ChainEntry }) {
  const [limit, setLimit] = useState(ROW_LIMIT);
  const hover = useHoverCard();
  const shown = entry.ids.slice(0, limit);
  const rest = entry.ids.length - shown.length;
  return (
    <ol className="chain-batch" data-testid="stack-batch" aria-label="Each object in this batch">
      {shown.map((id, i) => (
        <li key={id} className={`chain-batch-item ${i === 0 ? "first" : ""}`} {...hover(id)}
          title={i === 0 ? `Chain ${entry.no - i}: resolves first of these` : `Chain ${entry.no - i}`}>{entry.no - i}</li>
      ))}
      {rest > 0 && (
        <li>
          <button className="tt-btn ghost" onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); setLimit((n) => n + ROW_LIMIT * 4); }}>
            Show {Math.min(rest, ROW_LIMIT * 4).toLocaleString("en-US")} more
          </button>
        </li>
      )}
    </ol>
  );
}
