import { useEffect, useRef, useState } from "react";
import { toast } from "../components/Toasts";
import { perspective, useGame } from "../state/gameStore";
import { send } from "./actions";
import { inGame, numberChits, parseChits, playerChits, teamChits } from "./bags";
import "./dice.css";
import "./tabletoys.css";

/**
 * -- table toys -- the table's draw bag (opened from the roll panel): fill it with chits (numbers, the players' names,
 * teams, any words) and draw one at random, shown to everyone or kept to yourself. The server keeps what's inside
 * (app/game/handlers/toys.py): this panel knows only how many chits there are and the ones drawn that you may see. Every draw
 * is logged; undoing one asks the table, as a roll does. Esc closes.
 */
export function DrawBagPanel({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const panel = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [replace, setReplace] = useState(true);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose();
    };
    const onDown = (e: PointerEvent) => {
      const t = e.target as HTMLElement;
      if (panel.current?.contains(t) || t.closest?.("[data-dice-toggle]")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [onClose]);
  if (!view) return null;
  const me = perspective(view, actingAs);
  const bag = view.bag ?? { count: 0, drawn: [], drawn_count: 0 };
  const mine = bag.drawn.filter((d) => d.player === me && !d.shown && d.chit);
  const nameOf = (pid: string) => view.players.find((p) => p.id === pid)?.name ?? "";
  const colorOf = (pid: string) => view.players.find((p) => p.id === pid)?.color;
  const players = inGame(view).length;
  const fill = (chits: string[]) => {
    if (!chits.length) return toast("Type the chits: one a line, or separated by commas", "warn");
    void send({ type: "bag_fill", chits, replace }).then((ok) => ok && setText(""));
  };
  const draw = (reveal: boolean) => void send({ type: "bag_draw", reveal });
  return (
    <div className="dice-panel bag-panel" ref={panel} role="dialog" aria-label="Draw bag" data-testid="bag-panel">
      <div className="dice-panel-head">
        <span className="dice-panel-title">Draw bag</span>
        <span className="bag-count" data-testid="bag-count">{bag.count === 1 ? "1 chit inside" : `${bag.count} chits inside`} · hidden</span>
        <span className="spacer" />
        <button type="button" className="tt-btn ghost" onClick={() => useGame.getState().openDialog("dice")} title="Back to the dice">Dice</button>
      </div>
      <div className="bag-draw-row">
        <button type="button" className="tt-btn brass" onClick={() => draw(true)} disabled={!bag.count} data-testid="bag-draw" autoFocus
          title="Draw a chit at random and show it to everyone">Draw · show all</button>
        <button type="button" className="tt-btn" onClick={() => draw(false)} disabled={!bag.count} data-testid="bag-draw-hidden"
          title="Draw a chit at random: only you see it (the table sees that you drew one)">Draw · only me</button>
      </div>
      {mine.length > 0 && (
        <div className="bag-mine" data-testid="bag-mine">
          <span>You drew <b>{mine.map((d) => `“${d.chit}”`).join(", ")}</b> (only you see it)</span>
          <span className="spacer" />
          <button type="button" className="tt-btn ghost" onClick={() => void send({ type: "bag_show" })}>Show everyone</button>
        </div>
      )}
      {bag.drawn.length > 0 && (
        <section className="bag-recent" aria-label="Drawn chits">
          <div className="bag-recent-head">Drawn ({bag.drawn_count})</div>
          <ol>
            {bag.drawn.slice(-5).reverse().map((d, i) => (
              <li key={`${bag.drawn_count - i}`} style={{ ["--seat" as string]: colorOf(d.player) }}>
                <i className="who" aria-hidden />
                <span>{nameOf(d.player)}</span>
                {d.chit ? <span className="chit">{d.chit}{!d.shown && " (only you)"}</span> : <span className="hidden">a hidden chit</span>}
              </li>
            ))}
          </ol>
          <div className="bag-tools">
            <button type="button" className="tt-btn ghost" onClick={() => void send({ type: "bag_return" })} title="Put every drawn chit back in the bag">Put drawn chits back</button>
          </div>
        </section>
      )}
      <form className="bag-fill" onSubmit={(e) => { e.preventDefault(); fill(parseChits(text)); }}>
        <div className="bag-fill-head">Fill the bag</div>
        <div className="bag-presets" role="group" aria-label="Quick fills">
          <button type="button" className="tt-btn" onClick={() => fill(playerChits(view))} title="A chit with each player's name (a random player, a random seat)">Player names</button>
          <button type="button" className="tt-btn" onClick={() => fill(numberChits(Math.max(2, players)))} title="1, 2, 3 … one for each player">Numbers 1–{Math.max(2, players)}</button>
          <button type="button" className="tt-btn" onClick={() => fill(teamChits(players))} title="Team A and Team B chits, one for each player">Two teams</button>
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Or your own chits: one a line, or separated by commas (a house chaos draw…)"
          aria-label="Chits to put in the bag" maxLength={4000} data-testid="bag-text" />
        <div className="bag-fill-row">
          <label><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Empty the bag first</label>
          <span className="spacer" />
          <button type="submit" className="tt-btn" disabled={!text.trim()} data-testid="bag-fill">Put in</button>
        </div>
      </form>
      <div className="bag-tools">
        <button type="button" className="tt-btn ghost" onClick={() => void send({ type: "bag_empty" })} disabled={!bag.count && !bag.drawn_count}>Empty the bag</button>
      </div>
      <p className="dice-panel-hint">Only the host's server knows what's inside; a draw is random and logged. Undoing a draw asks the table.</p>
    </div>
  );
}
