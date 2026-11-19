import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the end-turn / hot-seat round: End turn skips your own attack (and still stops for a decision: the cleanup
 * discard, with Select all and Shift+click), the hot-seat "Pass to Bob" cover, a kicker card dragged without priority (no chooser:
 * the refusal says why), the trigger-order plaque clear of its creatures, "dies" in the log, the draw notice clear of a selected
 * card's action bar, and Shift+P in Help on a Full table. Skipped unless SHOT_DIR is set; point E2E_PORT at a server with the real
 * card database.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(420_000);

const ALICE = "Commander\n1 Jodah, Archmage Eternal\nDeck\n1 Blood Artist\n1 Zulaport Cutthroat\n1 Llanowar Elves\n1 Grizzly Bears\n1 Rite of Replication\n"
  + "1 Lightning Bolt\n20 Island\n20 Swamp\n10 Mountain";
const BOB = "Commander\n1 Trostani, Selesnya's Voice\nDeck\n1 Grizzly Bears\n1 Giant Spider\n30 Forest";

type Card = { name?: string; owner: string; zone: string };
type Decision = { id: string; kind: string; player: string; options: { id: string; label: string }[]; min_choices: number };
type View = { zones: Record<string, string[]>; cards: Record<string, Card>; log: { parts: { t?: string }[] }[];
  turn: { number: number; active_player: string; phase: string }; rules: { priority: string | null; decision: Decision | null } };

async function prefs(page: Page, handoff: boolean) {
  await page.addInitScript((h) => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, hotseatHandoff: h } }] }));
  }, handoff);
}

