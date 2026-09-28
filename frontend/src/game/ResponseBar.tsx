import { perspective, playerName, useGame } from "../state/gameStore";
import { send } from "./actions";

/**
 * "Anything in response?" — a compact strip, never a modal. It asks, it doesn't enforce:
 * the player who asked can go ahead anyway, and the host can force it closed.
 */
export function ResponseBar() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  if (!view || view.game.settings.priority_helper !== "simple") return null;
  const me = perspective(view, actingAs);
  const w = view.response;
  const auto = view.auto_pass?.includes(me) ?? false;
  const isHost = view.game.mode === "local" || view.game.host_seat === view.viewer;
  const seated = view.viewer !== "__spectator__";

  if (!w) {
    if (!auto || !seated) return null;
    return (
      <div className="resp-bar quiet" data-testid="response-bar">
        <span>Auto-passing this turn</span>
        <button className="tt-btn ghost" onClick={() => void send({ type: "response_auto", on: false })}>Stop</button>
      </div>
    );
  }
  const names = (ids: string[]) => ids.map((id) => playerName(view, id)).join(", ");
  const mine = w.opener === me;
  const waitingOnMe = seated && w.waiting.includes(me);
  const status = w.responder
    ? `${playerName(view, w.responder)} is responding`
    : w.waiting.length
      ? `Waiting on ${names(w.waiting)}`
      : "Everyone passed";

  return (
    <div className={`resp-bar ${waitingOnMe ? "ask" : ""}`} data-testid="response-bar">
      <span className="resp-what">
        <b>{mine ? "You" : playerName(view, w.opener)}</b> {mine ? "want" : "wants"} to {w.text}
      </span>
      <span className="resp-status" data-testid="response-status">{status}</span>
      {waitingOnMe && (
        <>
          <button className="tt-btn" data-testid="respond" title="R" onClick={() => void send({ type: "response_respond" })}>Respond</button>
          <button className="tt-btn brass" data-testid="pass" title="P" onClick={() => void send({ type: "response_pass" })}>Pass</button>
          <button className={`tt-btn ${auto ? "on" : "ghost"}`} data-testid="auto-pass" title="Shift+P — pass every check until the end of this turn"
            onClick={() => void send({ type: "response_auto", on: !auto })}>Auto-pass</button>
        </>
      )}
      {(mine || w.responder === me) && (
        <button className="tt-btn ghost" data-testid="proceed" onClick={() => void send({ type: "response_close", apply_intent: w.has_intent })}>
          {w.has_intent && !w.responder ? "Go ahead anyway" : "Close"}
        </button>
      )}
      {isHost && !mine && w.responder !== me && (
        <button className="tt-btn ghost" data-testid="force-pass" title="Host: close this check" onClick={() => void send({ type: "response_close", as_host: true })}>
          Force
        </button>
      )}
    </div>
  );
}
