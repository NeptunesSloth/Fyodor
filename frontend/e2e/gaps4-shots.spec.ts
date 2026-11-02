import * as fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, hostLobby, joinLobby, newPlayer, remoteDevice, saveDecks } from "./helpers";

/**
 * Frames for review of two table fixes: what a player who is out of the game is still invited to do (the hand's hint, the
 * seat buttons, the game-moving keys), and the lobby's styles no longer reaching the game screen (the 2D top bar's room code
 * and the seat plate's name button must look exactly as before, and the lobby too). Skipped unless SHOT_DIR is set;
 * SHOT_ONLY picks one; SHOT_BEFORE=1 takes the frames and the computed styles without the checks (the before state). Run
 * after a before run, the CSS test compares every computed style of the top bar, the seat plates and the lobby with it.
 */
const OUT = process.env.SHOT_DIR ?? "";
const ONLY = process.env.SHOT_ONLY ?? "";
const BEFORE = !!process.env.SHOT_BEFORE;
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

const tag = BEFORE ? "before" : "after";

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
}

async function pastIntro(page: Page) {
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect(intro).toHaveCount(0);
}

/** Every computed style of `selector`'s elements and all their descendants, keyed by a stable DOM path. */
async function computed(page: Page, selector: string): Promise<Record<string, Record<string, string>>> {
  return page.evaluate((sel) => {
    const out: Record<string, Record<string, string>> = {};
    const path = (el: Element): string => {
      const parts: string[] = [];
      for (let e: Element | null = el; e && e !== document.body; e = e.parentElement) {
        const i = e.parentElement ? [...e.parentElement.children].indexOf(e) : 0;
        parts.unshift(`${e.tagName.toLowerCase()}${e.classList.length ? `.${[...e.classList].sort().join(".")}` : ""}:${i}`);
      }
      return parts.join(">");
    };
    document.querySelectorAll(sel).forEach((root) => {
      for (const el of [root, ...root.querySelectorAll("*")]) {
        for (const pseudo of [null, "::before", "::after"]) {
          const cs = getComputedStyle(el, pseudo);
          if (pseudo && (cs.content === "none" || cs.content === "normal")) continue;
          const props: Record<string, string> = {};
          for (let i = 0; i < cs.length; i++) props[cs[i]!] = cs.getPropertyValue(cs[i]!);
          const r = el.getBoundingClientRect();
          props["@rect"] = [r.x, r.y, r.width, r.height].map((n) => n.toFixed(2)).join(",");
          out[`${path(el)}${pseudo ?? ""}`] = props;
        }
      }
    });
    return out;
  }, selector);
}

/** The room code is new each run: the same letters every time, so two runs compare (proportional type changes its width). */
async function fixedCode(page: Page) {
  await page.evaluate(() => {
    const top = document.querySelector(".game-top .room-code");
    if (top) top.textContent = "Room QWERTY";
    const lobby = document.querySelector('.lobby [data-testid="room-code"]');
    if (lobby) lobby.textContent = "QWERTY";
  });
}

/**
 * Save this run's computed styles; after a before run, compare with it and list every difference. The one change made on
 * purpose: the top bar's room code is a label, not a button, so it no longer shows the lobby button's pointer cursor.
 */
const ALLOWED = [/span\.room-code:\d+ cursor: pointer -> auto$/];
function compare(name: string, now: Record<string, Record<string, string>>): string[] {
  fs.writeFileSync(`${OUT}/${tag}-${name}.styles.json`, JSON.stringify(now, null, 1));
  const file = `${OUT}/before-${name}.styles.json`;
  if (BEFORE || !fs.existsSync(file)) return [];
  const was = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, Record<string, string>>;
  const diffs: string[] = [];
  for (const key of new Set([...Object.keys(was), ...Object.keys(now)])) {
    const a = was[key], b = now[key];
    if (!a || !b) {
      diffs.push(`${key}: ${a ? "gone" : "new"}`);
      continue;
    }
    for (const p of new Set([...Object.keys(a), ...Object.keys(b)])) if (a[p] !== b[p]) diffs.push(`${key} ${p}: ${a[p]} -> ${b[p]}`);
  }
  fs.writeFileSync(`${OUT}/diff-${name}.txt`, diffs.join("\n"));
  return diffs.filter((d) => !ALLOWED.some((re) => re.test(d)));
}

