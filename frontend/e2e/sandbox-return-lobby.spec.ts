import { expect, test } from "@playwright/test";
import { ALICE_DECK } from "./helpers";

/** A LAN Sandbox table that ends and goes back to the lobby: the lobby draws (a requeued deck's report has no unresolved list). */
test("a finished Sandbox table returns to its lobby without crashing", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (d) => void d.accept());
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const deck = (await (await page.request.post("/api/decks", { data: { text: ALICE_DECK } })).json()) as { id: string };
  const res = await page.request.post("/api/games", { data: { name: "S", format: "sandbox", mode: "lan", mulligan_rule: "none", players: [{ name: "Alice", deck_id: deck.id }] } });
  const body = (await res.json()) as { game: { id: string }; seat: { token: string } };
  const H = { "X-Seat-Token": body.seat.token };
  await page.goto("/#/play");
  await page.evaluate(([g, t]) => localStorage.setItem(`fyodor.seat.${g}`, t!), [body.game.id, body.seat.token]);
  await page.goto(`/#/game/${body.game.id}`);
  const ended = await page.request.post(`/api/games/${body.game.id}/night/propose`, { data: { result_type: "single", winners: ["p1"], as_player: "p1" }, headers: H });
  expect(ended.ok(), await ended.text()).toBeTruthy();
  await page.getByRole("button", { name: "Return to lobby" }).click();
  await expect(page.getByTestId("lobby")).toBeVisible({ timeout: 20_000 });
  expect(errors).toEqual([]);
});
