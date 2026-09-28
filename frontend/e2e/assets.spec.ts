import { expect, test } from "@playwright/test";
import { keepAll, pngBuffer, startLanGame } from "./helpers";

test("a player brings custom sleeves and a playmat from their own device; everyone sees them", async ({ browser }) => {
  const { host, guest } = await startLanGame(browser);
  const alice = host.page;
  const bob = guest.page;
  await keepAll(alice, bob);

  await bob.getByTestId("table-menu").click();
  await bob.locator(".ctx-menu .ctx-item", { hasText: "Appearance" }).click();
  await expect(bob.getByTestId("appearance")).toBeVisible();
  // Card back → Local image
  await bob.getByTestId("sleeve-file").setInputFiles({ name: "red-sleeves.png", mimeType: "image/png", buffer: pngBuffer(5, 7, [160, 20, 20]) });
  await expect(bob.getByTestId("sleeve-pick")).toHaveCount(1);
  // A disguised file is refused by content
  await bob.getByTestId("mat-file").setInputFiles({ name: "evil.png", mimeType: "image/png", buffer: Buffer.from("<svg onload=alert(1)>") });
  await expect(bob.locator(".toast.error")).toContainText("Only PNG, JPEG and WEBP");
  // Playmat → Local image → use it
  await bob.getByTestId("mat-file").setInputFiles({ name: "felt.png", mimeType: "image/png", buffer: pngBuffer(32, 18, [20, 60, 90]) });
  await bob.getByTestId("mat-save").click();
  await bob.keyboard.press("Escape");

  // Alice's browser: Bob's hand backs wear his sleeves, and his battlefield has his mat
  await expect(alice.locator(".card-back.sleeved").first()).toBeVisible();
  const style = await alice.locator(".card-back.sleeved").first().getAttribute("style");
  expect(style).toContain("/api/assets/");
  await expect(alice.locator(".battlefield .playmat-layer")).toHaveCount(1);

  // Asset manager on the host computer lists both with where they're used
  await alice.goto("/#/assets");
  await expect(alice.getByTestId("asset-item")).toHaveCount(1); // playmats tab
  await expect(alice.getByTestId("asset-item")).toContainText("Bob's playmat");

  await host.context.close();
  await guest.context.close();
});
