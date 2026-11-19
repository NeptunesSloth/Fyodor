import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * Review frames for the deck lab (deck editor → Stats) and friends' decks (Decks page, Settings → Deck sharing). Skipped unless
 * SHOT_DIR is set; E2E_PORT is this computer's server (real card database) and FRIEND_URL a second Fyodor standing in for a
 * friend's computer (its own data directory), browsed by address since discovery may not reach it.
 */
const OUT = process.env.SHOT_DIR ?? "";
const FRIEND = process.env.FRIEND_URL ?? "";
test.skip(!OUT || !FRIEND, "set SHOT_DIR and FRIEND_URL to capture screenshots");
test.setTimeout(240_000);

const SPELLS = ["Sol Ring", "Arcane Signet", "Llanowar Elves", "Birds of Paradise", "Rampant Growth", "Cultivate", "Kodama's Reach",
  "Swords to Plowshares", "Counterspell", "Wrath of God", "Doubling Season", "Serra Angel", "Grizzly Bears", "Brainstorm", "Ponder",
  "Demonic Tutor", "Vampiric Tutor", "Cyclonic Rift", "Rhystic Study", "Smothering Tithe", "Path to Exile", "Beast Within",
  "Eternal Witness", "Sakura-Tribe Elder", "Wood Elves", "Farseek", "Nature's Lore", "Three Visits", "Fact or Fiction", "Mystic Remora",
  "Anguished Unmaking", "Assassin's Trophy", "Toxic Deluge", "Damnation", "Deepglow Skate", "Tezzeret's Gambit", "Inexorable Tide",
  "Contagion Engine", "Evolution Sage", "Flux Channeler", "Hydroid Krasis", "Swan Song", "Arcane Denial", "Generous Gift",
  "Teferi's Protection", "Heroic Intervention", "Seedborn Muse", "Kenrith's Transformation", "Ravenous Chupacabra", "Mulldrifter",
  "Phyrexian Arena", "Night's Whisper", "Sign in Blood", "Solemn Simulacrum", "Burnished Hart"];
const MDFC = ["Sea Gate Restoration", "Emeria's Call", "Agadeem's Awakening", "Turntimber Symbiosis"];
const LANDS = ["Command Tower", "Evolving Wilds", "Temple Garden", "Hallowed Fountain", "Watery Grave", "Overgrown Tomb", "Godless Shrine",
  "Breeding Pool", "Exotic Orchard", "Karn's Bastion"];
const basics = 99 - SPELLS.length - MDFC.length - LANDS.length;
const ATRAXA = ["Commander", "1 Atraxa, Praetors' Voice", "Deck", ...[...SPELLS, ...MDFC, ...LANDS].map((n) => `1 ${n}`),
  `${Math.ceil(basics / 4)} Forest`, `${Math.floor(basics / 4)} Plains`, `${Math.ceil(basics / 4)} Island`, `${basics - 2 * Math.ceil(basics / 4) - Math.floor(basics / 4)} Swamp`].join("\n");
const KRENKO = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n1 Goblin Guide\n1 Goblin Matron\n1 Lightning Bolt\n1 Skirk Prospector\n1 Siege-Gang Commander\n1 Impact Tremors\n35 Mountain";
const MEREN = "Commander\n1 Meren of Clan Nel Toth\nDeck\n1 Sol Ring\n1 Eternal Witness\n1 Sakura-Tribe Elder\n1 Spore Frog\n18 Forest\n18 Swamp";

/** A fresh library on that server (the review reruns against the same servers). */
async function emptyLibrary(browser: Browser, baseURL?: string) {
  const ctx = await browser.newContext(baseURL ? { baseURL } : {});
  for (const d of await (await ctx.request.get("/api/decks")).json() as { id: string }[]) await ctx.request.delete(`/api/decks/${d.id}`);
  await ctx.request.put("/api/decks/sharing", { data: { enabled: false, all: false } });
  await ctx.close();
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

async function friendSetup(browser: Browser) {
  const ctx = await browser.newContext({ baseURL: FRIEND });
  const r = ctx.request;
  for (const [text, name, shared] of [[KRENKO, "Krenko's Goblins", true], [MEREN, "Meren Recursion", true], [ATRAXA, "Secret brew", false]] as const) {
    const d = await (await r.post("/api/decks", { data: { text, name } })).json() as { id: string };
    await r.put(`/api/decks/${d.id}`, { data: { ...(await (await r.get(`/api/decks/${d.id}`)).json()), notes: "PRIVATE NOTE" } });
    if (shared) await r.put(`/api/decks/${d.id}/shared`, { data: { shared: true } });
  }
  expect((await r.put("/api/decks/sharing", { data: { enabled: true, all: false } })).ok()).toBeTruthy();
  await ctx.close();
}

async function prefs(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  });
}

