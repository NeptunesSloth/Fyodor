import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

test("multiple exported decks are saved and reopen without external requests", async ({ page, baseURL }) => {
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  await page.goto("/#/decks");
  await page.getByRole("button", { name: "Import multiple decks" }).click();
  await page.getByLabel("Deck export files").setInputFiles([
    { name: "Offline Alice.txt", mimeType: "text/plain", buffer: Buffer.from(ALICE_DECK) },
    { name: "Offline Bob.txt", mimeType: "text/plain", buffer: Buffer.from(BOB_DECK) },
    { name: "Empty.txt", mimeType: "text/plain", buffer: Buffer.from("") },
  ]);
  await page.getByRole("button", { name: "Preview decks" }).click();
  await expect(page.getByText("Ready to import", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Import failed", { exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "Save decks" }).click();
  await expect(page.getByText("Saved to this host", { exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Done", exact: true }).click();
  const host = new URL(baseURL!).host;
  const outside: string[] = [];
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.protocol.startsWith("http") && url.host !== host) {
      outside.push(url.href);
      await route.abort();
    } else await route.continue();
  });
  await page.reload();
  await expect(page.getByRole("link", { name: "Offline Alice", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Offline Bob", exact: true }).click();
  await expect(page.locator("input.deck-title")).toHaveValue("Offline Bob");
  expect(outside).toEqual([]);
});
