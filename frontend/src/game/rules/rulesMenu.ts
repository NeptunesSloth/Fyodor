/** Card-menu entries when automation is on: play / cast / activate, per-card automation, mana sources. */
import type { MenuItem } from "../../components/ContextMenu";
import { useCardCache } from "../../state/cardCache";
import { isVisible, splitZone, type GameCard, type GameView } from "../../types/game";
import { abilityLines, automationOn, isLand, send, setPrefs } from "./intents";

export function rulesMenu(card: GameCard, view: GameView, me: string): MenuItem[] {
  const rules = view.rules;
  if (!rules || !automationOn(view) || !isVisible(card)) return [];
  const { zone, player } = splitZone(card.zone);
  const items: MenuItem[] = [];
  const hints = rules.hints;
  const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
  const mine = card.controller === me || (player === me && (zone === "hand" || zone === "command" || zone === "graveyard"));
  if (mine && zone === "hand" && isLand(card.id, view)) {
    items.push({ label: "Play land", disabled: !hints.playable_lands?.includes(card.id), onClick: () => void send({ type: "play_land", card_id: card.id }) });
  } else if (mine && (zone === "hand" || zone === "command")) {
    items.push({ label: "Cast", disabled: !hints.castable?.includes(card.id), onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
  } else if (mine && zone === "graveyard" && hints.castable?.includes(card.id)) {
    items.push({ label: "Cast with flashback", onClick: () => void send({ type: "cast_spell", card_id: card.id }) });
  }
  const oracle = data?.faces?.[card.face ?? 0]?.oracle_text ?? data?.oracle_text ?? "";
  const morph = abilityLines(oracle).find((l) => /^(mega)?morph \{/i.test(l));
  const dash = abilityLines(oracle).find((l) => /^dash \{/i.test(l));
  if (mine && zone === "hand" && dash) {
    items.push({ label: `Cast with ${dash}`, onClick: () => void send({ type: "cast_spell", card_id: card.id, dash: true }) });
  }
  if (mine && zone === "graveyard") {
    abilityLines(oracle).forEach((line, i) => {
      if (/^unearth \{/i.test(line)) items.push({ label: line, onClick: () => void send({ type: "activate_ability", card_id: card.id, ability: i }) });
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
      .filter(({ line }) => /^[^.]*:\s/.test(line) && !/^(Enchant|Equip \{|Cycling)/.test(line) || /: Add /.test(line) || /^Crew \d+$/.test(line));
    for (const { line, i } of abilities) {
      const ready = hints.activatable?.some((a) => a.card_id === card.id && a.ability === i) || /: Add /.test(line);
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
