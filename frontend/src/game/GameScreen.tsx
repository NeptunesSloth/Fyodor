import { tapGesture } from "./rules/intents";
import { useMacros } from "../state/macros";
import { playmatStyle, usePlaymat } from "./appearance";
import { lazy, Suspense, useEffect } from "react";
import { perspective, useGame } from "../state/gameStore";
import { SPECTATOR } from "../types/game";
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
import { bookmarkSlot, matchHotkey } from "./hotkeys";
import { recallBookmark, saveBookmark } from "./bookmarks";
import { ResponseBar } from "./ResponseBar";
import { AutomationErrorPanel, AutomationHud, DecisionPanel, PriorityBar, RulesStack } from "./rules/RulesHud";
import { passPriority } from "./rules/intents";
import "./rules/rules.css";
import { resolveRenderer } from "../table3d/renderer";

const Table3D = lazy(() => import("../table3d/Table3D").then((m) => ({ default: m.Table3D })));

export function GameScreen() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const detail = useGame((s) => s.statusDetail);
  const outbox = useGame((s) => s.outbox);
  const actingAs = useGame((s) => s.actingAs);
  const focus = useGame((s) => s.focus);
  const rendererPref = usePrefs((s) => s.renderer);
  const browserOpen = useGame((s) => !!s.browser || (!!s.view && !!s.view.searches[s.view.viewer]));
  useShortcuts();
  useHudClass();
  usePreferredLook();
  useEffect(() => useMacros.getState().refresh(), []);

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
  const three = resolveRenderer(rendererPref) === "3d";

  return (
    <div className="game-screen">
      <TopBar />
      <div className="game-body">
        <main className={`table ${three ? "is-3d" : ""}`}>
          {three ? <Suspense fallback={<div className="table3d-loading">Setting the table…</div>}><Table3D me={me} /></Suspense> : <TablePlaymat />}
          {!three && <div className={`opponents n${others.length} ${focus && focus !== me ? "focused" : ""} ${focus === me ? "shrunk" : ""}`}>
            {others.map((pid) => (
              <PlayerArea key={pid} player={pid} me={me} mine={false} compact={others.length > 1} focused={focus === pid} />
            ))}
          </div>}
          {!three && <div className={`me ${focus === me ? "focused" : ""} ${focus && focus !== me ? "shrunk" : ""}`}>
            <PlayerArea player={me} me={me} mine />
          </div>}
          {browserOpen && <ZoneBrowser me={me} />}
          {canSeeMyHand && <Hand player={me} me={me} />}
        </main>
      </div>
      {status !== "open" && (
        <div className={`conn-banner ${status}`} role="status" data-testid="conn-banner">
          {status === "reconnecting" ? "Connection lost — reconnecting…" : status === "connecting" ? "Connecting to the table…" : detail ?? status}
          {outbox > 0 && <span className="conn-outbox"> · {outbox} action{outbox === 1 ? "" : "s"} will be sent when the table is back</span>}
        </div>
      )}
      <StackWidget me={me} />
      <LogDrawer />
      <ToolTray />
      <SelectionBar />
      <CardPreview />
      <GameDialogs me={me} />
      <MulliganOverlay />
      <ResponseBar />
      <AutomationHud />
      <RulesStack />
      <PriorityBar />
      <DecisionPanel />
      <AutomationErrorPanel />
      <DragLayer />
      {!three && <CombatArrows />}
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
      const bm = bookmarkSlot(e);
      if (bm) {
        e.preventDefault();
        if (bm.save) void saveBookmark(bm.slot);
        else recallBookmark(bm.slot);
        return;
      }
      const id = matchHotkey(e, usePrefs.getState().keymap);
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
            tapGesture(targets.filter((cid) => view.cards[cid]?.zone.endsWith(":battlefield")), (x) => void tapCards(x));
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
          if (view.rules && !view.rules.controlled_by && (view.rules.priority === me || (!!view.rules.acting_as && view.rules.priority === view.rules.acting_as)) && !view.rules.decision) void passPriority();
          else if (w?.waiting.includes(me)) void send({ type: "response_pass" });
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

const appliedLook = new Set<string>();

/** Wear the profile's preferred sleeves / playmat when sitting down at a table (once per game). */
function usePreferredLook() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  useEffect(() => {
    if (!view || view.viewer === SPECTATOR) return;
    const me = perspective(view, actingAs);
    const key = `${view.game.id}:${me}`;
    if (appliedLook.has(key)) return;
    appliedLook.add(key);
    const p = view.players.find((x) => x.id === me);
    const prefs = usePrefs.getState();
    const action: Record<string, unknown> = { type: "set_appearance" };
    if (p && !p.sleeve && prefs.preferredSleeve) action.sleeve = prefs.preferredSleeve;
    if (p && !p.playmat && prefs.preferredPlaymat) action.playmat = { asset_id: prefs.preferredPlaymat, fit: "cover", scale: 1, offset_x: 0, offset_y: 0, rotation: 0, opacity: 1, show_zones: true };
    if (Object.keys(action).length > 1 && view.game.mode === "lan") void useGame.getState().conn?.request({ type: "action", action }).catch(() => undefined);
  }, [view, actingAs]);
}
