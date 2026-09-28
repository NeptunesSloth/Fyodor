import { useEffect, useState } from "react";
import { CardDetails } from "../cards/CardDetails";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { useDebounced } from "../hooks/useDebounced";
import { getCard, getPrintings, searchCards } from "../services/cards";
import { useCardCache } from "../state/cardCache";
import type { CardData } from "../types/cards";

const HELP = "Try: sol ring · t:creature c:g mv<=2 · o:\"draw a card\" · is:commander id:rg · s:cmm";

export function CardBrowser() {
  const [query, setQuery] = useState("");
  const [tokens, setTokens] = useState<"false" | "true">("false");
  const [results, setResults] = useState<CardData[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const debounced = useDebounced(query, 180);

  useEffect(() => {
    let cancelled = false;
    searchCards(debounced, { tokens, limit: 90 }).then(
      (res) => {
        if (cancelled) return;
        useCardCache.getState().put(res.results);
        setResults(res.results);
        setHasMore(res.has_more);
        setError(null);
      },
      (e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [debounced, tokens]);

  const loadMore = () =>
    searchCards(debounced, { tokens, limit: 90, offset: results.length }).then((res) => {
      useCardCache.getState().put(res.results);
      setResults((r) => [...r, ...res.results]);
      setHasMore(res.has_more);
    });

  return (
    <div className="page card-browser">
      <div className="toolbar">
        <input
          className="search"
          autoFocus
          placeholder="Search cards…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="seg">
          <button className={tokens === "false" ? "on" : ""} onClick={() => setTokens("false")}>Cards</button>
          <button className={tokens === "true" ? "on" : ""} onClick={() => setTokens("true")}>Tokens</button>
        </div>
      </div>
      <p className="hint">{HELP}</p>
      {error && <p className="error">{error}</p>}
      <div className="card-grid">
        {results.map((c) => (
          <button key={c.id} className="grid-card" onClick={() => setSelected(c.id)} title={c.name}>
            <CardFace card={c} size="normal" />
          </button>
        ))}
      </div>
      {hasMore && <button className="btn more" onClick={loadMore}>Load more</button>}
      {!error && results.length === 0 && <p className="hint">No cards match.</p>}
      {selected && <CardModal id={selected} onClose={() => setSelected(null)} onSelect={setSelected} />}
    </div>
  );
}

export function CardModal({ id, onClose, onSelect }: { id: string; onClose: () => void; onSelect?: (id: string) => void }) {
  const [card, setCard] = useState<CardData | null>(null);
  const [printings, setPrintings] = useState<CardData[]>([]);
  const [face, setFace] = useState(0);
  useEffect(() => {
    setFace(0);
    getCard(id).then(setCard, () => setCard(null));
    getPrintings(id).then(setPrintings, () => setPrintings([]));
  }, [id]);
  if (!card) return null;
  return (
    <Modal title={card.name} onClose={onClose} wide>
      <CardDetails
        card={card}
        face={face}
        extra={
          <>
            {card.double_faced && (
              <button className="btn" onClick={() => setFace((f) => (f + 1) % card.image_faces)}>Turn over</button>
            )}
            {card.related_tokens && card.related_tokens.length > 0 && (
              <div className="related">
                <h4>Creates</h4>
                {card.related_tokens.map((t) => (
                  <button key={t.id} className="chip" onClick={() => onSelect?.(t.id)}>{t.name}</button>
                ))}
              </div>
            )}
            {printings.length > 1 && (
              <div className="printings">
                <h4>Printings ({printings.length})</h4>
                <div className="printing-list">
                  {printings.map((p) => (
                    <button key={p.id} className={`chip ${p.id === card.id ? "on" : ""}`} onClick={() => onSelect?.(p.id)}>
                      {p.set_code.toUpperCase()} #{p.collector_number}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        }
      />
    </Modal>
  );
}