test("end turn, hot-seat cover and leftovers", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  let page = await ctx.newPage();
  await prefs(page, false);
  const ids: string[] = [];
  for (const text of [ALICE, BOB]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: {
    name: "Final", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "full",
    priority_helper: "off", players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as View;
  const act = async (as: string, action: Record<string, unknown>, ok = true) => {
    const r = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as, viewer: as } });
    if (ok) expect(r.ok(), await r.text()).toBeTruthy();
  };
  let v = await view();
  const named = (name: string, owner: string, zone?: string) =>
    Object.entries(v.cards).find(([, c]) => c.name?.startsWith(name) && c.owner === owner && (!zone || c.zone.endsWith(zone)))?.[0];
  const put = async (name: string, owner: string, zone: string, x = 0, y = 0) => {
    v = await view();
    const cid = named(name, owner, "library");
    expect(cid, name).toBeTruthy();
    await act(owner, { type: "move", card_ids: [cid], to: { zone, player: owner }, ...(zone === "battlefield" ? { x, y } : {}) });
  };
  for (const [i, n] of ["Blood Artist", "Zulaport Cutthroat", "Llanowar Elves", "Grizzly Bears"].entries()) await put(n, "p1", "battlefield", 250 + i * 150, 120);
  for (let i = 0; i < 4; i++) await put("Island", "p1", "battlefield", 200 + i * 110, 330);
  await put("Mountain", "p1", "battlefield", 700, 330);
  for (const n of ["Rite of Replication", "Lightning Bolt"]) await put(n, "p1", "hand");
  for (const [i, n] of ["Grizzly Bears", "Giant Spider"].entries()) await put(n, "p2", "battlefield", 400 + i * 150, 120);
  const shot = (name: string) => page.screenshot({ path: `${OUT}/${name}.png` });
  // answers what the table asks (first options), passing for the player with priority, until `done`
  const drive = async (done: (v: View) => boolean, who: string[] = ["p1", "p2"], n = 80) => {
    for (let i = 0; i < n; i++) {
      v = await view();
      if (done(v)) return;
      const d = v.rules.decision;
      if (d && who.includes(d.player)) {
        if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
        else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
        else if (d.options.some((o) => o.id === "auto")) await act(d.player, { type: "choose", decision_id: d.id, option_ids: ["auto"] }); // (pay: Auto pay)
        else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
      } else if (!d && v.rules.priority && who.includes(v.rules.priority)) await act(v.rules.priority, { type: "pass_priority" });
      else return;
    }
  };

  // to Alice's next turn (her creatures can attack then), Bob stopping at every priority from there
  await drive((x) => x.turn.number === 3 && x.turn.phase === "main1" && x.rules.priority === "p1");
  await act("p2", { type: "set_prefs", response: "on" });
  await page.goto(`/#/game/${gid}?viewer=p1`);
  await expect(page.locator(".game-screen")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500);

  // Shift+P in Help on a Full table
  await page.keyboard.press("Shift+?");
  await page.getByRole("searchbox").fill("shift+p");
  await page.waitForTimeout(400);
  await shot("01-help-shift-p-full");
  await page.keyboard.press("Escape");

  // the draw notice with a selected battlefield card's action bar open
  v = await view();
  await page.locator(`.battlefield [data-card-id="${named("Mountain", "p1", "battlefield")}"]`).first().click({ force: true, timeout: 5000 });
  await page.waitForTimeout(400);
  await act("p1", { type: "draw", count: 1 });
  await page.waitForTimeout(900);
  await shot("03-draw-notice-clear-of-action-bar");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  // a creature dies with Blood Artist and Zulaport Cutthroat out: the order plaque stays off their names
  v = await view();
  await act("p1", { type: "cast_spell", card_id: named("Lightning Bolt", "p1", "hand"), targets: [named("Llanowar Elves", "p1", "battlefield")] });
  await drive((x) => x.rules.priority === "p2" && !!x.zones["stack"]?.length, ["p1"]);
  // a kicker card double-clicked while Bob has priority (Bolt on the stack): no chooser, the refusal says why
  v = await view();
  await page.waitForTimeout(800);
  await page.locator(`.hand-card[data-card-id="${named("Rite of Replication", "p1", "hand")}"]`).dblclick({ force: true }); // (dropFromHand)
  await page.waitForTimeout(1200);
  await shot("02-kicker-without-priority-no-chooser");
  await expect(page.locator(".ctx-menu, [role='menu']")).toHaveCount(0);
  await drive((x) => x.rules.decision?.kind === "order" || (x.zones["stack"]?.length === 0 && !x.rules.decision), ["p1", "p2"]);
  await page.waitForTimeout(1200);
  await shot("04-trigger-order-clear-of-sources");
  await drive((x) => x.zones["stack"]?.length === 0 && !x.rules.decision && x.rules.priority === "p1");
  await page.getByTestId("log-drawer").locator(".log-pill").click();
  await page.waitForTimeout(700);
  await shot("05-log-dies");
  await page.locator(".log-close").click();

  // End turn with 15 more cards: no attack, but the cleanup discard stops it
  await act("p1", { type: "draw", count: 15 });
  await page.waitForTimeout(1500);
  await page.keyboard.press("Escape");
  await page.getByTestId("pass-turn").hover();
  await page.waitForTimeout(900);
  await shot("06-end-turn-tooltip");
  await page.getByTestId("pass-turn").click();
  let sawAttack = false;
  for (let i = 0; i < 60; i++) {
    v = await view();
    const d = v.rules.decision;
    if (d?.kind === "declare_attackers" && d.player === "p1") sawAttack = true;
    if (d?.player === "p1" || v.turn.number > 3) break;
    if (v.rules.priority === "p2") await act("p2", { type: "pass_priority" });
    await page.waitForTimeout(150);
  }
  expect(sawAttack).toBe(false);
  expect(v.rules.decision?.player).toBe("p1"); // the discard to hand size
  await page.waitForTimeout(1500);
  await shot("07-end-turn-skipped-attack-discard-stops");
  const thumbs = page.locator(".tgt-tray .tgt-thumb");
  await thumbs.nth(0).click({ force: true, timeout: 5000 });
  await thumbs.nth(7).click({ modifiers: ["Shift"], force: true, timeout: 5000 });
  await page.waitForTimeout(400);
  await shot("08-discard-shift-click-range");
  await page.getByTestId("targeting-clear").or(page.getByTestId("targeting-all")).first().click();
  await page.waitForTimeout(300);
  if (await page.getByTestId("targeting-all").isVisible()) await page.getByTestId("targeting-all").click();
  await page.waitForTimeout(400);
  await shot("09-discard-select-all");
  await page.getByTestId("decision-done").click();
  await page.waitForTimeout(1200);
  v = await view();
  expect(v.log.map((e) => e.parts.map((p) => p.t ?? "").join("")).join("\n")).toContain("doesn't attack");

  // hot-seat: a page with the hand-off on, Alice's view, the table waiting on Bob
  await drive((x) => x.turn.number === 4 && x.rules.priority === "p2", ["p1"]);
  await page.close();
  page = await ctx.newPage();
  await prefs(page, true);
  await page.goto(`/#/game/${gid}?viewer=p1`);
  await expect(page.getByTestId("hotseat-cover")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/10-hotseat-pass-to-bob.png` });
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("hotseat-cover")).toHaveCount(0);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/11-hotseat-bobs-view.png` });
  await act("p2", { type: "pass_priority" });
  await drive((x) => x.rules.priority === "p1" || x.rules.decision?.player === "p1", ["p2"]);
  await expect(page.getByTestId("hotseat-cover")).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/12-hotseat-pass-to-alice.png` });
  await ctx.close();
});
