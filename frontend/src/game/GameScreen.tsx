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
import { AttachLines, CombatArrows, DragLayer, PickLayer, StackFocusMarks } from "./Overlays";
import { FirstGameGuide } from "./FirstGameGuide";
import { FocusKeys2D } from "./focus2d";
import { Hand, toggleHandBrowser } from "./Hand";
import { MulliganOverlay } from "./MulliganOverlay";
import { PlayerArea } from "./PlayerArea";
import { TopBar } from "./TopBar";
import { CardPreview, LogDrawer, SelectionBar, StackWidget, ToolTray, useHudClass } from "./Hud";
import { usePrefs } from "../state/prefs";
import { toast } from "../components/Toasts";
import { CrashScreen } from "../components/CrashScreen";
import { cycleCombatFilter } from "./combatFilter";
import { ZoneBrowser } from "./ZoneBrowser";
import { bookmarkSlot, matchHotkey } from "./hotkeys";
import { outKeyBlocked } from "./outOfGame";
import { recallBookmark, saveBookmark } from "./bookmarks";
import { ResponseBar } from "./ResponseBar";
import { UndoRequestBar } from "./UndoRequestBar";
import { AutomationErrorPanel, DecisionPanel, dialState, RulesStack, TurnDial, XPrompt } from "./rules/RulesHud";
import { passOrResolve, passPriority } from "./rules/intents";
import "./rules/rules.css";
import { resolveRenderer } from "../table3d/renderer";
import { CombatLanes, CombatStrip } from "./CombatLanes";
import { GameNight } from "./GameNight";
import { TestEnding } from "./TestEnding";
import { MajorNotices } from "./MajorNotices";
import { SignalLayer } from "./Signals";
import { PingLayer } from "./Pings";
import { DiceLayer } from "./DiceLayer";
import { DigDialog } from "./DigDialog";
import { RevealNotice } from "./RevealNotice";
import { DrawNotice } from "./DrawNotice";
import { TableImporter } from "./TableImporter";
import { ExileCastables } from "./ExileCastablesRow";
import { useTurnAlert } from "./turnAlert";
import { HotSeatCover } from "./HotSeatCover";
import { nextHandSort, HAND_SORT_LABEL } from "./handSort";
import { Motion2D } from "./motion/Motion2D";
import { BagDraws } from "./BagDraws";
import { PlanechasePlaque } from "./PlanechasePlaque";
import { DayNightLayer } from "./DayNightLayer";

/**
 * -- 3D fallback -- the 3D table couldn't start on this computer (no working WebGL, a graphics driver refusing it, its part of
 * the page not loading): the table switches to 2D (a saved preference, Settings brings 3D back) instead of the whole page failing.
 */
function Fall2D() {
  useEffect(() => {
    usePrefs.getState().set({ renderer: "2d" });
    toast("The 3D table couldn't start on this computer, so the table is in 2D. Settings can switch it back.", "error");
  }, []);
  return null;
}

const Table3D = lazy(() => import("../table3d/Table3D").then((m) => ({ default: m.Table3D })));

