/**
 * The automation UX on the 2D table (docs/AUTOMATION_UX.md): a compact status HUD
 * (AUTO / RESP / MANA), the priority bar with PASS and the stack fast controls, the prompt panel
 * for every kind of decision, the numbered STACK helper, and the AUTOMATION ERROR panel.
 * Everything here reads `view.rules`; the server decides, the client only asks and shows.
 */
import { useState } from "react";
import { openMenu } from "../../components/ContextMenu";
import { perspective, playerName, useGame } from "../../state/gameStore";
import { PHASE_LABEL, PHASES, type PhaseName, type DecisionOptionView, type DecisionView, type GameView } from "../../types/game";
import { autocomplete } from "../../services/cards";
import { canConcede, choose, chooseName, concede, delveCard, divide, next, passPriority, payWith, RESPONSE_CYCLE, send, setPrefs, tapForMana, useXPrompt, submitNumericPrompt } from "./intents";
import { GameCardFace } from "../GameCardFace";
import { ChainRow, chainEntries } from "../StackChain";
import { ManaText } from "../../cards/ManaText";

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
  const [conceding, setConceding] = useState(false);
  if (!ctx) return null;
  const { view, rules, seated, me } = ctx;
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
      {seated && rules?.hints.deferred_payments?.map((window) => (
        <button key={window.id} className="auto-pill" data-testid="pay-deferred"
          disabled={!rules.hints.has_priority || !!rules.decision || rules.paused}
          onClick={() => void send({ type: "pay_deferred", window_id: window.id })}>
          Pay <ManaText text={window.cost} /> to prevent {window.name}
        </button>
      ))}
      {canConcede(view, me) && (conceding ? (
        <span className="auto-pill" data-testid="concede-confirm">
          Concede the game?{" "}
          <button className="tt-btn ghost" data-testid="concede-yes" onClick={() => { setConceding(false); void concede(); }}>Concede</button>
          <button className="tt-btn ghost" data-testid="concede-no" onClick={() => setConceding(false)}>Keep playing</button>
        </span>
      ) : (
        <button className="auto-pill" data-testid="concede" title="Concede the game (any time: CR 104.3a)" onClick={() => setConceding(true)}>
          Concede
        </button>
      ))}
      {open && <AutomationSettings onClose={() => setOpen(false)} />}
      {!!rules?.attacking_bands?.length && (
        <details className="auto-pill" data-testid="attacking-bands">
          <summary>{rules.attacking_bands.length} attacking {rules.attacking_bands.length === 1 ? "band" : "bands"}</summary>
          {rules.attacking_bands.map((band, i) => (
            <div key={i}>Band {i + 1}: {band.map((cid) => { const card = view.cards[cid]; return card && !card.hidden ? card.name : "Creature"; }).join(" + ")}</div>
          ))}
        </details>
      )}
      {view.rules?.draw_reason && <span className="auto-pill winner" title={view.rules.draw_reason}>Draw</span>}
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
            <Switch label="Always let me order my graveyard" on={prefs.ask_graveyard_order} set={(v) => void setPrefs({ ask_graveyard_order: v })} />
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

const STEP_GROUPS: { label: string; steps: PhaseName[] }[] = [
  { label: "Begin", steps: ["untap", "upkeep", "draw"] },
  { label: "Main 1", steps: ["main1"] },
  { label: "Combat", steps: ["begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"] },
  { label: "Main 2", steps: ["main2"] },
  { label: "End", steps: ["end", "cleanup"] },
];

/** What passing priority with an empty stack moves the game to. */
const NEXT_VERB: Record<PhaseName, string> = {
  untap: "To upkeep", upkeep: "To draw step", draw: "To main phase", main1: "To combat", begin_combat: "To attackers",
  declare_attackers: "To blockers", declare_blockers: "To damage", combat_damage: "End combat", end_combat: "To main 2",
  main2: "To end step", end: "End turn", cleanup: "Next turn",
};

