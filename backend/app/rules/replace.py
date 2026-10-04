"""Replacement and prevention effects, stage 2 (CR 614, 615, 616; researched against CR 2026-09-25).

CHOKE POINTS — every rules path that makes one of these events happen goes through them (a test in
tests/test_rules_replacements2.py fails if a table action in app/rules bypasses them):

``create_tokens(plan, controller, token, count, *, source=None, tapped=False, ctx=None, bind=None, then=None)``
    ``controller`` creates ``count`` tokens of ``token`` (a create_token spec: name, power,
    toughness, colors, type_line, text; 111.2: the creator owns and controls them). The
    token-creation replacements apply (614.16, 616.1), then each token enters with its own
    "enters" replacements (614.1c-d, 616.1g: creating comes before entering). Returns the new card
    ids, or None while the creating player chooses the order of two replacements (then the tokens
    are created when they answer, their ids are recorded in ``ctx`` as binding ``bind`` and the
    continuation ``then`` runs). Copies (agent F) go through here too.
``put_counters(plan, puts, *, by, effect=True, then=None, entering=None)``
    ``puts``: [(card id or player id, counter kind, n), …] put at once by player ``by``;
    ``effect``: put by an effect (614.16: "If an effect would put …" statics apply) rather than as
    a cost; ``entering``: {card id: controller} for permanents given counters as they enter (122.6).
``draw_cards(plan, players, n, *, then=None)``
    each of ``players`` draws ``n`` (121.2: one at a time; 121.2c: in APNAP order).
``gain_life(plan, gains, *, then=None)``
    [(player, n), …]: each a separate life gain event (119.10, 702.15e).
-- static_other sweep (wave 16B) -- Dredge (702.52a): a card with "Dredge N" in its owner's graveyard is an OPTIONAL replacement of that
owner's draw ("As long as you have at least N cards in your library, if you would draw a card, you may instead mill N cards and
return this card from your graveyard to your hand"): the draw's affected player is asked before anything else applies (a decline
lets the other effects apply as before), and the cards a dredge mills may be dredged for the next draw of the same instruction, so
the draws after one are planned again once it has happened (``draw_cards``). It is no draw: nothing triggers on drawing (614.6).
``plan_damage(plan, events, *, answers, order)``
    one simultaneous damage batch (120.4b): replacement and prevention effects per event, 615.7
    shields, then the results — lifelink gains, wither/infect counters, poison — through the life
    and counter replacements (120.4c). Used by combat (app/rules/combat.py) and effects._deal.

``then`` is a JSON continuation run once the event has happened ({"do": "continue", "ctx": …} goes
on with a resolution, {"do": "rerun", "ctx": …, "e": …} re-runs an effect primitive); a site that
passes none can't pause: it uses a remembered answer, or applies the effects it can and logs the
ones left for the players (never a guess).

The 616.1 loop: the candidates are the statics of permanents on the battlefield (definitions
``{"static": "replace"}``: app/rules/replace_grammar.py; the legacy "prevent all" statics and
records; 615.7 shields) and this turn's records (``RulesState.replacements``). For each event:
self-replacement effects first (616.1a); if one applies, or every order of the applicable ones
leads to the same result (tried by applying them), they apply in timestamp order without a
prompt; otherwise the affected object's controller or the affected player (616.1; APNAP between
players) chooses one to apply, and the loop repeats (616.1f) — re-evaluating what applies to the
modified event (616.2), each effect at most once per event and its successors (614.5). A replaced
event never happens (614.6), so nothing triggers on it (603.2g): only the final events become
table actions, which is also what history, replay and undo record.

Refused (kept manual) in v1: 616.1b-d (control, copy, back face), redirection (614.9), skip
(614.10) of steps, "can't" effects (614.17), "can't be prevented" (615.12), paying life (119.4:
UNVERIFIED whether a payment is replaceable), life-loss replacements, "you would put" counter
wordings, token replacements that add a different token.

-- refused grants/replacements (wave 3R2) -- Now automated: redirection statics (614.9, op
"redirect"), skips (614.10: app/rules/skips.py), "can't gain life" (614.17: app/rules/cant_gain.py),
"can't be prevented" (615.12) and source-of-your-choice shields (609.7, 615.8:
app/rules/source_shields.py), a different token added (op "extra": app/rules/extra_tokens.py).
Still refused, and why:
* 616.1b-d: no replacement the engine applies changes who controls an entering object, makes it a
  copy as it enters through this loop, or has it enter transformed — nothing to order yet.
* Paying life (119.4): UNVERIFIED whether a payment is a replaceable life-loss event; a cost is
  paid as written.
* Life-loss replacements ("If an opponent would lose life during your turn, they lose twice that
  much life instead."): life loss has no choke point yet (seven direct sites).
* "If you would put one or more counters" (Vorinclex, Lae'zel): who "puts" a counter is not
  recorded for every site, and whether a player "getting" counters or a source's controller
  "giving" poison counters (120.3b) is "putting" them is UNVERIFIED.
* Count-level draw replacements ("If an opponent would draw two or more cards, instead …": Alms
  Collector, 121.2a): draws are proposed one card at a time.
* Kalitas-style "instead exile that card and create a token" (a zone replacement with an extra
  event): the move replacement runs inside a table step and can't ask the affected player to
  order it against another "exile instead" (616.1), which then matters.
* A leveler's / Class's level lines and a Room's door lines are never applied (``conditional_lines``):
  the level and the door aren't tracked. An entering permanent's own counter statics: no Commander
  card is blocked by it (614.12 allows only self-only ones, which none has).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, zone_key
from app.rules import scripts, selectors

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Event = dict[str, Any]
Sim = dict[str, Any]
ANSWERS = "replace_answers"  # the resolution context's answers so far (while an effect re-runs)
SHIELDS = "replace_shield_order"  # … and its 615.7 shield picks
MAX_TOKENS_STEP = 100  # (the create_token table action's limit: more are created in several steps)
_EXPLORE_BUDGET = 4000  # orders tried before a question is asked anyway


@dataclass
class Candidate:
    """One replacement / prevention effect that could apply to an event."""

    id: str  # "s:<source object>:<ability index>" | "r:<record id>" | "p:<n>" (legacy prevent all) | "shield:<key>"
    event: str
    match: dict[str, Any]
    op: dict[str, Any]
    controller: str
    source_card: str | None
    source_oid: str | None
    seq: tuple[int, ...]
    label: str
    self_repl: bool = False  # 614.15
    legacy: dict[str, Any] | None = None  # a stage-1 "prevent all" record / static (replacements._applies)

    @property
    def prevention(self) -> bool:
        return bool(self.op.get("prevention"))


# -- the effects in force ---------------------------------------------------------------------------
_LEVEL_MARKER = re.compile(r"^LEVEL \d|: Level \d+\.?$")


def conditional_lines(ch: Characteristics) -> set[int]:
    """Ability lines under a leveler's "LEVEL N" or a Class's "{cost}: Level N" header: they apply
    only at that level, which the engine doesn't track — never applied here (not a guess)."""
    out: set[int] = set()
    on = False
    for ab in ch.abilities:
        if _LEVEL_MARKER.search(ab.text.strip()):
            on = True
            continue
        if on:
            out.add(ab.index)
    return out


def static_candidates(plan: Plan, event: str | tuple[str, ...]) -> list[Candidate]:
    """The replacement statics of permanents on the battlefield for this kind of event (611.3a:
    they apply while their source is there; a face-down permanent has none; a card taken out of
    automation is left to the players)."""
    events = (event,) if isinstance(event, str) else event
    from app.rules.layers import timestamp  # (layers → plan: type hints only)

    out: list[Candidate] = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        defs = scripts.definitions(ch)
        wanted = [(i, d) for i, d in defs.items() if d["kind"] == "static" and d.get("static") == "replace"
                  and d.get("event") in events]
        if not wanted or "Room" in ch.subtypes:  # (a Room's door is unlocked or not: not modelled)
            continue
        skip = conditional_lines(ch)
        oid = plan.oid(c)
        for i, d in sorted(wanted):
            if i in skip:
                continue
            out.append(Candidate(id=f"s:{oid}:{i}", event=d["event"], match=d["match"], op=d["op"], controller=c.controller,
                                 source_card=c.id, source_oid=oid, seq=(timestamp(plan.state, c.id), 0, i),
                                 label=ch.name or c.name or "a permanent"))
    return out


def record_candidates(plan: Plan, event: str | tuple[str, ...]) -> list[Candidate]:
    """This turn's replacement records (``RulesState.replacements`` kind "replace": "Until end of
    turn, if …", 611.2a)."""
    events = (event,) if isinstance(event, str) else event
    turn = plan.state.turn.number
    out = []
    for rec in plan.rules.replacements:
        if rec.get("kind") != "replace" or rec.get("turn") != turn or rec.get("event") not in events:
            continue
        if rec.get("controller") not in plan.live():
            continue  # 800.4a: effects of a player who left the game end
        out.append(Candidate(id=f"r:{rec['id']}", event=rec["event"], match=rec.get("match") or {}, op=rec["op"],
                             controller=rec["controller"], source_card=rec.get("source_card"), source_oid=rec.get("source"),
                             seq=(int(rec.get("seq") or 0), 1, 0), label=rec.get("label") or "an effect",
                             self_repl=bool(rec.get("self"))))
    return out


def candidates(plan: Plan, event: str | tuple[str, ...]) -> list[Candidate]:
    return static_candidates(plan, event) + record_candidates(plan, event)


def add_record(plan: Plan, *, event: str, match: dict[str, Any], op: dict[str, Any], controller: str,
               source: str | None, source_card: str | None, label: str, **extra: Any) -> dict[str, Any]:
    """A replacement effect of a resolved spell or ability lasting this turn (611.2a); its
    timestamp is when it was created (613.7b)."""
    import secrets

    r = plan.rules
    rec = {"id": secrets.token_hex(4), "kind": "replace", "turn": plan.state.turn.number, "event": event, "match": match,
           "op": op, "controller": controller, "source": source, "source_card": source_card, "label": label,
           "seq": r.next_object, **extra}
    r.replacements.append(rec)
    return rec


