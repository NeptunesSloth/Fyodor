import { useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { getPrintings, searchCards } from "../services/cards";
import { useCard, useCardCache } from "../state/cardCache";
import type { LobbySeat } from "../types/game";

/**
 * A commander framed for the lobby: the art window of the cached scan fills the frame (lobby.css crops it), and a card
 * without a scan stands whole in the frame as its readable proxy. `back` shows a face-down card (a private deck).
 */
export function CommanderArt({ id, back, className }: { id?: string | null; back?: boolean; className?: string }) {
  const card = useCard(back ? null : id);
  return (
    <span className={`cmdr-art ${className ?? ""}`} aria-hidden>
      {back ? <CardFace faceDown /> : <CardFace card={card} />}
    </span>
  );
}

/** name → printing id with art (null: none found), shared by every recap row. */
const found = new Map<string, string | null>();
const asked = new Map<string, Promise<string | null>>();

async function lookUp(name: string): Promise<string | null> {
  const res = await searchCards(`"${name}"`, { limit: 10 });
  const card = res.results.find((c) => c.name === name) ?? null;
  if (!card) return null;
  if (card.has_image) {
    useCardCache.getState().put([card]);
    return card.id;
  }
  const withArt = (await getPrintings(card.id)).find((c) => c.has_image) ?? card;
  useCardCache.getState().put([withArt]);
  return withArt.id;
}

/**
 * The printing to picture for a commander named in tonight's recap: the one a seated deck uses, else a printing from the
 * card database (one with a cached scan when there is one). Commander names in the recap are public already.
 */
export function useCommanderPrinting(name: string | null, seats: LobbySeat[]): string | null {
  const seated = useMemo(() => {
    if (!name) return null;
    for (const s of seats) {
      const i = s.deck?.commanders?.indexOf(name) ?? -1;
      if (i >= 0 && s.deck?.commander_ids?.[i]) return s.deck.commander_ids[i]!;
    }
    return null;
  }, [name, seats]);
  const [id, setId] = useState<string | null>(() => (name ? found.get(name) ?? null : null));
  useEffect(() => {
    if (!name || seated) return;
    if (found.has(name)) {
      setId(found.get(name) ?? null);
      return;
    }
    let live = true;
    let ask = asked.get(name);
    if (!ask) {
      ask = lookUp(name).catch(() => null).then((v) => {
        found.set(name, v);
        return v;
      });
      asked.set(name, ask);
    }
    void ask.then((v) => live && setId(v));
    return () => {
      live = false;
    };
  }, [name, seated]);
  return seated ?? id;
}
