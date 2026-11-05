import { expect, test } from "@playwright/test";
import { ALICE_DECK } from "./helpers";

/**
 * Taking decks to another computer (an offline one too): back up here, restore the file there, restart. Settings says how,
 * and a restore ends in a "Restart Fyodor now" button (the launcher restarts in place; a server started some other way, like
 * this test's, says to restart it by hand).
 */
test("back up, restore the file, and the restore asks for a restart", async ({ page }) => {
  test.setTimeout(120_000);
  const made = await page.request.post("/api/decks", { data: { text: ALICE_DECK, name: "Travelling deck" } });
  expect(made.ok()).toBeTruthy();
  await page.goto("/#/settings");
  const section = page.getByTestId("backups");
  await expect(section.getByTestId("move-computers")).toContainText("Taking your decks to another computer");

  const download = page.waitForEvent("download");
  await section.getByTestId("backup-now").click();
  const file = await (await download).path();
  expect(file).toBeTruthy();

  page.once("dialog", (d) => void d.accept());
  await section.locator('input[type="file"]').setInputFiles(file!);
  const restart = section.getByTestId("restart-now");
  await expect(restart).toBeVisible();
  await restart.click();
  await expect(page.getByText(/Restart Fyodor yourself/)).toBeVisible(); // (this test's server isn't run by the launcher)
});
