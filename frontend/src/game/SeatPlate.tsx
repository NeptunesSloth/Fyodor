import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useGame } from "../state/gameStore";
import { changeLife, changeResource, send } from "./actions";
import { LETHAL_COMMANDER, LETHAL_POISON, PlayerPanel } from "./PlayerPanel";
import "./seat.css";

/**
 * Taps on a counter gathered into one change: three quick clicks send "−3" once (one log line, one undo step),
 * and the counter shows the change it is about to make while you click.
 */
function useBatched(commit: (delta: number) => void, wait = 650): [number, (d: number) => void] {
  const [pending, setPending] = useState(0);
  const sum = useRef(0);
  const timer = useRef(0);
  const latest = useRef(commit);
  latest.current = commit;
  useEffect(() => () => {
    window.clearTimeout(timer.current);
    if (sum.current) latest.current(sum.current); // leaving mid-count still counts
  }, []);
  const bump = (d: number) => {
    sum.current += d;
    setPending(sum.current);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const total = sum.current;
      sum.current = 0;
      setPending(0);
      if (total) latest.current(total);
    }, wait);
  };
  return [pending, bump];
}

/** Click +1, right-click −1, the wheel, or ↑/↓ and +/− on the keyboard: a counter you use on the table, not in a menu. */
function counterHandlers(bump: (d: number) => void) {
  return {
    onClick: (e: React.MouseEvent) => { e.stopPropagation(); bump(e.shiftKey ? 5 : 1); },
    onContextMenu: (e: React.MouseEvent) => { e.preventDefault(); e.stopPropagation(); bump(e.shiftKey ? -5 : -1); },
    onWheel: (e: React.WheelEvent) => { e.stopPropagation(); bump(e.deltaY < 0 ? 1 : -1); },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "ArrowUp" || e.key === "+" || e.key === "=") { e.preventDefault(); e.stopPropagation(); bump(1); }
      if (e.key === "ArrowDown" || e.key === "-") { e.preventDefault(); e.stopPropagation(); bump(-1); }
    },
    onPointerDown: (e: React.PointerEvent) => e.stopPropagation(),
  };
}

