import { useEffect, useRef, useState } from "react";
import { useDebounced } from "../hooks/useDebounced";
import { searchCards } from "../services/cards";
import { useCardCache } from "../state/cardCache";
import type { CardData } from "../types/cards";
import { ManaText } from "../cards/ManaText";

interface Props {
  placeholder?: string;
  tokens?: "true" | "false" | "any";
  onPick: (card: CardData, e: { shiftKey: boolean }) => void;
  onHover?: (card: CardData | null) => void;
  autoFocus?: boolean;
}

/** Search-as-you-type field with a keyboard-navigable result dropdown. */
export function CardSearchBox({ placeholder = "Add a card…", tokens = "false", onPick, onHover, autoFocus }: Props) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<CardData[]>([]);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(q, 150);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!debounced.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    searchCards(debounced, { tokens, limit: 12 }).then((r) => {
      if (cancelled) return;
      useCardCache.getState().put(r.results);
      setResults(r.results);
      setActive(0);
      setOpen(true);
    }, () => undefined);
    return () => {
      cancelled = true;
    };
  }, [debounced, tokens]);

  useEffect(() => {
    const close = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, []);

  const pick = (card: CardData, shiftKey: boolean) => {
    onPick(card, { shiftKey });
    setQ("");
    setResults([]);
    setOpen(false);
  };

  return (
    <div className="search-box" ref={box}>
      <input
        value={q}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(results.length - 1, a + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(0, a - 1));
          } else if (e.key === "Enter" && results[active]) {
            e.preventDefault();
            pick(results[active]!, e.shiftKey);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && results.length > 0 && (
        <ul className="search-results">
          {results.map((c, i) => (
            <li
              key={c.id}
              className={i === active ? "active" : ""}
              onPointerEnter={() => {
                setActive(i);
                onHover?.(c);
              }}
              onPointerDown={(e) => {
                e.preventDefault();
                pick(c, e.shiftKey);
              }}
            >
              <span className="name">{c.name}</span>
              <span className="cost"><ManaText text={c.mana_cost} /></span>
              <span className="type hint">{c.type_line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
