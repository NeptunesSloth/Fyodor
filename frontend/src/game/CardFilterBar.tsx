import { ManaSymbol } from "../cards/ManaText";
import type { CardData } from "../types/cards";
import { isVisible, type GameCard } from "../types/game";
import { CARD_TYPES, COLORS, MANA_VALUES, NO_FILTER, SORTS, filtering, toggle, type CardFilter, type CardSort, type FilterCard } from "./cardFilters";
import "./cardFilters.css";

const COLOR_NAMES: Record<string, string> = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", C: "Colorless" };

/** What the filters may read of a card on the table: nothing of a card hidden from this viewer. */
export function filterCardOf(id: string, card: GameCard | undefined, data: CardData | undefined): FilterCard {
  if (!isVisible(card)) return { id, name: null, data: null };
  if (!data) return { id, name: card.name, data: null };
  // a double-faced card's colours live on its faces
  const colors = data.colors.length ? data.colors : [...new Set(data.faces.flatMap((f) => f.colors ?? []))];
  return { id, name: card.name, data: { type_line: data.type_line, cmc: data.cmc, colors, oracle_text: data.oracle_text } };
}

/**
 * Compact chips over a list of cards (library search, look at the top N, a tutor's finds): card types, mana value, colours
 * (as mana symbols with their names, never colour alone) and a sort. ``text`` adds a name/type/text box when the list
 * has none of its own.
 */
export function CardFilterBar({ value, onChange, text = false, orderLabel = "Library order" }: {
  value: CardFilter; onChange: (f: CardFilter) => void; text?: boolean; orderLabel?: string;
}) {
  const set = (patch: Partial<CardFilter>) => onChange({ ...value, ...patch });
  return (
    <div className="card-filters" data-testid="card-filters">
      {text && (
        <input className="card-filters-text" data-testid="card-filter-text" placeholder="Filter by name, type or text…" aria-label="Filter by name, type or text"
          value={value.text} onChange={(e) => set({ text: e.target.value })} />
      )}
      <div className="cf-group" role="group" aria-label="Card type">
        {CARD_TYPES.map((t) => (
          <button key={t} type="button" className="cf-chip" aria-pressed={value.types.includes(t)} data-testid={`cf-type-${t}`}
            onClick={() => set({ types: toggle(value.types, t) })}>{t}</button>
        ))}
      </div>
      <div className="cf-group" role="group" aria-label="Mana value">
        <span className="cf-label" aria-hidden>MV</span>
        {MANA_VALUES.map((m) => (
          <button key={m} type="button" className="cf-chip cf-num" aria-pressed={value.mvs.includes(m)} data-testid={`cf-mv-${m}`}
            aria-label={m >= 7 ? "Mana value 7 or more" : `Mana value ${m}`} onClick={() => set({ mvs: toggle(value.mvs, m) })}>{m >= 7 ? "7+" : m}</button>
        ))}
      </div>
      <div className="cf-group" role="group" aria-label="Color">
        {COLORS.map((c) => (
          <button key={c} type="button" className="cf-chip cf-color" aria-pressed={value.colors.includes(c)} data-testid={`cf-color-${c}`}
            aria-label={COLOR_NAMES[c]} title={COLOR_NAMES[c]} onClick={() => set({ colors: toggle(value.colors, c) })}>
            <ManaSymbol sym={c} label={COLOR_NAMES[c]} />
          </button>
        ))}
      </div>
      <label className="cf-sort">
        <span>Sort</span>
        <select value={value.sort} data-testid="cf-sort" onChange={(e) => set({ sort: e.target.value as CardSort })}>
          {SORTS.map((s) => <option key={s.id} value={s.id}>{s.id === "order" ? orderLabel : s.label}</option>)}
        </select>
      </label>
      {(filtering(value) || value.sort !== "order") && (
        <button type="button" className="cf-clear" data-testid="cf-clear" onClick={() => onChange({ ...NO_FILTER, text: text ? "" : value.text })}>Clear</button>
      )}
    </div>
  );
}
