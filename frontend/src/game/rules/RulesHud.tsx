/**
 * The automation UX on the 2D table (docs/AUTOMATION_UX.md): a compact status HUD
 * (AUTO / RESP / MANA), the priority bar with PASS and the stack fast controls, the prompt panel
 * for every kind of decision, the numbered STACK helper, and the AUTOMATION ERROR panel.
 * Everything here reads `view.rules`; the server decides, the client only asks and shows.
 */
import { useState } from "react";
import { perspective, playerName, useGame } from "../../state/gameStore";
import { PHASE_LABEL, type DecisionOptionView, type DecisionView, type GameView } from "../../types/game";
import { choose, next, passPriority, RESPONSE_CYCLE, send, setPrefs, tapForMana } from "./intents";
import { GameCardFace } from "../GameCardFace";
import { ManaText } from "../../cards/ManaText";
import { useCardCache } from "../../state/cardCache";

function useRules() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  if (!view) return null;
  const me = perspective(view, actingAs);
  const isHost = view.game.mode === "local" || view.game.host_seat === view.viewer;
  return { view, rules: view.rules ?? null, me, isHost, seated: view.viewer !== "__spectator__" };
}

/** AUTO: FULL · RESP: AUTO · MANA: ASK — click for the automation settings. */
export function AutomationHud() {
  const ctx = useRules();
  const [open, setOpen] = useState(false);
  if (!ctx) return null;
  const { view, rules, seated } = ctx;
  const level = rules ? (rules.paused ? "PAUSED" : rules.automation.toUpperCase()) : "OFF";
  const custom = rules?.preset === "custom" ? "*" : "";
  const prefs = rules?.prefs;
  return (
    <div className="auto-hud" data-testid="automation-hud">
      <button className={`auto-pill ${rules && !rules.paused ? "on" : ""}`} data-testid="auto-level" title="Automation settings" onClick={() => setOpen(!open)}>
        AUTO: {level}{custom}
      </button>
      {rules && prefs && seated && (
        <>
          <button className="auto-pill" data-testid="resp-mode" title="RESPONSE: when the engine stops for you (click to change)"
            onClick={() => void setPrefs({ response: next(RESPONSE_CYCLE, prefs.response) })}>
            RESP: {prefs.response.toUpperCase()}
          </button>
        </>
      )}
      {open && <AutomationSettings onClose={() => setOpen(false)} />}
      {view.rules?.winner && <span className="auto-pill winner">{playerName(view, view.rules.winner)} wins</span>}
    </div>
  );
}

