import { playmatStyle, usePlaymat } from "./appearance";
import { useEffect } from "react";
import { perspective, useGame } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { isVisible, splitZone } from "../types/game";
import { draw, moveCards, send, tapCards } from "./actions";
import { GameDialogs } from "./Dialogs";
import { CombatArrows, DragLayer, PickLayer } from "./Overlays";
import { Hand } from "./Hand";
import { MulliganOverlay } from "./MulliganOverlay";
import { PlayerArea } from "./PlayerArea";
import { TopBar } from "./TopBar";
import { CardPreview, LogDrawer, SelectionBar, StackWidget, ToolTray, useHudClass } from "./Hud";
import { usePrefs } from "../state/prefs";
import { ZoneBrowser } from "./ZoneBrowser";
import { matchHotkey } from "./hotkeys";
import { ResponseBar } from "./ResponseBar";

export function GameScreen() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const detail = useGame((s) => s.statusDetail);
  const actingAs = useGame((s) => s.actingAs);
  const browserOpen = useGame((s) => !!s.browser || (!!s.view && !!s.view.searches[s.view.viewer]));
  useShortcuts();
  useHudClass();

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
          <TablePlaymat />
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
      </div>
      {status !== "open" && <div className="conn-banner">{status === "reconnecting" ? "Connection lost — reconnecting…" : detail ?? status}</div>}
      <StackWidget me={me} />
      <LogDrawer />
      <ToolTray />
      <SelectionBar />
      <CardPreview />
      <GameDialogs me={me} />
      <MulliganOverlay />
      <ResponseBar />
      <DragLayer />
      <CombatArrows />
      <PickLayer />
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
      const id = matchHotkey(e);
      if (!id) return;
      const targets = s.selection.length ? s.selection : s.hover && view.cards[s.hover] ? [s.hover] : [];
      const w = view.response;
      switch (id) {
        case "undo":
          e.preventDefault();
          void s.undo();
          break;
        case "redo":
          e.preventDefault();
          void s.redo();
          break;
        case "tap":
          if (targets.length) {
            e.preventDefault();
            void tapCards(targets.filter((cid) => view.cards[cid]?.zone.endsWith(":battlefield")));
          }
          break;
        case "draw":
          void draw(me, 1);
          break;
        case "next_step":
          void send({ type: "phase", to: "next" });
          break;
        case "next_turn":
          void send({ type: "next_turn" });
          break;
        case "untap_all":
          void send({ type: "untap_all", player: me });
          break;
        case "turn_over": {
          const cid = targets[0];
          const c = cid ? view.cards[cid] : undefined;
          if (c && isVisible(c) && c.card_id) {
            const data = useCardCache.getState().cards[c.card_id];
            if (data && (data.double_faced || data.faces.length > 1)) void send({ type: "set_face", card_id: c.id });
          }
          break;
        }
        case "to_graveyard":
          if (targets.length && targets.every((cid) => splitZone(view.cards[cid]?.zone ?? "").zone !== "graveyard")) {
            void moveCards(targets, "graveyard"); // each card goes to its owner's graveyard
          }
          break;
        case "cancel":
          s.clearSelection();
          s.openBrowser(null);
          if (view.my_views?.some((v) => v.kind === "look")) void send({ type: "end_view" });
          break;
        case "help":
          s.openDialog("help");
          break;
        case "pass":
          if (w?.waiting.includes(me)) void send({ type: "response_pass" });
          break;
        case "respond":
          if (w && w.opener !== me) void send({ type: "response_respond" });
          break;
        case "hud": {
          const prefs = usePrefs.getState();
          prefs.set({ hud: prefs.hud === "full" ? "minimal" : "full" });
          break;
        }
        case "auto_pass":
          void send({ type: "response_auto", on: !view.auto_pass?.includes(me) });
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

function TablePlaymat() {
  const { mat, url } = usePlaymat(null);
  if (!url) return null;
  return <div className="playmat-layer table-mat" style={playmatStyle(mat, url)} aria-hidden />;
}
