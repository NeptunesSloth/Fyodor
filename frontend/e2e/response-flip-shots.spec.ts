import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for "I have a response!" (the dial's button, the shout, the hold before the top object resolves), smart Resolve (a run of
 * your own triggers in one press, Resolve all beside it) and "flip the table" (the confirm, the jolt in 2D and 3D, concede and flip).
 * Skipped unless SHOT_DIR is set; point E2E_PORT at a server with the real card database.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(300_000);

const KRENKO = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n1 Lightning Bolt\n1 Siege-Gang Commander\n1 Impact Tremors\n1 Purphoros, God of the Forge\n"
  + "1 Goblin Guide\n1 Goblin Matron\n1 Skirk Prospector\n1 Goblin Chieftain\n1 Mogg War Marshal\n1 Raging Goblin\n1 Beetleback Chief\n35 Mountain";
const ATRAXA = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Sol Ring\n1 Llanowar Elves\n1 Grizzly Bears\n1 Savannah Lions\n1 Serra Angel\n"
  + "1 Swords to Plowshares\n1 Counterspell\n1 Wrath of God\n1 Rampant Growth\n10 Forest\n10 Plains\n10 Island\n10 Swamp";

type View = { zones: Record<string, string[]>; cards: Record<string, { name?: string; zone?: string }>; rules?: { priority: string | null; decision?: { id: string; player: string; kind: string; options?: { id: string }[] } | null };
  turn: { active_player: string; phase: string } };

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free", sound: false } }] }));
  }, renderer);
}

/** A LAN table, Alice (this page, host) against Bob (acting through the API with his own seat). */
async function lanGame(page: Page) {
  const ids: string[] = [];
  for (const text of [KRENKO, ATRAXA]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: { name: "Review", mode: "lan", automation: "full", mulligan_rule: "none", shuffle: false,
    first_player: 0, players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }] } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const made = (await res.json()) as { game: { id: string; code: string }; seat: { token: string } };
  const id = made.game.id;
  const alice = made.seat.token;
  const bob = ((await (await page.request.post("/api/join", { data: { code: made.game.code, seat: "p2", name: "Bob" } })).json()) as { token: string }).token;
  const tok = (p: string) => (p === "p1" ? alice : bob);
  const act = async (action: Record<string, unknown>, p = "p1") => {
    const r = await page.request.post(`/api/games/${id}/actions`, { data: { action }, headers: { "X-Seat-Token": tok(p) } });
    expect(r.ok(), `${JSON.stringify(action)} ${await r.text()}`).toBeTruthy();
  };
  const view = async (p = "p1") => (await (await page.request.get(`/api/games/${id}/view`, { headers: { "X-Seat-Token": tok(p) } })).json()) as View;
  const signal = (data: Record<string, unknown>, p = "p1") => page.request.post(`/api/games/${id}/night/signal`, { data, headers: { "X-Seat-Token": tok(p) } });
  await page.addInitScript(([g, t]) => localStorage.setItem(`fyodor.seat.${g}`, t), [id, alice] as const);
  return { id, act, view, signal };
}

const named = (v: View, name: string, pid: string) => Object.entries(v.cards).find(([, c]) => c.name === name && (c.zone ?? "").startsWith(pid))?.[0];

async function toMain(g: Awaited<ReturnType<typeof lanGame>>) {
  for (let i = 0; i < 12; i++) {
    const v = await g.view();
    if (v.turn.phase === "main1" && v.turn.active_player === "p1" && v.rules?.priority === "p1" && !v.zones["stack"]?.length) return;
    await g.act({ type: "pass_priority" }, v.rules?.priority ?? "p1");
  }
  throw new Error("never reached Alice's main phase");
}

