import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for a big hand (a Grimoire + Shabraz draw loop: 77 cards): the fan that always fits, the scrolling strip, the hand
 * browser (Shift+H), an opponent's 77 cards as a pile with a count, and the private draw notice. Skipped unless SHOT_DIR is set; point
 * E2E_PORT at a server with the real card database (and art).
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(180_000);

const SPELLS = ["Sol Ring", "Arcane Signet", "Lightning Bolt", "Counterspell", "Swords to Plowshares", "Llanowar Elves", "Grizzly Bears",
  "Serra Angel", "Wrath of God", "Rampant Growth", "Doubling Season", "Shock", "Goblin Guide", "Savannah Lions", "Opt", "Brainstorm",
  "Dark Ritual", "Giant Growth", "Cultivate", "Kodama's Reach", "Path to Exile", "Mind Stone", "Command Tower", "Evolving Wilds",
  "Terramorphic Expanse", "Murder", "Naturalize", "Disenchant", "Divination", "Negate", "Ponder", "Preordain", "Thought Vessel",
  "Fellwar Stone", "Wayfarer's Bauble", "Beast Within", "Swan Song", "Harmonize", "Night's Whisper", "Sign in Blood"];
function deck(basics: number): string {
  const each = Math.floor(basics / 4);
  return `Commander\n1 Atraxa, Praetors' Voice\nDeck\n${SPELLS.map((s) => `1 ${s}`).join("\n")}\n${each} Forest\n${each} Plains\n${each} Island\n${basics - 3 * each} Swamp`;
}

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free" } }] }));
  }, renderer);
}

type View = { zones: Record<string, string[] | { count: number }> };

async function newGame(page: Page, basics = 59) {
  const ids: string[] = [];
  for (let i = 0; i < 2; i++) {
    const r = await page.request.post("/api/decks", { data: { text: deck(basics) } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Big hand", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }] },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const id = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>, as = "p1") => {
    const r = await page.request.post(`/api/games/${id}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (p = "p1") => (await (await page.request.get(`/api/games/${id}/view?viewer=${p}`)).json()) as View;
  return { id, act, view };
}

async function open(page: Page, id: string, renderer: "2d" | "3d", w: number, h: number) {
  await page.setViewportSize({ width: w, height: h });
  await page.goto(`/#/game/${id}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(renderer === "3d" ? 6000 : 3000);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

/** Frames per second while the strip scrolls end to end (rAF count over ~2 s). */
async function scrollFps(page: Page): Promise<{ fps: number; idle: number; cards: number }> {
  return page.evaluate(async () => {
    // the same page standing still first: headless WebGL is software-rendered, so the 3D table's own frame rate is the baseline
    let still = 0;
    const s0 = performance.now();
    await new Promise<void>((done) => { const f = () => { still++; if (performance.now() - s0 < 2000) requestAnimationFrame(f); else done(); }; requestAnimationFrame(f); });
    const idle = Math.round((still * 1000) / (performance.now() - s0));
    const strip = document.querySelector<HTMLElement>("[data-testid=my-hand-cards]")!;
    const max = strip.scrollWidth - strip.clientWidth;
    let frames = 0;
    const t0 = performance.now();
    await new Promise<void>((done) => {
      const tick = () => {
        frames++;
        const t = performance.now() - t0;
        strip.scrollLeft = (max * (t % 1000)) / 1000;
        if (t < 2000) requestAnimationFrame(tick);
        else done();
      };
      requestAnimationFrame(tick);
    });
    return { fps: Math.round((frames * 1000) / (performance.now() - t0)), idle, cards: strip.children.length };
  });
}

for (const [w, h] of [[1920, 1080], [1366, 768]] as const) {
  for (const renderer of ["3d", "2d"] as const) {
    test(`77-card hand (${renderer}, ${w}x${h})`, async ({ page }) => {
      await prefs(page, renderer);
      const g = await newGame(page);
      await g.act({ type: "draw", player: "p1", count: 77 });
      await g.act({ type: "draw", player: "p2", count: 77 }, "p2");
      expect(((await g.view()).zones["p1:hand"] as string[]).length).toBe(77);
      await open(page, g.id, renderer, w, h);
      const tag = `${renderer}-${w}`;
      await expect(page.getByTestId("hand-browse")).toContainText("77");
      await expect(page.getByTestId("my-hand-cards")).toHaveAttribute("data-mode", "strip");
      await shot(page, `hand77-${tag}`);
      // hover a card in the strip: it lifts and magnifies
      const card = page.locator("[data-testid=my-hand-cards] .hand-card").nth(5);
      const box = (await card.boundingBox())!;
      await page.mouse.move(box.x + 12, h - 40);
      await page.waitForTimeout(500);
      await shot(page, `hand77-${tag}-hover`);
      // scroll along with the › button
      await page.mouse.move(w / 2, h / 3);
      await page.getByTestId("hand-scroll-right").click();
      await page.waitForTimeout(700);
      await shot(page, `hand77-${tag}-scrolled`);
      if (w === 1920) {
        const perf = await scrollFps(page);
        console.log(`scroll fps ${tag}: ${perf.fps} (standing still: ${perf.idle}) with ${perf.cards} cards`);
      }
      // the whole hand as a grid
      await page.keyboard.press("Shift+H");
      await expect(page.getByTestId("hand-browser")).toBeVisible();
      await page.waitForTimeout(1500);
      await shot(page, `hand77-${tag}-browser`);
      await page.keyboard.press("Escape"); // (the filter box has the focus: Esc closes the browser)
      await expect(page.getByTestId("hand-browser")).toHaveCount(0);
      // a burst of draws from an effect: one private notice with the faces and a count
      await g.act({ type: "draw", player: "p1", count: 3 });
      await expect(page.getByTestId("draw-notice")).toBeVisible();
      await page.waitForTimeout(700);
      await shot(page, `hand80-${tag}-draw-notice`);
    });
  }
}

test("fan sizes: 7 and 20 cards fit (3d and 2d, 1366)", async ({ page }) => {
  await prefs(page, "3d");
  const g = await newGame(page);
  await g.act({ type: "draw", player: "p1", count: 7 });
  await open(page, g.id, "3d", 1366, 768);
  await expect(page.getByTestId("my-hand-cards")).toHaveAttribute("data-mode", "fan");
  await shot(page, "hand7-3d-1366");
  await g.act({ type: "draw", player: "p1", count: 13 });
  await page.waitForTimeout(1500);
  await expect(page.getByTestId("my-hand-cards")).toHaveAttribute("data-mode", "fan");
  await page.keyboard.press("Escape");
  await shot(page, "hand20-3d-1366");
});

test("200 cards: the strip stays smooth (3d, 1920)", async ({ page }) => {
  await prefs(page, "3d");
  const g = await newGame(page, 220);
  await g.act({ type: "draw", player: "p1", count: 100 });
  await g.act({ type: "draw", player: "p1", count: 100 });
  expect(((await g.view()).zones["p1:hand"] as string[]).length).toBe(200);
  await open(page, g.id, "3d", 1920, 1080);
  await expect(page.getByTestId("hand-browse")).toContainText("200");
  await shot(page, "hand200-3d-1920");
  const perf = await scrollFps(page);
  console.log(`scroll fps 3d-1920 200 cards: ${perf.fps} (standing still: ${perf.idle}) with ${perf.cards} cards`);
  const imgs = await page.evaluate(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=my-hand-cards] img")].filter((i) => i.complete && i.naturalWidth > 0).length);
  console.log(`hand images loaded: ${imgs}`);
});