const STOP_STEPS = ["upkeep", "draw", "main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "main2", "end"] as const;

/** The automation panel: level (host), RESPONSE, MANA and where the engine stops for you. */
export function AutomationSettings({ onClose }: { onClose: () => void }) {
  const ctx = useRules();
  if (!ctx) return null;
  const { rules, isHost, seated } = ctx;
  const prefs = rules?.prefs;
  const level = rules?.automation ?? "off";
  const configure = (patch: Record<string, unknown>) => void send({ type: "configure", ...patch });
  const toggleStop = (key: "stops_my_turn" | "stops_their_turn", step: string) => {
    if (!prefs) return;
    const cur = prefs[key];
    void setPrefs({ [key]: cur.includes(step) ? cur.filter((x) => x !== step) : [...cur, step] });
  };
  return (
    <div className="auto-settings frame ornate" role="dialog" aria-label="Automation settings" data-testid="automation-settings">
      <div className="auto-settings-head">
        <span className="frame-title">Automation</span>
        <button className="tt-icon" aria-label="Close" onClick={onClose}>✕</button>
      </div>
      <div className="segmented" role="radiogroup" aria-label="Automation level">
        {(["off", "assisted", "full"] as const).map((lv) => (
          <button key={lv} className={level === lv ? "on" : ""} disabled={!isHost} data-testid={`level-${lv}`} onClick={() => configure({ automation: lv })}
            title={isHost ? undefined : "The host sets the automation level"}>{lv === "off" ? "Off" : lv === "assisted" ? "Assisted" : "Full"}</button>
        ))}
      </div>
      {isHost && rules && (
        <button className="tt-link auto-pause" onClick={() => configure({ automation_paused: !rules.paused })}>
          {rules.paused ? "Resume automation" : "Pause automation"}
        </button>
      )}
      {rules && prefs && seated && (
        <>
          <span className="frame-title">Responses</span>
          <div className="segmented blue">
            {RESPONSE_CYCLE.map((m) => (
              <button key={m} className={prefs.response === m ? "on" : ""} onClick={() => void setPrefs({ response: m })}>{m[0]!.toUpperCase() + m.slice(1)}</button>
            ))}
          </div>
          <span className="frame-title">Mana</span>
          <div className="hint" data-testid="mana-rule">You tap your own lands for mana; costs are paid from your mana pool. Fyodor never taps them for you.</div>
          <span className="frame-title">Stops</span>
          <div className="stop-grid">
            <span />
            {STOP_STEPS.map((st) => <span key={st} className="stop-step">{PHASE_LABEL[st]}</span>)}
            <span className="stop-row">My turn</span>
            {STOP_STEPS.map((st) => (
              <button key={st} className={`stop-cell ${prefs.stops_my_turn.includes(st) ? "on" : ""}`} aria-label={`Stop in my ${PHASE_LABEL[st]}`}
                onClick={() => toggleStop("stops_my_turn", st)} />
            ))}
            <span className="stop-row">Others</span>
            {STOP_STEPS.map((st) => (
              <button key={st} className={`stop-cell ${prefs.stops_their_turn.includes(st) ? "on" : ""}`} aria-label={`Stop in opponents' ${PHASE_LABEL[st]}`}
                onClick={() => toggleStop("stops_their_turn", st)} />
            ))}
          </div>
          <div className="auto-switches">
            <Switch label="Hold priority after I cast" on={prefs.hold_priority} set={(v) => void setPrefs({ hold_priority: v })} />
            <Switch label="Full control (never pass for me)" on={prefs.full_control} set={(v) => void setPrefs({ full_control: v })} />
            <Switch label="Bluff stops" on={prefs.bluff_stops} set={(v) => void setPrefs({ bluff_stops: v })} />
            <Switch label="Auto-order identical triggers" on={prefs.auto_order_identical_triggers} set={(v) => void setPrefs({ auto_order_identical_triggers: v })} />
          </div>
        </>
      )}
      {!rules && <p className="hint">Automation is off: the table is a sandbox. {isHost ? "Choose Assisted or Full to let Fyodor enforce the rules." : "The host can turn it on."}</p>}
    </div>
  );
}

function Switch({ label, on, set }: { label: string; on: boolean; set: (v: boolean) => void }) {
  return (
    <label className="switch-row">
      <span>{label}</span>
      <span className="switch"><input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} /><span /></span>
    </label>
  );
}

