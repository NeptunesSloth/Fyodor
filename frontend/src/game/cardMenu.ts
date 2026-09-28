/** Context-menu contents for a card, depending on the zone it is in. */
import type { MenuItem } from "../components/ContextMenu";
import { askNumber, askText } from "../components/Prompt";
import { useGame } from "../state/gameStore";
import { useCardCache } from "../state/cardCache";
import { FACE_DOWN_LABEL, isVisible, splitZone, type FaceDownKind, type GameCard, type GameView, type ZoneName } from "../types/game";
import { addCounter, COMMON_COUNTERS, moveCards, send, tapCards, targetsFor } from "./actions";

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
  const items: MenuItem[] = [];
  const opponents = view.seat_order.filter((p) => p !== me);
  const players = view.players;

  if (zone === "battlefield") {
    items.push({ label: card.tapped ? "Untap" : "Tap", hint: "T / double-click", onClick: () => void tapCards(ids) });
    items.push({
      label: "Add counter",
      submenu: [
        ...COMMON_COUNTERS.map((k) => ({ label: k, onClick: () => void addCounter(ids, k, 1) })),
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
    items.push("separator");
    items.push({
      label: "Attack",
      submenu: [
        ...opponents.map((p) => ({ label: players.find((x) => x.id === p)?.name ?? p, onClick: () => void send({ type: "attack", card_ids: ids, target: { kind: "player", id: p } }) })),
        ...attackableCards(view, me).map((c) => ({ label: `${c.name}`, onClick: () => void send({ type: "attack", card_ids: ids, target: { kind: "card", id: c.id } }) })),
        ...(card.attacking ? ["separator" as const, { label: "Stop attacking", onClick: () => void send({ type: "attack", card_ids: ids, target: null }) }] : []),
      ],
    });
    const attackers = Object.values(view.cards).filter((c) => c.attacking && c.controller !== card.controller);
    if (!multi && (attackers.length || card.blocking)) {
      items.push({
        label: "Block",
        submenu: [
          ...attackers.map((a) => ({ label: isVisible(a) ? a.name : "Face-down creature", onClick: () => void send({ type: "block", card_id: card.id, attacker_id: a.id }) })),
          ...(card.blocking ? ["separator" as const, { label: "Stop blocking", onClick: () => void send({ type: "block", card_id: card.id, attacker_id: null }) }] : []),
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
  if (visible && (card.is_token || card.ability)) {
    items.push({ label: card.ability ? "Remove ability" : "Remove token", danger: true, onClick: () => void send({ type: "delete_card", card_ids: ids }) });
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
