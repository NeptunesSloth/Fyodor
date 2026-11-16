/** Card-menu entries when automation is on: play / cast / activate, per-card automation, mana sources. */
import type { AbilityRow, MenuItem } from "../../components/ContextMenu";
import { useCardCache } from "../../state/cardCache";
import { isVisible, splitZone, type GameCard, type GameView } from "../../types/game";
import { abilityLines, automationOn, isLand, kickerItems, kickerLine, send, setPrefs, useXPrompt } from "./intents";

/** -- Star Trek beam me up (wave 112T) -- the server's label of a beam me up cost: "<source>: beam me up {cost}". */
const BEAM = /^(.*): beam me up ((?:\{[^}]+\})+)$/;

/** -- pod audit -- 709.3, 715.3: a split card (not a Room) or an adventure, cast from the hand as the half the player chooses. */
const twoSpells = (data?: { layout: string; faces: { name: string; mana_cost?: string | null }[] }): data is { layout: string; faces: { name: string; mana_cost?: string | null }[] } =>
  (data?.layout === "split" || data?.layout === "adventure") && data.faces.length === 2;

/** -- Rooms (wave 18G) -- 709.5: a split card whose halves share one Room type line. */
const isRoom = (data?: { layout: string; faces: { type_line?: string | null }[] }): data is { layout: string; faces: { name: string; mana_cost?: string | null; type_line?: string | null }[] } =>
  data?.layout === "split" && data.faces.length === 2 && data.faces.every((f) => /\bRoom\b/.test(f.type_line ?? ""));

/**
 * An activated ability as a menu row: cost and effect split at the first ": " outside quotes (602.1), shown whole with mana
 * symbols, and when it can't be activated now, the likeliest plain reason (only facts the client sees; the server decides).
 */
