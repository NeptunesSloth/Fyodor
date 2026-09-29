/** Menus for manual table tracking: effects, damage, choices, stack notes, exile groups, arrows. */
import type { MenuItem } from "../components/ContextMenu";
import { askNumber, askText } from "../components/Prompt";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { send } from "./actions";

export const EFFECT_PRESETS: { name: string; value?: string; color?: string }[] = [
  { name: "+1/+1", value: "+1/+1" },
  { name: "+2/+2", value: "+2/+2" },
  { name: "+3/+3", value: "+3/+3" },
  { name: "-1/-1", value: "-1/-1" },
  { name: "-2/-0", value: "-2/-0" },
  { name: "Flying", color: "#8fb3d9" },
  { name: "Trample", color: "#8fbf7f" },
  { name: "Deathtouch", color: "#9d8bb5" },
  { name: "Lifelink", color: "#e0d7b5" },
  { name: "Double strike", color: "#d98c6a" },
  { name: "First strike", color: "#d9a86a" },
  { name: "Haste", color: "#d97a6a" },
  { name: "Vigilance", color: "#e0d7b5" },
  { name: "Hexproof", color: "#7fb3bf" },
  { name: "Indestructible", color: "#bfb38f" },
  { name: "Can't block", color: "#999" },
  { name: "Can't attack", color: "#999" },
  { name: "Must attack", color: "#c97" },
];
const PROTECTION = ["white", "blue", "black", "red", "green", "everything"];

export const CHOICE_KEYS = [
  "Chosen color",
  "Chosen creature type",
  "Named card",
  "Chosen player",
  "Chosen number",
  "Chosen mode",
  "Chosen value",
];

export const CAST_TAGS = [
  "Kicked",
  "Overloaded",
  "Escaped",
  "Flashed back",
  "Foretold",
  "Cast from exile",
  "Cast from command zone",
  "Alternate cost",
  "Buyback",
  "Copy",
];

export const EXILE_GROUPS = ["Foretell", "Adventure", "Plot", "Suspend", "Impulse (play this turn)"];

export function effectsMenu(ids: string[], card: GameCard): MenuItem {
  const add = (name: string, value?: string, color?: string, text?: string) =>
    void send({ type: "add_effect", card_ids: ids, name, ...(value ? { value } : {}), ...(color ? { color } : {}), ...(text ? { text } : {}) });
  const existing = card.effects ?? [];
  return {
    label: "Effects",
    submenu: [
      ...EFFECT_PRESETS.map((e) => ({ label: e.name, onClick: () => add(e.name, e.value, e.color) })),
      { label: "Protection from…", submenu: PROTECTION.map((c) => ({ label: c, onClick: () => add(`Protection from ${c}`, undefined, "#c9b27a") })) },
      {
        label: "Custom effect…",
        onClick: async () => {
          const name = await askText("Effect name (e.g. “Can't be countered”, “+X/+0”)", "");
          if (!name) return;
          const value = await askText("Value (optional, e.g. +2/+0 or 3)", "");
          add(name.slice(0, 60), value ? value.slice(0, 20) : undefined);
        },
      },
      ...(existing.length
        ? [
            "separator" as const,
            ...existing.map((e) => ({ label: `Remove ${e.name}${e.value && e.value !== e.name ? ` ${e.value}` : ""}`, onClick: () => void send({ type: "remove_effect", card_ids: [card.id], effect_id: e.id }) })),
          ]
        : []),
      "separator",
      { label: "Clear effects", onClick: () => void send({ type: "cleanup", what: ["effects"], card_ids: ids }) },
    ],
  };
}

export function damageMenu(ids: string[], card: GameCard): MenuItem {
  return {
    label: card.damage ? `Damage (${card.damage})` : "Damage",
    submenu: [
      { label: "+1", onClick: () => void send({ type: "set_damage", card_ids: ids, delta: 1 }) },
      { label: "−1", onClick: () => void send({ type: "set_damage", card_ids: ids, delta: -1 }) },
      {
        label: "Set damage…",
        onClick: async () => {
          const n = await askNumber("Damage marked", card.damage ?? 0, { min: 0 });
          if (n !== null) void send({ type: "set_damage", card_ids: ids, value: n });
        },
      },
      { label: "Clear", onClick: () => void send({ type: "set_damage", card_ids: ids, value: 0 }) },
    ],
  };
}

