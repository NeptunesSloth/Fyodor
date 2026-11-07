import { useEffect, useMemo, useState } from "react";
import { Modal } from "../components/Modal";
import { toast } from "../components/Toasts";
import { requestCards, useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, isVisible, type GameView } from "../types/game";
import { send } from "./actions";
import { keyLabel } from "./hotkeys";
import {
  SLOW_OBJECTS, SLOW_TRIGGERS, biovisionaryNeed, boardLoad, createTokens, creatureCensus, doppelgang, factorFor, fmt, graveyardLands, landfallApply,
  landsUntil, project, readBoard, selfCopyApply, selfCopyGrowth, tokenCensus, totals, underPressure,
  type ApplyStep, type Board, type BoardLoad, type TokenFactor,
} from "./tokenMath";
import "./tokenMath.css";

/**
 * TOKEN MATH (Shift+T, or the Bag of Extras): Scute Swarm and landfall projections, token doublers and copies, and a count
 * of your tokens. It reads the public board (any player's, as everyone can see it) and sends nothing; every number can be
 * changed by hand to try a line before playing it. The math is game/tokenMath.ts.
 */
type Tab = "landfall" | "copies" | "board";

interface Overrides { lands?: number; swarms?: number; triggers?: number; doublers?: number; landNames?: number }

const num = (v: string, min = 0, max = 1_000_000) => Math.max(min, Math.min(max, Math.floor(Number(v) || 0)));

function NumberField({ label, value, onChange, min = 0, max = 1_000_000, title, testId }: {
  label: string; value: number; onChange: (n: number) => void; min?: number; max?: number; title?: string; testId?: string;
}) {
  return (
    <label className="field tm-num" title={title}>
      {label}
      <input type="number" min={min} max={max} value={value} onChange={(e) => onChange(num(e.target.value, min, max))} data-testid={testId} />
    </label>
  );
}

