/**
 * The automation UX on the 2D table (docs/AUTOMATION_UX.md): a compact status HUD
 * (AUTO / RESP / MANA), the priority bar with PASS and the stack fast controls, the prompt panel
 * for every kind of decision, the numbered STACK helper, and the AUTOMATION ERROR panel.
 * Everything here reads `view.rules`; the server decides, the client only asks and shows.
 */
import { useState } from "react";
import { perspective, playerName, useGame } from "../../state/gameStore";
import { PHASE_LABEL, type DecisionOptionView, type DecisionView, type GameView } from "../../types/game";
import { choose, next, passPriority, PAYMENT_CYCLE, RESPONSE_CYCLE, send, setPrefs } from "./intents";

function useRules() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  if (!view) return null;
  const me = perspective(view, actingAs);
  const isHost = view.game.mode === "local" || view.game.host_seat === view.viewer;
  return { view, rules: view.rules ?? null, me, isHost, seated: view.viewer !== "__spectator__" };
}

/** AUTO: FULL · RESP: AUTO · MANA: ASK — click to change. */
export function AutomationHud() {
  const ctx = useRules();
  const [menu, setMenu] = useState(false);
  if (!ctx) return null;
  const { view, rules, isHost, seated } = ctx;
  const level = rules ? (rules.paused ? "PAUSED" : rules.automation.toUpperCase()) : "OFF";
  const custom = rules?.preset === "custom" ? "*" : "";
  const prefs = rules?.prefs;
  const configure = (patch: Record<string, unknown>) => {
    setMenu(false);
    void send({ type: "configure", ...patch });
  };
  return (
    <div className="auto-hud" data-testid="automation-hud">
      <button className={`auto-pill ${rules && !rules.paused ? "on" : ""}`} data-testid="auto-level"
        title={isHost ? "Automation level (host)" : "Automation level (the host changes it)"}
        onClick={() => isHost && setMenu(!menu)}>
        AUTO: {level}{custom}
      </button>
      {rules && prefs && seated && (
        <>
          <button className="auto-pill" data-testid="resp-mode" title="RESPONSE: when the engine stops for you (click to change)"
            onClick={() => void setPrefs({ response: next(RESPONSE_CYCLE, prefs.response) })}>
            RESP: {prefs.response.toUpperCase()}
          </button>
          <button className="auto-pill" data-testid="mana-mode" title="MANA: how your costs are paid (click to change)"
            onClick={() => void setPrefs({ payment: next(PAYMENT_CYCLE, prefs.payment) })}>
            MANA: {prefs.payment.toUpperCase()}
          </button>
        </>
      )}
      {menu && isHost && (
        <div className="auto-menu" role="menu">
          {(["off", "assisted", "full"] as const).map((lv) => (
            <button key={lv} className={`tt-btn ${rules?.automation === lv || (!rules && lv === "off") ? "on" : "ghost"}`}
              onClick={() => configure({ automation: lv })}>{lv.toUpperCase()}</button>
          ))}
          {rules && (
            <button className="tt-btn ghost" onClick={() => configure({ automation_paused: !rules.paused })}>
              {rules.paused ? "Resume automation" : "Pause automation"}
            </button>
          )}
          <span className="auto-menu-note">OFF keeps everything; turning it back on reconciles with the table.</span>
        </div>
      )}
      {view.rules?.winner && <span className="auto-pill winner">{playerName(view, view.rules.winner)} wins</span>}
    </div>
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

/** STACK — N, top first, with controller and targets. */
export function RulesStack() {
  const ctx = useRules();
  if (!ctx || !ctx.rules || !ctx.view.stack.length) return null;
  const { view } = ctx;
  const ids = [...view.stack].reverse();
  return (
    <div className="rules-stack" data-testid="rules-stack">
      <div className="rules-stack-title">STACK — {ids.length}</div>
      <ol>
        {ids.map((id) => {
          const c = view.cards[id];
          const name = c ? (c.hidden ? "A card" : c.name || "Ability") : "?";
          const targets = (view.arrows ?? []).filter((a) => a.source === id).flatMap((a) => a.targets);
          return (
            <li key={id} data-testid="stack-entry">
              <b>{name}</b>
              <span className="rules-stack-who"> · {c ? playerName(view, c.controller) : ""}</span>
              {targets.length > 0 && <span className="rules-stack-tgt"> → {targets.map((t) => targetName(view, t)).join(", ")}</span>}
              <button className="tt-icon" title="Hold after this resolves" onClick={() => void setPrefs({ stop_after: id })}>⏸</button>
            </li>
          );
        })}
      </ol>
    </div>
  );
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
  return (
    <div className="decision-panel" data-testid="decision-panel" data-kind={d.kind}>
      <div className="decision-prompt">{d.prompt}</div>
      <DecisionBody key={d.id} d={d} view={view} />
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
  if (!d || d.player !== me || d.kind !== "choose_one" || !d.options) return false;
  const opt = d.options.find((o) => o.id === cardOrPlayer || o.card_id === cardOrPlayer);
  if (!opt) return false;
  void choose(d.id, [opt.id]);
  return true;
}
