import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the declare-attackers prompt (playtest nov 18): eight creatures incl. double-faced cards (one transformed) and two
 * identical Human tokens, two opponents (one with a planeswalker). Skipped unless SHOT_DIR is set; point E2E_PORT at a server with the
 * real card database. SHOT_PHASE=before takes only the plain prompt (the old dialog has none of the rest).
 */
const OUT = process.env.SHOT_DIR ?? "";
const PHASE = process.env.SHOT_PHASE ?? "after";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(300_000);

const ALICE = "Commander\n1 Tovolar, Dire Overlord\nDeck\n1 Burly Breaker\n1 Kessig Prowler\n1 Grizzly Bears\n1 Goblin Guide\n1 Thragtusk\n"
  + "1 Llanowar Elves\n1 Craterhoof Behemoth\n1 Ghalta, Primal Hunger\n20 Forest\n20 Mountain";
const BOB = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Garruk Wildspeaker\n1 Grizzly Bears\n10 Forest\n10 Plains";
const CAROL = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Goblin Guide\n20 Mountain";

type Card = { name?: string; owner: string; zone: string };
type View = { zones: Record<string, string[]>; cards: Record<string, Card>; turn: { number: number; active_player: string };
  rules: { priority: string | null; decision: { id: string; kind: string; player: string; options: { id: string }[]; min_choices: number } | null } };

async function prefs(page: Page, renderer: "2d" | "3d", layout: "free" | "arranged" = "free") {
  await page.addInitScript(([r, layout]) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: layout } }] }));
  }, [renderer, layout] as const);
}

