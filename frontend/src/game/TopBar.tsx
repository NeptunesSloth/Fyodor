import { openMenu, type MenuItem } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import type { GameView } from "../types/game";
import { useIsHost } from "./HostTools";
import { useGame } from "../state/gameStore";
import { OMNISCIENT, PHASE_LABEL, PHASES, SPECTATOR } from "../types/game";
import { send } from "./actions";

export function PhaseBar() {
  const turn = useGame((s) => s.view?.turn);
  const players = useGame((s) => s.view?.players);
  if (!turn || !players) return null;
  const active = players.find((p) => p.id === turn.active_player);
  return (
    <div className="phase-bar">
      <span className="turn-badge" style={{ ["--player-color" as string]: active?.color }} title="Active player">
        T{turn.number} · {active?.name}
      </span>
      <button className="icon-btn" title="Previous step" onClick={() => void send({ type: "phase", to: "prev" })}>‹</button>
      <div className="phases">
        {PHASES.map((ph) => (
          <button
            key={ph}
            className={`phase ${ph === turn.phase ? "current" : ""} ${ph.includes("combat") || ph.startsWith("declare") ? "combat" : ""}`}
            onClick={() => void send({ type: "phase", to: ph })}
            title={PHASE_LABEL[ph]}
          >
            {PHASE_LABEL[ph]}
          </button>
        ))}
      </div>
      <button className="icon-btn" title="Next step (N)" onClick={() => void send({ type: "phase", to: "next" })}>›</button>
      <button className="btn small primary" title="Next turn (Shift+N)" onClick={() => void send({ type: "next_turn" })}>Next turn</button>
    </div>
  );
}

export function TopBar() {
  const view = useGame((s) => s.view);
  const status = useGame((s) => s.status);
  const actingAs = useGame((s) => s.actingAs);
  const { undo, redo, openDialog, setViewer, setActingAs } = useGame.getState();
  const isHost = useIsHost();
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
      <PhaseBar />
      <span className="spacer" />
      <button
        className={`icon-btn daynight ${dayNight ?? ""}`}
        title="Day / night (click to cycle)"
        onClick={() => void send({ type: "set_day_night", value: dayNight === null ? "day" : dayNight === "day" ? "night" : null })}
      >
        {dayNight === "day" ? "☀" : dayNight === "night" ? "☾" : "◐"}
      </button>
      <button className="btn small" onClick={() => openDialog("tokens")} title="Create tokens">Tokens</button>
      <button className="btn small" onClick={() => openDialog("dice")} title="Dice and coins">🎲</button>
      <button className="btn small" disabled={!view.game.can_undo} onClick={() => void undo()} title="Undo (Ctrl+Z)">↶ Undo</button>
      <button className="btn small" disabled={!view.game.can_redo} onClick={() => void redo()} title="Redo (Ctrl+Shift+Z)">↷</button>
      <button className="btn small" onClick={() => openDialog("save")} title="Save game">Save</button>
      {isHost && (
        <button className="btn small" data-testid="end-game" onClick={() => openDialog("endgame")} title="Record who won">
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
      <button className="icon-btn" onClick={() => openDialog("help")} title="Keyboard shortcuts (?)">?</button>
      <button className="icon-btn" data-testid="table-menu" aria-label="More" onClick={(e) => openMenu(e, tableMenu(isHost), "Table")}>⋯</button>
    </header>
  );
}

function tableMenu(isHost: boolean): MenuItem[] {
  const s = useGame.getState();
  return [
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
