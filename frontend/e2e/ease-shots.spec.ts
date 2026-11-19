import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the player-ease round: the opening hand's check (lands, curve, colours), the turn recap beside the dial after
 * Bob's turn, the mana readout by the hand and the lands a hovered Lightning Bolt would tap (2D and 3D), the Undo label and its
 * "Undo back to…" list, and the End turn tooltip. Skipped unless SHOT_DIR is set; point E2E_PORT at a server with the real card database.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(420_000);

const ALICE = "Commander\n1 Jodah, Archmage Eternal\nDeck\n1 Llanowar Elves\n1 Lightning Bolt\n1 Counterspell\n2 Forest\n1 Mountain\n1 Grizzly Bears\n"
  + "1 Shivan Dragon\n20 Mountain\n20 Forest";
const BOB = "Commander\n1 Trostani, Selesnya's Voice\nDeck\n1 Grizzly Bears\n1 Llanowar Elves\n30 Forest";

type Card = { name?: string; owner: string; zone: string };
type Decision = { id: string; kind: string; player: string; options: { id: string; label: string }[]; min_choices: number };
type View = { zones: Record<string, string[]>; cards: Record<string, Card>; stack: string[];
  turn: { number: number; active_player: string; phase: string }; rules: { priority: string | null; decision: Decision | null } };

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, hotseatHandoff: false, renderer: r, graphics: "low" } }] }));
  }, renderer);
}

test("player ease: recap, mana readout, pay preview, mulligan check, undo label", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  let page = await ctx.newPage();
  await prefs(page, "2d");
  const ids: string[] = [];
  for (const text of [ALICE, BOB]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", { data: {
    name: "Ease", format: "commander", mode: "local", shuffle: false, first_player: 1, automation: "full", mulligan_rule: "commander_london",
    priority_helper: "off", players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as View;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as, viewer: as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  let v = await view();
  const named = (name: string, owner: string, zone?: string) =>
    Object.entries(v.cards).find(([, c]) => c.name?.startsWith(name) && c.owner === owner && (!zone || c.zone.endsWith(zone)))?.[0];
  const spare = (name: string, owner: string) => named(name, owner, "library") ?? named(name, owner, "hand");
  const shot = async (name: string) => {
    for (const [w, h] of [[1920, 1080], [1600, 900]] as const) {
      await page.setViewportSize({ width: w, height: h });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/${name}-${w}.png` });
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
  };
  const drive = async (done: (v: View) => boolean, n = 120) => {
    for (let i = 0; i < n; i++) {
      v = await view();
      if (done(v)) return;
      const d = v.rules.decision;
      if (d) {
        if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
        else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
        else if (d.options.some((o) => o.id === "auto")) await act(d.player, { type: "choose", decision_id: d.id, option_ids: ["auto"] });
        else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o) => o.id) });
      } else if (v.rules.priority) await act(v.rules.priority, { type: "pass_priority" });
      else return;
    }
    throw new Error("drive: stuck");
  };

  // the opening hand's check
  await page.goto(`/#/game/${gid}?viewer=p1`);
  await expect(page.getByTestId("mull-check")).toBeVisible({ timeout: 30_000 });
  await shot("01-mulligan-check");
  await act("p1", { type: "mulligan_finish" });

  // Bob: turn 1 a Forest and Llanowar Elves, his Grizzly Bears out; turn 3 a Forest, then the Bears attack Alice
  v = await view();
  await act("p2", { type: "move", card_ids: [spare("Grizzly Bears", "p2")], to: { zone: "battlefield", player: "p2" }, x: 300, y: 120 });
  for (const n of ["Forest", "Llanowar Elves", "Forest"]) {
    v = await view();
    if ((await view()).zones["p2:hand"]?.filter((id) => v.cards[id]?.name === n).length) continue;
    await act("p2", { type: "move", card_ids: [named(n, "p2", "library")], to: { zone: "hand", player: "p2" } });
  }
  await drive((x) => x.turn.number === 3 && x.turn.phase === "main1" && x.rules.priority === "p2" && !x.stack.length);
  v = await view();
  await act("p2", { type: "play_land", card_id: named("Forest", "p2", "hand") });
  await act("p2", { type: "cast_spell", card_id: named("Llanowar Elves", "p2", "hand") });
  await drive((x) => !x.stack.length && x.rules.priority === "p2" && x.turn.phase === "main1");
  await act("p2", { type: "pass_priority" });
  await drive((x) => x.rules.decision?.kind === "declare_attackers");
  v = await view();
  await act("p2", { type: "declare_attackers", attackers: [{ card_id: named("Grizzly Bears", "p2", "battlefield"), target: "p1" }] });
  await drive((x) => x.turn.number === 4 && x.turn.phase === "main1" && x.rules.priority === "p1");
  // Alice's lands, and a land drop to undo
  v = await view();
  const lands = ["Mountain", "Forest"].flatMap((n) => Object.entries(v.cards).filter(([, c]) => c.name === n && c.owner === "p1" && c.zone.endsWith("library")).slice(0, 2).map(([id]) => id));
  for (const [i, id] of lands.entries()) await act("p1", { type: "move", card_ids: [id], to: { zone: "battlefield", player: "p1" }, x: 220 + i * 120, y: 330 });
  v = await view();
  const hand = (n: string) => named(n, "p1", "hand");
  if (hand("Forest")) await act("p1", { type: "play_land", card_id: hand("Forest") });
  await page.waitForTimeout(2500);

  await expect(page.getByTestId("turn-recap")).toBeVisible();
  await expect(page.getByTestId("mana-ready")).toBeVisible();
  await shot("02-turn-recap-and-mana-readout");
  console.log("recap:", await page.getByTestId("turn-recap").innerText());
  console.log("mana:", await page.getByTestId("mana-ready").getAttribute("aria-label"));

  // pointing at Lightning Bolt: the Mountain it would tap
  v = await view();
  await page.locator(`.hand-card[data-card-id="${hand("Lightning Bolt")}"]`).hover({ force: true });
  await expect(page.locator(".table-card.pay-preview")).toHaveCount(1, { timeout: 5000 });
  await shot("03-pay-preview-bolt-2d");
  await page.mouse.move(960, 300);

  // Undo names what it takes back; ▾ lists the last ten
  console.log("undo title:", await page.getByTestId("undo").getAttribute("title"));
  await page.locator(".undo-more").click();
  await page.waitForTimeout(800);
  await shot("04-undo-back-to-menu");
  await page.keyboard.press("Escape");
  console.log("end turn title:", await page.getByTestId("pass-turn").getAttribute("title"));
  await page.getByTestId("turn-recap-close").click();
  await expect(page.getByTestId("turn-recap")).toHaveCount(0);

  // the 3D table: the readout, the recap (a fresh page shows it again) and the rings over the lands to tap
  await page.close();
  page = await ctx.newPage();
  await prefs(page, "3d");
  await page.goto(`/#/game/${gid}?viewer=p1`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(5000);
  await page.locator(`.hand-card[data-card-id="${hand("Lightning Bolt")}"]`).hover({ force: true });
  await expect(page.getByTestId("pay-marks")).toBeVisible({ timeout: 5000 });
  await shot("05-3d-recap-readout-pay-preview-bolt");
  await ctx.close();
});
