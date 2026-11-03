import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

/** REPEAT (RepeatPanel.tsx): do a loop once, then Repeat ×10 from the turn dial; the server repeats it through the rules. */
const OUT = process.env.SHOT_DIR ?? "";

test("Repeat: a loop done once by hand is repeated ×10 from the turn dial", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Repeat", mode: "local", automation: "full", shuffle: false, first_player: 0,
    mulligan_rule: "none", players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }] } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  type V = { turn: { phase: string }; players: { id: string; mana: Record<string, number>; mana_units?: unknown[] }[]; cards: Record<string, { name: string }> };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as V;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as: "p1" } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  for (let i = 0; i < 6 && (await view()).turn.phase !== "main1"; i++) await act({ type: "pass_priority" });
  // a stand-in combo piece: "{0}: Add {C}." (a free, repeatable mana ability), activated once by hand
  await act({ type: "create_token", player: "p1", token: { name: "Fountain", type_line: "Token Artifact", text: "{0}: Add {C}." } });
  const fountain = Object.entries((await view()).cards).find(([, c]) => c.name === "Fountain")![0];
  await act({ type: "activate_ability", card_id: fountain, ability: 0 });
  const pool = async () => { const p = (await view()).players.find((x) => x.id === "p1")!; return Object.values(p.mana).reduce((a, b) => a + b, 0) + (p.mana_units?.length ?? 0); };
  expect(await pool()).toBe(1);

  await page.goto(`/#/game/${gameId}`);
  await page.getByTestId("open-repeat").click();
  await expect(page.getByTestId("repeat-steps")).toContainText("Activate Fountain");
  await page.getByTestId("repeat-times-10").click();
  if (OUT) await page.screenshot({ path: `${OUT}/repeat-panel.png` });
  await page.getByTestId("repeat-go").click();
  await expect.poll(pool).toBe(11);
  await expect(page.getByTestId("repeat-steps")).toHaveCount(0); // the panel closed
});
