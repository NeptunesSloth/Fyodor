import { useState } from "react";
import { Icon } from "../components/Icon";
import { toastError } from "../components/Toasts";
import { botStep, setBotSpeed } from "../services/games";
import { useGame } from "../state/gameStore";
import { BOT_LEVELS, BOT_SPEEDS, botLevel, botsOf } from "./botSeat";
import { send } from "./actions";
import { useIsHost } from "./HostTools";
import "./botSpeed.css";

/**
 * -- test opponent -- the top bar's "Bot: Normal / Fast / Step" at a table with an opponent the server plays for (app/multiplayer/bots.py).
 * Step waits for Next before each of its actions; the dot says it has one waiting. The server keeps the setting (for the table, not
 * the game: it never enters the history).
 */
const LEVEL_SHORT = { simple: "Simple", intermediate: "Mid", advanced: "Adv" } as const;

export function BotSpeed() {
  const view = useGame((s) => s.view);
  const [busy, setBusy] = useState(false);
  const isHost = useIsHost();
  const bot = view?.game.bot;
  if (!view || !bot || !botsOf(view).length) return null;
  const id = view.game.id;
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const step = bot.speed === "step";
  return (
    <span className="bot-speed" data-testid="bot-speed">
      <span className={`bot-speed-label ${bot.waiting ? "waiting" : ""}`} title={bot.waiting ? "The opponent has an action to play" : "The opponent the server plays for"}>
        Bot{bot.waiting && <span className="bot-speed-dot" aria-label="(an action waiting)" />}
      </span>
      <span className="tt-split" role="group" aria-label="Bot speed">
        {BOT_SPEEDS.map((s) => (
          <button key={s.id} className="tt-btn ghost" aria-pressed={bot.speed === s.id} disabled={busy} title={s.hint}
            data-testid={`bot-speed-${s.id}`} onClick={() => { if (bot.speed !== s.id) void run(() => setBotSpeed(id, s.id)); }}>
            {s.label}
          </button>
        ))}
      </span>
      {isHost && botsOf(view).map((p, i, all) => ( // -- bot levels -- how well each opponent plays (the host's: recorded like any action)
        <span key={p.id} className="tt-split bot-levels" role="group" aria-label={`${p.name}: level`} data-testid={`bot-level-${p.id}`}>
          {/* -- playtest (nov 17) -- which bot: the robot glyph and its number at the table ("O" and "O2" read as nothing), the name on hover */}
          {all.length > 1 && (
            <span className="bot-level-who" title={p.name} data-testid={`bot-level-who-${p.id}`}>
              <Icon name="bot" size={13} label={p.name} /><b>{i + 1}</b>
            </span>
          )}
          {/* (two or more bots: a chooser each, so the bar keeps End game on screen at 1600 px) */}
          {all.length > 1 ? (
            <select className="bot-level-pick" value={botLevel(p)} aria-label={`${p.name}: level`} title={`How well ${p.name} plays`}
              data-testid={`bot-level-${p.id}-pick`} onChange={(e) => void send({ type: "set_bot_level", player: p.id, level: e.target.value })}>
              {BOT_LEVELS.map((l) => <option key={l.id} value={l.id} title={l.hint}>{LEVEL_SHORT[l.id]}</option>)}
            </select>
          ) : BOT_LEVELS.map((l) => (
            <button key={l.id} className="tt-btn ghost" aria-pressed={botLevel(p) === l.id} title={`${p.name} plays at ${l.label}: ${l.hint}`}
              data-testid={`bot-level-${p.id}-${l.id}`} onClick={() => { if (botLevel(p) !== l.id) void send({ type: "set_bot_level", player: p.id, level: l.id }); }}>
              {LEVEL_SHORT[l.id]}
            </button>
          ))}
        </span>
      ))}
      {step && (
        <button className="tt-btn bot-speed-next" disabled={busy || !bot.waiting} data-testid="bot-step"
          title={bot.waiting ? "Play the opponent's next action" : "The opponent has nothing to do right now"} onClick={() => void run(() => botStep(id))}>
          Next
        </button>
      )}
    </span>
  );
}
