import { expect, test, type Page } from "@playwright/test";
import { act, ALICE_DECK, BOB_DECK, bringDeck, hostLobby, joinLobby, keepAll, newPlayer, recordTraffic, serverView } from "./helpers";

/**
 * -- live cursors -- (as in Tabletop Simulator) two players at a LAN table on their own computers, both on the 3D table:
 * Bob's pointer moving over a card on his screen shows on Alice's, in his seat colour with his name, over that same card
 * (each screen lays the table out from its own seat); it leaves when his pointer goes to his hand.
 */
const OUT = process.env.SHOT_DIR ?? "";

// the arranged boards (the default): each screen lays the rows out its own way, so over a card the cursor names it
const at3d = (page: Page) => page.addInitScript(() => {
  localStorage.setItem("fyodor.renderer", "3d");
  localStorage.setItem("fyodor.welcomeDone", "1");
});

test("a pointer moved on one screen shows on the other, over the same card", async ({ browser }) => {
  test.setTimeout(360_000); // two software-WebGL tables at once, each drawing a frame or two a second
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  await at3d(host.page);
  await at3d(guest.page);
  const aliceTraffic = recordTraffic(host.page);
  const { gameId, code } = await hostLobby(host.page, { name: "Alice" });
  await joinLobby(guest.page, code, "Bob");
  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  await bringDeck(guest.page, BOB_DECK, "Goblins");
  await host.page.getByTestId("ready").click();
  await guest.page.getByTestId("ready").click();
  await host.page.getByTestId("start-game").click();
  const alice = host.page;
  const bob = guest.page;
  for (const p of [alice, bob]) {
    // (a software-WebGL context can fail to start on a busy machine, and the table falls back to 2D: try the page again)
    await expect(async () => {
      if (!(await p.getByTestId("table-3d").isVisible())) await p.reload();
      await expect(p.getByTestId("table-3d")).toBeVisible({ timeout: 20_000 });
    }).toPass({ timeout: 90_000 });
  }
  await keepAll(alice, bob);

  // a card on Alice's battlefield
  const me = (await serverView(alice, gameId)) as { viewer: string; zones: Record<string, string[]> };
  const bobSeat = ((await serverView(bob, gameId)) as { viewer: string }).viewer;
  const card = me.zones[`${me.viewer}:hand`]![0]!;
  await act(alice, gameId, { type: "move", card_ids: [card], to: { zone: "battlefield", player: me.viewer }, x: 600, y: 200 });
  const cardAt = (p: Page) => p.evaluate((cid) => window.__fyodor3d!.cardAt(cid), card);
  // settled on both tables (software WebGL draws a frame or two a second: wait out the card's flight and its showcase)
  for (const p of [alice, bob]) {
    await expect.poll(async () => {
      if ((await p.evaluate(() => window.__fyodor3d!.motion?.().busy)) !== false) return false;
      const a = await cardAt(p);
      await p.waitForTimeout(500);
      const b = await cardAt(p);
      return !!a && !!b && Math.hypot(a.x - b.x, a.y - b.y) < 1;
    }, { timeout: 45_000 }).toBe(true);
  }

  const cursor = () => alice.evaluate((pid) => window.__fyodor3d!.cursorAt?.(pid) ?? null, bobSeat);
  // how far Bob's cursor is drawn from a spot on Alice's screen while he keeps his pointer about there (a hair of
  // movement each poll: a still cursor fades after 3 s, and a busy software-WebGL machine draws few frames a second)
  let wiggle = 0;
  const offBy = async (at: { x: number; y: number }, from: { x: number; y: number }) => {
    await bob.mouse.move(from.x + (wiggle++ % 2), from.y);
    const c = await cursor();
    return c ? Math.hypot(c.x - at.x, c.y - at.y) : 1e9;
  };

  // Bob points at it (he sees it on the far side of the table, upside down from Alice's view)
  const onBob = (await cardAt(bob))!;
  await bob.mouse.move(onBob.x - 40, onBob.y + 30);
  await bob.mouse.move(onBob.x, onBob.y, { steps: 6 });
  const onAlice = (await cardAt(alice))!;
  // eased into place: it settles over the card on Alice's screen
  await expect.poll(() => offBy(onAlice, onBob), { timeout: 30_000 }).toBeLessThan(12);
  // (a screenshot of a software-WebGL page takes a while: keep the pointer moving until one catches the cursor)
  for (let i = 0; OUT && i < 4; i++) {
    await bob.mouse.move(onBob.x + (wiggle++ % 2), onBob.y);
    await alice.screenshot({ path: `${OUT}/live-cursors-alice.png` });
    if (await cursor()) break;
  }

  // an empty spot on Bob's own battlefield: the same spot of that battlefield on Alice's screen
  const spotOn = (p: Page) => p.evaluate((pid) => window.__fyodor3d!.battlefieldAt(pid, 700, 380), bobSeat);
  const empty = (await spotOn(bob))!;
  await bob.mouse.move(empty.x, empty.y, { steps: 5 });
  const there = (await spotOn(alice))!;
  await expect.poll(() => offBy(there, empty), { timeout: 30_000 }).toBeLessThan(12);

  // the wire carried a seat and a point, and a card only when it is one everyone sees; nothing from Bob's hand
  const bobHand = ((await serverView(bob, gameId)) as { zones: Record<string, string[]> }).zones[`${bobSeat}:hand`]!;
  const frames = aliceTraffic.text().split("\n").filter((f) => f.includes('"type":"cursor"'));
  expect(frames.length).toBeGreaterThan(0);
  const shapes = [["from", "player", "type", "x", "y"], ["card", "cx", "cy", "from", "player", "type", "x", "y"], ["from", "gone", "type"]];
  for (const f of frames) expect(shapes).toContainEqual(Object.keys(JSON.parse(f) as object).sort());
  expect(frames.some((f) => f.includes(card))).toBe(true);
  expect(frames.every((f) => bobHand.every((h) => !f.includes(h)))).toBe(true);

  // Alice's own pointer never shows on her own screen; Bob sees hers
  const mine = (await cardAt(alice))!;
  await alice.mouse.move(mine.x + 60, mine.y - 20, { steps: 4 });
  await expect.poll(async () => {
    await alice.mouse.move(mine.x + 60 + (wiggle++ % 2), mine.y - 20);
    return bob.evaluate((pid) => window.__fyodor3d!.cursorAt?.(pid) ?? null, me.viewer);
  }, { timeout: 30_000 }).not.toBeNull();
  expect(await alice.evaluate((pid) => window.__fyodor3d!.cursorAt?.(pid) ?? null, me.viewer)).toBeNull();
  if (OUT) await bob.screenshot({ path: `${OUT}/live-cursors-bob.png` });

  // Bob moves onto his hand: his pointer leaves Alice's table (nothing of what he hovers there goes out)
  const hand = bob.locator("main.table > .hand .hand-card").first();
  await hand.hover();
  await expect.poll(cursor, { timeout: 15_000 }).toBeNull();
  const after = aliceTraffic.text().split("\n").filter((f) => f.includes('"type":"cursor"'));
  expect(after.every((f) => bobHand.every((h) => !f.includes(h)))).toBe(true);
  expect(JSON.parse(after[after.length - 1]!)).toEqual({ type: "cursor", from: bobSeat, gone: true });

  await host.context.close();
  await guest.context.close();
});
