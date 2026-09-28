/**
 * Client game state: the latest server view (reconciled for structural sharing) plus local
 * UI state (selection, hover, open dialogs). The server stays authoritative: every change
 * goes through `send()`, and the UI re-renders from the view the server sends back.
 */
import { create } from "zustand";
import { toast } from "../components/Toasts";
import { GameConnection, type ConnStatus } from "../services/gameSocket";
import {
  OMNISCIENT,
  SPECTATOR,
  type Action,
  type GameCard,
  type GameView,
  type LibraryView,
  type LobbyView,
  type PlayerView,
} from "../types/game";
import { reconcile } from "./reconcile";
import { requestCards } from "./cardCache";

export interface BrowserState {
  zone: string;
  title?: string;
  /** Only show the first N cards (look at top N). */
  limit?: number;
}

interface GameStore {
  gameId: string | null;
  view: GameView | null;
  /** The pregame lobby, while the host hasn't started the game yet. */
  lobby: LobbyView | null;
  status: ConnStatus;
  statusDetail: string | null;
  conn: GameConnection | null;
  /** Local hot-seat: which seat actions are attributed to. */
  actingAs: string | null;
  selection: string[];
  hover: string | null;
  inspect: string | null;
  browser: BrowserState | null;
  dialog: null | "tokens" | "dice" | "save" | "help" | "counters" | "ability" | "host";
  dialogArg: string | null;
  pendingPositions: Record<string, [number, number]>;

  connect: (gameId: string, opts: { token?: string | null; viewer?: string | null }) => void;
  disconnect: () => void;
  send: (action: Action) => Promise<boolean>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  setViewer: (viewer: string) => void;
  setActingAs: (player: string) => void;
  select: (ids: string[], mode?: "replace" | "toggle" | "add") => void;
  clearSelection: () => void;
  setHover: (id: string | null) => void;
  setInspect: (id: string | null) => void;
  openBrowser: (b: BrowserState | null) => void;
  openDialog: (d: GameStore["dialog"], arg?: string | null) => void;
  setPending: (positions: Record<string, [number, number]>) => void;
}

export const useGame = create<GameStore>((set, get) => ({
  gameId: null,
  view: null,
  lobby: null,
  status: "closed",
  statusDetail: null,
  conn: null,
  actingAs: null,
  selection: [],
  hover: null,
  inspect: null,
  browser: null,
  dialog: null,
  dialogArg: null,
  pendingPositions: {},

  connect: (gameId, opts) => {
    get().conn?.close();
    const conn = new GameConnection(gameId, opts, {
      onState: (incoming, replace) => {
        const prev = get().view;
        const view = prev && !replace && prev.game.id === incoming.game.id ? reconcile(prev, incoming) : incoming;
        const ids: string[] = [];
        for (const c of Object.values(view.cards)) {
          if (!c.hidden && c.card_id) ids.push(c.card_id);
          if (!c.hidden && c.ability?.source_card_id) ids.push(c.ability.source_card_id);
        }
        for (const p of view.players) for (const cmd of p.commanders) if (cmd.card_id) ids.push(cmd.card_id);
        requestCards(ids);
        set((s) => ({
          view,
          lobby: null,
          pendingPositions: {},
          selection: s.selection.filter((id) => id in view.cards),
          actingAs: resolveActingAs(view, s.actingAs),
        }));
      },
      onLobby: (lobby) => set({ lobby, view: null }),
      onStatus: (status, detail) => set({ status, statusDetail: detail ?? null }),
      onClosedByServer: (reason) => set({ status: "closed", statusDetail: reason }),
    });
    set({ gameId, conn, view: null, lobby: null, selection: [], browser: null, dialog: null, actingAs: null });
    conn.connect();
  },

  disconnect: () => {
    get().conn?.close();
    set({ conn: null, view: null, lobby: null, gameId: null, status: "closed" });
  },

  send: async (action) => {
    const { conn, view, actingAs } = get();
    if (!conn || !view) return false;
    const as = view.game.mode === "local" ? actingAs ?? undefined : undefined;
    try {
      await conn.request({ type: "action", action, as });
      return true;
    } catch (e) {
      set({ pendingPositions: {} });
      toast(e instanceof Error ? e.message : String(e), "error");
      return false;
    }
  },

  undo: async () => {
    const { conn, view, actingAs } = get();
    if (!conn || !view?.game.can_undo) return;
    await conn.request({ type: "undo", as: view.game.mode === "local" ? actingAs : undefined }).catch((e: Error) => toast(e.message, "error"));
  },

  redo: async () => {
    const { conn, view, actingAs } = get();
    if (!conn || !view?.game.can_redo) return;
    await conn.request({ type: "redo", as: view.game.mode === "local" ? actingAs : undefined }).catch((e: Error) => toast(e.message, "error"));
  },

  setViewer: (viewer) => {
    get().conn?.setViewer(viewer);
    set({ selection: [], browser: null, actingAs: viewer === OMNISCIENT || viewer === SPECTATOR ? get().actingAs : viewer });
  },

  setActingAs: (player) => set({ actingAs: player }),

  select: (ids, mode = "replace") =>
    set((s) => {
      if (mode === "replace") return { selection: ids };
      if (mode === "add") return { selection: [...new Set([...s.selection, ...ids])] };
      const current = new Set(s.selection);
      for (const id of ids) {
        if (current.has(id)) current.delete(id);
        else current.add(id);
      }
      return { selection: [...current] };
    }),
  clearSelection: () => set({ selection: [] }),
  setHover: (id) => set({ hover: id }),
  setInspect: (id) => set({ inspect: id }),
  openBrowser: (b) => set({ browser: b }),
  openDialog: (dialog, arg = null) => set({ dialog, dialogArg: arg }),
  setPending: (positions) => set((s) => ({ pendingPositions: { ...s.pendingPositions, ...positions } })),
}));

function resolveActingAs(view: GameView, current: string | null): string {
  if (view.viewer in view.game.seats) return view.viewer;
  if (current && view.seat_order.includes(current)) return current;
  return view.turn.active_player;
}

// ---------------------------------------------------------------------------- selectors

export const useCardView = (id: string): GameCard | undefined => useGame((s) => s.view?.cards[id]);
export const useZoneIds = (key: string): string[] | undefined =>
  useGame((s) => {
    const z = s.view?.zones[key];
    return Array.isArray(z) ? z : undefined;
  });
export const useLibrary = (key: string): LibraryView | undefined =>
  useGame((s) => {
    const z = s.view?.zones[key];
    return z && !Array.isArray(z) ? z : undefined;
  });
export const usePlayer = (id: string): PlayerView | undefined => useGame((s) => s.view?.players.find((p) => p.id === id));

/** The seat the local user is playing as (their perspective at the table). */
export function perspective(view: GameView, actingAs: string | null): string {
  if (view.viewer in view.game.seats) return view.viewer;
  return actingAs ?? view.seat_order[0]!;
}

export function playerName(view: GameView | null, id: string | null | undefined): string {
  if (!view || !id) return "";
  return view.players.find((p) => p.id === id)?.name ?? id;
}
