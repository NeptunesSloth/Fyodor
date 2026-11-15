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

/** A folder's decks can be hidden on the all-decks shelf (and stay hidden on this device after a reload). */
test("hide and show a folder's decks", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const deck = (await (await page.request.post("/api/decks", { data: { name: "Folded", text: "1 Sol Ring\n" } })).json()) as { id: string };
  await page.request.put(`/api/decks/${deck.id}/folder`, { data: { folder: "Shelved" } });
  await page.goto("/#/decks");
  await page.getByTestId("deck-folders").getByRole("button", { name: /^All decks/ }).click();
  const toggle = page.getByRole("button", { name: "Hide Shelved" });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const group = page.locator(".dk-group").filter({ has: toggle });
  await expect(group.locator(".dk-grid")).toBeVisible();
  await toggle.click();
  await expect(page.getByRole("button", { name: "Show Shelved" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".dk-group").filter({ has: page.getByRole("button", { name: "Show Shelved" }) }).locator(".dk-grid")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Show Shelved" })).toBeVisible();
  await page.getByRole("button", { name: "Show Shelved" }).click();
  await expect(page.getByRole("button", { name: "Hide Shelved" })).toBeVisible();
});