const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`);

/** The scripted tables' heart: the life total itself is the control. */
function LifeHeart({ player, name, life, testId }: { player: string; name: string; life: number; testId: string }) {
  const [pending, bump] = useBatched((d) => void changeLife(player, d));
  // the Oops heart: its left half (▼) takes life away, its right half (▲) gives it; right-click for 5
  const half = (e: React.MouseEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    return e.clientX < r.left + r.width / 2 ? -1 : 1;
  };
  const keys = counterHandlers(bump);
  return (
    <button className={`seat-heart ${life + pending <= 0 ? "dead" : ""}`} data-testid={`heart-${player}`}
      aria-label={`${name}: ${life + pending} life. Click the left half to lose 1 or the right half to gain 1 (right-click: 5)`}
      title="Life: click ▼ −1 or ▲ +1, right-click for 5, the wheel, or ↑/↓"
      onClick={(e) => { e.stopPropagation(); bump(half(e) * (e.shiftKey ? 5 : 1)); }}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); bump(half(e) * 5); }}
      onWheel={keys.onWheel} onKeyDown={keys.onKeyDown} onPointerDown={keys.onPointerDown}>
      <svg viewBox="0 0 64 58" aria-hidden className="seat-heart-shape">
        <path d="M32 55 C14 42 3 31 3 18 C3 9 10 3 18 3 C24 3 29 6 32 11 C35 6 40 3 46 3 C54 3 61 9 61 18 C61 31 50 42 32 55 Z" />
        <path className="seat-heart-tri" d="M9 22h6l-3 4z M49 26h6l-3-4z" />
      </svg>
      <span className="seat-heart-n" data-testid={testId}>{life + pending}</span>
      {pending !== 0 && <span className={`seat-pending ${pending > 0 ? "up" : "down"}`} aria-hidden>{sign(pending)}</span>}
    </button>
  );
}

/** One small counter beside the heart (commander damage from one commander, or poison). */
function Tracker({ value, lethal, label, title, color, glyph, onChange, testId }: {
  value: number; lethal: number; label: string; title: string; color?: string; glyph: string; onChange: (d: number) => void; testId: string;
}) {
  const [pending, bump] = useBatched(onChange);
  const n = Math.max(0, value + pending);
  return (
    <button className={`seat-track ${n >= lethal ? "lethal" : n ? "" : "zero"}`} data-testid={testId}
      style={color ? { ["--track" as string]: color } : undefined}
      aria-label={`${label}: ${n} of ${lethal}. Click to add 1, right-click to remove 1`} title={`${title} — click +1, right-click −1`}
      {...counterHandlers(bump)}>
      <span className="seat-track-glyph" aria-hidden>{glyph}</span>
      <span className="seat-track-n">{n}</span>
    </button>
  );
}

/**
 * A seat's plaque, after the scripted Tabletop Simulator tables: the portrait and name (click for the full player
 * panel), then the life heart and the trackers you click directly, as on the Oops table: commander damage from
 * each opposing commander (in its owner's colour), poison, and the hand count. The 3D table places it in the aisle
 * by each seat; the 2D table puts it in each seat's strip (variant "2d", with life steppers and connection state).
 */
export function SeatPlate({ player, me, open, onToggle, variant = "3d", drop = "up" }: {
  player: string; me: string; open: boolean; onToggle: () => void; variant?: "3d" | "2d"; drop?: "up" | "down";
}) {
  const p = useGame((s) => s.view?.players.find((x) => x.id === player));
  const players = useGame((s) => s.view?.players); // the stable list (a filtered copy here would re-render forever)
  const active = useGame((s) => s.view?.turn.active_player === player);
  const priority = useGame((s) => s.view?.rules?.priority === player);
  const monarch = useGame((s) => s.view?.table.monarch === player);
  const seat = useGame((s) => (s.view?.game.mode === "lan" ? s.view.game.seats[player] : undefined));
  const plate = useRef<HTMLDivElement>(null);
  if (!p) return null;
  const flat = variant === "2d";
  const poison = p.resources.poison ?? 0;
  const sources = (players ?? []).filter((o) => o.id !== player).flatMap((o) => o.commanders.map((c) => ({ ...c, owner: o })));
  const presence = seat ? seat.presence ?? (seat.connected ? "connected" : "disconnected") : null;
  return (
    <div ref={plate} className={`t3d-seat ${flat ? "seat-2d" : ""} ${active ? "active" : ""} ${priority ? "priority" : ""}`} style={{ ["--player-color" as string]: p.color }} data-player-id={player}>
      {(active || priority) && (
        <span className="t3d-seat-flags" aria-live="polite">
          {active && <span className="t3d-flag turn">Turn</span>}
          {priority && <span className="t3d-flag prio">Priority</span>}
        </span>
      )}
      <div className="t3d-seat-main">
        <button className="seat-who" onClick={onToggle} data-testid={`seat-${player}`} aria-label={`${p.name}${player === me ? " (you)" : ""}: ${p.life} life. Open player panel`} aria-expanded={open}>
          <span className={`portrait ${active ? "active" : ""}`} style={{ ["--size" as string]: "34px", borderColor: p.color }}>{p.name.slice(0, 1).toUpperCase()}</span>
          <span className="t3d-seat-name">{p.name}{player === me ? " (you)" : ""}{monarch ? " ♚" : ""}</span>
        </button>
        {/* on the 3D table the life heart floats over the seat itself (table3d/seatProps.ts) */}
        {flat && <LifeHeart player={player} name={p.name} life={p.life} testId={`life-${player}`} />}
        <span className="seat-trackers">
          {sources.map((c) => (
            <Tracker key={c.key} value={p.commander_damage[c.key] ?? 0} lethal={LETHAL_COMMANDER} color={c.owner.color} glyph={c.owner.name.slice(0, 1).toUpperCase()}
              label={`Commander damage to ${p.name} from ${c.name}`} title={`Commander damage from ${c.name} (${c.owner.name}); it also changes life`}
              testId={`cmdr-${player}-${c.key}`} onChange={(d) => void send({ type: "commander_damage", player, commander: c.key, delta: d })} />
          ))}
          <Tracker value={poison} lethal={LETHAL_POISON} glyph="☠" label={`${p.name}'s poison counters`} title="Poison counters" testId={`poison-${player}`}
            onChange={(d) => void changeResource(player, "poison", d)} />
          <span className="seat-hand" title={`${p.hand_count} cards in hand`} aria-label={`${p.hand_count} cards in hand`}>
            <span aria-hidden>▯</span>{p.hand_count}
          </span>
          {flat && presence && presence !== "connected" && <span className={`seat-presence ${presence}`} data-testid={`presence-${player}`}>{{ reconnecting: "Reconnecting…", disconnected: "Disconnected", open: "Open seat" }[presence] ?? presence}</span>}
          {flat && presence === "connected" && <span className="seat-presence connected" data-testid={`presence-${player}`}>Connected</span>}
        </span>
      </div>
      {flat && <span className="seat-steps">
        <button aria-label={`${p.name}: gain 1 life`} title="Gain 1 life" data-testid={`life-plus-${player}`} onClick={() => void changeLife(player, 1)}>+</button>
        <button aria-label={`${p.name}: lose 1 life`} title="Lose 1 life" data-testid={`life-minus-${player}`} onClick={() => void changeLife(player, -1)}>−</button>
      </span>}
      {open && !flat && (
        <div className={`t3d-seat-panel frame ${drop === "down" ? "down" : ""}`}>
          <PlayerPanel player={player} me={me} />
        </div>
      )}
      {open && flat && <FloatingPanel anchor={plate} drop={drop} color={p.color}><PlayerPanel player={player} me={me} /></FloatingPanel>}
    </div>
  );
}

/**
 * The 2D table's player panel: drawn over the whole page next to its plaque. The plaque sits in a strip or rail that
 * clips (overflow) and a drop-shadow filter (which also traps position: fixed), so a panel inside it was cut off.
 */
function FloatingPanel({ anchor, drop, color, children }: { anchor: React.RefObject<HTMLDivElement | null>; drop: "up" | "down"; color: string; children: React.ReactNode }) {
  const [box, setBox] = useState<{ left: number; top?: number; bottom?: number } | null>(null);
  useLayoutEffect(() => {
    const place = () => {
      const r = anchor.current?.getBoundingClientRect();
      if (!r) return;
      const left = Math.max(8, Math.min(r.left, window.innerWidth - 268));
      setBox(drop === "down" ? { left, top: r.bottom + 8 } : { left, bottom: window.innerHeight - r.top + 8 });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [anchor, drop]);
  if (!box) return null;
  return createPortal(
    <div className={`t3d-seat-panel frame floating ${drop === "down" ? "down" : ""}`} style={{ ...box, ["--player-color" as string]: color }} data-testid="seat-panel">{children}</div>,
    document.body,
  );
}
