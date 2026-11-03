import type { DeckChange, DeckComparison } from "./deckCompare";
import { SECTION_LABEL } from "../types/decks";

/**
 * Deck Lab's compare view: the cards the next-game version brings in and takes out, against the deck brought to this game,
 * with the deck's size before and after. A section other than the deck itself is named after the card.
 */
export function DeckChanges({ cmp }: { cmp: DeckComparison }) {
  const same = !cmp.added.length && !cmp.removed.length;
  const count = (xs: DeckChange[]) => xs.reduce((n, c) => n + c.n, 0);
  return (
    <div className="deck-compare" data-testid="deck-compare">
      <p className="hint">
        Against the deck you brought to this game · {cmp.before === cmp.after ? `${cmp.after} cards` : `${cmp.before} → ${cmp.after} cards`}
      </p>
      {same ? (
        <p className="deck-compare-same">No changes yet: this is the deck you brought.</p>
      ) : (
        <div className="deck-compare-cols">
          <Column title="In" sign="+" changes={cmp.added} total={count(cmp.added)} />
          <Column title="Out" sign="−" changes={cmp.removed} total={count(cmp.removed)} />
        </div>
      )}
    </div>
  );
}

function Column({ title, sign, changes, total }: { title: string; sign: string; changes: DeckChange[]; total: number }) {
  return (
    <section className={`deck-compare-col ${sign === "+" ? "in" : "out"}`} aria-label={`${title}: ${total}`}>
      <h4>{title} <span className="deck-compare-total">{total ? `${sign}${total}` : "none"}</span></h4>
      <ul>
        {changes.map((c) => (
          <li key={`${c.section}|${c.name}`}>
            <span className="deck-compare-n">{sign}{c.n}</span>
            <span className="deck-compare-name">{c.name}</span>
            {c.section !== "main" && <span className="deck-compare-sec">{SECTION_LABEL[c.section]}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
