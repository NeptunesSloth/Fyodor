import { usePrefs } from "../state/prefs";
import { AppearanceDialog } from "./AppearanceDialog";
import { DicePanel } from "./DicePanel";
import { DrawBagPanel } from "./DrawBagPanel";
import { ExtrasBag } from "./ExtrasBag";
import { EndGameDialog } from "./EndGameDialog";
import { HistoryDialog } from "./HistoryDialog";
import { MacroDialog } from "./MacroDialog";
import { SpawnDialog } from "./SpawnDialog";
import { SettingsPanel } from "../pages/SettingsPanel";
import { HostToolsDialog } from "./HostTools";
import { HOTKEYS, keyCap } from "./hotkeys";
import { useEffect, useMemo, useState } from "react";
import { CardDetails } from "../cards/CardDetails";
import { CardFace } from "../cards/CardFace";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { useDebounced } from "../hooks/useDebounced";
import { api } from "../services/api";
import { searchCards } from "../services/cards";
import { requestCards, useCard, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import type { CardData } from "../types/cards";
import { isVisible } from "../types/game";
import { send } from "./actions";
import { uniqueTokens } from "./bags";
import { GameCardFace } from "./GameCardFace";

export function GameDialogs({ me }: { me: string }) {
  const dialog = useGame((s) => s.dialog);
  const arg = useGame((s) => s.dialogArg);
  const inspect = useGame((s) => s.inspect);
  const close = () => useGame.getState().openDialog(null);
  return (
    <>
      {dialog === "tokens" && <TokenDialog me={me} sourceId={arg} onClose={close} />}
      {dialog === "dice" && <DicePanel onClose={close} />}
      {dialog === "drawbag" && <DrawBagPanel onClose={close} />}
      {dialog === "extras" && <ExtrasBag me={me} anchor={arg} onClose={close} />}
      {dialog === "ability" && <AbilityDialog sourceId={arg} onClose={close} />}
      {dialog === "save" && <SaveDialog onClose={close} />}
      {dialog === "help" && <HelpDialog onClose={close} initial={arg ?? ""} />}
      {dialog === "host" && <HostToolsDialog onClose={close} />}
      {dialog === "endgame" && <EndGameDialog onClose={close} />}
      {dialog === "appearance" && <AppearanceDialog onClose={close} />}
      {dialog === "history" && <HistoryDialog onClose={close} />}
      {dialog === "macro" && <MacroDialog cardId={arg} onClose={close} />}
      {dialog === "spawn" && <SpawnDialog onClose={close} />}
      {dialog === "settings" && <Modal title="Settings" onClose={close} wide><SettingsPanel /></Modal>}
      {inspect && <InspectDialog id={inspect} onClose={() => useGame.getState().setInspect(null)} />}
    </>
  );
}

function TokenDialog({ me, sourceId, onClose }: { me: string; sourceId: string | null; onClose: () => void }) {
  const view = useGame((s) => s.view);
  const cache = useCardCache((s) => s.cards);
  const [tab, setTab] = useState<"suggested" | "search" | "custom">("suggested");
  const [count, setCount] = useState(1);
  const [controller, setController] = useState(me);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<CardData[]>([]);
  const debounced = useDebounced(q, 180);
  const [custom, setCustom] = useState({ name: "Soldier", power: "1", toughness: "1", colors: [] as string[], type_line: "Token Creature — Soldier", text: "" });

  const suggested = useMemo(() => {
    if (!view) return [] as string[];
    const ids = new Set<string>();
    const shortcuts = view.players.find((p) => p.id === me)?.token_shortcuts ?? [];
    shortcuts.forEach((id) => ids.add(id));
    for (const c of Object.values(view.cards)) {
      if (!isVisible(c) || c.owner !== me || !c.card_id) continue;
      for (const t of cache[c.card_id]?.related_tokens ?? []) ids.add(t.id);
    }
    return uniqueTokens([...ids], (id) => cache[id]); // each token once, whichever printings the cards list
  }, [view, cache, me]);

  useEffect(() => requestCards(suggested), [suggested]);
  useEffect(() => {
    if (tab !== "search") return;
    let cancelled = false;
    searchCards(debounced, { tokens: "true", limit: 60 }).then((r) => {
      if (cancelled) return;
      useCardCache.getState().put(r.results);
      setResults(r.results);
    }, toastError);
    return () => {
      cancelled = true;
    };
  }, [debounced, tab]);

  const create = async (token: Record<string, unknown>) => {
    const collapse = usePrefs.getState().tokenCollapse;
    const stacked = collapse > 0 && count > collapse;
    if (await send({ type: "create_token", player: controller, token, count, stacked, ...(sourceId ? { source_id: sourceId } : {}) })) {
      toast(`Created ${count} token${count > 1 ? "s" : ""}`);
      onClose();
    }
  };

  return (
    <Modal
      title="Create tokens"
      wide
      onClose={onClose}
      footer={
        <>
          <label className="field inline">
            Count <input type="number" min={1} max={100} value={count} onChange={(e) => setCount(Math.max(1, Math.min(100, Number(e.target.value) || 1)))} />
          </label>
          <label className="field inline">
            For
            <select value={controller} onChange={(e) => setController(e.target.value)}>
              {view?.players.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <span className="spacer" />
          <button className="btn" onClick={onClose}>Cancel</button>
        </>
      }
    >
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={tab === "suggested" ? "on" : ""} onClick={() => setTab("suggested")}>From your cards ({suggested.length})</button>
        <button className={tab === "search" ? "on" : ""} onClick={() => setTab("search")}>Search tokens</button>
        <button className={tab === "custom" ? "on" : ""} onClick={() => setTab("custom")}>Custom</button>
      </div>
      {tab === "suggested" && (
        <>
          {suggested.length === 0 && <p className="hint">None of your cards list tokens they create. Search instead, or make a custom token.</p>}
          <div className="card-grid small">
            {suggested.map((id) => <TokenTile key={id} id={id} onPick={() => void create({ card_id: id })} />)}
          </div>
        </>
      )}
      {tab === "search" && (
        <>
          <input className="search" autoFocus placeholder="Treasure, Food, Clue, Zombie, Goblin, Soldier…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%", marginBottom: 10 }} />
          <div className="card-grid small">
            {results.map((c) => (
              <button key={c.id} className="grid-card" onClick={() => void create({ card_id: c.id })} title={`${c.name} — ${c.type_line ?? ""}`}>
                <CardFace card={c} size="small" />
                <span className="caption">{c.power != null ? `${c.power}/${c.toughness} ` : ""}{c.name}</span>
              </button>
            ))}
          </div>
        </>
      )}
      {tab === "custom" && (
        <form
          className="custom-token"
          onSubmit={(e) => {
            e.preventDefault();
            void create({ ...custom, power: custom.power || null, toughness: custom.toughness || null });
          }}
        >
          <div className="row">
            <label className="field grow">Name<input value={custom.name} maxLength={80} onChange={(e) => setCustom({ ...custom, name: e.target.value })} /></label>
            <label className="field">Power<input value={custom.power} maxLength={8} style={{ width: 70 }} onChange={(e) => setCustom({ ...custom, power: e.target.value })} /></label>
            <label className="field">Toughness<input value={custom.toughness} maxLength={8} style={{ width: 70 }} onChange={(e) => setCustom({ ...custom, toughness: e.target.value })} /></label>
          </div>
          <label className="field">Type line (creature types)<input value={custom.type_line} maxLength={120} onChange={(e) => setCustom({ ...custom, type_line: e.target.value })} /></label>
          <div className="field">
            Colors
            <div className="color-pick">
              {["W", "U", "B", "R", "G"].map((c) => (
                <button
                  type="button"
                  key={c}
                  className={`mana ${c.toLowerCase()} ${custom.colors.includes(c) ? "on" : "off"}`}
                  onClick={() => setCustom({ ...custom, colors: custom.colors.includes(c) ? custom.colors.filter((x) => x !== c) : [...custom.colors, c] })}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <label className="field">Rules text / notes<textarea rows={3} maxLength={1000} value={custom.text} onChange={(e) => setCustom({ ...custom, text: e.target.value })} /></label>
          <button className="btn primary" type="submit">Create {count} {custom.name}</button>
        </form>
      )}
    </Modal>
  );
}

function TokenTile({ id, onPick }: { id: string; onPick: () => void }) {
  const card = useCard(id);
  return (
    <button className="grid-card" onClick={onPick} title={card?.name}>
      <CardFace card={card} size="small" />
      <span className="caption">{card ? `${card.power != null ? `${card.power}/${card.toughness} ` : ""}${card.name}` : "…"}</span>
    </button>
  );
}

function AbilityDialog({ sourceId, onClose }: { sourceId: string | null; onClose: () => void }) {
  const source = useGame((s) => (sourceId ? s.view?.cards[sourceId] : undefined));
  const data = useCard(source && isVisible(source) ? source.card_id : null);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"activated" | "triggered" | "other">("activated");
  const lines = (data?.oracle_text ?? "").split("\n").filter(Boolean);
  const submit = async (t: string) => {
    if (!t.trim()) return;
    if (await send({ type: "create_ability", text: t.trim(), source_id: sourceId, kind })) onClose();
  };
  return (
    <Modal
      title={source && isVisible(source) ? `Ability of ${source.name}` : "Put an ability on the stack"}
      onClose={onClose}
      footer={
        <>
          <div className="seg">
            {(["activated", "triggered", "other"] as const).map((k) => (
              <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{k}</button>
            ))}
          </div>
          <span className="spacer" />
          <button className="btn primary" disabled={!text.trim()} onClick={() => void submit(text)}>Put on stack</button>
        </>
      }
    >
      {lines.length > 0 && (
        <div className="ability-lines">
          <p className="hint">Pick a line of rules text, or write your own:</p>
          {lines.map((l, i) => (
            <button key={i} className="ability-line" onClick={() => setText(l)}>{l}</button>
          ))}
        </div>
      )}
      <textarea rows={3} autoFocus value={text} maxLength={500} onChange={(e) => setText(e.target.value)} placeholder="e.g. Whenever a creature dies, draw a card." style={{ width: "100%" }} />
    </Modal>
  );
}

function SaveDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const [name, setName] = useState(view ? `${view.game.name} — turn ${view.turn.number}` : "");
  const token = useGame((s) => (s.gameId ? localStorage.getItem(`fyodor.seat.${s.gameId}`) : null));
  if (!view) return null;
  const save = async () => {
    try {
      const res = await fetch(`/api/games/${view.game.id}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { "X-Seat-Token": token } : {}) },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Save failed (${res.status})`);
      toast("Game saved");
      onClose();
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <Modal title="Save game" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => void save()}>Save</button></>}>
      <form onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <label className="field">Save name<input autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
      </form>
      <p className="hint">The whole table is saved, including hidden cards, library order and undo history. Games also autosave every few actions. Load saves from the Play screen.</p>
    </Modal>
  );
}

const keyLabel = keyCap;

const SHORTCUTS: [string, string][] = [
  ["Double-click (battlefield)", "Tap / untap"],
  ["Double-click (hand)", "Play to the battlefield"],
  ["Double-click (library)", "Draw a card"],
  ["Right-click", "All actions for a card, pile or player"],
  ["Drag", "Move cards between zones; drag empty table to box-select"],
  ["Shift / Ctrl + click", "Add to selection"],
  ["Alt + drop", "Place by hand, without the rules engine"],
  ["Right-drag", "3D table: turn the view around the table, and tilt it (a right-click that doesn't move still opens the menu)"],
  ["Middle-drag", "3D table: move the view across the table"],
  ["Wheel", "3D table: zoom toward the pointer (over a life heart: change life)"],
];

/** The common moves, in plain steps. */
const HOW_TO: [string, string][] = [
  ["Play a land or cast a spell", "Drag it from your hand onto your side of the table (or double-click it). With automation on, the engine asks for mana and targets."],
  ["Attack", "In combat, the engine asks you to declare attackers; or right-click a creature → Attack."],
  ["Respond", "When you have priority, cast or activate something; the turn dial says when you have it."],
  ["Choose a color, player or number", "A wheel opens at your pointer: click an option, or type its number and press Enter. Esc shows the list instead; Settings turns the wheel off."],
  ["Move on", "Press the big button on the turn dial (P): it says what passing will do."],
  ["Fix a mistake", "Undo (Ctrl+Z), or the Undo button on the message after a discard, exile or mill. The host can limit undo to each player's own actions, or to the host (Host tools)."],
];

/** What the marks on the 3D table mean. */
const TABLE_LEGEND: [string, string][] = [
  ["P/T plate", "Current power/toughness; ▲ above or ▼ below the printed card"],
  ["Round badges", "Keyword abilities from counters or effects (flying, first strike, deathtouch…); ×2 means two counters"],
  ["Orange beam", "An attack, landing on the creature or player attacked"],
  ["Blue beam", "A block"],
  ["Ice beam", "A target"],
  ["Numbered cards at the centre", "The stack: the highest number resolves next"],
  ["Turn / Priority tabs", "On a player's plaque: whose turn it is and who may act now"],
];

/** Help, task first: how to do things, what the table's marks mean, then every shortcut — all searchable. */
function HelpDialog({ onClose, initial }: { onClose: () => void; initial: string }) {
  const [q, setQ] = useState(initial);
  const match = ([k, v]: [string, string]) => !q.trim() || `${k} ${v}`.toLowerCase().includes(q.trim().toLowerCase());
  const keys = [...SHORTCUTS, ...HOTKEYS.map((h): [string, string] => [h.keys.map(keyLabel).join("  /  "), h.label])].filter(match);
  const how = HOW_TO.filter(match);
  const legend = TABLE_LEGEND.filter(match);
  return (
    <Modal title="Help" onClose={onClose}>
      <input type="search" className="help-search" placeholder="Search help: attack, undo, stack, camera…" aria-label="Search help"
        value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {how.length > 0 && (
        <>
          <h3 className="help-section">How to</h3>
          <table className="shortcuts"><tbody>{how.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
        </>
      )}
      {legend.length > 0 && (
        <>
          <h3 className="help-section">On the 3D table</h3>
          <table className="shortcuts"><tbody>{legend.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
        </>
      )}
      {keys.length > 0 && (
        <>
          <h3 className="help-section">Mouse and keys</h3>
          <table className="shortcuts"><tbody>{keys.map(([k, v]) => <tr key={k}><td><kbd>{k}</kbd></td><td>{v}</td></tr>)}</tbody></table>
        </>
      )}
      {!how.length && !legend.length && !keys.length && <p className="hint">Nothing matches “{q}”. Try a game word like attack, mana, stack or undo.</p>}
      <p className="hint">With automation on, the rules engine decides what's legal; with it off, you decide, as at a real table. Everything is logged and can be undone.</p>
    </Modal>
  );
}

function InspectDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const card = useGame((s) => s.view?.cards[id]);
  const data = useCard(card && isVisible(card) ? card.card_id : null);
  const [full, setFull] = useState<CardData | null>(null);
  useEffect(() => {
    if (data) api.get<CardData>(`/cards/${data.id}`).then(setFull, () => setFull(data));
  }, [data]);
  if (!card) return null;
  return (
    <Modal title={isVisible(card) ? card.name : "Hidden card"} onClose={onClose} wide>
      {full ? <CardDetails card={full} face={isVisible(card) ? card.face : 0} /> : <div style={{ width: 300 }}><GameCardFace card={card} peek /></div>}
    </Modal>
  );
}
