import { expect, test } from "@playwright/test";
import { act, keepAll, menuPath, playFromHand, serverView, startLanGame } from "./helpers";

test("effects, damage, targeting arrows, choices, selection filters and cleanup sync to the table", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  const alice = host.page;
  const bob = guest.page;
  await keepAll(alice, bob);
  const card = await playFromHand(alice);
  const onAlice = alice.locator(`.table-card[data-card-id="${card}"]`);
  const onBob = bob.locator(`.table-card[data-card-id="${card}"]`);

  // temporary effect + damage marker, visible to everyone
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Effects", "Flying");
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Effects", "Protection from…", "red");
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Damage", "+1");
  await expect(onBob.locator(".fx", { hasText: "Flying" })).toBeVisible();
  await expect(onBob.locator(".fx", { hasText: "Protection from red" })).toBeVisible();
  await expect(onBob.locator(".fx.dmg")).toHaveText("1");

  // targeting arrow: card → Bob's player plate (pick mode)
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Target / point to…");
  await expect(alice.getByTestId("pick-bar")).toBeVisible();
  await alice.locator('[data-player-id="p2"]').first().click();
  await alice.getByTestId("pick-done").click();
  await expect(bob.getByTestId("table-arrows").locator(".arrow.target")).toHaveCount(1);
  const view = (await serverView(bob, gameId)) as { arrows: { source: string; targets: string[] }[] };
  expect(view.arrows[0]).toMatchObject({ source: card, targets: ["p2"] });

  // selection filters
  await alice.getByTestId("table-menu").click();
  await menuPath(alice, "Select", "Everything I control");
  const mine = Object.values((await serverView(alice, gameId)).cards as Record<string, { zone: string; controller: string }>)
    .filter((c) => c.zone === "p1:battlefield" && c.controller === "p1").length;
  expect(mine).toBeGreaterThan(0);
  await expect(alice.locator(".table-card.selected")).toHaveCount(mine);
  await alice.keyboard.press("Escape");
  await expect(alice.locator(".table-card.selected")).toHaveCount(0);

  // cleanup: effects, damage, arrows — the card stays
  await act(alice, gameId, { type: "cleanup", what: ["effects", "damage", "arrows"] });
  await expect(onBob.locator(".fx")).toHaveCount(0);
  await expect(bob.getByTestId("table-arrows")).toHaveCount(0);
  await expect(onBob).toBeVisible();

  await host.context.close();
  await guest.context.close();
});
