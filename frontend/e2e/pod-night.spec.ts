import { expect, test, type Page } from "@playwright/test";
import {
  ALICE_DECK, ALICE_SECRETS, BOB_DECK, act, bringDeck, hostLobby, joinLobby, keepAll, newPlayer, playFromHand, recordTraffic, serverView,
} from "./helpers";

type View = { zones: Record<string, string[]>; cards: Record<string, { name?: string; hidden?: boolean }>; players: { id: string; life: number }[] };
const life = async (page: Page, gameId: string, pid: string) =>
  ((await serverView(page, gameId)) as unknown as View).players.find((p) => p.id === pid)!.life;

/**
 * Full pod regression: four devices on the LAN play a game night end to end — lobby, decks,
 * mulligans, plays, life, hidden information, a dropped device, a snapshot restore and the
 * result in pod stats.
 */
test("pod night: four players from lobby to pod stats", async ({ browser }) => {
  test.setTimeout(150_000);
  const host = await newPlayer(browser);
  const guests = [await newPlayer(browser, true), await newPlayer(browser, true), await newPlayer(browser, true)];
  const traffic = guests.map((g) => recordTraffic(g.page));
  const { gameId, code } = await hostLobby(host.page, { name: "Alice" });
  const names = ["Bob", "Cara", "Dan"];
  for (const [i, g] of guests.entries()) await joinLobby(g.page, code, names[i]!);

  // Everyone brings a deck and gets ready; the host starts.
  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  for (const [i, g] of guests.entries()) await bringDeck(g.page, BOB_DECK, `Goblins ${i + 1}`);
  const pages = [host.page, ...guests.map((g) => g.page)];
  for (const p of pages) await p.getByTestId("ready").click();
  await expect(host.page.getByTestId("start-game")).toBeEnabled();
  await host.page.getByTestId("start-game").click();
  for (const p of pages) await expect(p.locator(".game-screen")).toBeVisible();

  // Opening hands, then everyone plays a card that the whole table sees.
  await keepAll(...pages);
  const played: string[] = [];
  for (const p of pages) played.push(await playFromHand(p));
  for (const p of pages) for (const id of played) await expect(p.locator(`.table-card[data-card-id="${id}"]`)).toBeVisible();

  // Life and commander damage from the plates sync to every device.
  await guests[1]!.page.getByTestId("life-minus-p3").click();
  for (const p of pages) await expect(p.getByTestId("life-p3")).toHaveText("39");
  const bobView = (await serverView(guests[0]!.page, gameId)) as unknown as { players: { id: string; commanders: { key: string }[] }[] };
  const krenko = bobView.players.find((p) => p.id === "p2")!.commanders[0]!.key;
  await act(guests[0]!.page, gameId, { type: "commander_damage", player: "p1", commander: krenko, delta: 3 });
  await expect.poll(() => life(host.page, gameId, "p1")).toBe(37);

  // A device drops and comes back: same seat, same hand.
  const dan = guests[2]!;
  const danHand = ((await serverView(dan.page, gameId)) as unknown as View).zones["p4:hand"];
  await dan.page.close();
  await expect(host.page.getByTestId("presence-p4")).toHaveText("Reconnecting…");
  dan.page = await dan.context.newPage();
  traffic[2] = recordTraffic(dan.page);
  pages[3] = dan.page;
  await dan.page.goto(`/#/game/${gameId}`);
  await expect(dan.page.locator(".game-screen")).toBeVisible();
  await expect(host.page.getByTestId("presence-p4")).toHaveText("Connected");
  expect(((await serverView(dan.page, gameId)) as unknown as View).zones["p4:hand"]).toEqual(danHand);

  // A named snapshot, a misplay, and the host restores the table for everyone.
  const token = await host.page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
  const snap = await (await host.page.request.post(`/api/games/${gameId}/snapshots`, { data: { name: "Before the swing" }, headers: { "X-Seat-Token": token! } })).json();
  await act(guests[0]!.page, gameId, { type: "life", player: "p2", delta: -20 });
  for (const p of pages) await expect(p.getByTestId("life-p2")).toHaveText("20");
  expect((await host.page.request.post(`/api/games/${gameId}/snapshots/${snap.id}/restore`, { headers: { "X-Seat-Token": token! } })).ok()).toBeTruthy();
  for (const p of pages) await expect(p.getByTestId("life-p2")).toHaveText("40");

  // Hidden information: Alice's hand and library never reached any other device.
  const aliceView = (await serverView(host.page, gameId)) as unknown as View;
  // Alice's unique cards are secret unless she put one on the battlefield.
  const secrets = ALICE_SECRETS.filter((n) => n !== aliceView.cards[played[0]!]!.name);
  expect(secrets.length).toBeGreaterThanOrEqual(3);
  for (const t of traffic) for (const s of secrets) expect(t.text()).not.toContain(s);
  for (const g of guests) {
    const v = (await serverView(g.page, gameId)) as unknown as View;
    for (const id of v.zones["p1:hand"]!) expect(v.cards[id]!.name).toBeUndefined();
  }

  // Cara wins; the host records it and it shows up in pod stats.
  await host.page.getByTestId("end-game").click();
  await host.page.getByTestId("winner-p3").click();
  await host.page.getByTestId("confirm-result").click();
  await expect(host.page.getByTestId("result-confirm")).toContainText("Winner: Cara");
  await host.page.getByTestId("record-result").click();
  await expect(host.page.getByTestId("result-recorded")).toContainText("Cara");
  await host.page.goto("/#/stats");
  await expect(host.page.getByTestId("pod-row-Cara").locator("td").nth(2)).toHaveText("1");

  for (const c of [host, ...guests]) await c.context.close();
});
