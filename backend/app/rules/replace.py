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
    continuation ``then`` runs). Copies (agent F) go through here too. -- token entering choices (wave 34A) -- 614.12a: each token's
    own "As ~ enters, choose …" (a token copy's copied one) is asked of its controller before any token is created, one question per
    token in creation order (``replacements.token_choices``; the answers are ``enter:<n>:<what>`` in the same resume data).
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
(614.10) of steps, "can't" effects (614.17), "can't be prevented" (615.12), "you would put" counter
wordings, token replacements that add a different token.

-- replacements: draws and life (wave 28B) --
* Draw bodies (app/rules/draw_bodies.py): "If you would draw a card, instead <instructions>" runs the instructions (the effect grammar's own)
  as a small resolution of its own once the draws before it have happened (121.6b / 614.11a); ``draw_cards`` plans one draw at a time, stops
  at a body and plans the rest when it is done (continuation ``draw_rest``). 614.5: a draw the body makes isn't replaced by that effect
  again (``exclude`` / the body context's ``repl_applied``); 614.6 / 121.5: a replaced draw never happens, cards a body puts into a hand aren't
  drawn. "you may … instead" is an optional replacement (the affected player is asked, as for Dredge); a site that can't pause
  (``then`` None) doesn't run a body: it logs it for the players. "The next time you would draw a card this turn, …" (Words of …) is a
  record that is spent by the first draw it replaces (``Planner.used``).
* Count-level draw replacements (121.2a, 616.1g: "If you would draw one or more cards, you draw that many plus one", "If an opponent would
  draw two or more cards, instead you and that player each draw a card"): event ``draw_count``, applied to the instruction before its
  individual draws are considered (``draw_cards``, ``counted``).
* Life loss (119.3, 119.4, 118.11, 614.1a): ``lose_life`` is the choke point of every life loss that isn't damage's own result — effects, a
  payment of life ("the player loses that much life", and a payment may be modified by effects) — and ``damage_outcome`` applies the same
  replacements to the life damage causes (120.3a: the damage dealt stays what it was). Only "twice that much" exists on a Commander card
  (Bloodletter of Aclazotz). Life gain may carry "while you have N or less life" (Phial of Galadriel), read as the gain would happen.
* Mill counts (701.17a: "If an opponent would mill one or more cards, they mill twice that many / that many plus four"): ``mill_counts``
  changes the number an instruction says; the caller mills what the library holds.

-- refused grants/replacements (wave 3R2) -- Now automated: redirection statics (614.9, op
"redirect"), skips (614.10: app/rules/skips.py), "can't gain life" (614.17: app/rules/cant_gain.py),
"can't be prevented" (615.12) and source-of-your-choice shields (609.7, 615.8:
app/rules/source_shields.py), a different token added (op "extra": app/rules/extra_tokens.py).
Still refused, and why:
* 616.1b-d: no replacement the engine applies changes who controls an entering object, makes it a
  copy as it enters through this loop, or has it enter transformed — nothing to order yet.
* "If you would put one or more counters" (Vorinclex, Lae'zel): who "puts" a counter is not
  recorded for every site, and whether a player "getting" counters or a source's controller
  "giving" poison counters (120.3b) is "putting" them is UNVERIFIED.
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

from app.game.rules_state import DecisionOption, turn_log_now
from app.game.state import CardInstance, zone_key

# Native continuations register while scripts and their leaf modules import.
# Establish the registry before that cycle, and retain those registrations below.
THEN: dict[str, Any] = {}

# isort: split
from app.rules import card_names, scripts, selectors, stack_interaction, statics  # noqa: E402  # (card_names: wave 53B)

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.counter_receipts import CounterPlacement
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
        emblem = c.zone.endswith(":command") and c.token is not None and c.token.type_line == "Emblem"  # (-- life floor (wave 35C) -- 114.4: an emblem's)
        from app.rules import (
            wave110d_enter,  # -- enters (wave 110D) -- "As long as this creature is in your graveyard, …" (113.6)
        )

        gy110d = c.zone.endswith(":graveyard") and not c.is_token and "counters" in events and wave110d_enter.in_graveyard(c, plan.ch(c))
        if not (c.zone.endswith(":battlefield") or emblem or gy110d) or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        if "damage" in events and not gy110d:
            from app.rules import absorb

            out += absorb.candidates(plan, c, ch)
        defs = scripts.definitions(ch)
        wanted = [(i, d) for i, d in defs.items() if d["kind"] == "static" and d.get("static") == "replace"
                  and d.get("event") in events and (not emblem or d.get("event") in ("life_loss", "damage"))
                  and bool(d.get("gy110d")) == gy110d]
        if not wanted or "Room" in ch.subtypes:  # (a Room's door is unlocked or not: not modelled)
            continue
        skip = conditional_lines(ch)
        oid = plan.oid(c)
        for i, d in sorted(wanted):
            if i in skip or not statics.static_if_holds(plan, d, c):  # (wave 35D: "As long as ~ is untapped, …", 611.3a)
                continue
            # -- enters (wave 110D) -- "a counter of that kind" for each kind on the source (Blue, Loyal Raptor): one static per kind
            for kind in wave110d_enter.kinds(c, d):
                out.append(Candidate(id=f"s:{oid}:{i}" + (f":{kind}" if kind else ""), event=d["event"],
                                     match={**d["match"], "counter": kind} if kind else d["match"], op=d["op"], controller=c.controller,
                                     source_card=c.id, source_oid=oid, seq=(timestamp(plan.state, c.id), 0, i),
                                     label=ch.name or c.name or "a permanent"))
    return out


def record_candidates(plan: Plan, event: str | tuple[str, ...]) -> list[Candidate]:
    """This turn's replacement records (``RulesState.replacements`` kind "replace": "Until end of
    turn, if …", 611.2a)."""
    events = (event,) if isinstance(event, str) else event
    from app.rules.timed_damage_replacements import active

    out = []
    for rec in plan.rules.replacements:
        if rec.get("kind") != "replace" or not active(plan, rec) or rec.get("event") not in events:
            continue
        if (rec.get("controller") not in plan.live() and rec.get("until") not in ("next_turn", "source_on_battlefield")) or rec.get("spent"):
            continue  # 800.4m: next-turn and source-tracking effects survive their creator departing until their duration ends.
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
    used: list[str] = field(default_factory=list)  # (-- replacements: draws (wave 28B) -- the effects applied to the events, for "the next time")
    opt_n: int = 0  # (optional replacements met so far in this pass: each is its own question, wave 16B)
    gate: Any = None  # (review 37: False for an event that can't happen at all: no replacement effect sees it, 101.2 — draw_cards' draw limit)
    stop_draw_sequence: bool = False  # 121.6b: finish a body/dredge before planning the next draw
    stopped: bool = False
    pending_draws: list[Event] = field(default_factory=list)

    # -- kind-specific rules ------------------------------------------------------------------------
    def applies(self, c: Candidate, ev: Event, sim: Sim) -> bool:
        # (-- counter putters (wave 22C) -- "… on a permanent or player": one counters static also applies to player events)
        if (c.event != ev["kind"] and not (c.event == "counters" and ev["kind"] == "player_counters" and c.match.get("players"))) \
                or c.id in (ev.get("applied") or ()) or (c.op.get("once") and not c.op.get("batch") and c.id in self.used):
            # (review 28B: "the next time": one event; wave 35A, ``batch``: damage's "next time" is one TIME — every event of the batch)
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
        found = [c for c in self.cands if self.applies(c, ev, sim) and (not c.op.get("optional") or c.op.get("external_optional"))]
        selfs = [c for c in found if c.self_repl]  # 616.1a: a self-replacement effect first
        creators = [c for c in found if c.event == "tokens" and c.op.get("do") == "set_creator"]
        # 616.1b: changing whose control a token enters under precedes token multipliers.
        return sorted(selfs or creators or found, key=lambda c: c.seq)

    # -- the loop -----------------------------------------------------------------------------------
    def settle(self, ev: Event, sim: Sim, on_final: Any) -> None:
        """616.1: apply one effect at a time until none applies; each final event is performed in
        ``sim`` and handed to ``on_final`` in order (614.11a / 121.6b: a replacement's events
        complete before the sequence goes on)."""
        if self.gate is not None and not self.gate(ev):
            return
        if (opt := self.optional(ev, sim)) is not None:  # -- static_other sweep (wave 16B) -- dredge: the player took it
            self.used.append(opt.id)
            self._children(self.apply(opt, ev, sim), sim, on_final)
            return
        found = self.applicable(ev, sim)
        if not found:
            self.perform(ev, sim)
            on_final(ev)
            if self.stop_draw_sequence and ev["kind"] in ("body", "dredge"):
                self.stopped = True
            return
        chosen = found[0]
        if len(found) > 1:
            outcomes = None if any(c.op.get("external_optional") for c in found) else self._by_first(ev, found, sim)
            if outcomes is None or len({o for os_ in outcomes.values() for o in os_}) > 1:
                picked = self.choose(ev, found, sim, outcomes)
                if picked is None:  # can't pause, nothing remembered: the players apply these
                    self.left.append((ev, [c.label for c in found]))
                    self.perform(ev, sim)
                    on_final(ev)
                    return
                chosen = picked
        if chosen.op.get("external_optional"):
            self.opt_n += 1
            fp = f"external{self.opt_n}:{_fingerprint(ev, [chosen])}"
            said = self.answers.get(fp)
            if said is None and self.ask and chosen.controller in self.plan.live():
                raise AskOptional(chosen.controller, fp, ev, [chosen], {})
            if said != chosen.id:
                self._children([{**ev, "applied": [*(ev.get("applied") or []), chosen.id]}], sim, on_final)
                return
        self.used.append(chosen.id)
        self._children(self.apply(chosen, ev, sim), sim, on_final)

    def _children(self, children: list[Event], sim: Sim, on_final: Any) -> None:
        for i, nxt in enumerate(children):
            self.settle(nxt, sim, on_final)
            if self.stopped:
                # 121.6b / 614.5: retain unprocessed draws from a doubler, along
                # with the effects already applied to them. Plan them only after
                # the current body finishes, against the resulting game state.
                self.pending_draws.extend(children[i + 1:])
                return

    def optional(self, ev: Event, sim: Sim) -> Candidate | None:
        """The optional replacement ("you may instead") the affected player applies to this event, if any: asked once per event
        (a recorded answer: the candidate's id, or "decline")."""
        opts = [c for c in self.cands if c.op.get("optional") and not c.op.get("external_optional") and self.applies(c, ev, sim)]
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
    if kind in ("tokens", "draw", "draw_count", "life", "life_loss", "mill", "player_counters", "scry", "explore", "connive", "proliferate"):
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
    if kind == "draw_count":
        return f"{plan.name(ev['player'])} draws {ev['n']} card{'s' if ev['n'] != 1 else ''}"
    if kind == "dredge":
        return f"{plan.name(ev['player'])} dredges {ev['n']}"
    if kind == "body":  # -- draw bodies (wave 28B) --
        return f"{ev['label']}'s effect"
    if kind == "win":
        return f"{plan.name(ev['player'])} wins the game"
    if kind == "life":
        return f"{plan.name(ev['player'])} gains {ev['n']} life"
    if kind == "life_loss":
        return f"{plan.name(ev['player'])} loses {ev['n']} life"
    if kind == "mill":
        return f"{plan.name(ev['player'])} mills {ev['n']} card{'s' if ev['n'] != 1 else ''}"
    if kind in ("explore", "connive"):  # -- keyword actions (wave 35C) --
        return f"{ev['name']} {kind}s"
    if kind == "scry":
        return f"{plan.name(ev['player'])} scries {ev['n']}"
    if kind == "proliferate":
        return f"{plan.name(ev['player'])} proliferates"
    if kind == "damage":  # (-- damage bodies (wave 35C) -- and what a replacement counts of it: "0 damage (Phytohydra counts 6)")
        return f"{ev['amount']} damage" + "".join(f" ({r['name']} counts {r['n']})" for r in ev.get("riders") or [])
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


def _resume_base(resume: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    """A paused site's resume data: the site with the answers so far (and its shield picks, kept out of the context it is saved with)."""
    base = {**copy.deepcopy(resume), "answers": dict(answers)}
    if base.get("ctx") is not None:
        base["order"] = list(base["ctx"].pop(SHIELDS, None) or base.get("order") or [])
        base["ctx"].pop(ANSWERS, None)
    return base


def ask(plan: Plan, q: Ask, answers: dict[str, str], resume: dict[str, Any]) -> None:
    """Open the affected player's choice (616.1e) with the answers so far and how to go on."""
    from app.rules.plan import decide

    what = describe(plan, q.ev)
    names = " and ".join(c.label for c in q.applicable)
    base = {**_resume_base(resume, answers), "step": "replace_order", "fp": q.fp}
    if isinstance(q, AskOptional):  # -- static_other sweep (wave 16B) -- 702.52a: "you may instead" (public: a card in a graveyard)
        rule = "702.52" if any(c.op.get("do") == "dredge" for c in q.applicable) else "614.1a"  # (review 28B: "you may … instead" isn't only dredge)
        decide(plan, player=q.chooser, kind="choose_one", prompt=f"{what}: apply a replacement effect instead? ({rule})",
               options=[*(DecisionOption(id=f"o{i}", label=f"{c.label}: mill {c.op['n']}, return it to your hand" if c.op.get("do") == "dredge"
                                     else f"{c.label}: apply it instead", card_id=c.source_card)
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
    answers = {**(r.get("answers") or {}), r["fp"]: r["map"][chosen[0]] if "map" in r else chosen[0]}  # (no map: a token's entering choice, wave 34A)
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
    if site == "mana_damage":
        from app.rules import damage_rider_continuations

        damage_rider_continuations.resume_mana(plan, r["request"], answers, order)
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


THEN.update({"draw_rest": lambda plan, then: _then_draw_rest(plan, then), "noop": lambda plan, then: None})  # Built-ins preserve native registrations made during cyclic imports.


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
    if m.get("who") == "opponent" and ev["player"] == c.controller:
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
    if op["do"] == "set_creator":
        return [{**ev, "player": c.controller}]
    if op["do"] == "extra":  # -- refused grants/replacements (wave 3R2) -- "those tokens plus a Food token" (614.16)
        from app.rules import extra_tokens

        return extra_tokens.apply(c, ev, sim)
    if op["do"] in ("replace", "each_of"):  # -- token swaps (wave 35C) -- app/rules/extra_tokens.py
        from app.rules import extra_tokens

        return extra_tokens.swap(c, ev)
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
                       answers: dict[str, str] | None = None,
                       recipient_refs: list[str] | None = None,
                       attachment_refs: list[dict[str, Any] | None] | None = None,
                       replacement_receipts: list[dict[str, Any]] | None = None,
                       creation_atoms: list[str] | None = None,
                       receipt_bind: str | None = None) -> list[str] | None:
    """Several players creating tokens at once ("each player creates a Treasure token"): each
    player's creation is its own event, their choices in APNAP order (616.1). Requests: (player,
    token spec, count, source card, tapped)."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    token_candidates = candidates(plan, "tokens")
    planner = Planner(plan, token_candidates, answers, ask=then is not None)
    from app.rules import token_creation_replacements as grouped

    grouped_mode = any(c.op.get("group_tokens") for c in token_candidates)
    receipt_key = "_token_replacement_receipts"
    receipt_data = (ctx.get(receipt_key) if ctx is not None else replacement_receipts) or []
    receipts = [grouped.TokenReplacementChoice.model_validate(r) for r in receipt_data]
    order = plan.apnap()
    reqs = sorted(enumerate(requests), key=lambda ir: order.index(ir[1][0]) if ir[1][0] in order else len(order))  # 616.1: APNAP
    finals: list[tuple[Event, list[Event]]] = []
    try:
        for request_index, (pid, spec, count, source, tapped) in reqs:
            if count <= 0 or pid not in plan.live():
                continue
            ev: Event = {"kind": "tokens", "player": pid, "count": int(count), "token": spec, "source": source,
                         "tapped": bool(tapped), "applied": [], 'embalmed': bool(spec.get('_embalmed')),
                         'effect_tapped': bool(spec.get('_effect_tapped', tapped))}
            if recipient_refs is not None and request_index < len(recipient_refs):
                ev["recipient_ref"] = recipient_refs[request_index]
            if attachment_refs is not None and request_index < len(attachment_refs):
                ev['attachment_ref'] = attachment_refs[request_index]
            if creation_atoms is not None and request_index < len(creation_atoms):
                ev["creation_atom"] = creation_atoms[request_index]
            out: list[Event] = []
            if grouped_mode:
                finals.append((ev, [ev]))
            else:
                planner.settle(ev, {}, out.append)
                finals.append((ev, out))
        if grouped_mode:
            groups = grouped.initial_groups(plan, [ev for ev, _ in finals])
            groups = grouped.creator_groups(plan, "tokens", token_candidates, groups, answers)
            prior = grouped.prior_creators(plan)
            finals = [(group.parts[0], grouped.plan_group(plan, "tokens:" + str(i), token_candidates, group, prior, answers, receipts).parts)
                      for i, group in enumerate(groups)]
    except grouped.GroupQuestion as group_question:
        receipt_data = [r.model_dump(mode="json") for r in receipts]
        if ctx is not None:
            ctx[receipt_key] = receipt_data
        resume = _resume_for(then, "tokens", {"requests": [list(r) for r in requests], "bind": bind, "recipient_refs": recipient_refs, "attachment_refs": attachment_refs, "replacement_receipts": receipt_data, "creation_atoms": creation_atoms, "receipt_bind": receipt_bind})
        if resume is None:
            raise ValueError("Optional token replacement requires a pausable native instruction") from group_question
        from app.rules.plan import decide

        decide(plan, player=group_question.player, kind="choose_one", prompt=group_question.prompt, options=group_question.options,
               resume={**_resume_base(resume, answers), "step": "replace_order", "fp": group_question.fingerprint, "map": group_question.commands})
        return None
    except Ask as q:
        resume = _resume_for(then, "tokens", {"requests": [list(r) for r in requests], "bind": bind, "recipient_refs": recipient_refs, "attachment_refs": attachment_refs, "replacement_receipts": receipt_data, "creation_atoms": creation_atoms, "receipt_bind": receipt_bind})
        if _pause(plan, q, answers, resume):
            return None
        raise
    receipt_data = [r.model_dump(mode="json") for r in receipts]
    if grouped_mode and ctx is not None:
        ctx[receipt_key] = receipt_data
    left_to_players(plan, planner)
    # -- token entering choices (wave 34A) -- 614.12a: "As this enters, choose …" of each token (a token copy's copied ability), asked before any is created
    from app.rules import replacements

    picks, question = replacements.token_choices(plan, [ev for _, out in finals for ev in out], answers)
    if question is not None:
        resume = _resume_for(then, "tokens", {"requests": [list(r) for r in requests], "bind": bind, "recipient_refs": recipient_refs, "attachment_refs": attachment_refs, "replacement_receipts": receipt_data, "creation_atoms": creation_atoms, "receipt_bind": receipt_bind})
        if resume is not None:  # (a site that can't pause leaves a copied choice to the players: copying.token_copy)
            from app.rules.plan import decide

            if question.get("coin_form"):
                from app.rules import copiable_coin_entry

                data = {"caller": "token", "resume": _resume_base(resume, answers),
                        "answers": dict(answers), "key": question["key"]}
                if copiable_coin_entry.run_coin(plan, question["player"], data):
                    copiable_coin_entry.resume(plan, data)
                return None
            decide(plan, player=question["player"], kind="choose_one", prompt=question["prompt"], options=question["options"],
                   resume={**_resume_base(resume, answers), "step": "replace_order", "fp": question["key"]},
                   source=plan.state.cards.get(question["source"] or ""))
            return None
        picks = []
    made: list[str] = []
    created_receipts: list[dict[str, Any]] = []
    started: dict[str, int] = {}  # -- review (wave 5R) -- each player's first batch
    i = 0
    for before, out in finals:
        note_applied(plan, before, out, actor=before["player"])
        start = started.setdefault(before["player"], plan.rules.batch)
        for ev in out:
            created_ids = _make_tokens(plan, ev, picks[i] if i < len(picks) else [])
            made += created_ids
            if receipt_bind is not None:
                from app.rules import context as token_context

                refs = [ref.model_dump(mode="json") for cid in created_ids
                        if (ref := token_context.ref_of(plan, cid)) is not None]
                created_receipts.append({"atom": str(ev.get("creation_atom", "instruction")), "objects": refs})
            i += 1
        _one_batch(plan, start)
    if grouped_mode and ctx is not None:
        ctx.pop(receipt_key, None)
    if receipt_bind is not None and ctx is not None:
        ctx[receipt_bind] = created_receipts
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


def _make_tokens(plan: Plan, ev: Event, picks: list[dict[str, str]]) -> list[str]:
    import json

    from app.rules import creature_entry_redirect, replacements, token_copy_entry

    pid, left = ev["player"], int(ev["count"])
    aura_picks = [p for p in picks if token_copy_entry.HOST in p or token_copy_entry.SKIP in p]
    if aura_picks:
        picks = [p for p in picks if not p.get(token_copy_entry.SKIP)]
        left = len(picks)
    individual = bool(aura_picks) or any(p.get(token_copy_entry.COPY) for p in picks)
    made: list[str] = []
    receipts: dict[str, dict[str, Any]] = {}
    diverted_ids: set[str] = set()
    pick_index = 0
    while left > 0:
        k = 1 if individual else min(left, MAX_TOKENS_STEP)
        left -= k
        pick = picks[pick_index] if pick_index < len(picks) else {}
        effective = token_copy_entry.effective(ev, pick)
        diverted = creature_entry_redirect.token_exiles(plan, pid, effective)
        spec = {key: value for key, value in ev['token'].items() if key not in ('_copy', '_entry_counters', '_embalmed', '_effect_tapped')}
        incoming = token_copy_entry.probe(plan, pid, effective)
        prospective = incoming.token.model_dump(mode='json') if incoming.token is not None else effective
        explicit_tapped = bool(ev.get('effect_tapped', ev.get('tapped'))) or bool(json.loads(pick.get(token_copy_entry.ENTRY, '{}')).get('tapped'))
        enters_tapped = (explicit_tapped or replacements.token_enters_tapped(plan, pid, prospective)) and not replacements.token_enters_untapped(plan, pid, prospective)
        created = plan.do({'type': 'create_token', 'player': pid, 'count': k, 'stacked': False, 'tapped': enters_tapped,
                           'source_id': ev.get('source') if ev.get('source') in plan.state.cards else None,
                           'token': spec, 'embalmed': bool(ev.get('embalmed')), **({'zone': 'exile'} if diverted else {})}, actor=pid)
        new_ids = getattr(created, 'r', None)
        ids = list(new_ids.ids) if new_ids is not None else []
        made += ids
        for tid in ids:
            receipts[tid] = effective
            if diverted:
                diverted_ids.add(tid)
        pick_index += k
    i_entry = {tid: json.loads(picks[i].get(token_copy_entry.ENTRY, '{}')) if i < len(picks) else {} for i, tid in enumerate(made)}
    for tid in made:
        recipe = receipts[tid].get('_copy')
        if recipe is not None:
            from app.rules import copying

            copying.add_copy_effect(plan, [plan.oid(tid)], copying.CopyRecipe.model_validate(recipe), pid,
                                    duration='end_of_turn' if i_entry.get(tid, {}).get('duration') == 'end_of_turn' else 'permanent')
    for i, tid in enumerate(made):
        if i < len(picks) and picks[i].get(token_copy_entry.HOST) and tid not in diverted_ids:
            from app.rules import attachments

            attachments.attach(plan, tid, picks[i][token_copy_entry.HOST], pid)
    for i, tid in enumerate(made):
        if i < len(picks) and "devour" in str(ev["token"].get("text") or "").lower():  # -- devour token (wave 110B) -- 702.82a
            from app.rules import wave110b_devour

            picks[i] = wave110b_devour.sacrifice(plan, tid, pid, picks[i]) or picks[i]
    for i, tid in enumerate(made):
        # 616.1g: created first, then it enters (its "enters with" counters; -- wave 34A -- what it chose as it entered, 614.12a)
        extra: dict[str, int] = {}
        for counter in ev['token'].get('_entry_counters') or []:
            if counter.get('if_type') and counter['if_type'] not in plan.ch(plan.state.cards[tid]).types:
                continue
            extra[counter['counter']] = extra.get(counter['counter'], 0) + int(counter['n'])
        for counter in i_entry[tid].get('counters') or []:
            if counter.get('if_type') and counter['if_type'] not in plan.ch(plan.state.cards[tid]).types:
                continue
            if counter.get('if_control') and i_entry[tid].get('controller') != pid:
                continue
            value = 0 if counter['n'] == 'X' else int(counter['n'])
            extra[counter['counter']] = extra.get(counter['counter'], 0) + value
        replacements.after_entry(plan, tid, pid, newcomers=made, choices=({key: value for key, value in picks[i].items() if key not in (token_copy_entry.COPY, token_copy_entry.ENTRY)} if i < len(picks) else None) or None,
                                 extra_counters=extra or None)
    recipient = ev.get("recipient_ref")
    if recipient in plan.live() and pid == plan.active and recipient != pid and plan.state.turn.phase in (
            "declare_attackers", "declare_blockers", "combat_damage", "end_combat"):
        from app.rules.token_grammar import _attack_with

        creatures = [cid for cid in made if (card := plan.state.cards.get(cid)) is not None
                     and card.zone.endswith(":battlefield") and card.controller == pid
                     and "Creature" in plan.ch(card).types]
        _attack_with(plan, creatures, recipient, pid)
    return made


def _run_tokens(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    ctx = then.get("ctx") if then else None
    requests = [(r[0], r[1], int(r[2]), r[3], bool(r[4])) for r in request["requests"]]
    made = create_token_batch(plan, requests, ctx=ctx, bind=request.get("bind"), then=then, answers=answers,
                              recipient_refs=request.get("recipient_refs"), attachment_refs=request.get("attachment_refs"),
                              replacement_receipts=request.get("replacement_receipts"), creation_atoms=request.get("creation_atoms"), receipt_bind=request.get("receipt_bind"))
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
    if spec.get("band_of_source"):
        from app.rules import banding

        holder = plan.state.cards.get(c.source_card or "")
        return (holder is not None and plan.oid(holder) == c.source_oid and oid == plan.oid(card)
                and ch.is_creature and card.id in banding.members(plan.state, holder.id))
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
    if m.get("bloodthirst110a") and not any(t == plan.state.turn.number for p, t in plan.rules.damaged.items() if p != c.controller):
        return False  # -- bloodthirst grant (wave 110A) -- 702.54a: an opponent was dealt damage this turn
    if not _putter_ok(c, ev):
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
    if op["do"] == "half":  # -- counter putters (wave 22C) -- "half that many … rounded down" (Vorinclex)
        n = ev["n"] // 2
    return [{**ev, "n": max(0, n)}]


def _putter_ok(c: Candidate, ev: Event) -> bool:
    """-- counter putters (wave 22C) -- "If you / an opponent would put …": the player putting them (``by``) is the
    static's controller or not (122.6a, 120.3d). (Review 22C: counters "given" are put — 122.6 calls an object
    "given counters" as it enters counters being put on it, and proliferate (701.34a) "gives" them — so infect / toxic
    poison is put by the source's controller, 120.3b/g, and "target opponent gets …" by the effect's controller, 608.2c.)"""
    putter = c.match.get("putter")
    if not putter:
        return True
    return bool(ev.get("by")) and (ev["by"] == c.controller) == (putter == "you")


def _player_counters_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["n"] <= 0:
        return False
    if c.match.get("counter") and c.match["counter"] != ev["counter"]:
        return False
    if c.event == "counters":  # -- counter putters (wave 22C) -- "on a permanent or player" / "or on yourself"
        if c.match["players"] == "you" and ev["player"] != c.controller:
            return False
        if c.match.get("counter") and c.match["counter"] != ev["counter"]:
            return False
        return _putter_ok(c, ev)
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
    if "entering_mana_value" in times:
        _, ch = _counter_object(plan, ev)
        return (1 if ch is not None and ch.mana_value <= times["entering_mana_value"]
                else int(times["otherwise"]))
    ctx = {"controller": c.controller, "source_card": c.source_card, "source_object": c.source_oid}
    if "mana_from" in times:  # -- mana provenance (wave 18B) -- "for each mana from an artifact source spent to cast it": the entering one
        ctx["source_object"] = plan.oid(ev["card"])  # The entering incarnation, never an earlier cast of this card.
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
                 newcomers: list[str] | None = None, putters: list[str] | None = None,
                 receipt_bind: str | None = None) -> bool:
    """THE counter choke point (see the module docstring). Removing counters (negative ``n``)
    isn't a replaceable "put" and passes straight through. False while a choice is open (the
    continuation ``then`` runs after the answer)."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    planned = plan_counters(plan, puts, by=by, effect=effect, entering=entering, answers=answers, ask=then is not None,
                            newcomers=newcomers, putters=putters)
    if isinstance(planned, Ask):
        request = {"puts": [list(p) for p in puts], "by": by, "effect": effect, "entering": entering,
                   "receipt_bind": receipt_bind,
                   **({"newcomers": newcomers} if newcomers else {}), **({"putters": putters} if putters is not None else {})}
        if _pause(plan, planned, answers, _resume_for(then, "counters", request)):
            return False
        raise planned
    receipt: list[CounterPlacement] | None = [] if receipt_bind is not None else None
    do_counters(plan, planned, by=by, receipt=receipt)
    if receipt_bind is not None and ctx is not None:
        from app.rules import counter_receipts

        counter_receipts.store(ctx, receipt_bind, receipt or [])
    return True


@dataclass
class CounterPlan:
    finals: list[tuple[Event, list[Event]]]
    planner: Planner


def plan_counters(plan: Plan, puts: list[tuple[str, str, int]], *, by: str, effect: bool,
                  entering: dict[str, str] | None, answers: dict[str, str], ask: bool,
                  cands: list[Candidate] | None = None, newcomers: list[str] | None = None,
                  putters: list[str] | None = None) -> CounterPlan | Ask:
    from app.rules import prohibitions  # -- prohibitions (wave 22B) -- 614.17

    planner = Planner(plan, cands if cands is not None else candidates(plan, ("counters", "player_counters")), answers, ask=ask)
    finals: list[tuple[Event, list[Event]]] = []
    events: list[Event] = []
    # -- counters (wave 5H) -- an entering permanent given none of a kind an "enters with an additional" static adds:
    # a zero event of that kind, for the static to modify (614.1c, 122.6)
    extra_kinds = entering_kinds(plan, planner.cands) if entering else set()
    puts = list(puts) + [(cid, kind, 0) for cid in (entering or {}) for kind in sorted(extra_kinds)
                         if not any(p[0] == cid and p[1] == kind for p in puts)]
    for i, (target, kind, n) in enumerate(puts):
        actor = putters[i] if putters is not None and i < len(putters) else by
        if target in plan.state.players:
            events.append({"kind": "player_counters", "player": target, "counter": kind, "n": int(n), "by": actor, "applied": []})
        elif target in plan.state.cards:
            ev: Event = {"kind": "counters", "card": target, "oid": plan.oid(target), "counter": kind, "n": int(n),
                         "by": actor, "effect": bool(effect), "applied": []}
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
            if ev["kind"] == "counters" and (ev["n"] > 0 or (ev["n"] == 0 and ev.get("entering") and extra_kinds)) and (
                    barred := prohibitions.cant_counters(plan, ev["card"], ev.get("controller") if ev.get("entering") else None, ev["counter"])):
                ev["prohibited"] = barred  # -- prohibitions (wave 22B) -- 614.17: no event: nothing replaces or triggers on it
            elif ev["kind"] == "player_counters" and ev["n"] > 0 and (barred := prohibitions.cant_get_counters(plan, ev["player"], ev["counter"])):
                ev["prohibited"] = barred
            elif ev["n"] > 0 or (ev.get("entering") and extra_kinds):  # (wave 5H: a zero entering event too)
                planner.settle(ev, {}, out.append)
            else:
                out = [ev]  # (removing counters: nothing replaces it)
            finals.append((ev, out))
    except Ask as q:
        return q
    return CounterPlan(finals, planner)


def do_counters(plan: Plan, planned: CounterPlan, *, by: str, receipt: list[CounterPlacement] | None = None) -> None:
    """The planned counters as table actions: the same kind and number for several objects is one
    step (one event batch), as without replacement effects."""
    left_to_players(plan, planned.planner)
    groups: dict[tuple[str, str, int], list[str]] = {}
    group = plan.rules.batch + 1
    for before, out in planned.finals:
        actor = before.get("by") or by
        if before.get("prohibited"):  # -- prohibitions (wave 22B) -- 614.17
            card_id = before.get("card")
            who = plan.name(before["player"]) if card_id is None else plan.state.cards[card_id].name or "a permanent"
            plan.note(f"{before['prohibited']}: counters can't be put on {who}", [card_id] if card_id else [], actor=actor)
        note_applied(plan, before, out, actor=actor)
        for ev in out:
            if ev["n"] == 0:
                continue
            if ev["kind"] == "player_counters":
                plan.do({"type": "resource", "player": ev["player"], "key": ev["counter"], "delta": ev["n"], "group": group}, actor=ev.get("by") or actor)
                continue
            if ev["card"] in plan.state.cards:
                groups.setdefault((ev.get("by") or actor, ev["counter"], ev["n"]), []).append(ev["card"])
    # -- counters (wave 7C) -- several kinds at once are one instruction: its steps share a group (the batch the first
    # one gets), so "whenever you put one or more counters on a creature" triggers once (122.6)
    for (actor, kind, n), cards in groups.items():
        # The instruction and replacement plan are already fixed. Table-action
        # input bounds do not limit its quantity; every chunk keeps one group.
        while n:
            chunk = max(-1000, min(1000, n))
            plan.do({"type": "counter", "card_ids": cards, "kind": kind, "delta": chunk, **({"group": group} if group else {})},
                    actor=actor)
            if receipt is not None and chunk > 0:
                from app.rules import context, counter_receipts

                receipt.extend(counter_receipts.CounterPlacement(destination=ref, kind=kind, amount=chunk)
                               for cid in cards if (ref := context.ref_of(plan, cid)) is not None)
            n -= chunk


def _run_counters(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    puts = [(p[0], p[1], int(p[2])) for p in request["puts"]]
    if put_counters(plan, puts, by=request["by"], effect=bool(request.get("effect", True)), then=then,
                    entering=request.get("entering"), answers=answers, newcomers=request.get("newcomers"), putters=request.get("putters"),
                    ctx=then.get("ctx") if then else None, receipt_bind=request.get("receipt_bind")):
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
            "step": {p: draws_this_step(plan, p) for p in plan.state.players}, "dredged": [],
            "would": dict(plan.rules.would_draw) if plan.rules.would_draw_turn == plan.state.turn.number else {},  # (-- draws (wave 110C) --)
            "hand": {p: len(plan.state.zones.get(zone_key(p, "hand"), [])) for p in plan.state.players}}


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
    if m.get("hand_empty") and sim["hand"].get(pid, 0) > 0:
        return False  # -- draw bodies (wave 28B) -- "while you have no cards in hand": as the draw would happen
    if m.get("max_speed"):
        from app.rules import speed

        if speed.of(plan, pid) < speed.MAX:  # 702.178a: "as long as you have max speed"
            return False
    if m.get("first_time_turn") and sim["would"].get(pid, 0) > 0:
        return False  # -- draws (wave 110C) -- "The first time you would draw a card each turn": an earlier draw event this turn, replaced or not, used it up
    if m.get("draw_step_only") and not (plan.state.turn.phase == "draw" and plan.active == pid):
        return False
    if m.get("not_first_in_draw_step"):
        # 504.1: the first card they draw in each of their draw steps (the turn-based draw)
        in_their_draw_step = plan.state.turn.phase == "draw" and plan.active == pid
        if in_their_draw_step and sim["step"].get(pid, 0) == 0:
            return False
    return True


def _dcount_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    """-- replacements: draws (wave 28B) -- "If you would draw one or more cards …" / "If an opponent would draw two or more cards …" (121.2a)."""
    pid, m = ev["player"], c.match
    if pid not in plan.live() or ev["n"] < int(m.get("min", 1)):
        return False
    who = m.get("who")
    if who == "you" and pid != c.controller or who == "opponent" and pid == c.controller:
        return False
    return m.get("hand_max") is None or sim["hand"].get(pid, 0) <= int(m["hand_max"])  # ("as long as you have one or fewer cards in hand")


def _dcount_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    if c.op["do"] == "add":
        return [{**ev, "n": ev["n"] + int(c.op["n"])}]
    if c.op["do"] == "each_one":  # "instead you and that player each draw a card" (121.7: the draws happen one at a time)
        order = plan.apnap()  # (121.2c: when several players draw, the active player first)
        # (review 28B: each is an instruction to draw one card, which another count replacement not yet applied may still change: 614.5,
        # 616.1f — Quantum Riddler's "one or more cards")
        return [{"kind": "draw_count", "player": p, "n": 1} for p in sorted(dict.fromkeys([c.controller, ev["player"]]),
                                                                             key=lambda p: order.index(p) if p in order else len(order))]
    return [ev]


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
    if op == "body":  # -- draw bodies (wave 28B) -- run by do_draws once everything before it has happened (app/rules/draw_bodies.py)
        return [{"kind": "body", "player": ev["player"], "effects": c.op["effects"],
                 "controller": ev["player"] if c.op.get("affected_controller") else c.controller,
                 "replacement_controller": c.controller, "targets": c.op.get("targets", []), "x": c.op.get("x", 0),
                 "source_card": c.source_card, "source_oid": c.source_oid, "label": c.label}]
    return [ev]


def _draw_perform(plan: Plan, ev: Event, sim: Sim) -> None:
    pid = ev["player"]
    left = sim["library"].get(pid, 0)
    if left > 0:
        sim["library"][pid] = left - 1
        sim["step"][pid] = sim["step"].get(pid, 0) + 1
        sim["hand"][pid] = sim["hand"].get(pid, 0) + 1


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
    more = sum(k for _, k in mill_counts(plan, [(pid, int(f["n"]))]) or [(pid, int(f["n"]))])  # (-- mill counts (wave 28B) -- 701.17a)
    plan.do({"type": "mill", "player": pid, "count": min(more, len(plan.state.zones.get(zone_key(pid, "library"), [])))}, actor=pid)
    if card is not None and card.zone == zone_key(pid, "graveyard"):
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": pid, "zone": "hand"}}, actor=pid)


def draw_cards(plan: Plan, players: list[str], n: int | dict[str, int], *, then: dict[str, Any] | None = None,
               answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None, exclude: list[str] | None = None,
               counted: bool = False) -> bool:
    """THE draw choke point (see the module docstring). 121.2: one card at a time; 121.2c: the
    active player draws all their cards first, then the others in turn order; 121.6a / 614.11:
    replacement effects apply even with an empty library; 704.5b: a draw from an empty library
    that isn't replaced loses the game at the next check. False while a choice is open.
    -- draw bodies (wave 28B) -- ``exclude``: replacement effects that already applied to the event these draws come from (614.5: a body's own
    "draw a card" isn't replaced by that effect again; the context of a body says so, ``repl_applied``). 121.6b: a body is completed before
    the draws after it; the plan stops at it and the rest is planned once it is done (the continuation ``draw_rest``), so False also
    means "a replacement effect is running and goes on by itself". ``counted``: the instruction's replacements that refer to the number of
    cards drawn (121.2a, 616.1g: "If you would draw one or more cards …") have already applied (the rest of a draw sequence after a body)."""
    answers = answers if answers is not None else _ctx_answers(ctx)
    exclude = list(exclude if exclude is not None else (ctx or {}).get("repl_applied") or [])
    order = plan.apnap()
    who = sorted([p for p in players if p in plan.live()], key=lambda p: order.index(p) if p in order else len(order))
    found = candidates(plan, ("draw", "draw_count"))  # (one scan of the table)
    cands = [*(c for c in found if c.event == "draw"), *dredge_candidates(plan, who)]
    sim = _draw_sim(plan, who)
    if then is None:  # (a site that can't pause can't run a replacement effect's choices: the players do it, 616.1)
        # (review 28B: only the effects that apply to one of these draws, the optional ones too; "the next time you would draw" is used up)
        for c in [c for c in cands if (c.op.get("do") == "body" or c.op.get("optional")) and c.id not in exclude
                  and any(_draw_applies(plan, c, {"kind": "draw", "player": p, "applied": exclude}, sim) for p in who)]:
            plan.note(f"{c.label} {'may' if c.op.get('optional') else 'would'} replace a draw here, and the engine can't ask: "
                      "apply it by hand (121.6)")
            if c.op.get("once") and (rec := next((r for r in plan.rules.replacements if f"r:{r.get('id')}" == c.id), None)) is not None:
                rec["spent"] = True
        cands = [c for c in cands if c.op.get("do") != "body"]
    planner = Planner(plan, cands, answers, ask=then is not None, stop_draw_sequence=True)
    # -- review 37 -- 101.2, 121.2 (Narset, Parter of Veils; Spirit of the Labyrinth): "can't draw more than one card each turn" is read one draw at a time, a
    # replacement's draws too ("draw two cards instead": only the first is allowed); a draw not allowed is ignored and no replacement effect applies to it; a draw a
    # replacement effect replaced (dredge, Notion Thief) was not drawn, so the next one may be (the Narset and Leovold rulings)
    from app.rules import prohibitions

    left: dict[str, list[int] | None] = {}

    seen: list[bool] = []  # (-- draws (wave 110C) -- whether the last draw event was allowed: a draw that can't happen isn't a time the player would draw)

    def allowed(ev: Event) -> bool:
        seen[:] = [ok := _allowed(ev)]
        return ok

    def _allowed(ev: Event) -> bool:
        if ev["kind"] != "draw":
            return True
        pid = ev["player"]
        if pid not in left:
            got = prohibitions.draw_left(plan, pid)
            left[pid] = list(got) if got is not None else None
        room = left[pid]
        if room is None or room[0] > 0:
            return True
        if room[0] == 0:
            plan.note(f"{plan.name(pid)} can't draw cards" if room[1] == 0 else f"{plan.name(pid)} can't draw more than {room[1]} card{'s' if room[1] != 1 else ''} each turn", actor=pid)
            room[0] = -1  # (noted once)
        return False

    def drawn(out: list[Event]) -> Any:
        def add(f: Event) -> None:
            out.append(f)
            if f["kind"] == "draw" and (room := left.get(f["player"])) is not None:
                room[0] -= 1
        return add

    planner.gate = allowed
    slots: list[str] = []
    marks: list[list[str]] = []  # -- replaced draws (wave 29C) -- parallel to ``slots``: the effects that changed the instruction a slot came from (121.2a)
    actions: list[tuple[Event, list[Event]]] = []
    cut: int | None = None
    count_planner = Planner(plan, [] if counted else [c for c in found if c.event == "draw_count"], answers, ask=then is not None)
    counts: list[tuple[Event, list[Event]]] = []  # (review 28B: the modified instructions, for the log)
    try:
        for pid in who:  # (a dict: each player's own count, wave 16B)
            k = max(0, int(n[pid] if isinstance(n, dict) else n))
            if k and count_planner.cands:  # -- replacements: draws (wave 28B) -- 121.2a: an instruction to draw N cards is modified first, 616.1g
                cev: Event = {"kind": "draw_count", "player": pid, "n": k, "applied": list(exclude)}
                counted_out: list[Event] = []
                count_planner.settle(cev, sim, counted_out.append)
                counts.append((cev, counted_out))
                for f in counted_out:
                    slots += [f["player"]] * f["n"] if f["kind"] == "draw_count" else [f["player"]] if f["kind"] == "draw" else []
                    marks += [list(f.get("applied") or [])] * (f["n"] if f["kind"] == "draw_count" else 1 if f["kind"] == "draw" else 0)
            else:
                slots += [pid] * k
                marks += [list(exclude)] * k
        if extra := [p for p in dict.fromkeys(slots) if p not in who]:  # (review 28B: Alms Collector's controller draws too: 702.52a dredge)
            planner.cands += dredge_candidates(plan, extra)
        counters = {c.id for c in found if c.event == "draw_count"}  # (review 29C: a slot of an instruction whose number one of them changed)
        for i, pid in enumerate(slots):
            ev: Event = {"kind": "draw", "player": pid, "applied": list(marks[i])}  # (the same as ``exclude`` unless a count replacement applied)
            if counters & set(marks[i]):
                ev["counted"] = True
            out: list[Event] = []
            planner.settle(ev, sim, drawn(out))
            if seen and seen[0]:
                sim["would"][pid] = sim["would"].get(pid, 0) + 1  # (-- draws (wave 110C) -- this slot was a time the player would draw)
            seen.clear()
            actions.append((ev, out))
            if any(f["kind"] in ("dredge", "body") for f in out):
                cut = i  # (-- static_other sweep (wave 16B) -- a dredge mills cards that may be dredged for the next draw: the draws after it
                break  # are planned again once it has happened; likewise after a body, 121.6b)
    except Ask as q:
        request = {"players": who, "n": n, "exclude": exclude, "counted": counted}
        if _pause(plan, q, answers, _resume_for(then, "draw", request)):
            return False
        raise
    plan.rules.would_draw_turn, plan.rules.would_draw = plan.state.turn.number, dict(sim["would"])
    left_to_players(plan, planner)
    left_to_players(plan, count_planner)
    for before, finals in counts:
        note_applied(plan, before, finals, actor=before["player"])
    for rec in plan.rules.replacements:  # -- replacements: draws (wave 28B) -- "The next time you would draw a card this turn": one draw, then spent
        if rec.get("kind") == "replace" and (rec.get("op") or {}).get("once") and f"r:{rec['id']}" in planner.used:
            rec["spent"] = True
    rest: dict[str, int] = {}
    for pid in slots[cut + 1:] if cut is not None else ():
        rest[pid] = rest.get(pid, 0) + 1
    # (review 28B: the players of the slots left, not of the instruction — "you and that player each draw a card" adds Alms Collector's controller)
    # (wave 29C: the draws left after a body / a dredge are still the result of the count replacement that applied to their instruction)
    kept = list(dict.fromkeys([*exclude, *(m for ms in marks for m in ms)]))
    after: dict[str, Any] = {"do": "draw_rest", "players": list(rest), "n": rest, "then": then, "exclude": kept}  # (already counted)
    if planner.pending_draws:
        after = {"do": "draw_pending", "pending": planner.pending_draws, "then": after}
    if do_draws(plan, actions, after):
        return False
    if planner.pending_draws:
        _then_draw_pending(plan, after)
        return False
    if rest:
        return draw_cards(plan, list(rest), rest, then=then, answers={}, exclude=kept, counted=True)
    return True


def _then_draw_rest(plan: Plan, then: dict[str, Any]) -> None:
    """-- draw bodies (wave 28B) -- a replacement effect is done: the draws that were left, then what the instruction goes on with."""
    if not then["players"] or draw_cards(plan, list(then["players"]), dict(then["n"]), then=then["then"], answers={},
                                         exclude=list(then.get("exclude") or []), counted=True):
        run_then(plan, then["then"])


def _then_draw_pending(plan: Plan, then: dict[str, Any]) -> None:
    """121.6b: finish unprocessed draws inside a replacement before the outer sequence."""
    pending = list(then["pending"])
    if not pending:
        run_then(plan, then["then"])
        return
    first, rest = pending[0], pending[1:]
    assert first["kind"] == "draw"
    after = {"do": "draw_pending", "pending": rest, "then": then["then"]} if rest else then["then"]
    if draw_cards(plan, [first["player"]], 1, then=after, answers={}, exclude=list(first.get("applied") or []), counted=True):
        run_then(plan, after)


THEN["draw_pending"] = _then_draw_pending


def do_draws(plan: Plan, actions: list[tuple[Event, list[Event]]], after: dict[str, Any] | None = None) -> bool:
    """The final events of a draw sequence, in order: consecutive draws by one player are one
    table step (each card is still its own "drew" event, 121.2). True when a body (wave 28B) was run last: ``after`` goes on once it is
    done (the plan stops at a body, so nothing follows it)."""
    r = plan.rules
    # (player, how: "replaced" — drawn as a result of a replacement effect, 614.11b, wave 29C; "counted" — by an instruction a replacement
    # effect changed the number of, 121.2a, review 29C; "" — neither)
    run: list[tuple[str, str, list[str]]] = []

    def flush() -> None:
        if not run:
            return
        pid, k = run[0][0], len(run)
        how = [h for _, h, _ in run]
        ancestry = [applied for _, _, applied in run]
        run.clear()
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        drawn = min(k, len(library))
        if drawn:
            top = list(library[:drawn])
            # A table Draw action carries at most100 cards; the rules instruction
            # remains one planned sequence with no intervening priority or SBA.
            for start in range(0, drawn, 100):
                plan.do({"type": "draw", "player": pid, "count": min(100, drawn - start)}, actor=pid)
            if (draw_log := turn_log_now(plan.state)) is not None:
                for c, applied in zip(top, ancestry, strict=False):
                    draw_log.drawn_applied[plan.rules.object_id(c)] = applied
            if (log := turn_log_now(plan.state)) is not None and any(how[:drawn]):  # -- replaced draws (wave 29C) -- 121.6c, 614.11b:
                for c, h in zip(top, how, strict=False):  # "reveal them" etc. isn't done to cards a replacement effect drew
                    if h:
                        (log.drawn_counted if h == "counted" else log.drawn_replaced).setdefault(pid, []).append(plan.rules.object_id(c))
            from app.rules import (
                miracle,  # -- casting extras (wave 18E) -- 702.94a: the first card drawn this turn
            )

            miracle.on_draw(plan, pid, top)
            from app.rules import first_reveal100b

            first_reveal100b.on_draw(plan, pid, top)  # -- if you do (wave 100B) -- "Reveal the first card you draw each turn" (Rowen)
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
                if run and run[0][0] != f["player"]:
                    flush()
                # (a replaced draw's events carry the effects applied, 616.1; the slot of a changed instruction says so: ``draw_cards``)
                run.append((f["player"], "counted" if before.get("counted") else "replaced" if f.get("applied") else "", list(f.get("applied") or [])))
            elif f["kind"] == "win":
                flush()
                _win(plan, f["player"])
            elif f["kind"] == "body":  # -- draw bodies (wave 28B) -- 121.6b: completed before the draws after it (draw_bodies.py)
                flush()
                from app.rules import draw_bodies

                draw_bodies.run(plan, f, after or {"do": "draw_rest", "players": [], "n": {}, "then": None})
                return True
    flush()
    return False


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
    if draw_cards(plan, list(request["players"]), n if isinstance(n, dict) else int(n), then=then, answers=answers,
                  exclude=list(request.get("exclude") or []), counted=bool(request.get("counted"))):
        run_then(plan, then)


# == life gain (119.9, 119.10) =======================================================================
def _life_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["n"] <= 0 or ev["player"] not in plan.live():
        return False  # 119.10: gaining 0 life isn't a life gain event
    if c.match.get('players') is not None and ev['player'] not in c.match['players']:
        return False
    who = c.match.get("who")
    if who == "you" and ev["player"] != c.controller or who == "opponent" and ev["player"] == c.controller:
        return False
    if c.match.get("by_controller") and (ev["key"] != ev["player"] or ev.get("actor") != ev["player"]):
        return False  # -- life gain (wave 110H) -- Rain of Gore: only a spell or ability gain of its controller; lifelink (key = source card, 702.15b) is damage's result, not a spell or ability
    cap = c.match.get("life_max")  # -- life modifiers (wave 28B) -- "while you have 5 or less life": as the gain would happen (119.10)
    return cap is None or plan.state.players[ev["player"]].life <= int(cap)  # (review 28B: one call's gains are simultaneous, 702.15e)


def _loss_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    """-- life modifiers (wave 28B) -- "If an opponent would lose life during your turn, they lose twice that much life instead" (119.3, 614.1a)."""
    if ev["n"] <= 0 or ev["player"] not in plan.live():
        return False  # (losing 0 life isn't a life loss event, as for 119.10)
    who, mine = c.match.get("who"), ev["player"] == c.controller
    if who == "you" and not mine or who == "opponent" and mine:
        return False
    if c.match.get("damage") and not ev.get("damage"):
        return False  # -- life floor (wave 35C) -- "damage that would reduce your life total": the life damage makes a player lose (120.3a), not other loss
    if c.op["do"] == "floor":  # the loss would take them below 1 life from 1 or more (a player already below 1 is dealt damage as normal)
        life, keep = plan.state.players[ev["player"]].life, int(c.op.get("to", 1))  # (wave 110B: Elderscale Wurm keeps 7)
        if life < keep or ev["n"] < life - keep + 1:
            return False
    if (cond := c.match.get("if")) is not None:
        from app.rules import conditions

        if not conditions.holds(plan, {"controller": c.controller, "source_card": c.source_card}, cond):
            return False
    return c.match.get("turn") != "yours" or plan.active == c.controller


def _loss_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op
    if op["do"] == "mul":
        return [{**ev, "n": ev["n"] * int(op["n"])}]
    if op["do"] == "floor":  # (applies only with 1 or more life and a loss of at least that much) they keep 1 life
        return [{**ev, "n": plan.state.players[ev["player"]].life - int(op.get("to", 1))}]
    return [ev]


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
              cands: list[Candidate] | None = None, actor: str | None = None) -> tuple[list[tuple[Event, list[Event]]], Planner] | Ask:
    """Life gain events ([(player, n, key)], each its own event: 702.15e) through 616.1."""
    planner = Planner(plan, cands if cands is not None else candidates(plan, ("life", "life_loss")), answers, ask=ask)
    sim: Sim = {}  # (review 28B: the gains of one call happen at the same time, 702.15e: a condition reads the life total before them)
    order = plan.apnap()
    evs: list[Event] = [{"kind": "life", "player": p, "n": int(n), "key": key, "applied": [], "actor": actor} for p, n, key in gains]
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
            planner.settle(ev, sim, out.append)
            finals.append((ev, out))
    except Ask as q:
        return q
    return finals, planner


def _life_operation(plan: Plan, operation: int | None) -> int:
    if operation is not None and operation > 0:
        return operation
    plan.rules.next_life_operation += 1
    return plan.rules.next_life_operation


def gain_life(plan: Plan, gains: list[tuple[str, int]], *, actor: str, then: dict[str, Any] | None = None,
              answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None, operation: int | None = None) -> bool:
    """THE life-gain choke point (see the module docstring). False while a choice is open."""
    operation = _life_operation(plan, operation)
    answers = answers if answers is not None else _ctx_answers(ctx)
    planned = plan_life(plan, [(p, n, p) for p, n in gains], answers=answers, ask=then is not None, actor=actor)
    if isinstance(planned, Ask):
        request = {"gains": [list(g) for g in gains], "actor": actor, "operation": operation}
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
                from app.rules import (
                    life_lock,  # -- can't lose life (wave 29D) -- 614.17c: "loses that much life instead" of a player who can't
                )

                for pid, n in life_lock.keep(plan, [(ev["player"], ev["n"])], actor=actor):
                    plan.do({"type": "life", "player": pid, "delta": -n, "group": operation}, actor=actor)
    return True


def _run_life(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    if gain_life(plan, [(g[0], int(g[1])) for g in request["gains"]], actor=request["actor"], then=then, answers=answers, operation=request.get("operation")):
        run_then(plan, then)


# == life loss (119.3, 119.4, 118.11, 614.1a) ========================================================
def plan_loss(plan: Plan, losses: list[tuple[str, int]], *, answers: dict[str, str], ask: bool,
              cands: list[Candidate] | None = None, damage: bool = False) -> tuple[list[tuple[Event, list[Event]]], Planner] | Ask:
    """-- life modifiers (wave 28B) -- life loss events ([(player, n)], each its own event) through 616.1. ``damage``: the life damage makes them
    lose (120.3a; wave 35C: "damage that would reduce your life total to less than 1" reads those and no other loss)."""
    planner = Planner(plan, cands if cands is not None else candidates(plan, "life_loss"), answers, ask=ask)
    order = plan.apnap()
    evs: list[Event] = [{"kind": "life_loss", "player": p, "n": int(n), "applied": [], **({"damage": True} if damage else {})}
                        for p, n in losses if n > 0]
    evs.sort(key=lambda e: order.index(e["player"]) if e["player"] in order else len(order))
    sim: Sim = {}
    finals: list[tuple[Event, list[Event]]] = []
    try:
        for ev in evs:
            out: list[Event] = []
            planner.settle(ev, sim, out.append)
            finals.append((ev, out))
    except Ask as q:
        return q
    return finals, planner


def lose_life(plan: Plan, losses: list[tuple[str, int]], *, actor: str | None = None, then: dict[str, Any] | None = None,
              answers: dict[str, str] | None = None, ctx: dict[str, Any] | None = None, as_gain: bool = False,
              receipt: list[int] | None = None, bind: str | None = None, operation: int | None = None, paid: bool = False) -> bool:
    """THE life-loss choke point (wave 28B): every way a player loses life that isn't damage's own result (effects, a payment of life: 119.4
    "the player loses that much life", 118.11 a payment may be modified by effects) goes through the "would lose life" replacements.
    With none in force, each player just loses it. False while a choice is open."""
    if receipt is not None:
        receipt.clear()
    losses = [(p, int(n)) for p, n in losses if n > 0 and p in plan.state.players]
    from app.rules import (
        life_lock,  # -- can't lose life (wave 29D) -- 119.8, 614.17c: a loss that can't happen isn't an event, nothing replaces it
    )

    losses = life_lock.keep(plan, losses, actor=actor)
    if not losses:
        return True
    operation = _life_operation(plan, operation)
    if not candidates(plan, "life_loss"):
        for pid, n in losses:
            if receipt is not None and not as_gain:
                receipt.append(n)
            if as_gain:  # -- counters (wave 44C) -- "gain life rather than lose life from radiation" (728.1a): the gain event, through the gain replacements
                gain_life(plan, [(pid, n)], actor=actor or pid, operation=operation)
            else:
                plan.do({"type": "life", "player": pid, "delta": -n, "group": operation, **({"paid": True} if paid else {})}, actor=actor or pid)
        return True
    answers = answers if answers is not None else _ctx_answers(ctx)
    planned = plan_loss(plan, losses, answers=answers, ask=then is not None)
    if isinstance(planned, Ask):
        request = {"losses": [list(x) for x in losses], "actor": actor, "bind": bind, "operation": operation, "paid": paid}
        if _pause(plan, planned, answers, _resume_for(then, "loss", request)):
            return False
        raise planned
    finals, planner = planned
    left_to_players(plan, planner)
    for before, out in finals:
        note_applied(plan, before, out, actor=actor)
        for ev in out:
            if ev["kind"] == "life_loss" and ev["n"] > 0:
                if receipt is not None and not as_gain:
                    receipt.append(int(ev["n"]))
                if as_gain:  # (wave 44C)
                    gain_life(plan, [(ev["player"], ev["n"])], actor=actor or ev["player"], operation=operation)
                else:
                    plan.do({"type": "life", "player": ev["player"], "delta": -ev["n"], "group": operation, **({"paid": True} if paid else {})}, actor=actor or ev["player"])
    return True


# == mill (701.17, 614.1a) ==========================================================================
def _mill_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    """-- mill counts (wave 28B) -- "If an opponent would mill one or more cards, they mill twice that many cards instead." (Bruvac, The Water Crystal)"""
    who, mine = c.match.get("who"), ev["player"] == c.controller
    return ev["n"] > 0 and ev["player"] in plan.live() and not (who == "you" and not mine or who == "opponent" and mine)


def _mill_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    if c.op["do"] == "mul":
        return [{**ev, "n": ev["n"] * int(c.op["n"])}]
    if c.op["do"] == "add":
        return [{**ev, "n": ev["n"] + int(c.op["n"])}]
    return [ev]


def mill_counts(plan: Plan, wants: list[tuple[str, int]], *, then: dict[str, Any] | None = None, answers: dict[str, str] | None = None,
                ctx: dict[str, Any] | None = None) -> list[tuple[str, int]] | None:
    """THE mill choke point (wave 28B): how many cards each player mills once the "would mill" replacements have applied to the
    number the instruction says (701.17a: the library may hold fewer — the caller mills what is there). The count is the event,
    so the caller mills after this returns. None while a choice is open (``then`` continues the instruction)."""
    wants = [(p, int(n)) for p, n in wants if n > 0 and p in plan.state.players]
    cands = candidates(plan, "mill")
    if not cands or not wants:
        return wants
    answers = answers if answers is not None else _ctx_answers(ctx)
    planner = Planner(plan, cands, answers, ask=then is not None)  # (``then``: the instruction run again with the answers, replace.rerun_then)
    order = plan.apnap()
    evs: list[Event] = [{"kind": "mill", "player": p, "n": n, "applied": []} for p, n in wants]
    evs.sort(key=lambda e: order.index(e["player"]) if e["player"] in order else len(order))
    finals: list[tuple[Event, list[Event]]] = []
    try:
        for ev in evs:
            out: list[Event] = []
            planner.settle(ev, {}, out.append)
            finals.append((ev, out))
    except Ask as q:
        if _pause(plan, q, answers, _resume_for(then, "mill", {"wants": [list(w) for w in wants]})):
            return None
        raise
    left_to_players(plan, planner)
    result: list[tuple[str, int]] = []
    for before, out in finals:
        note_applied(plan, before, out, actor=before["player"])
        result.append((before["player"], sum(f["n"] for f in out if f["kind"] == "mill")))
    return result


# == keyword actions (wave 35C) -- 614.1a: scry, explore and connive replaced by other instructions ======================================
def _action_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    """"If a creature you control would explore / connive": the creature is one its controller (the effect's) controls; "If you would scry a number of
    cards": at least one (scrying 0 is no scry, 701.22b)."""
    if ev["player"] not in plan.live() or ev["player"] != c.controller:
        return False
    if ev["kind"] == "scry":
        return int(ev["n"]) >= 1
    if ev["kind"] == "proliferate":  # (-- keyword actions (wave 50F) -- 701.34a: the player proliferates)
        return True
    card = plan.state.cards.get(ev.get("card") or "")
    return card is not None and card.zone.endswith(":battlefield") and plan.ch(card).is_creature and card.controller == c.controller


def _action_apply(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> list[Event]:
    op = c.op

    def body(effects: list[dict[str, Any]]) -> Event:
        return {"kind": "body", "player": ev["player"], "effects": copy.deepcopy(effects), "controller": c.controller, "label": c.label,
                "source_card": c.source_card, "source_oid": c.source_oid}

    if op["do"] == "again":  # two explores, neither replaced again by this effect (614.5)
        return [dict(ev), dict(ev)]
    if op["do"] == "before":
        return [body(op["effects"]), dict(ev)]
    if op["do"] == "draw":  # the scry never happens (614.6): they draw that many instead
        return [body([{"do": "draw", "who": "you", "n": int(ev["n"])}])]
    if op["do"] == "plus":  # -- keyword actions (wave 50G) -- "scry that many cards plus one instead" (Kenessos): the same scry, one card deeper (614.1a)
        return [{**ev, "n": int(ev["n"]) + 1}]
    return [ev]


def run_effects(plan: Plan, ctx: dict[str, Any], effects: list[dict[str, Any]], *, controller: str | None = None) -> bool:
    """A replacement's instructions as a small resolution of its own (like a draw body, 121.6b): they run in order with the context of the replaced
    instruction (its targets and event), and the resolution that instruction was part of goes on once they are done. False: it is running (or waiting
    for a choice); the caller returns it."""
    from app.rules import effects as fx

    inner = copy.deepcopy({k: v for k, v in ctx.items() if k != "body_done"})
    inner.update({"effects": copy.deepcopy(effects), "next": 0, "body_done": {"do": "continue", "ctx": ctx}})
    inner.pop(ANSWERS, None)
    inner.pop(SHIELDS, None)
    if controller:
        inner["controller"] = controller
    fx.continue_effects(plan, inner)
    return False


def keyword_replace(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], kind: str, pid: str, *, card: str | None = None, n: int = 1) -> bool | None:
    """THE choke point of scry / explore / connive (wave 35C): None when no replacement effect applies (the caller does the action), False when one
    did (what it makes runs as a resolution of its own, the caller returns False) or a choice is open (616.1: the instruction runs again with the
    answer, ``rerun_then``)."""
    cands = candidates(plan, kind)
    if not cands:
        return None
    card_obj = plan.state.cards.get(card or "")
    ev: Event = {"kind": kind, "player": pid, "n": int(n), "card": card, "name": (card_obj.name if card_obj is not None else None) or "A creature",
                 "applied": list(e.get("repl_applied") or [])}
    answers = _ctx_answers(ctx)
    then = rerun_then(ctx, e)
    planner = Planner(plan, cands, answers, ask=then is not None)
    out: list[Event] = []
    try:
        planner.settle(ev, {}, out.append)
    except Ask as q:
        if _pause(plan, q, answers, _resume_for(then, "keyword", {})):
            return False
        raise
    left_to_players(plan, planner)
    if not planner.used:
        return None
    note_applied(plan, ev, out, actor=pid)
    effects: list[dict[str, Any]] = []
    for f in out:
        if f["kind"] == "body":
            effects += f["effects"]
        else:
            effects.append({**e, **({"n": f["n"]} if f["kind"] == "scry" else {}), "repl_applied": list(f.get("applied") or [])})  # (wave 50G: a scry made deeper)
    first = next((f for f in out if f["kind"] == "body"), None)
    return run_effects(plan, ctx, effects, controller=first["controller"] if first is not None else None)


def _run_loss(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    receipt: list[int] = []
    if lose_life(plan, [(x[0], int(x[1])) for x in request["losses"]], actor=request["actor"], then=then, answers=answers,
                 receipt=receipt, bind=request.get("bind"), operation=request.get("operation"), paid=bool(request.get("paid"))):
        if request.get("bind") and then is not None and isinstance(then.get("ctx"), dict):
            from app.rules import context

            context.bind_amount(then["ctx"], request["bind"], sum(receipt))
        run_then(plan, then)


# == damage (120.4b, 614, 615, 616) ==================================================================
def source_info(plan: Plan, card_id: str | None, oid: str | None, ch: Any, controller: str | None) -> dict[str, Any]:
    """What a damage source is, for the statics' source filters (609.7c): its colors, types,
    subtypes, whether it's a spell on the stack, and its controller (as it last existed if gone)."""
    card = plan.state.cards.get(card_id or "")
    spell = bool(card is not None and card.zone == "stack" and card.ability is None)
    ctrl = controller
    counters: dict[str, int] = {}
    if card is not None and (card.zone.endswith(":battlefield") or card.zone == "stack") and (oid is None or plan.oid(card) == oid):
        ctrl, counters = card.controller, card.counters
    elif oid and oid in plan.rules.lki:
        ctrl, counters = plan.rules.lki[oid].controller, plan.rules.lki[oid].counters
    from app.rules.history import (
        log_for,  # -- counters (wave 44C) -- "a creature you control that entered this turn" (Neriv): the source's object entered the battlefield this turn
    )

    soid = oid or (plan.oid(card) if card is not None else None)
    from app.rules import wave110f_cards  # -- Ghostly Flame (wave 110F) --

    ch = wave110f_cards.damage_colors(plan, ch)
    return {"card": card_id, "controller": ctrl, "spell": spell, "entered": soid is not None and any(e.object_id == soid for e in log_for(plan, False).entered),
            "colors": sorted(ch.colors) if ch is not None else [], "types": sorted(ch.types) if ch is not None else [],
            "subtypes": sorted(ch.subtypes) if ch is not None else [],
            "keywords": sorted(ch.keywords) if ch is not None else [],
            "names": card_names.names_of(ch) if ch is not None else [],  # (wave 53B: "sources with the chosen name", 709.4a)
            "counters": {k: n for k, n in counters.items() if n > 0},  # (wave 51C: the kinds, "with a +1/+1 counter on it", Uncivil Unrest)
            "has_counters": any(n > 0 for n in counters.values()),  # (-- counters (wave 41A) -- "a creature you control with a counter on it", Raphael, the Muscle)
            "mv": None if ch is None else stack_interaction.mana_value(card if spell else None, ch)}  # (-- cant restrictions (wave 46A) -- Obosh: 202.3e)


def _source_matches(plan: Plan, spec: dict[str, Any], c: Candidate, ev: Event) -> bool:
    from app.rules import scoped_prevention_effects

    if not scoped_prevention_effects.source_matches(plan, spec, ev):
        return False
    from app.rules import conditional_prevention_effects

    if not conditional_prevention_effects.source_matches(plan, spec, c, ev):
        return False
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
    if spec.get("sel"):  # -- redirection statics (wave 50E) -- "damage ... by unblocked creatures": the source, while it is that object on the battlefield, matched as a selector (509.1h)
        from app.rules import selectors

        source = plan.state.cards.get(ev.get("source_card") or "")
        if source is None or plan.oid(source) != ev.get("source_oid") or not source.zone.endswith(":battlefield") or not selectors.matches(
                plan, selectors.from_key(spec["sel"]), source, plan.ch(source), c.controller, c.source_card):
            return False
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
    if spec.get("entered") and not src.get("entered"):  # (wave 44C)
        return False
    if spec.get("has_counters") and not src.get("has_counters"):  # (wave 41A: a source with a counter of any kind on it as it would deal the damage)
        return False
    if spec.get("has_counter") and not (src.get("counters") or {}).get(spec["has_counter"]):  # (wave 51C: a counter of that kind on the source as it would deal the damage)
        return False
    if spec.get("mv_parity") and (src.get("mv") is None or src["mv"] % 2 != (spec["mv_parity"] == "odd")):  # (wave 46A)
        return False
    if spec.get("colors") and not set(spec["colors"]) & set(src.get("colors") or ()):
        return False
    if spec.get("chosen_color"):  # (-- prevention riders (wave 17A) -- "sources of the chosen color": its permanent's choice, 614.12a)
        from app.rules import selectors

        color = selectors.COLORS.get((selectors.source_choice(plan, c.source_card, "color") or "").lower())
        if color is None or color not in (src.get("colors") or ()):
            return False
    if spec.get("chosen_name"):  # -- chosen filters (wave 53B) -- "sources with the chosen name": its permanent's choice (614.12a), one of the source's names (709.4a)
        from app.cards.names import normalize_name

        chosen_name = card_names.chosen(plan, c.source_card)
        if not chosen_name or normalize_name(chosen_name) not in {normalize_name(n) for n in src.get("names") or ()}:
            return False
    if spec.get("chosen_type"):  # -- one-shot shields (wave 35A) -- "a creature of the chosen type" (Circle of Solace): its permanent's choice, 614.12a
        from app.rules import selectors

        kind = (selectors.source_choice(plan, c.source_card, "creature type") or "").strip()
        if not kind or kind not in (src.get("subtypes") or ()):
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
    if spec.get("chosen_player_or_controlled"):
        from app.rules import keyed_player_bindings

        return keyed_player_bindings.recipient(plan, c.source_card, c.source_oid, target)
    if target in plan.state.players:
        if spec.get("pids") is not None:  # (-- prevention riders (wave 17A) -- the player a shield was made for)
            return target in spec["pids"]
        want = spec.get("players")
        if want is None:
            return False
        if want == "enchanted":  # -- instead (wave 100K) -- the player the source Aura is attached to now (702.5d)
            source = plan.state.cards.get(c.source_card or "")
            return source is not None and source.attached_player == target
        return not (want == "you" and target != c.controller or want == "opponent" and target == c.controller)
    objects = spec.get("objects")
    if objects is None:
        return False
    card = plan.state.cards.get(target)
    if card is None or not card.zone.endswith(":battlefield"):
        return False
    return _object_matches(plan, objects, c, card, plan.ch(card), ev.get("target_oid"))


def _finite_prevention_key(candidate: Candidate, event: Event) -> str:
    if candidate.op.get('budget_scope') == 'source_batch':
        from app.rules.source_batch_prevention import budget_key

        return budget_key(candidate, event)
    return 'limited:' + candidate.id


def _damage_applies(plan: Plan, c: Candidate, ev: Event, sim: Sim) -> bool:
    if ev["amount"] <= 0:
        return False  # 614.7a: a source dealing 0 damage deals no damage: nothing to replace or prevent
    # -- refused grants/replacements (wave 3R2) -- 615.12: a prevention effect applied to damage that can't be
    # prevented prevents none of it and a shield isn't reduced; none the engine applies has an additional effect
    # (app/rules/source_shields.py), so it isn't applied at all. 615.8: a "next time" shield is used up once.
    if (c.prevention or c.legacy is not None) and ev.get("unpreventable") and not (
            (c.op.get("rider") and c.id.startswith("s:")) or c.op.get("consume_unpreventable")):  # (-- prevention riders (wave 17A) -- a static's additional effect
        return False  # still takes place, 615.12; a record's or shield's riders all count the damage prevented: none)
    from app.rules import source_shields

    if (ev.get("unredirectable110h") or source_shields.cant_redirect110g(plan, ev)) and c.op.get("do") == "redirect":  # -- Lava Burst (wave 110H) -- 614.9: that damage can't be dealt instead to another
        return False
    if c.op.get("once") and not c.op.get("batch") and f"once:{c.id}" in sim.get("shields", {}):  # (wave 35A: ``batch``, see Planner.applies)
        return False
    # -- end refused grants/replacements (wave 3R2) --
    if c.op.get("protection_target"):
        from app.rules import damage_protection

        return damage_protection.applies(plan, c, ev)
    if c.legacy is not None:  # a stage-1 "prevent all …" static or this turn's record
        from app.rules import replacements

        return replacements._applies(plan, c.legacy, ev)
    if c.op["do"] == "shield":
        # 615.7: a shield prevents only damage to what it protects
        return c.op["key"].split("#")[0] == _shield_key(plan, ev["target"]) and sim.get("shields", {}).get(c.op["key"], 0) > 0
    if c.op["do"] == "scoped_shield" and sim.get("shields", {}).get(c.op["key"], 0) <= 0:
        return False
    m = c.match
    if m.get("combat") is not None and bool(m["combat"]) != bool(ev.get("combat")):
        return False
    if m.get("monarch") and plan.state.table.monarch != c.controller:  # (-- prevention riders (wave 17A) -- "while you're the monarch")
        return False
    if m.get("attacking") and ((holder := plan.state.cards.get(c.source_card or "")) is None or not holder.is_attacking):
        return False
    if m.get("untapped") and ((holder := plan.state.cards.get(c.source_card or "")) is None or holder.tapped):  # -- redirection statics (wave 50E) -- "As long as this creature is untapped"
        return False
    if m.get("max_speed"):  # -- damage sized by a count (wave 34D) -- 702.178a: "As long as you have max speed, if a source you control would deal damage …"
        from app.rules import speed

        if speed.of(plan, c.controller) < speed.MAX:
            return False
    if m.get("below_value") is not None and ev["amount"] >= _added_value(plan, c, m["below_value"]):
        return False  # 616.1: another replacement may have raised this event above the current threshold.
    if m.get("at_least") and ev["amount"] < m["at_least"]:
        return False  # -- instead (wave 20B) -- "If a source would deal 4 or more damage …": judged on the amount as it is now (614.6)
    if c.op["do"] == "redirect":  # -- refused grants/replacements (wave 3R2) -- 614.9: nowhere to redirect to: nothing
        from app.rules import source_shields

        if source_shields.redirect_target(plan, c, ev) is None:
            return False
        if c.op.get("limit") is not None and (int(c.op["limit"]) <= 0 or
                (sim.get("shields", {}).get(f"redir:{c.id}", c.op["limit"]) <= 0 and not c.op.get("allocate"))):
            return False  # (-- prevention riders (wave 17A) -- "the next 1 damage": used up)
    if c.op["do"] == "finite_prevention":
        left = sim.get("shields", {}).get(_finite_prevention_key(c, ev), c.op["limit"])
        if int(c.op["limit"]) <= 0 or (left <= 0 and not c.op.get("allocate")):
            return False
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
            if op.get("allocate"):
                from app.rules import single_recipient_redirection

                k = single_recipient_redirection.amount(sim, c, ev, left)
            else:
                k = min(k, left)
            shields[f"redir:{c.id}"] = left - k
        if op.get("once"):  # (the next time a source would deal damage: used up by this instance, 615.8)
            sim.setdefault("shields", {})[f"once:{c.id}"] = 0
        if k <= 0:
            return [dict(ev)]
        moved = source_shields.redirect(plan, c, {**ev, "amount": k})
        return [moved, {**ev, "amount": int(ev["amount"]) - k}] if k < int(ev["amount"]) else [moved]
    if op.get("shield_counter"):
        used = sim.setdefault("shield_counter_used", [])
        if op["shield_counter"] not in used:
            used.append(op["shield_counter"])
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
    elif kind == "set_value":
        n = max(0, _added_value(plan, c, op["value"]))
    elif kind == "cap":  # -- instead (wave 20B) -- "that source deals 3 damage instead" (the threshold was met: the amount is above the cap)
        n = int(op["n"])
    elif kind == "prevent":
        n = max(0, n - int(op["n"]) - (_added_value(plan, c, op["value"]) if op.get("value") else 0))
    elif kind == "prevent_half_up":  # -- damage wordings (wave 6B) -- prevent half, rounded up: half rounded down is left
        n //= 2
    elif kind == "prevent_half_down":  # -- one-shot shields (wave 35A) -- Dark Sphere: prevent half, rounded down: the rest is dealt
        n -= n // 2
    elif kind == "prevent_all_but":
        n = min(n, int(op["n"]))
    elif kind == "prevent_all" or kind == "body":  # (-- damage bodies (wave 35C) -- a replaced damage is never dealt, 614.6)
        n = 0
    elif kind == "finite_prevention":
        from app.rules import single_recipient_redirection

        shields = sim.setdefault("shields", {})
        key = _finite_prevention_key(c, ev)
        left = int(shields.get(key, op["limit"]))
        used = single_recipient_redirection.amount(sim, c, ev, left)
        shields[key] = left - used
        n -= used
    elif kind in ("shield", "scoped_shield"):  # 615.7: each 1 damage prevented reduces the shield by 1
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
        if int(ev["amount"]) > n:
            from app.rules import prevention_receipts

            row = prevention_receipts.receipt(c, ev, int(ev["amount"]) - n)
            out["prevention_receipts"] = [*(ev.get("prevention_receipts") or []), row]
    if (op.get("prevention") or kind in ("body", "observe110g")) and op.get("rider"):  # -- prevention riders (wave 17A) -- 615.5: the additional effect, once the damage has been dealt
        from app.rules import prevention_receipts

        out["riders"] = [*(ev.get("riders") or []), {"rider": op["rider"], "n": int(ev["amount"]) - n, "of": int(ev["amount"]), "by": c.controller,
                                                     "card": c.source_card, "oid": c.source_oid, "name": c.label,
                                                     "receipt": prevention_receipts.receipt(c, ev, int(ev["amount"]) - n)["id"],
                                                     "ev": {k: ev.get(k) for k in ("src", "source_card", "source_oid", "target", "target_oid", "combat")},
                                                     **({"batch": c.id} if op.get("batch") or op["rider"].get("aggregation") else {})}]
    return [out]


def damage_candidates(plan: Plan) -> list[Candidate]:
    """The damage effects in force: replacement and prevention statics, this turn's records, the
    stage-1 "prevent all" statics and records, and 615.7 shields."""
    from app.rules import damage_protection, replacements, shield_counters

    out = candidates(plan, "damage") + damage_protection.candidates(plan) + shield_counters.damage_candidates(plan)
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
    if any(candidate.op.get('frontier_age') for candidate in out):
        from app.rules import prevention_frontier_cards

        return prevention_frontier_cards.bind_candidates(plan, out)
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
    from app.rules import prevention_frontier_bridge as joint_prevention

    if joint_prevention.PREFIX in answers or joint_prevention.eligible(plan, events, cands):
        return joint_prevention.plan_damage(plan, events, answers=answers, order=order, ask=ask, cands=cands)
    planner = Planner(plan, cands, answers, ask=ask)
    sim: Sim = {"shields": {k: int(v) for k, v in plan.rules.prevention.items()}}
    from app.rules import single_recipient_redirection

    sim["redirect_allocations"] = single_recipient_redirection.allocations(answers)
    picks = list(order or [])
    for lineage, ev in enumerate(events):
        ev.setdefault("_damage_lineage", str(lineage))
        if any(c.op.get("allocate") for c in cands):
            ev.setdefault("_redirect_lineage", str(lineage))
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
                shield_left = _shield_left(sim, key)
                if shield_left <= 0:
                    # Scoped budgets share the same 615.7 source-order choice, but only
                    # between events to which that source/combat-filtered shield applies.
                    shared = [c for c in cands if c.op["do"] == "scoped_shield"
                              and sum(_damage_applies(plan, c, event, sim) for event in contenders) > 1]
                    contenders = [event for event in contenders if any(_damage_applies(plan, c, event, sim) for c in shared)]
                    shield_left = sum(sim["shields"].get(c.op["key"], 0) for c in shared)
                if len(contenders) > 1 and shield_left > 0 \
                        and len({replacements._shield_signature(plan, e) for e in contenders}) > 1:
                    # 615.7: which source's damage the shield prevents first
                    mine = [p for p in picks if p.startswith(f"{target}:")]
                    if mine:
                        pick = mine[0]
                        picks.remove(pick)
                        ev = next((e for e in contenders if f"{target}:{e['source_oid']}" == pick), contenders[0])
                    elif ask:
                        raise ShieldAsk(target, chooser_of(target), contenders, shield_left)
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
    if ask and (allocation := single_recipient_redirection.validate(plan, sim, cands, answers)) is not None:
        return allocation
    result = [e for i, ev in enumerate(events) for e in finals.get(i, [ev])]
    #122.1c: the native prevention candidate projected one counter removal per permanent.
    used = [str(cid) for cid in sim.get("shield_counter_used") or []]
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
    wither_by: dict[str, dict[str, int]] = field(default_factory=dict)  # (wave 17D) ... by the player who puts them (120.3d)
    poison: dict[str, int] = field(default_factory=dict)  # poison counters (120.3b, 702.164c), after their replacements
    poison_by: dict[str, dict[str, int]] = field(default_factory=dict)
    lifelink: dict[str, int] = field(default_factory=dict)  # life gained per source (702.15e), after its replacements
    losses: list[tuple[str, int]] = field(default_factory=list)  # a lifelink gain replaced by a loss (Tainted Remedy)
    deathtouched: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    shields: dict[str, int] = field(default_factory=dict)
    left: list[Planner] = field(default_factory=list)
    counter_finals: list[tuple[Event, list[Event]]] = field(default_factory=list)
    life_finals: list[tuple[Event, list[Event]]] = field(default_factory=list)
    shield_counters: list[str] = field(default_factory=list)  # (wave 7C) 122.1c
    preventions: list[dict[str, Any]] = field(default_factory=list)
    riders: list[dict[str, Any]] = field(default_factory=list)  # (wave 17A) the additional effects of prevention effects, 615.5


def _merged_riders(riders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine only the additional effects belonging to the same logical prevention occurrence."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    keys: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in riders:
        if r.get("receipt"):
            if r["receipt"] in seen:
                continue
            seen.add(r["receipt"])
        aggregation = r["rider"].get("aggregation")
        event = r.get("ev") or {}
        extra = (event.get("source_oid"),) if aggregation == "source" else ((event.get("target_oid") or event.get("target")),) if aggregation == "recipient" else ()
        key = (r.get("batch"), *extra)
        merge = bool(r.get("batch")) and (bool(aggregation) or not re.search(r"ref:to|from_ctrl|ref:prevented_source", json.dumps(r["rider"])))
        mine = keys.get(key) if merge else None
        if mine is not None:
            mine["n"] += r["n"]
            if "of" in r:
                mine["of"] = int(mine.get("of", 0)) + int(r["of"])
        else:
            row = dict(r)
            out.append(row)
            if merge:
                keys[key] = row
    return out


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
                        riders=_merged_riders([{**r, "ev": r.get("ev") or {k: ev.get(k) for k in ("src", "source_card", "source_oid", "target", "target_oid", "combat")}}
                                               for ev in planned.events for r in ev.get("riders") or []]))
    from app.rules import prevention_receipts

    out.preventions = prevention_receipts.collect(planned.events)
    from app.rules import life_total_damage_results43

    infect_players = life_total_damage_results43.infect_players(plan)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Everlasting Torment

    all_wither = static_perm100d.any_static(plan, static_perm100d.ALL_WITHER)
    counters: list[tuple[str, str, int, str]] = []  # (target, kind, n, by)
    gains: dict[str, int] = {}
    for ev in out.events:
        n = int(ev["amount"])
        kw = set(ev.get("kw") or ())
        key = ev["target"]
        by = (ev.get("src") or {}).get("controller") or ""
        if key in plan.state.players:
            if "infect" in kw or key in infect_players:
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
            elif {"wither", "infect"} & kw or all_wither:
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
                        mine = out.poison_by.setdefault(f["player"], {})
                        mine[by] = mine.get(by, 0) + f["n"]
                    else:
                        out.wither[f["card"]] = out.wither.get(f["card"], 0) + f["n"]
                        mine = out.wither_by.setdefault(f["card"], {})
                        mine[by] = mine.get(by, 0) + f["n"]
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
    from app.rules import (
        damage_life_results42,
        life_lock,  # -- can't lose life (wave 29D) -- 120.3a: the damage is still dealt (its events stay); the life loss that can't happen is no event
    )

    for pid in list(out.players):
        if (why := life_lock.why_not(plan, pid, "lose")) is not None:
            out.notes.append(f"{why}: {plan.name(pid)} can't lose life, so {out.players.pop(pid)} damage dealt to them makes them lose none")
        elif (why := damage_life_results42.why_not(plan, pid)) is not None:
            out.notes.append(f"{why}: {out.players.pop(pid)} damage dealt to {plan.name(pid)} doesn't cause life loss")
    if out.players and (loss_cands := candidates(plan, "life_loss")):
        # -- life modifiers (wave 28B) -- 120.3a: the life lost to damage is a life-loss event of its own (the damage dealt stays what it was):
        # "would lose life" replacements change it (Bloodletter of Aclazotz: "Damage causes loss of life.")
        planned_loss = plan_loss(plan, list(out.players.items()), answers=answers, ask=ask, cands=loss_cands, damage=True)
        if isinstance(planned_loss, Ask):
            return planned_loss
        loss_finals, loss_planner = planned_loss
        out.left.append(loss_planner)
        out.life_finals = [*out.life_finals, *loss_finals]
        out.players = {}
        for before, finals in loss_finals:
            lost = sum(f["n"] for f in finals if f["kind"] == "life_loss" and f["n"] > 0)
            if lost:
                out.players[before["player"]] = lost
    return out


def do_damage(plan: Plan, out: DamageOutcome, *, actor: str, combat: bool, extra: dict[str, Any] | None = None,
              then: dict[str, Any] | None = None) -> bool:
    """Commit damage once, then run immediate riders; false transfers the terminal to a saved body."""
    _commit_damage(plan, out, actor=actor, combat=combat, extra=extra)
    if not out.riders:
        return True
    from app.rules import damage_rider_continuations

    done = damage_rider_continuations.run(plan, damage_rider_continuations.DamageRiderFrame(out.riders, then or {"do": "noop"}))
    if not done and then is None:
        raise ValueError("Suspending prevention body requires a real damage continuation")
    return done


def _commit_damage(plan: Plan, out: DamageOutcome, *, actor: str, combat: bool, extra: dict[str, Any] | None = None) -> None:
    """Record a planned damage batch: one ``rules_damage`` step (one simultaneous event batch),
    then the defense counters removed from battles (120.3h) and any lifelink gain a replacement
    turned into a loss; the 615.7 shields as used; the replacement notes."""
    from app.rules import prevention_receipts

    prevention_receipts.commit(plan, out.preventions)
    for planner in out.left:
        left_to_players(plan, planner)
    for text in out.notes:
        plan.note(text, actor=actor)
    for before, finals in [*out.counter_finals, *out.life_finals]:
        note_applied(plan, before, finals, actor=actor)
    commit_shields(plan, out.shields)
    # -- counters (wave 7C) --
    from app.rules import shield_counters

    if not out.events:
        shield_counters.remove(plan, out.shield_counters, actor)
        return
    from app.rules import life_game_history

    dealt = [{"attacking_player": ev.get("attacking_player") if combat else None, "source_controller": (ev.get("src") or {}).get("controller"), "creature_names": life_game_history.damage_names(plan, ev), "source": ev["source_oid"], "target": ev["target"], "amount": int(ev["amount"]),
              **({"target_object": plan.oid(ev["target"])} if ev["target"] in plan.state.cards else {})} for ev in out.events]
    # -- trigger damage (wave 39B) -- 120.10, 120.4a: the excess damage the sources of this batch together dealt to each permanent (above the
    # lethal damage left, as it was before this damage; deathtouch 702.2c), on the first event of that permanent: "is dealt excess damage" triggers
    # and the turn's log read it (the one place lethal damage is computed for them, this_way.excess_by_target)
    from app.rules import this_way as _this_way

    for target, over in _this_way.excess_by_target(plan, out.events, note=False).items():
        if over > 0:
            next(d for d in dealt if d["target"] == target)["excess"] = over
    # (-- can't lose life (wave 29D) -- 120.3a: a player was dealt damage whether or not it made them lose life: bloodthirst reads the damage)
    for pid in [*out.players, *out.poison, *(d["target"] for d in dealt)]:
        if pid in plan.state.players:
            plan.rules.damaged[pid] = plan.state.turn.number
    from app.rules import wave110h_cards

    plan.do({"type": "rules_damage", "creatures": out.creatures, "players": out.players, "poison": out.poison, "poison_by": out.poison_by,
             "wither": out.wither, "wither_by": out.wither_by, "planeswalkers": out.walkers, "lifelink": out.lifelink, "combat": combat, "dealt": dealt,
             "heal110h": wave110h_cards.healed(plan, out.creatures),  # -- Wolverine, Fierce Fighter (wave 110H) --
             **(extra or {})}, actor=actor)
    for key, n in out.battles.items():
        have = plan.state.cards[key].counters.get("defense", 0) if key in plan.state.cards else 0
        if have:
            plan.do({"type": "counter", "card_ids": [key], "kind": "defense", "delta": -min(have, n)}, actor=actor)
    from app.rules import life_lock  # -- can't lose life (wave 29D) --

    for pid, n in life_lock.keep(plan, out.losses, actor=actor):  # (after the damage: its own step, UNVERIFIED batching)
        plan.do({"type": "life", "player": pid, "delta": -n}, actor=actor)
    plan.rules.deathtouched = list(dict.fromkeys([*plan.rules.deathtouched, *out.deathtouched]))
    shield_counters.remove(plan, out.shield_counters, actor)


def commit_shields(plan: Plan, shields: dict[str, int]) -> None:
    """The shields as the damage left them (615.7: used up by what they prevented)."""
    r = plan.rules
    # -- refused grants/replacements (wave 3R2) -- 615.8: a "next time" shield that prevented damage is used up
    used = {key[len("once:r:"):] for key in shields if key.startswith("once:r:")}
    for key, left in shields.items():  # -- prevention riders (wave 17A) -- what is left of "the next N damage is dealt to … instead"
        if key.startswith(("redir:r:", "limited:r:")):
            record_id = key.split(":", 2)[2]
            if left <= 0:
                used.add(record_id)
            else:
                for rec in r.replacements:
                    if rec.get("id") == record_id:
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
    from app.rules import prevention_frontier_bridge as joint_prevention
    from app.rules import replacements, single_recipient_redirection
    from app.rules.plan import decide

    if isinstance(s, joint_prevention.JointAsk):
        joint_prevention.ask(plan, s, resume, order)
        return

    if isinstance(s, single_recipient_redirection.AllocationAsk):
        single_recipient_redirection.ask(plan, s, resume, order)
        return
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
                            "draw": _draw_applies, "draw_count": _dcount_applies, "life": _life_applies, "life_loss": _loss_applies, "mill": _mill_applies,
                            "damage": _damage_applies, "scry": _action_applies, "explore": _action_applies, "connive": _action_applies, "proliferate": _action_applies}
_APPLY: dict[str, Any] = {"tokens": _tokens_apply, "counters": _counters_apply, "player_counters": _counters_apply,
                          "draw": _draw_apply, "draw_count": _dcount_apply, "life": _life_apply, "life_loss": _loss_apply, "mill": _mill_apply,
                          "damage": _damage_apply, "scry": _action_apply, "explore": _action_apply, "connive": _action_apply, "proliferate": _action_apply}
_PERFORM: dict[str, Any] = {"draw": _draw_perform, "dredge": _dredge_perform}
SITES: dict[str, Any] = {"tokens": _run_tokens, "counters": _run_counters, "draw": _run_draw, "life": _run_life, "loss": _run_loss}

from app.rules import copiable_coin_entry as _copiable_coin_entry  # noqa: E402

THEN.update(_copiable_coin_entry.THEN)

from app.rules import numeric_entry_roll42 as _numeric_entry_roll42  # noqa: E402, I001

THEN.update(_numeric_entry_roll42.THEN)

from app.rules import life_changes44 as _life_changes44  # noqa: E402, I001

SITES['life_changes44'] = _life_changes44.resume

from app.rules import random_cost_roll44 as _random_cost_roll44  # noqa: E402

THEN.update(_random_cost_roll44.THEN)