export function abilityRow(line: string, card: GameCard, view: GameView, ready: boolean): AbilityRow {
  const text = line.replace(/\s*\([^)]*\)\s*$/, "").trim(); // reminder text
  const m = /^([^:"]*?):\s+([\s\S]+)$/.exec(text);
  const [cost, effect] = m ? [m[1]!, m[2]!] : ["", text];
  if (ready) return { cost, effect };
  const hints = view.rules?.hints;
  const stack = (view.zones?.["stack"] as string[] | undefined)?.length ?? 0;
  const mine = view.turn?.active_player === card.controller;
  const main = view.turn?.phase === "main1" || view.turn?.phase === "main2";
  let why = "Can't be activated right now";
  if (!hints?.has_priority) why = "Wait for priority";
  else if (/\{T\}/.test(cost) && card.tapped) why = "Already tapped";
  else if (/\{[TQ]\}/.test(cost) && hints?.summoning_sick?.includes(card.id)) why = "Summoning sick: it came under your control this turn";
  else if (/\{Q\}/.test(cost) && !card.tapped) why = "Needs to be tapped first";
  else if (/activate only as a sorcery/i.test(effect) && (!mine || !main || stack > 0)) why = "Sorcery speed: your main phase, empty stack";
  else if (/activate only during your turn/i.test(effect) && !mine) why = "Only during your turn";
  else if (/activate only once each turn/i.test(effect)) why = "Once each turn (maybe used)";
  else why = "Can't pay the cost, or no legal target";
  return { cost, effect, why };
}

export function rulesMenu(card: GameCard, view: GameView, me: string): MenuItem[] {
  const rules = view.rules;
  if (!rules || !automationOn(view) || !isVisible(card)) return [];
  const { zone, player } = splitZone(card.zone);
  const items: MenuItem[] = [];
  const hints = rules.hints;
  const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
  // A card in another player's exile is yours to cast or play when the server lists it in your hints (Hostage Taker, Valgavoth).
  const offered = zone === "exile" && player !== me && !!(hints.castable?.includes(card.id) || hints.free_castable?.includes(card.id)
    || hints.playable_lands?.includes(card.id) || hints.alt_castable?.[card.id]);
  const mine = card.controller === me || offered
    || (player === me && (zone === "hand" || zone === "command" || zone === "graveyard" || zone === "exile" || zone === "library"));
  const oracle = data?.faces?.[card.face ?? 0]?.oracle_text ?? data?.oracle_text ?? "";
  // Other zones (your graveyard, exile, the top of your library): only when the server says a
  // permission lets you (flashback, "you may play that card this turn", "… from the top of your library").
  const elsewhere = zone === "graveyard" || zone === "exile" || zone === "library";
  if (mine && zone === "hand" && isLand(card.id, view)) {
    items.push({ label: "Play land", disabled: !hints.playable_lands?.includes(card.id), onClick: () => void send({ type: "play_land", card_id: card.id }) });
  } else if (mine && elsewhere && isLand(card.id, view) && hints.playable_lands?.includes(card.id)) {
    items.push({ label: `Play land from ${zone}`, onClick: () => void send({ type: "play_land", card_id: card.id }) });
  } else if (mine && zone === "hand" && isRoom(data)) {
    // 709.5: a Room is cast as one half (its door is unlocked as it enters)
    data.faces.forEach((f, i) => items.push({ label: `Cast ${f.name} ${f.mana_cost ?? ""}`.trim(),
      onClick: () => void send({ type: "cast_spell", card_id: card.id, face: i }) }));
  } else if (mine && zone === "hand" && twoSpells(data)) {
    // -- pod audit -- 709.3: which half is chosen before the spell is cast (Revival // Revenge, Bonecrusher Giant // Stomp); the hint counts either half
    data.faces.forEach((f, i) => items.push({ label: `Cast ${f.name} ${f.mana_cost ?? ""}`.trim(), disabled: !hints.castable?.includes(card.id),
      onClick: () => void send({ type: "cast_spell", card_id: card.id, face: i }) }));
  } else if (mine && (zone === "hand" || zone === "command")) {
    items.push({ label: "Cast", disabled: !hints.castable?.includes(card.id), onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
  } else if (mine && elsewhere && hints.castable?.includes(card.id)) {
    // 702.127a: the aftermath half of a split card is cast from the graveyard, as that half (face 1).
    const aftermath = zone === "graveyard" && data?.faces?.[1] && /^aftermath\b/im.test(data.faces[1].oracle_text ?? "");
    if (aftermath) {
      items.push({ label: `Cast ${data?.faces?.[1]?.name ?? "the second half"} (aftermath)`, onClick: () => void send({ type: "cast_spell", card_id: card.id, face: 1 }) });
    }
    const flashback = zone === "graveyard" && abilityLines(oracle).some((l) => /^flashback \{/i.test(l));
    if (!aftermath) items.push({ label: flashback ? "Cast with flashback" : `Cast from ${zone}`, onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
  }
  // -- Chorus of the Conclave (wave 110C) -- 601.2b: any amount of extra mana for +1/+1 counters, announced with the cast (the server lists the cards)
  if (mine && hints.chorus?.includes(card.id)) {
    items.push({ label: "Cast with Chorus of the Conclave…", onClick: () => useXPrompt.setState({ action: { type: "cast_spell", card_id: card.id }, field: "chorus" }) });
  }
  if (mine && hints.free_castable?.includes(card.id) && !isLand(card.id, view)) {
    items.push({ label: "Cast without paying its mana cost", onClick: () => void send({ type: "cast_spell", card_id: card.id, free: true }) });
  }
  // Alternative costs written on cards (118.9): Force of Will's own, Jodah's for every spell. The server lists the
  // ones usable now; targets and the cards to exile or sacrifice are asked for as usual.
  if (mine && !isLand(card.id, view)) {
    for (const alt of hints.alt_castable?.[card.id] ?? []) {
      const what = alt.label.length > 60 ? alt.label.slice(0, 57) + "…" : alt.label;
      // -- Star Trek beam me up (wave 112T) -- from the graveyard, offered as flashback is: "Cast with beam me up {2}{W}" (a granted one names its source: Scotty)
      const beam = zone === "graveyard" ? BEAM.exec(alt.label) : null;
      const label = beam ? `Cast with beam me up ${beam[2]}${beam[1] !== (data?.name ?? card.name) ? ` (${beam[1]})` : ""}` : `Cast for alternative cost (${what})`;
      items.push({ label, onClick: () => void send({ type: "cast_spell", card_id: card.id, alt_cost: alt.id }) });
    }
    // Optional additional costs other permanents offer (Defiler of Vigor: "you may pay 2 life … cost {G} less").
    for (const opt of hints.optional_costs?.[card.id] ?? []) {
      // (pod audit: a split card's or an adventure's optional cost is for one half, named, 709.3)
      const half = opt.face !== undefined ? data?.faces?.[opt.face]?.name : undefined;
      items.push({ label: `Cast ${half ? `${half} ` : ""}and ${opt.label.replace(/^[^:]*: /, "")} (${opt.label.split(":")[0]})`,
        onClick: () => void send({ type: "cast_spell", card_id: card.id, optional_costs: [opt.id], ...(opt.face !== undefined ? { face: opt.face } : {}) }) });
    }
    // -- pod audit -- 118.9d: an optional additional cost with a cast without paying its mana cost (Deadly Rollick with Silverquill's casualty)
    for (const opt of hints.free_optional_costs?.[card.id] ?? []) {
      const half = opt.face !== undefined ? data?.faces?.[opt.face]?.name : undefined;
      items.push({ label: `Cast ${half ? `${half} ` : ""}without paying its mana cost and ${opt.label.replace(/^[^:]*: /, "")} (${opt.label.split(":")[0]})`,
        onClick: () => void send({ type: "cast_spell", card_id: card.id, free: true, optional_costs: [opt.id], ...(opt.face !== undefined ? { face: opt.face } : {}) }) });
    }
  }
  const morph = abilityLines(oracle).find((l) => /^(mega)?morph \{/i.test(l));
  const disguise = abilityLines(oracle).find((l) => /^disguise \{/i.test(l));
  const evoke = abilityLines(oracle).find((l) => /^evoke \{/i.test(l));
  if (mine && zone === "hand" && evoke) {
    items.push({ label: `Cast with ${evoke}`, onClick: () => void send({ type: "cast_spell", card_id: card.id, evoke: true }) });
  }
  const dash = abilityLines(oracle).find((l) => /^dash \{/i.test(l));
  if (mine && zone === "hand" && dash) {
    items.push({ label: `Cast with ${dash}`, onClick: () => void send({ type: "cast_spell", card_id: card.id, dash: true }) });
  }
  // 702.113a: awaken is an alternative cost: "Awaken 3—{4}{U}" (the counters go on a land chosen as a target).
  const awaken = abilityLines(oracle).find((l) => /^awaken \d+—/i.test(l));
  if (mine && zone === "hand" && awaken) {
    items.push({ label: `Cast with ${awaken}`, onClick: () => void send({ type: "cast_spell", card_id: card.id, awaken: true }) });
  }
  // 702.102a: a split card with fuse may be cast as both halves from the hand (one fused split spell).
  if (mine && zone === "hand" && abilityLines(oracle).some((l) => /^fuse\b/i.test(l))) {
    items.push({ label: "Cast both halves (fuse)", disabled: !hints.castable?.includes(card.id),
      onClick: () => void send({ type: "cast_spell", card_id: card.id, fuse: true }) });
  }
  const buyback = abilityLines(oracle).find((l) => /^buyback(?: \{|—)/i.test(l));
  if (mine && zone === "hand" && buyback) {
    items.push({ label: `Cast with ${buyback}`, disabled: !hints.castable?.includes(card.id),
      onClick: () => void send({ type: "cast_spell", card_id: card.id, buyback: true }) });
  }
  const kicker = kickerLine(oracle);
  if (mine && (zone === "hand" || zone === "command") && kicker) {
    items.push(...kickerItems(card.id, kicker, !!hints.castable?.includes(card.id)));
  }
  // -- granted replicate (wave 111R3) -- 702.56b: each replicate a permanent gives this spell (Hugh, First of Many) is paid
  // separately, in the order the server lists them (CastSpell.replicate); listed only for castable cards
  const replicates = hints.replicate111r3?.[card.id];
  if (mine && replicates?.length) {
    replicates.forEach((label, slot) => {
      const counts = (n: number) => replicates.map((_, i) => (i === slot ? n : 0));
      const cast = (n: number) => () => void send({ type: "cast_spell", card_id: card.id, replicate: counts(n) });
      items.push({ label: `Cast with ${label}`,
        submenu: [...[1, 2, 3].map((n) => ({ label: `Replicate ×${n}`, onClick: cast(n) })),
          { label: "Other count…", onClick: () => useXPrompt.setState({ action: { type: "cast_spell", card_id: card.id, replicate: counts(0) }, field: "replicate", slot }) }] });
    });
  }
  // 702.160a / 718.3: a prototype card may be cast prototyped (its alternative mana cost, power and toughness).
  const prototype = abilityLines(oracle).find((l) => /^prototype \{/i.test(l));
  if (mine && zone === "hand" && prototype) {
    items.push({ label: `Cast ${prototype.replace(/^prototype /i, "prototyped: ")}`, onClick: () => void send({ type: "cast_spell", card_id: card.id, prototype: true }) });
  }
  // 702.47a: cards in your hand with splice onto Arcane / onto instant or sorcery, revealed as this spell is cast.
  if (mine && zone === "hand" && /\b(?:Arcane|Instant|Sorcery)\b/.test(data?.type_line ?? "")) {
    const hand = (view.zones?.[`${me}:hand`] as string[] | undefined) ?? [];
    const splicers = hand.flatMap((id) => {
      const c = view.cards[id];
      const d = c && !c.hidden && c.card_id ? useCardCache.getState().cards[c.card_id] : undefined;
      return id !== card.id && d && /^splice onto /im.test(d.oracle_text ?? "") ? [{ id, name: d.name }] : [];
    });
    if (splicers.length > 0) {
      items.push({ label: "Cast with splice", disabled: !hints.castable?.includes(card.id),
        submenu: splicers.map((sp) => ({ label: `Splice ${sp.name}`,
          onClick: () => void send({ type: "cast_spell", card_id: card.id, splice: [sp.id] }) })) });
    }
  }
  // 702.94a: a card with miracle you just drew as the first card this turn may be revealed now (the server lists only your own).
  if (mine && zone === "hand" && hints.miracle?.includes(card.id)) {
    items.push({ label: "Reveal for miracle", onClick: () => void send({ type: "miracle_reveal", card_id: card.id }) });
  }
  // -- companion (wave 38D) -- 116.2g, 702.139a: your companion is put into your hand for {3}, a special action (the server checks the main
  // phase, the empty stack, the starting deck against the card's condition and the payment); it is the card's "Companion — …" line.
  if (player === me && zone === "companion") {
    const i = abilityLines(oracle).findIndex((l) => /^companion\s*—/i.test(l));
    if (i >= 0) items.push({ label: "Put into your hand ({3}, special action)", disabled: !hints.has_priority, onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
  }
  // 702.151a / 702.167a: reconfigure's attach and unattach abilities and craft are activated abilities the server adds after / in place of their
  // keyword line (rules/oracle.py): reconfigure's two come after all the printed lines (numbers n and n + 1 for n printed lines, so no
  // printed line's number moves), craft's is the line itself.
  if (mine && zone === "battlefield") {
    const lines = abilityLines(oracle);
    lines.forEach((line, i) => {
      if (/^reconfigure(?: (?:\{[^}]+\})+|—.+)\.?$/i.test(line)) {
        const ready = (n: number) => !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === n);
        const [attach, unattach] = [lines.length, lines.length + 1];
        items.push({ label: `Reconfigure: attach (${line.replace(/^reconfigure(?: |—)/i, "").replace(/\.$/, "")})`, disabled: !ready(attach), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: attach }) });
        items.push({ label: `Reconfigure: unattach (${line.replace(/^reconfigure(?: |—)/i, "").replace(/\.$/, "")})`, disabled: !ready(unattach), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: unattach }) });
      } else if (/^craft with /i.test(line)) {
        const ready = !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === i);
        items.push({ label: `Activate: ${line}`, section: "Abilities", ability: abilityRow(line, card, view, ready), disabled: !ready, onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
      }
    });
  }
  if (mine && zone === "graveyard") {
    abilityLines(oracle).forEach((line, i) => {
      if (/^unearth \{/i.test(line)) {
        items.push({ label: line, onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
        return;
      }
      // 113.6m: an ability whose cost exiles the card from the graveyard works only there. Offered
      // when its cost says so or the server lists it; enabled only when the server lists it.
      const listed = !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === i);
      const cost = /^([^:"]*):\s/.exec(line)?.[1];
      if (!listed && !(cost && /\bfrom (?:your|a|its owner's) graveyard\b/i.test(cost))) return;
      items.push({ label: `Activate: ${line}`, section: "Abilities", ability: abilityRow(line, card, view, listed), disabled: !listed,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
    });
  }
  // -- abilities in exile (wave 111R1) -- 113.6b: an ability that works while its card is exiled ("… Activate only during your turn
  // and only if this card is exiled.", which Q, Stacking the Deck grants to a card it exiles). Read from the server's list of the
  // card's abilities (stable index, granted ones included) and enabled only when the server says it can be activated now.
  if (mine && zone === "exile") {
    const listed = (i: number) => hints.activatable?.find((a) => a.card_id === card.id && a.ability === i);
    for (const ability of rules.stats?.[card.id]?.abilities ?? []) {
      const now = listed(ability.index);
      // (review 111R: only activated abilities — a triggered one given in exile, Uvilda's "if this card is exiled, remove a refine counter", isn't activated)
      if (ability.kind !== "activated" || (!now && !/\bif this card is exiled\b/i.test(ability.text))) continue;
      const line = ability.text.replace(/\s*\(.*$/, "");
      items.push({ label: `Activate: ${line}`, section: "Abilities", ability: abilityRow(line, card, view, !!now), disabled: !now,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: ability.index }) });
    }
  }
  if (mine && zone === "hand" && (morph || disguise)) {
    items.push({ label: `Cast face down (${morph ? "morph" : "disguise"}, {3})`, onClick: () => void send({ type: "cast_spell", card_id: card.id, face_down: true }) });
  }
  const room = rules.stats?.[card.id];
  if (mine && zone === "battlefield" && room?.doors && room.halves) {
    // 116.2m, 709.5e: the unlock special action — pay a locked half's mana cost (the server checks the phase and the stack);
    // the halves come from the server (a copy of a Room has the copied card's, 709.5b)
    const open = room.doors;
    room.halves.forEach((f, i) => {
      if (!open.includes(i + 1)) items.push({ label: `Unlock ${f.name} ${f.mana_cost ?? ""}`.trim(), disabled: !hints.has_priority,
        onClick: () => void send({ type: "unlock_door", card_id: card.id, door: i + 1 }) });
    });
  }
  // -- licids (wave 50A) -- 116.2c: "You may pay {W} to end this effect" is a special action of the effect's player (any time they have priority, no stack); the
  // server lists the cost only to that player, on the permanent the effect is on
  const endCost = rules.stats?.[card.id]?.end_cost;
  if (zone === "battlefield" && endCost) {
    items.push({ label: `${rules.stats?.[card.id]?.end_label ?? "End the effect"} (${endCost}, special action)`, disabled: !hints.has_priority, onClick: () => void send({ type: "end_effect", card_id: card.id }) });
  }
  if (mine && zone === "battlefield" && card.face_down) {
    const ways = rules.stats?.[card.id]?.turn_up;
    if (ways?.length) {
      for (const way of ways) items.push({ label: `Turn face up (${way.method === "mana_cost" ? "mana cost" : way.method}, ${way.cost})`,
        disabled: !hints.has_priority, onClick: () => void send({ type: "turn_face_up", card_id: card.id, method: way.method }) });
    } else if (morph || disguise) {
      items.push({ label: `Turn face up (${morph ?? disguise})`, onClick: () => void send({ type: "turn_face_up", card_id: card.id }) });
    }
  }
  if (mine && zone === "hand") {
    const text = oracle;
    abilityLines(text).forEach((line, i) => {
      // (wave 5A) 113.6m / 605.3a: "Exile this card from your hand: Add {R}." (Simian Spirit Guide)
      // (wave 24C) 702.57a: "Forecast — {1}{U}, Reveal this card from your hand: …" (the server checks the upkeep and once each turn)
      if (/^(?:(?:(?:basic|artifact) )?[a-z]+)?cycling \{/i.test(line) || /^cycling\s*[—-]/i.test(line) || /^suspend (?:\d+|X)\s*[—-]/i.test(line) || /^forecast\s*—/i.test(line)
        || /^Exile this card from your hand: Add /.test(line)
        // (review 24C) 113.6m: any other ability that works from the hand ("{B}, Reveal this card from your hand: …", channel) when the server lists it
        || !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === i)) {
        items.push({ label: line.replace(/\s*\(.*$/, ""), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
      }
    });
    // Zone grants use the server's stable ability index and are visible only with the card.
    for (const ability of rules.stats?.[card.id]?.abilities ?? []) {
      // (wave F1) Talon Gates' special action, offered on each nonland card in the planar controller's hand (the server checks the timing)
      if (ability.kind === "keywords" && /^(?:(?:(?:basic|artifact) )?[a-z]+)?cycling(?: \{|\s*[—-])/i.test(ability.text)
        || /^Talon Gates — Exile this card from your hand/.test(ability.text)) {
        items.push({ label: ability.text.replace(/\s*\(.*$/, ""), disabled: !hints.has_priority,
          onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: ability.index }) });
      }
    }
  }
  if (mine && zone === "battlefield") {
    const text = data?.faces?.[card.face ?? 0]?.oracle_text ?? data?.oracle_text ?? "";
    const lines = abilityLines(text);
    const abilities = lines
      .map((line, i) => ({ line, i }))
      .filter(({ line }) => /^[^.]*:\s/.test(line) && !/^(Enchant|Equip \{|Cycling)/.test(line) || /: Add /.test(line)
        || /^Crew \d+(?:\.|$)/.test(line) || /^Equip(?: |—)/.test(line));
    for (const { line, i } of abilities) {
      // Equip (702.6a) is checked by the server (sorcery speed, a creature you control): offered with priority.
      const ready = hints.activatable?.some((a) => a.card_id === card.id && a.ability === i) || /: Add /.test(line)
        || (/^Equip(?: |—)/.test(line) && !!hints.has_priority);
      items.push({ label: `Activate: ${line}`, section: "Abilities", ability: abilityRow(line, card, view, !!ready), disabled: !ready,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
    }
    for (const g of rules.stats?.[card.id]?.abilities ?? []) {
      if (g.kind !== "activated" && g.kind !== "mana") continue;
      const ready = g.kind === "mana" || hints.activatable?.some((a) => a.card_id === card.id && a.ability === g.index);
      const row = abilityRow(g.text, card, view, !!ready);
      items.push({ label: `Activate (granted): ${g.text}`, section: "Abilities", ability: { ...row, effect: `${row.effect} (granted)` }, disabled: !ready,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: g.index }) });
    }
    if (abilities.some(({ line }) => /: Add /.test(line))) {
      const current = rules.prefs?.mana_sources[card.id] ?? "normal";
      items.push({
        label: `Mana source: ${current.toUpperCase()}`,
        submenu: (["prefer", "normal", "save"] as const).map((p) => ({
          label: p.toUpperCase(), disabled: p === current,
          onClick: () => void setPrefs({ mana_source: card.id, mana_source_protection: p }),
        })),
      });
    }
  }
  if (card.zone === "stack") {
    items.push({ label: "Hold after this resolves", onClick: () => void setPrefs({ stop_after: card.id }) });
  }
  if (card.controller === me || card.owner === me) {
    const mode = rules.card_modes[card.id] ?? "auto";
    items.push({
      label: `Automation: ${mode.toUpperCase()}`,
      submenu: (["auto", "manual"] as const).map((m) => ({
        label: m === "manual" ? "MANUAL (resolve this card by hand)" : "AUTO", disabled: m === mode,
        onClick: () => void send({ type: "set_card_automation", card_id: card.id, mode: m }),
      })),
    });
  }
  return items.length ? [...items, "separator" as const] : [];
}
