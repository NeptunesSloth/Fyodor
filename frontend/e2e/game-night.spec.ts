import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, bringDeck, hostLobby, joinLobby, keepAll, newPlayer, serverView } from "./helpers";

/**
 * Game night (docs/GAME_NIGHT_FLOW.md) on two devices: the pod-rule d20 intro, an agreed ending,
 * the result spotlight, an all-rematch vote (the winner goes last) and a return to the lobby with
 * every deck still selected. SHOT_DIR, when set, keeps screenshots of each moment.
 */
const OUT = process.env.SHOT_DIR ?? "";
const shot = async (page: Page, name: string) => {
  if (OUT) await page.screenshot({ path: `${OUT}/night-${name}.png` });
};

type NightView = { viewer: string; game: { night: { number: number; order_source: string; previous_winner: string | null } } };

async function seatPost(page: Page, gameId: string, path: string, data: Record<string, unknown>) {
  const token = await page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
  const res = await page.request.post(`/api/games/${gameId}/night/${path}`, { data, headers: token ? { "X-Seat-Token": token } : {} });
  expect(res.ok(), await res.text()).toBeTruthy();
  return res.json();
}

test("game night: d20 intro, agreed ending, spotlight, rematch and back to the lobby", async ({ browser }) => {
  test.setTimeout(180_000);
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  for (const p of [host.page, guest.page]) {
    await p.setViewportSize({ width: 1600, height: 900 });
    await p.addInitScript(() => localStorage.setItem("fyodor.nightScenes", "1"));
  }
  const { gameId, code } = await hostLobby(host.page, { name: "Alice", turnOrder: "pod" });
  await joinLobby(guest.page, code, "Bob");
  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  await bringDeck(guest.page, BOB_DECK, "Goblins");
  await host.page.getByTestId("ready").click();
  await guest.page.getByTestId("ready").click();
  await host.page.getByTestId("start-game").click();
  const pages = [host.page, guest.page];

  // Game 1: everyone sees the same server-rolled d20s and the resulting order.
  for (const p of pages) await expect(p.getByTestId("game-intro")).toBeVisible();
  await expect(host.page.getByTestId("game-intro")).toContainText("Game 1");
  await expect(host.page.locator(".night-die").first()).toBeVisible();
  await host.page.waitForTimeout(900);
  await shot(host.page, "intro");
  for (const p of pages) {
    await p.keyboard.press("Escape");
    await expect(p.getByTestId("game-intro")).toHaveCount(0);
  }
  const first = (await serverView(host.page, gameId)) as unknown as NightView;
  expect(first.game.night.order_source).toBe("d20");
  await keepAll(...pages);

  // Bob proposes that Alice wins; Alice agrees on her screen.
  const alice = first.viewer;
  await seatPost(guest.page, gameId, "propose", { result_type: "single", winners: [alice] });
  await expect(host.page.getByTestId("night-proposal")).toContainText("Bob proposes ending the game");
  await shot(host.page, "proposal");
  await host.page.getByTestId("proposal-agree").click();

  // The spotlight: Victory for Alice, Defeat for Bob; then the rematch vote.
  await expect(host.page.getByTestId("result-spotlight")).toContainText("Victory");
  await expect(guest.page.getByTestId("result-spotlight")).toContainText("Defeat");
  await host.page.waitForTimeout(900);
  await shot(host.page, "victory");
  await shot(guest.page, "defeat");
  for (const p of pages) await expect(p.getByTestId("night-result")).toBeVisible({ timeout: 15_000 });
  await shot(host.page, "vote");
  await host.page.getByTestId("vote-rematch").click();
  await expect(guest.page.getByTestId("night-result")).toContainText("Rematch");
  await guest.page.getByTestId("vote-rematch").click();

  // Game 2: a fresh game where last game's winner (Alice) goes last.
  await expect(host.page.getByTestId("game-intro")).toContainText("Game 2");
  await expect(host.page.getByTestId("game-intro")).toContainText("Won last game");
  await shot(host.page, "intro-rematch");
  const second = (await serverView(host.page, gameId)) as unknown as NightView;
  expect(second.game.night.order_source).toBe("winner_last");
  expect(second.viewer).toBe("p2");
  for (const p of pages) await p.keyboard.press("Escape");
  await keepAll(...pages);

  // Game 2 ends in a draw; Bob wants the lobby: the pod goes back with decks still chosen.
  await seatPost(host.page, gameId, "propose", { result_type: "draw", winners: [] });
  await guest.page.getByTestId("proposal-agree").click();
  for (const p of pages) await expect(p.getByTestId("night-result")).toBeVisible({ timeout: 15_000 });
  await guest.page.getByTestId("vote-lobby").click();
  for (const p of pages) await expect(p.getByTestId("lobby")).toBeVisible();
  await expect(guest.page.getByTestId("lobby")).toContainText("Goblins");
  const recap = host.page.getByTestId("session-recap");
  await expect(recap).toContainText("2 games");
  await expect(recap).toContainText("Alice won with Atraxa, Praetors' Voice (agreed)");
  await expect(recap).toContainText("Draw");
  await shot(host.page, "lobby-again");
});

