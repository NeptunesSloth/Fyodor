import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, menuPath } from "./helpers";

test("Automation FULL: HUD, RESPONSE toggle, play a land through the rules, pass priority", async ({ page }) => {
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  await page.goto("/#/play");
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
  await expect(page.getByTestId("mana-mode")).toHaveText(/MANA: (AUTO|ASK|MANUAL)/);

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
});
