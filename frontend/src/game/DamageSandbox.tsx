import { useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import { toastError } from "../components/Toasts";
import { ApiError } from "../services/api";
import { SANDBOX_KEYWORDS, runSandbox, sandboxBoard, type SandboxKeyword, type SandboxResult, type ScenarioCreature } from "../services/spectate";
import {
  attackTargets,
  blockTargets,
  describeResult,
  fromBoard,
  patchCreature,
  patchPlayer,
  setAttack,
  setBlock,
  toScenario,
  type SandboxState,
} from "./spectate";

const SHORT: Record<SandboxKeyword, string> = {
  "first strike": "First strike", "double strike": "Double strike", trample: "Trample", deathtouch: "Deathtouch",
  lifelink: "Lifelink", indestructible: "Indestructible", infect: "Infect", wither: "Wither",
};

let customId = 0;

/**
 * DAMAGE SANDBOX (docs/SPECTATOR_ACTIVITIES_MILESTONE.md §4): "was that attack actually lethal?". It starts from the public
 * board with its current combat (only what everyone can see: a face-down creature is a nameless 2/2), lets you change
 * attackers, blockers, power, toughness, keywords and life, and the server works the combat out with the rules engine's own
 * damage computation on a throwaway table. Informational only: it never sends a game action.
 */
export function DamageSandbox({ gameId, viewer, onClose }: { gameId: string; viewer?: string; onClose: () => void }) {
  const [st, setSt] = useState<SandboxState | null>(null);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [combatOnly, setCombatOnly] = useState(false);
  const asked = useRef(0);

  const copyBoard = () => {
    sandboxBoard(gameId, viewer).then((b) => {
      const next = fromBoard(b);
      setSt(next);
      setCombatOnly(next.creatures.some((c) => c.attacking));
    }, (e) => {
      toastError(e);
      onClose();
    });
  };
  useEffect(copyBoard, [gameId, viewer]); // eslint-disable-line react-hooks/exhaustive-deps

  // work it out again shortly after each change (one request for a burst of edits)
  useEffect(() => {
    if (!st) return;
    const scenario = toScenario(st);
    if (!scenario.creatures.some((c) => c.attacking)) {
      setResult(null);
      setProblem(null);
      return;
    }
    const n = ++asked.current;
    const t = window.setTimeout(() => {
      runSandbox(gameId, scenario, viewer).then((r) => {
        if (n !== asked.current) return;
        setResult(r);
        setProblem(null);
      }, (e) => {
        if (n !== asked.current) return;
        setResult(null);
        setProblem(e instanceof ApiError ? e.message : String(e));
      });
    }, 300);
    return () => window.clearTimeout(t);
  }, [st, gameId, viewer]);

  const text = useMemo(() => (st && result ? describeResult(st, result) : null), [st, result]);
  const addCreature = () => {
    if (!st?.players.length) return;
    const id = `sandbox-${++customId}`;
    const c: ScenarioCreature = { id, name: "Creature", controller: st.players[0]!.id, power: 2, toughness: 2, damage: 0, keywords: [],
      commander: null, attacking: null, blocking: null };
    setSt({ ...st, creatures: [...st.creatures, c] });
    setCombatOnly(false);
  };

  return (
    <Modal wide title="Damage sandbox" onClose={onClose} footer={
      <>
        <span className="sandbox-label">Sandbox — does not affect the live game</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={copyBoard} title="Start again from the public board and its current combat">Copy current public combat</button>
        <button className="tt-btn" onClick={addCreature} disabled={!st}>Add creature</button>
        <button className="tt-btn brass" onClick={onClose}>Done</button>
      </>
    }>
      {!st ? <p className="hint">Reading the public board…</p> : (
        <div className="sandbox" data-testid="damage-sandbox">
          <p className="hint">Only what everyone at the table can see. It doesn't guess at tricks, prevention or triggers.</p>
          <div className="sandbox-players">
            {st.players.map((p) => (
              <label key={p.id} className="sandbox-player">
                <b>{p.name}</b>
                <span>Life <input type="number" value={p.life} onChange={(e) => setSt(patchPlayer(st, p.id, { life: num(e.target.value) }))} /></span>
                <span>Poison <input type="number" min={0} value={p.poison} onChange={(e) => setSt(patchPlayer(st, p.id, { poison: Math.max(0, num(e.target.value)) }))} /></span>
              </label>
            ))}
          </div>
          <label className="check sandbox-filter">
            <input type="checkbox" checked={combatOnly} onChange={(e) => setCombatOnly(e.target.checked)} /> Only creatures in this combat
          </label>
          {st.players.map((p) => {
            const mine = st.creatures.filter((c) => c.controller === p.id && (!combatOnly || c.attacking || c.blocking));
            if (!mine.length) return null;
            return (
              <section key={p.id} className="sandbox-side">
                <h4>{p.name}</h4>
                <ul>{mine.map((c) => <CreatureRow key={c.id} st={st} c={c} onChange={setSt} />)}</ul>
              </section>
            );
          })}
          {!st.creatures.length && <p className="hint">No creatures on the battlefield. Add one to try something out.</p>}
          <div className="sandbox-result" aria-live="polite">
            {problem ? <p className="warn">{problem}</p> : !text ? (
              <p className="hint">Choose attackers (and blockers) to see the damage.</p>
            ) : (
              <>
                {text.losers.map((l) => <p key={l} className="sandbox-lethal">{l}</p>)}
                {text.rounds.map((r) => (
                  <div key={r.label}><b>{r.label}</b><ul>{r.lines.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
                ))}
                <ul>{text.players.map((l) => <li key={l}>{l}</li>)}</ul>
                {text.creatures.length > 0 && <ul>{text.creatures.map((l) => <li key={l}>{l}</li>)}</ul>}
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function num(v: string): number {
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? Math.max(-999, Math.min(9999, n)) : 0;
}

function CreatureRow({ st, c, onChange }: { st: SandboxState; c: ScenarioCreature; onChange: (s: SandboxState) => void }) {
  const targets = attackTargets(st, c);
  const blocks = blockTargets(st, c);
  const role = c.attacking ? `attack:${c.attacking}` : c.blocking ? `block:${c.blocking}` : "";
  const custom = c.id.startsWith("sandbox-");
  const setRole = (v: string) => {
    if (!v) onChange(setBlock(setAttack(st, c.id, null), c.id, null));
    else if (v.startsWith("attack:")) onChange(setAttack(st, c.id, v.slice(7)));
    else onChange(setBlock(st, c.id, v.slice(6)));
  };
  return (
    <li className={`sandbox-creature ${c.attacking ? "attacking" : c.blocking ? "blocking" : ""}`}>
      {custom ? (
        <input className="sandbox-name" value={c.name} maxLength={80} aria-label="Name" onChange={(e) => onChange(patchCreature(st, c.id, { name: e.target.value }))} />
      ) : (
        <span className="sandbox-name">{c.name}{c.commander ? <span className="sandbox-tag">Commander</span> : null}</span>
      )}
      <span className="sandbox-pt">
        <input type="number" aria-label="Power" value={c.power} onChange={(e) => onChange(patchCreature(st, c.id, { power: num(e.target.value) }))} />/
        <input type="number" aria-label="Toughness" value={c.toughness} onChange={(e) => onChange(patchCreature(st, c.id, { toughness: num(e.target.value) }))} />
      </span>
      {custom && (
        <select aria-label="Controller" value={c.controller} onChange={(e) => onChange(patchCreature(st, c.id, { controller: e.target.value, attacking: null, blocking: null }))}>
          {st.players.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <select aria-label="In combat" value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="">Not in combat</option>
        {targets.map((p) => <option key={p.id} value={`attack:${p.id}`}>Attacks {p.name}</option>)}
        {blocks.map((a) => <option key={a.id} value={`block:${a.id}`}>Blocks {a.name}</option>)}
      </select>
      <span className="sandbox-keywords" role="group" aria-label="Keywords">
        {SANDBOX_KEYWORDS.map((k) => {
          const on = c.keywords.includes(k);
          return (
            <button key={k} type="button" className={`sandbox-kw ${on ? "on" : ""}`} aria-pressed={on}
              onClick={() => onChange(patchCreature(st, c.id, { keywords: on ? c.keywords.filter((x) => x !== k) : [...c.keywords, k] }))}>
              {SHORT[k]}
            </button>
          );
        })}
      </span>
      {c.damage > 0 && <span className="hint">{c.damage} damage marked</span>}
    </li>
  );
}
