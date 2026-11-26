import { useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { useGame } from "../state/gameStore";
import { isVisible, splitZone, type CardPermissions, type UndoPolicy } from "../types/game";
import { setTableReactions } from "../services/spectate";
import { send } from "./actions";
import { InternetInvite } from "./InternetInvite";
import { UNDO_POLICIES } from "./undoPolicy";
import { CARD_PERMISSIONS } from "./cardPermissions";

const PRESENCE: Record<string, string> = {
  connected: "Connected",
  reconnecting: "Reconnecting…",
  disconnected: "Disconnected",
  open: "Open seat",
};

const hostHeaders = (gameId: string): Record<string, string> => {
  const t = seatToken(gameId);
  return t ? { "X-Seat-Token": t } : {};
};

/** True when this browser may use the host tools (the LAN host, or anyone at a hot-seat table). */
export function useIsHost(): boolean {
  return useGame((s) => !!s.view && (s.view.game.mode === "local" || s.view.game.host_seat === s.view.viewer));
}

/**
 * HOST TOOLS: practical repairs for a private pod. Deliberately tucked away (⋯ → Host tools),
 * not part of normal play.
 */
export function HostToolsDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const selection = useGame((s) => s.selection);
  const [link, setLink] = useState<{ seat: string; url: string } | null>(null);
  if (!view) return null;
  const gameId = view.game.id;
  const lan = view.game.mode === "lan";
  const post = <T,>(path: string, body: unknown = {}) => api.post<T>(`/games/${gameId}/host/${path}`, body, hostHeaders(gameId));
  const run = (fn: () => Promise<unknown>, ok?: string) =>
    void fn().then(() => ok && toast(ok), toastError);

  const selected = selection.map((id) => view.cards[id]).filter((c) => !!c);
  const stolen = selected.filter((c) => isVisible(c) && (c.controller !== c.owner || splitZone(c.zone).player !== c.owner));
  const lost = Object.values(view.cards).filter(
    (c) => c.zone.endsWith(":battlefield") && ((c.x ?? 0) < -40 || (c.y ?? 0) < -40 || (c.x ?? 0) > 3000 || (c.y ?? 0) > 2200),
  );

  return (
    <Modal title="Host tools" onClose={onClose} wide>
      <div className="host-tools" data-testid="host-tools">
        {lan && (
          <section>
            <h3>Seats</h3>
            {view.seat_order.map((pid) => {
              const seat = view.game.seats[pid];
              const p = view.players.find((x) => x.id === pid);
              const presence = seat?.presence ?? (seat?.connected ? "connected" : "disconnected");
              const hostSeat = pid === view.game.host_seat;
              return (
                <div key={pid} className="host-row" data-testid={`host-seat-${pid}`}>
                  <b>{p?.name ?? pid}</b>
                  <span className={`presence-label ${presence}`}>{PRESENCE[presence] ?? presence}</span>
                  <span className="spacer" />
                  <button className="tt-btn ghost" disabled={presence !== "connected"}
                    onClick={() => run(() => post("reconnect", { seat: pid }), `Asked ${p?.name} to reconnect`)}>Force reconnect</button>
                  {!hostSeat && (
                    <button className="tt-btn ghost" title="Issue a new link for this seat (the old one stops working)" data-testid={`seat-link-${pid}`}
                      onClick={() => run(async () => {
                        const res = await post<{ path: string }>("seat-link", { seat: pid });
                        setLink({ seat: pid, url: `${window.location.origin}${window.location.pathname}${res.path.replace(/^\//, "")}` });
                      })}>Reclaim / assign seat</button>
                  )}
                  {!hostSeat && presence !== "connected" && (
                    <button className="tt-btn ghost danger" onClick={() => {
                      if (window.confirm(`Remove ${p?.name} from the game? Every card they own leaves the game.`)) void send({ type: "remove_player", player: pid });
                    }}>Remove player</button>
                  )}
                </div>
              );
            })}
            {link && (
              <div className="host-link">
                <span>Open this on the device that should sit in {view.players.find((x) => x.id === link.seat)?.name}'s seat:</span>
                <code data-testid="seat-link">{link.url}</code>
                <button className="tt-btn" onClick={() => void navigator.clipboard?.writeText(link.url).then(() => toast("Link copied"), () => undefined)}>Copy</button>
              </div>
            )}
          </section>
        )}
        <section>
          <h3>Table</h3>
          <div className="host-grid">
            <button className="tt-btn" data-testid="resync-all" disabled={!lan}
              onClick={() => run(() => post("resync"), "Everyone received a fresh copy of the table")}>Resync all clients</button>
            <button className="tt-btn" disabled={!view.response} onClick={() => void send({ type: "response_close", as_host: true })}>Force pass response</button>
            <button className="tt-btn" disabled={!stolen.length} title="Selected cards go back to their owners"
              onClick={() => void send({ type: "return_to_owner", card_ids: stolen.map((c) => c.id) })}>Return selected to owner</button>
            <button className="tt-btn" disabled={!selected.length} onClick={() => void send({ type: "set_lock", card_ids: selected.map((c) => c.id), value: false })}>
              Unlock selected
            </button>
            <button className="tt-btn" disabled={!lost.length} title="Bring cards dragged off the edge of the table back into view"
              onClick={() => void send({ type: "set_position", moves: lost.map((c, i) => [c.id, 60 + (i % 10) * 24, 60 + Math.floor(i / 10) * 24]) })}>
              Restore lost objects{lost.length ? ` (${lost.length})` : ""}
            </button>
          </div>
          <p className="hint">Undo (Ctrl+Z) restores anything deleted by mistake. Dice objects arrive with the tabletop toys.</p>
        </section>
        <UndoSetting />
        {lan && <InternetInvite gameId={gameId} />}
        <PlanechaseHostSetting />
        {lan && <CardPermissionsSetting />}
        {lan && <ReactionsSetting gameId={gameId} on={view.game.night?.reactions !== false} />}
      </div>
    </Modal>
  );
}

