import { usePlayer } from "../state/gameStore";
import { Battlefield } from "./Battlefield";
import { Hand } from "./Hand";
import { PlayerPanel } from "./PlayerPanel";
import { CommandZone, LibraryPile, Pile } from "./ZonePile";

/**
 * One player's side of the table. `mine` areas sit at the bottom with the hand below;
 * opponents' areas are mirrored so their lands face them, like a real table.
 */
export function PlayerArea({ player, me, mine, compact }: { player: string; me: string; mine: boolean; compact?: boolean }) {
  const p = usePlayer(player);
  if (!p) return null;
  return (
    <section className={`player-area ${mine ? "mine" : "opponent"} ${compact ? "compact" : ""}`} style={{ ["--player-color" as string]: p.color }}>
      {!mine && <Hand player={player} me={me} compact />}
      <div className="area-row">
        <aside className="area-side">
          <PlayerPanel player={player} me={me} compact={compact} />
          <div className="piles">
            <LibraryPile player={player} me={me} name={p.name} />
            <Pile player={player} zone="graveyard" />
            <Pile player={player} zone="exile" />
          </div>
          <CommandZone player={player} me={me} />
        </aside>
        <Battlefield player={player} me={me} mirrored={!mine} color={p.color} />
      </div>
    </section>
  );
}
