import { useEffect, useMemo, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import type { DeckSummary } from "../types/decks";
import { CommanderArt } from "./CommanderArt";
import { deckSize, deckTitle } from "./playBits";

export { deckSize, deckTitle };

/**
 * Choose a seat's deck from the library by its commander: each deck shows its commander's art, the commander and the deck's
 * name, its colours and size, and whose seat already has it. "No deck" leaves the seat with an empty library.
 */
export function DeckPicker({ decks, value, seat, usedBy, onPick, onClose }: {
  decks: DeckSummary[];
  value: string | null;
  seat: string;
  /** deck id → the other seats' names that already use it */
  usedBy: Map<string, string[]>;
  onPick: (deckId: string | null) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  // focus moves into the picker (the search box, else this seat's deck or the first one) and back to the seat on close
  const root = useRef<HTMLDivElement>(null);
  const [opener] = useState(() => (document.activeElement instanceof HTMLElement ? document.activeElement : null)); // before autofocus moves it
  useEffect(() => {
    const el = root.current;
    if (el && !el.contains(document.activeElement)) el.querySelector<HTMLElement>(".dp-deck.on, .dp-deck")?.focus();
    return () => opener?.focus();
  }, [opener]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return decks;
    return decks.filter((d) => d.name.toLowerCase().includes(needle) || d.commanders.some((c) => c.toLowerCase().includes(needle)));
  }, [decks, q]);
  return (
    <Modal wide title={`Choose a deck for ${seat}`} onClose={onClose}
      footer={<><a className="dp-library" href="#/decks"><Icon name="cards" size={15} />Import or edit decks in the Deck library</a><span className="spacer" /><button className="tt-btn" onClick={onClose}>Cancel</button></>}>
      <div className="deck-picker" ref={root}>
        {decks.length > 5 && (
          <input type="search" className="dp-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a deck or a commander"
            aria-label="Find a deck or a commander" autoFocus />
        )}
        {decks.length === 0 && <p className="dp-none-yet">Your deck library is empty. Import a list or an Archidekt link in the Deck library, or play this seat with an empty library.</p>}
        <ul className="dp-grid">
          {shown.map((d) => {
            const on = d.id === value;
            const others = usedBy.get(d.id);
            return (
              <li key={d.id}>
                <button className={`dp-deck ${on ? "on" : ""}`} aria-pressed={on} onClick={() => onPick(d.id)} data-testid={`pick-deck-${d.id}`}>
                  <span className="dp-art">{d.commanders.length && d.cover_id ? <CommanderArt id={d.cover_id} /> : <CommanderArt back />}</span>
                  <span className="dp-text">
                    <span className="dp-cmdr">{deckTitle(d)}</span>
                    <span className="dp-sub">
                      {d.commanders.length > 0 && <span className="dp-name">{d.name}</span>}
                      <ColorPips colors={d.color_identity} />
                    </span>
                    <span className="dp-facts">
                      <span>{deckSize(d)} cards</span>
                      {d.unresolved > 0 && <span className="dp-warn">{d.unresolved} not found</span>}
                      {on ? <span className="dp-here"><Icon name="check" size={13} />This seat</span>
                        : others ? <span>Also at {others.join(", ")}'s seat</span> : null}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
          {!q && (
            <li>
              <button className={`dp-deck dp-empty ${value === null ? "on" : ""}`} aria-pressed={value === null} onClick={() => onPick(null)}>
                <span className="dp-art"><CommanderArt back /></span>
                <span className="dp-text">
                  <span className="dp-cmdr">No deck</span>
                  <span className="dp-facts"><span>An empty library: bring cards in by hand</span></span>
                </span>
              </button>
            </li>
          )}
        </ul>
        {q && shown.length === 0 && <p className="dp-none-yet">No deck or commander matches “{q}”.</p>}
      </div>
    </Modal>
  );
}
