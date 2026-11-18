import { useEffect } from "react";
import { perspective, settledChange, useGame } from "../../state/gameStore";
import { gameEnded } from "../nightEnding";
import { passPriority, setPrefs } from "./intents";
import { autoPassedMyCast, HOLD_HINT, holdHintDue, usePassStop } from "./passStop";
import { toast } from "../../components/Toasts";

/** Resolve all, remembering to explain a stop (passStop.ts). */
export function resolveAll(): void {
  usePassStop.getState().arm();
  void passPriority("stack_empty");
}

/**
 * -- playtest (nov 16) -- why the automatic passing stopped, over the turn dial where the pass buttons are: a loop the engine paused (its
 * whole line, which only showed cut short in the log ticker), or a card I drew and can cast now. The choices are the dial's own: go on
 * (Resolve all again), one object at a time, or stop here (the banner goes; I keep priority).
 */
export function PassStopBanner({ mine }: { mine: boolean }) {
  const stop = usePassStop((s) => s.stop);
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  useEffect(() => useGame.subscribe((s, prev) => {
    const change = settledChange(s, prev); // (-- resolving progress -- not for an interim view: against the last update before it)
    if (!change || change.after.viewer === "__spectator__") return;
    const { before, after: next } = change;
    const me = perspective(next, s.actingAs);
    usePassStop.getState().update(before, next, me);
    if (autoPassedMyCast(before, next, me) && holdHintDue()) toast(HOLD_HINT, "info", { label: "Hold priority", run: () => void setPrefs({ hold_priority: true }) });
  }), []);
  // (-- resolving progress -- while a chain is worked out the indicator sits here instead; the banner stays mounted, so its
  // subscription above still sees the action's own update, which may bring the very note it shows)
  const resolving = useGame((s) => s.resolving);
  if (resolving || !stop || !view || gameEnded(view, perspective(view, actingAs))) return null;
  const dismiss = () => usePassStop.getState().dismiss();
  const loop = stop.kind === "loop";
  return (
    <section className={`pass-stop plaque ${stop.kind}`} role="status" aria-live="polite" data-testid="pass-stop" data-kind={stop.kind}>
      <header className="pass-stop-head">{loop ? (/^many objects to resolve/i.test(stop.text) ? "Paused: many objects to resolve" : "Paused: this keeps repeating") : "Resolve all stopped"}</header>
      <p className="pass-stop-text">{stop.text}</p>
      <div className="pass-stop-actions">
        {mine && view.stack.length > 0 && (
          <>
            <button className="tt-btn brass" data-testid="pass-stop-continue" onClick={() => { dismiss(); resolveAll(); }}
              title="Keep passing until the stack is empty (it stops again for the same reasons)">{loop ? "Continue" : "Keep resolving"}</button>
            <button className="tt-btn" data-testid="pass-stop-one" onClick={() => { dismiss(); void passPriority("stack_changes"); }}
              title="Resolve only the top object, then get priority back">Resolve one</button>
          </>
        )}
        <button className="tt-btn ghost" data-testid="pass-stop-dismiss" onClick={dismiss}
          title={mine ? "Stop here: keep priority and act (cast, activate), or propose a draw from End game" : "Close"}>{mine ? "Stop here" : "Close"}</button>
      </div>
    </section>
  );
}
