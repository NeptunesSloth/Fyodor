import { expect, test } from "@playwright/test";

/** Every Commander precon is bundled: one is added to the library's Precons folder from the Decks page. */
test("add a precon to the library", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  await page.goto("/#/decks");
  await page.getByTestId("open-precons").click();
  await expect(page.getByTestId("precons").locator("li")).not.toHaveCount(0);
  await page.getByRole("searchbox", { name: "Find a precon, commander or set" }).fill("Forces of the Imperium");
  if (process.env.SHOT_DIR) await page.getByRole("dialog").screenshot({ path: `${process.env.SHOT_DIR}/precons.png` });
  await page.getByTestId("precons").getByRole("button", { name: "Add" }).first().click();
  await expect(page.getByTestId("precons").getByText("Added")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("deck-folder").filter({ hasText: "Precons" })).toBeVisible();
});
