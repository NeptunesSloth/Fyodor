import { tapGesture } from "./rules/intents";
/** Context-menu contents for a card, depending on the zone it is in. */
import { macrosFor } from "../state/macros";
import { usePrefs } from "../state/prefs";
import type { MenuItem } from "../components/ContextMenu";
import { askNumber, askText } from "../components/Prompt";
import { useGame } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { FACE_DOWN_LABEL, isVisible, splitZone, type FaceDownKind, type GameCard, type GameView, type ZoneName } from "../types/game";
import { addCounter, COMMON_COUNTERS, moveCards, send, tapCards, targetsFor } from "./actions";
import { choicesMenu, damageMenu, effectsMenu, exileGroupMenu, stackMenu, startArrow, startCopyTarget } from "./marksMenu";
import { rulesMenu } from "./rules/rulesMenu";

function moveMenu(ids: string[], current: ZoneName, owner: string | null, me: string): MenuItem[] {
  const items: MenuItem[] = [];
  const add = (label: string, zone: ZoneName, opts: Parameters<typeof moveCards>[2] = {}, hint?: string) => {
    if (zone === current && !opts.position) return;
    items.push({ label, hint, onClick: () => void moveCards(ids, zone, opts) });
  };
  add("Battlefield", "battlefield", { player: me });
  add("Hand", "hand", { player: owner });
  add("Graveyard", "graveyard", { player: owner });
  add("Exile", "exile", { player: owner });
  add("Library — top", "library", { player: owner, position: "top" });
  add("Library — bottom", "library", { player: owner, position: "bottom" });
  items.push({
    label: "Library — position…",
    onClick: async () => {
      const n = await askNumber("Put at position from the top (1 = top)", 1, { min: 1 });
      if (n) void moveCards(ids, "library", { player: owner, index: n - 1 });
    },
  });
  add("Command zone", "command", { player: owner });
  add("Stack", "stack");
  add("Exile face down", "exile", { player: owner, face_down: true });
  add("Sideboard", "sideboard", { player: owner });
  return items;
}

