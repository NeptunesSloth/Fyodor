import { expect, test } from "@playwright/test";
import { act, keepAll, seatToken, serverView, startLanGame } from "./helpers";

type View = { zones: Record<string, string[]>; cards: Record<string, { name?: string; hidden?: boolean }>; players: { id: string; life: number }[] };

const handNames = (v: View, pid: string) => v.zones[`${pid}:hand`]!.map((id) => v.cards[id]!.name).sort();

test("refresh keeps the seat and hand; save → close → load restores the table", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  await keepAll(host.page, guest.page);
  await act(guest.page, gameId, { type: "draw", count: 2 });
  await act(host.page, gameId, { type: "life", player: "p2", delta: -7 });
  const before = (await serverView(guest.page, gameId)) as unknown as View;
  expect(handNames(before, "p2")).toHaveLength(9);

  // The guest's browser reloads (or crashes and comes back): same seat, same private hand.
  await guest.page.reload();
  await expect(guest.page.locator(".game-screen")).toBeVisible();
  const after = (await serverView(guest.page, gameId)) as unknown as View;
  expect(handNames(after, "p2")).toEqual(handNames(before, "p2"));
  await expect(guest.page.locator("main.table > .hand .hand-card")).toHaveCount(9);

  // The host saves, closes the table and loads the save.
  const token = (await seatToken(host.page, gameId))!;
  const save = await host.page.request.post(`/api/games/${gameId}/save`, { data: { name: "E2E save" }, headers: { "X-Seat-Token": token } });
  expect(save.ok()).toBeTruthy();
  const saveId = ((await save.json()) as { id: string }).id;
  expect((await host.page.request.delete(`/api/games/${gameId}`)).status()).toBe(204);
  const loaded = await host.page.request.post(`/api/saves/${saveId}/load`, { data: { mode: "local" } });
  expect(loaded.ok()).toBeTruthy();
  const localView = (await (await host.page.request.get(`/api/games/${gameId}/view?viewer=all`)).json()) as View;
  expect(handNames(localView, "p2")).toEqual(handNames(before, "p2"));
  expect(localView.players.find((p) => p.id === "p2")!.life).toBe(33);

  await host.context.close();
  await guest.context.close();
});
