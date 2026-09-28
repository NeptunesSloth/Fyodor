import { AppearanceDialog } from "./AppearanceDialog";
import { EndGameDialog } from "./EndGameDialog";
import { HostToolsDialog } from "./HostTools";
import { HOTKEYS } from "./hotkeys";
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
import { GameCardFace } from "./GameCardFace";

export function GameDialogs({ me }: { me: string }) {
  const dialog = useGame((s) => s.dialog);
  const arg = useGame((s) => s.dialogArg);
  const inspect = useGame((s) => s.inspect);
  const close = () => useGame.getState().openDialog(null);
  return (
    <>
      {dialog === "tokens" && <TokenDialog me={me} sourceId={arg} onClose={close} />}
      {dialog === "dice" && <DiceDialog onClose={close} />}
      {dialog === "ability" && <AbilityDialog sourceId={arg} onClose={close} />}
      {dialog === "save" && <SaveDialog onClose={close} />}
      {dialog === "help" && <HelpDialog onClose={close} />}
      {dialog === "host" && <HostToolsDialog onClose={close} />}
      {dialog === "endgame" && <EndGameDialog onClose={close} />}
      {dialog === "appearance" && <AppearanceDialog onClose={close} />}
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
    return [...ids];
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
    if (await send({ type: "create_token", player: controller, token, count, ...(sourceId ? { source_id: sourceId } : {}) })) {
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

function DiceDialog({ onClose }: { onClose: () => void }) {
  const [expr, setExpr] = useState("2d6");
  const roll = (sides: number, count = 1) => void send({ type: "roll", sides, count });
  const parse = () => {
    const m = /^\s*(\d*)\s*d\s*(\d+)\s*$/i.exec(expr);
    if (!m) return toast("Use the form XdY, e.g. 3d6", "warn");
    roll(Number(m[2]), Number(m[1] || 1));
  };
  const last = useGame((s) => [...(s.view?.log ?? [])].reverse().find((e) => e.kind === "dice"));
  return (
    <Modal title="Dice & coins" onClose={onClose}>
      <div className="dice-grid">
        {[4, 6, 8, 10, 12, 20, 100].map((d) => (
          <button key={d} className="btn die" onClick={() => roll(d)}>d{d}</button>
        ))}
        <button className="btn die" onClick={() => void send({ type: "coin" })}>Coin</button>
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); parse(); }} style={{ marginTop: 12 }}>
        <label className="field grow">Roll XdY<input value={expr} onChange={(e) => setExpr(e.target.value)} /></label>
        <button className="btn primary" type="submit">Roll</button>
      </form>
      {last && (
        <p className="dice-result">
          {last.parts.map((p) => ("t" in p ? p.t : "")).join("")}
        </p>
      )}
      <p className="hint">Results are rolled on the host with a cryptographic RNG and written to the game log.</p>
    </Modal>
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

const keyLabel = (k: string) =>
  k.split("+").map((p) => (p === "ctrl" ? "Ctrl" : p === "shift" ? "Shift" : p === " " ? "Space" : p.length === 1 ? p.toUpperCase() : p[0]!.toUpperCase() + p.slice(1))).join("+");

const SHORTCUTS: [string, string][] = [
  ["Double-click (battlefield)", "Tap / untap"],
  ["Double-click (hand)", "Play to the battlefield"],
  ["Double-click (library)", "Draw a card"],
  ["Right-click", "All actions for a card, pile or player"],
  ["Drag", "Move cards between zones; drag empty table to box-select"],
  ["Shift / Ctrl + click", "Add to selection"],
];

function HelpDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Controls" onClose={onClose}>
      <table className="shortcuts">
        <tbody>
          {[...SHORTCUTS, ...HOTKEYS.map((h): [string, string] => [h.keys.map(keyLabel).join("  /  "), h.label])].map(([k, v]) => (
            <tr key={k}><td><kbd>{k}</kbd></td><td>{v}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="hint">Fyodor doesn't enforce the rules: you decide what's legal, just like at a real table. Everything is logged and can be undone.</p>
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