# -- the 616.1 loop ---------------------------------------------------------------------------------
class Ask(Exception):
    """A choice the affected player has to make before the event can happen."""

    def __init__(self, chooser: str, fp: str, ev: Event, applicable: list[Candidate], outcomes: dict[str, str]) -> None:
        super().__init__(fp)
        self.chooser, self.fp, self.ev, self.applicable, self.outcomes = chooser, fp, ev, applicable, outcomes


class AskOptional(Ask):
    """The affected player chooses whether to apply an optional replacement effect, and which (dredge: one card each)."""


class _TooMany(Exception):
    pass


def _canon(ev: Event) -> str:
    # (an entering permanent's counters are the same event before and after it moves: 614.12a)
    skip = ("applied", "why", "oid", "newcomers") if ev.get("entering") else ("applied", "why")  # (newcomers: wave 5H)
    return json.dumps({k: v for k, v in ev.items() if k not in skip}, sort_keys=True, default=str)


def _fingerprint(ev: Event, applicable: list[Candidate]) -> str:
    raw = json.dumps([_canon(ev), sorted(ev.get("applied") or []), sorted(c.id for c in applicable)], sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class Planner:
    """Applies the 616.1 loop to events of one choke point call. Pure: it reads the table and
    changes nothing (``sim`` carries what earlier events of the same call would have changed)."""

    plan: Plan
    cands: list[Candidate]
    answers: dict[str, str] = field(default_factory=dict)
    ask: bool = True  # False: a site that can't pause (remembered answers only)
    left: list[tuple[Event, list[str]]] = field(default_factory=list)  # (event, effects left to the players)
    opt_n: int = 0  # (optional replacements met so far in this pass: each is its own question, wave 16B)

    # -- kind-specific rules ------------------------------------------------------------------------
    def applies(self, c: Candidate, ev: Event, sim: Sim) -> bool:
        if c.event != ev["kind"] or c.id in (ev.get("applied") or ()):
            return False
        fn = _APPLIES.get(ev["kind"])
        return bool(fn and fn(self.plan, c, ev, sim))

    def apply(self, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
        out = _APPLY[ev["kind"]](self.plan, c, ev, sim)
        applied = [*(ev.get("applied") or []), c.id]
        for nxt in out:
            nxt["applied"] = list(dict.fromkeys([*(nxt.get("applied") or []), *applied]))
            nxt["why"] = [*(ev.get("why") or []), c.label]
        return out

    def perform(self, ev: Event, sim: Sim) -> None:
        fn = _PERFORM.get(ev["kind"])
        if fn is not None:
            fn(self.plan, ev, sim)

    def applicable(self, ev: Event, sim: Sim) -> list[Candidate]:
        found = [c for c in self.cands if self.applies(c, ev, sim) and not c.op.get("optional")]
        selfs = [c for c in found if c.self_repl]  # 616.1a: a self-replacement effect first
        return sorted(selfs or found, key=lambda c: c.seq)

    # -- the loop -----------------------------------------------------------------------------------
    def settle(self, ev: Event, sim: Sim, on_final: Any) -> None:
        """616.1: apply one effect at a time until none applies; each final event is performed in
        ``sim`` and handed to ``on_final`` in order (614.11a / 121.6b: a replacement's events
        complete before the sequence goes on)."""
        if (opt := self.optional(ev, sim)) is not None:  # -- static_other sweep (wave 16B) -- dredge: the player took it
            for nxt in self.apply(opt, ev, sim):
                self.settle(nxt, sim, on_final)
            return
        found = self.applicable(ev, sim)
        if not found:
            self.perform(ev, sim)
            on_final(ev)
            return
        chosen = found[0]
        if len(found) > 1:
            outcomes = self._by_first(ev, found, sim)
            if outcomes is None or len({o for os_ in outcomes.values() for o in os_}) > 1:
                picked = self.choose(ev, found, sim, outcomes)
                if picked is None:  # can't pause, nothing remembered: the players apply these
                    self.left.append((ev, [c.label for c in found]))
                    self.perform(ev, sim)
                    on_final(ev)
                    return
                chosen = picked
        for nxt in self.apply(chosen, ev, sim):
            self.settle(nxt, sim, on_final)

    def optional(self, ev: Event, sim: Sim) -> Candidate | None:
        """The optional replacement ("you may instead") the affected player applies to this event, if any: asked once per event
        (a recorded answer: the candidate's id, or "decline")."""
        opts = [c for c in self.cands if c.op.get("optional") and self.applies(c, ev, sim)]
        if not opts:
            return None
        self.opt_n += 1
        fp = f"opt{self.opt_n}:{_fingerprint(ev, opts)}"
        said = self.answers.get(fp)
        if said is not None:
            return next((c for c in opts if c.id == said), None)
        chooser = affected(self.plan, ev)
        if self.ask and chooser:
            raise AskOptional(chooser, fp, ev, opts, {})
        return None  # (a site that can't pause: no draw is replaced; every site of a draw can pause)

    def _by_first(self, ev: Event, found: list[Candidate], sim: Sim) -> dict[str, set[str]] | None:
        """The results reachable when each candidate is applied first (every later order tried):
        the choice matters only if the results differ (616.1: commuting effects need no prompt).
        None when there are too many orders to try (then the player is asked)."""
        budget = [_EXPLORE_BUDGET]
        out: dict[str, set[str]] = {}
        try:
            for c in found:
                s2 = copy.deepcopy(sim)
                results: set[str] = set()
                self._walk(self.apply(c, ev, s2), s2, [], results, budget)
                out[c.id] = results
        except _TooMany:
            return None
        return out

    def _walk(self, pending: list[Event], sim: Sim, done: list[str], results: set[str], budget: list[int]) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            raise _TooMany
        if not pending:
            results.add(json.dumps([done, sim], sort_keys=True, default=str))
            return
        ev, rest = pending[0], pending[1:]
        found = self.applicable(ev, sim)
        if not found:
            s2 = copy.deepcopy(sim)
            self.perform(ev, s2)
            self._walk(rest, s2, [*done, _canon(ev)], results, budget)
            return
        for c in found:
            s2 = copy.deepcopy(sim)
            self._walk([*self.apply(c, ev, s2), *rest], s2, done, results, budget)

    def choose(self, ev: Event, found: list[Candidate], sim: Sim, outcomes: dict[str, set[str]] | None) -> Candidate | None:
        fp = _fingerprint(ev, found)
        picked = self.answers.get(fp)
        if picked is not None:
            hit = next((c for c in found if c.id == picked), None)
            if hit is not None:
                return hit
        chooser = affected(self.plan, ev)
        if len(found) == 2 and chooser:
            from app.rules.engine import remembered  # (engine → effects → this module)

            pair = pair_order(found)
            key, context = memory(pair, ev)
            said = remembered(self.plan, chooser, key, context)
            if said in ("yes", "no"):
                return pair[0] if said == "yes" else pair[1]
        if self.ask and chooser:
            raise Ask(chooser, fp, ev, found, _describe_outcomes(self.plan, ev, found, sim, self))
        return None


def affected(plan: Plan, ev: Event) -> str | None:
    """616.1: the affected object's controller (its owner if it has none) or the affected player."""
    kind = ev["kind"]
    if kind in ("tokens", "draw", "life", "player_counters"):
        return ev.get("player")
    if kind == "counters":
        if ev.get("controller"):
            return str(ev["controller"])  # (a permanent entering: the player it enters under)
        card = plan.state.cards.get(ev["card"])
        return card.controller if card is not None else None
    if kind == "damage":
        target = ev["target"]
        if target in plan.state.players:
            return str(target)
        card = plan.state.cards.get(target)
        return card.controller if card is not None else None
    return None


def _identity(c: Candidate) -> str:
    return json.dumps([c.label, c.op, c.match], sort_keys=True)


def pair_order(found: list[Candidate]) -> list[Candidate]:
    """Two effects in a fixed order by what they are (name and wording), whatever their
    timestamps: "yes" to "apply the first one first?" means the same thing each time."""
    return sorted(found, key=_identity)


def memory(pair: list[Candidate], ev: Event) -> tuple[str, str]:
    """A remembered order ("yes this turn": the first of ``pair`` before the second) for the same
    two effects — by name and wording, so it carries over to other copies of the same cards — in
    the same kind of event."""
    raw = json.dumps([_identity(pair[0]), _identity(pair[1])], sort_keys=True)
    key = f"replace_order:{hashlib.sha1(raw.encode()).hexdigest()[:12]}"
    return key, f"{ev['kind']}:{ev.get('counter') or ''}"


# -- describing events and choices (public information only) ----------------------------------------
def describe(plan: Plan, ev: Event) -> str:
    kind = ev["kind"]
    if kind == "tokens":
        n = ev["count"]
        return f"{n} {ev['token']['name']} token{'s' if n != 1 else ''}"
    if kind == "counters":
        n = ev["n"]
        return f"{n} {ev['counter']} counter{'s' if n != 1 else ''}"
    if kind == "player_counters":
        n = ev["n"]
        return f"{n} {ev['counter']} counter{'s' if n != 1 else ''} for {plan.name(ev['player'])}"
    if kind == "draw":
        return f"{plan.name(ev['player'])} draws a card"
    if kind == "dredge":
        return f"{plan.name(ev['player'])} dredges {ev['n']}"
    if kind == "win":
        return f"{plan.name(ev['player'])} wins the game"
    if kind == "life":
        return f"{plan.name(ev['player'])} gains {ev['n']} life"
    if kind == "life_loss":
        return f"{plan.name(ev['player'])} loses {ev['n']} life"
    if kind == "damage":
        return f"{ev['amount']} damage"
    return kind


def _describe_outcomes(plan: Plan, ev: Event, found: list[Candidate], sim: Sim, planner: Planner) -> dict[str, str]:
    """For each candidate applied first, what happens (when that is certain): for the prompt."""
    out: dict[str, str] = {}
    for c in found:
        s2 = copy.deepcopy(sim)
        results: set[str] = set()
        try:
            planner._walk(planner.apply(c, ev, s2), s2, [], results, [_EXPLORE_BUDGET])
        except _TooMany:
            continue
        if len(results) != 1:
            continue
        done = json.loads(next(iter(results)))[0]
        finals = [json.loads(x) for x in done]
        out[c.id] = "; ".join(describe(plan, f) for f in finals) if finals else "nothing"
    return out


def option_label(c: Candidate, outcomes: dict[str, str]) -> str:
    """"Hardened Scales first → 4 +1/+1 counters" (the outcome when it is certain)."""
    label = f"{c.label} first" + (f" → {outcomes[c.id]}" if c.id in outcomes else "")
    return label if len(label) <= 200 else label[:199] + "…"


def ask(plan: Plan, q: Ask, answers: dict[str, str], resume: dict[str, Any]) -> None:
    """Open the affected player's choice (616.1e) with the answers so far and how to go on."""
    from app.rules.plan import decide

    what = describe(plan, q.ev)
    names = " and ".join(c.label for c in q.applicable)
    base = {**copy.deepcopy(resume), "step": "replace_order", "fp": q.fp, "answers": dict(answers)}
    if base.get("ctx") is not None:
        base["order"] = list(base["ctx"].pop(SHIELDS, None) or base.get("order") or [])
        base["ctx"].pop(ANSWERS, None)
    if isinstance(q, AskOptional):  # -- static_other sweep (wave 16B) -- 702.52a: "you may instead" (public: a card in a graveyard)
        decide(plan, player=q.chooser, kind="choose_one", prompt=f"{what}: apply a replacement effect instead? (702.52)",
               options=[*(DecisionOption(id=f"o{i}", label=f"{c.label}: mill {c.op['n']}, return it to your hand", card_id=c.source_card)
                          for i, c in enumerate(q.applicable)), DecisionOption(id="decline", label="Draw normally")],
               resume={**base, "map": {**{f"o{i}": c.id for i, c in enumerate(q.applicable)}, "decline": "decline"}})
        return
    if len(q.applicable) == 2:
        a, b = pair_order(q.applicable)
        key, context = memory([a, b], q.ev)
        prompt = f"{names} both apply ({what}): apply {a.label} first? (616.1)"
        decide(plan, player=q.chooser, kind="confirm", prompt=prompt,
               options=[DecisionOption(id="yes", label=option_label(a, q.outcomes)),
                        DecisionOption(id="no", label=option_label(b, q.outcomes))],
               resume={**base, "map": {"yes": a.id, "no": b.id}}, memory_key=key, memory_context=context)
        return
    options = [DecisionOption(id=f"o{i}", label=option_label(c, q.outcomes)) for i, c in enumerate(q.applicable)]
    decide(plan, player=q.chooser, kind="choose_one", prompt=f"{names} apply ({what}): which applies first? (616.1)",
           options=options, resume={**base, "map": {f"o{i}": c.id for i, c in enumerate(q.applicable)}})


def left_to_players(plan: Plan, planner: Planner) -> None:
    """A site that couldn't ask: log the effects the players still have to apply by hand."""
    for ev, labels in planner.left:
        plan.note(f"{' and '.join(labels)} both apply to {describe(plan, ev)} and the order matters: "
                  "the engine couldn't ask here — apply them by hand (616.1)")
    planner.left.clear()


def note_applied(plan: Plan, before: Event, finals: list[Event], actor: str | None = None) -> None:
    """One log line for an event that replacement effects modified (the event itself never
    happened, 614.6: only the final events are table actions)."""
    why = list(dict.fromkeys(w for f in finals for w in (f.get("why") or [])))
    if not why:
        return
    after = "; ".join(describe(plan, f) for f in finals) or "nothing"
    plan.note(f"{', '.join(why)}: {after} instead of {describe(plan, before)}", actor=actor)


# -- resume -----------------------------------------------------------------------------------------
def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The affected player chose which effect applies first: the site runs again with the answer."""
    r = d.resume
    answers = {**(r.get("answers") or {}), r["fp"]: r["map"][chosen[0]]}
    resume_site(plan, r, answers, r.get("order"))


def resume_site(plan: Plan, r: dict[str, Any], answers: dict[str, str], order: list[str] | None) -> None:
    """Run a paused site again with the answers so far (616.1 orders; 615.7 shield picks)."""
    site = r.get("site")
    if site == "rerun":  # an effect primitive, run again from the start with the answers
        from app.rules import effects

        ctx, e = r["ctx"], r["e"]
        ctx[ANSWERS], ctx[SHIELDS] = answers, list(order or [])
        done = effects.PRIMITIVES[e["do"]](plan, ctx, e)
        ctx.pop(ANSWERS, None)
        ctx.pop(SHIELDS, None)
        if done:
            effects.continue_effects(plan, ctx)
        return
    if site == "combat" or "round" in r:
        from app.rules import combat
        from app.rules.engine import _after_resolution

        if combat.deal_combat_damage(plan, r["round"], shield_order=order, answers=answers):
            _after_resolution(plan)
        return
    runner = SITES[str(site)]
    runner(plan, r["request"], answers, r.get("then"))


def run_then(plan: Plan, then: dict[str, Any] | None) -> None:
    """A site's continuation once its event has happened."""
    if not then:
        return
    kind = then.get("do")
    if kind == "continue":
        from app.rules import effects

        effects.continue_effects(plan, then["ctx"])
        return
    fn = THEN.get(str(kind))
    if fn is None:
        raise ValueError(f"unknown continuation {kind!r}")
    fn(plan, then)


THEN: dict[str, Any] = {}  # continuation name -> fn(plan, then): filled by the sites' modules


def _ctx_answers(ctx: dict[str, Any] | None) -> dict[str, str]:
    return dict((ctx or {}).get(ANSWERS) or {})


def rerun_then(ctx: dict[str, Any] | None, e: dict[str, Any] | None) -> dict[str, Any] | None:
    """The continuation of an effect primitive run by the resolver: run it again with the
    answers. None when it isn't the effect being resolved (called from another primitive)."""
    if ctx is None or e is None:
        return None
    effects = ctx.get("effects") or []
    k = int(ctx.get("next") or 0) - 1
    if 0 <= k < len(effects) and effects[k] == e:
        return {"site": "rerun", "ctx": ctx, "e": e}
    return None


def _pause(plan: Plan, q: Ask, answers: dict[str, str], resume: dict[str, Any] | None) -> bool:
    if resume is None:
        return False
    ask(plan, q, answers, resume)
    return True


# == tokens (111.2, 614.16, 616.1g) ==================================================================
def _token_types(spec: dict[str, Any]) -> tuple[set[str], set[str]]:
    line = spec.get("type_line") or ""
    left, _, right = line.partition("—")
    types = {w for w in left.split() if w not in ("Token", "Legendary", "Basic", "Snow")}
    return types, set(right.split())


def _tokens_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["count"] <= 0:
        return False
    m = c.match
    if m.get("who") == "you" and ev["player"] != c.controller:
        return False
    if c.op["do"] == "extra":  # -- refused grants/replacements (wave 3R2) -- app/rules/extra_tokens.py
        from app.rules import extra_tokens

        if not extra_tokens.applies(c, ev, sim, lambda cand, token: _token_matches(cand.match, token)):
            return False
    return _token_matches(m, ev["token"])


def _token_matches(m: dict[str, Any], token: dict[str, Any]) -> bool:
    types, subtypes = _token_types(token)
    if m.get("types") and not set(m["types"]) & types:
        return False
    return not (m.get("subtypes") and not set(m["subtypes"]) & subtypes)


def _tokens_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op
    if op["do"] == "extra":  # -- refused grants/replacements (wave 3R2) -- "those tokens plus a Food token" (614.16)
        from app.rules import extra_tokens

        return extra_tokens.apply(c, ev, sim)
    n = ev["count"] * int(op["n"]) if op["do"] == "mul" else ev["count"] + int(op["n"]) if op["do"] == "add" else ev["count"]
    return [{**ev, "count": max(0, n)}]


def create_tokens(plan: Plan, controller: str, token: dict[str, Any], count: int, *, source: str | None = None,
                  tapped: bool = False, ctx: dict[str, Any] | None = None, bind: str | None = None,
                  then: dict[str, Any] | None = None) -> list[str] | None:
    """THE token-creation choke point (see the module docstring). ``then``: a continuation
    ({"site": "rerun", …} from ``rerun_then``, or {"do": …}); None: the site can't pause."""
    return create_token_batch(plan, [(controller, token, count, source, tapped)], ctx=ctx, bind=bind, then=then)


def create_token_batch(plan: Plan, requests: list[tuple[str, dict[str, Any], int, str | None, bool]], *,
                       ctx: dict[str, Any] | None, bind: str | None, then: dict[str, Any] | None,
                       answers: dict[str, str] | None = None) -> list[str] | None:
    """Several players creating tokens at once ("each player creates a Treasure token"): each
    player's creation is its own event, their choices in APNAP order (616.1). Requests: (player,
    token spec, count, source card, tapped)."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    planner = Planner(plan, candidates(plan, "tokens"), answers, ask=then is not None)
    order = plan.apnap()
    reqs = sorted(requests, key=lambda r: order.index(r[0]) if r[0] in order else len(order))  # 616.1: APNAP
    finals: list[tuple[Event, list[Event]]] = []
    try:
        for pid, spec, count, source, tapped in reqs:
            if count <= 0 or pid not in plan.live():
                continue
            ev: Event = {"kind": "tokens", "player": pid, "count": int(count), "token": spec, "source": source,
                         "tapped": bool(tapped), "applied": []}
            out: list[Event] = []
            planner.settle(ev, {}, out.append)
            finals.append((ev, out))
    except Ask as q:
        resume = _resume_for(then, "tokens", {"requests": [list(r) for r in requests], "bind": bind})
        if _pause(plan, q, answers, resume):
            return None
        raise
    left_to_players(plan, planner)
    made: list[str] = []
    started: dict[str, int] = {}  # -- review (wave 5R) -- each player's first batch
    for before, out in finals:
        note_applied(plan, before, out, actor=before["player"])
        start = started.setdefault(before["player"], plan.rules.batch)
        for ev in out:
            made += _make_tokens(plan, ev)
        _one_batch(plan, start)
    if bind and ctx is not None:
        from app.rules import context

        context.bind_objects(plan, ctx, bind, made)  # the tokens, as the new objects they are
    return made


# -- review (wave 5R) --
def _one_batch(plan: Plan, start: int) -> None:
    """One instruction creating several kinds of token ("a 3/3 … token with deathtouch and a 3/3 … token with
    lifelink", Wurmcoil Engine), or more than one table step of them, is one event (701.7a, 603.2c): the steps since
    batch ``start`` become one batch, so a "whenever one or more tokens enter" ability triggers once. (Each table
    step is its own batch: app/game/rules_state.track.)"""
    r = plan.rules
    if r.batch <= start + 1 or r.trigger_batch > start:
        return
    for e in r.events:
        if e.batch > start:
            e.batch = start + 1
    r.batch = start + 1
# -- end review (wave 5R) --


def _make_tokens(plan: Plan, ev: Event) -> list[str]:
    from app.rules import replacements

    pid, left = ev["player"], int(ev["count"])
    spec = {k: v for k, v in ev["token"].items() if k != "_copy"}
    recipe = ev["token"].get("_copy")  # a token copy (app/rules/copying.py): its copiable values (707.2)
    made: list[str] = []
    while left > 0:
        k = min(left, MAX_TOKENS_STEP)
        left -= k
        created = plan.do({"type": "create_token", "player": pid, "count": k, "stacked": False, "tapped": bool(ev.get("tapped")),
                           "source_id": ev.get("source") if ev.get("source") in plan.state.cards else None,
                           "token": spec}, actor=pid)
        new_ids = getattr(created, "r", None)
        made += list(new_ids.ids) if new_ids is not None else []
    for tid in made:
        if recipe is not None:  # the copy effect applies before anything looks at it, then it enters (707.5)
            from app.rules import copying

            copying.add_copy_effect(plan, [plan.oid(tid)], copying.CopyRecipe.model_validate(recipe), pid)
        replacements.after_entry(plan, tid, pid, newcomers=made)  # 616.1g: created first, then it enters (its "enters with" counters)
    return made


def _run_tokens(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    ctx = then.get("ctx") if then else None
    requests = [(r[0], r[1], int(r[2]), r[3], bool(r[4])) for r in request["requests"]]
    made = create_token_batch(plan, requests, ctx=ctx, bind=request.get("bind"), then=then, answers=answers)
    if made is not None:
        run_then(plan, then)


def _resume_for(then: dict[str, Any] | None, site: str, request: dict[str, Any]) -> dict[str, Any] | None:
    """The decision's resume data: re-run an effect primitive, or this site's request, then ``then``."""
    if then is None:
        return None
    if then.get("site") == "rerun":
        return {"site": "rerun", "ctx": then["ctx"], "e": then["e"]}
    return {"site": site, "request": request, "then": then}


# == counters (122.6, 614.16) ========================================================================
def _object_matches(plan: Plan, spec: dict[str, Any], c: Candidate, card: CardInstance | None, ch: Any,
                    oid: str | None) -> bool:
    if card is None:
        return False
    if spec.get("oids") is not None:  # (-- prevention riders (wave 17A) -- the permanent a shield was made for, as that object)
        return oid in spec["oids"]
    if spec.get("counter") and not card.counters.get(spec["counter"]):  # (-- prevention riders (wave 17A) -- "while it has a +1/+1 counter on it")
        return False
    if spec.get("self"):
        return oid is not None and oid == c.source_oid
    if spec.get("attached"):
        src = plan.state.cards.get(c.source_card or "")
        return src is not None and src.attached_to == card.id
    key = spec.get("sel")
    if not key:
        return True
    return selectors.matches(plan, selectors.from_key(key), card, ch, c.controller, c.source_card)


def _counter_object(plan: Plan, ev: Event) -> tuple[CardInstance | None, Any]:
    """The permanent counters would be put on — as it would exist on the battlefield when it is
    entering (614.12: under the player it enters under)."""
    card = plan.state.cards.get(ev["card"])
    if card is None:
        return None, None
    if ev.get("entering") and (not card.zone.endswith(":battlefield") or card.controller != ev["controller"]):
        probe = card.model_copy(update={"zone": zone_key(ev["controller"], "battlefield"), "controller": ev["controller"]})
        return probe, plan.ch(probe)
    return card, plan.ch(card)


def _counters_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if c.match.get("entering_only"):  # -- counters (wave 5H) -- "… enters with an additional … counter" (614.1c)
        if not ev.get("entering") or ev["n"] < 0 or c.source_card in (ev.get("newcomers") or ()):
            return False  # (614.12: a permanent entering at the same time doesn't apply it)
    elif ev["n"] <= 0:
        return False
    if ev.get("entering") and c.source_card == ev["card"]:
        # 614.12: an entering permanent's own static applies to it only if it affects only it;
        # its general ones ("… on a creature you control") don't (UNVERIFIED for self-only ones:
        # left out, so before and after the move the same effects apply)
        return False
    m = c.match
    if m.get("counter") and m["counter"] != ev["counter"]:
        return False
    if m.get("effect_only") and not ev.get("effect"):
        return False  # "If an effect would put …": not a cost (Doubling Season; 614.16)
    card, ch = _counter_object(plan, ev)
    if card is None or not card.zone.endswith(":battlefield"):
        return False  # (only permanents: a card in exile with time counters isn't one)
    return _object_matches(plan, m.get("on") or {}, c, card, ch, ev.get("oid"))


def _counters_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op
    if op.get("entering"):  # -- counters (wave 5H) --
        return [{**ev, "n": max(0, ev["n"] + int(op["n"]) * _entering_times(plan, c, ev))}]
    n = ev["n"] * int(op["n"]) if op["do"] == "mul" else ev["n"] + int(op["n"]) if op["do"] == "add" else ev["n"]
    return [{**ev, "n": max(0, n)}]


def _player_counters_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["n"] <= 0:
        return False
    who = c.match.get("who")
    return not (who == "you" and ev["player"] != c.controller)


# -- counters (wave 5H) --
def _entering_times(plan: Plan, c: Candidate, ev: Event) -> int:
    """How many times an "enters with an additional …" static adds its counters: once, "equal to ~'s toughness" (the
    source as it is now), "for each …" (values), "for each Angel you already control" (not the permanents entering
    now, 614.12)."""
    times = c.op.get("times")
    if times is None:
        return 1
    ctx = {"controller": c.controller, "source_card": c.source_card, "source_object": c.source_oid}
    if "already" in times:
        fresh = {ev["card"], *(ev.get("newcomers") or ())}
        return sum(1 for cid in selectors.candidates(plan, selectors.from_key(times["already"]), c.controller, c.source_card)
                   if cid not in fresh)
    from app.rules import values

    return max(0, values.evaluate(plan, ctx, times))


def entering_kinds(plan: Plan, cands: list[Candidate]) -> set[str]:
    """The counter kinds an "enters with an additional …" static could add (a zero event of each is planned)."""
    return {str(c.match["counter"]) for c in cands if c.match.get("entering_only") and c.match.get("counter")}
# -- end counters (wave 5H) --


def put_counters(plan: Plan, puts: list[tuple[str, str, int]], *, by: str, effect: bool = True,
                 then: dict[str, Any] | None = None, entering: dict[str, str] | None = None,
                 answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None,
                 newcomers: list[str] | None = None) -> bool:
    """THE counter choke point (see the module docstring). Removing counters (negative ``n``)
    isn't a replaceable "put" and passes straight through. False while a choice is open (the
    continuation ``then`` runs after the answer)."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    planned = plan_counters(plan, puts, by=by, effect=effect, entering=entering, answers=answers, ask=then is not None,
                            newcomers=newcomers)
    if isinstance(planned, Ask):
        request = {"puts": [list(p) for p in puts], "by": by, "effect": effect, "entering": entering,
                   **({"newcomers": newcomers} if newcomers else {})}
        if _pause(plan, planned, answers, _resume_for(then, "counters", request)):
            return False
        raise planned
    do_counters(plan, planned, by=by)
    return True


@dataclass
class CounterPlan:
    finals: list[tuple[Event, list[Event]]]
    planner: Planner


def plan_counters(plan: Plan, puts: list[tuple[str, str, int]], *, by: str, effect: bool,
                  entering: dict[str, str] | None, answers: dict[str, str], ask: bool,
                  cands: list[Candidate] | None = None, newcomers: list[str] | None = None) -> CounterPlan | Ask:
    planner = Planner(plan, cands if cands is not None else candidates(plan, ("counters", "player_counters")), answers, ask=ask)
    finals: list[tuple[Event, list[Event]]] = []
    events: list[Event] = []
    # -- counters (wave 5H) -- an entering permanent given none of a kind an "enters with an additional" static adds:
    # a zero event of that kind, for the static to modify (614.1c, 122.6)
    extra_kinds = entering_kinds(plan, planner.cands) if entering else set()
    puts = list(puts) + [(cid, kind, 0) for cid in (entering or {}) for kind in sorted(extra_kinds)
                         if not any(p[0] == cid and p[1] == kind for p in puts)]
    for target, kind, n in puts:
        if target in plan.state.players:
            events.append({"kind": "player_counters", "player": target, "counter": kind, "n": int(n), "applied": []})
        elif target in plan.state.cards:
            ev: Event = {"kind": "counters", "card": target, "oid": plan.oid(target), "counter": kind, "n": int(n),
                         "by": by, "effect": bool(effect), "applied": []}
            if entering and target in entering:  # given counters as it enters (122.6): asked before it enters (614.12a)
                ev.update(controller=entering[target], entering=True, oid=None)
                if newcomers:  # -- counters (wave 5H) -- the permanents entering with it (614.12)
                    ev["newcomers"] = sorted(newcomers)
            events.append(ev)
    order = plan.apnap()
    events.sort(key=lambda e: order.index(affected(plan, e) or "") if affected(plan, e) in order else len(order))  # 616.1: APNAP
    try:
        for ev in events:
            out: list[Event] = []
            if ev["n"] > 0 or (ev.get("entering") and extra_kinds):  # (wave 5H: a zero entering event too)
                planner.settle(ev, {}, out.append)
            else:
                out = [ev]  # (removing counters: nothing replaces it)
            finals.append((ev, out))
    except Ask as q:
        return q
    return CounterPlan(finals, planner)


def do_counters(plan: Plan, planned: CounterPlan, *, by: str) -> None:
    """The planned counters as table actions: the same kind and number for several objects is one
    step (one event batch), as without replacement effects."""
    left_to_players(plan, planned.planner)
    groups: dict[tuple[str, str, int], list[str]] = {}
    for before, out in planned.finals:
        note_applied(plan, before, out, actor=by)
        for ev in out:
            if ev["n"] == 0:
                continue
            if ev["kind"] == "player_counters":
                plan.do({"type": "resource", "player": ev["player"], "key": ev["counter"], "delta": ev["n"]}, actor=by)
                continue
            if ev["card"] in plan.state.cards:
                groups.setdefault(("card", ev["counter"], ev["n"]), []).append(ev["card"])
    # -- counters (wave 7C) -- several kinds at once are one instruction: its steps share a group (the batch the first
    # one gets), so "whenever you put one or more counters on a creature" triggers once (122.6)
    group = plan.rules.batch + 1 if len(groups) > 1 else 0
    for (_, kind, n), cards in groups.items():
        plan.do({"type": "counter", "card_ids": cards, "kind": kind, "delta": n, **({"group": group} if group else {})},
                actor=by)


def _run_counters(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    puts = [(p[0], p[1], int(p[2])) for p in request["puts"]]
    if put_counters(plan, puts, by=request["by"], effect=bool(request.get("effect", True)), then=then,
                    entering=request.get("entering"), answers=answers, newcomers=request.get("newcomers")):
        run_then(plan, then)


# == draw (121, 614.11, 121.6) =======================================================================
def _draw_step_key(plan: Plan) -> str:
    return f"{plan.state.turn.number}:{plan.state.turn.phase}"


def draws_this_step(plan: Plan, pid: str) -> int:
    """Cards ``pid`` actually drew in the current step (synchronous: counted by ``do_draws``)."""
    r = plan.rules
    if r.replace_step_key != _draw_step_key(plan):
        return 0
    return int(r.replace_step_draws.get(pid, 0))


def _draw_sim(plan: Plan, players: list[str]) -> Sim:
    return {"library": {p: len(plan.state.zones.get(zone_key(p, "library"), [])) for p in plan.state.players},
            "step": {p: draws_this_step(plan, p) for p in plan.state.players}, "dredged": []}


def _draw_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    pid = ev["player"]
    if pid not in plan.live():
        return False
    m = c.match
    if c.op.get("do") == "dredge":  # 702.52a: at least N cards in the library, the card still in the graveyard
        return sim["library"].get(pid, 0) >= int(c.op["n"]) and c.op["card"] not in sim["dredged"] and pid == m["player"]
    who = m.get("who")
    if who == "you" and pid != c.controller or who == "opponent" and pid == c.controller:
        return False
    if m.get("player") and pid != m["player"]:
        return False  # a record for one player ("if target player would draw a card")
    if m.get("library_empty") and sim["library"].get(pid, 0) > 0:
        return False
    if m.get("not_first_in_draw_step"):
        # 504.1: the first card they draw in each of their draw steps (the turn-based draw)
        in_their_draw_step = plan.state.turn.phase == "draw" and plan.active == pid
        if in_their_draw_step and sim["step"].get(pid, 0) == 0:
            return False
    return True


def _draw_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op["do"]
    if op == "win":
        return [{"kind": "win", "player": ev["player"]}]
    if op == "skip":
        return []
    if op == "steal":  # "instead that player skips that draw and you draw a card"
        return [{"kind": "draw", "player": c.controller}]
    if op == "dredge":  # -- static_other sweep (wave 16B) -- 702.52a (performed by do_draws)
        return [{"kind": "dredge", "player": ev["player"], "card": c.op["card"], "n": int(c.op["n"])}]
    if op == "draw":
        return [{"kind": "draw", "player": ev["player"]} for _ in range(int(c.op["n"]))]
    return [ev]


def _draw_perform(plan: Plan, ev: Event, sim: Sim) -> None:
    pid = ev["player"]
    left = sim["library"].get(pid, 0)
    if left > 0:
        sim["library"][pid] = left - 1
        sim["step"][pid] = sim["step"].get(pid, 0) + 1


def _dredge_perform(plan: Plan, ev: Event, sim: Sim) -> None:
    sim["library"][ev["player"]] = sim["library"].get(ev["player"], 0) - int(ev["n"])
    sim["dredged"].append(ev["card"])


def dredge_amount(ch: Any) -> int | None:
    """702.52a: the N of the card's "Dredge N" line."""
    for ab in ch.abilities:
        if ab.kind == "keywords" and "dredge" in ab.keywords and (m := re.fullmatch(r"dredge (\d+)", ab.text.strip().rstrip(".").lower())):
            return int(m[1])
    return None


def dredge_candidates(plan: Plan, players: list[str]) -> list[Candidate]:
    """-- static_other sweep (wave 16B) -- the dredge cards in each player's own graveyard (702.52a: "from your graveyard")."""
    out: list[Candidate] = []
    for pid in players:
        for cid in plan.state.zones.get(zone_key(pid, "graveyard"), []):
            card = plan.state.cards[cid]
            if card.owner != pid or card.is_token or plan.manual(card) or (n := dredge_amount(plan.ch(card))) is None:
                continue
            out.append(Candidate(id=f"d:{cid}", event="draw", match={"player": pid}, op={"do": "dredge", "card": cid, "n": n, "optional": True},
                                 controller=pid, source_card=cid, source_oid=plan.oid(card), seq=(0, 2, 0), label=f"Dredge {n} ({card.name})"))
    return out


def _dredge(plan: Plan, f: Event) -> None:
    """Mill N cards, then return the dredged card from the graveyard to its owner's hand (702.52a)."""
    pid, card = f["player"], plan.state.cards.get(f["card"])
    plan.do({"type": "mill", "player": pid, "count": int(f["n"])}, actor=pid)
    if card is not None and card.zone == zone_key(pid, "graveyard"):
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": pid, "zone": "hand"}}, actor=pid)


def draw_cards(plan: Plan, players: list[str], n: int | dict[str, int], *, then: dict[str, Any] | None = None,
               answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None) -> bool:
    """THE draw choke point (see the module docstring). 121.2: one card at a time; 121.2c: the
    active player draws all their cards first, then the others in turn order; 121.6a / 614.11:
    replacement effects apply even with an empty library; 704.5b: a draw from an empty library
    that isn't replaced loses the game at the next check. False while a choice is open."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    order = plan.apnap()
    who = sorted([p for p in players if p in plan.live()], key=lambda p: order.index(p) if p in order else len(order))
    planner = Planner(plan, [*candidates(plan, "draw"), *dredge_candidates(plan, who)], answers, ask=then is not None)
    sim = _draw_sim(plan, who)
    actions: list[tuple[Event, list[Event]]] = []
    try:
        for pid in who:
            for _ in range(max(0, int(n[pid] if isinstance(n, dict) else n))):  # (a dict: each player's own count, wave 16B)
                ev: Event = {"kind": "draw", "player": pid, "applied": []}
                out: list[Event] = []
                planner.settle(ev, sim, out.append)
                actions.append((ev, out))
    except Ask as q:
        request = {"players": who, "n": n}
        if _pause(plan, q, answers, _resume_for(then, "draw", request)):
            return False
        raise
    left_to_players(plan, planner)
    # -- static_other sweep (wave 16B) -- a dredge mills cards that may be dredged for the next draw: those draws are planned again
    # once it has happened (answers start over: the question for the next one is its own)
    cut = next((k for k, (_, out) in enumerate(actions) if any(f["kind"] == "dredge" for f in out)), None)
    rest: dict[str, int] = {}
    if cut is not None:
        for before, _ in actions[cut + 1:]:
            rest[before["player"]] = rest.get(before["player"], 0) + 1
        actions = actions[: cut + 1]
    do_draws(plan, actions)
    if rest:
        return draw_cards(plan, [p for p in who if p in rest], rest, then=then, answers={})
    return True


def do_draws(plan: Plan, actions: list[tuple[Event, list[Event]]]) -> None:
    """The final events of a draw sequence, in order: consecutive draws by one player are one
    table step (each card is still its own "drew" event, 121.2)."""
    r = plan.rules
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        pid, k = run[0], len(run)
        run.clear()
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        drawn = min(k, len(library))
        if drawn:
            plan.do({"type": "draw", "player": pid, "count": drawn}, actor=pid)
            key = _draw_step_key(plan)
            if r.replace_step_key != key:
                r.replace_step_key, r.replace_step_draws = key, {}
            r.replace_step_draws[pid] = r.replace_step_draws.get(pid, 0) + drawn
        if drawn < k and pid not in r.drew_from_empty:
            r.drew_from_empty.append(pid)  # 704.5b at the next check

    for before, out in actions:
        if [f for f in out if f["kind"] != "draw" or f["player"] != before["player"]] or len(out) != 1:
            flush()
            note_applied(plan, before, out, actor=before["player"])
        for f in out:
            if f["kind"] == "dredge":
                flush()
                _dredge(plan, f)
            elif f["kind"] == "draw":
                if run and run[0] != f["player"]:
                    flush()
                run.append(f["player"])
            elif f["kind"] == "win":
                flush()
                _win(plan, f["player"])
    flush()


def _win(plan: Plan, pid: str) -> None:
    """104.2b: an effect says a player wins the game — the game ends at once (104.1): every other
    player is recorded as having lost it (so the engine stops handing priority on; nothing is
    removed from the table)."""
    r = plan.rules
    if r.winner is not None or pid not in plan.live():
        return
    from app.rules import (
        game_result,  # -- game result statics (wave 10B) -- "You can't win the game" (104.2b)
    )

    if game_result.cannot_win(plan, pid):
        plan.note(f"{plan.name(pid)} would win the game, but can't")
        return
    for other in plan.live():
        if other != pid:
            r.lost[other] = f"{plan.name(pid)} won the game"
    r.winner = pid
    r.priority = pid
    plan.note(f"{plan.name(pid)} wins the game")


def _run_draw(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    n = request["n"]
    if draw_cards(plan, list(request["players"]), n if isinstance(n, dict) else int(n), then=then, answers=answers):
        run_then(plan, then)


# == life gain (119.9, 119.10) =======================================================================
def _life_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["n"] <= 0 or ev["player"] not in plan.live():
        return False  # 119.10: gaining 0 life isn't a life gain event
    who = c.match.get("who")
    return not (who == "you" and ev["player"] != c.controller or who == "opponent" and ev["player"] == c.controller)


def _life_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op
    if op["do"] == "mul":
        return [{**ev, "n": ev["n"] * int(op["n"])}]
    if op["do"] == "add":
        return [{**ev, "n": ev["n"] + int(op["n"])}]
    if op["do"] == "set":
        return [{**ev, "n": int(op["n"])}]
    if op["do"] == "lose":  # "that player loses that much life instead" (a new kind of event, 616.2)
        return [{"kind": "life_loss", "player": ev["player"], "n": ev["n"]}]
    return [ev]


def plan_life(plan: Plan, gains: list[tuple[str, int, str]], *, answers: dict[str, str], ask: bool,
              cands: list[Candidate] | None = None) -> tuple[list[tuple[Event, list[Event]]], Planner] | Ask:
    """Life gain events ([(player, n, key)], each its own event: 702.15e) through 616.1."""
    planner = Planner(plan, cands if cands is not None else candidates(plan, "life"), answers, ask=ask)
    order = plan.apnap()
    evs: list[Event] = [{"kind": "life", "player": p, "n": int(n), "key": key, "applied": []} for p, n, key in gains]
    evs.sort(key=lambda e: order.index(e["player"]) if e["player"] in order else len(order))
    finals: list[tuple[Event, list[Event]]] = []
    from app.rules import cant_gain  # -- refused grants/replacements (wave 3R2) --

    try:
        for ev in evs:
            out: list[Event] = []
            # 614.17c: a gain that can't happen isn't replaced by anything but a self-replacement effect (none here)
            if ev["n"] > 0 and (why := cant_gain.why_not(plan, ev["player"])) is not None:
                finals.append((ev, [{"kind": "nothing", "why": [f"{why}: {plan.name(ev['player'])} can't gain life"]}]))
                continue
            planner.settle(ev, {}, out.append)
            finals.append((ev, out))
    except Ask as q:
        return q
    return finals, planner


def gain_life(plan: Plan, gains: list[tuple[str, int]], *, actor: str, then: dict[str, Any] | None = None,
              answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None) -> bool:
    """THE life-gain choke point (see the module docstring). False while a choice is open."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    planned = plan_life(plan, [(p, n, p) for p, n in gains], answers=answers, ask=then is not None)
    if isinstance(planned, Ask):
        request = {"gains": [list(g) for g in gains], "actor": actor}
        if _pause(plan, planned, answers, _resume_for(then, "life", request)):
            return False
        raise planned
    finals, planner = planned
    left_to_players(plan, planner)
    for before, out in finals:
        note_applied(plan, before, out, actor=actor)
        for ev in out:
            if ev["kind"] == "life" and ev["n"] > 0:
                plan.do({"type": "life", "player": ev["player"], "delta": ev["n"]}, actor=actor)
            elif ev["kind"] == "life_loss" and ev["n"] > 0:
                plan.do({"type": "life", "player": ev["player"], "delta": -ev["n"]}, actor=actor)
    return True


def _run_life(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    if gain_life(plan, [(g[0], int(g[1])) for g in request["gains"]], actor=request["actor"], then=then, answers=answers):
        run_then(plan, then)


# == damage (120.4b, 614, 615, 616) ==================================================================
def source_info(plan: Plan, card_id: str | None, oid: str | None, ch: Any, controller: str | None) -> dict[str, Any]:
    """What a damage source is, for the statics' source filters (609.7c): its colors, types,
    subtypes, whether it's a spell on the stack, and its controller (as it last existed if gone)."""
    card = plan.state.cards.get(card_id or "")
    spell = bool(card is not None and card.zone == "stack" and card.ability is None)
    ctrl = controller
    if card is not None and (card.zone.endswith(":battlefield") or card.zone == "stack") and (oid is None or plan.oid(card) == oid):
        ctrl = card.controller
    elif oid and oid in plan.rules.lki:
        ctrl = plan.rules.lki[oid].controller
    return {"card": card_id, "controller": ctrl, "spell": spell,
            "colors": sorted(ch.colors) if ch is not None else [], "types": sorted(ch.types) if ch is not None else [],
            "subtypes": sorted(ch.subtypes) if ch is not None else []}


def _source_matches(plan: Plan, spec: dict[str, Any], c: Candidate, ev: Event) -> bool:
    src = ev.get("src") or {}
    if spec.get("alts"):  # -- as long as (wave 9B) -- "a red or artifact source you control": either description (609.7c)
        return any(_source_matches(plan, alt, c, ev) for alt in spec["alts"])
    # -- refused grants/replacements (wave 3R2) -- a source of a player's choice (609.7a: the object chosen; its
    # property, if any, is checked again below: 609.7b)
    if spec.get("oids") is not None and ev.get("source_oid") not in spec["oids"]:
        return False
    # -- end refused grants/replacements (wave 3R2) --
    if spec.get("self"):
        return ev.get("source_oid") is not None and ev.get("source_oid") == c.source_oid
    if spec.get("attached"):
        holder = plan.state.cards.get(c.source_card or "")
        return holder is not None and holder.attached_to is not None and holder.attached_to == ev.get("source_card") \
            and plan.state.cards[holder.attached_to].zone.endswith(":battlefield")
    if spec.get("other") and ev.get("source_card") == c.source_card:
        return False
    if spec.get("controller") == "you" and src.get("controller") != c.controller:
        return False
    if spec.get("controller") == "opponent" and src.get("controller") in (None, c.controller):
        return False
    if spec.get("spell") and not src.get("spell"):
        return False
    if spec.get("colors") and not set(spec["colors"]) & set(src.get("colors") or ()):
        return False
    if spec.get("chosen_color"):  # (-- prevention riders (wave 17A) -- "sources of the chosen color": its permanent's choice, 614.12a)
        from app.rules import selectors

        color = selectors.COLORS.get((selectors.source_choice(plan, c.source_card, "color") or "").lower())
        if color is None or color not in (src.get("colors") or ()):
            return False
    if spec.get("colorless") and src.get("colors"):  # (-- prevention riders (wave 17A) -- "colorless sources", "non-Human sources")
        return False
    if spec.get("not_subtypes") and set(spec["not_subtypes"]) & set(src.get("subtypes") or ()):
        return False
    if spec.get("types") and not set(spec["types"]) & set(src.get("types") or ()):
        return False
    if spec.get("not_types") and set(spec["not_types"]) & set(src.get("types") or ()):
        return False
    return not (spec.get("subtypes") and not set(spec["subtypes"]) & set(src.get("subtypes") or ()))


def _recipient_matches(plan: Plan, spec: dict[str, Any], c: Candidate, ev: Event) -> bool:
    if not spec:
        return True
    target = ev["target"]
    if target in plan.state.players:
        if spec.get("pids") is not None:  # (-- prevention riders (wave 17A) -- the player a shield was made for)
            return target in spec["pids"]
        want = spec.get("players")
        if want is None:
            return False
        return not (want == "you" and target != c.controller or want == "opponent" and target == c.controller)
    objects = spec.get("objects")
    if objects is None:
        return False
    card = plan.state.cards.get(target)
    if card is None or not card.zone.endswith(":battlefield"):
        return False
    return _object_matches(plan, objects, c, card, plan.ch(card), ev.get("target_oid"))


def _damage_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["amount"] <= 0:
        return False  # 614.7a: a source dealing 0 damage deals no damage: nothing to replace or prevent
    # -- refused grants/replacements (wave 3R2) -- 615.12: a prevention effect applied to damage that can't be
    # prevented prevents none of it and a shield isn't reduced; none the engine applies has an additional effect
    # (app/rules/source_shields.py), so it isn't applied at all. 615.8: a "next time" shield is used up once.
    if (c.prevention or c.legacy is not None) and ev.get("unpreventable") and not (
            c.op.get("rider") and c.id.startswith("s:")):  # (-- prevention riders (wave 17A) -- a static's additional effect
        return False  # still takes place, 615.12; a record's or shield's riders all count the damage prevented: none)
    if c.op.get("once") and f"once:{c.id}" in sim.get("shields", {}):
        return False
    # -- end refused grants/replacements (wave 3R2) --
    if c.legacy is not None:  # a stage-1 "prevent all …" static or this turn's record
        from app.rules import replacements

        return replacements._applies(plan, c.legacy, ev)
    if c.op["do"] == "shield":
        # 615.7: a shield prevents only damage to what it protects
        return c.op["key"].split("#")[0] == _shield_key(plan, ev["target"]) and sim.get("shields", {}).get(c.op["key"], 0) > 0
    m = c.match
    if m.get("combat") is not None and bool(m["combat"]) != bool(ev.get("combat")):
        return False
    if m.get("monarch") and plan.state.table.monarch != c.controller:  # (-- prevention riders (wave 17A) -- "while you're the monarch")
        return False
    if c.op["do"] == "redirect":  # -- refused grants/replacements (wave 3R2) -- 614.9: nowhere to redirect to: nothing
        from app.rules import source_shields

        if source_shields.redirect_target(plan, c, ev) is None:
            return False
        if c.op.get("limit") is not None and sim.get("shields", {}).get(f"redir:{c.id}", c.op["limit"]) <= 0:
            return False  # (-- prevention riders (wave 17A) -- "the next 1 damage": used up)
    return _source_matches(plan, m.get("source") or {}, c, ev) and _recipient_matches(plan, m.get("to") or {}, c, ev)


def _added_value(plan: Plan, c: Candidate, value: Any) -> int:
    """-- as long as (wave 9B) -- "plus X, where X is Hawkeye's power" / "plus … the number of fire counters on this enchantment":
    read from the permanent with the effect as the damage is dealt (608.2h)."""
    from app.rules import values

    return values.evaluate(plan, {"controller": c.controller, "source_card": c.source_card, "source_object": c.source_oid}, value)


def _damage_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op
    if op["do"] == "redirect":  # -- refused grants/replacements (wave 3R2) -- 614.9 (app/rules/source_shields.py)
        from app.rules import source_shields

        k = int(ev["amount"])
        if op.get("limit") is not None:  # -- prevention riders (wave 17A) -- 614.9, 615.7-like: only the next N damage is redirected
            shields = sim.setdefault("shields", {})
            left = int(shields.get(f"redir:{c.id}", op["limit"]))
            k = min(k, left)
            shields[f"redir:{c.id}"] = left - k
        if op.get("once"):  # (the next time a source would deal damage: used up by this instance, 615.8)
            sim.setdefault("shields", {})[f"once:{c.id}"] = 0
        moved = source_shields.redirect(plan, c, {**ev, "amount": k})
        return [moved, {**ev, "amount": int(ev["amount"]) - k}] if k < int(ev["amount"]) else [moved]
    n = int(ev["amount"])
    kind = op["do"]
    if ev.get("unpreventable") and op.get("prevention"):
        pass  # (-- prevention riders (wave 17A) -- 615.12: the effect applies once and prevents none of it)
    elif kind == "mul":
        n *= int(op["n"])
    elif kind == "add":
        n += int(op["n"]) + (_added_value(plan, c, op["value"]) if op.get("value") else 0)
    elif kind == "sub":
        n = max(0, n - int(op["n"]))
    elif kind == "half":
        n //= 2
    elif kind == "prevent":
        n = max(0, n - int(op["n"]))
    elif kind == "prevent_half_up":  # -- damage wordings (wave 6B) -- prevent half, rounded up: half rounded down is left
        n //= 2
    elif kind == "prevent_all_but":
        n = min(n, int(op["n"]))
    elif kind == "prevent_all":
        n = 0
    elif kind == "shield":  # 615.7: each 1 damage prevented reduces the shield by 1
        shields = sim.setdefault("shields", {})
        left = int(shields.get(op["key"], 0))
        used = min(left, n)
        shields[op["key"]] = left - used
        n -= used
    if op.get("once"):  # -- refused grants/replacements (wave 3R2) -- 615.8: used up by this instance of damage
        sim.setdefault("shields", {})[f"once:{c.id}"] = 0
    out = {**ev, "amount": n}
    if op.get("prevention"):
        out["prevented"] = int(ev.get("prevented") or 0) + (int(ev["amount"]) - n)
        if op.get("rider"):  # -- prevention riders (wave 17A) -- 615.5: the additional effect, once the damage has been dealt
            out["riders"] = [*(ev.get("riders") or []), {"rider": op["rider"], "n": int(ev["amount"]) - n, "by": c.controller,
                                                         "card": c.source_card, "oid": c.source_oid, "name": c.label}]
    return [out]


def damage_candidates(plan: Plan) -> list[Candidate]:
    """The damage effects in force: replacement and prevention statics, this turn's records, the
    stage-1 "prevent all" statics and records, and 615.7 shields."""
    from app.rules import replacements

    out = candidates(plan, "damage")
    for i, rec in enumerate(replacements._records(plan)):
        src = plan.state.cards.get(rec.get("source_card") or "")
        label = (src.name if src is not None else None) or "a prevention effect"
        out.append(Candidate(id=f"p:{rec.get('id') or rec.get('source') or i}:{i}", event="damage", match={},
                             op={"do": "prevent_all", "prevention": True, **({"rider": rec["rider"]} if rec.get("rider") else {})},
                             controller=rec["controller"],
                             source_card=rec.get("source_card"), source_oid=rec.get("source"), seq=(0, 2, i), label=label,
                             legacy=rec))
    for key in sorted(plan.rules.prevention):
        info = plan.rules.prevention_riders.get(key) or {}  # (-- prevention riders (wave 17A) -- "key#id": a shield with a rider)
        out.append(Candidate(id=f"shield:{key}", event="damage", match={},
                             op={"do": "shield", "key": key, "prevention": True, **({"rider": info["rider"]} if info else {})},
                             controller=info.get("by", ""), source_card=info.get("card"), source_oid=info.get("oid"),
                             seq=(0, 3, 0), label=info.get("name") or "a prevention shield"))
    return out


def _shield_key(plan: Plan, target: str) -> str:
    return target if target in plan.state.players else plan.oid(target)


def _shield_left(sim: Sim, key: str) -> int:
    """-- prevention riders (wave 17A) -- what is left of the shields on this recipient ("<key>#<id>": one with a rider)."""
    return sum(v for k, v in sim["shields"].items() if not k.startswith("once:") and k.split("#")[0] == key)


@dataclass
class DamagePlan:
    events: list[Event]  # each with its final "amount" (and "prevented"), in the order given
    notes: list[str]
    shields: dict[str, int]
    planner: Planner
    shield_counters: list[str] = field(default_factory=list)  # -- counters (wave 7C) -- shield counters used up (122.1c)


class ShieldAsk(Exception):
    """615.7: several sources would deal damage to a shielded target at once and it matters which
    one's damage the shield prevents: the shielded player or the permanent's controller chooses."""

    def __init__(self, target: str, chooser: str, pending: list[Event], shield: int) -> None:
        super().__init__(target)
        self.target, self.chooser, self.pending, self.shield = target, chooser, pending, shield


def plan_damage(plan: Plan, events: list[Event], *, answers: dict[str, str], order: list[str] | None, ask: bool,
                cands: list[Candidate] | None = None) -> DamagePlan | Ask | ShieldAsk:
    """One simultaneous damage event batch (120.4b): each event (source → recipient) through the
    616.1 loop — replacement effects (614) and prevention effects (615) alike, chosen by the
    recipient or its controller (APNAP between them) when their order matters — with the 615.7
    shields shared by the events to the same recipient. Pure: the table is untouched."""
    from app.rules import replacements

    cands = cands if cands is not None else damage_candidates(plan)
    planner = Planner(plan, cands, answers, ask=ask)
    sim: Sim = {"shields": {k: int(v) for k, v in plan.rules.prevention.items()}}
    picks = list(order or [])
    for ev in events:
        ev["kind"] = "damage"
        ev.setdefault("applied", [])
        ev["prevented"] = int(ev.get("prevented") or 0)
        ev["target_oid"] = plan.oid(ev["target"]) if ev["target"] in plan.state.cards else None
        # -- refused grants/replacements (wave 3R2) -- 615.12: damage that can't be prevented
        from app.rules import source_shields

        if source_shields.unpreventable(plan, ev):
            ev["unpreventable"] = True
        # -- end refused grants/replacements (wave 3R2) --
    apnap = plan.apnap()
    by_target: dict[str, list[Event]] = {}
    for ev in events:
        by_target.setdefault(ev["target"], []).append(ev)

    def chooser_of(target: str) -> str:
        if target in plan.state.players:
            return target
        card = plan.state.cards.get(target)
        return card.controller if card is not None else ""

    targets = sorted(by_target, key=lambda t: (apnap.index(chooser_of(t)) if chooser_of(t) in apnap else len(apnap)))
    finals: dict[int, list[Event]] = {}  # (-- prevention riders (wave 17A) -- a redirection of "the next 1 damage" splits an event)
    index = {id(ev): i for i, ev in enumerate(events)}
    try:
        for target in targets:
            evs = by_target[target]
            key = _shield_key(plan, target)
            pending = list(evs)
            while pending:
                ev = pending[0]
                # (damage a "prevent all" effect prevents anyway isn't what the shield would prevent)
                contenders = [e for e in pending if e["amount"] > 0 and not e.get("unpreventable")  # (615.12, wave 3R2)
                              and not any(c.legacy is not None and replacements._applies(plan, c.legacy, e) for c in cands)]
                if len(contenders) > 1 and _shield_left(sim, key) > 0 \
                        and len({replacements._shield_signature(plan, e) for e in contenders}) > 1:
                    # 615.7: which source's damage the shield prevents first
                    mine = [p for p in picks if p.startswith(f"{target}:")]
                    if mine:
                        pick = mine[0]
                        picks.remove(pick)
                        ev = next((e for e in contenders if f"{target}:{e['source_oid']}" == pick), contenders[0])
                    elif ask:
                        raise ShieldAsk(target, chooser_of(target), contenders, _shield_left(sim, key))
                    else:
                        ev = contenders[0]
                pending.remove(ev)
                out: list[Event] = []
                planner.settle(dict(ev), sim, out.append)
                finals[index[id(ev)]] = out or [{**ev, "amount": 0}]
    except Ask as q:
        return q
    except ShieldAsk as s:
        return s
    result = [e for i, ev in enumerate(events) for e in finals.get(i, [ev])]
    # -- counters (wave 7C) -- 122.1c: what the other effects left, prevented
    from app.rules import shield_counters

    used = shield_counters.prevent_damage(plan, result)
    notes = []
    for i, before in enumerate(events):
        for after in finals.get(i, [before]):
            if after.get("why"):
                who = replacements._label(plan, before["target"])
                why = ", ".join(dict.fromkeys(after["why"]))
                if after["amount"] <= 0:
                    notes.append(f"{before['amount']} damage to {who} prevented ({why})")
                elif after["target"] != before["target"]:
                    notes.append(f"{why}: {after['amount']} damage to {replacements._label(plan, after['target'])} instead of {who}")
                else:
                    notes.append(f"{why}: {after['amount']} damage to {who} instead of {before['amount']}")
    return DamagePlan(result, notes, sim["shields"], planner, used)


@dataclass
class DamageOutcome:
    """A planned damage batch with its results (120.3, 120.4c), as they'll be recorded."""

    events: list[Event]  # the final damage events (source → recipient, amount), those still dealing damage
    creatures: dict[str, int] = field(default_factory=dict)
    players: dict[str, int] = field(default_factory=dict)  # life lost to damage (120.3a)
    walkers: dict[str, int] = field(default_factory=dict)  # loyalty removed (120.3c)
    battles: dict[str, int] = field(default_factory=dict)  # defense removed (120.3h)
    wither: dict[str, int] = field(default_factory=dict)  # -1/-1 counters put (120.3d), after their replacements
    poison: dict[str, int] = field(default_factory=dict)  # poison counters (120.3b, 702.164c), after their replacements
    lifelink: dict[str, int] = field(default_factory=dict)  # life gained per source (702.15e), after its replacements
    losses: list[tuple[str, int]] = field(default_factory=list)  # a lifelink gain replaced by a loss (Tainted Remedy)
    deathtouched: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    shields: dict[str, int] = field(default_factory=dict)
    left: list[Planner] = field(default_factory=list)
    counter_finals: list[tuple[Event, list[Event]]] = field(default_factory=list)
    life_finals: list[tuple[Event, list[Event]]] = field(default_factory=list)
    shield_counters: list[str] = field(default_factory=list)  # (wave 7C) 122.1c
    riders: list[dict[str, Any]] = field(default_factory=list)  # (wave 17A) the additional effects of prevention effects, 615.5


def damage_outcome(plan: Plan, events: list[Event], *, answers: dict[str, str], order: list[str] | None,
                   ask: bool) -> DamageOutcome | Ask | ShieldAsk:
    """The whole of one damage batch: the damage events through ``plan_damage``, then what the
    dealt damage does (120.3) — with the replacement effects of those results (120.4c): wither /
    infect -1/-1 counters and poison counters through the counter replacements (not "an effect",
    614.16), each lifelink source's gain through the life-gain ones (702.15e). Each event carries
    its source's ``kw`` (keywords, 702.15c: as it last existed), ``lkey`` (whose lifelink gain it
    is: the source card, or its controller if it's gone) and ``toxic`` (combat damage to a player,
    702.164c)."""
    planned = plan_damage(plan, events, answers=answers, order=order, ask=ask)
    if not isinstance(planned, DamagePlan):
        return planned
    out = DamageOutcome(events=[ev for ev in planned.events if ev["amount"] > 0], notes=list(planned.notes),
                        shields=planned.shields, left=[planned.planner],
                        shield_counters=planned.shield_counters,
                        riders=[{**r, "ev": {k: ev.get(k) for k in ("src", "source_card", "source_oid", "target", "target_oid", "combat")}}
                                for ev in planned.events for r in ev.get("riders") or []])
    counters: list[tuple[str, str, int, str]] = []  # (target, kind, n, by)
    gains: dict[str, int] = {}
    for ev in out.events:
        n = int(ev["amount"])
        kw = set(ev.get("kw") or ())
        key = ev["target"]
        by = (ev.get("src") or {}).get("controller") or ""
        if key in plan.state.players:
            if "infect" in kw:
                counters.append((key, "poison", n, by))  # 120.3b
            else:
                out.players[key] = out.players.get(key, 0) + n
            if ev.get("toxic"):
                counters.append((key, "poison", int(ev["toxic"]), by))  # 702.164c
        else:
            ch = plan.ch(plan.state.cards[key])
            if "Planeswalker" in ch.types and not ch.is_creature:
                out.walkers[key] = out.walkers.get(key, 0) + n
            elif "Battle" in ch.types and not ch.is_creature:
                out.battles[key] = out.battles.get(key, 0) + n
            elif {"wither", "infect"} & kw:
                counters.append((key, "-1/-1", n, by))  # 120.3d
            else:
                out.creatures[key] = out.creatures.get(key, 0) + n
            if key not in out.walkers and key not in out.battles and "deathtouch" in kw and key not in out.deathtouched:
                out.deathtouched.append(key)
        if "lifelink" in kw and ev.get("lkey"):
            gains[ev["lkey"]] = gains.get(ev["lkey"], 0) + n
    # the results' own replacement effects, in the same answers (120.4c)
    if counters:
        cands = candidates(plan, ("counters", "player_counters"))
        for by in dict.fromkeys(b for *_, b in counters):
            puts = [(t, k, n) for t, k, n, b in counters if b == by]
            cp = plan_counters(plan, puts, by=by, effect=False, entering=None, answers=answers, ask=ask, cands=cands)
            if isinstance(cp, Ask):
                return cp
            out.left.append(cp.planner)
            out.counter_finals += cp.finals
            for _before, finals in cp.finals:
                for f in finals:
                    if f["n"] <= 0:
                        continue
                    if f["kind"] == "player_counters":
                        out.poison[f["player"]] = out.poison.get(f["player"], 0) + f["n"]
                    else:
                        out.wither[f["card"]] = out.wither.get(f["card"], 0) + f["n"]
    if gains:
        who = []
        for key, n in gains.items():
            card = plan.state.cards.get(key)
            pid = key if key in plan.state.players else card.controller if card is not None else None
            if pid is not None and n > 0:
                who.append((pid, n, key))
        planned_life = plan_life(plan, who, answers=answers, ask=ask)
        if isinstance(planned_life, Ask):
            return planned_life
        life_finals, life_planner = planned_life
        out.left.append(life_planner)
        out.life_finals = life_finals
        for before, finals in life_finals:
            for f in finals:
                if f["kind"] == "life" and f["n"] > 0:
                    out.lifelink[before["key"]] = out.lifelink.get(before["key"], 0) + f["n"]
                elif f["kind"] == "life_loss" and f["n"] > 0:
                    out.losses.append((f["player"], f["n"]))
    return out


def do_damage(plan: Plan, out: DamageOutcome, *, actor: str, combat: bool, extra: dict[str, Any] | None = None) -> None:
    """Record a planned damage batch: one ``rules_damage`` step (one simultaneous event batch),
    then the defense counters removed from battles (120.3h) and any lifelink gain a replacement
    turned into a loss; the 615.7 shields as used; the replacement notes."""
    for planner in out.left:
        left_to_players(plan, planner)
    for text in out.notes:
        plan.note(text, actor=actor)
    for before, finals in [*out.counter_finals, *out.life_finals]:
        note_applied(plan, before, finals, actor=actor)
    commit_shields(plan, out.shields)
    # -- counters (wave 7C) --
    from app.rules import shield_counters

    shield_counters.remove(plan, out.shield_counters, actor)
    if not out.events:
        _run_riders(plan, out.riders)
        return
    dealt = [{"source": ev["source_oid"], "target": ev["target"], "amount": int(ev["amount"]),
              **({"target_object": plan.oid(ev["target"])} if ev["target"] in plan.state.cards else {})} for ev in out.events]
    for pid in [*out.players, *out.poison]:
        if pid in plan.state.players:
            plan.rules.damaged[pid] = plan.state.turn.number
    plan.do({"type": "rules_damage", "creatures": out.creatures, "players": out.players, "poison": out.poison,
             "wither": out.wither, "planeswalkers": out.walkers, "lifelink": out.lifelink, "combat": combat, "dealt": dealt,
             **(extra or {})}, actor=actor)
    for key, n in out.battles.items():
        have = plan.state.cards[key].counters.get("defense", 0) if key in plan.state.cards else 0
        if have:
            plan.do({"type": "counter", "card_ids": [key], "kind": "defense", "delta": -min(have, n)}, actor=actor)
    for pid, n in out.losses:  # (after the damage: its own step, UNVERIFIED batching)
        plan.do({"type": "life", "player": pid, "delta": -n}, actor=actor)
    plan.rules.deathtouched = list(dict.fromkeys([*plan.rules.deathtouched, *out.deathtouched]))
    _run_riders(plan, out.riders)


def _run_riders(plan: Plan, riders: list[dict[str, Any]]) -> None:
    from app.rules import source_shields

    for r in riders:
        source_shields.run_rider(plan, r)


def commit_shields(plan: Plan, shields: dict[str, int]) -> None:
    """The shields as the damage left them (615.7: used up by what they prevented)."""
    r = plan.rules
    # -- refused grants/replacements (wave 3R2) -- 615.8: a "next time" shield that prevented damage is used up
    used = {key[len("once:r:"):] for key in shields if key.startswith("once:r:")}
    for key, left in shields.items():  # -- prevention riders (wave 17A) -- what is left of "the next N damage is dealt to … instead"
        if key.startswith("redir:r:"):
            if left <= 0:
                used.add(key[len("redir:r:"):])
            else:
                for rec in r.replacements:
                    if rec.get("id") == key[len("redir:r:"):]:
                        rec["op"] = {**rec["op"], "limit": left}
    if used:
        r.replacements = [rec for rec in r.replacements if rec.get("id") not in used]
    # -- end refused grants/replacements (wave 3R2) --
    for key, left in shields.items():
        if key not in r.prevention:
            continue
        if left > 0:
            r.prevention[key] = left
        else:
            r.prevention.pop(key, None)
            r.prevention_riders.pop(key, None)


def ask_shield(plan: Plan, s: ShieldAsk, resume: dict[str, Any], order: list[str]) -> None:
    """The 615.7 choice (a private decision of the shielded player / permanent's controller)."""
    from app.rules import replacements
    from app.rules.plan import decide

    options = []
    for e in s.pending:
        src = replacements._source_card(plan, e)
        options.append(DecisionOption(id=f"{s.target}:{e['source_oid']}",
                                      label=f"{(src.name if src else None) or 'a source'} ({e['amount']})",
                                      card_id=src.id if src is not None else None))
    base = copy.deepcopy(resume)
    if base.get("ctx") is not None:
        base["ctx"].pop(ANSWERS, None)
        base["ctx"].pop(SHIELDS, None)
    decide(plan, player=s.chooser, kind="choose_one",
           prompt=f"{replacements._label(plan, s.target)}: a shield prevents the next {s.shield} damage — which source's "
                  f"damage does it prevent first? (615.7)",
           options=options, resume={**base, "step": "shield_order", "order": list(order)})


# -- the kinds' rules (the loop dispatches on the event's kind) ------------------------------------
_APPLIES: dict[str, Any] = {"tokens": _tokens_applies, "counters": _counters_applies, "player_counters": _player_counters_applies,
                            "draw": _draw_applies, "life": _life_applies, "damage": _damage_applies}
_APPLY: dict[str, Any] = {"tokens": _tokens_apply, "counters": _counters_apply, "player_counters": _counters_apply,
                          "draw": _draw_apply, "life": _life_apply, "damage": _damage_apply}
_PERFORM: dict[str, Any] = {"draw": _draw_perform, "dredge": _dredge_perform}
SITES: dict[str, Any] = {"tokens": _run_tokens, "counters": _run_counters, "draw": _run_draw, "life": _run_life}
