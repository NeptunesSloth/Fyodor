import { useEffect, useState } from "react";
import { useGame } from "../state/gameStore";
import type { GameClock } from "../types/game";
import { formatClock, remainingNow } from "./turnClock";

/** The chip's spoken label: the state in words, never colour alone. */
export function chipLabel(name: string, bank: number, buffer: number, running: boolean, away: boolean): string {
  const left = `${name}'s clock: ${formatClock(bank)} left`;
  if (away && !running) return `${left}, paused, reconnecting`;
  return running ? `${left}, running${buffer > 0 ? `, ${formatClock(buffer)} grace` : ""}${away ? ", away" : ""}` : left;
}

/** Re-renders once a second, and only while `active`. */
function useTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

/**
 * -- turn clock -- a seat's countdown: the bank as m:ss in tabular figures; while it runs, the grace buffer first (`0:24 · 12:31`).
 * Away with reconnect time left says "Paused — reconnecting"; away once it is spent (the reconnect grace is one budget per player
 * per game) runs and says "Away — clock running". Words, not colour; nothing flashes or pulses.
 */
export function TurnClockChip({ player }: { player: string }) {
  const clock = useGame((s) => s.view?.game.clock);
  const skew = useGame((s) => s.clockSkew);
  const name = useGame((s) => s.view?.players.find((p) => p.id === player)?.name ?? player);
  const anyRunning = !!clock?.players && Object.values(clock.players).some((x) => x.running);
  const now = useTick(anyRunning);
  return <ClockChipView clock={clock} skew={skew} name={name} player={player} now={now} />;
}

/** The chip drawn from the clock block, the skew and "now" (pure: the connected chip above feeds it). */
export function ClockChipView({ clock, skew, name, player, now }: { clock: GameClock | undefined; skew: number | null; name: string; player: string; now: number }) {
  const e = clock?.settings.on ? clock.players?.[player] : undefined;
  if (!clock || !e) return null;
  const left = remainingNow(e, clock.sent_at, skew ?? 0, now);
  const live = e.running;
  return (
    <span className={`turn-clock ${live ? "running" : ""} ${e.away ? "away" : ""}`} data-testid={`clock-${player}`}
      role="timer" aria-live="off" aria-label={chipLabel(name, left.bank, left.buffer, live, e.away)}>
      <span aria-hidden className="turn-clock-glyph">⏱</span>
      <span className="turn-clock-n" aria-hidden>
        {live && left.buffer > 0 && <>{formatClock(left.buffer)}{" · "}</>}{formatClock(left.bank)}
      </span>
      {e.away && <span className="turn-clock-away" aria-hidden>{live ? "Away — clock running" : "Paused — reconnecting"}</span>}
    </span>
  );
}
