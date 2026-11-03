import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "../components/Toasts";
import { useGame } from "../state/gameStore";
import { SPECTATOR, type GameView } from "../types/game";
import { HOTKEYS, type HotkeyId } from "./hotkeys";
import { HISTORY_KEYS, MOVING_KEYS, isOut, outKeyBlocked, outReason, outRefusal } from "./outOfGame";

const OUT_WORDS = "You're out of this game (you conceded): you can watch and chat, but not move the game.";

function view(over: { viewer?: string; mode?: "lan" | "local"; conceded?: string[]; lost?: Record<string, string>; rules?: boolean; id?: string; host?: boolean } = {}): GameView {
  return {
    viewer: over.viewer ?? "p3",
    seat_order: ["p1", "p2", "p3"],
    players: ["Ann", "Ben", "Cat"].map((name, i) => ({ id: `p${i + 1}`, name })),
    turn: { active_player: "p1", number: 4, phase: "main1" },
    cards: {},
    zones: {},
    stack: [],
    game: { id: over.id ?? "g", mode: over.mode ?? "lan", seats: { p1: {}, p2: {}, p3: {} }, host_seat: "p1", night: { number: 1, result: null }, settings: {},
      can_undo: true, can_redo: true, undo_host: over.host ?? false },
    rules: over.rules === false ? null : { conceded: over.conceded ?? [], lost: over.lost ?? {}, paused: false, priority: "p1", decision: null, hints: {} },
  } as unknown as GameView;
}

describe("who is out of the game (the turn dial's test)", () => {
  it("a seated player who conceded or lost, while the rules engine runs the game", () => {
    expect(isOut(view({ conceded: ["p3"] }), "p3")).toBe(true);
    expect(isOut(view({ lost: { p3: "0 or less life" } }), "p3")).toBe(true);
    expect(outReason(view({ conceded: ["p3"] }), "p3")).toBe(OUT_WORDS);
    expect(outReason(view({ lost: { p3: "0 or less life" } }), "p3")).toBe(OUT_WORDS.replace("conceded", "lost"));
  });
  it("not the players still in, a spectator, or a table without the rules engine", () => {
    expect(isOut(view({ conceded: ["p3"] }), "p1")).toBe(false);
    expect(isOut(view({ viewer: SPECTATOR, conceded: ["p3"] }), "p3")).toBe(false);
    expect(isOut(view({ rules: false }), "p3")).toBe(false);
    expect(isOut(null, "p3")).toBe(false);
    expect(outReason(view(), "p3")).toBeNull();
  });
});

describe("what the table still sends for a player who is out (app/game/out_of_game.py)", () => {
  const out = view({ conceded: ["p3"] });
  it("refuses the table tools that move the game, with the server's words", () => {
    for (const type of ["draw", "phase", "next_turn", "resolve_top", "move", "tap", "life", "set_life", "untap_all", "mill", "look_top", "reveal_top", "mulligan",
      "set_position", "commander_damage", "counter", "shuffle", "create_token", "response_respond", "response_close"]) {
      expect(outRefusal(out, "p3", type)).toBe(OUT_WORDS);
    }
  });
  it("keeps what anyone watching does, and the rules intents (the engine answers those)", () => {
    for (const type of ["chat", "roll", "coin", "rename_player", "set_appearance", "end_view", "response_pass", "response_auto", "pass_priority", "concede", "set_prefs", "set_stops",
      "configure", "remove_player", "set_table_playmat", "restart_game", "mulligan_finish"]) {
      expect(outRefusal(out, "p3", type)).toBeNull();
    }
  });
  it("the players still in send everything", () => {
    expect(outRefusal(out, "p1", "draw")).toBeNull();
    expect(outRefusal(view(), "p3", "next_turn")).toBeNull();
  });
});

