import { expect, test } from "@playwright/test";

test("four-player game: end game, record the winner, pod stats, correct the winner", async ({ page }) => {
  const names = ["Jonathan", "Mike", "Alex", "Chris"];
  const created = await page.request.post("/api/games", {
    data: { name: "Friday pod", mode: "local", players: names.map((name) => ({ name })) },
  });
  expect(created.ok()).toBeTruthy();
  const gameId = ((await created.json()) as { game: { id: string } }).game.id;
  const statsBefore = (await (await page.request.get("/api/pod/players")).json()) as { name: string }[];

  await page.goto(`/#/game/${gameId}`);
  await expect(page.locator(".game-screen")).toBeVisible();
  await page.getByTestId("end-game").click();
  await expect(page.getByTestId("confirm-result")).toBeDisabled(); // a winner must be chosen
  await page.getByTestId("winner-p2").click(); // Mike
  await page.getByTestId("result-notes").fill("Mike killed everyone with 84 Goblins.");
  await page.getByTestId("confirm-result").click();
  await expect(page.getByTestId("result-confirm")).toContainText("Winner: Mike");
  await expect(page.getByTestId("result-confirm")).toContainText("Players: Jonathan, Mike, Alex, Chris");
  await page.getByTestId("record-result").click();
  await expect(page.getByTestId("result-recorded")).toContainText("Mike");
  await expect(page.getByTestId("end-game")).toHaveText("Result ✓");

  await page.goto("/#/stats");
  const row = (name: string) => page.getByTestId(`pod-row-${name}`);
  const cells = async (name: string) => (await row(name).locator("td").allTextContents()).slice(1);
  expect(statsBefore.filter((p) => names.includes(p.name))).toEqual([]); // other tests may have recorded games
  await expect.poll(() => cells("Mike")).toEqual(["1", "1", "0", "0", "100%"]); // (the table renders after the page: poll, don't read once)
  for (const n of ["Jonathan", "Alex", "Chris"]) expect(await cells(n)).toEqual(["1", "0", "1", "0", "0%"]);
  const game = page.getByTestId("pod-game").filter({ hasText: "Jonathan" }); // other tests record games too
  await expect(game).toContainText("84 Goblins");

  // Somebody clicked the wrong person: correct it.
  await game.getByTestId("edit-result").click();
  await page.getByTestId("winner-p3").click(); // Alex
  await page.getByTestId("save-result").click();
  await expect(game).toContainText("Winner: Alex");
  await expect.poll(() => cells("Alex")).toEqual(["1", "1", "0", "0", "100%"]);
  expect(await cells("Mike")).toEqual(["1", "0", "1", "0", "0%"]);

  // Player history
  await row("Alex").click();
  await expect(page.getByTestId("pod-player")).toContainText("Games played: 1");
  await expect(page.getByTestId("pod-player")).toContainText("WIN");
});
