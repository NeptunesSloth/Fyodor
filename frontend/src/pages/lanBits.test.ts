import { describe, expect, it } from "vitest";
import type { GameSummary } from "../types/game";
import type { BroughtLibrary, MyDeck } from "../services/games";
import {
  firstOpenLobby,
  friendAddress,
  heldTokenFor,
  inviteCodeKey,
  inviteKey,
  seatLinks,
  friendFolder,
  listCount,
  ownDecks,
  joinLink,
  nearbyRows,
  orderGames,
  planInvite,
  readInvite,
  showInvitePopover,
  tableStatus,
  tileActions,
  withoutInvite,
  type NearbyServer,
  type NearbyTable,
} from "./lanBits";

const table = (over: Partial<NearbyTable> = {}): NearbyTable => ({
  id: "g1", name: "Thursday Commander", format: "commander", phase: "lobby", code: "ABC123", has_password: false,
  seats: 4, taken: 2, open: 2, players: ["Alice", "Bob"], turn: 0, ...over,
});
const server = (name: string, tables: NearbyTable[], url = `http://192.168.1.${name.length}:8000`): NearbyServer => ({ name, url, version: "0.1.0", tables });
const game = (over: Partial<GameSummary> = {}): GameSummary => ({
  id: "g1", name: "Friday", format: "commander", mode: "lan", phase: "lobby", code: "ABC123", has_password: false, turn: 0, spectators: 0, updated_at: 1,
  players: [
    { id: "p1", name: "Alice", claimed: true, connected: true },
    { id: "p2", name: "Seat 2", claimed: false, connected: false },
  ],
  ...over,
});
const q = (s: string) => new URLSearchParams(s);

describe("a join link's parameters", () => {
  it("reads the code, the name and what to do", () => {
    expect(readInvite(q("code=abc123&name=Dana&join=1"))).toEqual({ code: "ABC123", name: "Dana", action: "join", handoff: null });
    expect(readInvite(q("code=ABC123&watch=1"))).toEqual({ code: "ABC123", name: "", action: "watch", handoff: null });
    expect(readInvite(q("code=ABC123&name=Dana&join=1&handoff=tok_123-abcdefghijklmnop"))?.handoff).toBe("tok_123-abcdefghijklmnop");
    // a plain invite link only fills the code in, as before
    expect(readInvite(q("code=ABC123"))).toEqual({ code: "ABC123", name: "", action: "fill", handoff: null });
  });

  it("ignores links without a usable code and odd values", () => {
    expect(readInvite(q("join=1"))).toBeNull();
    expect(readInvite(q("code=ab&join=1"))).toBeNull();
    expect(readInvite(q("code=ABC%20123&join=1"))).toBeNull();
    expect(readInvite(q("tab=saves"))).toBeNull();
    expect(readInvite(q(`code=ABC123&join=1&name=${"x".repeat(80)}`))?.name).toHaveLength(40);
    expect(readInvite(q("code=ABC123&join=1&handoff=<script>"))?.handoff).toBeNull();
  });

  it("joins at once without a password, asks for it otherwise, and opens a seat this browser already holds", () => {
    const join = readInvite(q("code=ABC123&name=Dana&join=1"))!;
    const watch = readInvite(q("code=ABC123&watch=1"))!;
    const none = () => false;
    expect(planInvite(join, [game()], none)).toEqual({ kind: "join", spectate: false });
    expect(planInvite(watch, [game()], none)).toEqual({ kind: "join", spectate: true });
    expect(planInvite(join, [game({ has_password: true })], none)).toEqual({ kind: "password" });
    expect(planInvite(join, [game()], (id) => id === "g1")).toEqual({ kind: "open", gameId: "g1" });
    // not listed (closed, or a typo): the server decides and says why
    expect(planInvite(join, [], none)).toEqual({ kind: "join", spectate: false });
    expect(planInvite(readInvite(q("code=ABC123"))!, [game()], none)).toEqual({ kind: "fill" });
  });

  it("comes off the address once handled, keeping anything else", () => {
    expect(withoutInvite("#/play?code=ABC123&name=Dana&join=1&handoff=t")).toBe("#/play");
    expect(withoutInvite("#/play?code=ABC123&watch=1&tab=saves")).toBe("#/play?tab=saves");
    expect(withoutInvite("#/play")).toBe("#/play");
  });
});