async function setup(page: Page, crowd: boolean | "ghalta" = false) {
  const ids: string[] = [];
  for (const text of [ALICE, BOB, CAROL]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: {
    name: "Attack", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "full",
    priority_helper: "off", players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }, { name: "Carol", deck_id: ids[2] }],
  } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as View;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as, viewer: "p1" } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  for (const p of ["p1", "p2", "p3"]) await act(p, { type: "set_prefs", response: "on" });
  let v = await view();
  const named = (name: string, owner: string) => Object.entries(v.cards).find(([, c]) => c.name?.startsWith(name) && c.owner === owner)?.[0];
  const mine = ["Tovolar", "Burly Breaker", "Kessig Prowler", "Grizzly Bears", "Goblin Guide", "Thragtusk"];
  for (const [i, n] of mine.entries()) {
    const cid = named(n, "p1");
    if (cid) await act("p1", { type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p1" }, x: 60 + i * 130, y: 120 });
  }
  await act("p1", { type: "create_token", player: "p1", token: { name: "Human", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Human" },
    count: 2, stacked: false, x: 860, y: 120 });
  if (crowd) { // 13 attackers (Craterhoof: haste, trample), and blockers for both opponents
    const hoof = named("Craterhoof Behemoth", "p1");
    if (hoof) await act("p1", { type: "move", card_ids: [hoof], to: { zone: "battlefield", player: "p1" }, x: 900, y: 330 });
    const ghalta = crowd === "ghalta" ? named("Ghalta, Primal Hunger", "p1") : undefined; // (trample, 12/12: the division's "rest" row)
    if (ghalta) await act("p1", { type: "move", card_ids: [ghalta], to: { zone: "battlefield", player: "p1" }, x: 1050, y: 330 });
    await act("p1", { type: "create_token", player: "p1", token: { name: "Wolf", power: "2", toughness: "2", colors: ["G"], type_line: "Token Creature — Wolf" },
      count: 4, stacked: false, x: 300, y: 330 });
    await act("p2", { type: "create_token", player: "p2", token: { name: "Soldier", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Soldier" },
      count: 3, stacked: false, x: 500, y: 150 });
    await act("p3", { type: "create_token", player: "p3", token: { name: "Spider", power: "1", toughness: "2", colors: ["G"], type_line: "Token Creature — Spider" },
      count: 2, stacked: false, x: 500, y: 150 });
  }
  const bobs = [named("Garruk Wildspeaker", "p2"), named("Grizzly Bears", "p2")];
  await act("p1", { type: "configure", automation_paused: true }); // (Garruk keeps the loyalty given by hand)
  for (const cid of bobs) if (cid) await act("p2", { type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p2" }, x: 300, y: 150 });
  if (bobs[0]) await act("p2", { type: "set_counter", card_id: bobs[0], kind: "loyalty", value: 3 });
  await act("p1", { type: "configure", automation_paused: false });
  const carol = named("Goblin Guide", "p3");
  if (carol) await act("p3", { type: "move", card_ids: [carol], to: { zone: "battlefield", player: "p3" } });
  const breaker = named("Burly Breaker", "p1");
  if (breaker) await act("p1", { type: "set_face", card_id: breaker, face: 1 });
  for (let i = 0; i < 300; i++) {
    v = await view();
    const d = v.rules.decision;
    if (v.turn.number > 1 && v.turn.active_player === "p1" && d?.kind === "declare_attackers") break;
    if (!d) await act(v.rules.priority ?? v.turn.active_player, { type: "pass_priority" });
    else if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
    else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
  }
  expect(v.rules.decision?.kind).toBe("declare_attackers");
  return { gid, view, act };
}

async function open(page: Page, gid: string, renderer: "2d" | "3d") {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${gid}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("declare-attackers")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(renderer === "3d" ? 7000 : 3500);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/attack-${name}.png` });

for (const renderer of ["2d", "3d"] as const) {
  test(`declare attackers (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await setup(page);
    await open(page, g.gid, renderer);
    if (PHASE === "before") {
      await shot(page, `before-${renderer}`);
      return;
    }
    await shot(page, `after-${renderer}-01-prompt`);
    // hover a row: its card's preview
    await page.locator(".attacker-row").nth(1).hover();
    await page.waitForTimeout(900);
    await shot(page, `after-${renderer}-02-hover-row`);
    // Attack with all → Bob
    await page.getByTestId("attack-all-p2").click();
    await page.waitForTimeout(renderer === "3d" ? 2500 : 1200);
    await shot(page, `push-${renderer}-03-all-to-bob`);
    // Clear, then the keyboard: A
    await page.getByTestId("attack-clear").click();
    await page.mouse.move(960, 540);
    await page.keyboard.press("a");
    await page.waitForTimeout(600);
    await page.keyboard.press("a");
    await page.waitForTimeout(renderer === "3d" ? 2500 : 1200);
    await shot(page, `after-${renderer}-04-key-a-twice`);
    await page.getByTestId("attack-clear").click();
    await page.waitForTimeout(renderer === "3d" ? 4000 : 800); // (the creatures slide home first)
    // a drag: Grizzly Bears forward toward Carol, held mid-way
    const v = await g.view();
    const bears = Object.entries(v.cards).find(([, c]) => c.name === "Grizzly Bears" && c.owner === "p1")![0];
    const from = renderer === "3d"
      ? await page.evaluate((id) => (window as unknown as { __fyodor3d: { cardAt: (id: string) => { x: number; y: number } | null } }).__fyodor3d.cardAt(id), bears)
      : await page.locator(`[data-card-id="${bears}"]`).first().boundingBox().then((b) => b && { x: b.x + b.width / 2, y: b.y + b.height / 2 });
    expect(from).toBeTruthy();
    const to = renderer === "3d"
      ? await page.evaluate(() => (window as unknown as { __fyodor3d: { heartAt: (p: string) => { x: number; y: number } | null } }).__fyodor3d.heartAt("p3"))
      : await page.locator(`[data-drop="p3:battlefield"]`).first().boundingBox().then((b) => b && { x: b.x + b.width / 2, y: b.y + b.height / 2 });
    expect(to).toBeTruthy();
    await page.mouse.move(from!.x, from!.y);
    await page.mouse.down();
    for (let i = 1; i <= 12; i++) {
      await page.mouse.move(from!.x + ((to!.x - from!.x) * i) / 14, from!.y + ((to!.y - from!.y) * i) / 14);
      await page.waitForTimeout(60);
    }
    await page.waitForTimeout(500);
    await shot(page, `drag-${renderer}-05-mid-drag`);
    await page.mouse.move(to!.x, to!.y, { steps: 3 });
    await page.waitForTimeout(300);
    await page.mouse.up();
    await page.waitForTimeout(renderer === "3d" ? 2500 : 1200);
    await shot(page, `drag-${renderer}-06-dropped-on-carol`);
    await page.getByTestId("attack-all-p2").click();
    await page.waitForTimeout(500);
    await page.getByTestId("declare-attackers").click();
    await page.waitForTimeout(renderer === "3d" ? 4000 : 2000);
    await shot(page, `push-${renderer}-07-declared`);
  });
}

/** Combat read physically: 11 attackers at two opponents, several blocks (one creature blocking two), no fan of arrows. */
for (const [renderer, layout] of [["2d", "free"], ["3d", "free"], ["3d", "arranged"]] as const) {
  test(`combat with blocks (${renderer} ${layout})`, async ({ page }) => {
    await prefs(page, renderer, layout);
    const g = await setup(page, true);
    let v = await g.view();
    const mine = v.zones["p1:battlefield"]!.filter((id) => v.rules.decision!.options.some((o) => o.id === `a:${id}`));
    const atk = mine.map((id, i) => ({ card_id: id, target: i % 3 === 2 ? "p3" : "p2" }));
    await g.act("p1", { type: "declare_attackers", attackers: atk });
    for (let i = 0; i < 40; i++) {
      v = await g.view();
      const d = v.rules.decision;
      if (d?.kind === "declare_blockers") {
        const blockers = d.options.filter((o) => o.id.startsWith("b:")).map((o) => o.id.slice(2));
        const theirs = atk.filter((a) => a.target === d.player).map((a) => a.card_id);
        const blocks = blockers.map((b, k) => ({ blocker_id: b, attacker_id: theirs[k % theirs.length]! }));
        await g.act(d.player, { type: "declare_blockers", blocks });
        continue;
      }
      if (!d && Object.values(v.cards).some((c) => (c as { blocking?: string }).blocking)) break;
      if (!d) await g.act(v.rules.priority ?? "p1", { type: "pass_priority" });
      else await g.act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`/#/game/${g.gid}`);
    if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
    await page.waitForTimeout(renderer === "3d" ? 9000 : 4000);
    const tag = `${renderer}-${layout}`;
    const cshot = (name: string) => page.screenshot({ path: `${OUT}/${name}.png` });
    await cshot(`combat-${PHASE}-${tag}`);
    if (renderer === "3d") {
      const first = atk[0]!.card_id;
      const at = await page.evaluate((id) => (window as unknown as { __fyodor3d: { cardAt: (id: string) => { x: number; y: number } | null } }).__fyodor3d.cardAt(id), first);
      if (at) {
        await page.mouse.move(at.x, at.y);
        await page.waitForTimeout(2500);
        await cshot(`combat-${PHASE}-${tag}-hover-attacker`);
      }
    }
  });
}

/** The combat damage division: Ghalta (12/12 trample) blocked by four of Bob's creatures. */
for (const renderer of ["2d", "3d"] as const) {
  test(`divide combat damage (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await setup(page, "ghalta");
    let v = await g.view();
    const hoof = Object.entries(v.cards).find(([, c]) => c.name === "Ghalta, Primal Hunger")![0];
    await g.act("p1", { type: "declare_attackers", attackers: [{ card_id: hoof, target: "p2" }] });
    for (let i = 0; i < 60; i++) {
      v = await g.view();
      const d = v.rules.decision;
      if (d?.kind === "divide" && d.player === "p1") break;
      if (d?.kind === "declare_blockers") {
        const blocks = d.player === "p2" ? d.options.filter((o) => o.id.startsWith("b:")).map((o) => ({ blocker_id: o.id.slice(2), attacker_id: hoof })) : [];
        await g.act(d.player, { type: "declare_blockers", blocks });
      } else if (!d) await g.act(v.rules.priority ?? "p1", { type: "pass_priority" });
      else await g.act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
    }
    expect(v.rules.decision?.kind).toBe("divide");
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`/#/game/${g.gid}`);
    if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("decision-done")).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(renderer === "3d" ? 7000 : 3000);
    const dshot = (name: string) => page.screenshot({ path: `${OUT}/divide-${PHASE}-${renderer}-${name}.png` });
    await dshot("01-prompt");
    if (PHASE !== "before") {
      await page.getByTestId("divide-first").click();
      await page.waitForTimeout(400);
      await dshot("02-all-to-first");
      const rest = page.locator("[data-testid^='divide-rest-']").first();
      await page.locator("input[data-testid^='divide-']").first().fill("1");
      await rest.click();
      await page.waitForTimeout(400);
      await dshot("03-too-little-then-rest-to-bob");
    }
  });
}
