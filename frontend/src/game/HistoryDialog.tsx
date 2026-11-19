import { useCallback, useEffect, useState } from "react";
import { groupText } from "./logGroups";
import { Modal } from "../components/Modal";
import { askText } from "../components/Prompt";
import { toast, toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { useGame } from "../state/gameStore";
import { isVisible, PHASE_LABEL, type GameView, type LogPartView, type PhaseName } from "../types/game";
import { useIsHost } from "./HostTools";

interface Snapshot { id: string; name: string; seq: number; turn: number; created_at: number; by: string }
export interface HistoryItem {
  position: number; seq: number; type: string; actor: string | null; log: LogPartView[][]; undone: boolean;
  /** The turn and step the action happened in (from its log lines; absent when it logged nothing). */
  turn?: number | null; phase?: string | null;
}

export interface StepHead { label: string; first: number }

/** -- undo back to here -- the (newest-first) list grouped by turn and step: keyed by each group's newest row (where its heading
 * goes), the group's label and its oldest position (what "Undo from here" goes back to before). Rows that logged nothing join the
 * group around them. */
export function stepHeads(items: HistoryItem[]): Map<number, StepHead> {
  const heads = new Map<number, StepHead>();
  let label = "", top = -1;
  [...items].reverse().forEach((it) => {
    const key = it.turn == null || !it.phase ? label : `Turn ${it.turn} · ${PHASE_LABEL[it.phase as PhaseName] ?? it.phase.replace(/_/g, " ")}`;
    if (key !== label || top < 0) {
      label = key;
      top = it.position;
      heads.set(top, { label: key || "Earlier", first: it.position });
    } else {
      const head = heads.get(top)!;
      heads.delete(top);
      top = it.position;
      heads.set(top, head);
    }
  });
  return heads;
}

export const partText = (p: LogPartView) => ("t" in p ? p.t : "card" in p ? p.card.name : [...(p.group.length ? [groupText(p.group)] : []), ...(p.hidden ? [`${p.hidden} hidden`] : [])].join(", "));

/** The event history, newest first (the same request the History tab makes). */
export async function fetchHistory(view: GameView): Promise<HistoryItem[]> {
  const q = view.game.mode === "local" ? `?viewer=${view.viewer === "__omniscient__" ? "all" : view.viewer}` : "";
  const t = seatToken(view.game.id);
  const h = await api.get<{ items: HistoryItem[] }>(`/games/${view.game.id}/history${q}`, t ? { "X-Seat-Token": t } : {});
  return [...h.items].reverse();
}

export const historyText = (it: HistoryItem): string => it.log.map((line) => line.map(partText).join("")).join(" ") || it.type.replace(/_/g, " ");

/**
 * Snapshots (“Before board wipe”) and the event history — for testing lines, replaying a turn,
 * settling disputes, or recovering from an accident. Restoring is the host's call and can be undone.
 */
export function HistoryDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const isHost = useIsHost();
  const actingAs = useGame((s) => s.actingAs);
  const [tab, setTab] = useState<"snapshots" | "history">("snapshots");
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [picked, setPicked] = useState<number | null>(null);
  const [past, setPast] = useState<GameView | null>(null);
  const gameId = view?.game.id ?? "";
  const q = view?.game.mode === "local" ? `?viewer=${view.viewer === "__omniscient__" ? "all" : view.viewer}` : "";
  const headers = useCallback((): Record<string, string> => {
    const t = seatToken(gameId);
    return t ? { "X-Seat-Token": t } : {};
  }, [gameId]);
  const refresh = useCallback(() => {
    if (!gameId) return;
    api.get<Snapshot[]>(`/games/${gameId}/snapshots`, headers()).then(setSnaps, toastError);
    api.get<{ items: HistoryItem[] }>(`/games/${gameId}/history${q}`, headers()).then((h) => setItems([...h.items].reverse()), toastError);
  }, [gameId, q, headers]);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    if (picked == null) return setPast(null);
    api.get<GameView>(`/games/${gameId}/history/${picked}${q}`, headers()).then(setPast, toastError);
  }, [picked, gameId, q, headers]);
  if (!view) return null;
  const cursor = items.reduce((n, it) => (it.undone ? n : Math.max(n, it.position)), 0);
  const heads = stepHeads(items);

  const restore = async (path: string, what: string) => {
    if (!window.confirm(`Restore the table to ${what}? Everyone's table changes; Undo brings it back.`)) return;
    await api.post(path, {}, headers()).then(() => { toast("Table restored"); onClose(); }, toastError);
  };
  // -- undo back to here -- every action after ``position`` at once, under the table's undo rules (Redo puts them back one at a time)
  const undoTo = async (position: number) => {
    const n = cursor - position;
    if (n <= 0 || !window.confirm(`Undo the last ${n} action${n === 1 ? "" : "s"}, back to #${position}?`)) return;
    const as = view.game.mode === "local" ? actingAs : null;
    await api.post(`/games/${gameId}/history/${position}/undo`, { as }, headers()).then(() => { toast(`Undid ${n} action${n === 1 ? "" : "s"}`); onClose(); }, toastError);
  };

  return (
    <Modal title="Snapshots & history" onClose={onClose} wide>
      <div className="deck-src-tabs">
        <button className={`tt-tab ${tab === "snapshots" ? "on" : ""}`} onClick={() => setTab("snapshots")}>Snapshots</button>
        <button className={`tt-tab ${tab === "history" ? "on" : ""}`} onClick={() => setTab("history")}>History</button>
      </div>
      {tab === "snapshots" ? (
        <div className="snapshots" data-testid="snapshots">
          <button className="tt-btn brass" data-testid="take-snapshot" onClick={async () => {
            const name = await askText("Snapshot name", "Before board wipe");
            if (name === null) return;
            await api.post(`/games/${gameId}/snapshots`, { name }, headers()).then(() => refresh(), toastError);
          }}>Save snapshot</button>
          {snaps.length === 0 && <p className="hint">Save the whole table (hands, libraries, positions, counters, life…) to come back to it later.</p>}
          {snaps.map((s) => (
            <div key={s.id} className="host-row" data-testid="snapshot-row">
              <b>{s.name}</b>
              <span className="hint">turn {s.turn} · {new Date(s.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {s.by}</span>
              <span className="spacer" />
              {isHost && <button className="tt-btn" data-testid="restore-snapshot" onClick={() => void restore(`/games/${gameId}/snapshots/${s.id}/restore`, `“${s.name}”`)}>Restore</button>}
              {isHost && <button className="tt-btn ghost danger" onClick={() => void api.del(`/games/${gameId}/snapshots/${s.id}`, headers()).then(refresh, toastError)}>Delete</button>}
            </div>
          ))}
        </div>
      ) : (
        <div className="history-view" data-testid="history">
          <div className="history-list">
            {items.map((it) => (
              <div key={it.position} className="history-row">
                {heads.has(it.position) && (
                  <div className="history-head">
                    <span>{heads.get(it.position)!.label}</span>
                    {heads.get(it.position)!.first <= cursor && (
                      <button className="tt-btn ghost" data-testid="undo-step" title="Undo every action of this step"
                        onClick={() => void undoTo(heads.get(it.position)!.first - 1)}>Undo this step</button>
                    )}
                  </div>
                )}
                <button className={`history-item ${picked === it.position ? "on" : ""} ${it.undone ? "undone" : ""}`} onClick={() => setPicked(it.position)}>
                  <span className="hint">#{it.position}</span>
                  <span>{it.log.length ? it.log.map((l) => l.map(partText).join("")).join(" · ") : `${it.actor ?? ""} ${it.type.replace(/_/g, " ")}`}</span>
                </button>
              </div>
            ))}
          </div>
          <div className="history-state">
            {!past ? (
              <p className="hint">Pick an event to see the table right after it (as you could see it then).</p>
            ) : (
              <>
                <p><b>After #{picked}</b> · Turn {past.turn.number} · {past.players.find((p) => p.id === past.turn.active_player)?.name} · {PHASE_LABEL[past.turn.phase as PhaseName]}</p>
                {past.players.map((p) => {
                  const bf = (past.zones[`${p.id}:battlefield`] as string[] | undefined) ?? [];
                  return (
                    <div key={p.id} className="history-player">
                      <b>{p.name}</b> · {p.life} life · hand {p.hand_count} · library {p.library_count}
                      <div className="hint">{bf.map((id) => { const c = past.cards[id]; return c && isVisible(c) ? c.name : "face-down card"; }).join(", ") || "empty battlefield"}</div>
                    </div>
                  );
                })}
                {picked != null && picked < cursor && (
                  <button className="tt-btn brass" data-testid="undo-to-history" onClick={() => void undoTo(picked)}>Undo back to here</button>
                )}
                {isHost && picked != null && (
                  <button className="tt-btn" data-testid="restore-history" onClick={() => void restore(`/games/${gameId}/history/${picked}/restore`, `step #${picked}`)}>Restore from here</button>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
