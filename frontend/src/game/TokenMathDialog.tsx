import { useEffect, useMemo, useState } from "react";
import { Modal } from "../components/Modal";
import { requestCards, useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible } from "../types/game";
import { keyLabel } from "./hotkeys";
import {
  SLOW_OBJECTS, SLOW_TRIGGERS, createTokens, creatureCensus, factorFor, fmt, landsUntil, project, readBoard, selfCopyGrowth, tokenCensus, totals,
  type Board, type TokenFactor,
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

  const ids = useMemo(() => {
    const out: string[] = [];
    if (!view) return out;
    for (const [zone, zids] of Object.entries(view.zones)) {
      if (!zone.endsWith(":battlefield") || !Array.isArray(zids)) continue;
      for (const id of zids) {
        const c = view.cards[id];
        if (c && isVisible(c) && c.card_id) out.push(c.card_id);
      }
    }
    return out;
  }, [view]);
  useEffect(() => requestCards(ids), [ids]);

  const read = useMemo(() => (view ? readBoard(view, player, (id) => cache[id]) : null), [view, player, cache]);
  if (!view || !read) return null;

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
  const key = keyLabel("token_math", keymap);
  const name = view.players.find((p) => p.id === player)?.name ?? "";

  return (
    <Modal title="Token math" wide onClose={onClose}
      footer={<>
        <span className="hint">Only you see this: it reads the public board and sends nothing.{key ? ` ${key} opens and closes it.` : ""}</span>
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

      <Multipliers board={board} read={read} factorC={factorC} factorO={factorO} />

      {tab !== "board" && (
        <div className="tm-row">
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
        </div>
      )}

      {tab === "landfall" && (
        <LandfallTab board={board} enter={enter} setEnter={setEnter} together={together} setTogether={setTogether}
          skip={skip} setSkip={setSkip} target={target} setTarget={setTarget} automation={automation}
          setLandNames={(n) => set({ landNames: n })} />
      )}
      {tab === "copies" && (
        <CopiesTab board={board} make={make} setMake={setMake} creature={makeCreature} setCreature={setMakeCreature}
          rounds={rounds} setRounds={setRounds} factorC={factorC} automation={automation}
          census={creatureCensus(view, player, (id) => cache[id])}
          biovisionaries={countNamed(view, player, "Biovisionary")} />
      )}
      {tab === "board" && <BoardTab rows={tokenCensus(view, player)} name={name} />}
    </Modal>
  );
}

function countNamed(view: NonNullable<ReturnType<typeof useGame.getState>["view"]>, player: string, name: string): number {
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
      <span className="tm-mult-head">Each creation: <b>×{fmt(factorC)}</b> creature tokens{factorO !== factorC ? <>, <b>×{fmt(factorO)}</b> other tokens</> : null}</span>
      {chips.length === 0 && <span className="hint">No token or trigger doublers on this board.</span>}
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

function LandfallTab({ board, enter, setEnter, together, setTogether, skip, setSkip, target, setTarget, automation, setLandNames }: {
  board: Board; enter: number; setEnter: (n: number) => void; together: boolean; setTogether: (b: boolean) => void;
  skip: string[]; setSkip: (s: string[]) => void; target: number; setTarget: (n: number) => void; automation: boolean; setLandNames: (n: number) => void;
}) {
  const steps = project(board, { lands: enter, together, skip });
  const sum = totals(steps);
  const last = steps.at(-1);
  const until = landsUntil(board, target);
  const otherLabels = [...new Set(steps.flatMap((s) => Object.keys(s.tokens)))];
  const objects = sum.newSwarms + sum.insects + sum.extra + Object.values(sum.tokens).reduce((a, b) => a + b, 0);
  const hasPlants = board.makers.some((m) => m.kind === "plant_counters");
  const hasTifa = board.makers.some((m) => m.kind === "double_power");
  const shown = steps.length > 40 ? [...steps.slice(0, 20), null, ...steps.slice(-19)] : steps;
  return (
    <>
      <div className="tm-row">
        <NumberField label="Lands entering" value={enter} min={1} max={together ? 500 : 60} onChange={setEnter} testId="tm-enter" />
        <div className="seg" role="group" aria-label="How they enter">
          <button className={!together ? "on" : ""} onClick={() => setTogether(false)} data-testid="tm-one-at-a-time" title="Land drops, fetch lands, Azusa: each land resolves before the next">One at a time</button>
          <button className={together ? "on" : ""} onClick={() => setTogether(true)} data-testid="tm-all-at-once" title="Lumra, Scapeshift, Splendid Reclamation: every land enters in one event">All at once</button>
        </div>
      </div>
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
              <td>{together ? `${s.entered} lands` : `#${steps.indexOf(s) + 1}`}</td>
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
      <p className="tm-sum" data-testid="tm-total">
        In all: <b>{fmt(sum.triggers)}</b> triggers
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
        <div className="tm-row">
          <NumberField label="Swarms wanted" value={target} min={1} onChange={setTarget} testId="tm-target" />
          <span data-testid="tm-until">{until === null ? "Out of reach one land at a time." : until === 0 ? "You're there." : `${until} more land${until > 1 ? "s" : ""}, one at a time.`}</span>
        </div>
      )}
      <SlowNote triggers={Math.max(0, ...steps.map((s) => s.triggers))} objects={objects} automation={automation} />
      <p className="hint">
        Each land is one landfall event (603.2c): lands entering together trigger every Scute Swarm once per land, but the copies they make
        weren't there yet and don't trigger (603.10). One at a time, the copies trigger on the next land, so the count grows exponentially.
        Six lands is checked as each trigger resolves.
      </p>
    </>
  );
}

