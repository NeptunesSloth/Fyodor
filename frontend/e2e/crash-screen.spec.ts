import { expect, test } from "@playwright/test";

/**
 * A crash while drawing never leaves a black page: the page says what broke and in which browser, with a reload (an
 * offline computer's old browser or graphics driver is where this happens), and a 3D backdrop that can't start gives way
 * to the flat one instead of taking the page down.
 */
test("an error while drawing shows what broke, not a black page", async ({ page }) => {
  await page.addInitScript(() => { window.matchMedia = () => { throw new Error("simulated: matchMedia missing"); }; });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Fyodor hit a problem drawing this page");
  await expect(page.getByTestId("crash-details")).toContainText("simulated: matchMedia missing");
  await expect(page.getByTestId("crash-details")).toContainText("Browser:");
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
});

test("no 3D graphics: the home page still opens, on its flat backdrop", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    HTMLCanvasElement.prototype.getContext = function () { throw new Error("simulated: no WebGL"); } as never;
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Fyodor", exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