test("deck lab and friends' decks", async ({ browser }) => {
  await emptyLibrary(browser, FRIEND);
  await emptyLibrary(browser);
  await friendSetup(browser);
  const sizes = [
    { tag: "1080", viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 },
    { tag: "720at125", viewport: { width: 1024, height: 576 }, deviceScaleFactor: 1.25 }, // 1280×720 at 125% Windows scaling
  ];
  const ctx0 = await browser.newContext();
  const deck = await (await ctx0.request.post("/api/decks", { data: { text: ATRAXA, name: "Atraxa Superfriends" } })).json() as { id: string };
  await ctx0.close();

  for (const size of sizes) {
    const ctx = await browser.newContext({ viewport: size.viewport, deviceScaleFactor: size.deviceScaleFactor });
    const page = await ctx.newPage();
    await prefs(page);

    // -- deck lab -- opened from the keyboard
    await page.goto(`/#/decks/${deck.id}`);
    await expect(page.getByTestId("deck-stats-open")).toBeVisible();
    await page.waitForTimeout(1500);
    await page.getByTestId("deck-stats-open").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("deck-stats")).toBeVisible();
    await expect(page.getByTestId("ds-avg-lands")).not.toHaveText("0");
    await shot(page, `decklab-stats-${size.tag}`);
    await page.getByTestId("ds-draw").focus();
    await page.keyboard.press("Enter");
    await page.getByTestId("ds-100").click();
    await expect(page.getByTestId("ds-keep-rate")).toContainText("of 100 hands");
    await page.getByTestId("ds-draw").scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await shot(page, `decklab-hand-${size.tag}`);
    await page.getByTestId("ds-mulligan").click();
    await page.waitForTimeout(500);
    await shot(page, `decklab-mulligan-${size.tag}`);
    await page.keyboard.press("Escape");

    // -- settings: deck sharing (off by default on this computer)
    await page.goto("/#/settings");
    const share = page.getByTestId("share-decks");
    await share.scrollIntoViewIfNeeded();
    await expect(page.getByTestId("share-decks-toggle")).not.toBeChecked();
    await shot(page, `share-settings-off-${size.tag}`);

    // -- friends' decks: none found, then browsed by address and copied
    await page.goto("/#/decks");
    await page.getByTestId("friend-decks-toggle").click();
    // (whatever this network has: other Fyodors found by discovery, or none)
    await expect(page.getByTestId("friend-host").first().or(page.getByText(/No other Fyodor found|turned off/))).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("friend-decks").scrollIntoViewIfNeeded();
    await shot(page, `friends-found-${size.tag}`);
    await page.getByTestId("friend-address").fill(FRIEND.replace("http://", ""));
    await page.getByTestId("friend-address").press("Enter");
    await expect(page.getByTestId("friend-deck")).toHaveCount(2);
    await expect(page.getByTestId("friend-decks")).not.toContainText("Secret brew");
    await expect(page.getByTestId("friend-decks")).not.toContainText("PRIVATE NOTE");
    await page.getByTestId("friend-deck").first().scrollIntoViewIfNeeded();
    await shot(page, `friends-browse-${size.tag}`);
    if (size.tag === "1080") {
      await page.getByRole("button", { name: "Copy Krenko's Goblins into my decks" }).click();
      await expect(page.getByTestId("friend-deck").filter({ hasText: "Krenko" })).toContainText("Copied");
      await expect(page.getByTestId("deck-folders")).toContainText("From ");
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, `friends-copied-${size.tag}`);
    }
    await ctx.close();
  }

  // the friend computer turns sharing off: browsing says so
  const off = await browser.newContext({ baseURL: FRIEND });
  await off.request.put("/api/decks/sharing", { data: { enabled: false, all: false } });
  await off.close();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  await prefs(page);
  await page.goto("/#/decks");
  await page.getByTestId("friend-decks-toggle").click();
  await page.getByTestId("friend-address").fill(FRIEND.replace("http://", ""));
  await page.getByTestId("friend-address").press("Enter");
  await expect(page.getByTestId("friend-decks")).toContainText("isn't sharing its decks");
  await page.getByTestId("friend-decks").scrollIntoViewIfNeeded();
  await shot(page, "friends-not-sharing-1080");
  // this computer turns sharing on in Settings, and a deck is marked from its menu
  await page.goto("/#/settings");
  await page.getByTestId("share-decks").scrollIntoViewIfNeeded();
  await page.getByTestId("share-decks-toggle").check({ force: true });
  await expect(page.getByTestId("share-which")).toBeVisible();
  await shot(page, "share-settings-on-1080");
  await page.goto("/#/decks");
  await page.getByRole("button", { name: "More for Atraxa Superfriends" }).click();
  await page.getByRole("menuitem", { name: "Share with friends" }).click();
  await expect(page.locator(".dk-shared").first()).toBeVisible();
  await shot(page, "shelf-shared-badge-1080");
  await ctx.close();
});