export function choicesMenu(card: GameCard, view: GameView): MenuItem | null {
  if (!isVisible(card)) return null;
  const set = async (key: string) => {
    let value: string | null;
    if (key === "Chosen player") {
      const names = view.players.map((p) => p.name).join(", ");
      value = await askText(`Chosen player (${names})`, card.choices?.[key] ?? "");
    } else if (key === "Chosen number") {
      const n = await askNumber("Chosen number", Number(card.choices?.[key] ?? 0));
      value = n === null ? null : String(n);
    } else value = await askText(key, card.choices?.[key] ?? "");
    if (value !== null) void send({ type: "set_choice", card_id: card.id, key, value: value || null });
  };
  const current = Object.entries(card.choices ?? {});
  return {
    label: "Choices",
    submenu: [
      ...CHOICE_KEYS.map((k) => ({ label: card.choices?.[k] ? `${k}: ${card.choices[k]}` : `${k}…`, onClick: () => void set(k) })),
      {
        label: "Custom choice…",
        onClick: async () => {
          const key = await askText("What was chosen? (label)", "");
          if (key) await set(key.slice(0, 60));
        },
      },
      ...(current.length
        ? ["separator" as const, ...current.map(([k]) => ({ label: `Clear ${k}`, onClick: () => void send({ type: "set_choice", card_id: card.id, key: k, value: null }) }))]
        : []),
    ],
  };
}

/** Modes listed on the card ("• Destroy target artifact." …), for the mode picker. */
export function cardModes(card: GameCard): string[] {
  if (!isVisible(card) || !card.card_id) return [];
  const data = useCardCache.getState().cards[card.card_id];
  const text = data?.oracle_text ?? "";
  return text.split("\n").filter((l) => /^[••]/.test(l.trim())).map((l) => l.replace(/^[••]\s*/, "").trim());
}

export function stackMenu(card: GameCard): MenuItem {
  const info = card.stack_info ?? { x: null, modes: [], tags: [] };
  const modes = cardModes(card);
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  return {
    label: "Spell details",
    submenu: [
      {
        label: info.x != null ? `X = ${info.x}` : "Set X…",
        onClick: async () => {
          const n = await askNumber("X =", info.x ?? 0, { min: 0 });
          if (n !== null) void send({ type: "set_stack_info", card_id: card.id, x: n });
        },
      },
      ...(info.x != null ? [{ label: "Clear X", onClick: () => void send({ type: "set_stack_info", card_id: card.id, clear_x: true }) }] : []),
      {
        label: "Modes",
        submenu: [
          ...modes.map((m) => ({ label: `${info.modes.includes(m) ? "✓" : "□"} ${m}`, onClick: () => void send({ type: "set_stack_info", card_id: card.id, modes: toggle(info.modes, m) }) })),
          ...info.modes.filter((m) => !modes.includes(m)).map((m) => ({ label: `✓ ${m}`, onClick: () => void send({ type: "set_stack_info", card_id: card.id, modes: toggle(info.modes, m) }) })),
          {
            label: "Other mode…",
            onClick: async () => {
              const m = await askText("Mode chosen", "");
              if (m) void send({ type: "set_stack_info", card_id: card.id, modes: [...info.modes, m.slice(0, 120)] });
            },
          },
        ],
      },
      {
        label: "Cast labels",
        submenu: CAST_TAGS.map((t) => ({ label: `${info.tags.includes(t) ? "✓" : "□"} ${t}`, onClick: () => void send({ type: "set_stack_info", card_id: card.id, tags: toggle(info.tags, t) }) })),
      },
    ],
  };
}

export function exileGroupMenu(ids: string[], card: GameCard, view: GameView): MenuItem {
  const onTable = Object.values(view.cards).filter((c) => isVisible(c) && c.zone.endsWith(":battlefield") && !c.is_token).slice(0, 20);
  return {
    label: card.exile_group ? `Exile group: ${card.exile_group}` : "Exile group",
    submenu: [
      ...EXILE_GROUPS.map((g) => ({ label: g, onClick: () => void send({ type: "set_exile_group", card_ids: ids, group: g }) })),
      ...(onTable.length
        ? [{ label: "Exiled with…", submenu: onTable.map((c) => ({ label: isVisible(c) ? c.name : "?", onClick: () => void send({ type: "set_exile_group", card_ids: ids, group: isVisible(c) ? c.name : "?" }) })) }]
        : []),
      {
        label: "Custom…",
        onClick: async () => {
          const g = await askText("Exile group name", card.exile_group ?? "");
          if (g !== null) void send({ type: "set_exile_group", card_ids: ids, group: g || null });
        },
      },
      ...(card.exile_group ? [{ label: "General exile", onClick: () => void send({ type: "set_exile_group", card_ids: ids, group: null }) }] : []),
    ],
  };
}

/** Start pick mode: click cards (and players) to choose targets, then Done. */
export function startArrow(source: string, kind: "target" | "attack" | "block" | "custom" = "target") {
  useGame.getState().setPick({
    prompt: kind === "custom" ? "Point to…" : "Choose targets",
    multi: true,
    picked: [],
    players: true,
    onDone: (ids) => {
      if (ids.length) void send({ type: "create_arrow", source, targets: ids, kind });
    },
  });
}

export function startCopyTarget(cardId: string) {
  useGame.getState().setPick({
    prompt: "Choose what this copy is copying",
    multi: false,
    picked: [],
    players: false,
    onDone: (ids) => {
      if (ids[0]) void send({ type: "set_copy_source", card_id: cardId, source_id: ids[0] });
    },
  });
}