function CopiesTab({ board, make, setMake, creature, setCreature, rounds, setRounds, factorC, automation, census, biovisionaries }: {
  board: Board; make: number; setMake: (n: number) => void; creature: boolean; setCreature: (b: boolean) => void;
  rounds: number; setRounds: (n: number) => void; factorC: number; automation: boolean;
  census: { count: number; power: number; untapped: number; untappedPower: number }; biovisionaries: number;
}) {
  const made = createTokens(make, creature, board.factors, board.extras.length);
  const hoofX = census.count + 1;
  return (
    <>
      <h3 className="help-section">Create tokens or copies</h3>
      <div className="tm-row">
        <NumberField label="Tokens (or copies)" value={make} min={1} onChange={setMake} testId="tm-make" title="Rite of Replication kicked: 5. Doppelgang X=3: 9 (3 copies of each of 3)." />
        <label className="field inline"><input type="checkbox" checked={creature} onChange={(e) => setCreature(e.target.checked)} /> creature tokens</label>
        <span className="tm-big" data-testid="tm-made">→ {fmt(made.tokens)}{made.extra ? ` + ${fmt(made.extra)} Squirrels` : ""}</span>
      </div>
      <SlowNote triggers={0} objects={made.tokens + made.extra} automation={automation} />

      <h3 className="help-section">Cards that copy themselves</h3>
      {board.copiers.length === 0 ? (
        <p className="hint">None on this board. Biowaste Blob, Council of Reeds and Giant Adephage show up here: every copy has the ability too.</p>
      ) : (
        <>
          <div className="tm-row"><NumberField label="Rounds" value={rounds} min={1} max={20} onChange={setRounds} testId="tm-rounds" /></div>
          <table className="shortcuts tm-table" data-testid="tm-copiers">
            <thead><tr><th>Card</th><th>Now</th>{Array.from({ length: rounds }, (_, i) => <th key={i}>{i + 1}</th>)}</tr></thead>
            <tbody>
              {board.copiers.map((c) => (
                <tr key={c.name} title={`Triggers ${c.when}`}>
                  <td>{c.name}<br /><small className="hint">{c.when}</small></td>
                  <td>{c.count}</td>
                  {selfCopyGrowth(c.count, factorC, rounds).map((n, i) => <td key={i}>{fmt(n)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3 className="help-section">Swing</h3>
      <p data-testid="tm-swing">
        {fmt(census.count)} creatures, {fmt(census.untappedPower)} power untapped ({fmt(census.power)} in all).
        {" "}With Craterhoof Behemoth entering: X = {fmt(hoofX)}, so the untapped creatures plus Craterhoof hit for <b>{fmt(census.untappedPower + 5 + (census.untapped + 1) * hoofX)}</b> (all trample, if they can all attack).
      </p>
      {biovisionaries > 0 && <p data-testid="tm-biovisionary">Biovisionary: {biovisionaries} of 4 {biovisionaries >= 4 ? "— you win at the beginning of the end step." : ""}</p>}
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
