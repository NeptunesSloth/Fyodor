import { useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { setClock } from "../services/games";
import { useGame } from "../state/gameStore";
import { clockPatch } from "../pages/TurnClockSetting";

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
          <input type="number" min={5} max={300} defaultValue={s.buffer_seconds} key={`g${s.buffer_seconds}`} style={{ width: 60 }} disabled={busy}
            onBlur={(e) => { const n = Math.max(5, Math.min(300, Math.round(Number(e.target.value) || s.buffer_seconds))); if (n !== s.buffer_seconds) change({ buffer_seconds: n }); }} /> seconds
        </label>
        <label className="field inline">Reconnect grace
          <input type="number" min={1} max={30} defaultValue={Math.round(s.grace_seconds / 60)} key={`r${s.grace_seconds}`} style={{ width: 56 }} disabled={busy}
            onBlur={(e) => { const n = Math.max(30, Math.min(1800, Math.round((Number(e.target.value) || 2) * 60))); if (n !== s.grace_seconds) change({ grace_seconds: n }); }} /> minutes
        </label>
      </div>
      {s.on && humans.map((pid) => {
        const p = view.players.find((x) => x.id === pid);
        const away = !!clock?.players?.[pid]?.away;
        return (
          <div key={pid} className="host-row" data-testid={`host-clock-${pid}`}>
            <b>{p?.name ?? pid}</b>
            <span className="spacer" />
            <button className="tt-btn ghost" disabled={busy} onClick={() => void go({ op: "add_time", player: pid, seconds: 60 }, `Added 1:00 to ${p?.name}`)}>+1:00</button>
            <button className="tt-btn ghost" disabled={busy} onClick={() => void go({ op: "add_time", player: pid, seconds: 300 }, `Added 5:00 to ${p?.name}`)}>+5:00</button>
            {away && <button className="tt-btn ghost" disabled={busy} onClick={() => void go({ op: "grace", player: pid, seconds: 120 }, `Gave ${p?.name} 2 more minutes to reconnect`)}>Give 2 more minutes to reconnect</button>}
          </div>
        );
      })}
      <p className="hint">An optional clock for the whole game: each player has a bank, and each decision first gets a short grace that isn't charged. At zero Fyodor makes the safest choice for them, or only shows 0:00. It never concedes for anyone.</p>
    </section>
  );
}
