import { useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { setClock } from "../services/games";
import { useGame } from "../state/gameStore";
import { clockPatch } from "../pages/TurnClockSetting";
import { CommitNumber } from "../components/CommitNumber";
import type { ClockBody } from "../services/games";

/** The grace extension the host button gives, in seconds (the route takes seconds). */
export const GRACE_EXTENSION_SECONDS = 120;

/** A player's host buttons: the label and the request it sends. The reconnect one only for a player who is away. */
export function clockRowButtons(away: boolean): { label: string; body: (pid: string) => Extract<ClockBody, { player: string }>; done: (name: string) => string }[] {
  const add = (label: string, seconds: number) => ({
    label, body: (pid: string) => ({ op: "add_time" as const, player: pid, seconds }), done: (name: string) => `Added ${label.slice(1)} to ${name}`,
  });
  return [
    add("+1:00", 60), add("+5:00", 300),
    ...(away ? [{ label: "Give 2 more minutes to reconnect", body: (pid: string) => ({ op: "grace" as const, player: pid, seconds: GRACE_EXTENSION_SECONDS }),
      done: (name: string) => `Gave ${name} 2 more minutes to reconnect` }] : []),
  ];
}

/** One player's row of host buttons (all disabled while a request is out). */
export function ClockRow({ pid, name, away, busy, go }: { pid: string; name: string; away: boolean; busy: boolean; go: (body: ClockBody, ok: string) => void }) {
  return (
    <div className="host-row" data-testid={`host-clock-${pid}`}>
      <b>{name}</b>
      <span className="spacer" />
      {clockRowButtons(away).map((b) => (
        <button key={b.label} className="tt-btn ghost" disabled={busy} onClick={() => go(b.body(pid), b.done(name))}>{b.label}</button>
      ))}
    </div>
  );
}

/** -- turn clock -- the host's controls (server: app/api/turn_clock.py): on/off, what happens at zero, the grace, and time for a player. */
export function TurnClockHostSection() {
  const view = useGame((s) => s.view);
  const [busy, setBusy] = useState(false);
  if (!view) return null;
  const gameId = view.game.id;
  const clock = view.game.clock;
  const s = clockPatch(clock?.settings, {}).clock;
  const go = async (body: Parameters<typeof setClock>[1], ok?: string) => {
    setBusy(true);
    try {
      await setClock(gameId, body);
      if (ok) toast(ok);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const change = (p: Partial<typeof s>) => void go({ op: "settings", settings: { ...s, ...p } });
  const humans = view.seat_order.filter((pid) => view.game.seats[pid] && !view.players.find((x) => x.id === pid)?.bot);
  return (
    <section data-testid="host-turn-clock">
      <h3>Turn clock</h3>
      <div className="row wrap">
        <label className="check"><input type="checkbox" checked={s.on} disabled={busy} data-testid="clock-on" onChange={(e) => change({ on: e.target.checked })} /> {s.on ? "On" : "Off"}</label>
        <label className="field inline">At zero
          <select value={s.at_zero} disabled={busy} onChange={(e) => change({ at_zero: e.target.value as typeof s.at_zero })}>
            <option value="act">Act for the player</option>
            <option value="show">Only show it</option>
          </select>
        </label>
        <label className="field inline">Grace per decision
          <CommitNumber min={5} max={300} value={s.buffer_seconds} label="Grace per decision, in seconds" disabled={busy}
            onCommit={(n) => change({ buffer_seconds: n })} /> seconds
        </label>
        <label className="field inline">Reconnect grace
          <CommitNumber min={1} max={30} value={Math.round(s.grace_seconds / 60)} label="Reconnect grace, in minutes" disabled={busy}
            onCommit={(n) => change({ grace_seconds: n * 60 })} onInvalid={() => toast("Enter a reconnect grace of 1 to 30 minutes")} /> minutes
        </label>
      </div>
      {s.on && humans.map((pid) => {
        const p = view.players.find((x) => x.id === pid);
        return <ClockRow key={pid} pid={pid} name={p?.name ?? pid} away={!!clock?.players?.[pid]?.away} busy={busy} go={(b, ok) => void go(b, ok)} />;
      })}
      <p className="hint">An optional clock for the whole game: each player has a bank, and each decision first gets a short grace that isn't charged. At zero Fyodor makes the safest choice for them, or only shows 0:00. It never concedes for anyone.</p>
    </section>
  );
}