export function cardMenu(card: GameCard, view: GameView, me: string): { title: string; items: MenuItem[] } {
  const ids = targetsFor(card.id);
  const { zone, player: zoneOwner } = splitZone(card.zone);
  const visible = isVisible(card);
  const cardData = visible && card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
  const multi = ids.length > 1;
  const title = multi ? `${ids.length} cards` : visible ? card.name : "Hidden card";
  const items: MenuItem[] = multi ? [] : rulesMenu(card, view, me);
  const opponents = view.seat_order.filter((p) => p !== me);
  const players = view.players;

  if (zone === "battlefield") {
    items.push({ label: card.tapped ? "Untap" : "Tap", hint: "T / double-click", onClick: () => tapGesture(ids, (x) => void tapCards(x)) });
    items.push({
      label: "Add counter",
      submenu: [
        ...[...new Set([...usePrefs.getState().favoriteCounters, ...COMMON_COUNTERS])].map((k) => ({ label: k, onClick: () => void addCounter(ids, k, 1) })),
        "separator" as const,
        {
          label: "Several…",
          onClick: async () => {
            const kind = await askText("Counter type", "+1/+1");
            if (!kind) return;
            const n = await askNumber(`How many ${kind} counters?`, 1, { min: 1 });
            if (n) void addCounter(ids, kind, n);
          },
        },
        {
          label: "Custom type…",
          onClick: async () => {
            const kind = await askText("Counter type", "");
            if (kind) void addCounter(ids, kind, 1);
          },
        },
      ],
    });
    const counters = Object.keys(card.counters ?? {});
    if (counters.length) {
      items.push({
        label: "Remove counter",
        submenu: counters.map((k) => ({ label: `${k} (${card.counters![k]})`, onClick: () => void addCounter(ids, k, -1) })),
      });
      if (!multi) {
        items.push({
          label: "Change counter type",
          submenu: counters.map((k) => ({
            label: k,
            onClick: async () => {
              const kind = await askText(`Change ${k} counters to`, k);
              if (kind && kind !== k) void send({ type: "set_counter", card_id: card.id, kind, value: card.counters![k]!, rename_from: k });
            },
          })),
        });
      }
    }
    items.push(effectsMenu(ids, card));
    items.push(damageMenu(ids, card));
    items.push("separator");
    items.push({
      label: "Attack",
      submenu: [
        ...opponents.map((p) => ({ label: players.find((x) => x.id === p)?.name ?? p, onClick: () => void send({ type: "attack", card_ids: ids, target: { kind: "player", id: p } }) })),
        ...attackableCards(view, me).map((c) => ({ label: `${c.name}`, onClick: () => void send({ type: "attack", card_ids: ids, target: { kind: "card", id: c.id } }) })),
        ...(card.attacking || card.attacking_without_target ? ["separator" as const, { label: "Stop attacking", onClick: () => void send({ type: "attack", card_ids: ids, target: null }) }] : []),
      ],
    });
    const attackers = Object.values(view.cards).filter((c) => (c.attacking || c.attacking_without_target) && c.controller !== card.controller);
    if (!multi && (attackers.length || card.blocking || card.blocking_without_attacker)) {
      items.push({
        label: "Block",
        submenu: [
          ...attackers.map((a) => ({ label: isVisible(a) ? a.name : "Face-down creature", onClick: () => void send({ type: "block", card_id: card.id, attacker_id: a.id }) })),
          ...((card.blocking || card.blocking_without_attacker) ? ["separator" as const, { label: "Stop blocking", onClick: () => void send({ type: "block", card_id: card.id, attacker_id: null }) }] : []),
        ],
      });
    }
    items.push("separator");
  }

  if (zone === "hand" || (zone === "library" && visible) || zone === "sideboard") {
    items.push({ label: "Play", hint: "double-click", onClick: () => void moveCards(ids, "battlefield", { player: me }) });
    items.push({ label: "Cast (to stack)", onClick: () => void moveCards(ids, "stack") });
    items.push({
      label: "Play face down",
      submenu: (["generic", "morph", "disguise", "manifest", "cloak"] as FaceDownKind[]).map((kind) => ({
        label: FACE_DOWN_LABEL[kind],
        onClick: () => void moveCards(ids, "battlefield", { player: me, face_down: true, face_down_kind: kind }),
      })),
    });
    if (zone === "hand") items.push({ label: "Discard", onClick: () => void moveCards(ids, "graveyard", { player: zoneOwner }) });
    items.push("separator");
  }

  if (zone === "stack" && !multi) {
    const top = view.stack[view.stack.length - 1] === card.id;
    if (top) items.push({ label: "Resolve", onClick: () => void send({ type: "resolve_top" }) });
    items.push(stackMenu(card));
    if (visible && !card.ability) items.push({ label: "Counter (to graveyard)", onClick: () => void moveCards([card.id], "graveyard", { player: card.owner }) });
    items.push("separator");
  }

  if (visible && !multi && cardData && (cardData.double_faced || cardData.faces.length > 1)) {
    items.push({ label: cardData.double_faced ? "Transform / turn over" : "Show other half", hint: "F", onClick: () => void send({ type: "set_face", card_id: card.id }) });
  }
  if (zone === "battlefield" && !multi) items.push({ label: "Flip 180°", onClick: () => void send({ type: "flip", card_id: card.id }) });
  if (["battlefield", "exile", "stack", "foretell"].includes(zone)) {
    if (card.face_down) items.push({ label: "Turn face up", onClick: () => void send({ type: "face_down", card_ids: ids, face_down: false }) });
    else if (zone === "battlefield")
      items.push({
        label: "Turn face down",
        submenu: (["generic", "morph", "disguise", "manifest", "cloak"] as FaceDownKind[]).map((kind) => ({
          label: FACE_DOWN_LABEL[kind],
          onClick: () => void send({ type: "face_down", card_ids: ids, face_down: true, kind }),
        })),
      });
    else items.push({ label: "Turn face down", onClick: () => void send({ type: "face_down", card_ids: ids, face_down: true }) });
  }
  if ((zone === "battlefield" || zone === "stack") && visible && !multi) {
    items.push({
      label: "Create copy",
      submenu: [
        { label: "Copy", onClick: () => void send({ type: "copy_card", card_id: card.id, player: me }) },
        // the scripted tables' exact copy (a plain copy starts without them, as the rules say)
        { label: "Exact copy", hint: "keeps counters and markers", onClick: () => void send({ type: "copy_card", card_id: card.id, player: me, exact: true }) },
        {
          label: "Copy with changes…",
          onClick: async () => {
            const mods = await askText("Copy modifications (e.g. “not legendary”, “1/1”)", "");
            if (mods !== null) void send({ type: "copy_card", card_id: card.id, player: me, modifications: mods });
          },
        },
        {
          label: "Several copies…",
          onClick: async () => {
            const n = await askNumber("How many copies?", 2, { min: 1, max: 50 });
            if (n) void send({ type: "copy_card", card_id: card.id, player: me, count: n });
          },
        },
      ],
    });
    items.push({ label: "Put ability on stack…", onClick: () => useGame.getState().openDialog("ability", card.id) });
  }
  if (zone === "battlefield" && visible) {
    // the encoder's power/toughness box: a P/T marker on the card, for manual play (remove it from Effects)
    items.push({
      label: "Set power/toughness…",
      onClick: async () => {
        const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
        const pt = await askText("Power/toughness to show on the card", data?.power != null ? `${data.power}/${data.toughness}` : "2/2", { label: "e.g. 4/4" });
        const m = pt ? /^\s*(-?\d+|\*)\s*\/\s*(-?\d+|\*)\s*$/.exec(pt) : null;
        if (m) void send({ type: "add_effect", card_ids: ids, name: "P/T", value: `${m[1]}/${m[2]}`, color: "#f4ead6" });
      },
    });
  }

  if (zone === "hand" || zone === "library" || zone === "sideboard" || zone === "foretell") {
    items.push({
      label: "Reveal",
      submenu: [
        { label: "To everyone", onClick: () => void send({ type: "reveal", card_ids: ids }) },
        ...opponents.map((p) => ({ label: `To ${players.find((x) => x.id === p)?.name ?? p}`, onClick: () => void send({ type: "reveal", card_ids: ids, to: [p] }) })),
      ],
    });
    if (visible && card.revealed) items.push({ label: "Stop revealing", onClick: () => void send({ type: "hide", card_ids: ids }) });
  }

  if (!multi && (zone === "battlefield" || zone === "stack")) {
    items.push({ label: "Target / point to…", hint: "arrow", onClick: () => startArrow(card.id) });
    const mine = (view.arrows ?? []).filter((a) => a.source === card.id || a.targets.includes(card.id));
    if (mine.length) items.push({ label: `Remove arrows (${mine.length})`, onClick: () => mine.forEach((a) => void send({ type: "remove_arrow", arrow_id: a.id })) });
  }
  if (!multi && (zone === "battlefield" || zone === "stack")) {
    const choices = choicesMenu(card, view);
    if (choices) items.push(choices);
  }
  if (zone === "exile" || zone === "foretell") items.push(exileGroupMenu(ids, card, view));
  if (zone === "battlefield") {
    items.push({
      label: "Arrange",
      submenu: [
        { label: "Rotate 90° →", onClick: () => void send({ type: "rotate", card_ids: ids, delta: 90 }) },
        { label: "Rotate 90° ←", onClick: () => void send({ type: "rotate", card_ids: ids, delta: -90 }) },
        { label: "Reset rotation", onClick: () => void send({ type: "rotate", card_ids: ids, degrees: 0 }) },
        "separator",
        ...(multi ? [{ label: "Group (move together)", onClick: () => void send({ type: "group", card_ids: ids }) }] : []),
        { label: "Ungroup", onClick: () => void send({ type: "ungroup", card_ids: ids }) },
        { label: card.locked ? "Unlock" : "Lock in place", onClick: () => void send({ type: "set_lock", card_ids: ids, value: !card.locked }) },
        {
          label: "Attach to…",
          onClick: () =>
            useGame.getState().setPick({
              prompt: "Choose the permanent to attach to",
              multi: false,
              picked: [],
              players: false,
              onDone: (to) => to[0] && void send({ type: "attach", card_ids: ids, to: to[0] }),
            }),
        },
        { label: "Detach", onClick: () => void send({ type: "detach", card_ids: ids }) },
      ],
    });
  }
  if (zone === "battlefield" || zone === "stack") {
    const macros = macrosFor(cardData?.oracle_id);
    const selected = useGame.getState().selection.filter((id) => id !== card.id);
    items.push({
      label: "Custom actions",
      submenu: [
        ...macros.map((m) => ({
          label: m.name,
          hint: m.scope === "card" ? "this card" : "library",
          onClick: () => void send({ type: "run_macro", macro: m.definition, card_id: card.id, selected }),
        })),
        ...(macros.length ? ["separator" as const] : []),
        { label: "New custom action…", onClick: () => useGame.getState().openDialog("macro", card.id) },
      ],
    });
  }
  if (!multi && visible && card.copy_of) items.push({ label: `Change copy target (copying ${card.copy_of.source_name})…`, onClick: () => startCopyTarget(card.id) });
  if (!multi && visible && zone === "battlefield" && !card.is_token) {
    items.push({ label: "Create tokens from this…", hint: "remembers the source", onClick: () => useGame.getState().openDialog("tokens", card.id) });
  }

  items.push({ label: "Move to", submenu: moveMenu(ids, zone, zoneOwner ?? card.owner, me) });

  if (zone === "battlefield") {
    items.push({
      label: "Give control to",
      submenu: players.filter((p) => p.id !== card.controller).map((p) => ({ label: p.name, onClick: () => void send({ type: "set_controller", card_ids: ids, player: p.id }) })),
    });
  }
  if (card.controller !== card.owner || (zoneOwner && zoneOwner !== card.owner && zone !== "stack")) {
    items.push({ label: "Return to owner", hint: players.find((p) => p.id === card.owner)?.name, onClick: () => void send({ type: "return_to_owner", card_ids: ids }) });
  }
  if (visible && card.commander_key && zone !== "command" && zone !== "stack") {
    items.push({ label: "Return to command zone", onClick: () => void moveCards(ids, "command", { player: card.owner }) });
  }

  if (visible && !multi) {
    items.push("separator");
    items.push({
      label: card.note ? "Edit note…" : "Add note…",
      onClick: async () => {
        const text = await askText(`Note on ${card.name}`, card.note, { multiline: true });
        if (text !== null) void send({ type: "note", card_id: card.id, text });
      },
    });
    if (!card.is_token && !card.ability) {
      items.push(
        card.commander_key
          ? { label: "Unmark as commander", onClick: () => void send({ type: "set_commander", card_id: card.id, value: false }) }
          : { label: "Mark as commander", onClick: () => void send({ type: "set_commander", card_id: card.id, value: true }) },
      );
    }
    items.push({ label: "View card", hint: "hover", onClick: () => useGame.getState().setInspect(card.id) });
  }
  if (multi) {
    const objs = ids.map((id) => view.cards[id]).filter((c): c is GameCard => !!c);
    const disposable = objs.filter((c) => isVisible(c) && (c.is_token || !!c.copy_of || !!c.ability));
    if (disposable.length) {
      items.push({
        label: `Delete all tokens & copies (${disposable.length})`,
        danger: true,
        onClick: () => {
          const real = objs.length - disposable.length;
          if (real && !window.confirm(`Delete ${disposable.length} tokens/copies? The ${real} real card${real > 1 ? "s" : ""} in the selection stay on the table.`)) return;
          void send({ type: "delete_card", card_ids: disposable.map((c) => c.id) });
        },
      });
    }
  } else if (visible && (card.is_token || card.ability || card.copy_of)) {
    items.push({ label: card.ability ? "Remove ability" : card.copy_of && !card.is_token ? "Remove copy" : "Remove token", danger: true, onClick: () => void send({ type: "delete_card", card_ids: ids }) });
  }
  return { title, items };
}

function attackableCards(view: GameView, me: string) {
  const out: { id: string; name: string }[] = [];
  for (const c of Object.values(view.cards)) {
    if (!isVisible(c) || c.controller === me || !c.zone.endsWith(":battlefield")) continue;
    const type = c.card_id ? useCardCache.getState().cards[c.card_id]?.type_line ?? "" : c.token?.type_line ?? "";
    if (/Planeswalker|Battle/.test(type)) out.push({ id: c.id, name: c.name });
  }
  return out;
}
