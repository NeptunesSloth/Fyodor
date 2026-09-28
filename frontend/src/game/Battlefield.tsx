import { playmatStyle, usePlaymat } from "./appearance";
import { useEffect, useRef, useState } from "react";
import { useDrag } from "./dnd";
import { useGame, useZoneIds } from "../state/gameStore";
import { battlefieldCardWidth, BF_H, BF_W, CARD_RATIO, toPixels } from "./geometry";
import { TableCard } from "./TableCard";

interface Props {
  player: string;
  me: string;
  mirrored: boolean;
  color: string;
}

/** A player's free-form battlefield. Positions are virtual units scaled to the element size. */
export function Battlefield({ player, me, mirrored, color }: Props) {
  const playmat = usePlaymat(player);
  const key = `${player}:battlefield`;
  const ids = useZoneIds(key) ?? [];
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 300 });
  const pending = useGame((s) => s.pendingPositions);
  const cards = useGame((s) => s.view?.cards);
  const over = useDrag((s) => s.drag?.overZone === key);
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const cardW = battlefieldCardWidth(size.w, size.h);
  const cardH = cardW * CARD_RATIO;

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || e.target !== e.currentTarget) return;
    const rect = ref.current!.getBoundingClientRect();
    const x0 = e.clientX - rect.left;
    const y0 = e.clientY - rect.top;
    if (!e.shiftKey) useGame.getState().clearSelection();
    let current = { x0, y0, x1: x0, y1: y0 };
    const move = (ev: PointerEvent) => {
      current = { x0, y0, x1: ev.clientX - rect.left, y1: ev.clientY - rect.top };
      setMarquee(current);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setMarquee(null);
      const minX = Math.min(current.x0, current.x1);
      const maxX = Math.max(current.x0, current.x1);
      const minY = Math.min(current.y0, current.y1);
      const maxY = Math.max(current.y0, current.y1);
      if (maxX - minX < 4 && maxY - minY < 4) return;
      const hit = ids.filter((id) => {
        const c = cards?.[id];
        if (!c || c.x == null || c.y == null) return false;
        const [px, py] = toPixels(c.x, c.y, size.w, size.h, cardH, mirrored);
        return px < maxX && px + cardW > minX && py < maxY && py + cardH > minY;
      });
      useGame.getState().select(hit, e.shiftKey ? "add" : "replace");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div
      ref={ref}
      className={`battlefield ${mirrored ? "mirrored" : ""} ${over ? "drop-over" : ""}`}
      style={{ ["--player-color" as string]: color }}
      data-drop={key}
      data-battlefield=""
      data-cardh={cardH}
      {...(mirrored ? { "data-mirrored": "" } : {})}
      onPointerDown={onPointerDown}
    >
      {playmat.url && (
        <div className={`playmat-layer ${playmat.mat?.show_zones ? "" : "bare"}`} style={playmatStyle(playmat.mat, playmat.url)} aria-hidden />
      )}
      {ids.map((id, i) => {
        const c = cards?.[id];
        if (!c) return null;
        const [vx, vy] = pending[id] ?? [c.x ?? 0, c.y ?? 0];
        const [left, top] = toPixels(Math.max(-40, Math.min(BF_W, vx)), Math.max(-40, Math.min(BF_H, vy)), size.w, size.h, cardH, mirrored);
        return <TableCard key={id} id={id} left={left} top={top} width={cardW} me={me} z={i + 1} />;
      })}
      {marquee && (
        <div
          className="marquee"
          style={{
            left: Math.min(marquee.x0, marquee.x1),
            top: Math.min(marquee.y0, marquee.y1),
            width: Math.abs(marquee.x1 - marquee.x0),
            height: Math.abs(marquee.y1 - marquee.y0),
          }}
        />
      )}
    </div>
  );
}
