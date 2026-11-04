import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
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
import { castableIn } from "./exileCastables";
import "./exile.css";
import { commanderDealt, dealtText } from "./commanderDamage";
import { isOut } from "./outOfGame";
import { taxMedallionUrl, taxSentence, whenIconFontReady } from "./seatIcons";
import { useHoverCard } from "./hoverCard";

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
  const out = useGame((s) => isOut(s.view, me)); // -- out of the game -- no "double-click to draw" for a player who left
  const count = lib?.count ?? 0;
  return (
    <div
      className={`pile library ${over ? "drop-over" : ""}`}
      data-drop={key}
      data-library=""
      title={out ? `${player === me ? "Your" : `${name}'s`} library` : "Click for library actions · double-click to draw"}
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
  const hover = useHoverCard();
  const key = `${player}:${zone}`;
  const ids = useZoneIds(key) ?? [];
  const topId = ids[ids.length - 1];
  const top = useCardView(topId ?? "");
  const over = useDrag((s) => s.drag?.overZone === key);
  const label = LABEL[zone] ?? zone;
  const castable = useGame((s) => (zone === "exile" ? castableIn(s.view, key) : 0));
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
      {...(topId ? hover(topId) : {})}
    >
      <div className="pile-card">{top ? <GameCardFace card={top} /> : <div className="pile-empty" />}</div>
      <span className="pile-count">{ids.length}</span>
      <span className="pile-label">{label}</span>
      {castable > 0 && <span className="pile-castable" data-testid="pile-castable" title="Cards here you may cast or play now">{castable} castable</span>}
    </div>
  );
}

/**
 * Command zone: a slot for each commander (a partner or background gets its own, as on the Oops mat), the commander
 * face up in it while it's here, and its tax counter under it (click +2, right-click −2). Anything else in the zone
 * (emblems …) comes after the slots.
 */
export function CommandZone({ player, me }: { player: string; me: string }) {
  const key = `${player}:command`;
  const ids = useZoneIds(key) ?? [];
  const over = useDrag((s) => s.drag?.overZone === key);
  const commanders = useGame((s) => s.view?.players.find((p) => p.id === player)?.commanders);
  const players = useGame((s) => s.view?.players);
  const list = commanders ?? [];
  const others = ids.filter((id) => !list.some((c) => c.instance_id === id));
  return (
    <div className={`command-zone ${over ? "drop-over" : ""} ${list.length > 1 ? "partners" : ""}`} data-drop={key}>
      {ids.length === 0 && list.length === 0 && <span className="pile-label">Command</span>}
      {list.map((c, i) => (
        <div key={c.key} className="command-slot">
          {c.instance_id && ids.includes(c.instance_id) ? <CommandCard id={c.instance_id} me={me} player={player} />
            : <div className="command-empty" title={`${c.name} isn't in the command zone${dealtLine(players, c.key)}`}>
              <Icon name="crown" size={15} /><span className="command-empty-label">{i === 0 ? "Commander" : "Partner"}</span>
            </div>}
          <TaxButton commander={c.key} name={c.name} tax={c.tax} />
        </div>
      ))}
      {others.map((id) => (
        <CommandCard key={id} id={id} me={me} player={player} />
      ))}
    </div>
  );
}

/** The commander-damage line for an empty command slot's tooltip (hovering the card itself shows it in the inspector). */
function dealtLine(players: Parameters<typeof commanderDealt>[0] | undefined, key: string): string {
  const text = players ? dealtText(commanderDealt(players, key)) : "";
  return text ? `\nCommander damage dealt: ${text}` : "";
}

/**
 * A commander's tax, kept by hand: click +2 (one more cast), right-click −2. A brass tax coin with the tax to pay
 * struck on it ("+4"), as the 3D table's coin column (game/seatIcons.ts); at 0 an empty coin socket.
 */
function TaxButton({ commander, name, tax }: { commander: string; name: string; tax: number }) {
  const [, redraw] = useState(0);
  useEffect(() => { void whenIconFontReady().then(() => redraw(1)); }, []);
  return (
    <button className={`tax-btn ${tax ? "" : "zero"}`} data-testid={`tax-${commander}`}
      title={`${taxSentence(tax)}\n${name}: click +2, right-click −2`} aria-label={`Commander tax for ${name}: ${tax}. Click to add 2, right-click to remove 2`}
      onClick={(e) => { e.stopPropagation(); void send({ type: "commander_tax", commander, delta: 2 }); }}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); void send({ type: "commander_tax", commander, delta: -2 }); }}
      onPointerDown={(e) => e.stopPropagation()}>
      <img src={taxMedallionUrl(tax)} alt="" draggable={false} />
    </button>
  );
}

function CommandCard({ id, me, player }: { id: string; me: string; player: string }) {
  const card = useCardView(id);
  const hover = useHoverCard();
  void player;
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
      {...hover(id)}
      title="Double-click to cast (adds commander tax)"
    >
      <GameCardFace card={card} />
    </div>
  );
}