/** -- planechase -- deal the table a planar deck, or put it away, mid-game (the server deals and shuffles: app/game/handlers/planechase.py). */
function PlanechaseHostSetting() {
  const settings = useGame((s) => s.view?.game.settings);
  const on = useGame((s) => !!s.view?.planechase);
  const [count, setCount] = useState(settings?.planar_deck_size ?? 10);
  const [phenomena, setPhenomena] = useState(settings?.planar_phenomena !== false);
  const deal = () => {
    if (on && !window.confirm("Deal a new planar deck? The current plane and the planes visited go away (Undo brings them back).")) return;
    void send({ type: "planar_start", count, phenomena });
  };
  return (
    <section data-testid="host-planechase">
      <h3>Planechase</h3>
      <div className="row wrap">
        <label className="field inline">Planar deck
          <input type="number" min={2} max={60} value={count} style={{ width: 56 }} onChange={(e) => setCount(Math.max(2, Math.min(60, Number(e.target.value) || 10)))} /> cards
        </label>
        <label><input type="checkbox" checked={phenomena} onChange={(e) => setPhenomena(e.target.checked)} /> Include phenomena</label>
        <button className="tt-btn" onClick={deal}>{on ? "Deal a new planar deck" : "Deal a planar deck"}</button>
        {on && <button className="tt-btn ghost" onClick={() => void send({ type: "planar_end" })}>Put the planar deck away</button>}
      </div>
      <p className="hint">One shared deck of distinct planes. The die, its cost and planeswalking are automatic; players apply each plane's effects.</p>
    </section>
  );
}

/** -- table permissions -- who may change a player's cards at this LAN table (the server enforces it; saved with the game). */
function CardPermissionsSetting() {
  const policy = useGame((s) => s.view?.game.settings.card_permissions ?? "everyone");
  const current = CARD_PERMISSIONS.find((p) => p.id === policy) ?? CARD_PERMISSIONS[0]!;
  return (
    <section>
      <h3>Cards</h3>
      <label className="field inline">Who may change a player's cards
        <select value={policy} data-testid="card-permissions"
          onChange={(e) => void send({ type: "configure", card_permissions: e.target.value as CardPermissions })}>
          {CARD_PERMISSIONS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>
      <p className="hint">{current.hint}.</p>
    </section>
  );
}

/** (spectator activities) the table-wide switch for spectators' reactions; each player can still mute them in Settings. */
function ReactionsSetting({ gameId, on }: { gameId: string; on: boolean }) {
  const [busy, setBusy] = useState(false);
  const toggle = async (value: boolean) => {
    setBusy(true);
    try {
      await setTableReactions(gameId, value);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section>
      <h3>Reactions</h3>
      <label className="check"><input type="checkbox" checked={on} disabled={busy} data-testid="table-reactions"
        onChange={(e) => void toggle(e.target.checked)} /> Spectators and players who are out can send reactions</label>
      <p className="hint">For the whole table, for tonight. Each player can also hide reactions just for themselves in Settings.</p>
    </section>
  );
}

/** -- undo policy (gap 3) -- who may undo at this table (the server enforces it; saved with the game). */
function UndoSetting() {
  const mode = useGame((s) => s.view?.game.mode);
  const policy = useGame((s) => s.view?.game.settings.undo_policy ?? "everyone");
  const current = UNDO_POLICIES.find((p) => p.id === policy) ?? UNDO_POLICIES[0]!;
  const extra = mode === "local"
    ? " Everyone at a hot-seat table sits at the host computer: Host only lets everyone undo, and Own actions only follows the player acting."
    : (policy !== "everyone" ? " Others can ask the table instead (Ask to undo: every other player still in the game approves). To take back someone else's action anyway: Snapshots & history, Restore from here." : "")
      // -- quick undo request -- (app/game/undo_requests.py)
      + " Taking back a draw, a look at a library, a reveal, a search or a random result always asks the table first.";
  return (
    <section>
      <h3>Undo</h3>
      <label className="field inline">Who can undo
        <select value={policy} data-testid="undo-policy" onChange={(e) => void send({ type: "configure", undo_policy: e.target.value as UndoPolicy })}>
          {UNDO_POLICIES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </label>
      <p className="hint">{current.hint}.{extra}</p>
    </section>
  );
}
