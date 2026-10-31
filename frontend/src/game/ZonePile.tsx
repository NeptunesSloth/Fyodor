import { sleeveStyle, useSleeve } from "./appearance";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { askNumber, askText } from "../components/Prompt";
import { useCardView, useGame, useLibrary, useZoneIds } from "../state/gameStore";
import { splitZone, type ZoneName } from "../types/game";
import { draw, moveCards, send } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag, useDrag, type DropResult } from "./dnd";
import { dropAsIntent, send as sendIntent, useXPrompt } from "./rules/intents";
import { GameCardFace } from "./GameCardFace";

const LABEL: Partial<Record<ZoneName, string>> = {
  library: "Library",
  graveyard: "Graveyard",
  exile: "Exile",
  command: "Command",
  sideboard: "Sideboard",
  companion: "Companion",
  foretell: "Foretold",
  phased: "Phased out",
};

function dropInto(ids: string[], target: DropResult | null) {
  if (!target) return;
  if (dropAsIntent(ids, target)) return; // automation on: casting a commander from the command zone
  const { zone, player } = splitZone(target.zone);
  void moveCards(ids, zone, { player, position: target.position, index: target.index, x: target.x, y: target.y });
}

/** Rules actions on the top card of a library: a permission to play or cast it (yours, or another player's with Xanathar), a free cast
 * (Temporal Aperture), plot (Fblthp, 116.2k). Only a top card this viewer can see is in the view, and the server lists it in the viewer's own hints. */
export function libraryTopActions(player: string, me: string): MenuItem[] {
  const view = useGame.getState().view;
  const top = view?.zones[`${player}:library`];
  const topId = top && !Array.isArray(top) ? top.known.find(([i]) => i === 0)?.[1] : undefined;
  const hints = view?.rules && !view.rules.paused ? view.rules.hints : undefined;
  if (!topId || !hints) return [];
  const items: MenuItem[] = [];
  const whose = player === me ? "the top card" : "their top card";
  if (hints.playable_lands?.includes(topId)) {
    items.push({ label: `Play ${whose} as your land`, onClick: () => void sendIntent({ type: "play_land", card_id: topId }) });
  }
  if (hints.castable?.includes(topId)) {
    items.push({ label: `Cast ${whose}`, onClick: () => void sendIntent({ type: "cast_spell", card_id: topId }) });
  }
  if (hints.chorus?.includes(topId)) {
    items.push({ label: `Cast ${whose} with Chorus of the Conclave…`, onClick: () => useXPrompt.setState({ action: { type: "cast_spell", card_id: topId }, field: "chorus" }) });
  }
  if (hints.free_castable?.includes(topId)) {
    items.push({ label: `Cast ${whose} without paying its mana cost`, onClick: () => void sendIntent({ type: "cast_spell", card_id: topId, free: true }) });
  }
  for (const a of hints.activatable?.filter((x) => x.card_id === topId) ?? []) {
    items.push({ label: "Plot the top card (special action)", onClick: () => void sendIntent({ type: "activate_ability", card_id: topId, ability: a.ability }) });
  }
  return items.length ? [...items, "separator"] : [];
}

