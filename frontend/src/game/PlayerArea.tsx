import { useState } from "react";
import { useGame, usePlayer } from "../state/gameStore";
import { Battlefield } from "./Battlefield";
import { Hand } from "./Hand";
import { SeatButtons } from "./SeatButtons";
import { SeatPlate } from "./SeatPlate";
import { CommandZone, LibraryPile, Pile } from "./ZonePile";

/**
 * One player's side of the 2D table: the mat, and the seat's plaque and zones at its edge (as on the 3D table and a
 * real playmat). An opponent's plaque, piles, command zone and hand sit in one strip along their edge, so their mat
 * gets the full width of the seat; mine sit in a slim rail beside my mat. Opponents' mats are mirrored so their lands
 * face them, like a real table.
 */
export function PlayerArea({ player, me, mine, compact, focused }: { player: string; me: string; mine: boolean; compact?: boolean; focused?: boolean }) {
  const p = usePlayer(player);
  const [open, setOpen] = useState(false);
  if (!p) return null;
  const plaque = <SeatPlate player={player} me={me} open={open} onToggle={() => setOpen((o) => !o)} variant="2d" drop={mine ? "up" : "down"} />;
  const zones = (
    <div className="zone-rail">
      <LibraryPile player={player} me={me} name={p.name} />
      <Pile player={player} zone="graveyard" />
      <Pile player={player} zone="exile" />
      <CommandZone player={player} me={me} />
    </div>
  );
  const cls = `player-area ${mine ? "mine" : "opponent"} ${compact ? "compact" : ""} ${focused ? "focused" : ""}`;
  if (mine) {
    return (
      <section className={cls} style={{ ["--player-color" as string]: p.color }}>
        <div className="area-row">
          <aside className="area-side">
            {plaque}
            {zones}
            <SeatButtons />
          </aside>
          <Battlefield player={player} me={me} mirrored={false} color={p.color} />
        </div>
      </section>
    );
  }
  return (
    <section className={cls} style={{ ["--player-color" as string]: p.color }}>
      <div className="seat-strip">
        {plaque}
        {zones}
        <Hand player={player} me={me} compact />
        <FocusButton player={player} focused={!!focused} />
      </div>
      <Battlefield player={player} me={me} mirrored color={p.color} />
    </section>
  );
}

/** "Look at Bob's board": the 2D table's camera move (keys 2–6, as on the 3D table; 1 or Esc to come back). */
function FocusButton({ player, focused }: { player: string; focused: boolean }) {
  const name = useGame((s) => s.view?.players.find((x) => x.id === player)?.name ?? "");
  return (
    <button className="tt-btn ghost seat-look" data-testid={`look-${player}`} aria-pressed={focused}
      title={focused ? "Back to the whole table (1)" : `Look closely at ${name}'s board`}
      onClick={() => useGame.getState().setLayout({ focus: focused ? null : player })}>
      {focused ? "Whole table" : "Look"}
    </button>
  );
}