describe("the link to a table on another computer", () => {
  it("opens that computer's Play page ready to join", () => {
    expect(joinLink("http://192.168.1.7:8000", "ABC123", { name: "Dana Ö" })).toBe("http://192.168.1.7:8000/#/play?code=ABC123&name=Dana+%C3%96&join=1");
    expect(joinLink("http://192.168.1.7:8000/", "ABC123", { watch: true })).toBe("http://192.168.1.7:8000/#/play?code=ABC123&watch=1");
    expect(joinLink("http://192.168.1.7:8000", "ABC123", { name: "Player", handoff: "tok" })).toBe("http://192.168.1.7:8000/#/play?code=ABC123&join=1&handoff=tok");
  });
});

describe("games on the network", () => {
  it("says where a table stands", () => {
    expect(tableStatus(table())).toBe("In the lobby · 2 of 4 seats taken");
    expect(tableStatus(table({ taken: 1, seats: 3 }))).toBe("In the lobby · 1 of 3 seats taken");
    expect(tableStatus(table({ phase: "playing", turn: 6 }))).toBe("Turn 6");
  });

  it("lists open lobbies first, across computers", () => {
    const rows = nearbyRows([
      server("DESKTOP-42", [table({ id: "a", phase: "playing", turn: 3 }), table({ id: "b", open: 0, taken: 4 })]),
      server("LAPTOP", [table({ id: "c" })]),
    ]);
    expect(rows.map((r) => r.table.id)).toEqual(["c", "b", "a"]);
    expect(rows[0]!.server.name).toBe("LAPTOP");
  });

  it("offers the launcher the first open lobby", () => {
    expect(firstOpenLobby([server("A", [table({ phase: "playing" }), table({ id: "full", open: 0, taken: 4 })])])).toBeNull();
    expect(firstOpenLobby([server("A", [table({ phase: "playing" })]), server("B", [table({ id: "x" })])])?.table.id).toBe("x");
    expect(firstOpenLobby(null)).toBeNull();
  });
});

describe("tables on the Play page of another device", () => {
  it("shows open lobbies first", () => {
    const games = [
      game({ id: "playing", phase: "playing", turn: 4 }),
      game({ id: "full", players: [{ id: "p1", name: "A", claimed: true, connected: true }] }),
      game({ id: "open" }),
    ];
    expect(orderGames(games).map((g) => g.id)).toEqual(["open", "full", "playing"]);
  });

  it("offers Join with an open seat, Watch always, and Open for a seat this browser holds", () => {
    expect(tileActions(game(), false)).toEqual({ open: false, join: true, watch: true });
    expect(tileActions(game({ players: [{ id: "p1", name: "A", claimed: true, connected: true }] }), false)).toEqual({ open: false, join: false, watch: true });
    expect(tileActions(game({ phase: "playing" }), false)).toEqual({ open: false, join: true, watch: true });
    expect(tileActions(game(), true)).toEqual({ open: true, join: false, watch: false });
    expect(tileActions(game({ mode: "local", code: null }), false)).toEqual({ open: false, join: false, watch: false });
  });
});

describe("the decks a player brings to a seat", () => {
  const brought: BroughtLibrary = {
    from: "DANA-PC", unknown: [],
    decks: [{ name: "Goblins", commanders: ["Krenko, Mob Boss"], text: "1 Krenko, Mob Boss", cover_id: "c1" }],
  };
  const mine: MyDeck = {
    id: "m1", name: "Saved here", body: { name: "Saved here", text: "1 Atraxa" }, commanders: ["Atraxa, Praetors' Voice"], savedAt: 1,
    entries: [{ section: "commander", quantity: 1, name: "Atraxa, Praetors' Voice", printing_id: "a1" }, { section: "main", quantity: 1, name: "Sol Ring", printing_id: "s1" }],
  };

  it("are the ones from their own computer first", () => {
    const own = ownDecks(brought, [mine])!;
    expect(own.label).toBe("Your decks, from DANA-PC");
    expect(own.brought).toBe(true);
    expect(own.decks).toEqual([{ key: "b0", name: "Goblins", commanders: ["Krenko, Mob Boss"], cover: "c1", body: { name: "Goblins", text: "1 Krenko, Mob Boss" } }]);
  });

  it("or, in a browser with no Fyodor of its own, its My decks", () => {
    const own = ownDecks({ from: null, decks: [], unknown: [] }, [mine])!;
    expect(own.label).toBe("Your decks in this browser");
    expect(own.brought).toBe(false);
    expect(own.decks[0]).toEqual({ key: "m1", name: "Saved here", commanders: ["Atraxa, Praetors' Voice"], cover: "a1", body: mine.body });
    expect(ownDecks(null, [])).toBeNull();
  });
});

