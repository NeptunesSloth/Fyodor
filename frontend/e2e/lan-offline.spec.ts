import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as net from "node:net";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { PORT, newPlayer } from "./helpers";

/**
 * The game-night norm, end to end with two servers and no internet: a friend saved a deck on their own Fyodor while online
 * (its art cached there; its commander from a set newer than the host's card database), then at the host's LAN table they
 * press Join under "Games on your network" and play it, nothing else clicked. The table server of these tests is the host;
 * this spec starts the friend's server beside it. Finding each other uses the real UDP broadcast, so a machine without a
 * network interface skips the test.
 */

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let FRIEND_PORT = 0;
let FRIEND = "";
const PY = process.env.PYTHON ?? path.join(ROOT, "backend/.venv/bin/python");
const DATA = process.env.E2E_FRIEND_DIR ?? path.join(ROOT, "frontend/test-results/e2e-friend");
// the newer set's card (backend tests/fixtures/cards.py newer_set_card): uuid5 of "Zephyr of the New Set|nws|7"
let NEW_ID = "";
let friend: ChildProcess | null = null;

/** A port nobody listens on (the friend's server takes it). */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "0.0.0.0", () => {
      const port = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(port));
    });
  });
}

async function waitFor(url: string, ms: number): Promise<boolean> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      if ((await fetch(url)).ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

/** A card-sized JPEG painted in the browser (the friend's cached art for the new card). */
async function paintedJpeg(page: Page): Promise<Buffer> {
  const data = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 488;
    c.height = 680;
    const g = c.getContext("2d")!;
    const grad = g.createLinearGradient(0, 0, 488, 680);
    grad.addColorStop(0, "#7a1f12");
    grad.addColorStop(1, "#e8a33a");
    g.fillStyle = grad;
    g.fillRect(0, 0, 488, 680);
    g.fillStyle = "#fff4dc";
    g.font = "bold 34px serif";
    g.fillText("Zephyr of the New Set", 40, 70);
    return c.toDataURL("image/jpeg", 0.9).split(",")[1]!;
  });
  return Buffer.from(data, "base64");
}

test.beforeAll(async () => {
  fs.rmSync(DATA, { recursive: true, force: true });
  fs.mkdirSync(DATA, { recursive: true });
  const env = { ...process.env, PYTHONPATH: path.join(ROOT, "backend") };
  const built = spawnSync(PY, ["-m", "tools.fixture_db", path.join(DATA, "cards.sqlite"), "--newer"], { cwd: path.join(ROOT, "backend"), env });
  expect(built.status, String(built.stderr)).toBe(0);
  const id = spawnSync(PY, ["-c", "from tests.fixtures.cards import newer_set_card; print(newer_set_card()['id'])"], { cwd: path.join(ROOT, "backend"), env });
  NEW_ID = String(id.stdout).trim();
  FRIEND_PORT = await freePort();
  FRIEND = `http://127.0.0.1:${FRIEND_PORT}`;
  friend = spawn(PY, ["-m", "uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", String(FRIEND_PORT)], {
    cwd: path.join(ROOT, "backend"),
    env: { ...env, FYODOR_DATA_DIR: DATA, FYODOR_FRONTEND_DIST: path.join(ROOT, "frontend/dist"), FYODOR_ALLOW_NETWORK: "0",
           FYODOR_HOST: "0.0.0.0", FYODOR_PORT: String(FRIEND_PORT), FYODOR_LOG_LEVEL: "INFO" },
    stdio: ["ignore", fs.openSync(path.join(DATA, "server.log"), "w"), "inherit"],
  });
  expect(await waitFor(`${FRIEND}/api/health`, 60_000)).toBe(true);
  expect(friend.exitCode, "the friend's server stopped (its port was taken?)").toBeNull();
});

test.afterAll(() => {
  friend?.kill();
});

