import { expect, test } from "@playwright/test";
import { keepAll, newPlayer, serverView, startLanGame } from "./helpers";

type View = { zones: Record<string, string[]>; viewer: string };

test("disconnect / reconnect keeps the seat; host sees presence and can reassign a seat", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  const alice = host.page;
  await keepAll(alice, guest.page);
  const hand = ((await serverView(guest.page, gameId)) as unknown as View).zones["p2:hand"]!;
  await expect(alice.getByTestId("presence-p2")).toHaveText("Connected");

  // Bob's tab closes (browser crash, Wi-Fi drop…): the host sees him reconnecting.
  await guest.page.close();
  await expect(alice.getByTestId("presence-p2")).toHaveText("Reconnecting…");

  // He comes back in the same browser: same seat, same hand, no new player.
  const bob = await guest.context.newPage();
  await bob.goto(`/#/game/${gameId}`);
  await expect(bob.locator(".game-screen")).toBeVisible();
  await expect(alice.getByTestId("presence-p2")).toHaveText("Connected");
  const back = (await serverView(bob, gameId)) as unknown as View;
  expect(back.viewer).toBe("p2");
  expect(back.zones["p2:hand"]).toEqual(hand);
  expect(((await serverView(alice, gameId)) as { players: unknown[] }).players).toHaveLength(2);

  // Host tools are tucked away under ⋯ and only for the host.
  await bob.getByTestId("table-menu").click();
  await expect(bob.getByText("Host tools…")).toHaveCount(0);
  await bob.keyboard.press("Escape");
  await alice.getByTestId("table-menu").click();
  await alice.getByText("Host tools…").click();
  await expect(alice.getByTestId("host-seat-p2")).toContainText("Connected");
  await alice.getByTestId("resync-all").click();

  // Bob's laptop dies for good: the host hands his seat to another device with a link.
  await alice.getByTestId("seat-link-p2").click();
  const url = (await alice.getByTestId("seat-link").textContent())!;
  const path = url.slice(url.indexOf("#"));
  const other = await newPlayer(browser, true);
  await other.page.goto(`/${path}`);
  await expect(other.page.locator(".game-screen")).toBeVisible();
  expect(other.page.url()).not.toContain("seat_token"); // not left in the address bar
  const taken = (await serverView(other.page, gameId)) as unknown as View;
  expect(taken.viewer).toBe("p2");
  expect(taken.zones["p2:hand"]).toEqual(hand);
  await expect(bob.getByText("The host gave this seat to someone else")).toBeVisible();

  await host.context.close();
  await guest.context.close();
  await other.context.close();
});
