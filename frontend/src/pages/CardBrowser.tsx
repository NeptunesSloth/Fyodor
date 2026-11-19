import { useEffect, useState } from "react";
import { CardDetails } from "../cards/CardDetails";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { useDebounced } from "../hooks/useDebounced";
import { type CardCoverage, getCard, getCoverage, getPrintings, searchCards } from "../services/cards";
import { useCardCache } from "../state/cardCache";
import type { CardData } from "../types/cards";
import "./cards.css";

/** Searches to try, one click each (the search syntax by example). */
const EXAMPLES = ["sol ring", "t:creature c:g mv<=2", 'o:"draw a card"', "is:commander id:rg", "s:cmm"];

export function CardBrowser() {
  const [query, setQuery] = useState("");
  const [tokens, setTokens] = useState<"false" | "true">("false");
  const [results, setResults] = useState<CardData[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
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
        setSearched(true);
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

  const what = tokens === "true" ? "token" : "card";
  return (
    <div className="page card-browser">
      <header className="cb-head">
        <h1>Cards</h1>
        <p>Every card Fyodor knows, for looking things up. Choose one for its rules text, tokens and printings. A mechanic Fyodor
          doesn't play yet? <a href="#/teach">Teach Fyodor</a>.</p>
      </header>
      <div className="toolbar cb-bar">
        <label className="cb-search">
          <span className="cb-sr">Search cards</span>
          <input
            className="search"
            type="search"
            autoFocus
            placeholder="Search cards…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="seg cb-seg" role="group" aria-label="Show">
          <button type="button" className={tokens === "false" ? "on" : ""} aria-pressed={tokens === "false"} onClick={() => setTokens("false")}>Cards</button>
          <button type="button" className={tokens === "true" ? "on" : ""} aria-pressed={tokens === "true"} onClick={() => setTokens("true")}>Tokens</button>
        </div>
      </div>
      <p className="cb-help">
        <span>Try</span>
        {EXAMPLES.map((q) => (
          <button key={q} type="button" className="cb-eg" onClick={() => setQuery(q)}>{q}</button>
        ))}
      </p>
      {error && (
        <div className="cb-empty" role="alert">
          <span className="cb-empty-card" aria-hidden />
          <p className="cb-empty-title">That search didn't work.</p>
          <p className="error">{error}</p>
        </div>
      )}
      {!error && searched && results.length > 0 && (
        <p className="cb-count" aria-live="polite">{results.length}{hasMore ? "+" : ""} {what}{results.length === 1 && !hasMore ? "" : "s"}{query.trim() ? ` for “${query.trim()}”` : ""}</p>
      )}
      <div className="card-grid">
        {results.map((c) => (
          <button key={c.id} className="grid-card" onClick={() => setSelected(c.id)} title={c.name}>
            <CardFace card={c} size="normal" />
          </button>
        ))}
      </div>
      {hasMore && <button className="tt-btn cb-more" onClick={loadMore}>Load more</button>}
      {!error && searched && results.length === 0 && (
        <div className="cb-empty">
          <span className="cb-empty-card" aria-hidden />
          <p className="cb-empty-title">No {what}s match{query.trim() ? ` “${query.trim()}”` : ""}.</p>
          <p>Check the spelling, or search by part of a name. Filters: <code>t:</code> type, <code>c:</code> colour, <code>mv:</code> mana value, <code>o:</code> rules text, <code>id:</code> colour identity, <code>s:</code> set.</p>
        </div>
      )}
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
            <CoverageLine id={card.id} />
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

const COVERAGE_WORD: Record<CardCoverage["level"], string> = { FULL: "Full", PARTIAL: "Partial", REVIEW: "Review", MANUAL: "Manual" };

/** The card's rules automation: FULL / PARTIAL (and what is played by hand) / REVIEW / MANUAL. */
function CoverageLine({ id }: { id: string }) {
  const [cov, setCov] = useState<CardCoverage | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    setCov(undefined);
    getCoverage(id).then((c) => live && setCov(c), () => live && setCov(null));
    return () => { live = false; };
  }, [id]);
  if (!cov) return null;
  const manual = cov.manual_parts;
  const why = cov.level === "FULL" ? "Fyodor plays every part of it by itself."
    : cov.level === "REVIEW" ? "Its Oracle text changed since its rules were checked: play it by hand until a new Fyodor checks it again."
    : cov.level === "PARTIAL" ? `Played by hand: ${manual.join("; ")}.`
    : manual.length ? `Played by hand: ${manual.join("; ")}.` : "Played by hand.";
  return (
    <div className={`cov-line ${cov.level.toLowerCase()}`} data-testid="card-coverage">
      <h4>Rules automation</h4>
      <p><b className="cov-level"><i aria-hidden />{COVERAGE_WORD[cov.level]}</b> {why}</p>
    </div>
  );
}