/** Whose priority it is, PASS, and the stack fast controls. */
export function PriorityBar() {
  const ctx = useRules();
  if (!ctx || !ctx.rules || !ctx.seated) return null;
  const { view, rules, me } = ctx;
  if (rules.paused || rules.conceded.includes(me) || me in rules.lost) return null;
  const mine = rules.priority === me && !rules.decision;
  const prefs = rules.prefs;
  const stack = view.stack.length > 0;
  const holder = rules.priority ? playerName(view, rules.priority) : null;
  const phase = PHASE_LABEL[view.turn.phase] ?? view.turn.phase;
  return (
    <div className={`prio-bar ${mine ? "mine" : ""}`} data-testid="priority-bar">
      <span className="prio-where">{phase}</span>
      <span className="prio-who" data-testid="priority-holder">
        {rules.decision ? `${playerName(view, rules.decision.player)} is deciding` : mine ? "Your priority" : holder ? `${holder}'s priority` : ""}
      </span>
      {mine && (
        <>
          <button className="tt-btn brass" data-testid="pass-priority" title="Space" onClick={() => void passPriority()}>
            {stack ? "Pass" : "Next"}
          </button>
          {stack && <button className="tt-btn ghost" data-testid="resolve-one" onClick={() => void passPriority("stack_changes")}>Resolve one</button>}
          {stack && <button className="tt-btn ghost" data-testid="resolve-all" onClick={() => void passPriority("stack_empty")}>Resolve all</button>}
          {!stack && <button className="tt-btn ghost" data-testid="pass-turn" onClick={() => void passPriority("next_turn")}>End turn</button>}
        </>
      )}
      {prefs?.pass_until && (
        <button className="tt-btn ghost" data-testid="cancel-pass" onClick={() => void setPrefs({ cancel_pass: true })}>
          Passing until {prefs.pass_until.replace("_", " ")} · cancel
        </button>
      )}
      {prefs && (
        <>
          <button className={`tt-btn ${prefs.hold_priority ? "on" : "ghost"}`} data-testid="hold-priority" title="Keep priority after you cast"
            onClick={() => void setPrefs({ hold_priority: !prefs.hold_priority })}>Hold</button>
          <button className={`tt-btn ${prefs.full_control ? "on" : "ghost"}`} data-testid="full-control" title="No auto-passing at all"
            onClick={() => void setPrefs({ full_control: !prefs.full_control })}>Full control</button>
          {!mine && (
            <button className={`tt-btn ${prefs.force_stop ? "on" : "ghost"}`} data-testid="force-stop" title="Stop at your next priority"
              onClick={() => void setPrefs({ force_stop: !prefs.force_stop })}>Stop</button>
          )}
        </>
      )}
    </div>
  );
}

/** The Stack: most recent on top, with controller and targets; Pass / Respond / Auto-pass. */
export function RulesStack() {
  const ctx = useRules();
  const [responding, setResponding] = useState<string | null>(null);
  if (!ctx || !ctx.rules || !ctx.view.stack.length) return null;
  const { view, rules, me } = ctx;
  const ids = [...view.stack].reverse();
  const mine = rules.priority === me && !rules.decision;
  const top = ids[0] ?? "";
  return (
    <div className="rules-stack frame" data-testid="rules-stack">
      <div className="rules-stack-title">The Stack <span className="rules-stack-count">{ids.length}</span></div>
      <ol>
        {ids.map((id, i) => {
          const c = view.cards[id];
          const name = c ? (c.hidden ? "A card" : c.name || "Ability") : "?";
          const kind = c && !c.hidden ? (c.ability ? `${c.ability.kind === "triggered" ? "Triggered" : "Activated"} ability` : stackTypeLine(c.card_id)) : "";
          const targets = (view.arrows ?? []).filter((a) => a.source === id).flatMap((a) => a.targets);
          return (
            <li key={id} data-testid="stack-entry" className={i === 0 ? "top" : ""} onPointerEnter={() => useGame.getState().setHover(id)} onPointerLeave={() => useGame.getState().setHover(null)}>
              <span className="rules-stack-thumb">{c && <GameCardFace card={c} size="small" />}</span>
              <span className="rules-stack-body">
                <b>{name}</b>
                <span className="rules-stack-who">{c ? playerName(view, c.controller) : ""}{kind ? ` · ${kind}` : ""}</span>
                {targets.length > 0 && <span className="rules-stack-tgt">→ {targets.map((t) => targetName(view, t)).join(", ")}</span>}
              </span>
              <button className="tt-icon" title="Hold after this resolves" aria-label="Hold after this resolves" onClick={() => void setPrefs({ stop_after: id })}>❚❚</button>
            </li>
          );
        })}
      </ol>
      {mine && (
        <div className="rules-stack-actions">
          <button className="act-btn" data-testid="stack-pass" onClick={() => void passPriority()}>Pass</button>
          <button className={`act-btn primary ${responding === top ? "on" : ""}`} data-testid="stack-respond"
            title="Keep priority: cast or activate something in response" onClick={() => setResponding(top)}>Respond</button>
          <button className="act-btn green" data-testid="stack-autopass" title="Pass until the stack is empty (you still get every decision)"
            onClick={() => void passPriority("stack_empty")}>Auto-Pass</button>
        </div>
      )}
      {mine && responding === top && <div className="rules-stack-hint">Cast or activate something, then pass.</div>}
    </div>
  );
}

