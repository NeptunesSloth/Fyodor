import { useEffect } from "react";
import { perspective, useGame } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { isVisible, splitZone } from "../types/game";
import { draw, moveCards, send, tapCards } from "./actions";
import { GameDialogs } from "./Dialogs";
import { CombatArrows, DragLayer } from "./Overlays";
import { Hand } from "./Hand";
import { PlayerArea } from "./PlayerArea";
import { Inspector, LogPanel, StackPanel } from "./SidePanels";
import { TopBar } from "./TopBar";
import { ZoneBrowser } from "./ZoneBrowser";

export function GameScreen() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const detail = useGame((s) => s.statusDetail);
  const actingAs = useGame((s) => s.actingAs);
  const browserOpen = useGame((s) => !!s.browser || (!!s.view && !!s.view.searches[s.view.viewer]));
  useShortcuts();

  if (!view) {
    return (
      <div className="page">
        <p>{status === "closed" ? detail ?? "Disconnected." : "Connecting to the table…"}</p>
        <a className="btn" href="#/play">Back to lobby</a>
      </div>
    );
  }
  const me = perspective(view, actingAs);
  const order = view.seat_order;
  const start = order.indexOf(me);
  const others = [...order.slice(start + 1), ...order.slice(0, Math.max(0, start))];
  const canSeeMyHand = view.viewer !== "__spectator__";

  return (
    <div className="game-screen">
      <TopBar />
      <div className="game-body">
        <main className="table">
          <div className={`opponents n${others.length}`}>
            {others.map((pid) => (
              <PlayerArea key={pid} player={pid} me={me} mine={false} compact={others.length > 1} />
            ))}
          </div>
          <div className="me">
            <PlayerArea player={me} me={me} mine />
          </div>
          {browserOpen && <ZoneBrowser me={me} />}
          {canSeeMyHand && <Hand player={me} me={me} />}
        </main>
        <aside className="sidebar">
          <Inspector />
          <StackPanel me={me} />
          <LogPanel />
        </aside>
      </div>
      {status !== "open" && <div className="conn-banner">{status === "reconnecting" ? "Connection lost — reconnecting…" : detail ?? status}</div>}
      <GameDialogs me={me} />
      <DragLayer />
      <CombatArrows />
    </div>
  );
}

function useShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]") || document.querySelector(".modal-backdrop")) return;
      const s = useGame.getState();
      const view = s.view;
      if (!view) return;
      const me = perspective(view, s.actingAs);
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && key === "z") {
        e.preventDefault();
        void (e.shiftKey ? s.redo() : s.undo());
        return;
      }
      if (mod && key === "y") {
        e.preventDefault();
        void s.redo();
        return;
      }
      if (mod) return;
      const targets = s.selection.length ? s.selection : s.hover && view.cards[s.hover] ? [s.hover] : [];
      switch (key) {
        case "t":
        case " ":
          if (targets.length) {
            e.preventDefault();
            void tapCards(targets.filter((id) => view.cards[id]?.zone.endsWith(":battlefield")));
          }
          break;
        case "d":
          void draw(me, 1);
          break;
        case "n":
          void send(e.shiftKey ? { type: "next_turn" } : { type: "phase", to: "next" });
          break;
        case "u":
          void send({ type: "untap_all", player: me });
          break;
        case "f": {
          const id = targets[0];
          const c = id ? view.cards[id] : undefined;
          if (c && isVisible(c) && c.card_id) {
            const data = useCardCache.getState().cards[c.card_id];
            if (data && (data.double_faced || data.faces.length > 1)) void send({ type: "set_face", card_id: c.id });
          }
          break;
        }
        case "delete":
        case "backspace":
          if (targets.length && targets.every((id) => splitZone(view.cards[id]?.zone ?? "").zone !== "graveyard")) {
            void moveCards(targets, "graveyard"); // each card goes to its owner's graveyard
          }
          break;
        case "escape":
          s.clearSelection();
          s.openBrowser(null);
          if (view.my_views?.some((v) => v.kind === "look")) void send({ type: "end_view" });
          break;
        case "?":
          s.openDialog("help");
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
