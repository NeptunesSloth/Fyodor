import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, menuPath } from "./helpers";

test("Automation FULL: HUD, RESPONSE toggle, play a land through the rules, pass priority", async ({ page }) => {
  const ids: string[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) {
    const res = await page.request.post("/api/decks", { data: { text } });
    expect(res.ok()).toBeTruthy();
    ids.push((await res.json()).id as string);
  }
  // Player 1 plays Alice's Islands deck: preselect it (the library lists the newest deck first, so the
  // default would depend on whether the two imports landed in the same second).
  await page.goto(`/#/play?deck=${ids[0]}`);
  await page.getByTestId("mulligan-rule").selectOption("none");
  await page.getByTestId("automation-level").selectOption("full");
  await page.getByTestId("first-player").selectOption("0");
  await page.getByTestId("create-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();
  const gameId = page.url().split("/game/")[1]!;

  // The HUD tells the table what the engine does; RESPONSE cycles OFF → AUTO → ON.
  await expect(page.getByTestId("auto-level")).toHaveText("AUTO: FULL");
  await expect(page.getByTestId("resp-mode")).toHaveText("RESP: AUTO");
  await page.getByTestId("resp-mode").click();
  await expect(page.getByTestId("resp-mode")).toHaveText("RESP: ON");
  await page.getByTestId("resp-mode").click();
  await expect(page.getByTestId("resp-mode")).toHaveText("RESP: OFF");
  await page.getByTestId("resp-mode").click(); // back to AUTO: always stop in my first main phase
  await expect(page.getByTestId("resp-mode")).toHaveText("RESP: AUTO");
  await expect(page.getByTestId("mana-mode")).toHaveCount(0); // players always tap their own mana

  // Pass to the first main phase with the priority bar.
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view`)).json()) as Record<string, any>;
  for (let i = 0; i < 6 && (await view()).turn.phase !== "main1"; i++) {
    await page.getByTestId("priority-bar").getByRole("button", { name: /^(Pass|Next)/ }).first().click();
  }
  expect((await view()).turn.phase).toBe("main1");
  await expect(page.getByTestId("priority-bar")).toContainText("Your priority");

  // A land in hand: right-click → Play land goes through the rules engine (one land per turn).
  let island: string | undefined;
  for (let i = 0; i < 8 && !island; i++) {
    await page.keyboard.press("d"); // drawing by hand stays a sandbox action
    await expect.poll(async () => ((await view()).zones["p1:hand"] as string[]).length).toBe(i + 1);
    const v = await view();
    island = (v.zones["p1:hand"] as string[]).find((id) => v.cards[id]?.name === "Island");
  }
  expect(island).toBeTruthy();
  const card = page.locator(`main.table > .hand .hand-card[data-card-id="${island}"]`);
  await expect(card).toBeVisible();
  await card.click({ button: "right" });
  await menuPath(page, "Play land");
  await expect(page.locator(`.table-card[data-card-id="${island}"]`)).toBeVisible();
  const after = await view();
  expect(after.rules.hints?.playable_lands ?? []).not.toContain(island);
  expect(JSON.stringify(after.log ?? "")).not.toContain("by hand");

  // You tap your own land: a double-click taps it *for mana* (the engine never taps it for you).
  expect(after.cards[island!].tapped).toBeFalsy();
  await page.locator(`.table-card[data-card-id="${island}"]`).dblclick();
  await expect.poll(async () => ((await view()).players as { id: string; mana?: Record<string, number> }[])
    .find((p) => p.id === "p1")?.mana?.U ?? 0).toBe(1);
  expect((await view()).cards[island!].tapped).toBeTruthy();
});