function stackTypeLine(cardId: string | null | undefined): string {
  const data = cardId ? useCardCache.getState().cards[cardId] : undefined;
  return data?.type_line?.split("—")[0]?.trim() ?? "";
}

function targetName(view: GameView, id: string): string {
  if (view.players.some((p) => p.id === id)) return playerName(view, id);
  const c = view.cards[id];
  return c && !c.hidden ? c.name : "a card";
}

/** The pending decision: the chooser answers here (or by clicking a highlighted card on the table). */
export function DecisionPanel() {
  const ctx = useRules();
  if (!ctx || !ctx.rules?.decision) return null;
  const { view, me } = ctx;
  const d = ctx.rules.decision;
  if (d.player !== me || !d.options) {
    return (
      <div className="decision-panel waiting" data-testid="decision-waiting">
        {playerName(view, d.player)} is deciding: {d.prompt}
      </div>
    );
  }
  if (d.display?.kind === "payment") return <PaymentPanel key={d.id} d={d} view={view} />;
  if (d.display?.kind === "tap_mana") return <TapManaPanel key={d.id} d={d} view={view} />;
  const targeting = d.kind === "choose_one" && (d.options ?? []).some((o) => o.card_id) && (d.options ?? []).length > 1;
  return (
    <div className={`decision-panel frame ${targeting ? "targeting" : ""}`} data-testid="decision-panel" data-kind={d.kind}>
      <div className="decision-prompt">{d.prompt}</div>
      {targeting && <div className="decision-hint">Click a highlighted card or player on the table, or choose below.</div>}
      <DecisionBody key={d.id} d={d} view={view} />
    </div>
  );
}

/** Pay {3}{W}: the suggested sources, the alternatives, Auto Pay / Edit Payment / Cancel. */
function PaymentPanel({ d, view }: { d: DecisionView; view: GameView }) {
  const info = d.display as unknown as { cost: string; what: string; suggested: string[]; alternatives: string[]; pool: number };
  const [always, setAlways] = useState(false);
  const pay = () => {
    if (always) void setPrefs({ payment: "auto" });
    void choose(d.id, ["pay"]);
  };
  const thumbs = (ids: string[], picked: boolean) => ids.map((id) => {
    const c = view.cards[id];
    return c ? (
      <span key={id} className={`pay-thumb ${picked ? "picked" : ""}`} title={c.hidden ? "" : c.name}
        onPointerEnter={() => useGame.getState().setHover(id)} onPointerLeave={() => useGame.getState().setHover(null)}>
        <GameCardFace card={c} size="small" />
      </span>
    ) : null;
  });
  return (
    <div className="decision-panel payment frame ornate" data-testid="decision-panel" data-kind="payment">
      <div className="pay-head">
        <span className="pay-title">Pay</span>
        <span className="pay-cost"><ManaText text={info.cost} /></span>
      </div>
      <div className="pay-what">for {info.what}</div>
      <div className="frame-title">Recommended payment</div>
      <div className="pay-row">
        {thumbs(info.suggested, true)}
        {info.pool > 0 && <span className="pay-pool">+{info.pool} from your mana pool</span>}
        {!info.suggested.length && !info.pool && <span className="hint">Nothing to tap.</span>}
        <span className="pay-check" aria-hidden>✓</span>
      </div>
      {info.alternatives.length > 0 && (
        <>
          <div className="frame-title">Other sources</div>
          <div className="pay-row alt">{thumbs(info.alternatives, false)}</div>
        </>
      )}
      <label className="check pay-always"><input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} /> Always auto-pay with the best sources (MANA: AUTO)</label>
      <div className="pay-actions">
        <button className="act-btn primary" data-testid="option-pay" onClick={pay}>Auto Pay</button>
        <button className="act-btn" data-testid="option-manual" onClick={() => void choose(d.id, ["manual"])}>Edit Payment</button>
        <button className="act-btn red" data-testid="option-cancel" onClick={() => void choose(d.id, ["cancel"])}>Cancel</button>
      </div>
    </div>
  );
}