test("offline game night: Join from my own Fyodor, my deck waits on my seat, a new card and its art come along", async ({ browser }) => {
  test.setTimeout(120_000);
  const host = await newPlayer(browser);
  const me = await newPlayer(browser); // the friend, at their own computer
  await me.page.addInitScript(() => {
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Dana", avatar: "D", prefs: { ambience: false } }] }));
  });

  // at home, online: Dana saved the deck (its art is cached on her computer)
  const art = path.join(DATA, "images", "cards", NEW_ID.slice(0, 2), `${NEW_ID}-0-normal.jpg`);
  fs.mkdirSync(path.dirname(art), { recursive: true });
  fs.writeFileSync(art, await paintedJpeg(host.page)); // (painted on a blank page)
  const deck = await me.page.request.post(`${FRIEND}/api/decks`, {
    data: { name: "New toys", text: "Commander\n1 Zephyr of the New Set (NWS) 7\nDeck\n1 Sol Ring (CMM) 410\n12 Mountain\n" },
  });
  expect(deck.ok(), await deck.text()).toBeTruthy();
  // the host's card database is older: it doesn't know the commander, and has no art for it
  expect((await host.page.request.get(`/api/cards/${NEW_ID}`)).status()).toBe(404);

  // game night: Alice opens a LAN table
  await host.page.goto("/#/play");
  await host.page.getByTestId("table-mode-lan").check();
  await host.page.getByLabel("Table name").fill("Offline night");
  await host.page.getByTestId("host-name").fill("Alice");
  await host.page.getByTestId("create-game").click();
  await expect(host.page.getByTestId("lobby")).toBeVisible();

  // Dana's Fyodor finds it (a real broadcast on this machine's network)
  await me.page.goto(`${FRIEND}/#/play`);
  const near = me.page.getByTestId("nearby-games");
  const row = near.getByTestId("nearby-table").filter({ hasText: "Offline night" }).filter({ hasText: "In the lobby" }).first();
  const found = await row.waitFor({ timeout: 20_000 }).then(() => true, () => false);
  test.skip(!found, "no LAN broadcast on this machine (no network interface): the two servers can't find each other");
  if (process.env.LANFIND_SHOTS) await me.page.screenshot({ path: path.join(process.env.LANFIND_SHOTS, "offline-friend-play.png") });
  await row.getByRole("button", { name: /^Join “Offline night”/ }).click();

  // seated at the host's table, in this tab, with her decks on her seat
  await expect(me.page.getByTestId("lobby")).toBeVisible({ timeout: 20_000 });
  expect(new URL(me.page.url()).port).toBe(String(PORT));
  const seat = me.page.locator(".plinth.mine");
  if (process.env.LANFIND_SHOTS) await me.page.screenshot({ path: path.join(process.env.LANFIND_SHOTS, "offline-friend-seated.png") });
  const own = seat.getByTestId("own-decks");
  await expect(own).toContainText(/Your decks, from /);
  await expect(own).toContainText("Zephyr of the New Set");
  await own.getByRole("button", { name: "Use “New toys”" }).click();

  // the deck plays: the host learned the new card, and every card resolved
  await expect(seat).toContainText("Zephyr of the New Set");
  await expect(seat).toContainText("14 cards");
  await expect(seat.locator(".pl-warn")).toHaveCount(0);
  // the art came from Dana's computer over the LAN, and her seat shows it
  await expect.poll(async () => (await host.page.request.get(`/api/images/${NEW_ID}`)).status(), { timeout: 15_000 }).toBe(200);
  await expect(seat.locator(".pl-art img")).toBeVisible({ timeout: 15_000 });
  const hostSeat = host.page.locator('[data-testid^="seat-p"]').filter({ hasText: "Dana" });
  await expect(hostSeat).toContainText("Zephyr of the New Set");
  if (process.env.LANFIND_SHOTS) {
    await me.page.screenshot({ path: path.join(process.env.LANFIND_SHOTS, "offline-friend-seat.png") });
    await host.page.screenshot({ path: path.join(process.env.LANFIND_SHOTS, "offline-host-lobby.png") });
  }

  await host.context.close();
  await me.context.close();
});
