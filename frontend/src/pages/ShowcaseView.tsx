import { useEffect, useRef } from "react";
import { listDecks } from "../services/decks";
import { plane, type PlaneId } from "../theme/planes";
import { Showcase, type ShowcaseCard } from "../table3d/Showcase";

export default function ShowcaseView({ planeId }: { planeId: PlaneId }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<Showcase | null>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const s = new Showcase(el, plane(planeId));
    scene.current = s;
    const ro = new ResizeObserver(() => s.resize(el.clientWidth, el.clientHeight));
    ro.observe(el);
    s.resize(el.clientWidth, el.clientHeight);
    // the pod's latest commanders on the mat (the deck library lives on the host: elsewhere the mat shows none)
    let live = true;
    listDecks().then((decks) => {
      if (!live) return;
      const seen = new Set<string>();
      const cards: ShowcaseCard[] = [];
      for (const d of [...decks].sort((a, b) => b.updated_at.localeCompare(a.updated_at))) {
        if (!d.cover_id || seen.has(d.cover_id)) continue;
        seen.add(d.cover_id);
        cards.push({ id: d.cover_id, name: d.commanders[0] ?? d.name });
      }
      s.setCards(cards);
    }, () => undefined);
    return () => {
      live = false;
      ro.disconnect();
      s.dispose();
      scene.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => scene.current?.setPlane(plane(planeId)), [planeId]);
  return <div className="home-showcase" ref={host} aria-hidden />;
}