/** Pay {1}{G}: tap your own lands (click them on the table); it goes on once your pool covers it. */
function TapManaPanel({ d, view }: { d: DecisionView; view: GameView }) {
  const info = d.display as unknown as { cost: string; what: string; sources: string[]; pool: Record<string, number> };
  const untapped = info.sources.filter((id) => view.cards[id] && !view.cards[id]!.tapped);
  const pool = Object.entries(info.pool ?? {}).filter(([, n]) => n > 0).map(([m, n]) => `{${m}}`.repeat(n)).join("");
  return (
    <div className="decision-panel payment tap-mana frame ornate" data-testid="decision-panel" data-kind="tap_mana">
      <div className="pay-head">
        <span className="pay-title">Pay</span>
        <span className="pay-cost"><ManaText text={info.cost} /></span>
      </div>
      <div className="pay-what">for {info.what}</div>
      <div className="decision-hint">Tap your lands and mana sources: click a highlighted card on the table (or below).</div>
      <div className="pay-row">
        <span className="pay-pool" data-testid="tap-pool">Mana pool: {pool ? <ManaText text={pool} /> : "empty"}</span>
      </div>
      {untapped.length > 0 && (
        <div className="pay-row alt">
          {untapped.map((id) => (
            <button key={id} className="pay-thumb" title="Tap for mana" data-testid={`tap-source-${id}`}
              onClick={() => tapForMana(id)} onPointerEnter={() => useGame.getState().setHover(id)} onPointerLeave={() => useGame.getState().setHover(null)}>
              <GameCardFace card={view.cards[id]!} size="small" />
            </button>
          ))}
        </div>
      )}
      <div className="pay-actions two">
        <button className="act-btn primary" data-testid="option-pay" onClick={() => void choose(d.id, ["pay"])}>Pay</button>
        <button className="act-btn red" data-testid="option-cancel" onClick={() => void choose(d.id, ["cancel"])}>Cancel</button>
      </div>
    </div>
  );
}

function DecisionBody({ d, view }: { d: DecisionView; view: GameView }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [remember, setRemember] = useState<string>("");
  const options = d.options ?? [];
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const done = (ids: string[]) => void choose(d.id, ids, remember || undefined);
  const min = d.min_choices ?? 1;
  const max = d.max_choices ?? 1;

  if (d.kind === "declare_attackers") return <DeclareAttackers d={d} />;
  if (d.kind === "declare_blockers") return <DeclareBlockers d={d} />;
  if (d.kind === "choose_one" || d.kind === "confirm" || d.kind === "manual_resolution") {
    return (
      <div className="decision-options">
        {options.map((o) => (
          <button key={o.id} className="tt-btn" data-testid={`option-${o.id}`} onClick={() => done([o.id])}>{o.label}</button>
        ))}
        {d.rememberable && (
          <select className="decision-remember" data-testid="remember" value={remember} onChange={(e) => setRemember(e.target.value)}>
            <option value="">Ask me every time</option>
            <option value="yes_this_turn">Same answer this turn</option>
            <option value="always_yield">Always</option>
          </select>
        )}
      </div>
    );
  }
  if (d.kind === "order") {
    return (
      <div className="decision-options">
        {options.map((o) => (
          <button key={o.id} className={`tt-btn ${picked.includes(o.id) ? "on" : "ghost"}`} onClick={() => toggle(o.id)}>
            {picked.includes(o.id) ? `${picked.indexOf(o.id) + 1}. ` : ""}{o.label}
          </button>
        ))}
        <button className="tt-btn brass" disabled={picked.length !== options.length} data-testid="decision-done" onClick={() => done(picked)}>Done</button>
      </div>
    );
  }
  if (d.kind === "reconcile") return <Reconcile d={d} />;
  // choose_cards
  return (
    <div className="decision-options">
      {options.map((o) => (
        <button key={o.id} className={`tt-btn ${picked.includes(o.id) ? "on" : "ghost"}`} data-testid={`option-${o.id}`}
          onClick={() => toggle(o.id)}>{optionLabel(o, view)}</button>
      ))}
      <button className="tt-btn brass" data-testid="decision-done" disabled={picked.length < min || picked.length > max} onClick={() => done(picked)}>
        Done{max > 1 ? ` (${picked.length})` : ""}
      </button>
    </div>
  );
}

