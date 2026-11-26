import { CommitNumber } from "../components/CommitNumber";
import type { ClockSettings, LobbySettings } from "../types/game";

export const DEFAULT_CLOCK: ClockSettings = { on: false, bank_seconds: 1500, buffer_seconds: 30, at_zero: "act", grace_seconds: 120 };

/** A lobby PATCH carrying `clock` REPLACES the whole object on the server, so every change goes out as the complete clock. */
export function clockPatch(current: ClockSettings | undefined, change: Partial<ClockSettings>): { clock: ClockSettings } {
  return { clock: { ...DEFAULT_CLOCK, ...current, ...change } };
}

/**
 * -- turn clock -- the lobby's optional turn clock (server-owned, Stage 3): off by default. Self-contained like PlanechaseSetting.
 * The fields keep the server's limits (bank 1-120 min, grace 5-300 s).
 */
export function TurnClockSetting({ value, onChange }: { value: ClockSettings | undefined; onChange: (v: Pick<LobbySettings, "clock">) => void }) {
  const c = { ...DEFAULT_CLOCK, ...value };
  const change = (p: Partial<ClockSettings>) => onChange(clockPatch(value, p));
  const hint = !c.on
    ? "Off: no clock."
    : c.at_zero === "show"
      ? "At zero the clock just reads 0:00; nothing happens."
      : "Each player has a bank of time for the whole game. Each decision first gets a short grace that isn't charged. At zero, Fyodor makes the safest choice for them (pass, decline, no attack); it never concedes for anyone. Runs while rules automation is on.";
  return (
    <div className="field turn-clock-field" data-testid="lobby-turn-clock">
      <label className="inline"><input type="checkbox" checked={c.on} onChange={(e) => change({ on: e.target.checked })} /> Turn clock</label>
      {c.on && (
        <span className="inline">
          <label>Bank{" "}
            <CommitNumber min={1} max={120} value={Math.round(c.bank_seconds / 60)} label="Minutes in each player's bank"
              onCommit={(n) => change({ bank_seconds: n * 60 })} /> min
          </label>{" "}
          <label>Grace{" "}
            <CommitNumber min={5} max={300} value={c.buffer_seconds} label="Seconds of grace per decision"
              onCommit={(n) => change({ buffer_seconds: n })} /> s
          </label>{" "}
          <label>At zero{" "}
            <select value={c.at_zero} onChange={(e) => change({ at_zero: e.target.value as ClockSettings["at_zero"] })}>
              <option value="act">Act for the player</option>
              <option value="show">Only show it</option>
            </select>
          </label>
        </span>
      )}
      <span className="hint">{hint}</span>
    </div>
  );
}
