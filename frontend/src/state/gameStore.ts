/**
 * Client game state: the latest server view (reconciled for structural sharing) plus local
 * UI state (selection, hover, open dialogs). The server stays authoritative: every change
 * goes through `send()`, and the UI re-renders from the view the server sends back.
 */
import { create } from "zustand";
import { toast, useToasts } from "../components/Toasts";
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
import { publishTableEvents } from "../game/motion/tableEvents";
import { play, soundForLog } from "../game/sound";
import { requestCards } from "./cardCache";
import { undoActor, undoMode, undoRefusal, type UndoOp } from "../game/undoPolicy";
import { finalBoardRefusal } from "../game/finalBoard";
import { undoRequest } from "../services/undoRequest";

export interface PickMode {
  prompt: string;
  /** Allow several picks, finished with Done. */
  multi: boolean;
  picked: string[];
  /** Players can be picked too. */
  players: boolean;
  onDone: (ids: string[]) => void;
}

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
  /** Apply a lobby update unless a newer one (or the started game) is already here. */
  applyLobby: (lobby: LobbyView) => void;
  status: ConnStatus;
  statusDetail: string | null;
  /** Actions waiting to reach the table (after a dropped connection they are sent again). */
  outbox: number;
  conn: GameConnection | null;
  /** Local hot-seat: which seat actions are attributed to. */
  actingAs: string | null;
  selection: string[];
  /** The card whose action was just refused, flashed on the table for a moment. */
  errorCard: { id: string; at: number } | null;
  hover: string | null;
  inspect: string | null;
  browser: BrowserState | null;
  dialog: null | "tokens" | "dice" | "save" | "help" | "counters" | "ability" | "host" | "endgame" | "appearance" | "history" | "settings" | "macro" | "spawn";
  dialogArg: string | null;
  pendingPositions: Record<string, [number, number]>;
  /** Pick mode: the next clicks on cards / players choose targets (arrows, copy target…). */
  pick: PickMode | null;
  setPick: (p: PickMode | null) => void;
  /** Local view state (bookmarkable): an enlarged side of the table, open stack / log. */
  focus: string | null;
  stackOpen: boolean;
  logOpen: boolean;
  /** The game the focus belongs to ("<table id>#<game of the night>"): a new game opens on the whole table. */
  layoutGame: string | null;
  setLayout: (patch: Partial<Pick<GameStore, "focus" | "stackOpen" | "logOpen">>) => void;

  connect: (gameId: string, opts: { token?: string | null; viewer?: string | null }) => void;
  disconnect: () => void;
  send: (action: Action) => Promise<boolean>;
  /** The last AUTOMATION ERROR (a rules-engine failure: nothing was applied). */
  automationError: string | null;
  setAutomationError: (message: string | null) => void;
  /** True when the server took the step (false: nothing to do, the undo setting forbids it, or it failed; the reason is toasted). */
  undo: () => Promise<boolean>;
  redo: () => Promise<boolean>;
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

/** Actions that place a card, which Alt-dropping can also do by hand (past the rules intents). */
/** Which help topic a refused action opens on (the Help dialog's search). */
const HELP_TOPIC: Record<string, string> = { cast: "cast", cast_spell: "cast", play_land: "land", attack: "attack", declare_attackers: "attack", block: "block", activate: "stack", pass_priority: "priority", resolve_top: "stack", move: "drag", tap: "tap" };

const PLACING = new Set(["play_land", "cast", "cast_spell", "move", "put_from_hand"]);

/**
 * What to try next after a refused action, when the server's message doesn't already say. Never for
 * permission, host or ownership refusals (Alt can't bypass those), and the Alt hint only for actions
 * that place a card.
 */