export function TokenMathDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const me = useGame((s) => (s.view ? perspective(s.view, s.actingAs) : ""));
  const cache = useCardCache((s) => s.cards);
  const keymap = usePrefs((s) => s.keymap);
  const [player, setPlayer] = useState(me);
  const [tab, setTab] = useState<Tab>("landfall");
  const [over, setOver] = useState<Overrides>({});
  const [enter, setEnter] = useState(1);
  const [together, setTogether] = useState(false);
  const [skip, setSkip] = useState<string[]>([]);
  const [target, setTarget] = useState(100);
  const [make, setMake] = useState(1);
  const [makeCreature, setMakeCreature] = useState(true);
  const [rounds, setRounds] = useState(3);
  const [sacrificed, setSacrificed] = useState(0);
  const [dopX, setDopX] = useState(3);

  const ids = useMemo(() => {
    const out: string[] = [];
    if (!view) return out;
    for (const [zone, zids] of Object.entries(view.zones)) {
      // the battlefield, and the graveyards (public) for Lumra's count
      if (!(zone.endsWith(":battlefield") || zone.endsWith(":graveyard")) || !Array.isArray(zids)) continue;
      for (const id of zids) {
        const c = view.cards[id];
        if (c && isVisible(c) && c.card_id) out.push(c.card_id);
      }
    }
    return out;
  }, [view]);
  useEffect(() => requestCards(ids), [ids]);

  const read = useMemo(() => (view ? readBoard(view, player, (id) => cache[id]) : null), [view, player, cache]);
  const load = useMemo(() => (view ? boardLoad(view) : null), [view]);
  if (!view || !read || !load) return null;

  const extraDoublers: TokenFactor[] = Array.from({ length: over.doublers ?? 0 }, () => ({ name: "Extra doubler", factor: 2, creatureOnly: false }));
  const board: Board = {
    ...read,
    lands: over.lands ?? read.lands,
    landNames: over.landNames ?? read.landNames,
    swarms: over.swarms ?? read.swarms,
    triggers: over.triggers ?? read.triggers,
    factors: [...read.factors, ...extraDoublers],
  };
  const edited = Object.values(over).some((v) => v !== undefined);
  const set = (o: Overrides) => setOver((cur) => ({ ...cur, ...o }));
  const factorC = factorFor(board.factors, true);
  const factorO = factorFor(board.factors, false);
  const automation = !!view.rules;
  // -- put it on the table -- by hand, automation off, and only on your own board
  const apply: ApplyMode = automation ? "engine" : player !== me || view.viewer === SPECTATOR ? "other" : "yours";
  const key = keyLabel("token_math", keymap);
  const name = view.players.find((p) => p.id === player)?.name ?? "";
  const fields = <>
    {tab === "landfall" && <>
      <NumberField label="Lands" value={board.lands} onChange={(n) => set({ lands: n })} testId="tm-lands"
        title={read.creaturesAreLands ? "Lands you control, counting your nontoken creatures (Ashaya)" : "Lands you control"} />
      <NumberField label="Scute Swarms" value={board.swarms} onChange={(n) => set({ swarms: n })} testId="tm-swarms" />
      <NumberField label="Triggers per land" value={board.triggers} min={1} max={64} onChange={(n) => set({ triggers: n })} testId="tm-triggers"
        title="1, plus one for each Ancient Greenwarden, Traveling Chocobo or Yarok (603.2d)" />
    </>}
    <NumberField label="Extra doublers" value={over.doublers ?? 0} max={20} onChange={(n) => set({ doublers: n })} testId="tm-doublers"
      title="Try it with more token doublers (each ×2), e.g. a Parallel Lives still in your hand" />
    {edited && <button className="btn" onClick={() => setOver({})}>Back to the board</button>}
  </>;

  return (
    <Modal title="Token math" wide onClose={onClose}
      footer={<>
        <span className="hint">Only you see this: it reads the public board, and changes nothing unless you put a result on the table.{key ? ` ${key} opens and closes it.` : ""}</span>
        <span className="spacer" />
        <button className="btn" onClick={onClose}>Close</button>
      </>}>
      <div className="tm-top">
        <div className="seg" role="tablist">
          {([["landfall", "Landfall & Scute Swarm"], ["copies", "Copies & doublers"], ["board", "Tokens on board"]] as const).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)} data-testid={`tm-tab-${id}`}>{label}</button>
          ))}
        </div>
        <span className="spacer" />
        <label className="field inline">
          Board
          <select value={player} onChange={(e) => { setPlayer(e.target.value); setOver({}); setSkip([]); }}>
            {view.players.map((p) => <option key={p.id} value={p.id}>{p.id === me ? `${p.name} (you)` : p.name}</option>)}
          </select>
        </label>
      </div>

      {tab !== "landfall" && <Multipliers board={board} read={read} factorC={factorC} factorO={factorO} />}
      {tab !== "landfall" && <LoadLine load={load} />}

      {tab !== "board" && tab !== "landfall" && <div className="tm-row">{fields}</div>}

      {tab === "landfall" && (
        <LandfallTab fields={fields} edited={edited} mult={<Multipliers board={board} read={read} factorC={factorC} factorO={factorO} />}
          load={<LoadLine load={load} />} name={name} board={board} enter={enter} setEnter={setEnter} together={together} setTogether={setTogether}
          skip={skip} setSkip={setSkip} target={target} setTarget={setTarget} automation={automation}
          setLandNames={(n) => set({ landNames: n })} sacrificed={sacrificed} setSacrificed={setSacrificed}
          graveyard={graveyardLands(view, player, (id) => cache[id])} apply={apply} me={me}
          related={(id) => (id ? cache[id]?.related_tokens ?? [] : [])} />
      )}
      {tab === "copies" && (
        <CopiesTab board={board} make={make} setMake={setMake} creature={makeCreature} setCreature={setMakeCreature}
          rounds={rounds} setRounds={setRounds} factorC={factorC} automation={automation}
          census={creatureCensus(view, player, (id) => cache[id])}
          biovisionaries={countNamed(view, player, "Biovisionary")} dopX={dopX} setDopX={setDopX} apply={apply} me={me} />
      )}
      {tab === "board" && <BoardTab rows={tokenCensus(view, player)} name={name} />}
    </Modal>
  );
}