/** The 2D table's "camera": the 3D seat keys (2–6 look at an opponent, 1 or T back to the whole table) set the focus. */
function FocusKeys({ others, me }: { others: string[]; me: string }) {
  useEffect(() => {
    const onCam = (e: Event) => {
      const { id, digit, player } = (e as CustomEvent<{ id: string; digit: number; player?: string }>).detail;
      const setFocus = (focus: string | null) => useGame.getState().setLayout({ focus });
      if (id === "cam_seat" || id === "cam_reset" || id === "cam_table") setFocus(null);
      else if (id === "cam_player" && others[digit - 2]) setFocus(others[digit - 2]!);
      else if (id === "cam_focus_player") setFocus(player && player !== me && others.includes(player) ? player : null);
    };
    window.addEventListener("fyodor:camera", onCam);
    return () => window.removeEventListener("fyodor:camera", onCam);
  }, [others.join(), me]);
  return null;
}

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
  useTurnAlert();
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
      {/* the turn dial is fixed bottom-right, but early in the tab order: it is the game's main control */}
      <TurnDial />
      <div className="game-body">
        <main className={`table ${three ? "is-3d" : ""}`}>
          {/* -- day and night -- first, so the 2D night tint lies over the felt and under every card */}
          <DayNightLayer three={three} />
          {three ? <CrashScreen quiet={<Fall2D />}><Suspense fallback={<div className="table3d-loading">Setting the table…</div>}><Table3D me={me} /></Suspense></CrashScreen> : <TablePlaymat />}
          {!three && <FocusKeys others={others} me={me} />}
          {!three && <FocusKeys2D />}
          {!three && <div className={`opponents n${others.length} ${focus && focus !== me ? "focused" : ""} ${focus === me ? "shrunk" : ""}`}>
            {others.map((pid) => (
              <PlayerArea key={pid} player={pid} me={me} mine={false} compact={others.length > 1} focused={focus === pid} />
            ))}
          </div>}
          {!three && <CombatStrip />}
          {!three && <div className={`me ${focus === me ? "focused" : ""} ${focus && focus !== me ? "shrunk" : ""}`}>
            <PlayerArea player={me} me={me} mine />
          </div>}
          {browserOpen && <ZoneBrowser me={me} />}
          {canSeeMyHand && <Hand player={me} me={me} />}
          {canSeeMyHand && <ExileCastables me={me} />}
        </main>
      </div>
      {status !== "open" && (
        <div className={`conn-banner ${status}`} role="status" data-testid="conn-banner">
          {status === "reconnecting" ? "Connection lost — reconnecting…" : status === "connecting" ? "Connecting to the table…" : detail ?? status}
          {outbox > 0 && <span className="conn-outbox"> · {outbox} action{outbox === 1 ? "" : "s"} will be sent when the table is back</span>}
        </div>
      )}
      {!three && <DiceLayer />}
      {!three && <Motion2D />}
      <BagDraws />
      <DigDialog me={me} />
      <RevealNotice />
      {canSeeMyHand && <DrawNotice />}
      <TableImporter />
      <StackWidget me={me} />
      {/* -- planechase -- the face-up plane and the planar die (both tables: over the 3D view too) */}
      <PlanechasePlaque me={me} compact={three} />
      <LogDrawer />
      <ToolTray />
      <SelectionBar />
      <CardPreview skipHand={three} />
      <GameDialogs me={me} />
      <MulliganOverlay />
      <ResponseBar />
      <UndoRequestBar />
      <RulesStack />
      <DecisionPanel />
      <XPrompt />
      <AutomationErrorPanel />
      <DragLayer />
      {!three && <CombatArrows />}
      {!three && <AttachLines />}
      <StackFocusMarks />
      <FirstGameGuide me={me} />
      <PickLayer />
      {three && <CombatLanes />}
      <GameNight />
      <TestEnding />
      <MajorNotices />
      <HotSeatCover />
      <SignalLayer />
      <PingLayer />
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
      if (outKeyBlocked(view, me, id)) return; // -- out of the game -- keys that would move it do nothing (the reason, once)
      const targets = s.selection.length ? s.selection : s.hover && view.cards[s.hover] ? [s.hover] : [];
      const w = view.response;
      const myPriority = !!view.rules && !view.rules.controlled_by && !view.rules.decision
        && (view.rules.priority === me || (!!view.rules.acting_as && view.rules.priority === view.rules.acting_as));
      if (id.startsWith("cam_")) {
        // the 3D table moves its camera; the 2D table focuses a seat (FocusKeys); the arrows pan the 3D view only
        // (elsewhere they keep scrolling what they scroll)
        if (id === "cam_pan" && !document.querySelector("[data-testid='table-3d']")) return;
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("fyodor:camera", { detail: { id, digit: Number(e.key) || 0, hover: s.hover, key: e.key, shift: e.shiftKey } }));
        return;
      }
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
          if (!dialState(view, me).watching) void send({ type: "phase", to: "next" }); // out of the game: no step controls
          break;
        case "next_turn":
          if (!dialState(view, me).watching) void send({ type: "next_turn" });
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
            // one ordinary card goes at once (Undo covers it); several cards or a commander ask first
            const cmdr = targets.some((cid) => { const c = view.cards[cid]; return isVisible(c) && !!c.commander_key; });
            if ((targets.length > 1 || cmdr) && !window.confirm(`Put ${targets.length > 1 ? `${targets.length} cards` : "a commander"} into the graveyard? Undo (Ctrl+Z) brings ${targets.length > 1 ? "them" : "it"} back.`)) break;
            void moveCards(targets, "graveyard"); // each card goes to its owner's graveyard
          }
          break;
        case "cancel":
          s.clearSelection();
          s.openBrowser(null);
          if (view.my_views?.some((v) => v.kind === "look")) void send({ type: "end_view" });
          break;
        case "help":
          e.preventDefault(); // -- sweep B2 -- the "?" isn't typed into the help's search box too (it filtered the list down to itself)
          s.openDialog("help");
          break;
        case "ping":
          window.dispatchEvent(new Event("fyodor:ping-here"));
          break;
        case "hand_sort": {
          const prefs = usePrefs.getState();
          const next = nextHandSort(prefs.handSort);
          prefs.set({ handSort: next });
          toast(`Hand: ${HAND_SORT_LABEL[next]}`);
          break;
        }
        case "pass":
          if (myPriority) void passOrResolve(view.stack.length);
          else if (w?.waiting.includes(me)) void send({ type: "response_pass" });
          // manual play: P does what the dial's big button says
          else if (!view.rules) void send(view.stack.length ? { type: "resolve_top" } : { type: "phase", to: "next" });
          break;
        case "respond":
          if (w && w.opener !== me) void send({ type: "response_respond" });
          break;
        case "hand_browse":
          e.preventDefault(); // (the key mustn't land in the browser's filter box as it takes the focus)
          if (view.viewer !== "__spectator__") toggleHandBrowser(me);
          break;
        case "hud": {
          const prefs = usePrefs.getState();
          prefs.set({ hud: prefs.hud === "full" ? "minimal" : "full" });
          break;
        }
        case "combat_filter": cycleCombatFilter(); break;
        case "dice":
          e.preventDefault();
          s.openDialog(s.dialog === "dice" ? null : "dice");
          break;
        case "token_math":
          e.preventDefault();
          s.openDialog(s.dialog === "token_math" ? null : "token_math");
          break;
        case "auto_pass":
          // rules automation: the dial's End turn (the response checks below are manual tables' only; hotkeyLabel says which)
          if (view.rules) { if (myPriority && !view.stack.length) void passPriority("next_turn"); }
          else void send({ type: "response_auto", on: !view.auto_pass?.includes(me) });
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
