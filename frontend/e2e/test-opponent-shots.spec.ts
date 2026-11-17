import { expect, test, type Page } from "@playwright/test";

/**
 * -- test opponent -- review frames at 1920×1080: the Sandbox start with an opponent seated (its deck chosen, "Plays: Simple"), and a game
 * in progress where the server has played its lands and creatures and attacked. Skipped unless SHOT_DIR is set; point E2E_PORT at a
 * server with the real card database (and art). Alice only passes here (the API, as her seat): the opponent plays on its own.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(300_000);

const ALICE = `Commander
1 Krenko, Mob Boss
Deck
1 Sol Ring
1 Lightning Bolt
1 Goblin Guide
1 Monastery Swiftspear
30 Mountain
`;

const GRUUL = `Commander
1 Ruric Thar, the Unbowed
Deck
4 Llanowar Elves
4 Elvish Mystic
4 Grizzly Bears
4 Centaur Courser
4 Kalonian Tusker
3 Lightning Bolt
2 Rampant Growth
18 Forest
14 Mountain
`;

type View = {
  game: { bot?: { speed: string; waiting: boolean } };
  turn: { number: number; phase: string; active_player: string };
  pregame: { seats: Record<string, { status: string }> } | null;
  rules: { priority: string | null; decision: { id: string; kind: string; player: string; options?: unknown[] } | null; winner: string | null } | null;
  zones: Record<string, string[] | { count: number }>;
  log: { actor?: string | null; parts?: unknown[] }[];
};

async function prefs(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free" } }] }));
  });
}

async function newDeck(page: Page, text: string, name: string): Promise<string> {
  const r = await page.request.post("/api/decks", { data: { text, name } });
  expect(r.ok(), await r.text()).toBeTruthy();
  return ((await r.json()) as { id: string }).id;
}

test("the Sandbox start with an opponent, then the opponent playing", async ({ page }) => {
  await prefs(page);
  const alice = await newDeck(page, ALICE, "Goblins");
  const gruul = await newDeck(page, GRUUL, "Gruul stompy");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/play");
  await page.getByTestId("format-sandbox").check();
  await page.getByTestId("host-deck").click();
  await page.getByTestId(`pick-deck-${alice}`).click();
  await page.getByTestId("add-bot").click();
  await page.getByTestId(`pick-deck-${gruul}`).click();
  await page.getByTestId("add-dummy").click();
  await expect(page.getByTestId("bot-plays")).toHaveText("Simple");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/setup-opponent-tile.png` });

  await page.getByTestId("create-game").click();
  await page.waitForURL(/#\/game\//);
  const id = page.url().split("#/game/")[1]!.split(/[?/]/)[0]!;
  const token = await page.evaluate((g) => localStorage.getItem(`fyodor.seat.${g}`), id);
  const headers = { "X-Seat-Token": token ?? "" };
  const view = async () => (await (await page.request.get(`/api/games/${id}/view`, { headers })).json()) as View;
  const act = async (action: Record<string, unknown>) => {
    await page.request.post(`/api/games/${id}/actions`, { data: { action }, headers });
  };
  await page.request.post(`/api/games/${id}/bot/speed`, { data: { speed: "fast" }, headers });

  const attacked = (v: View) => v.log.some((e) => e.actor === "p2" && JSON.stringify(e.parts ?? []).includes("attacks"));
  const creatures = (v: View) => ((v.zones["p2:battlefield"] as string[] | undefined) ?? []).length;
  let v = await view();
  for (let i = 0; i < 400; i++) {
    v = await view();
    if (v.rules?.winner) break;
    if (v.turn.number >= 6 && attacked(v) && creatures(v) >= 5 && v.turn.active_player === "p1" && v.turn.phase === "main1") break;
    if (v.pregame?.seats?.p1?.status === "deciding") { await act({ type: "mulligan_keep" }); continue; }
    const d = v.rules?.decision;
    if (d && d.player === "p1" && d.options) {
      if (d.kind === "declare_blockers" || d.kind === "declare_attackers") await act({ type: d.kind });
      else {
        const firsts = new Map<string, string>(); // (the first answer to each question: reconcile and the like)
        for (const o of d.options as { id: string; group?: string | null }[]) if (!firsts.has(o.group ?? "")) firsts.set(o.group ?? "", o.id);
        await act({ type: "choose", decision_id: d.id, option_ids: d.kind === "reconcile" ? [...firsts.values()] : [...firsts.values()].slice(0, 1) });
      }
      continue;
    }
    if (v.rules?.priority === "p1" && !v.game.bot?.waiting) { await act({ type: "pass_priority" }); continue; }
    await page.waitForTimeout(150);
  }
  expect(attacked(v)).toBeTruthy();
  await page.request.post(`/api/games/${id}/bot/speed`, { data: { speed: "normal" }, headers });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${OUT}/game-opponent-in-progress.png` });
});