/** "yours": automation off and your own board, so a result can go on the table; "engine": the rules engine makes them; "other": not your board. */
type ApplyMode = "yours" | "engine" | "other";

/** Ask once, listing everything, then send the actions in order (each is one undo step). */
async function putOnTable(heading: string, steps: ApplyStep[], skipped: string[]): Promise<void> {
  const text = [heading, ...steps.map((s) => `• ${s.line}`), ...(skipped.length ? ["", "Left to you:", ...skipped.map((s) => `• ${s}`)] : [])].join("\n");
  if (!window.confirm(text)) return;
  const done: string[] = [];
  for (const s of steps) {
    if (!(await send(s.action))) break;
    done.push(s.line);
  }
  if (done.length) toast(`On the table: ${done.join(", ")}`);
}

/** The "put it on the table" control, or why there isn't one. */
function ApplyBar({ mode, label, disabled, why, onApply, testId }: {
  mode: ApplyMode; label: string; disabled?: boolean; why?: string; onApply: () => void; testId: string;
}) {
  if (mode === "engine") return <p className="hint tm-apply" data-testid={`${testId}-hint`}>The rules engine makes these when the triggers resolve.</p>;
  if (mode === "other") return null;
  return (
    <div className="tm-apply">
      <button className="btn primary" disabled={disabled} onClick={onApply} data-testid={testId}
        title="Automation is off: make these tokens now, as one card ×N where there are many. Asks first; Undo takes each back.">{label}</button>
      {why && <span className="hint">{why}</span>}
    </div>
  );
}

/** The whole battlefield as the table and the rules engine count it. */
function LoadLine({ load }: { load: BoardLoad }) {
  return (
    <p className="tm-load" data-testid="tm-load">
      On the battlefield now: <b>{fmt(load.objects)}</b> object{load.objects === 1 ? "" : "s"}
      {load.permanents !== load.objects && <> standing for <b>{fmt(load.permanents)}</b> permanents (a ×N stack is one object for N tokens)</>}
      {load.triggers > 0 && <>; {fmt(load.triggers)} trigger{load.triggers === 1 ? "" : "s"} waiting</>}.
    </p>
  );
}

/**
 * BOARD PRESSURE: a small top-bar badge once the battlefield is big (150+ objects, a ×N stack past 100, or 50+ triggers waiting).
 * It opens Token math. Public counts only (game/tokenMath.ts boardLoad).
 */
export function BoardPressure() {
  const view = useGame((s) => s.view);
  const load = useMemo(() => (view ? boardLoad(view) : null), [view]);
  const keymap = usePrefs((s) => s.keymap);
  if (!load || !underPressure(load)) return null;
  const key = keyLabel("token_math", keymap);
  const title = [
    `${fmt(load.objects)} objects on the battlefield${load.permanents !== load.objects ? `, standing for ${fmt(load.permanents)} permanents (a ×N stack is one object for N tokens)` : ""}.`,
    load.triggers ? `${fmt(load.triggers)} triggered abilities on the stack.` : "",
    "With rules automation on, each token copy (a Scute Swarm, a clone) is its own object for the rules engine and each trigger resolves one at a time, so big turns take a while.",
    `Token math${key ? ` (${key})` : ""} projects a turn before you play it.`,
  ].filter(Boolean).join(" ");
  return (
    <button className="tt-btn ghost tm-pressure" data-testid="board-pressure" title={title} aria-label={`Board load: ${title}`}
      onClick={() => useGame.getState().openDialog("token_math")}>
      <span className="tm-pressure-n">{fmt(load.objects)}</span> objects
      {load.biggestStack > 1 && <span className="tm-pressure-sub">· ×{fmt(load.biggestStack)} stack</span>}
      {load.triggers > 0 && <span className="tm-pressure-sub">· {fmt(load.triggers)} triggers</span>}
    </button>
  );
}

function countNamed(view: GameView, player: string, name: string): number {
  let n = 0;
  for (const c of Object.values(view.cards)) {
    if (isVisible(c) && c.controller === player && c.zone.endsWith(":battlefield") && c.name === name) n += Math.max(1, c.quantity ?? 1);
  }
  return n;
}

