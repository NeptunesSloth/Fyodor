import { expect, test } from "@playwright/test";
import { BOB_SECRETS, serverView, startLanGame } from "./helpers";

test("Commander London: simultaneous decisions, exact bottom selection, private bottoms", async ({ browser }) => {
  const { host, guest, gameId, hostTraffic } = await startLanGame(browser);
  const alice = host.page;
  const bob = guest.page;
  await expect(alice.getByTestId("mulligan")).toBeVisible();
  await expect(bob.getByTestId("mulligan")).toBeVisible();
  await expect(alice.getByTestId("mull-card")).toHaveCount(7);

  // Bob mulligans three times (the first is free): he will keep 7 and bottom exactly 2.
  for (let i = 1; i <= 3; i++) {
    await bob.getByTestId("mull-take").click();
    await expect(bob.getByTestId("mulligan")).toContainText(`Mulligan #${i}`);
  }
  await expect(alice.getByTestId("mull-seat-p2")).toContainText("Deciding · 3 mulligans");
  // he picks exactly 2 for the bottom, then keeps: one step
  await expect(bob.getByTestId("mull-keep")).toBeDisabled();
  await bob.getByTestId("mull-card").nth(0).click();
  await expect(bob.getByTestId("mull-keep")).toBeDisabled();
  await bob.getByTestId("mull-card").nth(1).click();
  await bob.getByTestId("mull-card").nth(2).click(); // a third pick: not exact
  await expect(bob.getByTestId("mull-keep")).toBeDisabled();
  await bob.getByTestId("mull-card").nth(2).click();
  await expect(bob.getByTestId("mull-keep")).toHaveText("Keep 5, bottom 2");
  await bob.getByTestId("mull-keep").click();
  await expect(bob.getByTestId("mulligan")).toContainText("You kept 5 cards");
  await expect(alice.getByTestId("mull-seat-p2")).toContainText("Kept 5");

  // Alice keeps her 7: the pregame ends for both.
  await alice.getByTestId("mull-keep").click();
  await expect(alice.getByTestId("mulligan")).toHaveCount(0);
  await expect(bob.getByTestId("mulligan")).toHaveCount(0);

  const aliceView = await serverView(alice, gameId);
  const log = JSON.stringify(aliceView.log);
  expect(log).toContain("kept 7 and put 2 cards on the bottom");
  expect(log).toContain("Everyone has kept");
  const bobPlayer = (aliceView.players as { id: string; hand_count: number; mulligans: number }[]).find((p) => p.id === "p2")!;
  expect(bobPlayer.hand_count).toBe(5);
  expect(bobPlayer.mulligans).toBe(3);
  // Nothing Alice's browser ever received names a card from Bob's hands or bottoms.
  for (const name of BOB_SECRETS) expect(hostTraffic.text()).not.toContain(name);

  await host.context.close();
  await guest.context.close();
});

test("host override starts the game while someone is still deciding", async ({ browser }) => {
  const { host, guest } = await startLanGame(browser);
  await expect(guest.page.getByTestId("mulligan-override")).toHaveCount(0); // guests can't
  host.page.once("dialog", (d) => void d.accept());
  await host.page.getByTestId("mulligan-override").click();
  await expect(host.page.getByTestId("mulligan")).toHaveCount(0);
  await expect(guest.page.getByTestId("mulligan")).toHaveCount(0);
  await host.context.close();
  await guest.context.close();
});
