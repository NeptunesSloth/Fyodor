/** Card-menu entries when automation is on: play / cast / activate, per-card automation, mana sources. */
import type { MenuItem } from "../../components/ContextMenu";
import { useCardCache } from "../../state/cardCache";
import { isVisible, splitZone, type GameCard, type GameView } from "../../types/game";
import { abilityLines, automationOn, isLand, send, setPrefs } from "./intents";

/** 702.33a / 702.33c: a "Kicker {cost}" or "Multikicker {cost}" keyword line (mana costs only, as the server pays them). */
const KICKER = /^(?:multi)?kicker (?:\{[^}]+\})+$/i;
/** Multikicker: how many times to pay (a submenu; more is rare enough to do by hand). */
export const MULTIKICKER_COUNTS = [1, 2, 3, 4, 5, 6];

export function rulesMenu(card: GameCard, view: GameView, me: string): MenuItem[] {
  const rules = view.rules;
  if (!rules || !automationOn(view) || !isVisible(card)) return [];
  const { zone, player } = splitZone(card.zone);
  const items: MenuItem[] = [];
  const hints = rules.hints;
  const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
  const mine = card.controller === me
    || (player === me && (zone === "hand" || zone === "command" || zone === "graveyard" || zone === "exile" || zone === "library"));
  const oracle = data?.faces?.[card.face ?? 0]?.oracle_text ?? data?.oracle_text ?? "";
  // Other zones (your graveyard, exile, the top of your library): only when the server says a
  // permission lets you (flashback, "you may play that card this turn", "… from the top of your library").
  const elsewhere = zone === "graveyard" || zone === "exile" || zone === "library";
  if (mine && zone === "hand" && isLand(card.id, view)) {
    items.push({ label: "Play land", disabled: !hints.playable_lands?.includes(card.id), onClick: () => void send({ type: "play_land", card_id: card.id }) });
  } else if (mine && elsewhere && isLand(card.id, view) && hints.playable_lands?.includes(card.id)) {
    items.push({ label: `Play land from ${zone}`, onClick: () => void send({ type: "play_land", card_id: card.id }) });
  } else if (mine && (zone === "hand" || zone === "command")) {
    items.push({ label: "Cast", disabled: !hints.castable?.includes(card.id), onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
  } else if (mine && elsewhere && hints.castable?.includes(card.id)) {
    const flashback = zone === "graveyard" && abilityLines(oracle).some((l) => /^flashback \{/i.test(l));
    items.push({ label: flashback ? "Cast with flashback" : `Cast from ${zone}`, onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
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
  const buyback = abilityLines(oracle).find((l) => /^buyback \{/i.test(l));
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
  if (mine && zone === "battlefield" && card.face_down && morph) {
    items.push({ label: `Turn face up (${morph})`, onClick: () => void send({ type: "turn_face_up", card_id: card.id }) });
  }
  if (mine && zone === "hand") {
    const text = oracle;
    abilityLines(text).forEach((line, i) => {
      if (/^(?:(?:basic )?[a-z]+)?cycling \{/i.test(line) || /^suspend \d+\s*[—-]/i.test(line)) {
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