function Multipliers({ board, read, factorC, factorO }: { board: Board; read: Board; factorC: number; factorO: number }) {
  const chips = [
    ...read.triggerSources.map((s) => ({ k: `t-${s}`, label: s, what: "+1 landfall trigger" })),
    ...board.factors.map((f, i) => ({ k: `f-${i}`, label: f.name, what: `×${f.factor}${f.creatureOnly ? " creature tokens" : " tokens"}` })),
    ...read.extras.map((s, i) => ({ k: `e-${i}`, label: s, what: "+ that many Squirrels" })),
  ];
  return (
    <div className="tm-mult" data-testid="tm-multipliers">
      {chips.length === 0 ? <span className="hint">No token or trigger doublers on this board.</span>
        : <span className="tm-mult-head">Each creation: <b>×{fmt(factorC)}</b> creature tokens{factorO !== factorC ? <>, <b>×{fmt(factorO)}</b> other tokens</> : null}</span>}
      {chips.map((c) => <span key={c.k} className="tm-chip" title={c.what}>{c.label} <small>{c.what}</small></span>)}
    </div>
  );
}

function SlowNote({ triggers, objects, automation }: { triggers: number; objects: number; automation: boolean }) {
  if (!automation || (triggers <= SLOW_TRIGGERS && objects <= SLOW_OBJECTS)) return null;
  return (
    <p className="tm-warn" data-testid="tm-slow">
      Big board for the rules engine: {fmt(triggers)} triggers resolve one at a time, and every token copy (a Scute Swarm, a clone) is its own
      object; copies of cards never stack. Expect it to take a while. To skip ahead, a player can pause rules automation and set the board up by hand.
    </p>
  );
}

