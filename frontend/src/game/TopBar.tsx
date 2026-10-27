import { viewsMenu } from "./bookmarks";
import { usePrefs } from "../state/prefs";
import { cleanupMenu, selectMenu } from "./selection";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import type { GameView } from "../types/game";
import { useIsHost } from "./HostTools";
import { fetchHistory, historyText } from "./HistoryDialog";
import { useGame } from "../state/gameStore";
import { OMNISCIENT, SPECTATOR } from "../types/game";
import { send } from "./actions";
import { resolveRenderer } from "../table3d/renderer";

export function TopBar() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const actingAs = useGame((s) => s.actingAs);
  const { undo, redo, openDialog, setViewer, setActingAs } = useGame.getState();
  const isHost = useIsHost();
  const hud = usePrefs((st) => st.hud);
  const renderer = usePrefs((st) => st.renderer);
  if (!view) return null;
  const is3d = resolveRenderer(renderer) === "3d";
  const local = view.game.mode === "local";
  const dayNight = view.table.day_night;
  return (
    <header className="game-top">
      <a className="brand" href="#/play" title="Back to lobby">←</a>
      <div className="game-title">
        <b>{view.game.name}</b>
        {view.game.mode === "lan" && view.game.code && <span className="room-code" title="Room code for other players">Room {view.game.code}</span>}
        {status !== "open" && <span className={`status ${status}`}>{status === "reconnecting" ? "Reconnecting…" : status}</span>}
      </div>
      <span className="spacer" />
      {dayNight && (
        <button className={`tt-btn ghost daynight ${dayNight}`} title="Day / night (click to cycle)"
          onClick={() => void send({ type: "set_day_night", value: dayNight === "day" ? "night" : null })}>
          {dayNight === "day" ? "☀ Day" : "☾ Night"}
        </button>
      )}
      <span className="tt-split" role="group" aria-label="Undo and redo">
        <button className="tt-btn ghost" disabled={!view.game.can_undo} onClick={() => void undo()} title="Undo (Ctrl+Z)">Undo</button>
        <button className="tt-btn ghost undo-more" disabled={!view.game.can_undo} aria-label="Undo back to a recent action" title="Undo back to a recent action" onClick={(e) => void recentMenu(e)}>▾</button>
        <button className="tt-btn ghost" disabled={!view.game.can_redo} onClick={() => void redo()} title="Redo (Ctrl+Shift+Z)">Redo</button>
      </span>
      {local && (
        <label className="seat-switch" title="Hot-seat: whose view to show">
          View
          <select value={view.viewer} onChange={(e) => setViewer(e.target.value === "all" ? OMNISCIENT : e.target.value)}>
            {view.players.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
            <option value={OMNISCIENT}>Open table</option>
            <option value={SPECTATOR}>Spectator</option>
          </select>
        </label>
      )}
      {local && !(view.viewer in view.game.seats) && (
        <label className="seat-switch" title="Actions are performed as this player">
          Act as
          <select value={actingAs ?? ""} onChange={(e) => setActingAs(e.target.value)}>
            {view.players.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>
      )}
      {resolveRenderer("3d") === "3d" && (
        <button className="tt-btn ghost" data-testid="renderer-toggle" title="Switch between the 3D table and the lighter 2D table (also in Settings → Table)"
          onClick={() => usePrefs.getState().set({ renderer: is3d ? "2d" : "3d" })}>
          {is3d ? "2D table" : "3D table"}
        </button>
      )}
      <button className="tt-btn ghost" title="Hide or show the player panels' counters, mana pool, commander damage and tool tray (H)" onClick={() => usePrefs.getState().set({ hud: usePrefs.getState().hud === "full" ? "minimal" : "full" })}>
        {hud === "full" ? "Hide counters & tools" : "Show counters & tools"}
      </button>
      <button className="tt-btn ghost" onClick={() => openDialog("help")} title="How to play, controls and shortcuts (?)">Help</button>
      <button className="tt-btn ghost" data-testid="table-menu" aria-label="More" title="Save, load, tools and settings" onClick={(e) => openMenu(e, tableMenu(isHost), "Table")}>More</button>
      {/* kept apart from Undo: ending the game is not a slip of the hand */}
      {(isHost || (view.game.mode === "lan" && view.viewer in view.game.seats)) && (
        <button className="tt-btn ghost" data-testid="end-game" onClick={() => openDialog("endgame")} title={isHost ? "Record who won" : "Propose ending the game"}>
          {view.game.result_id ? "Result ✓" : "End game"}
        </button>
      )}
    </header>
  );
}

/** The last few actions, newest first; picking one undoes everything back to and including it. */
async function recentMenu(e: React.MouseEvent) {
  const at = { clientX: e.clientX, clientY: e.clientY };
  const s = useGame.getState();
  if (!s.view) return;
  const items = await fetchHistory(s.view).catch(() => []);
  const live = items.filter((it) => !it.undone).slice(0, 10);
  openMenu(at, live.length ? live.map((it, i) => ({
    label: historyText(it),
    hint: i ? `Undo ${i + 1} actions` : "Undo this action",
    onClick: async () => { for (let k = 0; k <= i; k++) await useGame.getState().undo(); },
  })) : [{ label: "Nothing to undo", disabled: true }], "Undo back to…");
}

function tableMenu(isHost: boolean): MenuItem[] {
  const s = useGame.getState();
  const prefs = usePrefs.getState();
  return [
    { label: "Save game…", onClick: () => s.openDialog("save") },
    { label: "Snapshots & history…", onClick: () => s.openDialog("history") },
    { label: "Appearance…", hint: "sleeves & playmat", onClick: () => s.openDialog("appearance") },
    { label: "Settings…", hint: "profile, sound, keys", onClick: () => s.openDialog("settings") },
    {
      label: "Day / night",
      submenu: [
        { label: "Day", onClick: () => void send({ type: "set_day_night", value: "day" }) },
        { label: "Night", onClick: () => void send({ type: "set_day_night", value: "night" }) },
        { label: "Neither", onClick: () => void send({ type: "set_day_night", value: null }) },
      ],
    },
    soloMenu(isHost),
    viewsMenu(),
    selectMenu(),
    cleanupMenu(),
    { label: prefs.showTokenSources ? "Hide token sources" : "Show token sources", onClick: () => prefs.set({ showTokenSources: !prefs.showTokenSources }) },
    "separator",
    { label: "Resync my view", hint: "Fetch a fresh copy of the table from the host", onClick: () => s.conn?.resync() },
    { label: "Verify sync", hint: "Debug: compare this screen with the host's state", onClick: () => void verifySync() },
    ...(isHost
      ? ([
          "separator",
          { label: s.view?.game.result_id ? "Game result…" : "End game…", onClick: () => s.openDialog("endgame") },
          { label: "Host tools…", onClick: () => s.openDialog("host") },
        ] as MenuItem[])
      : []),
    "separator",
    { label: "Pod stats", onClick: () => window.open("#/stats", "_blank") },
  ];
}

/** Debug: compare the reconciled local view with a fresh one from the server; resync if they differ. */
async function verifySync(): Promise<void> {
  const s = useGame.getState();
  const local = s.view;
  if (!local) return;
  const token = seatToken(local.game.id);
  const q = local.game.mode === "local" ? `?viewer=${encodeURIComponent(local.viewer === "__omniscient__" ? "all" : local.viewer)}` : "";
  const fresh = await api.get<GameView>(`/games/${local.game.id}/view${q}`, token ? { "X-Seat-Token": token } : {});
  const strip = (v: GameView) => JSON.stringify({ ...v, log: v.log.length, game: { ...v.game, revision: 0, seats: 0 } });
  if (strip(fresh) === strip(useGame.getState().view ?? local)) toast(`In sync (revision ${fresh.game.revision ?? "?"})`);
  else {
    toast("This screen was out of date — resynced", "error");
    s.conn?.resync();
  }
}

function soloMenu(isHost: boolean): MenuItem {
  const s = useGame.getState();
  const allowed = !!s.view?.game.settings.allow_test_objects;
  return {
    label: "Solo tools",
    submenu: [
      { label: "Spawn a card…", disabled: !allowed, hint: allowed ? "test object" : "off at this table", onClick: () => s.openDialog("spawn") },
      { label: "Reset my deck…", onClick: () => { if (window.confirm("Gather your cards back into your deck, remove your tokens, copies and test objects, reset life and shuffle?")) void send({ type: "reset_deck", draw: 7 }); } },
      { label: "New opening hand", onClick: () => void send({ type: "mulligan" }) },
      ...(isHost
        ? ([
            "separator",
            { label: "Restart game…", onClick: () => { if (window.confirm("Reset every deck and go back to turn 1?")) void send({ type: "restart_game", draw: 7 }); } },
            { label: allowed ? "Disallow test cards" : "Allow test cards", onClick: () => void send({ type: "configure", allow_test_objects: !allowed }) },
          ] as MenuItem[])
        : []),
    ],
  };
}