const REVEAL_TYPES = ["Creature", "Land", "Basic Land", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker"];
const BASICS = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"];

export function libraryMenu(player: string, me: string, name: string): MenuItem[] {
  const mine = player === me;
  const items: MenuItem[] = [];
  items.push(...libraryTopActions(player, me));
  if (mine) {
    items.push({ label: "Draw a card", hint: "D", onClick: () => void draw(player, 1) });
    items.push({
      label: "Draw several…",
      onClick: async () => {
        const n = await askNumber("Draw how many cards?", 7, { min: 1, max: 100 });
        if (n) void draw(player, n);
      },
    });
  }
  items.push({ label: "Shuffle", onClick: () => void send({ type: "shuffle", player }) });
  items.push({ label: mine ? "Search library" : `Search ${name}'s library`, onClick: () => void send({ type: "search_start", zone: { zone: "library", player } }) });
  items.push({
    label: "Look at the top…",
    onClick: async () => {
      const n = await askNumber("Look at how many cards from the top?", 3, { min: 1, max: 100 });
      if (!n) return;
      if (await send({ type: "look_top", player, count: n })) useGame.getState().openBrowser({ zone: `${player}:library`, title: `Top ${n} of ${mine ? "your" : `${name}'s`} library`, limit: n });
    },
  });
  items.push({ label: "Reveal the top card", onClick: () => void send({ type: "reveal_top", player, count: 1 }) });
  // the scripted tables' library chores (the server reads the card types; nobody sees the library)
  const revealUntil = (card_type: string) => void send({ type: "reveal_until", player, card_type });
  items.push({
    label: "Reveal until…",
    submenu: [
      ...REVEAL_TYPES.map((t) => ({ label: `a ${t.toLowerCase()}`, onClick: () => revealUntil(t) })),
      "separator" as const,
      { label: "Another type…", onClick: async () => { const t = await askText("Reveal until a card of which type?", "Elf", { label: "Card type or subtype" }); if (t?.trim()) revealUntil(t.trim()); } },
    ],
  });
  if (mine) {
    items.push({
      label: "Cascade…",
      hint: "manual",
      onClick: async () => {
        const n = await askNumber("Cascade: exile until a nonland card with mana value less than…", 4, { min: 1, max: 30, label: "Mana value less than" });
        if (n) void send({ type: "cascade", player, below: n });
      },
    });
    const fetch = (name: string, to: "hand" | "battlefield") => void send({ type: "fetch_card", player, name, to });
    const named = (to: "hand" | "battlefield") => async () => { const n = await askText("Which card? (by its exact name)", "", { label: "Card name" }); if (n?.trim()) fetch(n.trim(), to); };
    items.push({
      label: "Get a basic land",
      submenu: [
        ...BASICS.map((b) => ({ label: `${b} into your hand`, onClick: () => fetch(b, "hand") })),
        "separator" as const,
        ...BASICS.map((b) => ({ label: `${b} onto the battlefield`, onClick: () => fetch(b, "battlefield") })),
        "separator" as const,
        { label: "Another card by name…", onClick: named("hand") },
      ],
    });
  }
  items.push({
    label: "Put the top card onto the battlefield face down",
    submenu: [
      { label: "Manifest", onClick: () => void send({ type: "put_top_face_down", player, kind: "manifest" }) },
      { label: "Cloak", onClick: () => void send({ type: "put_top_face_down", player, kind: "cloak" }) },
      { label: "Face down", onClick: () => void send({ type: "put_top_face_down", player, kind: "generic" }) },
    ],
  });
  items.push({
    label: "Mill…",
    onClick: async () => {
      const n = await askNumber("Mill how many cards?", 1, { min: 1, max: 500 });
      if (n) void send({ type: "mill", player, count: n });
    },
  });
  items.push({
    label: "Exile from top…",
    onClick: async () => {
      const n = await askNumber("Exile how many cards from the top?", 1, { min: 1, max: 500 });
      if (n) void send({ type: "mill", player, count: n, to: "exile" });
    },
  });
  if (mine) {
    items.push("separator");
    items.push({ label: "Mulligan (shuffle hand in, draw 7)", onClick: () => void send({ type: "mulligan", player }) });
  }
  return items;
}

/** Library: a face-down pile with its count. Known top cards are shown face up. */
export function LibraryPile({ player, me, name }: { player: string; me: string; name: string }) {
  const key = `${player}:library`;
  const lib = useLibrary(key);
  const topKnown = lib?.known.find(([i]) => i === 0)?.[1];
  const top = useCardView(topKnown ?? "");
  const sleeve = useSleeve(player);
  const over = useDrag((s) => s.drag?.overZone === key);
  const searching = useGame((s) => s.view?.searches);
  const beingSearched = searching ? Object.entries(searching).filter(([, z]) => z === key).map(([p]) => p) : [];
  const count = lib?.count ?? 0;
  return (
    <div
      className={`pile library ${over ? "drop-over" : ""}`}
      data-drop={key}
      data-library=""
      title="Click for library actions · double-click to draw"
      onClick={(e) => openMenu(e, libraryMenu(player, me, name), `${player === me ? "Your" : `${name}'s`} library (${count})`)}
      onDoubleClick={(e) => {
        e.stopPropagation();
        if (player === me) void draw(player, 1);
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        openMenu(e, libraryMenu(player, me, name), `${player === me ? "Your" : `${name}'s`} library (${count})`);
      }}
    >
      <div className="pile-card">{top && !top.hidden ? <GameCardFace card={top} /> : count ? <div className={`card-face card-back ${sleeve ? "sleeved" : ""}`} style={sleeveStyle(sleeve)} /> : <div className="pile-empty" />}</div>
      {top && !top.hidden && (
        <span className={`pile-known ${top.revealed ? "revealed" : ""}`} title={top.revealed ? "Revealed to everyone" : "Only known to you (you looked at it)"}>
          {top.revealed ? "revealed" : "👁 only you"}
        </span>
      )}
      <span className="pile-count">{count}</span>
      <span className="pile-label">Library</span>
      {beingSearched.length > 0 && <span className="pile-flag">searching</span>}
    </div>
  );
}

/** Right-click menu of a face-up pile (graveyard, exile…). */
export function pileMenu(player: string, zone: ZoneName, ids: string[]): MenuItem[] {
  const label = LABEL[zone] ?? zone;
  const open = () => useGame.getState().openBrowser({ zone: `${player}:${zone}`, title: label });
  const items: MenuItem[] = [{ label: `View ${label.toLowerCase()} (${ids.length})`, onClick: open }];
  if (ids.length) {
    items.push({ label: "Shuffle into library", onClick: async () => {
      if (await moveCards(ids, "library", { player })) void send({ type: "shuffle", player });
    } });
    items.push({ label: "Put all on bottom of library", onClick: () => void moveCards(ids, "library", { player, position: "bottom" }) });
    if (zone !== "exile") items.push({ label: "Exile all", onClick: () => void moveCards(ids, "exile", { player }) });
    if (zone !== "graveyard") items.push({ label: "Move all to graveyard", onClick: () => void moveCards(ids, "graveyard", { player }) });
    items.push({ label: "Return all to hand", onClick: () => void moveCards(ids, "hand", { player }) });
  }
  return items;
}

export const PILE_LABEL = LABEL;

/** Graveyard / exile / other face-up piles: shows the top card; click opens the zone browser. */
export function Pile({ player, zone }: { player: string; zone: ZoneName }) {
  const key = `${player}:${zone}`;
  const ids = useZoneIds(key) ?? [];
  const topId = ids[ids.length - 1];
  const top = useCardView(topId ?? "");
  const over = useDrag((s) => s.drag?.overZone === key);
  const label = LABEL[zone] ?? zone;
  const open = () => useGame.getState().openBrowser({ zone: key, title: label });
  return (
    <div
      className={`pile ${zone} ${over ? "drop-over" : ""}`}
      data-drop={key}
      title={label}
      onClick={open}
      onContextMenu={(e) => {
        e.preventDefault();
        openMenu(e, pileMenu(player, zone, ids), `${label}`);
      }}
      onPointerDown={(e) => {
        if (e.button !== 0 || !topId) return;
        beginPointerDrag(e, { ids: [topId], from: key, onDrop: (t) => dropInto([topId], t) });
      }}
      onPointerEnter={() => topId && useGame.getState().setHover(topId)}
      onPointerLeave={() => useGame.getState().setHover(null)}
    >
      <div className="pile-card">{top ? <GameCardFace card={top} /> : <div className="pile-empty" />}</div>
      <span className="pile-count">{ids.length}</span>
      <span className="pile-label">{label}</span>
    </div>
  );
}

/** Command zone: commanders shown face up with their tax; draggable to the stack/battlefield. */
export function CommandZone({ player, me }: { player: string; me: string }) {
  const key = `${player}:command`;
  const ids = useZoneIds(key) ?? [];
  const over = useDrag((s) => s.drag?.overZone === key);
  return (
    <div className={`command-zone ${over ? "drop-over" : ""}`} data-drop={key}>
      {ids.length === 0 && <span className="pile-label">Command</span>}
      {ids.map((id) => (
        <CommandCard key={id} id={id} me={me} player={player} />
      ))}
    </div>
  );
}

function CommandCard({ id, me, player }: { id: string; me: string; player: string }) {
  const card = useCardView(id);
  const tax = useGame((s) => {
    const key = card && !card.hidden ? card.commander_key : undefined;
    return key ? s.view?.players.find((p) => p.id === player)?.commander_tax[key] ?? 0 : 0;
  });
  if (!card) return null;
  return (
    <div
      className="command-card"
      data-card-id={id}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        beginPointerDrag(e, { ids: [id], from: card.zone, onDrop: (t) => dropInto([id], t) });
      }}
      onDoubleClick={() => void moveCards([id], "stack")}
      onContextMenu={(e) => {
        e.preventDefault();
        const view = useGame.getState().view;
        if (!view) return;
        const { title, items } = cardMenu(card, view, me);
        openMenu(e, items, title);
      }}
      onPointerEnter={() => useGame.getState().setHover(id)}
      onPointerLeave={() => useGame.getState().setHover(null)}
      title="Double-click to cast (adds commander tax)"
    >
      <GameCardFace card={card} />
      {tax > 0 && <span className="tax-badge" title="Commander tax">+{tax}</span>}
    </div>
  );
}
