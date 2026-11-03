/**
 * Small pieces the Play page and the launcher share: a seat's chip, a table's commanders as a mosaic, and when a save was made.
 */
import { contrast } from "../theme/planes";
import type { CommanderRef } from "../types/game";
import { CommanderArt } from "./CommanderArt";
import { SEAT_COLORS, mosaicGrid } from "./playBits";
import "./play.css";

export { SEAT_COLORS, whenSaved } from "./playBits";

const INK_DARK = "#15120e";
const INK_LIGHT = "#f7f0e2";

/** Dark ink on a light seat colour, light ink on a dark one. */
export function inkOn(color: string): string {
  try {
    return contrast(color, INK_DARK) >= contrast(color, INK_LIGHT) ? INK_DARK : INK_LIGHT;
  } catch {
    return INK_LIGHT;
  }
}

/** The CSS variables that paint a seat's chip: its colour, and an ink that reads on it. */
export function chipStyle(color: string | undefined): React.CSSProperties {
  const seat = color || "#8a6a3f";
  const ink = inkOn(seat);
  return {
    ["--seat" as string]: seat,
    ["--seat-ink" as string]: ink,
    ["--seat-ink-edge" as string]: ink === INK_DARK ? "0 0 2px rgba(255, 248, 235, 0.55)" : "0 1px 2px rgba(0, 0, 0, 0.75)",
  };
}

/** A seat's chip: its colour with a number or an initial, never colour alone. Decorative: the name is always written beside it. */
export function SeatChip({ color, text, className }: { color: string | undefined; text: string; className?: string }) {
  return <span className={`pg-chip ${className ?? ""}`} style={chipStyle(color)} aria-hidden>{text}</span>;
}

export interface MosaicSeat {
  name: string;
  /** an empty chair (a LAN table's unclaimed seat) */
  open?: boolean;
  color?: string | undefined;
  commanders?: CommanderRef[] | undefined;
}

/**
 * A table at a glance: each seat's commander art in a small mosaic (the seat colour along its foot), or the seat's chip on
 * the felt when its commander isn't known (a lobby, an old save). Decorative: the tile lists the players in words.
 */
export function TableMosaic({ seats, className }: { seats: MosaicSeat[]; className?: string }) {
  const shown = seats.slice(0, 6);
  const [cols, rows] = mosaicGrid(shown.length);
  // the frame is 10:7; a cell's ratio follows from the grid (the art crop needs it)
  const ratio = (10 / 7) * (rows / cols);
  return (
    <span className={`mosaic ${className ?? ""}`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }} aria-hidden>
      {shown.map((s, i) => {
        const cmdr = s.commanders?.[0];
        if (s.open) return <span key={i} className="mosaic-cell open" title={`${s.name}: open`} />;
        return (
          <span key={i} className="mosaic-cell" style={{ ...chipStyle(s.color || SEAT_COLORS[i % SEAT_COLORS.length]), ["--art-ratio" as string]: ratio }}
            title={cmdr ? `${s.name}: ${s.commanders!.map((c) => c.name).join(" & ")}` : s.name}>
            {cmdr?.card_id ? <CommanderArt id={cmdr.card_id} /> : <span className="pg-chip">{(s.name.trim()[0] ?? "?").toUpperCase()}</span>}
          </span>
        );
      })}
      {shown.length === 3 && <span className="mosaic-cell blank" />}
    </span>
  );
}
