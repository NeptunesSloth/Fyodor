import { useState } from "react";
import { toastError } from "../components/Toasts";
import { botStep, setBotSpeed } from "../services/games";
import { useGame } from "../state/gameStore";
import { BOT_SPEEDS, botsOf } from "./botSeat";
import "./botSpeed.css";

/**
 * -- test opponent -- the top bar's "Bot: Normal / Fast / Step" at a table with an opponent the server plays for (app/multiplayer/bots.py).
 * Step waits for Next before each of its actions; the dot says it has one waiting. The server keeps the setting (for the table, not
 * the game: it never enters the history).
 */
export function BotSpeed() {
  const view = useGame((s) => s.view);
  const [busy, setBusy] = useState(false);
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
      {step && (
        <button className="tt-btn bot-speed-next" disabled={busy || !bot.waiting} data-testid="bot-step"
          title={bot.waiting ? "Play the opponent's next action" : "The opponent has nothing to do right now"} onClick={() => void run(() => botStep(id))}>
          Next
        </button>
      )}
    </span>
  );
}