test("2D table at a LAN table: the top bar's room code and the seat plates look exactly as before", async ({ page, browser }) => {
  test.skip(!!ONLY && ONLY !== "css", "SHOT_ONLY");
  test.setTimeout(150_000);
  const decks = await saveDecks(page, [ALICE_DECK, BOB_DECK]);
  const res = await page.request.post("/api/games", { data: { name: "Plates", mode: "lan", automation: "full", mulligan_rule: "none", shuffle: false, first_player: 0,
    players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const { game } = (await res.json()) as { game: { id: string; code: string } };
  const context = await browser.newContext(remoteDevice());
  const guest = await context.newPage();
  const token = ((await (await guest.request.post("/api/join", { data: { code: game.code } })).json()) as { token: string }).token;
  await prefs(guest, "2d");
  await guest.addInitScript(([id, t]) => localStorage.setItem(`fyodor.seat.${id}`, t), [game.id, token] as const);
  for (const [w, h] of [[1440, 900], [1920, 1080]] as const) {
    await guest.setViewportSize({ width: w, height: h });
    await guest.goto(`/#/game/${game.id}`);
    await expect(guest.locator(".game-top .room-code")).toBeVisible();
    await pastIntro(guest);
    await guest.mouse.move(w / 2, h / 2);
    await guest.waitForTimeout(800);
    await fixedCode(guest);
    await guest.locator(".game-top").screenshot({ path: `${OUT}/${tag}-topbar-${w}.png` });
    for (const pid of ["p1", "p2"]) await guest.locator(`.t3d-seat[data-player-id="${pid}"]`).screenshot({ path: `${OUT}/${tag}-plate-${pid}-${w}.png` });
    await guest.screenshot({ path: `${OUT}/${tag}-table-${w}.png` });
    const diffs = compare(`game-${w}`, await computed(guest, ".game-top, .t3d-seat"));
    console.log(`game ${w}: ${diffs.length} computed-style differences`);
    if (!BEFORE) expect(diffs).toEqual([]);
  }
  await context.close();
});

test("the lobby looks exactly as before", async ({ browser }) => {
  test.skip(!!ONLY && ONLY !== "css", "SHOT_ONLY");
  test.setTimeout(150_000);
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  for (const p of [host.page, guest.page]) await prefs(p, "2d");
  const { code } = await hostLobby(host.page, { name: "Alice", turnOrder: "pod" });
  await joinLobby(guest.page, code, "Bob");
  await expect(host.page.getByTestId("seat-p2")).toContainText("Bob");
  for (const [w, h] of [[1440, 900], [1920, 1080]] as const) {
    await host.page.setViewportSize({ width: w, height: h });
    await host.page.mouse.move(2, h - 2);
    await host.page.waitForTimeout(800);
    await fixedCode(host.page);
    await host.page.screenshot({ path: `${OUT}/${tag}-lobby-${w}.png` });
    const diffs = compare(`lobby-${w}`, await computed(host.page, ".lobby"));
    console.log(`lobby ${w}: ${diffs.length} computed-style differences`);
    if (!BEFORE) expect(diffs).toEqual([]);
  }
  await host.context.close();
  await guest.context.close();
});

test("2D: a player who is out is no longer invited to draw, and their game-moving keys do nothing", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "out", "SHOT_ONLY");
  test.setTimeout(120_000);
  await prefs(page, "2d");
  const decks = await saveDecks(page, [ALICE_DECK, BOB_DECK, BOB_DECK]);
  const res = await page.request.post("/api/games", {
    data: { name: "Out", mode: "local", automation: "full", shuffle: false, first_player: 0, mulligan_rule: "none", players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i]!.id })) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const sent: string[] = [];
  page.on("websocket", (ws) => ws.on("framesent", (f) => sent.push(String(f.payload))));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await pastIntro(page);
  await expect(page.getByTestId("seat-buttons")).toBeVisible(); // still in: the seat's buttons by the mat
  await act("p1", { type: "concede" });
  await expect(page.getByTestId("eliminated-scene").or(page.getByTestId("eliminated-hub"))).toBeVisible({ timeout: 10_000 });
  if (await page.getByTestId("eliminated-scene").isVisible().catch(() => false)) await page.getByTestId("eliminated-scene").click();
  await page.getByTestId("eliminated-hub").getByRole("button", { name: "Keep watching" }).click();
  await expect(page.getByTestId("priority-holder")).toHaveText(/.+/);
  await page.mouse.move(720, 300);
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/${tag}-out-table.png` });
  sent.length = 0;
  for (const key of ["d", "n", "u", "Shift+N", "d"]) {
    await page.keyboard.press(key);
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${tag}-out-keys.png` });
  const actions = sent.filter((f) => f.includes('"type":"action"')).map((f) => (JSON.parse(f) as { action: { type: string } }).action.type);
  const toasts = await page.locator(".toast").allTextContents();
  console.log("out: actions sent", JSON.stringify(actions), "toasts", JSON.stringify(toasts));
  if (!BEFORE) {
    await expect(page.locator(".hand-empty")).toHaveCount(0); // no "press D to draw"
    await expect(page.getByTestId("seat-buttons")).toHaveCount(0); // no Untap / Draw / Scry / Mill / Reveal / Mulligan
    expect(actions).toEqual([]); // D, N, U, Shift+N sent nothing the server would refuse
    expect(toasts.filter((t) => t.includes("You're out of this game"))).toHaveLength(1); // the reason, once
    // looking around still works: 2 looks at the next player's board, 1 comes back
    await page.keyboard.press("2");
    await expect(page.locator(".opponents.focused")).toHaveCount(1);
    await page.keyboard.press("1");
    await expect(page.locator(".opponents.focused")).toHaveCount(0);
  }
});