function LandfallTab({ fields, edited, mult, load, name, board, enter, setEnter, together, setTogether, skip, setSkip, target, setTarget, automation, setLandNames, sacrificed, setSacrificed,
  graveyard, apply, me, related }: {
  fields: React.ReactNode; edited: boolean; mult: React.ReactNode; load: React.ReactNode; name: string;
  board: Board; enter: number; setEnter: (n: number) => void; together: boolean; setTogether: (b: boolean) => void;
  skip: string[]; setSkip: (s: string[]) => void; target: number; setTarget: (n: number) => void; automation: boolean; setLandNames: (n: number) => void;
  sacrificed: number; setSacrificed: (n: number) => void; graveyard: number; apply: ApplyMode; me: string;
  related: (cardId: string | undefined) => { id: string; name: string }[];
}) {
  const [shift, setShift] = useState(Math.min(board.lands, 6) || 1);
  const allAtOnce = (n: number, sac: number) => { setEnter(Math.max(1, n)); setTogether(true); setSacrificed(sac); };
  const steps = project(board, { lands: enter, together, skip, sacrificed: together ? sacrificed : 0 });
  const sum = totals(steps);
  const plan = landfallApply(board, sum, { player: me, collapse: usePrefs.getState().tokenCollapse, related });
  const last = steps.at(-1);
  const until = landsUntil(board, target);
  const otherLabels = [...new Set(steps.flatMap((s) => Object.keys(s.tokens)))];
  const objects = sum.newSwarms + sum.insects + sum.extra + Object.values(sum.tokens).reduce((a, b) => a + b, 0);
  const hasPlants = board.makers.some((m) => m.kind === "plant_counters");
  const hasTifa = board.makers.some((m) => m.kind === "double_power");
  const shown = steps.length > 40 ? [...steps.slice(0, 20), null, ...steps.slice(-19)] : steps;
  const nothing = board.swarms === 0 && board.makers.length === 0 && Object.keys(sum.tokens).length === 0 && sum.mana === 0;
  const how = together ? `${enter} land${enter === 1 ? "" : "s"} at once` : `${enter} land${enter === 1 ? "" : "s"}, one at a time`;
  const tiles: { k: string; n: string; label: string; plus?: string }[] = [
    ...(board.swarms > 0 ? [{ k: "sw", n: fmt(last?.swarms ?? board.swarms), label: "Scute Swarms", plus: `+${fmt(sum.newSwarms)}` }] : []),
    ...(sum.insects > 0 ? [{ k: "in", n: `+${fmt(sum.insects)}`, label: "Insects" }] : []),
    ...Object.entries(sum.tokens).map(([l, n]) => ({ k: `t-${l}`, n: `+${fmt(n)}`, label: l })),
    ...(sum.extra > 0 ? [{ k: "ex", n: `+${fmt(sum.extra)}`, label: "extra tokens" }] : []),
    ...(sum.mana > 0 ? [{ k: "mana", n: `+${fmt(sum.mana)}`, label: "mana" }] : []),
    { k: "tr", n: fmt(sum.triggers), label: sum.triggers === 1 ? "trigger" : "triggers" },
  ];
  return (
    <>
      {/* the answer first: what this many lands makes */}
      <section className={`tm-result ${nothing ? "quiet" : ""}`} aria-live="polite">
        <p className="tm-result-head">Play <b>{how}</b>{nothing ? null : <> and you get</>}</p>
        {nothing ? (
          <p className="tm-result-none">Nothing on {name ? `${name}'s` : "this"} board makes tokens on landfall. Type a number of Scute Swarms
            below to try a line before you play it.</p>
        ) : (
          <div className="tm-tiles">
            {tiles.map((t) => (
              <div key={t.k} className={`tm-tile ${t.k === "sw" ? "main" : ""} ${t.k === "tr" ? "dim" : ""}`}>
                <span className="tm-tile-n">{t.n}</span>
                <span className="tm-tile-l">{t.label}{t.plus && <small> ({t.plus})</small>}</span>
              </div>
            ))}
          </div>
        )}
        {/* (a plain sentence too: screen readers and the browser tests read this one) */}
        <p className={`tm-sum ${hasPlants || hasTifa ? "" : "tm-sr"}`} data-testid="tm-total">
          {fmt(sum.triggers)} triggers
          {board.swarms > 0 && <>, <b>{fmt(last?.swarms ?? board.swarms)}</b> Scute Swarms (+{fmt(sum.newSwarms)})</>}
          {sum.insects > 0 && <>, {fmt(sum.insects)} Insects</>}
          {Object.entries(sum.tokens).map(([l, n]) => <span key={l}>, {fmt(n)} {l}</span>)}
          {sum.extra > 0 && <>, {fmt(sum.extra)} extra tokens</>}
          {sum.mana > 0 && <>, {fmt(sum.mana)} mana</>}
          {hasPlants && <>, +{fmt(steps.reduce((a, s) => a + s.plantCounters, 0))} counters on each Plant ({board.plants} now)</>}
          {hasTifa && <>, power doubled {fmt(steps.reduce((a, s) => a + s.doublings, 0))} times (×{fmt(2 ** steps.reduce((a, s) => a + s.doublings, 0))})</>}
          .
        </p>
        {board.swarms > 0 && (
          <p className="tm-until">
            <label className="tm-inline-num">Want
              <input type="number" min={1} value={target} onChange={(e) => setTarget(num(e.target.value, 1))} data-testid="tm-target" aria-label="Swarms wanted" />
              Swarms?</label>
            <span data-testid="tm-until">{until === null ? "Out of reach one land at a time." : until === 0 ? "You're there." : `${until} more land${until > 1 ? "s" : ""}, one at a time.`}</span>
          </p>
        )}
        <ApplyBar mode={apply} label="Put this on the table" testId="tm-apply" disabled={!plan.steps.length}
          why={plan.steps.length ? "Play the lands yourself; mana and counters are yours to add." : plan.skipped[0] ? `Nothing to make here: ${plan.skipped[0]}.` : "No tokens in this projection."}
          onApply={() => void putOnTable(`Put on your battlefield (${how}):`, plan.steps, plan.skipped)} />
      </section>
      <SlowNote triggers={Math.max(0, ...steps.map((s) => s.triggers))} objects={objects} automation={automation} />

      <div className="tm-cols">
        <fieldset className="tm-card">
          <legend>1 · The lands you play</legend>
          <div className="tm-row">
            <NumberField label="How many" value={enter} min={1} max={together ? 500 : 60} onChange={setEnter} testId="tm-enter" />
            <div className="seg" role="group" aria-label="How they enter">
              <button className={!together ? "on" : ""} onClick={() => setTogether(false)} data-testid="tm-one-at-a-time" title="Land drops, fetch lands, Azusa: each land resolves before the next">One at a time</button>
              <button className={together ? "on" : ""} onClick={() => setTogether(true)} data-testid="tm-all-at-once" title="Lumra, Scapeshift, Splendid Reclamation: every land enters in one event">All at once</button>
            </div>
            {together && (
              <NumberField label="Sacrificed first" value={sacrificed} max={board.lands} onChange={setSacrificed} testId="tm-sacrificed"
                title="Scapeshift: the lands you sacrifice leave before the new ones enter, so the lands you control end where they started" />
            )}
          </div>
          <p className="tm-card-sub">Or set it up as:</p>
          <div className="tm-quick" role="group" aria-label="Quick setups">
            <button className="btn" disabled={graveyard === 0} onClick={() => allAtOnce(graveyard, 0)} data-testid="tm-graveyard"
              title="Lumra, Splendid Reclamation: every land card in this player's graveyard (public) returns at once">
              {graveyard ? `Return ${graveyard} from graveyard` : "No lands in graveyard"}
            </button>
            <span className="tm-quick-scape">
              <button className="btn" disabled={shift < 1 || board.lands < 1} onClick={() => allAtOnce(Math.min(shift, board.lands), Math.min(shift, board.lands))} data-testid="tm-scapeshift"
                title="Sacrifice that many lands, then that many enter at once: the lands you control end where they started">
                Scapeshift
              </button>
              <input type="number" min={1} max={Math.max(1, board.lands)} value={shift} aria-label="Lands sacrificed to Scapeshift"
                onChange={(e) => setShift(num(e.target.value, 1, Math.max(1, board.lands)))} data-testid="tm-scapeshift-n" />
            </span>
          </div>
        </fieldset>
        <fieldset className="tm-card">
          <legend>2 · {name ? `${name}'s board` : "The board"} <small>{edited ? "(edited)" : "(read from the table)"}</small></legend>
          <div className="tm-row">{fields}</div>
          {mult}
          {board.makers.length > 0 && (
            <div className="tm-makers">
              {board.makers.map((m) => (
                <label key={m.name} className="tm-maker" title={m.needsSevenNames ? "Needs seven or more lands with different names" : m.optional ? "A \"you may\": counted as yes" : undefined}>
                  <input type="checkbox" checked={!skip.includes(m.name)} onChange={(e) => setSkip(e.target.checked ? skip.filter((s) => s !== m.name) : [...skip, m.name])} />
                  {m.name}{m.count > 1 ? ` ×${m.count}` : ""} <small>{m.kind === "tokens" ? `${m.amount > 1 ? `${m.amount} ` : ""}${m.label}` : m.label}</small>
                  {m.needsSevenNames && (
                    <span className="tm-names" onClick={(e) => e.preventDefault()}>
                      — {board.landNames} names{board.landNames < 7 ? " (off)" : ""}
                      <input type="number" min={0} max={99} value={board.landNames} aria-label="Lands with different names" onChange={(e) => setLandNames(num(e.target.value, 0, 99))} />
                    </span>
                  )}
                </label>
              ))}
            </div>
          )}
          {load}
        </fieldset>
      </div>

      {!nothing && (
        <details className="tm-more">
          <summary>Land by land ({steps.length} step{steps.length === 1 ? "" : "s"})</summary>
          <table className="shortcuts tm-table" data-testid="tm-steps">
            <thead>
              <tr>
                <th>{together ? "Event" : "Land"}</th><th>Lands</th><th>Triggers</th><th>Scute Swarms</th>
                {sum.insects > 0 && <th>Insects</th>}
                {otherLabels.map((l) => <th key={l}>{l}</th>)}
                {sum.extra > 0 && <th>Extra</th>}
                {sum.mana > 0 && <th>Mana</th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((s, i) => s === null ? (
                <tr key="gap"><td colSpan={8} className="hint">…</td></tr>
              ) : (
                <tr key={i}>
                  <td>{together ? `${s.entered} land${s.entered === 1 ? "" : "s"}${sacrificed ? ` (${Math.min(sacrificed, board.lands)} sacrificed first)` : ""}` : `#${steps.indexOf(s) + 1}`}</td>
                  <td>{fmt(s.lands)}</td>
                  <td>{fmt(s.triggers)}</td>
                  <td><b>{fmt(s.swarms)}</b>{s.newSwarms ? <small> (+{fmt(s.newSwarms)})</small> : null}</td>
                  {sum.insects > 0 && <td>{s.insects ? `+${fmt(s.insects)}` : ""}</td>}
                  {otherLabels.map((l) => <td key={l}>{s.tokens[l] ? `+${fmt(s.tokens[l]!)}` : ""}</td>)}
                  {sum.extra > 0 && <td>{s.extra ? `+${fmt(s.extra)}` : ""}</td>}
                  {sum.mana > 0 && <td>{s.mana ? `+${fmt(s.mana)}` : ""}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      <details className="tm-more">
        <summary>Why one at a time grows faster</summary>
        <p className="hint">
          Each land is one landfall event (603.2c). Lands entering together trigger every Scute Swarm once per land, but the copies they make
          weren't there yet, so they don't trigger (603.10). One at a time, the new copies trigger on the next land, so the count doubles each land.
          The "six or more lands" check happens as each trigger resolves; Scapeshift sacrifices before the new lands enter, so the check sees the
          count you started with.
        </p>
      </details>
    </>
  );
}

function CopiesTab({ board, make, setMake, creature, setCreature, rounds, setRounds, factorC, automation, census, biovisionaries, dopX, setDopX, apply, me }: {
  board: Board; make: number; setMake: (n: number) => void; creature: boolean; setCreature: (b: boolean) => void;
  rounds: number; setRounds: (n: number) => void; factorC: number; automation: boolean;
  census: { count: number; power: number; untapped: number; untappedPower: number }; biovisionaries: number;
  dopX: number; setDopX: (n: number) => void; apply: ApplyMode; me: string;
}) {
  const made = createTokens(make, creature, board.factors, board.extras.length);
  const dop = doppelgang(dopX, board.factors, creature, board.extras.length);
  const hoofX = census.count + 1;
  const bio = biovisionaryNeed(biovisionaries, factorC);
  return (
    <>
      <h3 className="help-section">Create tokens or copies</h3>
      <div className="tm-row">
        <NumberField label="Tokens (or copies)" value={make} min={1} onChange={setMake} testId="tm-make" title="One effect creating this many: Rite of Replication kicked makes 5." />
        <label className="field inline"><input type="checkbox" checked={creature} onChange={(e) => setCreature(e.target.checked)} /> creature tokens</label>
        <button className="btn" onClick={() => { setMake(5); setCreature(true); }} data-testid="tm-rite" title="Rite of Replication, kicked: five copies of target creature">Rite of Replication, kicked</button>
        <span className="tm-big" data-testid="tm-made">→ {fmt(made.tokens)}{made.extra ? ` + ${fmt(made.extra)} Squirrels` : ""}</span>
      </div>
      <div className="tm-row" title="Doppelgang: for each of X target permanents, create X tokens that are copies of that permanent (X creations, each doubled)">
        <NumberField label="Doppelgang X" value={dopX} min={1} max={1000} onChange={setDopX} testId="tm-dop" />
        <span data-testid="tm-dop-out">
          {fmt(dopX)} target{dopX === 1 ? "" : "s"} × <b>{fmt(dop.perTarget)}</b> copies each{dop.perTarget !== dopX ? ` (${fmt(dopX)} × ${fmt(dop.perTarget / dopX)})` : ""} = <b>{fmt(dop.total)}</b> tokens
          {dop.extra ? ` + ${fmt(dop.extra)} Squirrels` : ""}
        </span>
      </div>
      <SlowNote triggers={0} objects={Math.max(made.tokens + made.extra, dop.total + dop.extra)} automation={automation} />

      <h3 className="help-section">Cards that copy themselves</h3>
      {board.copiers.length === 0 ? (
        <p className="hint">None on this board. Biowaste Blob, Council of Reeds and Giant Adephage show up here: every copy has the ability too.</p>
      ) : (
        <>
          <div className="tm-row"><NumberField label="Rounds" value={rounds} min={1} max={20} onChange={setRounds} testId="tm-rounds" /></div>
          <table className="shortcuts tm-table" data-testid="tm-copiers">
            <thead><tr><th>Card</th><th>Now</th>{Array.from({ length: rounds }, (_, i) => <th key={i}>{i + 1}</th>)}{apply === "yours" && <th />}</tr></thead>
            <tbody>
              {board.copiers.map((c) => {
                const step = selfCopyApply(c, factorC, rounds, me);
                return (
                  <tr key={c.name} title={`Triggers ${c.when}`}>
                    <td>{c.name}<br /><small className="hint">{c.when}</small></td>
                    <td>{c.count}</td>
                    {selfCopyGrowth(c.count, factorC, rounds).map((n, i) => <td key={i}>{fmt(n)}</td>)}
                    {apply === "yours" && (
                      <td>
                        <button className="btn" disabled={!step} data-testid="tm-copier-apply"
                          title={step ? `Make ${step.line} now. Asks first; Undo takes it back.` : "Too many to stand for with one card"}
                          onClick={() => step && void putOnTable(`${c.name}, ${rounds} round${rounds === 1 ? "" : "s"}:`, [step], [])}>
                          Apply {rounds} round{rounds === 1 ? "" : "s"}
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {apply === "engine" && <p className="hint">The rules engine makes these copies when the triggers resolve.</p>}
        </>
      )}

      <h3 className="help-section">Swing</h3>
      <p data-testid="tm-swing">
        {fmt(census.count)} creatures, {fmt(census.untappedPower)} power untapped ({fmt(census.power)} in all).
        {" "}With Craterhoof Behemoth entering: X = {fmt(hoofX)}, so the untapped creatures plus Craterhoof hit for <b>{fmt(census.untappedPower + 5 + (census.untapped + 1) * hoofX)}</b> (all trample, if they can all attack).
      </p>
      {biovisionaries > 0 && (
        <p data-testid="tm-biovisionary">
          Biovisionary: {biovisionaries} of 4
          {bio.copies === 0 ? " — you win at the beginning of the end step." : <> — <b>{bio.copies}</b> more cop{bio.copies === 1 ? "y" : "ies"} needed
            {factorC > 1 ? <>: each one-copy spell makes ×{fmt(factorC)} with your doublers, so <b>{bio.spells}</b> spell{bio.spells === 1 ? "" : "s"}</> : null}.</>}
        </p>
      )}
    </>
  );
}

function BoardTab({ rows, name }: { rows: ReturnType<typeof tokenCensus>; name: string }) {
  if (!rows.length) return <p className="hint">{name} has no tokens on the battlefield.</p>;
  const all = rows.reduce((a, r) => ({ count: a.count + r.count, power: a.power + r.power, untapped: a.untapped + r.untapped }), { count: 0, power: 0, untapped: 0 });
  return (
    <table className="shortcuts tm-table" data-testid="tm-census">
      <thead><tr><th>Token</th><th>Count</th><th>Untapped</th><th>Power</th></tr></thead>
      <tbody>
        {rows.map((r) => <tr key={r.name}><td>{r.name}</td><td>{fmt(r.count)}</td><td>{fmt(r.untapped)}</td><td>{fmt(r.power)}</td></tr>)}
        <tr className="tm-total-row"><td>All tokens</td><td>{fmt(all.count)}</td><td>{fmt(all.untapped)}</td><td>{fmt(all.power)}</td></tr>
      </tbody>
    </table>
  );
}