export function recoveryHint(message: string, actionType = ""): string {
  const m = message.toLowerCase();
  if (/^choose|first|unlock it|only the host|not your|your own|host|seat|private|hidden/.test(m)) return "";
  if (/when you have priority|priority/.test(m)) return "Wait until the turn dial says Your priority.";
  if (/can't pay|cannot pay|not enough mana|mana pool|don't pay/.test(m)) return "Tap lands or other sources for mana, then try again.";
  if (/legal target|isn't a legal target/.test(m)) return "Pick one of the highlighted targets.";
  if (/isn't here any more|different object now|no longer/.test(m)) return "The table changed before your action arrived: look again and retry.";
  if (/is tapped/.test(m) && !PLACING.has(actionType)) return "Untap it first (T on the card).";
  if (/stack is empty/.test(m)) return "Nothing is waiting to resolve.";
  if (/library is empty/.test(m)) return "The plaque's player panel shows each library's size.";
  if (PLACING.has(actionType) && /summoning sickness|is tapped|can't enchant|no legal|can only|isn't|not on the battlefield|not legal|illegal/.test(m)) {
    return "To do it anyway, hold Alt as you drop the card to place it by hand.";
  }
  return "";
}

/** Zones a card leaves the table for: moving there gets a confirmation with Undo. Battlefield moves show on the table. */
const AWAY: Record<string, string> = { graveyard: "put into the graveyard", exile: "exiled", library: "put into a library", hand: "returned to hand", command: "put into the command zone" };

/**
 * A one-line summary for manual actions that are easy to regret (cards sent away, removed or milled),
 * shown with an Undo button. Everything else stays quiet.
 */
export function undoableSummary(a: Record<string, unknown>): string | null {
  const n = Array.isArray(a.card_ids) ? a.card_ids.length : 0;
  const cards = (k: number) => `${k} card${k === 1 ? "" : "s"}`;
  if (a.type === "move") {
    const zone = (a.to as { zone?: string } | undefined)?.zone ?? "";
    return AWAY[zone] ? `${cards(n)} ${AWAY[zone]}` : null;
  }
  if (a.type === "delete_card") return `${cards(n)} removed from the game`;
  if (a.type === "mill") return `Milled ${cards(Number(a.count ?? 1))}`;
  return null;
}

export const useGame = create<GameStore>((set, get) => ({
  gameId: null,
  view: null,
  lobby: null,
  status: "closed",
  statusDetail: null,
  outbox: 0,
  conn: null,
  actingAs: null,
  selection: [],
  errorCard: null,
  hover: null,
  inspect: null,
  browser: null,
  dialog: null,
  dialogArg: null,
  pendingPositions: {},
  pick: null,
  setPick: (pick) => set({ pick }),
  focus: null,
  stackOpen: true,
  logOpen: false,
  layoutGame: null,
  setLayout: (patch) => set(patch),

  applyLobby: (lobby) =>
    set((s) => {
      // A lobby arrives both as HTTP responses and WebSocket pushes, in no guaranteed order.
      // Keep the newest: an older one (or any lobby after the game started) is stale.
      // ...unless the pod went back to the lobby after a game (a newer revision than the game view)
      const back = s.view?.game.revision != null && (lobby.revision ?? 0) > s.view.game.revision;
      if (s.view && s.view.game.id === lobby.game.id && !back) return {};
      if (s.lobby && s.lobby.game.id === lobby.game.id && (lobby.revision ?? 0) < (s.lobby.revision ?? 0)) return {};
      return { lobby, view: null };
    }),

  connect: (gameId, opts) => {
    get().conn?.close();
    const conn = new GameConnection(gameId, opts, {
      onState: (incoming, replace) => {
        const prev = get().view;
        if (prev && prev.game.id === incoming.game.id && !replace) playNewLogSounds(prev, incoming);
        // a rematch keeps the table's id but is a brand-new game: replace, never merge
        const sameGame = !!prev && prev.game.id === incoming.game.id && (prev.game.night?.number ?? 1) === (incoming.game.night?.number ?? 1);
        const view = prev && !replace && sameGame ? reconcile(prev, incoming) : incoming;
        const ids: string[] = [];
        for (const c of Object.values(view.cards)) {
          if (!c.hidden && c.card_id) ids.push(c.card_id);
          if (!c.hidden && c.ability?.source_card_id) ids.push(c.ability.source_card_id);
        }
        for (const p of view.players) for (const cmd of p.commanders) if (cmd.card_id) ids.push(cmd.card_id);
        requestCards(ids);
        const dragged = new Set(Object.keys(get().pendingPositions)); // (cards the viewer just dragged: already where the hand put them)
        const match = `${incoming.game.id}#${incoming.game.night?.number ?? 1}`;
        set((s) => ({
          view,
          lobby: null,
          pendingPositions: {},
          selection: s.selection.filter((id) => id in view.cards),
          actingAs: resolveActingAs(view, s.actingAs),
          // a new game of the night (a rematch keeps the table id, as after the lobby): the last game's 2D focus (its end scene
          // focused the winner's side) was that game's, so the table opens whole again; open panels stay (the player's choice)
          ...(s.layoutGame !== match ? { layoutGame: match, focus: null } : {}),
        }));
        // -- table motion -- what just happened, for the tables to show (display only; game/motion/tableEvents.ts)
        if (prev && !replace && sameGame) publishTableEvents(prev, view, dragged);
      },
      onLobby: (lobby) => get().applyLobby(lobby),
      onStatus: (status, detail) => set({ status, statusDetail: detail ?? null }),
      onClosedByServer: (reason) => set({ status: "closed", statusDetail: reason }),
      onOutbox: (count) => set({ outbox: count }),
      onSignal: (signal) => window.dispatchEvent(new CustomEvent("fyodor:signal", { detail: signal })),
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
    const closed = finalBoardRefusal(view, String((action as { type?: unknown }).type ?? ""));
    if (closed) {
      // -- final board -- the server would refuse it: put any dragged card back and say why (not again while that shows)
      set({ pendingPositions: {} });
      if (!useToasts.getState().toasts.some((t) => t.text === closed)) toast(closed, "info");
      return false;
    }
    try {
      await conn.requestAction({ type: "action", action, as });
      const done = undoableSummary(action as Record<string, unknown>);
      // -- undo policy (gap 3) -- offer Undo only when this player may take back the action they just sent (theirs)
      const after = get().view;
      const me = after ? undoActor(after, get().actingAs) : null;
      if (done && after?.game.can_undo && !undoRefusal(after, me, "undo", me) && !after.game.undo_ask) toast(done, "info", { label: "Undo", run: () => void get().undo() });
      return true;
    } catch (e) {
      set({ pendingPositions: {} });
      const message = e instanceof Error ? e.message : String(e);
      if (message.startsWith("AUTOMATION ERROR")) set({ automationError: message });
      else {
        const type = String((action as { type?: unknown }).type ?? "");
        toast(`${message.replace(/\.?$/, ".")} Nothing changed. ${recoveryHint(message, type)}`.trim(), "error", { label: "Help", run: () => get().openDialog("help", HELP_TOPIC[type] ?? "") });
        // mark the card involved on the table, not only in the corner
        const a = action as { card_id?: unknown; card_ids?: unknown; id?: unknown };
        const card = typeof a.card_id === "string" ? a.card_id : Array.isArray(a.card_ids) && typeof a.card_ids[0] === "string" ? a.card_ids[0] : null;
        if (card) set({ errorCard: { id: card, at: Date.now() } });
      }
      return false;
    }
  },
  automationError: null,
  setAutomationError: (message) => set({ automationError: message }),

  undo: () => historyStep(get, "undo"),
  redo: () => historyStep(get, "redo"),

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

/** Undo or redo one step; the table's undo setting is explained here rather than sent to the server to refuse (gap 3). */
async function historyStep(get: () => GameStore, op: UndoOp): Promise<boolean> {
  const { conn, view, actingAs } = get();
  if (!conn || !view || !(op === "undo" ? view.game.can_undo : view.game.can_redo)) return false;
  if (op === "undo") {
    // -- quick undo request -- the server says when an undo must ask the table first: ask it (the bar shows the answer)
    const mode = undoMode(view, undoActor(view, actingAs));
    if (mode.kind === "waiting") {
      toast(mode.why, "info");
      return false;
    }
    if (mode.kind === "ask") {
      await undoRequest(view.game.id, "request").then(
        () => toast("Asked the table to undo it.", "info"),
        (e: Error) => toast(e.message, "error"),
      );
      return false; // not undone yet: a multi-step undo stops here
    }
  }
  const why = undoRefusal(view, undoActor(view, actingAs), op);
  if (why) {
    toast(why, "error");
    return false;
  }
  return conn.request({ type: op, as: view.game.mode === "local" ? actingAs : undefined }).then(
    () => true,
    (e: Error) => {
      toast(e.message, "error");
      return false;
    },
  );
}

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

/** Cosmetic: a subtle sound for the newest log lines (at most one per update). */
function playNewLogSounds(prev: GameView, next: GameView): void {
  const lastSeq = prev.log.length ? prev.log[prev.log.length - 1]!.seq : -1;
  const fresh = next.log.filter((e) => e.seq > lastSeq).slice(-3);
  for (const e of fresh.reverse()) {
    const text = e.parts.map((p) => ("t" in p ? p.t : "")).join("");
    const name = soundForLog(e.kind, text);
    if (name) {
      play(name);
      return;
    }
  }
}
