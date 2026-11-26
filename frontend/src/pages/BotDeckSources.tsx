import { useEffect, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { toastError } from "../components/Toasts";
import { listPrecons, type Precon } from "../services/decks";
import { BOT_DECK_GENERATED, BOT_DECK_RANDOM, preconDeck } from "../game/botSeat";
import "./botDeckSources.css";

/**
 * -- bot decks -- a bot's deck without one of your decks: one of yours at random, a preconstructed Commander deck (the app's bundled
 * lists; one at random or a chosen one), or a deck generated for a random commander (the server's app/decks/bot_decks.py; nothing is
 * saved to your library). ``onPick`` gets the source's deck id and, for a chosen precon, its name.
 */
export function BotDeckSources({ value, hasLibrary, busy, onPick }: {
  value: string | null;
  hasLibrary: boolean;
  busy?: boolean;
  onPick: (deckId: string, label?: string) => void;
}) {
  const [precons, setPrecons] = useState<Precon[] | null>(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!open || precons) return;
    listPrecons().then(setPrecons, (e) => { toastError(e); setPrecons([]); });
  }, [open, precons]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const all = precons ?? [];
    const found = needle ? all.filter((p) => p.name.toLowerCase().includes(needle) || p.set.toLowerCase().includes(needle)
      || p.commanders.some((c) => c.toLowerCase().includes(needle))) : all;
    return found.slice(0, 80);
  }, [precons, q]);
  const choice = (id: string, icon: "bot" | "cards" | "gem", title: string, sub: string, disabled = false, testid = "") => (
    <button className={`bds-choice ${value === id ? "on" : ""}`} aria-pressed={value === id} disabled={busy || disabled}
      onClick={() => onPick(id)} data-testid={testid}>
      <Icon name={icon} size={18} />
      <span className="bds-text"><b>{title}</b><span>{sub}</span></span>
    </button>
  );
  const preconOn = !!value && value.startsWith("@precon:");
  return (
    <div className="bot-deck-sources" data-testid="bot-deck-sources">
      <p className="bds-head">Random, precon or generated</p>
      <div className="bds-row">
        {choice(BOT_DECK_RANDOM, "bot", "Random from my decks", hasLibrary ? "One of your decks, picked at random" : "Your library is empty",
          !hasLibrary, "bot-deck-random")}
        <button className={`bds-choice ${open || preconOn ? "on" : ""}`} aria-expanded={open} disabled={busy} onClick={() => setOpen((o) => !o)}
          data-testid="bot-deck-precons">
          <Icon name="cards" size={18} />
          <span className="bds-text"><b>Preconstructed…</b><span>A Commander precon, ready to play</span></span>
        </button>
        {choice(BOT_DECK_GENERATED, "gem", "Generated for a random commander", "100 cards: lands, ramp, removal, creatures", false,
          "bot-deck-generated")}
      </div>
      {open && (
        <div className="bds-precons">
          <div className="bds-precon-bar">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a precon, set or commander"
              aria-label="Find a precon, set or commander" autoFocus />
            <button className="tt-btn" disabled={busy} onClick={() => onPick(preconDeck())} data-testid="bot-deck-precon-random">
              Random precon
            </button>
          </div>
          {precons === null && <p className="hint">Loading the precons…</p>}
          {precons?.length === 0 && <p className="hint">No precons are bundled with this app.</p>}
          <ul className="bds-precon-list">
            {shown.map((p) => {
              const id = preconDeck(p.id);
              return (
                <li key={p.id}>
                  <button className={`bds-precon ${value === id ? "on" : ""}`} aria-pressed={value === id} disabled={busy}
                    onClick={() => onPick(id, p.name)}>
                    <b>{p.name}</b>
                    <span className="hint">{p.commanders.join(" & ")}</span>
                    <span className="bds-set">{p.set} · {p.released.slice(0, 4)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {precons && shown.length === 80 && <p className="hint">Showing 80: search to narrow.</p>}
        </div>
      )}
    </div>
  );
}