test("eliminated: a short scene, then opening-hand practice with your own deck", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.nightScenes", "1");
    localStorage.setItem("fyodor.welcomeDone", "1");
  });
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string; name: string }[];
  const res = await page.request.post("/api/games", { data: { name: "Out", mode: "local", automation: "full", mulligan_rule: "none",
    players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i % 2]!.id })) } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("game-intro")).toBeVisible();
  await expect(page.getByTestId("game-intro").locator(".night-row").first()).toContainText(/goes first|Alice|Bob|Cara/);
  await page.keyboard.press("Escape"); // past the intro
  await expect(page.getByTestId("game-intro")).toHaveCount(0);
  const conceded = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "concede" }, as: "p1" } });
  expect(conceded.ok(), await conceded.text()).toBeTruthy();
  await expect(page.getByTestId("eliminated-scene")).toContainText("Eliminated");
  await page.waitForTimeout(600);
  await shot(page, "eliminated");
  await expect(page.getByTestId("eliminated-hub")).toBeVisible({ timeout: 10_000 });
  await shot(page, "eliminated-hub");
  await page.getByRole("button", { name: "Practise opening hands" }).click();
  await expect(page.getByTestId("hand-sim").locator(".sim-card")).toHaveCount(7);
  await page.waitForTimeout(500);
  await shot(page, "hand-sim");
  // the live game didn't move: practice never touches it
  const v = (await (await page.request.get(`/api/games/${gameId}/view`)).json()) as { players: { id: string }[]; zones: Record<string, string[]> };
  expect(v.zones["p1:hand"]).toHaveLength(0);
});

for (const renderer of ["2d", "3d"] as const) {
  test(`out of the game (${renderer}): the dial only watches, the server refuses step changes, the open log sits beside the dial`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.addInitScript((r) => {
      localStorage.setItem("fyodor.welcomeDone", "1");
      localStorage.setItem("fyodor.renderer", r);
    }, renderer);
    for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
    const decks = (await (await page.request.get("/api/decks")).json()) as { id: string; name: string }[];
    const res = await page.request.post("/api/games", { data: { name: "Out", mode: "local", automation: "full", mulligan_rule: "none",
      players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i % 2]!.id })) } });
    const gameId = ((await res.json()) as { game: { id: string } }).game.id;
    await page.goto(`/#/game/${gameId}`);
    await expect(page.getByTestId("turn-dial").or(page.getByTestId("priority-bar"))).toBeVisible(); // (no night scenes: no intro)
    const conceded = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "concede" }, as: "p1" } });
    expect(conceded.ok(), await conceded.text()).toBeTruthy();
    await page.getByRole("button", { name: "Keep watching" }).click({ timeout: 15_000 }); // the hub folds to its pill
    // 800.4a: Alice left the game; the dial keeps the turn and step but offers no step controls
    const dial = page.getByTestId("turn-dial");
    await expect(page.getByTestId("priority-holder")).toHaveText("You're out: watching");
    await expect(dial.getByRole("button", { name: /Next turn|Previous step|To combat|Next step/ })).toHaveCount(0);
    await expect(page.getByTestId("current-phase")).toBeDisabled();
    const turn = ((await (await page.request.get(`/api/games/${gameId}/view`)).json()) as { turn: unknown }).turn;
    await page.keyboard.press("Shift+N"); // the hotkey sends nothing either
    for (const action of [{ type: "next_turn" }, { type: "phase", to: "next" }]) {
      const stepped = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as: "p1" } });
      expect(stepped.status()).toBe(409);
      expect(await stepped.text()).toContain("left this game");
    }
    expect(((await (await page.request.get(`/api/games/${gameId}/view`)).json()) as { turn: unknown }).turn).toEqual(turn);
    // the open log drawer and the dial don't cover each other
    await page.getByTestId("log-drawer").getByRole("button").click();
    await expect(page.locator(".log-drawer.open")).toBeVisible();
    const a = (await page.locator(".log-drawer.open").boundingBox())!;
    const b = (await page.locator(".turn-dial-wrap").boundingBox())!;
    expect(a.x >= b.x + b.width || b.x >= a.x + a.width || a.y >= b.y + b.height || b.y >= a.y + a.height).toBeTruthy();
    await page.waitForTimeout(300);
    await shot(page, `out-dial-${renderer}`);
  });
}

test("nudge: the waiting player gets one quiet reminder", async ({ browser }) => {
  test.setTimeout(120_000);
  const { startLanGame } = await import("./helpers");
  const { host, guest, gameId } = await startLanGame(browser);
  await keepAll(host.page, guest.page);
  const v = (await serverView(host.page, gameId)) as unknown as { viewer: string; turn: { active_player: string } };
  const [waiting, nudger] = v.turn.active_player === v.viewer ? [host.page, guest.page] : [guest.page, host.page];
  await expect(waiting.getByTestId("nudge")).toHaveCount(0); // never to yourself
  await nudger.getByTestId("nudge").click();
  await expect(waiting.getByText(/nudged you: the table is waiting on your action/)).toBeVisible();
  await expect(nudger.getByTestId("nudge")).toBeDisabled(); // cooldown
});
