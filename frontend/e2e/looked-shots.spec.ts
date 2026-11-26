import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the look-and-choose prompt (playtest nov 18, "Risen Reef's ability resolves weird"): Risen Reef enters with a nonland
 * and with a land on top of the library, and Augur of Bolas looks at three. Skipped unless SHOT_DIR is set; point E2E_PORT at a server with
 * the real card database. SHOT_PHASE=before names the frames for the old build.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PHASE = process.env.SHOT_PHASE ?? "after";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(240_000);

const ALICE = "Commander\n1 Tatyova, Benthic Druid\nDeck\n1 Risen Reef\n1 Augur of Bolas\n1 Grizzly Bears\n1 Lightning Bolt\n1 Llanowar Elves\n"
  + "20 Forest\n20 Island";
const BOB = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n10 Forest\n10 Plains";

type Card = { name?: string; owner: string; zone: string };
type View = { zones: Record<string, string[]>; cards: Record<string, Card>; turn: { number: number; active_player: string; phase: string; step?: string };
  rules: { priority: string | null; decision: { id: string; kind: string; player: string; options: { id: string }[]; min_choices: number } | null } };

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

/** Alice's main phase; ``top`` on top of her library; ``spell`` cast with the mana it needs; up to its look. */
async function setup(page: Page, top: string[], spell: string, mana: Record<string, number>) {
  const ids: string[] = [];
  for (const text of [ALICE, BOB]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: {
    name: "Look", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "full",
    priority_helper: "off", players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as View;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as, viewer: "p1" } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  let v = await view();
  const named = (name: string) => (Object.entries(v.cards).find(([, c]) => c.name === name && c.owner === "p1" && c.zone === "p1:library")
    ?? Object.entries(v.cards).find(([, c]) => c.name === name && c.owner === "p1" && c.zone === "p1:hand"))?.[0];
  // a few lands on the table, so the board isn't bare
  const lands = Object.entries(v.cards).filter(([, c]) => c.owner === "p1" && (c.name === "Forest" || c.name === "Island")).slice(0, 4).map(([id]) => id);
  for (const [i, cid] of lands.entries()) await act("p1", { type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p1" }, x: 60 + i * 120, y: 330 });
  await act("p1", { type: "pass_priority" }); // → Alice's main phase
  for (const name of [...top].reverse()) {
    v = await view();
    const cid = named(name);
    expect(cid, name).toBeTruthy();
    await act("p1", { type: "move", card_ids: [cid], to: { zone: "library", player: "p1" }, position: "top" });
  }
  v = await view();
  const card = Object.entries(v.cards).find(([, c]) => c.name === spell && c.owner === "p1")![0];
  await act("p1", { type: "move", card_ids: [card], to: { zone: "hand", player: "p1" } });
  await act("p1", { type: "add_mana", player: "p1", mana });
  await act("p1", { type: "cast_spell", card_id: card });
  for (let i = 0; i < 40; i++) {
    v = await view();
    const d = v.rules.decision;
    if (d?.kind === "choose_cards") break;
    if (!d) await act(v.rules.priority ?? v.turn.active_player, { type: "pass_priority" });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
  }
  expect(v.rules.decision?.kind).toBe("choose_cards");
  return { gid, view, act };
}

async function open(page: Page, gid: string) {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${gid}`);
  await expect(page.getByTestId("decision-panel")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(3500);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/look-${PHASE}-${name}.png` });

test("Risen Reef, a nonland on top", async ({ page }) => {
  await prefs(page);
  const g = await setup(page, ["Grizzly Bears"], "Risen Reef", { G: 1, U: 1, C: 1 });
  await open(page, g.gid);
  await shot(page, "reef-nonland");
});

test("Risen Reef, a land on top", async ({ page }) => {
  await prefs(page);
  const g = await setup(page, ["Island"], "Risen Reef", { G: 1, U: 1, C: 1 });
  await open(page, g.gid);
  await shot(page, "reef-land");
});

test("Augur of Bolas, three cards", async ({ page }) => {
  await prefs(page);
  const g = await setup(page, ["Grizzly Bears", "Lightning Bolt", "Forest"], "Augur of Bolas", { U: 1, C: 1 });
  await open(page, g.gid);
  await shot(page, "augur");
  if (PHASE === "after") {
    await page.getByTestId(/^option-/).first().click();
    await page.waitForTimeout(400);
    await shot(page, "augur-picked");
  }
});
