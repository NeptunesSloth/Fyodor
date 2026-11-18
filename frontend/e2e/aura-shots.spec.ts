import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for Auras on other players' permanents (playtest: "annoying to look at — devise a better way for enchanting
 * other people's creatures"): three players, Alice's Auras and Equipment on Bob's and Cara's creatures, Cara's Aura on the
 * same creature as Alice's, a Curse on Bob, an Aura on a land, a stolen creature (Control Magic) and Alice's own tucked
 * Aura for comparison. 3D and 2D, arranged and free, with a hover. Skipped unless SHOT_DIR is set; SHOT_PREFIX names the
 * set ("aura-before", "aura-after").
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "aura";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(240_000);

const ALICE = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Pacifism\n1 Rancor\n1 Vampiric Link\n1 Control Magic\n1 Bonesplitter\n"
  + "1 Curse of Bounty\n1 Spirit Link\n1 Ethereal Armor\n1 Llanowar Elves\n1 Land Tax\n1 Sol Ring\n20 Forest";
const BOB = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Goblin Guide\n1 Goblin Matron\n1 Goblin Chieftain\n1 Mogg War Marshal\n1 Sol Ring\n20 Mountain";
const CARA = "Commander\n1 Sythis, Harvest's Hand\nDeck\n1 Arrest\n1 Grizzly Bears\n1 Serra Angel\n1 Elvish Mystic\n20 Plains";

type View = { zones: Record<string, string[]>; cards: Record<string, { name?: string; zone: string }> };

async function prefs(page: Page, renderer: "2d" | "3d", layout: "arranged" | "free") {
  await page.addInitScript(([r, l]) => {
    localStorage.setItem("fyodor.renderer", r as string);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: l } }] }));
  }, [renderer, layout] as const);
}