describe("the shortcuts of a player who is out", () => {
  it("the keys that would move the game do nothing, and the first one says why, once", () => {
    const said: string[] = [];
    const out = view({ conceded: ["p3"], id: "keys" });
    for (const id of ["draw", "next_step", "next_turn", "untap_all", "tap", "turn_over", "to_graveyard", "respond", "draw"] as HotkeyId[]) {
      expect(outKeyBlocked(out, "p3", id, (t) => said.push(t))).toBe(true);
    }
    expect(said).toEqual([OUT_WORDS]);
  });
  it("looking around, the log, help, pings, dice, sorting, Escape and auto-pass keep working", () => {
    const said: string[] = [];
    const out = view({ conceded: ["p3"], id: "look" });
    const keep = HOTKEYS.map((h) => h.id).filter((id) => !MOVING_KEYS.has(id) && !HISTORY_KEYS.has(id));
    expect(keep).toEqual(expect.arrayContaining(["cam_seat", "cam_player", "cam_table", "cam_focus", "cam_stack", "cam_combat", "cam_reset", "cam_names", "ping", "hud",
      "help", "dice", "hand_sort", "cancel", "auto_pass", "pass"]));
    for (const id of keep) expect(outKeyBlocked(out, "p3", id, (t) => said.push(t))).toBe(false);
    expect(said).toEqual([]);
  });
  it("undo and redo do nothing for a player who is out (the server refuses them), except the host's", () => {
    const said: string[] = [];
    expect([...HISTORY_KEYS].sort()).toEqual(["redo", "undo"]);
    for (const id of ["undo", "redo", "undo"] as HotkeyId[]) expect(outKeyBlocked(view({ conceded: ["p3"], id: "history" }), "p3", id, (t) => said.push(t))).toBe(true);
    expect(said).toEqual([OUT_WORDS]);
    for (const id of HISTORY_KEYS) {
      expect(outKeyBlocked(view({ conceded: ["p3"], id: "host", host: true }), "p3", id, (t) => said.push(t))).toBe(false); // the host takes a concession back
      expect(outKeyBlocked(view({ conceded: ["p3"] }), "p1", id, (t) => said.push(t))).toBe(false);
      expect(outKeyBlocked(view({ viewer: "local", mode: "local", conceded: ["p3"], host: true }), "p3", id, (t) => said.push(t))).toBe(false);
    }
    expect(said).toEqual([OUT_WORDS]);
  });
  it("every moving key is a real shortcut, and a player still in is never stopped", () => {
    const ids = new Set(HOTKEYS.map((h) => h.id));
    for (const id of MOVING_KEYS) expect(ids.has(id)).toBe(true);
    for (const id of MOVING_KEYS) expect(outKeyBlocked(view({ conceded: ["p3"] }), "p1", id, () => undefined)).toBe(false);
    expect(outKeyBlocked(view({ viewer: SPECTATOR }), "p1", "draw", () => undefined)).toBe(false);
  });
});

describe("the store doesn't send what the server refuses from a player who is out", () => {
  const requestAction = vi.fn(() => Promise.resolve());
  beforeEach(() => {
    requestAction.mockClear();
    useToasts.setState({ toasts: [] });
    useGame.setState({ conn: { requestAction } as never, view: view({ conceded: ["p3"] }), actingAs: null, pendingPositions: { c1: [1, 2] } });
  });

  it("a draw, a drag or a life change is not sent: the card goes back and the reason shows once", async () => {
    expect(await useGame.getState().send({ type: "draw", player: "p3", count: 1 } as never)).toBe(false);
    expect(await useGame.getState().send({ type: "set_position", moves: [["c1", 1, 2]] } as never)).toBe(false);
    expect(await useGame.getState().send({ type: "life", player: "p1", delta: -1 } as never)).toBe(false);
    expect(requestAction).not.toHaveBeenCalled();
    expect(useGame.getState().pendingPositions).toEqual({});
    expect(useToasts.getState().toasts.map((t) => [t.text, t.kind])).toEqual([[OUT_WORDS, "info"]]);
  });

  it("chat and dice still go out, and so does everything from the players still in", async () => {
    expect(await useGame.getState().send({ type: "chat", text: "gg" } as never)).toBe(true);
    expect(await useGame.getState().send({ type: "roll", sides: 20 } as never)).toBe(true);
    useGame.setState({ view: view({ viewer: "p1", conceded: ["p3"] }) });
    expect(await useGame.getState().send({ type: "draw", player: "p1", count: 1 } as never)).toBe(true);
    expect(requestAction).toHaveBeenCalledTimes(3);
  });

  it("undo and redo are not sent for a player who is out; the host's are", async () => {
    const request = vi.fn(() => Promise.resolve());
    useGame.setState({ conn: { requestAction, request } as never });
    expect(await useGame.getState().undo()).toBe(false);
    expect(await useGame.getState().redo()).toBe(false);
    expect(request).not.toHaveBeenCalled();
    expect(useToasts.getState().toasts.map((t) => t.text)).toContain(OUT_WORDS);
    useGame.setState({ view: view({ conceded: ["p3"], host: true }) });
    expect(await useGame.getState().undo()).toBe(true);
    expect(request).toHaveBeenCalledWith({ type: "undo", as: undefined });
  });

  it("at a hot-seat table it is the seat the table acts as that counts", async () => {
    useGame.setState({ view: view({ viewer: "local", mode: "local", conceded: ["p3"] }), actingAs: "p3" });
    expect(await useGame.getState().send({ type: "next_turn" } as never)).toBe(false);
    useGame.setState({ actingAs: "p2" });
    expect(await useGame.getState().send({ type: "next_turn" } as never)).toBe(true);
    expect(requestAction).toHaveBeenCalledTimes(1);
  });
});
