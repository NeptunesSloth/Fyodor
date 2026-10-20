import { expect, test } from "@playwright/test";

/** Ordinary banding: declare a legal band through the real controls, reject two nonbanders, and reconnect. */
test("attacking bands can be declared, validated, and restored after reconnect", async ({ page }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = [
    "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Benalish Hero\n1 Mesa Pegasus\n1 Grizzly Bears\n1 Llanowar Elves\n20 Forest",
    "Commander\n1 Krenko, Mob Boss\nDeck\n1 Grizzly Bears\n20 Forest",
  ];
  const ids: string[] = [];
  for (const text of decks) {
    const res = await page.request.post("/api/decks", { data: { text } });
    expect(res.ok(), await res.text()).toBeTruthy();
    ids.push((await res.json()).id);
  }
  const created = await page.request.post("/api/games", { data: {
    name: "Banding", format: "commander", mode: "local", shuffle: false, first_player: 0,
    mulligan_rule: "none", automation: "full", priority_helper: "off",
    players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const gid = (await created.json()).game.id as string;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as Record<string, any>;
  const act = async (actor: string, action: Record<string, unknown>) => {
    const res = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as: actor, viewer: "p1" } });
    expect(res.ok(), await res.text()).toBeTruthy();
  };
  for (const pid of ["p1", "p2"]) await act(pid, { type: "set_prefs", response: "on" });
  let v = await view();
  const named = (name: string, owner = "p1") => Object.entries(v.cards).find(([, c]: [string, any]) => c.name === name && c.owner === owner)![0];
  const hero = named("Benalish Hero");
  const bear = named("Grizzly Bears");
  const elf = named("Llanowar Elves");
  const pegasus = named("Mesa Pegasus");
  const defender = named("Grizzly Bears", "p2");
  for (const cid of [hero, bear, elf, pegasus, defender]) {
    await act(cid === defender ? "p2" : "p1", { type: "move", card_ids: [cid], to: { player: cid === defender ? "p2" : "p1", zone: "battlefield" } });
  }
  for (let i = 0; i < 180; i++) {
    v = await view();
    const d = v.rules.decision;
    if (v.turn.number >= 3 && v.turn.active_player === "p1" && d?.kind === "declare_attackers") break;
    if (!d) await act(v.rules.priority, { type: "pass_priority" });
    else if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
    else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o: any) => o.id) });
  }
  expect(v.rules.decision?.kind).toBe("declare_attackers");
  await page.goto(`/#/game/${gid}`);
  for (const cid of [hero, bear, elf]) {
    await page.getByTestId(`attack-${cid}`).selectOption("t:p2");
    await page.getByTestId(`band-${cid}`).selectOption("1");
  }
  await expect(page.getByRole("alert")).toContainText("at most one creature without");
  await expect(page.getByTestId("declare-attackers")).toBeDisabled();
  await page.getByTestId(`band-${elf}`).selectOption("");
  await page.getByTestId(`attack-${elf}`).selectOption("");
  await expect(page.getByTestId("declare-attackers")).toBeEnabled();
  await page.getByTestId("declare-attackers").click();
  await expect.poll(async () => (await view()).rules.attacking_bands).toEqual([[hero, bear]]);
  await expect(page.getByTestId("attacking-bands")).toContainText("1 attacking band");
  await page.getByTestId("attacking-bands").locator("summary").click();
  await expect(page.getByTestId("attacking-bands")).toContainText("Benalish Hero + Grizzly Bears");
  await page.reload();
  await expect(page.getByTestId("attacking-bands")).toContainText("1 attacking band");
  expect((await view()).rules.attacking_bands).toEqual([[hero, bear]]);
});

/** Qualified bands allow several matching creatures without ordinary banding. */
test("bands with other legendary creatures allow a matching group and reject a nonlegendary member", async ({ page }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const ids: string[] = [];
  for (const text of [
    "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Karador, Ghost Chieftain\n1 Honest Rutstein\n1 Grizzly Bears\n1 Cathedral of Serra\n20 Forest",
    "Commander\n1 Krenko, Mob Boss\nDeck\n1 Grizzly Bears\n20 Forest",
  ]) {
    const res = await page.request.post("/api/decks", { data: { text } });
    expect(res.ok(), await res.text()).toBeTruthy();
    ids.push((await res.json()).id);
  }
  const created = await page.request.post("/api/games", { data: {
    name: "Qualified banding", format: "commander", mode: "local", shuffle: false, first_player: 0,
    mulligan_rule: "none", automation: "full", priority_helper: "off",
    players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }],
  } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const gid = (await created.json()).game.id as string;
  const view = async () => (await (await page.request.get(`/api/games/${gid}/view?viewer=all`)).json()) as Record<string, any>;
  const act = async (actor: string, action: Record<string, unknown>) => {
    const res = await page.request.post(`/api/games/${gid}/actions`, { data: { action, as: actor, viewer: "p1" } });
    expect(res.ok(), await res.text()).toBeTruthy();
  };
  for (const pid of ["p1", "p2"]) await act(pid, { type: "set_prefs", response: "on" });
  let v = await view();
  const named = (name: string, owner = "p1") => Object.entries(v.cards).find(([, c]: [string, any]) => c.name === name && c.owner === owner)![0];
  const members = [named("Atraxa, Praetors' Voice"), named("Karador, Ghost Chieftain"), named("Honest Rutstein")];
  const bear = named("Grizzly Bears");
  const land = named("Cathedral of Serra");
  const defender = named("Grizzly Bears", "p2");
  for (const cid of [...members, bear, land, defender]) {
    await act(cid === defender ? "p2" : "p1", { type: "move", card_ids: [cid], to: { player: cid === defender ? "p2" : "p1", zone: "battlefield" } });
  }
  for (let i = 0; i < 180; i++) {
    v = await view();
    const d = v.rules.decision;
    if (v.turn.number >= 3 && v.turn.active_player === "p1" && d?.kind === "declare_attackers") break;
    if (!d) await act(v.rules.priority, { type: "pass_priority" });
    else if (d.kind === "declare_attackers") await act(d.player, { type: "declare_attackers", attackers: [] });
    else if (d.kind === "declare_blockers") await act(d.player, { type: "declare_blockers", blocks: [] });
    else await act(d.player, { type: "choose", decision_id: d.id, option_ids: d.options.slice(0, Math.max(1, d.min_choices)).map((o: any) => o.id) });
  }
  expect(v.rules.decision?.kind).toBe("declare_attackers");
  expect(v.rules.decision.display.banding).toEqual([]);
  await page.goto(`/#/game/${gid}`);
  for (const cid of [...members, bear]) {
    await page.getByTestId(`attack-${cid}`).selectOption("t:p2");
    await page.getByTestId(`band-${cid}`).selectOption("1");
  }
  await expect(page.getByRole("alert")).toContainText("matching creatures");
  await expect(page.getByTestId("declare-attackers")).toBeDisabled();
  await page.getByTestId(`attack-${bear}`).selectOption("");
  await expect(page.getByTestId("declare-attackers")).toBeEnabled();
  await page.getByTestId("declare-attackers").click();
  await expect.poll(async () => (await view()).rules.attacking_bands).toEqual([members]);
  await expect(page.getByTestId("attacking-bands")).toContainText("1 attacking band");
  await page.reload();
  await expect(page.getByTestId("attacking-bands")).toContainText("1 attacking band");
});