async function setup(page: Page) {
  const decks: string[] = [];
  for (const text of [ALICE, BOB, CARA]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    decks.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Auras", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i] })) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const id = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>, as = "p1") => {
    const r = await page.request.post(`/api/games/${id}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (p = "p1") => (await (await page.request.get(`/api/games/${id}/view?viewer=${p}`)).json()) as View;
  const byName = async (p: string, name: string, zone = "battlefield") => {
    const v = await view(p);
    const hit = Object.entries(v.cards).find(([, c]) => c.name === name && c.zone === `${p}:${zone}`);
    expect(hit, `${name} of ${p}`).toBeTruthy();
    return hit![0];
  };
  for (const [p, n] of [["p1", 31], ["p2", 25], ["p3", 24]] as const) await act({ type: "draw", player: p, count: n }, p);
  const put = async (p: string, names: string[], y: number) => {
    for (const [i, n] of names.entries()) await act({ type: "move", card_ids: [await byName(p, n, "hand")], to: { zone: "battlefield", player: p }, x: 60 + i * 130, y }, p);
  };
  await put("p1", ["Pacifism", "Rancor", "Vampiric Link", "Control Magic", "Bonesplitter", "Curse of Bounty", "Spirit Link", "Ethereal Armor"], 240);
  await put("p1", ["Llanowar Elves", "Land Tax", "Sol Ring"], 60);
  await put("p1", ["Forest", "Forest", "Forest"], 430);
  await put("p2", ["Goblin Guide", "Goblin Matron", "Goblin Chieftain", "Mogg War Marshal"], 60);
  await put("p2", ["Mountain", "Mountain", "Mountain"], 420);
  await put("p3", ["Grizzly Bears", "Serra Angel", "Elvish Mystic", "Arrest"], 60);
  await put("p3", ["Plains", "Plains"], 420);
  const attach = async (p: string, name: string, owner: string, host: string) => {
    await act({ type: "attach", card_ids: [await byName(p, name)], to: await byName(owner, host) }, p);
  };
  await attach("p1", "Pacifism", "p2", "Goblin Guide");
  await attach("p1", "Rancor", "p2", "Goblin Chieftain");
  await attach("p3", "Arrest", "p2", "Goblin Chieftain"); // two players' Auras on one creature
  await attach("p1", "Vampiric Link", "p3", "Serra Angel");
  await attach("p1", "Bonesplitter", "p3", "Grizzly Bears");
  await attach("p1", "Ethereal Armor", "p2", "Mountain"); // an Aura on a land
  await attach("p1", "Spirit Link", "p1", "Llanowar Elves"); // my own, tucked as always
  await act({ type: "attach", card_ids: [await byName("p1", "Curse of Bounty")], to: "p2" }); // a Curse on a player
  // Control Magic: Alice steals Bob's Goblin Matron (it moves to her battlefield; Bob still owns it)
  const matron = await byName("p2", "Goblin Matron");
  await attach("p1", "Control Magic", "p2", "Goblin Matron");
  await act({ type: "set_controller", card_ids: [matron], player: "p1" });
  return { id, act, view, byName };
}

async function open(page: Page, id: string, renderer: "2d" | "3d") {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${id}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(renderer === "3d" ? 9000 : 5000);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${PREFIX}-${name}.png` });

/** Alice's plaque counts her cards attached elsewhere: hover lights them, a click selects them (their short lines show). */
async function chip(page: Page, tag: string) {
  const el = page.getByTestId("elsewhere-p1");
  if (!(await el.count())) return;
  await el.hover();
  await page.waitForTimeout(1200);
  await shot(page, `${tag}-chip-hover`);
  await el.click();
  await page.mouse.move(960, 1060);
  await page.waitForTimeout(1200);
  await shot(page, `${tag}-chip-selected`);
}

for (const layout of ["arranged", "free"] as const) {
  test(`auras on other players' permanents, 3D ${layout}`, async ({ page }) => {
    await prefs(page, "3d", layout);
    const g = await setup(page);
    await open(page, g.id, "3d");
    await shot(page, `3d-${layout}`);
    // hover the Aura on Bob's Goblin Chieftain, then the creature
    for (const [p, name, tag] of [["p1", "Rancor", "hover-aura"], ["p2", "Goblin Chieftain", "hover-host"]] as const) {
      const cid = await g.byName(p, name);
      const at = await page.evaluate((c) => window.__fyodor3d?.cardAt(c) ?? null, cid);
      if (!at) continue;
      await page.mouse.move(at.x, at.y);
      await page.waitForTimeout(1500);
      await shot(page, `3d-${layout}-${tag}`);
    }
    await chip(page, `3d-${layout}`);
  });

  test(`auras on other players' permanents, 2D ${layout}`, async ({ page }) => {
    await prefs(page, "2d", layout);
    const g = await setup(page);
    await open(page, g.id, "2d");
    await shot(page, `2d-${layout}`);
    for (const [p, name, tag] of [["p1", "Rancor", "hover-aura"], ["p2", "Goblin Chieftain", "hover-host"]] as const) {
      const cid = await g.byName(p, name);
      const el = page.locator(`[data-card-id="${cid}"]`).first();
      if (!(await el.count())) continue;
      const box = await el.boundingBox();
      if (!box) continue;
      // a tucked card shows only its edge: point at the part that peeks out (the host: its middle)
      if (tag === "hover-aura") await page.mouse.move(box.x + box.width - 5, box.y + box.height - 8);
      else await page.mouse.move(box.x + box.width * 0.35, box.y + box.height * 0.4);
      await page.waitForTimeout(1200);
      await shot(page, `2d-${layout}-${tag}`);
    }
    await chip(page, `2d-${layout}`);
  });
}

test("dragging my Aura drawn under an opponent's creature: on their board it springs back; onto mine it stays attached with rules on, comes off on a manual table (2D)", async ({ page }) => {
  await prefs(page, "2d", "arranged");
  const g = await setup(page);
  await open(page, g.id, "2d");
  const rancor = await g.byName("p1", "Rancor");
  const card = async () => ((await g.view()).cards[rancor] as unknown as { zone: string; attached_to?: string | null });
  const drag = async (toX: number, toY: number) => {
    const box = (await page.locator(`[data-card-id="${rancor}"]`).first().boundingBox())!;
    await page.mouse.move(box.x + box.width - 5, box.y + box.height - 8);
    await page.mouse.down();
    await page.mouse.move(toX - 20, toY - 20, { steps: 6 });
    await page.mouse.move(toX, toY, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(1500);
  };
  const bob = (await page.locator('[data-drop="p2:battlefield"]').boundingBox())!;
  await drag(bob.x + bob.width * 0.8, bob.y + bob.height * 0.5);
  expect(await card()).toMatchObject({ zone: "p1:battlefield", attached_to: await g.byName("p2", "Goblin Chieftain") });
  const chieftain = await g.byName("p2", "Goblin Chieftain");
  const mine = (await page.locator('[data-drop="p1:battlefield"]').boundingBox())!;
  // rules automation on: no detach (the state-based actions would bin it), it springs back and says so
  await g.act({ type: "configure", automation: "full" });
  await page.waitForTimeout(1500);
  await drag(mine.x + mine.width * 0.75, mine.y + mine.height * 0.5);
  expect(await card()).toMatchObject({ zone: "p1:battlefield", attached_to: chieftain });
  await expect(page.getByText(/Rancor stays attached/)).toBeVisible();
  await shot(page, "2d-drag-home-automation");
  // a manual table: pulled home, it comes off
  await g.act({ type: "configure", automation: "off" });
  await page.waitForTimeout(1500);
  await drag(mine.x + mine.width * 0.75, mine.y + mine.height * 0.5);
  expect(await card()).toMatchObject({ zone: "p1:battlefield" });
  expect((await card()).attached_to ?? null).toBeNull();
  await shot(page, "2d-drag-home");
});