describe("friends' decks", () => {
  it("reads a typed address", () => {
    expect(friendAddress("192.168.1.20:8123")).toBe("http://192.168.1.20:8123");
    expect(friendAddress(" http://10.0.0.5:8000/ ")).toBe("http://10.0.0.5:8000");
    expect(friendAddress("10.0.0.5")).toBe("http://10.0.0.5:8000");
    expect(friendAddress("localhost:8766")).toBe("http://127.0.0.1:8766");
    expect(friendAddress("https://example.com")).toBeNull();
    expect(friendAddress("")).toBeNull();
  });

  it("counts a list and names the folder", () => {
    expect(listCount("Commander\n1 Krenko, Mob Boss\nDeck\n12 Mountain\n2x Shock\n")).toBe(15);
    expect(friendFolder("DANA-PC")).toBe("From DANA-PC");
    expect(friendFolder(" ")).toBe("From a friend");
  });
});

describe("invites through the tunnel", () => {
  const q = (s: string) => new URLSearchParams(s);
  it("always ask for the password unless the table is held", () => {
    const join = readInvite(q("code=ABC123&join=1"))!;
    const g = [{ id: "g1", code: "ABC123", has_password: false }] as never;
    expect(planInvite(join, g, () => false, true)).toEqual({ kind: "password" });
    expect(planInvite(join, [], () => false, true)).toEqual({ kind: "password" });
    expect(planInvite(join, g, () => true, true)).toEqual({ kind: "open", gameId: "g1" });
    expect(planInvite(readInvite(q("code=ABC123"))!, g, () => false, true)).toEqual({ kind: "fill" });
    expect(planInvite(join, g, () => false, false)).toEqual({ kind: "join", spectate: false });
  });
  it("shows the invite popover to the host even without a LAN link", () => {
    expect(showInvitePopover(true, null)).toBe(true);
    expect(showInvitePopover(true, "http://192.168.1.2:8000/#/play?code=A")).toBe(true);
    expect(showInvitePopover(false, "http://192.168.1.2:8000/#/play?code=A")).toBe(false);
  });
});

describe("opening the invite link again", () => {
  const store = (entries: Record<string, string>) => (key: string) => entries[key] ?? null;
  const tokens: Record<string, string> = { g1: "tok-g1" };
  const seat = (id: string) => tokens[id] ?? null;
  it("sends the seat token this browser holds for the table the code opened", () => {
    expect(inviteKey(" abcdefghij ")).toBe("fyodor.invite.ABCDEFGHIJ");
    expect(heldTokenFor("ABCDEFGHIJ", store({ "fyodor.invite.ABCDEFGHIJ": "g1" }), seat)).toBe("tok-g1");
    expect(heldTokenFor("abcdefghij", store({ "fyodor.invite.ABCDEFGHIJ": "g1" }), seat)).toBe("tok-g1");
  });
  it("sends none for a code it never joined with, or a table it holds no seat at", () => {
    expect(heldTokenFor("ABCDEFGHIJ", store({}), seat)).toBeNull();
    expect(heldTokenFor("ABCDEFGHIJ", store({ "fyodor.invite.ABCDEFGHIJ": "g2" }), seat)).toBeNull();
  });
  it("finds the code a table was joined with (a tunnel view never carries the LAN code)", () => {
    expect(inviteCodeKey("g1")).toBe("fyodor.invite-code.g1");
  });
});

describe("the host's seat link", () => {
  const path = "/#/game/g1?seat=p2&token=abc";
  it("is a LAN link when the table isn't shared", () => {
    expect(seatLinks(path, "http://127.0.0.1:8000/", null)).toEqual([{ label: "On this network", url: "http://127.0.0.1:8000/#/game/g1?seat=p2&token=abc" }]);
  });
  it("adds an internet link on the share's address when the table is shared", () => {
    expect(seatLinks(path, "http://192.168.1.5:8000/", "https://fyodor-x.trycloudflare.com/#/play?code=ABCDEFGHIJ&join=1")).toEqual([
      { label: "On this network", url: "http://192.168.1.5:8000/#/game/g1?seat=p2&token=abc" },
      { label: "Over the internet", url: "https://fyodor-x.trycloudflare.com/#/game/g1?seat=p2&token=abc" },
    ]);
  });
  it("ignores a share link that isn't an https address", () => {
    expect(seatLinks(path, "http://127.0.0.1:8000/", "not a url")).toHaveLength(1);
    expect(seatLinks(path, "http://127.0.0.1:8000/", "http://evil.example/")).toHaveLength(1);
  });
});
