import { useGame } from "../state/gameStore";
import { changeLife } from "./actions";
import { LETHAL_COMMANDER, LETHAL_POISON, PlayerPanel } from "./PlayerPanel";
import "./seat.css";

/**
 * A seat's plaque: portrait, name, life and the three numbers that decide a Commander game; click for the full player
 * panel. The 3D table places it on the table by each seat; the 2D table puts it in each seat's strip by the mat, with
 * the life steppers and connection state at hand (variant "2d").
 */
export function SeatPlate({ player, me, open, onToggle, variant = "3d", drop = "up" }: {
  player: string; me: string; open: boolean; onToggle: () => void; variant?: "3d" | "2d"; drop?: "up" | "down";
}) {
  const p = useGame((s) => s.view?.players.find((x) => x.id === player));
  const active = useGame((s) => s.view?.turn.active_player === player);
  const priority = useGame((s) => s.view?.rules?.priority === player);
  const monarch = useGame((s) => s.view?.table.monarch === player);
  const seat = useGame((s) => (s.view?.game.mode === "lan" ? s.view.game.seats[player] : undefined));
  if (!p) return null;
  const flat = variant === "2d";
  // the numbers that decide a Commander game, shown only when they matter
  const cmd = Math.max(0, ...Object.values(p.commander_damage));
  const poison = p.resources.poison ?? 0;
  // the same three stats on every plaque; a zero is dimmed, not hidden
  const stats = [
    { key: "cmd", text: `Cmdr dmg ${cmd}/${LETHAL_COMMANDER}`, title: `Most damage taken from one commander: ${cmd} of ${LETHAL_COMMANDER}`, n: cmd, lethal: cmd >= LETHAL_COMMANDER },
    { key: "poison", text: `Poison ${poison}/${LETHAL_POISON}`, title: `${poison} of ${LETHAL_POISON} poison counters`, n: poison, lethal: poison >= LETHAL_POISON },
    { key: "hand", text: `Hand ${p.hand_count}`, title: `${p.hand_count} cards in hand`, n: p.hand_count, lethal: false },
  ];
  const presence = seat ? seat.presence ?? (seat.connected ? "connected" : "disconnected") : null;
  return (
    <div className={`t3d-seat ${flat ? "seat-2d" : ""} ${active ? "active" : ""} ${priority ? "priority" : ""}`} style={{ ["--player-color" as string]: p.color }} data-player-id={player}>
      {(active || priority) && (
        <span className="t3d-seat-flags" aria-live="polite">
          {active && <span className="t3d-flag turn">Turn</span>}
          {priority && <span className="t3d-flag prio">Priority</span>}
        </span>
      )}
      <button className="t3d-seat-main" onClick={onToggle} data-testid={`seat-${player}`} aria-label={`${p.name}${player === me ? " (you)" : ""}: ${p.life} life. Open player panel`} aria-expanded={open}>
        <span className={`portrait ${active ? "active" : ""}`} style={{ ["--size" as string]: "46px", borderColor: p.color }}>{p.name.slice(0, 1).toUpperCase()}</span>
        <span className="t3d-seat-text">
          <span className="t3d-seat-name">{p.name}{player === me ? " (you)" : ""}{monarch ? " ♚" : ""}</span>
          <span className="t3d-seat-life" data-testid={flat ? `life-${player}` : `life3d-${player}`}>{p.life}</span>
          <span className="t3d-seat-stats">
            {stats.map((x) => <span key={x.key} className={`t3d-stat t3d-stat-${x.key} ${x.lethal ? "lethal" : x.n ? "" : "zero"}`} title={x.title}>{x.text}{x.lethal ? " · lethal" : ""}</span>)}
            {flat && presence && presence !== "connected" && <span className={`seat-presence ${presence}`} data-testid={`presence-${player}`}>{{ reconnecting: "Reconnecting…", disconnected: "Disconnected", open: "Open seat" }[presence] ?? presence}</span>}
            {flat && presence === "connected" && <span className="seat-presence connected" data-testid={`presence-${player}`}>Connected</span>}
          </span>
        </span>
      </button>
      {flat && (
        <span className="seat-steps">
          <button aria-label={`${p.name}: gain 1 life`} title="Gain 1 life" data-testid={`life-plus-${player}`} onClick={() => void changeLife(player, 1)}>+</button>
          <button aria-label={`${p.name}: lose 1 life`} title="Lose 1 life" data-testid={`life-minus-${player}`} onClick={() => void changeLife(player, -1)}>−</button>
        </span>
      )}
      {open && (
        <div className={`t3d-seat-panel frame ${drop === "down" ? "down" : ""}`}>
          <PlayerPanel player={player} me={me} />
        </div>
      )}
    </div>
  );
}
