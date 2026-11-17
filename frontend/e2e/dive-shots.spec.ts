import { expect, test, type Page } from "@playwright/test";

/**
 * -- dive (wave DV) -- review frames: teaching the real keyword action "dive" as *an action* in Teach Fyodor (it can't be blocked until
 * it deals combat damage while attacking — docs/TEACH_FYODOR.md's worked example), then ▶ Try it: the creature attacks unblocked at the
 * table with its "Can't be blocked" marker, connects, and can be blocked again. Skipped unless SHOT_DIR is set; point E2E_PORT at a
 * server with the real card database (no printed card says "dives" yet, so a plain creature stands in for one that dives as it enters).
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(300_000);

async function prefs(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free" } }] }));
  });
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

interface View {
  turn: { phase: string; number?: number; active?: string };
  seat_order: string[];
  zones: Record<string, string[]>;
  cards: Record<string, { name?: string; effects?: { name?: string; text?: string }[] }>;
  rules?: { decision?: { id: string; kind: string; player: string; options: { id: string }[] } | null; priority?: string | null } | null;
  players: { id: string; life: number; name?: string }[];
  stack: string[];
}

const lifeOf = (v: View, pid: string) => v.players.find((p) => p.id === pid)?.life ?? 40;

test("teach dive as an action, then a diving creature attacks unblocked", async ({ page }) => {
  await prefs(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/teach");
  await expect(page.getByTestId("teach-page")).toBeVisible();
  await page.getByTestId("teach-kind-action").click();
  await page.getByTestId("teach-name").fill("dive");
  await page.getByPlaceholder("What the card says in brackets").fill("It can't be blocked until it deals combat damage while attacking.");
  // the one Do piece: Can't be blocked until … — its duration chip → "until it deals combat damage while attacking"
  await page.getByRole("button", { name: "Can't be blocked until …", exact: true }).click();
  await page.getByRole("button", { name: /^dur: rdur_turn\. Change$/ }).click();
  await page.getByRole("option", { name: "until it deals combat damage while attacking" }).click();
  await expect(page.getByTestId("teach-sentence")).toHaveText("It can't be blocked until it deals combat damage while attacking.");
  await expect(page.getByTestId("teach-phrase")).toContainText("When this creature enters, it dives.");
  await expect(page.getByTestId("teach-verdict")).toHaveText(/Fyodor understands/, { timeout: 30_000 });
  await page.waitForTimeout(400);
  await shot(page, "dive-01-taught-as-an-action");

  // keep it, then Try it
  await page.getByTestId("teach-save").click();
  await expect(page.locator(".t-rows li")).toHaveCount(1);
  await page.getByTestId("teach-try").click();
  await page.waitForURL(/#\/game\//, { timeout: 30_000 });
  const id = page.url().split("#/game/")[1]!.split("?")[0]!;
  const token = await page.evaluate((gid) => localStorage.getItem(`fyodor.seat.${gid}`), id);
  const headers: Record<string, string> = token ? { "x-seat-token": token } : {};
  const view = async (): Promise<View> => (await (await page.request.get(`/api/games/${id}/view`, { headers })).json()) as View;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${id}/actions`, { headers, data: { action } });
    if (!r.ok()) throw new Error(`${JSON.stringify(action)}: ${await r.text()}`);
  };
  let v = await view();
  const dummy = v.seat_order.find((p) => p !== "p1")!;
  const hand = v.zones["p1:hand"]!;
  expect(hand).toHaveLength(1);
  const diver = hand[0]!;
  // cast the stand-in (mana added by the host, so no payment prompt), then on through the turns; stop in the declare-blockers step
  // too, to see it attacking (the engine passes the other steps for you)
  await act({ type: "set_stops", own: ["main1", "declare_blockers", "main2"], others: [], smart_pass: false });
  await act({ type: "add_mana", player: "p1", mana: { W: 2, U: 2, B: 2, R: 2, G: 2, C: 3 } });
  await act({ type: "cast_spell", card_id: diver });
  let attacked = false;
  for (let i = 0; i < 80 && !attacked; i++) {
    v = await view();
    const d = v.rules?.decision ?? null;
    if (d && d.player === "p1") {
      if (d.kind === "declare_attackers") {
        if ((v.turn.number ?? 0) >= 3) {
          await act({ type: "declare_attackers", attackers: [{ card_id: diver, target: dummy }] });
          attacked = true;
        } else await act({ type: "declare_attackers", attackers: [] });
      } else if (d.kind === "declare_blockers") await act({ type: "declare_blockers", blocks: [] });
      else await act({ type: "choose", decision_id: d.id, option_ids: d.options.slice(0, 1).map((o) => o.id) });
    } else if (d) {
      await page.waitForTimeout(300); // (the dummy's own answer)
    } else if (!v.rules?.priority || v.rules.priority === "p1") await act({ type: "pass_priority" });
    else await page.waitForTimeout(300);
  }
  expect(attacked).toBeTruthy();
  // attacking, unblocked: the marker on the creature says why
  for (let i = 0; i < 20; i++) {
    v = await view();
    if (v.turn.phase === "declare_blockers" && !(v.rules?.decision)) break;
    await page.waitForTimeout(300);
  }
  const marks = (v.cards[diver]?.effects ?? []).map((e) => `${e.name ?? ""} ${e.text ?? ""}`);
  expect(marks.some((m) => /blocked/i.test(m) && /combat damage while attacking/.test(m)), marks.join(" | ")).toBeTruthy();
  await page.waitForTimeout(2500);
  await shot(page, "dive-02-attacking-unblocked");

  // it connects: the dummy loses life, and the dive ends — it can be blocked again
  const before = lifeOf(v, dummy);
  for (let i = 0; i < 12; i++) {
    v = await view();
    if (lifeOf(v, dummy) < before) break;
    const d = v.rules?.decision ?? null;
    if (d?.player === "p1" && d.kind !== "declare_attackers" && d.kind !== "declare_blockers") {
      await act({ type: "choose", decision_id: d.id, option_ids: d.options.slice(0, 1).map((o) => o.id) });
    } else if (!d && (!v.rules?.priority || v.rules.priority === "p1")) await act({ type: "pass_priority" });
    else await page.waitForTimeout(300);
  }
  v = await view();
  expect(lifeOf(v, dummy)).toBeLessThan(before);
  expect((v.cards[diver]?.effects ?? []).some((e) => /combat damage while attacking/.test(e.text ?? ""))).toBeFalsy();
  await page.waitForTimeout(2000);
  await shot(page, "dive-03-connected-can-be-blocked-again");
});
