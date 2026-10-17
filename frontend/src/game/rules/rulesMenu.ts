/** Card-menu entries when automation is on: play / cast / activate, per-card automation, mana sources. */
import type { MenuItem } from "../../components/ContextMenu";
import { useCardCache } from "../../state/cardCache";
import { isVisible, splitZone, type GameCard, type GameView } from "../../types/game";
import { abilityLines, automationOn, isLand, send, setPrefs } from "./intents";

/** 702.33a / 702.33c: a "Kicker {cost}" or "Multikicker {cost}" keyword line (mana costs only, as the server pays them). */
const KICKER = /^(?:(?:multi)?kicker|entwine) (?:\{[^}]+\})+$|^entwine—|^kicker—/i; // (702.42a entwine: kicker's count 1 is "choose all modes"; wave 43D: "Kicker—Sacrifice a land.", paid by the server)
/** Multikicker: how many times to pay (a submenu; more is rare enough to do by hand). */
export const MULTIKICKER_COUNTS = [1, 2, 3, 4, 5, 6];

/** -- Rooms (wave 18G) -- 709.5: a split card whose halves share one Room type line. */
const isRoom = (data?: { layout: string; faces: { type_line?: string | null }[] }): data is { layout: string; faces: { name: string; mana_cost?: string | null; type_line?: string | null }[] } =>
  data?.layout === "split" && data.faces.length === 2 && data.faces.every((f) => /\bRoom\b/.test(f.type_line ?? ""));

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
  if (mine && hints.free_castable?.includes(card.id) && !isLand(card.id, view)) {
    items.push({ label: "Cast without paying its mana cost", onClick: () => void send({ type: "cast_spell", card_id: card.id, free: true }) });
  }
  // Alternative costs written on cards (118.9): Force of Will's own, Jodah's for every spell. The server lists the
  // ones usable now; targets and the cards to exile or sacrifice are asked for as usual.
  if (mine && !isLand(card.id, view)) {
    for (const alt of hints.alt_castable?.[card.id] ?? []) {
      const what = alt.label.length > 60 ? alt.label.slice(0, 57) + "…" : alt.label;
      items.push({ label: `Cast for alternative cost (${what})`, onClick: () => void send({ type: "cast_spell", card_id: card.id, alt_cost: alt.id }) });
    }
    // Optional additional costs other permanents offer (Defiler of Vigor: "you may pay 2 life … cost {G} less").
    for (const opt of hints.optional_costs?.[card.id] ?? []) {
      items.push({ label: `Cast and ${opt.label.replace(/^[^:]*: /, "")} (${opt.label.split(":")[0]})`,
        onClick: () => void send({ type: "cast_spell", card_id: card.id, optional_costs: [opt.id] }) });
    }
  }
  const morph = abilityLines(oracle).find((l) => /^(mega)?morph \{/i.test(l));
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
  const kicker = abilityLines(oracle).find((l) => KICKER.test(l));
  if (mine && (zone === "hand" || zone === "command") && kicker) {
    const castable = !!hints.castable?.includes(card.id);
    const cast = (times: number) => () => void send({ type: "cast_spell", card_id: card.id, kicker: times });
    if (/^multikicker/i.test(kicker)) {
      // 702.33c: any number of times. The server checks the total cost when it's paid.
      items.push({ label: `Cast with ${kicker}`, disabled: !castable,
        submenu: MULTIKICKER_COUNTS.map((n) => ({ label: `Kicked ×${n}`, onClick: cast(n) })) });
    } else {
      items.push({ label: `Cast with ${kicker}`, disabled: !castable, onClick: cast(1) });
    }
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
      if (/^reconfigure (?:\{[^}]+\})+$/i.test(line)) {
        const ready = (n: number) => !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === n);
        const [attach, unattach] = [lines.length, lines.length + 1];
        items.push({ label: `Reconfigure: attach (${line.replace(/^reconfigure /i, "")})`, disabled: !ready(attach), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: attach }) });
        items.push({ label: `Reconfigure: unattach (${line.replace(/^reconfigure /i, "")})`, disabled: !ready(unattach), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: unattach }) });
      } else if (/^craft with /i.test(line)) {
        const ready = !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === i);
        items.push({ label: `Activate: ${line.length > 60 ? line.slice(0, 57) + "…" : line}`, disabled: !ready, onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
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
      items.push({ label: `Activate: ${line.length > 60 ? line.slice(0, 57) + "…" : line}`, disabled: !listed,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
    });
  }
  if (mine && zone === "hand" && morph) {
    items.push({ label: "Cast face down (morph, {3})", onClick: () => void send({ type: "cast_spell", card_id: card.id, face_down: true }) });
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
  if (mine && zone === "battlefield" && card.face_down && morph) {
    items.push({ label: `Turn face up (${morph})`, onClick: () => void send({ type: "turn_face_up", card_id: card.id }) });
  }
  if (mine && zone === "hand") {
    const text = oracle;
    abilityLines(text).forEach((line, i) => {
      // (wave 5A) 113.6m / 605.3a: "Exile this card from your hand: Add {R}." (Simian Spirit Guide)
      // (wave 24C) 702.57a: "Forecast — {1}{U}, Reveal this card from your hand: …" (the server checks the upkeep and once each turn)
      if (/^(?:(?:basic )?[a-z]+)?cycling \{/i.test(line) || /^suspend \d+\s*[—-]/i.test(line) || /^forecast\s*—/i.test(line)
        || /^Exile this card from your hand: Add /.test(line)
        // (review 24C) 113.6m: any other ability that works from the hand ("{B}, Reveal this card from your hand: …", channel) when the server lists it
        || !!hints.activatable?.some((a) => a.card_id === card.id && a.ability === i)) {
        items.push({ label: line.replace(/\s*\(.*$/, ""), onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
      }
    });
  }
  if (mine && zone === "battlefield") {
    const text = data?.faces?.[card.face ?? 0]?.oracle_text ?? data?.oracle_text ?? "";
    const lines = abilityLines(text);
    const abilities = lines
      .map((line, i) => ({ line, i }))
      .filter(({ line }) => /^[^.]*:\s/.test(line) && !/^(Enchant|Equip \{|Cycling)/.test(line) || /: Add /.test(line)
        || /^Crew \d+$/.test(line) || /^Equip (\{[^}]+\})+$/.test(line));
    for (const { line, i } of abilities) {
      // Equip (702.6a) is checked by the server (sorcery speed, a creature you control): offered with priority.
      const ready = hints.activatable?.some((a) => a.card_id === card.id && a.ability === i) || /: Add /.test(line)
        || (/^Equip \{/.test(line) && !!hints.has_priority);
      items.push({ label: `Activate: ${line.length > 60 ? line.slice(0, 57) + "…" : line}`, disabled: !ready,
        onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
    }
    for (const g of rules.stats?.[card.id]?.abilities ?? []) {
      if (g.kind !== "activated" && g.kind !== "mana") continue;
      const ready = g.kind === "mana" || hints.activatable?.some((a) => a.card_id === card.id && a.ability === g.index);
      items.push({ label: `Activate (granted): ${g.text.length > 50 ? g.text.slice(0, 47) + "…" : g.text}`, disabled: !ready,
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
