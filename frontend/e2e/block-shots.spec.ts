import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for drag-to-block (playtest nov 18): Alice attacks Bob with Serra Angel (flying), Boggart Brute (menace), Hill Giant and
 * Goblin Guide; Bob blocks by dragging his creatures onto them on the 2D and the 3D table. Skipped unless SHOT_DIR is set; point E2E_PORT
 * at a server with the real card database.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(300_000);

const ALICE = "Commander\n1 Gisela, Blade of Goldnight\nDeck\n1 Serra Angel\n1 Boggart Brute\n1 Hill Giant\n1 Goblin Guide\n20 Mountain\n20 Plains";
const BOB = "Commander\n1 Trostani, Selesnya's Voice\nDeck\n1 Giant Spider\n1 Grizzly Bears\n1 Palace Guard\n1 Llanowar Elves\n20 Forest\n20 Plains";

type Card = { name?: string; owner: string; zone: string; blocking?: string };
type View = { zones: Record<string, string[]>; cards: Record<string, Card>; turn: { number: number; active_player: string };
  rules: { priority: string | null; decision: { id: string; kind: string; player: string; options: { id: string }[]; min_choices: number } | null } };

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Bob", avatar: "B", prefs: { ambience: false } }] }));
  }, renderer);
}

async function setup(page: Page) {
  const ids: string[] = [];
  for (const text of [ALICE, BOB]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: {
    name: "Block", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "full",
    priority_helper: "off", players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as View;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as, viewer: as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  for (const p of ["p1", "p2"]) await act(p, { type: "set_prefs", response: "on" });
  let v = await view();
  const named = (name: string, owner: string) => Object.entries(v.cards).find(([, c]) => c.name?.startsWith(name) && c.owner === owner)?.[0];
  for (const [i, n] of ["Serra Angel", "Boggart Brute", "Hill Giant", "Goblin Guide"].entries()) {
    const cid = named(n, "p1");
    if (cid) await act("p1", { type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p1" }, x: 200 + i * 150, y: 120 });
  }
  for (const [i, n] of ["Giant Spider", "Grizzly Bears", "Palace Guard", "Llanowar Elves"].entries()) {
    const cid = named(n, "p2");
    if (cid) await act("p2", { type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p2" }, x: 200 + i * 150, y: 120 });
  }
  await act("p2", { type: "create_token", player: "p2", token: { name: "Soldier", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Soldier" },
    count: 2, stacked: false, x: 800, y: 120 });
  for (let i = 0; i < 300; i++) {
    v = await view();
    const d = v.rules.decision;
    if (v.turn.number > 2 && v.turn.active_player === "p1" && d?.kind === "declare_attackers") break;
    if (!d) await act(v.rules.priority ?? v.turn.active_player, { type: "pass_priority" });
    else if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
    else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
  }
  const elves = named("Llanowar Elves", "p2");
  if (elves) await act("p2", { type: "tap", card_ids: [elves], tapped: true }); // (a tapped creature isn't offered: it can't block)
  const atk = v.rules.decision!.options.filter((o) => o.id.startsWith("a:")).map((o) => ({ card_id: o.id.slice(2), target: "p2" }));
  await act("p1", { type: "declare_attackers", attackers: atk });
  for (let i = 0; i < 40; i++) {
    v = await view();
    const d = v.rules.decision;
    if (d?.kind === "declare_blockers") break;
    if (!d) await act(v.rules.priority ?? "p1", { type: "pass_priority" });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
  }
  expect(v.rules.decision?.kind).toBe("declare_blockers");
  return { gid, view, act, named: (n: string, o: string) => named(n, o)! };
}

for (const renderer of ["2d", "3d"] as const) {
  test(`drag to block (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await setup(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`/#/game/${g.gid}?viewer=p2`);
    if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("blockers-prompt")).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(renderer === "3d" ? 7000 : 3500);
    const shot = (name: string) => page.screenshot({ path: `${OUT}/block-${renderer}-${name}.png` });
    await shot("01-prompt");
    const at = async (id: string) => renderer === "3d"
      ? page.evaluate((cid) => (window as unknown as { __fyodor3d: { cardAt: (id: string) => { x: number; y: number } | null } }).__fyodor3d.cardAt(cid), id)
      : page.locator(`[data-card-id="${id}"]`).first().boundingBox().then((b) => b && { x: b.x + b.width / 2, y: b.y + b.height / 2 });
    const drag = async (from: string, to: string, opts: { hold?: string; shift?: boolean } = {}) => {
      const a = await at(from);
      const b = await at(to);
      expect(a && b).toBeTruthy();
      await page.mouse.move(a!.x, a!.y);
      await page.mouse.down();
      for (let i = 1; i <= 12; i++) {
        await page.mouse.move(a!.x + ((b!.x - a!.x) * i) / 12, a!.y + ((b!.y - a!.y) * i) / 12);
        await page.waitForTimeout(40);
      }
      if (opts.shift) await page.keyboard.down("Shift");
      await page.mouse.move(b!.x + 2, b!.y + 2, { steps: 2 });
      await page.waitForTimeout(400);
      if (opts.hold) await shot(opts.hold);
      await page.mouse.up();
      if (opts.shift) await page.keyboard.up("Shift");
      await page.waitForTimeout(renderer === "3d" ? 2200 : 900);
    };
    const angel = g.named("Serra Angel", "p1");
    const brute = g.named("Boggart Brute", "p1");
    const giant = g.named("Hill Giant", "p1");
    const spider = g.named("Giant Spider", "p2");
    const bears = g.named("Grizzly Bears", "p2");
    const guard = g.named("Palace Guard", "p2");
    // the Bears over Serra Angel: flying, refused (the caption says so); let go: nothing changes
    await drag(bears, angel, { hold: "02-illegal-flying-caption" });
    const elvesId = g.named("Llanowar Elves", "p2");
    await drag(elvesId, giant, { hold: "02b-tapped-caption" });
    await expect(page.getByTestId("block-to")).toHaveCount(0);
    // the Spider onto Serra Angel, held mid-drag for the caption, then let go
    await drag(spider, angel, { hold: "03-mid-drag" });
    // the Bears onto Hill Giant; Palace Guard ("can block any number") onto the Brute, then Shift onto the Giant as well
    await drag(bears, giant);
    await drag(guard, brute);
    await drag(guard, giant, { shift: true, hold: "04-shift-also" });
    await page.mouse.move(960, 200);
    await page.waitForTimeout(renderer === "3d" ? 1500 : 600);
    await shot("05-planned");
    await expect(page.getByTestId("block-summary")).toContainText("3 blocking");
    // declared: the Brute has menace and one blocker, the server says so (the plan stays); a Soldier joins from the list; declared
    await page.getByTestId("declare-blockers").click();
    await page.waitForTimeout(900);
    await shot("06-server-error");
    const soldier = Object.entries((await g.view()).cards).find(([, c]) => c.name === "Soldier" && c.owner === "p2")![0];
    await page.getByTestId(`block-${soldier}`).selectOption(`a:${brute}`);
    await page.getByTestId("declare-blockers").click();
    await page.waitForTimeout(renderer === "3d" ? 4500 : 2000);
    await shot("07-declared");
    const v = await g.view();
    expect(v.cards[spider]?.blocking).toBe(angel);
  });
}
