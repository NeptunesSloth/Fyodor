import { expect, test } from "@playwright/test";
import { keepAll, menuPath, serverView, startLanGame } from "./helpers";

test("snapshot → change → restore; history view; saved views; profile settings persist", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  const alice = host.page;
  await keepAll(alice, guest.page);

  await alice.getByTestId("table-menu").click();
  await menuPath(alice, "Snapshots & history…");
  await alice.getByTestId("take-snapshot").click();
  await alice.locator(".prompt input, .modal input").last().fill("Before board wipe");
  await alice.keyboard.press("Enter");
  await expect(alice.getByTestId("snapshot-row")).toContainText("Before board wipe");
  await alice.keyboard.press("Escape");

  await alice.getByTestId("life-minus-p2").click();
  await alice.getByTestId("life-minus-p2").click();
  await expect(guest.page.getByTestId("life-p2")).toHaveText("38");

  await alice.getByTestId("table-menu").click();
  await menuPath(alice, "Snapshots & history…");
  alice.once("dialog", (d) => void d.accept());
  await alice.getByTestId("restore-snapshot").click();
  await expect(guest.page.getByTestId("life-p2")).toHaveText("40");
  const log = JSON.stringify(((await serverView(guest.page, gameId)) as { log: unknown }).log);
  expect(log).toContain("restored the table");

  // saved view: focus Bob's side, save to slot 1, reset, recall with Ctrl+1
  await alice.getByTestId("table-menu").click();
  await menuPath(alice, "Views", "Bob's board");
  await expect(alice.locator(".player-area.focused")).toHaveCount(1);
  await alice.keyboard.press("Control+Shift+Digit1");
  await alice.locator(".prompt input, .modal input").last().fill("Bob's board");
  await alice.keyboard.press("Enter");
  await alice.getByTestId("table-menu").click();
  await menuPath(alice, "Views", "Whole table");
  await expect(alice.locator(".player-area.focused")).toHaveCount(0);
  await alice.keyboard.press("Control+Digit1");
  await expect(alice.locator(".player-area.focused")).toHaveCount(1);

  // the 2D table's camera: 1 is the whole table, Look (or 2–6, the 3D seat keys) enlarges one opponent's board
  await alice.keyboard.press("Digit1");
  await expect(alice.locator(".player-area.focused")).toHaveCount(0);
  await alice.getByTestId("look-p2").click();
  await expect(alice.getByTestId("look-p2")).toHaveAttribute("aria-pressed", "true");
  await alice.getByTestId("look-p2").click();
  await expect(alice.locator(".player-area.focused")).toHaveCount(0);
  await alice.keyboard.press("Digit2");
  await expect(alice.getByTestId("look-p2")).toHaveText("Whole table");

  // profile settings persist in this browser
  await alice.goto("/#/settings");
  await alice.getByTestId("profile-name").fill("Jonathan");
  await alice.getByTestId("graphics").selectOption("low");
  await alice.reload();
  await expect(alice.getByTestId("profile-name")).toHaveValue("Jonathan");
  await expect(alice.locator("body")).toHaveClass(/perf-low/);

  await host.context.close();
  await guest.context.close();
});