function optionLabel(o: DecisionOptionView, view: GameView): string {
  const c = o.card_id ? view.cards[o.card_id] : null;
  return c && !c.hidden && c.name ? c.name : o.label;
}

function Reconcile({ d }: { d: DecisionView }) {
  const groups = new Map<string, DecisionOptionView[]>();
  for (const o of d.options ?? []) groups.set(o.group ?? o.id, [...(groups.get(o.group ?? o.id) ?? []), o]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const questions = useGame((s) => s.view?.rules?.reconcile ?? []);
  return (
    <div className="decision-reconcile">
      {[...groups.entries()].map(([group, opts]) => (
        <div key={group} className="reconcile-q">
          <span>{questions.find((q) => q.id === group)?.question ?? group}</span>
          {opts.map((o) => (
            <button key={o.id} className={`tt-btn ${answers[group] === o.id ? "on" : "ghost"}`} onClick={() => setAnswers({ ...answers, [group]: o.id })}>
              {o.label}
            </button>
          ))}
        </div>
      ))}
      <button className="tt-btn brass" data-testid="decision-done" disabled={Object.keys(answers).length !== groups.size}
        onClick={() => void choose(d.id, Object.values(answers))}>Done</button>
    </div>
  );
}

function DeclareAttackers({ d }: { d: DecisionView }) {
  const opts = d.options ?? [];
  const attackers = opts.filter((o) => o.id.startsWith("a:"));
  const targets = opts.filter((o) => o.id.startsWith("t:"));
  const [plan, setPlan] = useState<Record<string, string>>({});
  const set = (a: string, t: string) => setPlan((p) => {
    const nextPlan = { ...p };
    if (!t) delete nextPlan[a];
    else nextPlan[a] = t;
    return nextPlan;
  });
  const declare = () => void send({
    type: "declare_attackers",
    attackers: Object.entries(plan).map(([a, t]) => ({ card_id: a.slice(2), target: t.slice(2) })),
  });
  return (
    <div className="decision-combat">
      {attackers.map((a) => (
        <label key={a.id} className="combat-row">
          <span>{a.label}</span>
          <select data-testid={`attack-${a.id.slice(2)}`} value={plan[a.id] ?? ""} onChange={(e) => set(a.id, e.target.value)}>
            <option value="">Doesn't attack</option>
            {targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </label>
      ))}
      <div className="decision-options">
        {targets.length === 1 && (
          <button className="tt-btn ghost" onClick={() => setPlan(Object.fromEntries(attackers.map((a) => [a.id, targets[0]!.id])))}>All attack</button>
        )}
        <button className="tt-btn brass" data-testid="declare-attackers" onClick={declare}>
          {Object.keys(plan).length ? `Attack with ${Object.keys(plan).length}` : "No attack"}
        </button>
      </div>
    </div>
  );
}

function DeclareBlockers({ d }: { d: DecisionView }) {
  const opts = d.options ?? [];
  const blockers = opts.filter((o) => o.id.startsWith("b:"));
  const attackers = opts.filter((o) => o.id.startsWith("a:"));
  const [plan, setPlan] = useState<Record<string, string>>({});
  const declare = () => void send({
    type: "declare_blockers",
    blocks: Object.entries(plan).map(([b, a]) => ({ blocker_id: b.slice(2), attacker_id: a.slice(2) })),
  });
  return (
    <div className="decision-combat">
      {blockers.map((b) => (
        <label key={b.id} className="combat-row">
          <span>{b.label}</span>
          <select data-testid={`block-${b.id.slice(2)}`} value={plan[b.id] ?? ""}
            onChange={(e) => setPlan((p) => { const n = { ...p }; if (e.target.value) n[b.id] = e.target.value; else delete n[b.id]; return n; })}>
            <option value="">Doesn't block</option>
            {attackers.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
      ))}
      <button className="tt-btn brass" data-testid="declare-blockers" onClick={declare}>
        {Object.keys(plan).length ? `Block with ${Object.keys(plan).length}` : "No blocks"}
      </button>
    </div>
  );
}

/** AUTOMATION ERROR: the engine failed on something; nothing changed, the table goes on. */
export function AutomationErrorPanel() {
  const error = useGame((s) => s.automationError);
  const clear = () => useGame.getState().setAutomationError(null);
  const ctx = useRules();
  if (!error || !ctx) return null;
  const { view, isHost } = ctx;
  return (
    <div className="auto-error" role="alertdialog" data-testid="automation-error">
      <div className="auto-error-title">Automation error</div>
      <p>{error.replace(/^AUTOMATION ERROR:\s*/, "")}</p>
      <div className="decision-options">
        <button className="tt-btn brass" data-testid="resolve-manually" onClick={clear}>Resolve manually</button>
        {isHost && view.rules && (
          <button className="tt-btn ghost" data-testid="pause-automation"
            onClick={() => { clear(); void send({ type: "configure", automation_paused: true }); }}>Pause automation</button>
        )}
        <a className="tt-btn ghost" data-testid="export-scenario" href={`/api/games/${view.game.id}/rules/scenario`} download>
          Export rules scenario
        </a>
      </div>
    </div>
  );
}

/** Legal-action highlight class for a card (restrained: a thin warm edge, never neon). */
export function legalClass(view: GameView | null, cardId: string, me: string): string {
  const rules = view?.rules;
  if (!rules || rules.paused || rules.options.highlights === "off") return "";
  const d = rules.decision;
  if (d && d.player === me && d.display?.kind === "tap_mana") {
    const sources = (d.display as { sources?: string[] }).sources ?? [];
    return sources.includes(cardId) && !view?.cards[cardId]?.tapped ? "rules-mana-source" : "";
  }
  if (d && d.player === me && d.options?.some((o) => o.card_id === cardId && (d.kind === "choose_one" || d.kind === "choose_cards"))) {
    return "rules-target";
  }
  const h = rules.hints;
  if (!h.has_priority) return "";
  if (h.playable_lands?.includes(cardId) || h.castable?.includes(cardId)) return "rules-playable";
  if (h.activatable?.some((a) => a.card_id === cardId)) return "rules-activatable";
  return "";
}

/** Clicking a card that the pending choose-one decision offers answers it (click-to-target). */
export function answerByClick(view: GameView | null, cardOrPlayer: string, me: string): boolean {
  const d = view?.rules?.decision;
  if (d && d.player === me && d.display?.kind === "tap_mana") return tapForMana(cardOrPlayer, me);  // click a land to tap it
  if (!d || d.player !== me || d.kind !== "choose_one" || !d.options) return false;
  const opt = d.options.find((o) => o.id === cardOrPlayer || o.card_id === cardOrPlayer);
  if (!opt) return false;
  void choose(d.id, [opt.id]);
  return true;
}
