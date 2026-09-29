import { expect, test } from "@playwright/test";

test("first-run guide: name, card database, how the pod joins; dismissed once done", async ({ page }) => {
  await page.goto("/#/");
  const welcome = page.getByTestId("welcome");
  await expect(welcome).toBeVisible();
  await expect(welcome).toContainText("cards ready");
  await expect(welcome).toContainText("Invite the pod");
  await page.getByTestId("welcome-name").fill("Morgan");
  await page.getByTestId("welcome-done").click();
  await expect(page).toHaveURL(/#\/play/);
  await page.goto("/#/");
  await expect(page.getByTestId("welcome")).toHaveCount(0);
  const profiles = await page.evaluate(() => localStorage.getItem("fyodor.profiles"));
  expect(profiles).toContain("Morgan");
  await page.getByRole("button", { name: "Setup guide" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
});