async function open(page: Page, id: string, renderer: "2d" | "3d", size = { width: 1920, height: 1080 }) {
  await page.setViewportSize(size);
  await page.goto(`/#/game/${id}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(renderer === "3d" ? 7000 : 3000);
  await page.mouse.move(size.width / 2, 40);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

async function boards(g: Awaited<ReturnType<typeof lanGame>>) {
  for (const p of ["p1", "p2"]) {
    await g.act({ type: "draw", player: p, count: 8 }, p);
    const hand = (await g.view(p)).zones[`${p}:hand`]!;
    for (const [i, cid] of hand.slice(0, 6).entries()) {
      await g.act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: p }, x: 80 + i * 130, y: i < 3 ? 200 : 400 }, p);
    }
  }
}

for (const renderer of ["2d", "3d"] as const) {
  test(`I have a response (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await lanGame(page);
    await toMain(g);
    await g.act({ type: "set_prefs", response: "on" }, "p2"); // Bob thinks over every priority (as a slow player or a bot would)
    await g.act({ type: "fetch_card", player: "p1", name: "Lightning Bolt", to: "hand" });
    await g.act({ type: "add_mana", player: "p1", mana: { R: 1 } });
    let v = await g.view();
    await g.act({ type: "cast_spell", card_id: named(v, "Lightning Bolt", "p1")!, targets: ["p2"] }); // Alice is passed for; Bob thinks
    await open(page, g.id, renderer);
    const button = page.getByTestId("response-call");
    await expect(button).toBeVisible();
    await shot(page, `response-${renderer}-1-button`);
    await page.keyboard.press("r"); // (R: the same as the button)
    await expect(page.getByTestId("response-shout")).toBeVisible();
    await shot(page, `response-${renderer}-2-shout`);
    await expect(button).toHaveAttribute("aria-pressed", "true");
    await page.waitForTimeout(3600);
    await shot(page, `response-${renderer}-3-called`);
    await g.act({ type: "pass_priority" }, "p2"); // Bob passes: Alice gets priority before the Bolt resolves
    await expect(page.getByTestId("pass-priority")).toBeVisible();
    v = await g.view();
    expect(v.zones["stack"]!.length).toBe(1);
    await page.waitForTimeout(600);
    await shot(page, `response-${renderer}-4-priority-before-it-resolves`);
  });

  test(`smart resolve (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await lanGame(page);
    await toMain(g);
    for (const name of ["Impact Tremors", "Purphoros, God of the Forge"]) await g.act({ type: "fetch_card", player: "p1", name, to: "battlefield" });
    await g.act({ type: "fetch_card", player: "p1", name: "Siege-Gang Commander", to: "hand" });
    await g.act({ type: "add_mana", player: "p1", mana: { R: 5 } });
    await g.act({ type: "set_prefs", response: "on" }); // (Alice stops at her own triggers: what the playtest saw with mana open)
    const v = await g.view();
    await g.act({ type: "cast_spell", card_id: named(v, "Siege-Gang Commander", "p1")! });
    for (let i = 0; i < 8 && (await g.view()).zones["stack"]!.length < 3; i++) {
      const d = (await g.view()).rules?.decision;
      if (d && d.player === "p1") await g.act({ type: "choose", decision_id: d.id, option_ids: (d.options ?? []).map((o) => o.id) });
      else await g.act({ type: "pass_priority", until: "stack_changes" });
    }
    for (let i = 0; i < 3; i++) { // (the order of the triggers: as offered)
      const d = (await g.view()).rules?.decision;
      if (!d || d.player !== "p1") break;
      await g.act({ type: "choose", decision_id: d.id, option_ids: (d.options ?? []).map((o) => o.id) });
    }
    await open(page, g.id, renderer);
    await expect(page.getByTestId("resolve-all")).toBeVisible();
    await shot(page, `resolve-${renderer}-1-run-of-triggers`);
    const before = (await g.view()).zones["stack"]!.length;
    await page.getByTestId("pass-priority").click();
    await page.waitForTimeout(2500);
    const after = (await g.view()).zones["stack"]!.length;
    console.log(`smart resolve: ${before} on the stack, ${after} after one press`);
    await shot(page, `resolve-${renderer}-2-after-one-press`);
    if (renderer === "2d") {
      await page.setViewportSize({ width: 1366, height: 768 });
      await page.waitForTimeout(800);
      await shot(page, "resolve-2d-3-dial-1366x768");
    }
  });

  test(`flip the table (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await lanGame(page);
    await toMain(g);
    await boards(g);
    await open(page, g.id, renderer);
    await page.getByTestId("flip-table").click();
    await expect(page.getByTestId("flip-confirm")).toBeVisible();
    await shot(page, `flip-${renderer}-1-confirm`);
    await page.getByTestId("flip-cancel").click();
    // Bob flips (for fun): every table sees his side jump
    const res = await g.signal({ kind: "flip" }, "p2");
    expect(res.ok(), await res.text()).toBeTruthy();
    if (renderer === "2d") {
      await expect(page.getByTestId("flip-glyph")).toBeVisible();
      for (const [i, t] of [120, 320, 600, 880].entries()) {
        await page.evaluate((ms) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; } }, t);
        await shot(page, `flip-2d-${i + 2}-frame-${t}ms`);
      }
      await page.evaluate(() => { for (const a of document.getAnimations()) a.finish(); });
    } else {
      await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().busy ?? false)).toBeTruthy();
      for (const [i, t] of [150, 330, 600, 900].entries()) {
        await page.evaluate((ms) => window.__fyodor3d?.motionFreeze?.(ms), t);
        await page.evaluate(() => window.__fyodor3d?.nextFrame?.());
        await page.waitForTimeout(150);
        await shot(page, `flip-3d-${i + 2}-frame-${t}ms`);
      }
      await page.evaluate(() => window.__fyodor3d?.motionFreeze?.(null));
    }
    await page.waitForTimeout(1500);
    await shot(page, `flip-${renderer}-6-settled`);
    // (a second flip within 30 s is refused: backend/tests/test_response_call.py)
    // Alice: Concede → "Concede and flip the table"
    await page.getByTestId("concede").click();
    await expect(page.getByTestId("concede-flip")).toBeVisible();
    await shot(page, `flip-${renderer}-7-concede-option`);
    await page.getByTestId("concede-flip").click();
    await page.waitForTimeout(400);
    await shot(page, `flip-${renderer}-8-concede-and-flip`);
    await page.waitForTimeout(2500);
    await shot(page, `flip-${renderer}-9-after`);
  });
}