/** What someone else's decision is, in a few words ("Waiting for Casey: choosing blockers"). */
const DECIDING: Partial<Record<string, string>> = {
  declare_attackers: "declaring attackers", declare_blockers: "choosing blockers", choose_one: "choosing an option",
  choose_cards: "choosing cards", confirm: "confirming a choice", order: "ordering triggers", divide: "dividing damage",
  manual_resolution: "resolving by hand", reconcile: "checking the board",
};

/**
 * The turn & priority dial, bottom right (Arena / Moxgate): whose turn and which step, who the game
 * is waiting for, and one big button that says what passing will do. With the rules engine off it
 * drives the steps by hand. The server decides; the dial only shows and asks.
 */
export function TurnDial() {
  const ctx = useRules();
  if (!ctx) return null;
  const { view, rules, me } = ctx;
  const turn = view.turn;
  const active = view.players.find((p) => p.id === turn.active_player);
  const step = turn.phase as PhaseName;
  const auto = !!rules && !rules.paused && ctx.seated && !rules.conceded.includes(me) && !(me in rules.lost);
  const mine = auto && !rules!.controlled_by && (rules!.priority === me || (!!rules!.acting_as && rules!.priority === rules!.acting_as)) && !rules!.decision;
  const prefs = rules?.prefs;
  const stack = view.stack.length > 0;
  const top = stack ? view.cards[view.stack[view.stack.length - 1]!] : undefined;
  const topName = top && "name" in top ? top.name : "the top of the stack";
  let status: string;
  const watching = !ctx.seated;
  if (watching) status = "Watching";
  else if (!auto) status = rules?.paused ? "Automation paused: move the steps yourself" : "Manual play: you move the steps";
  else if (rules!.controlled_by) status = `${playerName(view, rules!.controlled_by)} is making your choices`;
  else if (rules!.decision) {
    const d = rules!.decision;
    status = d.player === me ? "Your decision" : `Waiting for ${playerName(view, d.player)}: ${DECIDING[d.kind] ?? "deciding"}`;
  } else if (mine) status = rules!.acting_as ? `Your priority (controlling ${playerName(view, rules!.acting_as)})` : "Your priority";
  else status = rules!.priority ? `Waiting for ${playerName(view, rules!.priority)}` : "Waiting";
  const verb = stack ? "Resolve" : NEXT_VERB[step] ?? "Next";
  return (
    <div className="turn-dial-wrap plaque-wrap">
      <section className={`turn-dial plaque ${mine ? "mine" : ""}`} data-testid={auto ? "priority-bar" : "turn-dial"} aria-label="Turn and priority">
        <header className="td-head" data-testid="turn-tracker">
          <span className="td-seat" style={{ ["--player-color" as string]: active?.color }} aria-hidden>{active?.name.slice(0, 1).toUpperCase()}</span>
          <span className="td-turn">Turn {turn.number} · {active?.id === me ? "your turn" : active?.name}</span>
          {!auto && !watching && (
            <span className="td-steps">
              <button className="tt-icon" title="Previous step" aria-label="Previous step" onClick={() => void send({ type: "phase", to: "prev" })}>‹</button>
              <button className="tt-icon" title="Next step (N)" aria-label="Next step" onClick={() => void send({ type: "phase", to: "next" })}>›</button>
            </span>
          )}
        </header>
        <button className="td-phase" data-testid="current-phase" title="Jump to a step" disabled={auto || watching}
          onClick={(e) => openMenu(e, PHASES.map((ph) => ({ label: `${ph === step ? "● " : ""}${PHASE_LABEL[ph]}`, onClick: () => void send({ type: "phase", to: ph }) })), "Step")}>
          {PHASE_LABEL[step] ?? turn.phase}
        </button>
        <ol className="td-track" aria-label="Steps of the turn">
          {STEP_GROUPS.map((g) => {
            const here = g.steps.includes(step);
            return (
              <li key={g.label} className={here ? "here" : ""} aria-current={here ? "step" : undefined}>
                <span className="td-ticks">{g.steps.map((ph) => <i key={ph} className={ph === step ? "on" : PHASES.indexOf(ph) < PHASES.indexOf(step) ? "done" : ""} />)}</span>
                <span className="td-group">{g.label}</span>
              </li>
            );
          })}
        </ol>
        <p className="td-status" data-testid="priority-holder" aria-live="polite">{status}</p>
        {auto && mine && (
          <>
            <button className="td-pass" data-testid="pass-priority" aria-label={`Pass priority: ${verb.toLowerCase()}`} title="Pass priority (P)" onClick={() => void passPriority()}>
              {verb}
            </button>
            {stack && <p className="td-hint">{topName} resolves once everyone passes</p>}
            <div className="td-more">
              {stack && <button className="tt-btn ghost" data-testid="resolve-one" onClick={() => void passPriority("stack_changes")}>Resolve one</button>}
              {stack && <button className="tt-btn ghost" data-testid="resolve-all" onClick={() => void passPriority("stack_empty")}>Resolve all</button>}
              {!stack && <button className="tt-btn ghost" data-testid="pass-turn" onClick={() => void passPriority("next_turn")}>End turn</button>}
            </div>
          </>
        )}
        {!auto && !watching && (
          <>
            <button className="td-pass" onClick={() => void send({ type: "phase", to: "next" })} title="Next step (N)">{NEXT_VERB[step] ?? "Next step"}</button>
            <div className="td-more">
              <button className="tt-btn ghost next-turn" title="Next turn (Shift+N)" onClick={() => void send({ type: "next_turn" })}>Next turn</button>
            </div>
          </>
        )}
        {auto && prefs?.pass_until && (
          <button className="tt-btn ghost td-cancel" data-testid="cancel-pass" onClick={() => void setPrefs({ cancel_pass: true })}>
            Passing until {prefs.pass_until.replace("_", " ")}: cancel
          </button>
        )}
        {auto && prefs && (
          <div className="td-toggles">
            <button className={`td-toggle ${prefs.hold_priority ? "on" : ""}`} aria-pressed={!!prefs.hold_priority} data-testid="hold-priority" title="Keep priority after you cast"
              onClick={() => void setPrefs({ hold_priority: !prefs.hold_priority })}>Hold</button>
            <button className={`td-toggle ${prefs.full_control ? "on" : ""}`} aria-pressed={!!prefs.full_control} data-testid="full-control" title="No auto-passing at all"
              onClick={() => void setPrefs({ full_control: !prefs.full_control })}>Full control</button>
            {!mine && (
              <button className={`td-toggle ${prefs.force_stop ? "on" : ""}`} aria-pressed={!!prefs.force_stop} data-testid="force-stop" title="Stop at your next priority"
                onClick={() => void setPrefs({ force_stop: !prefs.force_stop })}>Stop</button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

/** The Stack: most recent on top, with controller and targets; Pass / Respond / Auto-pass. */
export function RulesStack() {
  const ctx = useRules();
  const [responding, setResponding] = useState<string | null>(null);
  if (!ctx || !ctx.rules || !ctx.view.stack.length) return null;
  const { view, rules, me } = ctx;
  const entries = chainEntries(view);
  const mine = !rules.controlled_by && (rules.priority === me || (!!rules.acting_as && rules.priority === rules.acting_as)) && !rules.decision;
  const top = entries[0]?.id ?? "";
  return (
    <div className="rules-stack-wrap plaque-wrap">
      <section className="rules-stack chain plaque" data-testid="rules-stack" aria-label="The stack">
        <div className="chain-head"><span className="chain-title">The stack<span className="chain-count"> · {view.stack.length}</span></span></div>
        <ol className="chain-list">
          {entries.map((entry, i) => (
            <ChainRow key={entry.id} entry={entry} top={i === 0} view={view}>
              <button className="tt-icon chain-hold" title="Stop and give me priority after this resolves" aria-label="Hold after this resolves" onClick={() => void setPrefs({ stop_after: entry.id })}>❚❚</button>
            </ChainRow>
          ))}
        </ol>
        {mine && (
          <div className="chain-actions">
            <button className={`btn small ${responding === top ? "primary" : ""}`} data-testid="stack-respond"
              title="Keep priority: cast or activate something in response" onClick={() => setResponding(top)}>Respond</button>
            <span className="chain-actions-hint">{responding === top ? "Cast or activate something, then pass." : "Pass from the turn dial."}</span>
          </div>
        )}
      </section>
    </div>
  );
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
        {d.public ? d.prompt : `${playerName(view, d.player)} is deciding: ${d.prompt}`}
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
type PaidPart = { card: string; name: string; kind: "convoke" | "improvise" | "delve"; pays: string };
type TapManaInfo = { cost: string; what: string; sources: string[]; convoke?: string[]; improvise?: string[];
  delve?: string[]; committed?: string[]; paid?: PaidPart[]; remaining?: string; pool: Record<string, number> };

const HELPER_LABEL = { convoke: "Convoke", improvise: "Improvise", delve: "Delve" } as const;

/** One symbol a contribution pays: "1" is one generic mana ({1}). */
export const paidSymbol = (pays: string) => `{${pays}}`;

function TapManaPanel({ d, view }: { d: DecisionView; view: GameView }) {
  const info = d.display as unknown as TapManaInfo;
  const committed = new Set(info.committed ?? []);
  const sources = info.sources.filter((id) => view.cards[id] && !view.cards[id]!.tapped);
  const helpers = (kind: "convoke" | "improvise" | "delve") => (info[kind] ?? []).filter((id) => view.cards[id]);
  const pool = Object.entries(info.pool ?? {}).filter(([, n]) => n > 0).map(([m, n]) => `{${m}}`.repeat(n)).join("");
  const hover = (id: string | null) => useGame.getState().setHover(id);
  const helperRow = (kind: "convoke" | "improvise" | "delve", title: string) => {
    const ids = helpers(kind);
    if (!ids.length) return null;
    return (
      <>
        <div className="frame-title">{title}</div>
        <div className="pay-row alt" data-testid={`pay-${kind}`}>
          {ids.map((id) => (
            <button key={id} className={`pay-thumb${committed.has(id) ? " picked" : ""}`} data-testid={`${kind}-${id}`}
              title={committed.has(id) ? "Paying part of the cost — click to take it back" : `Use for ${kind}`}
              onClick={() => (kind === "delve" ? delveCard(id) : payWith(id, kind))}
              onPointerEnter={() => hover(id)} onPointerLeave={() => hover(null)}>
              <GameCardFace card={view.cards[id]!} size="small" />
            </button>
          ))}
        </div>
      </>
    );
  };
  return (
    <div className="decision-panel payment tap-mana frame ornate" data-testid="decision-panel" data-kind="tap_mana">
      <div className="pay-head">
        <span className="pay-title">Cast cost</span>
        <span className="pay-cost"><ManaText text={info.cost} /></span>
      </div>
      <div className="pay-what">for {info.what}</div>
      <div className="decision-hint">Tap your lands and mana sources: click a highlighted card on the table (or below).</div>
      {(info.paid ?? []).length > 0 && (
        <ul className="pay-paid" data-testid="pay-paid">
          {(info.paid ?? []).map((p) => (
            <li key={p.card} data-testid={`paid-${p.card}`}>
              ✓ {p.name} — {HELPER_LABEL[p.kind]} <ManaText text={paidSymbol(p.pays)} />
            </li>
          ))}
        </ul>
      )}
      <div className="pay-row">
        <span className="pay-pool" data-testid="tap-pool">Mana pool: {pool ? <ManaText text={pool} /> : "empty"}</span>
        <span className="pay-remaining" data-testid="pay-remaining">
          Remaining: {info.remaining ? <ManaText text={info.remaining} /> : "PAID"}
        </span>
      </div>
      {sources.length > 0 && (
        <div className="pay-row alt">
          {sources.map((id) => (
            <button key={id} className="pay-thumb" title="Tap for mana" data-testid={`tap-source-${id}`}
              onClick={() => tapForMana(id)} onPointerEnter={() => hover(id)} onPointerLeave={() => hover(null)}>
              <GameCardFace card={view.cards[id]!} size="small" />
            </button>
          ))}
        </div>
      )}
      {helperRow("convoke", "Convoke: tap a creature to pay {1} or one mana of its color")}
      {helperRow("improvise", "Improvise: tap an artifact to pay {1}")}
      {helperRow("delve", "Delve: exile a card from your graveyard to pay {1}")}
      <div className="pay-actions two">
        <button className="act-btn primary" data-testid="option-pay" onClick={() => void choose(d.id, ["pay"])}>Pay</button>
        <button className="act-btn red" data-testid="option-cancel" onClick={() => void choose(d.id, ["cancel"])}>Cancel</button>
      </div>
    </div>
  );
}

/** A "choose a card name" decision (CR 201.4) is one option with this id (its `group` says what may be named); the cards after it are
 * what the chooser looked at (an opponent's hand) and are only shown. The name is typed; the server checks it against the Oracle list. */
export const NAME_OPTION = "__name__";

function CardNameChoice({ d, view }: { d: DecisionView; view: GameView }) {
  const [name, setName] = useState("");
  const [hint, setHint] = useState<string[]>([]);
  const seen = (d.options ?? []).slice(1);
  const type = (text: string) => {
    setName(text);
    if (text.trim().length >= 2) void autocomplete(text).then(setHint, () => setHint([]));
    else setHint([]);
  };
  return (
    <div className="decision-options" data-testid="card-name-choice">
      {seen.length > 0 && (
        <div className="decision-seen" data-testid="card-name-seen">
          {seen.map((o) => <span key={o.id} className="tt-chip">{optionLabel(o, view)}</span>)}
        </div>
      )}
      <input className="decision-name" data-testid="card-name-input" list="card-name-hints" value={name} placeholder="Card name"
        onChange={(e) => type(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) void chooseName(d.id, name.trim()); }} />
      <datalist id="card-name-hints">{hint.map((h) => <option key={h} value={h} />)}</datalist>
      <button className="tt-btn brass" data-testid="card-name-done" disabled={!name.trim()} onClick={() => void chooseName(d.id, name.trim())}>Name it</button>
    </div>
  );
}

/** -- X announced (wave 24D) -- 107.3a: the number for X, asked before the cast / activation is sent (the server validates the range). */
export function XPrompt() {
  const action = useXPrompt((s) => s.action);
  const field = useXPrompt((s) => s.field);
  const [x, setX] = useState("0");
  if (!action) return null;
  const close = () => { useXPrompt.setState({ action: null, field: "x_value" }); setX("0"); };
  const ok = /^\d{1,4}$/.test(x) && Number(x) <= 1000;
  const go = () => { if (submitNumericPrompt(x)) setX("0"); };
  return (
    <div className="decision-panel frame" data-testid="x-prompt">
      <div className="decision-prompt">{field === "kicker" ? "Choose a multikicker count (0–1000)" : "Choose a value for X"}</div>
      <div className="decision-options">
        <input className="decision-name" data-testid="x-input" type="number" min={0} max={1000} autoFocus value={x}
          onChange={(e) => setX(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") go(); if (e.key === "Escape") close(); }} />
        <button className="tt-btn brass" data-testid="x-done" disabled={!ok} onClick={go}>{field === "kicker" ? "Cast with multikicker" : "Cast / activate with X"}</button>
        <button className="tt-btn" data-testid="x-cancel" onClick={close}>Cancel</button>
      </div>
    </div>
  );
}

/** -- group choices (wave 53D) -- "secretly choose a number": one option with this id, whose label says the least ("Type a number ≥ 0"); the whole number is
 * typed and sent like a card name (the server checks it). */
export const NUMBER_OPTION = "__number__";

function NumberChoice({ d }: { d: DecisionView }) {
  const [n, setN] = useState("");
  const ok = /^\d{1,9}$/.test(n.trim());
  const canPass = (d.options ?? []).some((o) => o.id === "pass"); // a bid (wave 53D): "pass" is typed like the number, the server reads it
  return (
    <div className="decision-options" data-testid="number-choice">
      <div className="decision-seen">{d.options?.[0]?.label}</div>
      <input className="decision-name" data-testid="number-input" type="number" min={0} step={1} autoFocus value={n} placeholder="Number"
        onChange={(e) => setN(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && ok) void chooseName(d.id, n.trim()); }} />
      <button className="tt-btn brass" data-testid="number-done" disabled={!ok} onClick={() => void chooseName(d.id, n.trim())}>Choose</button>
      {canPass && <button className="tt-btn" data-testid="number-pass" onClick={() => void chooseName(d.id, "pass")}>Pass</button>}
      {d.cancelable && <button className="tt-btn" data-testid="number-cancel" onClick={() => void choose(d.id, ["cancel"])}>Cancel</button>}
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
  if (d.kind === "choose_one" && options[0]?.id === NAME_OPTION) return <CardNameChoice d={d} view={view} />;
  if (d.kind === "choose_one" && options[0]?.id === NUMBER_OPTION) return <NumberChoice d={d} />;
  if (d.kind === "choose_one" || d.kind === "confirm" || d.kind === "manual_resolution") {
    return (
      <div className="decision-options">
        {options.some((o) => o.group === "seen") && ( /* the cards the chooser looked at (an opponent's hand) are shown, never answers */
          <div className="decision-seen" data-testid="card-name-seen">
            {options.filter((o) => o.group === "seen").map((o) => <span key={o.id} className="tt-chip">{optionLabel(o, view)}</span>)}
          </div>
        )}
        {options.filter((o) => o.group !== "seen").map((o) => (
          <button key={o.id} className="tt-btn" data-testid={`option-${o.id}`} onClick={() => done([o.id])}>{o.label}</button>
        ))}
        {d.rememberable && (
          <select className="decision-remember" data-testid="remember" value={remember} onChange={(e) => setRemember(e.target.value)}>
            <option value="">Ask me every time</option>
            <option value="yes_this_turn">Same answer this turn</option>
            <option value="always_yield">Always</option>
          </select>
        )}
        {d.cancelable && <button className="tt-btn ghost" data-testid="option-cancel" onClick={() => done(["cancel"])}>Cancel</button>}
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
  if (d.kind === "divide") return <Divide d={d} view={view} />;
  // choose_cards
  return (
    <div className="decision-options">
      {options.map((o) => (
        <button key={o.id} className={`tt-btn ${picked.includes(o.id) ? "on" : "ghost"}`} data-testid={`option-${o.id}`}
          onClick={() => toggle(o.id)}>{optionLabel(o, view)}</button>
      ))}
      <button className="tt-btn brass" data-testid="decision-done" disabled={!canSubmitChoice(picked.length, min, max)} onClick={() => done(picked)}>
        {doneLabel(picked.length, min, max)}
      </button>
      {d.cancelable && <button className="tt-btn ghost" data-testid="option-cancel" onClick={() => done(["cancel"])}>Cancel</button>}
    </div>
  );
}

/** A choose_cards answer is legal with min..max picks; min 0 lets an EMPTY answer through (a cost
 * choice's "none to cancel", mana sources "pool only", "up to" choices). */
export function canSubmitChoice(n: number, min: number, max: number): boolean {
  return n >= min && n <= max;
}

export function doneLabel(n: number, min: number, max: number): string {
  if (n === 0 && min === 0) return "Done (none)";
  return `Done${max > 1 ? ` (${n})` : ""}`;
}

function optionLabel(o: DecisionOptionView, view: GameView): string {
  const c = o.card_id ? view.cards[o.card_id] : null;
  return c && !c.hidden && c.name ? c.name : o.label;
}

/** 601.2d: divide damage or counters among the chosen targets (at least 1 each, all of it). */
function Divide({ d, view }: { d: DecisionView; view: GameView }) {
  const options = d.options ?? [];
  const total = Number(d.display?.total ?? 0);
  const least = Number(d.display?.least ?? 1); // 510.1d: a blocker may assign 0 to some of the attackers it blocks
  const lethal = (d.display?.lethal as number[] | undefined) ?? []; // 702.19b: a trampler starts at lethal on each blocker, the rest on its target
  const [amounts, setAmounts] = useState<number[]>(() =>
    lethal.length ? options.map((_, i) => (i < lethal.length ? (lethal[i] ?? 0) : total - lethal.reduce((a, b) => a + b, 0)))
      : options.map((_, i) => (i === 0 ? total - (options.length - 1) * least : least)));
  const sum = amounts.reduce((a, b) => a + b, 0);
  const upto = d.display?.upto === true; // 115.6: "distribute up to N" may divide fewer than N
  const set = (i: number, v: number) => setAmounts((xs) => xs.map((x, k) => (k === i ? Math.max(least, v) : x)));
  return (
    <div className="decision-options">
      {options.map((o, i) => (
        <label key={o.id} className="decision-divide">
          <span>{optionLabel(o, view)}</span>
          <input type="number" min={least} max={total} value={amounts[i] ?? least} data-testid={`divide-${o.id}`}
            onChange={(e) => set(i, Number(e.target.value) || least)} />
        </label>
      ))}
      <button className="tt-btn brass" data-testid="decision-done" disabled={upto ? sum > total : sum !== total} onClick={() => void divide(d.id, amounts)}>
        Done ({sum}/{total})
      </button>
    </div>
  );
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
  const [bandPlan, setBandPlan] = useState<Record<string, string>>({});
  const banding = new Set(Array.isArray(d.display?.banding) ? d.display.banding as string[] : []);
  const qualities = (Array.isArray(d.display?.band_qualities) ? d.display.band_qualities : []) as {
    holders: string[]; members: string[]; description: string;
  }[];
  const leaders = new Set([...banding, ...qualities.flatMap((q) => q.holders)]);
  const groups = new Map<string, string[]>();
  for (const [a, group] of Object.entries(bandPlan)) {
    if (group && plan[a]) groups.set(group, [...(groups.get(group) ?? []), a]);
  }
  const bands = [...groups.values()];
  const invalidBand = bands.some((members) => {
    const banders = members.filter((a) => banding.has(a.slice(2))).length;
    const ordinary = banders > 0 && members.length - banders <= 1;
    const qualified = qualities.some((q) => members.some((a) => q.holders.includes(a.slice(2)))
      && members.every((a) => q.members.includes(a.slice(2))));
    return (!ordinary && !qualified) || new Set(members.map((a) => plan[a])).size > 1;
  });
  const set = (a: string, t: string) => setPlan((p) => {
    const nextPlan = { ...p };
    if (!t) delete nextPlan[a];
    else nextPlan[a] = t;
    return nextPlan;
  });
  const declare = () => void send({
    type: "declare_attackers",
    attackers: Object.entries(plan).map(([a, t]) => ({ card_id: a.slice(2), target: t.slice(2) })),
    bands: bands.map((members) => members.map((a) => a.slice(2))),
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
          {leaders.size > 0 && plan[a.id] && (
            <select aria-label={`Band for ${a.label}`} data-testid={`band-${a.id.slice(2)}`}
              value={bandPlan[a.id] ?? ""} onChange={(e) => setBandPlan({ ...bandPlan, [a.id]: e.target.value })}>
              <option value="">No band</option>
              {Array.from({ length: leaders.size }, (_, i) => <option key={i + 1} value={String(i + 1)}>Band {i + 1}</option>)}
            </select>
          )}
        </label>
      ))}
      {invalidBand && <div role="alert">{qualities.length
        ? "Each band needs compatible banding abilities, matching creatures, and the same defender."
        : "Each band needs banding, at most one creature without it, and the same defender."}</div>}
      <div className="decision-options">
        {targets.length === 1 && (
          <button className="tt-btn ghost" onClick={() => setPlan(Object.fromEntries(attackers.map((a) => [a.id, targets[0]!.id])))}>All attack</button>
        )}
        <button className="tt-btn brass" data-testid="declare-attackers" disabled={invalidBand} onClick={declare}>
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
    const info = d.display as { sources?: string[]; convoke?: string[]; improvise?: string[]; delve?: string[]; committed?: string[] };
    if (info.committed?.includes(cardId)) return "rules-committed";  // paying part of the cost (not tapped yet)
    const usable = [...(info.sources ?? []), ...(info.convoke ?? []), ...(info.improvise ?? []), ...(info.delve ?? [])];
    return usable.includes(cardId) && !view?.cards[cardId]?.tapped ? "rules-mana-source" : "";
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
