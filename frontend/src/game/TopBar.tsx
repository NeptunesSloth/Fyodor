import { viewsMenu } from "./bookmarks";
import { usePrefs } from "../state/prefs";
import { cleanupMenu, selectMenu } from "./selection";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import type { GameView } from "../types/game";
import { useIsHost } from "./HostTools";
import { useGame } from "../state/gameStore";
import { OMNISCIENT, SPECTATOR } from "../types/game";
import { send } from "./actions";

export function TopBar() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const actingAs = useGame((s) => s.actingAs);
  const { undo, redo, openDialog, setViewer, setActingAs } = useGame.getState();
  const isHost = useIsHost();
  const hud = usePrefs((st) => st.hud);
  if (!view) return null;
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
      <button className="tt-btn ghost" disabled={!view.game.can_undo} onClick={() => void undo()} title="Undo (Ctrl+Z)">Undo</button>
      <button className="tt-btn ghost" disabled={!view.game.can_redo} onClick={() => void redo()} title="Redo (Ctrl+Shift+Z)">Redo</button>
      {isHost && (
        <button className="tt-btn ghost" data-testid="end-game" onClick={() => openDialog("endgame")} title="Record who won">
          {view.game.result_id ? "Result ✓" : "End game"}
        </button>
      )}
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
      <button className="tt-btn ghost" title="Minimal / full HUD (H)" onClick={() => usePrefs.getState().set({ hud: usePrefs.getState().hud === "full" ? "minimal" : "full" })}>
        {hud === "full" ? "Detail: full" : "Detail: minimal"}
      </button>
      <button className="tt-icon" onClick={() => openDialog("help")} title="Controls and shortcuts (?)" aria-label="Controls and shortcuts">?</button>
      <button className="icon-btn" data-testid="table-menu" aria-label="More" onClick={(e) => openMenu(e, tableMenu(isHost), "Table")}>⋯</button>
    </header>
  );
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
