"""Replacement and prevention effects (CR 614, 615): one place for each kind of event they modify.

Replacement effects "watch for a particular event that would happen and completely or partially
replace that event with a different event" (614.1); prevention effects do the same for damage
(615.1). Neither is locked in ahead of time: they apply as the event happens. So the engine applies
them at the three points where such events are produced, whichever rules code produces them:

* **entering the battlefield** — :func:`entry_plan` / :func:`move_onto_battlefield` /
  :func:`after_entry`: "~ enters tapped [unless …]" (614.1d), "As ~ enters, you may pay N life. If
  you don't, it enters tapped" (614.1c, a choice made before it enters: 614.12a), "~ enters [tapped]
  with N … counters on it" (614.1c; the counters are put on it as it enters: 122.6), a
  planeswalker's loyalty (306.5b). Every path onto the battlefield goes through here: a resolving
  permanent spell, a land play, an effect that puts a card onto the battlefield (search,
  reanimation, blink, unearth, persist / undying) and tokens being created.
* **a zone change** — :func:`replace_move` (called by ``Plan.do`` for every ``move`` / ``mill``
  step): unearth's "if it would leave the battlefield, exile it instead" (702.84a), "If ~ would die
  / be put into a graveyard from anywhere, exile it instead" (the object's own ability), "If a
  creature would die, exile it instead" statics of permanents on the battlefield, madness (702.35a)
  and 903.9b (a commander that would go to its owner's hand or library may go to the command
  zone instead).
* **damage** — "Prevent all [combat] damage that would be dealt [to …] [by …]" statics of
  permanents on the battlefield and "… this turn" effects of resolved spells (records in
  ``RulesState.replacements``: :func:`_records`, :func:`_applies`), and the "prevent the next N
  damage" shields (615.7), where the shielded player or the permanent's controller chooses which
  source's damage a shield prevents when several sources would deal it at once. Since stage 2 they
  apply with the damage replacement effects in app/rules/replace.py (``plan_damage``, 616.1).

What stage 1 does NOT do (kept honest rather than guessed): the 616.1 ordering choice when several
replacement effects would modify the same event differently (the ones here never conflict: every
applicable one sends the object to exile, or applies to a different aspect of entering), "enters
tapped / with counters" imposed by *other* permanents (614.1d, "Permanents your opponents control
enter tapped"), damage doubling / redirection (614.9), draw and life-gain replacements, and "can't be
prevented" (615.12: the engine doesn't model it yet, so no prevention is skipped on its account).

Permanents an effect puts onto the battlefield together enter simultaneously (:func:`move_together`:
one move step, 603.6a): their choices are all made first (614.12a), their replacements are judged
against the table before any of them enters (614.12: a land that "enters tapped unless you control
a Plains" doesn't see a Plains entering with it), and they are timestamped in APNAP order (613.7m).

Records live in ``RulesState.replacements`` as JSON (saved and replayed with the rest of the rules
state); every choice is a ``Decision`` with resume data, and prompts about a hidden card only go to
the player who may see it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import secrets
from typing import TYPE_CHECKING, Any, NamedTuple

from app.game.rules_state import CopyRecipe, DecisionOption
from app.game.state import CardInstance, TokenDef, zone_key
from app.rules import card_names, conditions, scripts, selectors, statics, values  # (card_names: wave 22B)
from app.rules import characteristics as chars

if TYPE_CHECKING:
    from app.rules.plan import Plan

Entry = dict[str, Any]  # {"card", "player", "actor", "tapped"?, "pay_life"?, "x"?, "gain_haste"?, "counter"?, "exile_if_leaves"?, "delayed"?}


def _definitions(plan: Plan, card: CardInstance) -> dict[int, dict[str, Any]]:
    """The card's own definitions, unless it was taken out of automation (never guess for those)."""
    if plan.manual(card):
        return {}
    return scripts.definitions(plan.ch(card))


# -- entering the battlefield (614.1c-d, 614.12, 122.6, 306.5b) --------------------------------------
def unless_holds(plan: Plan, controller: str, card: CardInstance, cond: dict[str, Any]) -> bool:
    """"~ enters tapped unless <condition>": checked as it enters, while it is still in the zone it
    comes from (it is not yet on the battlefield: "unless you control a Plains" is not met by itself)."""
    if "any" in cond:  # "unless you control a Plains or an Island"
        return any(unless_holds(plan, controller, card, c) for c in cond["any"])
    return conditions.holds(plan, {"controller": controller, "source_card": card.id}, cond)


def others_enter_untapped(plan: Plan, card: CardInstance, controller: str) -> bool:
    """-- most-played cards II (wave 45A) -- 614.1d: "Lands you control enter untapped." (Horizon Explorer): the same reading as ``others_enter_tapped``. Its ruling
    (2025-07-25): a permanent put onto the battlefield tapped by an instruction always enters untapped; against its own "enters tapped" the controller chooses the
    order, so can have either. ponytail: a land that "enters tapped" is modelled as always entering untapped; wave 50B: a shock land still asks for its life (that is
    the one choice with a payoff: "don't pay" applies the shock effect first and Spelunking after, untapped; never offered: the order that leaves it tapped)."""
    return others_enter_tapped(plan, card, controller, "enters_untapped_others")


def shock_prompt(name: str, n: int, untapped: bool = False) -> tuple[str, list[DecisionOption]]:
    """The question of a shock land's life (614.1c, 614.12a); ``untapped``: it enters untapped either way (-- Spelunking (wave 50B) -- 616.1)."""
    if untapped:
        return (f"{name}: pay {n} life? It enters untapped either way (lands you control enter untapped)",
                [DecisionOption(id="pay", label=f"Pay {n} life"), DecisionOption(id="tapped", label="Don't pay (still untapped)")])
    return (f"{name}: pay {n} life, or it enters tapped?",
            [DecisionOption(id="pay", label=f"Pay {n} life (untapped)"), DecisionOption(id="tapped", label="Enters tapped")])


def entry_plan(plan: Plan, card: CardInstance, controller: str, **kw: Any) -> dict[str, Any]:
    from app.rules import copiable_coin_entry, entry_characteristics

    if (answer := (kw.get("answers") or {}).get(copiable_coin_entry.WHAT)) is not None:
        copiable_coin_entry.ensure_form(plan, card, controller, answer)
    from app.rules import chosen_forms95

    chosen_forms95.ensure(plan, card, controller, kw.get("answers") or {})
    card = entry_characteristics.probe(card, kw.pop("entry_characteristics", None))
    out = _entry_plan(plan, card, controller, **kw)
    # -- static permanents (wave 100D) -- "As ~ enters, discard your hand." (614.1c, 614.12)
    from app.rules import static_perm100d

    static_perm100d.plan_entry(plan, card, controller, out, kw.get("answers"))
    from app.rules import numeric_entry_roll42

    if (receipt := numeric_entry_roll42.current_receipt(plan, card, kw.get("answers"))) is not None:
        out.setdefault("choices", {})[numeric_entry_roll42.WHAT] = receipt.model_dump_json()
    if (counter_preview := out.pop("_entry_counter_preview", None)) is not None:
        card = card.model_copy(update={"counters": counter_preview})
    if out.get("tapped") and others_enter_untapped(plan, card, controller):
        out["tapped"] = False
    return out


def _entry_plan(plan: Plan, card: CardInstance, controller: str, *, pay_life: bool | None = None,
               tapped: bool = False, answers: dict[str, str] | None = None, x: int | None = None,
               extra: dict[str, int] | None = None, reserved: set[str] | None = None, bare: bool = False,
               tapped_if_land: bool = False) -> dict[str, Any]:
    """How the permanent's own replacement effects modify its entering: {"tapped": bool, "life": N
    (a shock land whose controller pays), "choices": {"color": "Blue", …} (its "As ~ enters, choose
    …" answers, ``answers``), "choice": {"life": N} | {"what": "color"} (the next thing still to be
    decided: 614.12a, choices are made before it enters)}. ``tapped`` is what the effect putting it
    onto the battlefield says ("put it onto the battlefield tapped").
    -- replacement effects stage 2 (wave 2E) -- Also other permanents' "[Objects] enter tapped"
    (614.1d), and the order of the replacement effects on the counters it enters with (616.1,
    asked before it enters, 614.12a: {"what": "order:<question>", "order": …}; ``x`` / ``extra``:
    the X it was cast with, counters the effect putting it there adds)."""
    out: dict[str, Any] = {"tapped": bool(tapped)}
    if bare:  # -- review 35 -- it enters with no abilities (``bare``: Xu-Ifit's ruling 2025-07-25): none of its own applies; others' still do (614.12)
        if tapped_if_land and "Land" in plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})).types:
            out["tapped"] = True
        out["tapped"] = out["tapped"] or others_enter_tapped(plan, card, controller)
        return out
    # -- copy system (wave 2F): "You may have ~ enter as a copy of …" (707.5, 614.12a): chosen first;
    # then the rest of this plan reads the copied text (app/rules/copying.py) --
    from app.rules import copying

    if copying.entering(plan, card, controller, answers, out):
        return out
    if tapped_if_land and "Land" in plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})).types:
        out["tapped"] = True
    # -- review (wave 22A) -- 614.12: the permanent as it would exist on the battlefield (Blood Moon, Humility: it has no such abilities)
    defs = [d for d in _definitions(plan, card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})).values()
            if d["kind"] == "replacement"]
    from app.rules import entry_payment_diversion

    if entry_payment_diversion.applies(plan, card, defs):
        return {**out, 'divert_zone': 'exile'}
    answers = dict(answers or {})
    named_choices(plan, controller, defs, answers, out)
    from app.rules import battles  # 310.9a: a battle's protector is chosen as it enters

    battles.entry_choice(plan, plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"),
                                                                "controller": controller})), controller, answers, out)
    entry_x = int((x if x is not None else card.stack_info.x if card.zone == "stack" and card.stack_info is not None else 0) or 0)
    for d in defs:
        kind = d["replacement"]
        if kind == "enters_tapped":
            unless = d.get("unless")
            if unless is None or not unless_holds(plan, controller, card, unless):
                out["tapped"] = True
        # "~ enters tapped with two charge counters on it."; -- entry forms (wave 5F) -- the Thriving lands
        elif (kind in ("enters_with_counters", "enters_choice") and d.get("tapped")
              or kind == "enters_with_counters" and d.get("tapped_x_max") is not None and entry_x <= d["tapped_x_max"]):
            out["tapped"] = True
    if not out["tapped"] and others_enter_tapped(plan, card, controller):  # -- replacement effects stage 2 (wave 2E) --
        out["tapped"] = True
    for d in defs:
        if d["replacement"] != "pay_life_or_tapped" and not d.get('pay_life_or_tapped'):
            continue
        life = int(d["life"])
        if "choice" in out or (out['tapped'] and not d.get('pay_life_or_tapped')):
            continue  # it enters tapped anyway ("put it onto the battlefield tapped"), or another choice comes first
        untapped = others_enter_untapped(plan, card, controller)  # -- Spelunking (wave 50B) -- the life is still the controller's choice (616.1, ruling 2023-11-10)
        player = plan.state.players.get(controller)
        from app.rules import (
            life_lock,  # -- can't lose life (wave 29D) -- 119.8: nor by a player who can't lose life
        )

        if player is None or player.life < life or life_lock.pay_problem(plan.state, plan.info, controller, life) is not None:
            out["tapped"] = True  # 119.4: life can be paid only from a life total of at least that much
            continue
        if pay_life is None:
            out["choice"] = {"life": life, "untapped": untapped,
                             **({'stays_tapped': True} if out['tapped'] and not untapped else {})}
        elif pay_life:
            out["life"] = out.get("life", 0) + life
        else:
            out["tapped"] = True
    # -- "this way" outcomes (wave 4A) -- "you may reveal an Island or Swamp card … If you don't, it enters tapped"
    from app.rules import reveal_lands

    reveal_lands.plan_entry(plan, card, controller, defs, answers, out)
    # -- entering for a cost (wave 5G) -- "If ~ would enter, you may discard a land card instead. …" (app/rules/enter_cost.py)
    from app.rules import enter_cost

    enter_cost.plan_entry(plan, card, controller, defs, answers, out, set(reserved or ()))
    if out.get("divert"):  # (it won't enter: nothing else about its entering is asked)
        out.pop("choice", None)
        return out
    # -- keyword mechanics (wave 9D) -- devour N (702.82a): which permanents to sacrifice as it enters (app/rules/devour.py)
    from app.rules import devour

    devour.plan_entry(plan, card, controller, answers, out, set(reserved or ()))
    if any(d["replacement"] == "enters_turn_down" for d in defs):  # -- hidden exile (wave 18A) -- Ixidron: the nontoken creatures there now
        out["turn_down"] = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.is_token
                            and not c.face_down and c.id != card.id and plan.ch(c).is_creature]
    from app.rules import (
        amplify,  # -- casting extras (wave 18E) -- amplify N (702.38a): which cards to reveal as it enters
    )

    amplify.plan_entry(plan, card, controller, answers, out)
    from app.rules import (
        riot,  # -- keywords (wave 15E) -- riot / unleash: the +1/+1 counter or haste (app/rules/riot.py)
    )

    riot.plan_entry(plan, card, controller, answers, out)
    from app.rules import (
        tribute,  # -- keywords (wave 50H) -- tribute N (702.104a): an opponent's choice as it enters
    )

    tribute.plan_entry(plan, card, controller, answers, out)
    if out.get("choice", {}).get("what") == enter_cost.WHAT and reserved:
        out["choice"]["reserved"] = sorted(reserved)
    # -- replacement effects stage 2 (wave 2E): the counters it enters with (122.6) --
    orders = {k: v for k, v in answers.items() if k.startswith(ORDER)}
    if orders:
        out.setdefault("choices", {}).update(orders)
    if "choice" not in out:
        counter_preview: dict[str, int] = {}
        order = _entering_order_choice(plan, card, controller, x=x, extra=extra, answers=orders,
                                       choices=answers, counter_preview=counter_preview)  # (wave 3S: the read-ahead number chosen first)
        if order is not None:
            out["choice"] = order
        elif counter_preview:
            # 614.12: the initial-counter replacement has already modified
            # the entry event. Read its planned outcome without committing it.
            incoming = card.model_copy(update={"counters": {**card.counters, **{
                kind: card.counters.get(kind, 0) + n for kind, n in counter_preview.items()}}})
            out["_entry_counter_preview"] = dict(incoming.counters)
            if not out["tapped"] and others_enter_tapped(plan, incoming, controller):
                out["tapped"] = True
    return out


def named_choices(plan: Plan, controller: str, defs: list[dict[str, Any]], answers: dict[str, str], out: dict[str, Any]) -> None:
    """"As ~ enters, choose a color." (614.1c): the answers so far go to ``out["choices"]``, the first question still open to ``out["choice"]``;
    the answer is recorded on the permanent (``after_entry``). -- token entering choices (wave 34A) -- shared with the tokens' own (``token_choices``)."""
    for d in defs:
        if d["replacement"] != "enters_choice":
            continue
        for e in d.get("effects") or []:
            what = e.get("what")
            if e.get("do") != "choose_value" or not what:
                continue
            if what == card_names.LOOK and what not in answers and (only := card_names.sole_opponent(plan, controller)):
                answers[what] = only  # -- card names (wave 22B) -- one opponent: no question
            if d.get("control") and what not in answers and (only := card_names.sole_opponent(plan, controller)):
                answers[what] = only  # -- entry control (wave 110A) -- one opponent: no question
            if what in answers:
                out.setdefault("choices", {})[what] = answers[what]
            elif "choice" not in out:
                out["choice"] = {"what": what, **({"pick110a": e["pick110a"]} if e.get("pick110a") else {}), **({"look": answers.get(card_names.LOOK)} if e.get("look") else {}), **({"reveal": True} if e.get("reveal") else {}),
                                 **({"options": e["options"]} if e.get("options") else {}), **({"random": True} if e.get("random") else {})}  # (wave 51C: "choose Elemental, Elf, …": only the creature types listed)
                if what == "second color":
                    out["choice"]["options"] = [o for o in ("White", "Blue", "Black", "Red", "Green") if o != answers.get("color")]
                if what == "second basic land type":  # (wave 53B: "choose two basic land types" are two different ones)
                    out["choice"]["options"] = [o for o in ("Plains", "Island", "Swamp", "Mountain", "Forest") if o != answers.get("basic land type")]


# -- replacement effects stage 2 (wave 2E) -----------------------------------------------------------
ORDER = "order:"  # an entering answer that is a 616.1 order: "order:<question>" -> the effect applied first


def others_enter_tapped(plan: Plan, card: CardInstance, controller: str, static: str = "enters_tapped_others") -> bool:
    """614.1d: "Creatures your opponents control enter tapped." — statics of permanents on the
    battlefield, checked against the permanent as it would exist on the battlefield under the
    player it enters under (614.12; it doesn't see itself: "Permanents enter tapped" doesn't make
    its own permanent enter tapped, 614.12 example)."""
    from app.rules.replace import conditional_lines

    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    ch = None
    if static == "enters_tapped_others":
        from app.rules import timed_damage_replacements

        for record in plan.rules.replacements:
            if record.get("event") != "enters_tapped" or not timed_damage_replacements.active(plan, record):
                continue
            key = (record.get("match") or {}).get("selector")
            if key:
                ch = ch if ch is not None else plan.ch(probe)
                if selectors.matches(plan, selectors.from_key(key), probe, ch, record["controller"], record.get("source_card")):
                    return True
    for src in plan.state.cards.values():
        if src.id == card.id or not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) \
                or plan.manual(src):
            continue
        src_ch = plan.ch(src)
        for i, d in scripts.definitions(src_ch).items():
            if d["kind"] != "static" or d.get("static") != static:
                continue
            if i in conditional_lines(src_ch) or "Room" in src_ch.subtypes:
                continue  # (a level's or an unlocked door's ability: not tracked, never applied)
            if not statics.conditions_hold(plan, d, source=src, controller=src.controller):
                continue  # -- commander sweep (wave 49B) -- "As long as ~ is tapped, other permanents enter tapped." (Archelos, 611.3a)
            ch = ch if ch is not None else plan.ch(probe)
            if any(selectors.matches(plan, selectors.from_key(key), probe, ch, src.controller, src.id) for key in d["who"]):
                return True
    return False


def entering_counters(plan: Plan, card: CardInstance, controller: str, ch: Any, *, x: int | None = None,
                      extra: dict[str, int] | None = None, choices: dict[str, str] | None = None,
                      newcomers: list[str] | None = None) -> dict[str, int]:
    """The counters a permanent enters with (122.6): its "enters with" counters (614.1c; the X its
    spell was cast with, 107.3), a planeswalker's loyalty (306.5b), bloodthirst (702.54) and what
    the effect putting it there adds (persist / undying)."""
    counters: dict[str, int] = {k: n for k, n in (extra or {}).items() if n > 0}
    if "Planeswalker" in ch.types:  # 306.5b: intrinsic, however it enters (even a card taken out of automation)
        # (a printed loyalty of X is the X its spell was cast with, 107.3; 0 when it wasn't cast)
        loyalty = int(ch.loyalty) if ch.loyalty and ch.loyalty.isdigit() else int(x or 0) if ch.loyalty == "X" else 0
        if loyalty and "compleated" in ch.keywords and not plan.manual(card):  # -- cast keywords (wave 43D) -- 702.150a: two fewer for each Phyrexian symbol paid with life
            paid = plan.rules.payments.get(plan.oid(card))  # ponytail: mana.solve pays a Phyrexian symbol with life only when mana falls short (no free choice)
            loyalty = max(0, loyalty - 2 * (paid.phyrexian if paid is not None else 0))
        if loyalty:
            counters["loyalty"] = counters.get("loyalty", 0) + loyalty
    if "Battle" in ch.types:  # 310.4b: intrinsic, however it enters
        from app.rules import battles

        if battles.defense(ch):
            counters["defense"] = counters.get("defense", 0) + battles.defense(ch)
    if not plan.manual(card):
        r = plan.rules
        bled = any(t == plan.state.turn.number for p, t in r.damaged.items() if p != controller)
        for ab in ch.abilities:  # 702.54 bloodthirst N: if an opponent was dealt damage this turn
            if ab.kind == "keywords" and bled:
                for kw in ab.keywords:
                    if kw == "bloodthirst":
                        m = re.fullmatch(r"bloodthirst (\d+)", ab.text.strip().rstrip(".").lower())
                        if m:
                            counters["+1/+1"] = counters.get("+1/+1", 0) + int(m.group(1))
        for ab in ch.abilities:  # -- random choices (wave 47B) -- 702.54b bloodthirst X: the total damage your opponents have been dealt this turn (Indoraptor ruling 2023-11-10: by any source)
            if ab.kind == "keywords" and "bloodthirst" in ab.keywords and ab.text.strip().rstrip(".").lower() == "bloodthirst x":
                from app.rules import history

                dealt = sum(f.amount for f in history.log_for(plan).facts if f.kind == "damage" and f.player != controller)
                if dealt:
                    counters["+1/+1"] = counters.get("+1/+1", 0) + dealt
        for ab in ch.abilities:  # -- keyword pieces (wave 8A) -- 702.43a modular N: "This permanent enters with N +1/+1 counters"
            for kw in ("modular", "graft"):  # (-- keyword mechanics (wave 9D) -- 702.58a graft N: the same)
                if ab.kind == "keywords" and kw in ab.keywords:
                    from app.rules import keyword_triggers

                    if kw == "modular" and keyword_triggers.modular_sunburst(ab.text):
                        n = _counter_amount(plan, card.id, controller, {"n": {"colors_spent": 1}}, x)
                        counters["+1/+1"] = counters.get("+1/+1", 0) + n
                    else:
                        for piece in keyword_triggers.pieces(kw, ab.text):
                            counters["+1/+1"] = counters.get("+1/+1", 0) + int(piece.split()[1])
        for ab in ch.abilities:  # -- keywords (wave 15E) -- 702.63a vanishing N / 702.32a fading N: "enters with N time / fade counters"
            for kw, kind in (("vanishing", "time"), ("fading", "fade")):
                if ab.kind == "keywords" and kw in ab.keywords:
                    from app.rules import keyword_triggers

                    for piece in keyword_triggers.pieces(kw, ab.text):
                        if " " in piece:  # (-- keywords (wave 50H) -- 702.63b: "Vanishing" alone enters with no counters of its own)
                            counters[kind] = counters.get(kind, 0) + int(piece.split()[1])
        from app.rules import (
            amplify,  # -- casting extras (wave 18E) -- 702.38a: N for each card revealed as it entered
            devour,  # -- keyword mechanics (wave 9D) -- 702.82a: N for each permanent sacrificed as it entered
            riot,  # -- keywords (wave 15E) -- 702.136a / 702.98a: the additional +1/+1 counter chosen
            tribute,  # -- keywords (wave 50H) -- 702.104a: N additional counters, put by the opponent who paid
        )

        if amplify.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + amplify.counters(ch, choices)
        if riot.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + riot.counters(ch, choices)
        if tribute.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + tribute.counters(ch, choices)
        if devour.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + devour.counters(ch, choices)
        from app.rules import reveal_lands  # (wave 100K: Dragon's Disciple)

        if reveal_lands.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + reveal_lands.counters(ch, choices)
        for ab in ch.abilities:  # -- keyword mechanics (wave 9D) -- 702.44a sunburst: a +1/+1 counter (a creature, ignoring
            if ab.kind == "keywords" and "sunburst" in ab.keywords:  # type-changing effects) or a charge counter for each
                from app.rules import (
                    keyword_triggers,  # color of mana spent to cast it; only from the stack (702.44b: no payment, none)
                )

                kind = "+1/+1" if "Creature" in ch.types else "charge"
                for _ in keyword_triggers.pieces("sunburst", ab.text):
                    n = _counter_amount(plan, card.id, controller, {"n": {"colors_spent": 1}}, x)
                    if n > 0:
                        counters[kind] = counters.get(kind, 0) + n
        if x and any(ab.kind == "keywords" and "ravenous" in ab.keywords for ab in ch.abilities):  # -- keyword meanings (wave 11B) -- 702.156a
            counters["+1/+1"] = counters.get("+1/+1", 0) + x
        for d in scripts.definitions(ch).values():
            if d["kind"] == "replacement" and d.get("replacement") == "enters_with_counters":
                if d.get("self_in_group"):  # -- review (wave 26D) -- it is one of the group it counts: unsettled (scripts._enters_self_check)
                    if card.zone.endswith(":battlefield"):  # (not while the counters are only being looked ahead at, before it moves)
                        plan.note(f"{plan.ch(card).name or 'It'} is one of the permanents its \"enters with\" counters count: whether it counts "
                                  "itself isn't settled — put its counters on by hand", [card.id])
                    continue
                for part in (d, *d.get("also", ())):  # (wave 26D: "enters with a +1/+1 counter, a flying counter, …": one event, 122.6)
                    n = _counter_amount(plan, card.id, controller, part, x, newcomers)
                    if n > 0:
                        counters[part["counter"]] = counters.get(part["counter"], 0) + n
        for d in scripts.definitions(ch).values():  # -- chosen filters (wave 53B) -- "As ~ enters, choose a creature type. ~ enters with a counter for each creature you control of the chosen type." (614.12a, 614.1c)
            if d.get("replacement") == "enters_choice" and d.get("counters") and (picked := (choices or {}).get(d["counters_choice"])):
                from app.rules import chosen as _chosen

                part = _chosen.bind_effects([d["counters"]], d["counters_choice"], picked)[0]
                if part["n"] == {"entry_opponent_creatures": True}:
                    part = {**part, "n": {"count": selectors.Selector(types=("Creature",), controller=f"player:{picked}").key()}}
                if (n := _counter_amount(plan, card.id, controller, part, x, newcomers)) > 0:
                    counters[part["counter"]] = counters.get(part["counter"], 0) + n
        from app.rules import copying

        for kind, n in copying.entry_counters(plan, card, controller, ch, choices, x).items():  # -- copy exceptions (wave 24A) -- 707.9e
            counters[kind] = counters.get(kind, 0) + n
        # -- counters (wave 7C) -- the kind its controller chose as it enters
        from app.rules import counter_choice

        for kind, n in counter_choice.entering(list(scripts.definitions(ch).values()), choices).items():
            counters[kind] = counters.get(kind, 0) + n
        # -- sagas & attached-object triggers (wave 3S): a Saga's lore counters (714.3a; read ahead 714.3b) --
        from app.rules import sagas

        lore = sagas.entering_lore(ch, choices)
        if lore:
            counters[sagas.LORE] = counters.get(sagas.LORE, 0) + lore
    from app.rules import (
        mana_units,  # -- mana provenance (wave 18B) -- 106.6: the mana's rider, whatever the permanent is
    )

    if n := mana_units.entering_counters(plan, card):  # (the spell's payment record follows the permanent: as in ``entered``)
        counters["+1/+1"] = counters.get("+1/+1", 0) + n
    from app.rules import casting_timing_permissions

    for kind, n in casting_timing_permissions.entering_counters(plan, card, controller, ch).items():
        counters[kind] = counters.get(kind, 0) + n
    from app.rules import numeric_entry_roll42

    if n := numeric_entry_roll42.counter_total(plan, card, ch, choices):
        counters["+1/+1"] = counters.get("+1/+1", 0) + n
    return counters


def _entering_order_choice(plan: Plan, card: CardInstance, controller: str, *, x: int | None,
                           extra: dict[str, int] | None, answers: dict[str, str],
                           choices: dict[str, str] | None = None,
                           counter_preview: dict[str, int] | None = None) -> dict[str, Any] | None:
    """616.1 / 614.12a: when replacement effects would modify the counters a permanent enters with
    and their order matters, its controller chooses before it enters."""
    from app.rules import replace

    if x is None and card.zone == "stack" and card.stack_info is not None:
        x = card.stack_info.x
    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    counters = entering_counters(plan, card, controller, plan.ch(probe), x=x, extra=extra, choices=choices)
    if not counters and not replace.entering_kinds(plan, replace.candidates(plan, "counters")):  # (wave 5H)
        return None
    puts = [(card.id, kind, n) for kind, n in counters.items()]
    planned = replace.plan_counters(plan, puts, by=controller, effect=True, entering={card.id: controller},
                                    answers={k[len(ORDER):]: v for k, v in answers.items()}, ask=True)
    if not isinstance(planned, replace.Ask):
        if counter_preview is not None:
            counter_preview.update({kind: 0 for kind in counters})
            for _initial, finals in planned.finals:
                for event in finals:
                    if event.get("kind") == "counters" and event.get("card") == card.id and not event.get("prohibited"):
                        kind = event["counter"]
                        counter_preview[kind] = counter_preview.get(kind, 0) + max(0, int(event.get("n", 0)))
        return None
    names = " and ".join(c.label for c in planned.applicable)
    options = [(c.id, replace.option_label(c, planned.outcomes)) for c in planned.applicable]
    return {"what": ORDER + planned.fp, "order": {
        "prompt": f"{card.name}: {names} both modify the counters it enters with — which applies first? (616.1)",
        "options": options}}
# -- end replacement effects stage 2 (wave 2E) --


def choice_needed(plan: Plan, card: CardInstance, entry: Entry) -> dict[str, Any] | None:
    """The choice a permanent's own "As ~ enters, you may …" asks for before it enters (614.12a)."""
    if not plan.state.players.get(entry["player"]):
        return None
    from app.rules import face_down_entries64

    card = face_down_entries64.probe(plan, card, entry)
    if entry.get("modal_back"):  # -- play now (wave 28A) -- 712.12: the land face chosen enters face up, so its replacements apply
        card = card.model_copy(update={"face": 1})
    return entry_plan(plan, card, entry["player"], pay_life=entry.get("pay_life"), tapped=bool(entry.get("tapped")),
                      answers=entry.get("choices"), x=entry.get("x"), extra=_extra(entry, plan), tapped_if_land=bool(entry.get("tapped_if_land")),
                      reserved=set(entry.get("reserved") or ()), bare=bool(entry.get("bare")), entry_characteristics=entry.get("entry_characteristics")).get("choice")  # (reserved: wave 5G)


def _extra(entry: Entry, plan: Plan | None = None) -> dict[str, int] | None:
    """The counters the effect putting it onto the battlefield adds (persist / undying: 702.79a, 702.93a)."""
    # (counter_n: wave 3E, "onto the battlefield with three +1/+1 counters on it")
    if '_resolved_extra_counters' in entry:
        return dict(entry['_resolved_extra_counters']) or None
    rules = list(entry.get('conditional_counters') or [])
    if entry.get('counter'):
        rules.append({'kind': entry['counter'], 'n': int(entry.get('counter_n') or 1), 'sel': entry.get('counter_if')})
    counters: dict[str, int] = {}
    for rule in rules:
        if rule.get('sel') and plan is not None:
            from app.rules import selectors

            card = plan.state.cards.get(entry['card'])
            if card is None:
                continue
            from app.rules import entry_characteristics

            card = entry_characteristics.probe(card, entry.get('entry_characteristics'))
            probe = card.model_copy(update={'zone': zone_key(entry['player'], 'battlefield'), 'controller': entry['player']})
            condition = dataclasses.replace(selectors.from_key(rule['sel']), card=False, zones=('battlefield',))
            if not selectors.matches(plan, condition, probe, plan.ch(probe), entry['player']):
                continue
        counters[rule['kind']] = counters.get(rule['kind'], 0) + int(rule['n'])
    return counters or None


def choice_prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    """The prompt and options for one entering choice (a shock land's life, or a named choice)."""
    if "order" in choice:  # -- replacement effects stage 2 (wave 2E): 616.1 before it enters (614.12a) --
        return choice["order"]["prompt"], [DecisionOption(id=cid, label=label) for cid, label in choice["order"]["options"]]
    if "life" in choice:
        name = plan.ch(card).name or card.name
        if choice.get('stays_tapped'):
            n = choice['life']
            return (f"{name}: pay {n} life? It enters tapped either way",
                    [DecisionOption(id='pay', label=f'Pay {n} life (still tapped)'),
                     DecisionOption(id='tapped', label="Don't pay (tapped)")])
        return shock_prompt(name, choice["life"], bool(choice.get("untapped")))
    from app.rules.effects import _choice_options

    what = choice["what"]
    if choice.get("pick110a"):  # -- chosen objects (wave 110A) --
        from app.rules import wave110a_pick

        return wave110a_pick.prompt(plan, card, controller, choice)
    from app.rules import chosen_forms95

    if what.startswith(chosen_forms95.PREFIX):
        return f"{card.name}: choose its form", [DecisionOption(id=o, label=o) for o in choice["options"]]
    if (named := card_names.prompt(plan, card, controller, choice)) is not None:  # -- card names (wave 22B) -- look at a hand, then name
        return named
    from app.rules import battles, reveal_lands
    from app.rules.chosen import PAIR_WHAT

    if what == PAIR_WHAT:  # -- chosen filters (wave 53B) -- "choose white Citizen, blue Camarid, …": its own options
        return f"{card.name}: as it enters, choose a color and creature type", [DecisionOption(id=o, label=o) for o in choice["options"]]
    if reveal_lands.is_choice(what):  # -- "this way" outcomes (wave 4A) -- private: the cards in their hand
        return reveal_lands.prompt(plan, card, controller, what)
    from app.rules import enter_cost

    if enter_cost.is_choice(what):  # -- entering for a cost (wave 5G) -- private: the cards in their hand
        return enter_cost.prompt(plan, card, controller, set(choice.get("reserved") or ()))
    from app.rules import devour  # -- keyword mechanics (wave 9D) --

    if devour.is_choice(what):
        return devour.prompt(plan, card, controller, choice)
    from app.rules import amplify  # -- casting extras (wave 18E) -- private: the cards in their hand

    if amplify.is_choice(what):
        return amplify.prompt(plan, card, controller, choice)
    from app.rules import riot  # -- keywords (wave 15E) --

    if riot.is_choice(what):
        return riot.prompt(plan, card, controller, what)
    from app.rules import tribute  # -- keywords (wave 50H) --

    if tribute.is_choice(what):
        return tribute.prompt(plan, card, controller, choice)

    if what == battles.PROTECTOR:  # 310.9a / 310.12a
        return f"{card.name}: as it enters, choose its protector", battles.choice_options(plan, controller, card)
    from app.rules import chosen

    if (picks := chosen.words(what)) is not None:  # -- linked words (wave 33B) -- 607.2f
        return f"{card.name}: as it enters, choose {' or '.join(picks)}", _choice_options(plan, {"controller": controller, "source_card": card.id}, what)
    article = "an" if what[:1] in "aeiou" else "a"
    return (f"{card.name}: as it enters, choose {article} {what}",  # (-- enter as copy (wave 5F) --: the entering card)
            [o for o in _choice_options(plan, {"controller": controller, "source_card": card.id}, what) if not choice.get("options") or o.id in choice["options"]])


def _answer(entry_or_answers: dict[str, Any], choice: dict[str, Any], chosen: str) -> dict[str, Any]:
    """Record an answer: a shock land's ``pay_life``, or a named choice under ``choices``."""
    if "life" in choice:
        return {**entry_or_answers, "pay_life": chosen == "pay"}
    from app.rules import devour  # -- keyword mechanics (wave 9D) -- devour's picks pile up

    if devour.is_choice(choice["what"]):
        chosen = devour.merge((entry_or_answers.get("choices") or {}).get(choice["what"]), chosen)
    from app.rules import amplify  # -- casting extras (wave 18E) -- amplify's picks pile up too

    if amplify.is_choice(choice["what"]):
        chosen = amplify.merge((entry_or_answers.get("choices") or {}).get(choice["what"]), chosen)
    return {**entry_or_answers, "choices": {**(entry_or_answers.get("choices") or {}), choice["what"]: chosen}}


def ask_entry_choice(plan: Plan, entries: list[Entry], index: int, ctx: dict[str, Any] | None, shuffle: str | None) -> None:
    """A permanent put onto the battlefield by an effect asks its controller before it enters
    (614.12a) — before any of the permanents entering with it does (they enter together): in
    private (the card may come from a hidden zone: the prompt names it only to them)."""
    from app.rules.plan import decide

    entry = entries[index]
    card = plan.state.cards[entry["card"]]
    choice = choice_needed(plan, card, entry) or {"life": 0}
    from app.rules import copiable_coin_entry

    if choice.get("what") == copiable_coin_entry.WHAT:
        data = {"caller": "entry", "entries": entries, "index": index, "ctx": ctx,
                "shuffle": shuffle, "object": plan.oid(card)}
        if copiable_coin_entry.run_coin(plan, entry["player"], data):
            copiable_coin_entry.resume(plan, data)
        return
    prompt, options = choice_prompt(plan, card, entry["player"], choice)
    if not options:  # (no opponent left to choose, 800.4: the choice is skipped)
        _enter_again(plan, entries, index, _answer(entry, choice, ""), ctx, shuffle)
        return
    decide(plan, player=choice.get("decider") or entry["player"], kind="choose_one", prompt=prompt, options=options,  # (-- keywords (wave 50H) -- tribute: the opponent decides, 702.104a)
           resume={"step": "enter_choice", "entries": entries, "index": index, "ctx": ctx, "shuffle": shuffle,
                   "choice": choice},
           source=card)


def _enter_again(plan: Plan, entries: list[Entry], index: int, entry: Entry, ctx: dict[str, Any] | None,
                 shuffle: str | None) -> None:
    from app.rules import attachments

    if attachments.enter(plan, [*entries[:index], entry, *entries[index + 1:]], ctx, shuffle=shuffle):
        _finish_entries(plan, ctx, shuffle)


def resume_entries(resume: dict[str, Any]) -> tuple[list[Entry], int]:
    """The entries of a paused simultaneous entry and the one that was asking (a decision saved
    before entries were batched holds that one and the rest after it)."""
    if "entries" in resume:
        return list(resume["entries"]), int(resume.get("index") or 0)
    return [resume["entry"], *(resume.get("rest") or [])], 0


def _finish_entries(plan: Plan, ctx: dict[str, Any] | None, shuffle: str | None) -> None:
    from app.rules.effects import continue_effects

    if shuffle:
        plan.do({"type": "shuffle", "player": shuffle, "zone": "library"}, actor=shuffle)
    if ctx is not None:
        # -- reanimation Auras (wave 51F) -- 400.7j: the effect that paused for an entry choice names what it put onto the battlefield ("as"): rebind it to the
        # objects they became, as the unpaused path does (effects._moved), so "attach this Aura to it" finds the creature
        from app.game.rules_state import ObjectRef
        from app.rules import context

        paused = ctx["effects"][ctx["next"] - 1] if ctx.get("next") else {}
        bound = (ctx.get("refs") or {}).get(paused.get("as") or "")
        if bound and bound.get("kind") == "objects" and "was" not in bound:
            context.bind_moved(plan, ctx, paused["as"], [ObjectRef.model_validate(o) for o in bound["objects"]])
        continue_effects(plan, ctx)


def resume_entry_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    entries, index = resume_entries(d.resume)
    entry = _answer(entries[index], d.resume.get("choice") or {"life": 0}, chosen[0])
    _enter_again(plan, entries, index, entry, d.resume.get("ctx"), d.resume.get("shuffle"))


def stack_entry_choice(plan: Plan, card: CardInstance, controller: str) -> bool:
    """A permanent spell about to resolve with an "As ~ enters, choose …" ability: ask its
    controller before it enters (614.12a). True while a question is open; the answers wait in
    ``RulesState.entry_choices`` and the spell resolves again with them."""
    from app.rules.plan import decide

    r = plan.rules
    ep = entry_plan(plan, card, controller, answers=r.entry_choices.get(card.id))
    choice = ep.get("choice")
    from app.rules import numeric_entry_roll42

    if (not ep.get("divert_zone") and (choice is None or "order" in choice)
            and numeric_entry_roll42.applies(plan, card, controller)
            and numeric_entry_roll42.current_receipt(plan, card, r.entry_choices.get(card.id)) is None):
        if not numeric_entry_roll42.run(plan, card, controller):
            return True
        return stack_entry_choice(plan, card, controller)
    if choice is None or "what" not in choice:
        return False  # (a shock land's question is never asked on the stack: the wording is printed on lands)
    from app.rules import copiable_coin_entry, random_entry_choice

    if choice.get("what") == copiable_coin_entry.WHAT:
        data = {"caller": "stack", "card": card.id, "object": plan.oid(card)}
        if not copiable_coin_entry.run_coin(plan, controller, data):
            return True
        return stack_entry_choice(plan, card, controller)
    if (value := random_entry_choice.answer(plan, choice, controller, card.id)) is not None:
        r.entry_choices.setdefault(card.id, {})[choice["what"]] = value
        return stack_entry_choice(plan, card, controller)
    prompt, options = choice_prompt(plan, card, controller, choice)
    if not options:
        r.entry_choices.setdefault(card.id, {})[choice["what"]] = ""
        return stack_entry_choice(plan, card, controller)
    decide(plan, player=choice.get("decider") or controller, kind="choose_one", prompt=prompt, options=options,  # (-- keywords (wave 50H) -- tribute: the opponent decides)
           resume={"step": "stack_enter_choice", "card": card.id, "what": choice["what"]}, source=card)
    return True


def _picked(plan: Plan, d: Any, chosen: str) -> str:
    from app.rules import (
        amplify,  # -- casting extras (wave 18E) --
        devour,  # -- keyword mechanics (wave 9D) --
    )

    if amplify.is_choice(d.resume["what"]):
        return amplify.merge(plan.rules.entry_choices.get(d.resume["card"], {}).get(amplify.WHAT), chosen)
    if not devour.is_choice(d.resume["what"]):
        return chosen
    return devour.merge(plan.rules.entry_choices.get(d.resume["card"], {}).get(devour.WHAT), chosen)


def resume_stack_enter_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import resolve_top_of_stack

    plan.rules.entry_choices.setdefault(d.resume["card"], {})[d.resume["what"]] = _picked(plan, d, chosen[0])
    resolve_top_of_stack(plan)


def resume_land_enter_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import play_land

    plan.rules.entry_choices.setdefault(d.resume["card"], {})[d.resume["what"]] = _picked(plan, d, chosen[0])
    plan.rules.priority = d.player
    play_land(plan, A.parse_action(d.resume["intent"]))  # type: ignore[arg-type]


def move_onto_battlefield(plan: Plan, entry: Entry) -> None:
    """Put one card onto the battlefield (:func:`move_together` with one entry)."""
    move_together(plan, [entry])


def turn_down(plan: Plan, ep: dict[str, Any], actor: str) -> None:
    """-- hidden exile (wave 18A) -- 708.2a: the creatures an "as it enters, turn … face down" names become 2/2 face-down creatures."""
    ids = [c for c in ep.get("turn_down") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if ids:
        plan.do({"type": "face_down", "card_ids": ids, "face_down": True, "kind": "generic"}, actor=actor)


def move_together(plan: Plan, entries: list[Entry], *, simultaneous: dict[str, Any] | None = None) -> None:
    """Put cards onto the battlefield at once, each under ``entry["player"]``'s control with its
    "enters" replacements applied: one event (603.6a), every replacement judged against the table
    as it is before any of them enters (614.12: "enters tapped unless you control …" doesn't see a
    card entering with it), the objects timestamped in APNAP order (613.7m: rules_state._diff).
    Tapped status is part of the move itself (it never enters untapped and then taps), a shock
    land's life is paid as it enters, its "enters with" counters and loyalty follow as the same
    event (122.6, 306.5b). Extras recorded on the entry by the effect that puts it there — a
    persist / undying counter, unearth's haste and "exile it instead" — are applied after."""
    planned: list[tuple[Entry, CardInstance, dict[str, Any]]] = []
    for entry in entries:
        card = plan.state.cards.get(entry["card"])
        if card is None or any(card.id == c.id for _, c, _ in planned):
            continue
        from app.rules import face_down_entries64

        card = face_down_entries64.probe(plan, card, entry)
        # (-- transform, wave 11A -- 712.14a: it enters with its back face up, so that face's replacement effects apply)
        planned.append((entry, card, entry_plan(plan, card.model_copy(update={"face": 1}) if entry.get("transformed") or entry.get("modal_back") else card,
                                                 entry["player"], pay_life=entry.get("pay_life"),
                                                 tapped=bool(entry.get("tapped")), answers=entry.get("choices"), tapped_if_land=bool(entry.get("tapped_if_land")),
                                                 x=entry.get("x"), extra=_extra(entry, plan),
                                                 reserved=set(entry.get("reserved") or ()), bare=bool(entry.get("bare")), entry_characteristics=entry.get("entry_characteristics"))))  # (reserved: wave 5G)
    # -- entering for a cost (wave 5G) -- the payment first, or it goes to its owner's graveyard instead (614.6)
    from app.rules import enter_cost

    kept = []
    for entry, card, ep in planned:
        if ep.get("pay") and not enter_cost.pay(plan, card, entry["player"], ep["pay"], entry["actor"]):
            ep["divert"] = True
        if ep.get('divert_zone') == 'exile':
            from app.rules import entry_payment_diversion

            entry_payment_diversion.divert(plan, card.id, entry['actor'])
        elif ep.get("divert"):
            enter_cost.divert(plan, card.id, entry["actor"])
        else:
            kept.append((entry, card, ep))
    planned = kept
    for entry, _card, ep in planned:  # -- keyword mechanics (wave 9D) -- devour: sacrificed as it enters (702.82a)
        from app.rules import devour

        devour.sacrifice(plan, ep, entry["player"])
        from app.rules import static_perm100d  # -- static permanents (wave 100D) -- 614.12: done as it enters

        static_perm100d.as_enters(plan, _card.id, ep, entry["player"])
        from app.rules import amplify  # -- casting extras (wave 18E) -- 702.38a: revealed as it enters

        amplify.reveal(plan, ep, entry["player"])
        turn_down(plan, ep, entry["actor"])
    # -- end entering for a cost (wave 5G) --
    if not planned:
        if simultaneous is not None:
            from app.rules import simultaneous_moves

            if simultaneous.get('kind') == 'discard_group':
                from app.rules import grouped_discard

                grouped_discard.commit(plan, [], simultaneous)
            else:
                simultaneous_moves.commit(plan, [], simultaneous)
        return
    for entry, _card, ep in planned:
        if ep.get("life"):
            from app.rules import replace as _replace_life  # (wave 28B: 119.4)
            _replace_life.lose_life(plan, [(entry["player"], int(ep["life"]))], actor=entry["actor"])
    # CR 614.12: another permanent arriving in this same event cannot change
    # whether an entry counter condition applied. Preserve even an empty result.
    for entry, _card, _ep in planned:
        if entry.get('counter_if') or entry.get('conditional_counters'):
            entry['_resolved_extra_counters'] = _extra(entry, plan) or {}
    if simultaneous is not None:
        from app.rules import simultaneous_moves

        if simultaneous.get('kind') == 'discard_group':
            from app.rules import grouped_discard

            grouped_discard.commit(plan, planned, simultaneous)
        else:
            simultaneous_moves.commit(plan, planned, simultaneous)
        return
    first = planned[0][0]
    payload: dict[str, Any] = {"type": "move", "card_ids": [c.id for _, c, _ in planned],
                               "to": {"player": first["player"], "zone": "battlefield"}}
    from app.rules import face_down_entries64

    face_down_entries64.payload([entry for entry, _, _ in planned], payload)
    forms = {c.id: e["entry_characteristics"] for e, c, _ in planned if e.get("entry_characteristics")}
    if forms:
        payload["entry_characteristics"] = forms
    tapped = [c.id for _, c, ep in planned if ep["tapped"]]
    if tapped:
        payload["tapped_ids"] = tapped
    back = [c.id for e, c, _ in planned if e.get("transformed") or e.get("modal_back")]  # (modal_back: wave 28A, 712.12)
    if back:
        payload["back_ids"] = back
    if any(e["player"] != first["player"] for e, _, _ in planned):
        payload["controllers"] = {c.id: e["player"] for e, c, _ in planned}
    plan.put_via = first.get("via")  # (-- trigger other (wave 51E) -- Entry.via)
    try:
        plan.do(payload, actor=first["actor"])
    finally:
        plan.put_via = None
    together = [c.id for _, c, _ in planned]  # (wave 5H: 614.12)
    for entry, card, ep in planned:
        _after_move(plan, entry, card.id, ep, together)


def _after_move(plan: Plan, entry: Entry, card_id: str, ep: dict[str, Any], together: list[str] | None = None,
                *, prepared: tuple[Any, Any] | None = None) -> None:
    controller = entry["player"]
    after_entry(plan, card_id, controller, x=entry.get("x"), extra_counters=_extra(entry, plan), choices=ep.get("choices"),
                newcomers=together, bare=bool(entry.get("bare")), prepared=prepared)
    entered = plan.state.cards.get(card_id)
    if entered is None or not entered.zone.endswith(":battlefield"):
        return
    if entry.get("played"):  # -- play now (wave 28A) -- 305.1: a land played as an effect resolves ("When you play another land")
        from app.game.rules_state import emit

        emit(plan.state, "land_played", object_id=plan.oid(entered), card=card_id, player=controller)
    oid = plan.oid(entered)
    if entry.get("gain_haste"):
        from app.rules import layers

        layers.add_effect(plan, affected=[oid], layer="6", source=None, controller=controller, add_keywords=("haste",),
                          duration="permanent", label=f"Haste ({entry['gain_haste']})")
    if entry.get("exile_if_leaves"):  # 702.84a: "If it would leave the battlefield, exile it instead of putting it anywhere else."
        plan.rules.exile_if_leaves.append(oid)
    if entry.get("delayed"):  # "Exile it at the beginning of the next end step" (702.84a) — a delayed trigger (603.7)
        from app.rules import delayed

        delayed.create_move(plan, controller, entered.id, oid, entry["delayed"], entered.name)


def _counter_amount(plan: Plan, card_id: str, controller: str, d: dict[str, Any], x: int | None,
                    newcomers: list[str] | None = None) -> int:
    if d.get("entry_condition") is not None:
        from app.rules import conditions

        context = {"controller": controller, "source_card": card_id,
                   "source_object": plan.oid(card_id), "x": x or 0,
                   "not_yet_entered": [card_id, *(newcomers or ())]}
        if not conditions.holds(plan, context, d["entry_condition"]):
            return 0
    n = d["n"]
    if isinstance(n, dict) and "entry_x_doubled_at" in n:
        amount = int(x or 0) * (2 if int(x or 0) >= n["entry_x_doubled_at"] else 1)
    elif isinstance(n, dict) and n.get("entry_delved_spells"):
        paid = plan.rules.payments.get(plan.oid(card_id))
        amount = 0
        for contribution in paid.contributions if paid is not None else ():
            if contribution.kind != "delve":
                continue
            types = contribution.card_types
            if types is None:
                plan.note("The exiled cost card's types weren't saved; put its entry counter on by hand if it was an instant or sorcery", [card_id])
                continue
            amount += bool({"Instant", "Sorcery"} & set(types))
    elif isinstance(n, dict) and n.get("entry_discarded_mana_value"):
        paid = plan.rules.payments.get(plan.oid(card_id))
        amount = 0
        if paid is not None and len(paid.discarded_objects) == 1:
            oid = paid.discarded_objects[0]
            discarded = next((c for c in plan.state.cards.values() if plan.oid(c) == oid), None)
            amount = int(plan.ch(discarded).mana_value) if discarded is not None else paid.discarded_mana_values.get(oid, 0)
            if discarded is None and oid not in paid.discarded_mana_values:
                plan.note("The discarded card's last known mana value wasn't saved; put its entry counters on by hand", [card_id])
    elif n == "X":  # the X its spell was cast with (107.3); 0 when it wasn't cast (put onto the battlefield)
        amount = int(x or 0)
    elif isinstance(n, dict):  # "for each creature card in your graveyard": the values grammar
        # (-- review (wave 26D) -- 614.12: read before it enters: it and what enters with it aren't on the battlefield yet, whatever
        # type-changing effects would make them — Michelangelo under Ashaya isn't one of "each land you control")
        amount = values.evaluate(plan, {"controller": controller, "source_card": card_id,  # (wave 4F: converge's record)
                                        "source_object": plan.oid(card_id), "x": x,  # (x: "twice X", wave 4K)
                                        "not_yet_entered": [card_id, *(newcomers or ())]}, n)
    else:
        amount = int(n)
    # -- review (wave 4R) -- a spell cast by hand has no payment known (engine.absorb_manual_events): X, converge's
    # kicks read 0 (converge's colors: values.evaluate says so) — say so; its controller adds the counters by hand.
    manual = plan.rules.payments.get(plan.oid(card_id))
    uses_x = n == "X" or "'x'" in str(n) or isinstance(n, dict) and "entry_x_doubled_at" in n
    if manual is not None and not manual.mana_known and (uses_x or d.get("per_kick") or d.get("if_kicked")):
        plan.note(f"{plan.state.cards[card_id].name or 'It'} was cast by hand: what was paid for it isn't known — "
                  "put its counters on by hand", [card_id])
    # -- end review (wave 4R) --
    if d.get("if_kicked") or d.get("per_kick"):  # 702.33e: how its spell was cast (the payment record)
        record = plan.rules.payments.get(plan.oid(card_id))
        kicked = record.kicked if record is not None else 0
        if isinstance(d.get("if_kicked"), dict) and not values.kicked_holds(plan, {"source_object": plan.oid(card_id), "source_card": card_id}, d["if_kicked"]):
            kicked = 0  # (-- keywords (wave 50H) -- 702.33f: kicked with that kicker's cost)
        amount = 0 if d.get("if_kicked") and not kicked else amount * kicked if d.get("per_kick") else amount
    if d.get("if_cast") is not None:  # -- refused modal/conditional (wave 3R1) -- adamant: how its spell was paid (601.2h)
        from app.rules import conditions

        ctx = {"controller": controller, "source_card": card_id, "source_object": plan.oid(card_id)}
        amount = amount if conditions.holds(plan, ctx, d["if_cast"]) else 0
    if d.get("escaped_n") is not None:  # -- cant restrictions (wave 46A) -- "It escapes with twelve +1/+1 counters on it instead." (Polukranos, Unchained): 702.138b
        from app.rules import conditions

        ctx = {"controller": controller, "source_card": card_id, "source_object": plan.oid(card_id)}
        amount = int(d["escaped_n"]) if conditions.holds(plan, ctx, {"object": "self", "cast": {"escaped": True}}) else amount
    return amount


def after_entry(plan: Plan, card_id: str, controller: str, *, x: int | None = None,
                extra_counters: dict[str, int] | None = None, choices: dict[str, str] | None = None,
                newcomers: list[str] | None = None, bare: bool = False,
                prepared: tuple[Any, Any] | None = None, preview: bool = False) -> tuple[Any, Any] | None:
    """The "enters with" part of entering (122.6: counters put on it as it enters, by its controller;
    306.5b: a planeswalker's loyalty), right after the move that put it onto the battlefield, and the
    record of what was chosen as it entered ("Chosen color: Blue" on the permanent, 614.12a)."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(":battlefield"):
        return None
    from app.rules import battles

    battles.entered(plan, card_id, choices)  # 310.9a: the protector chosen as it entered
    # -- "this way" outcomes (wave 4A) -- the card revealed as it entered (701.20a)
    from app.rules import reveal_lands

    reveal_lands.after_entry(plan, controller, choices)
    if choices:
        from app.rules import chosen as _chosen
        from app.rules.effects import CHOICE_LABELS

        for what, value in choices.items():
            from app.rules import chosen_forms95

            if value and what.startswith(chosen_forms95.PREFIX):
                plan.do({"type": "set_choice", "card_id": card_id, "key": "Chosen form", "value": value}, actor=controller)
                continue
            if value and value in (_chosen.words(what) or ()):  # -- linked words (wave 33B) -- 607.2f: the word, public, kept for this object (400.7)
                plan.do({"type": "set_choice", "card_id": card_id, "key": _chosen.WORD_LABEL, "value": value}, actor=controller)
                _chosen.record_word(plan, card_id, value)
                continue
            if value and what == _chosen.PAIR_WHAT:  # (wave 53B: a color and a creature type in one answer, each recorded as its own public choice)
                color, kind = value.split(" ", 1)
                plan.do({"type": "set_choice", "card_id": card_id, "key": "Chosen color", "value": color}, actor=controller)
                plan.do({"type": "set_choice", "card_id": card_id, "key": "Chosen creature type", "value": kind}, actor=controller)
                continue
            if not value or (what not in CHOICE_LABELS and not card_names.is_choice(what)):
                continue
            shown = plan.name(value) if what in ("opponent", "player") and value in plan.state.players else value
            plan.do({"type": "set_choice", "card_id": card_id, "key": card_names.LABEL if card_names.is_choice(what) else CHOICE_LABELS[what], "value": shown}, actor=controller)
            if what in ("opponent", "player") and value in plan.state.players:  # -- chosen player (wave 4J) --
                from app.rules import chosen

                chosen.record(plan, card_id, value)
    if not preview:
        from app.rules import wave110a_control  # -- entry control (wave 110A) --

        wave110a_control.give(plan, card_id, choices)
        from app.rules import wave110a_pick  # -- chosen objects (wave 110A) --

        wave110a_pick.record(plan, card_id, choices)
        from app.rules import chosen_color_pairs45

        chosen_color_pairs45.record_entry(plan, card_id, choices)
        from app.rules import text_global_word71

        text_global_word71.record_entry(plan, card_id, controller, choices)
    # -- replacement effects stage 2 (wave 2E): the counters it enters with, through the counter
    # choke point (122.6, 614.16), in the order its controller chose before it entered (614.12a) --
    from app.rules import (
        devour,  # -- keyword mechanics (wave 9D) -- 702.82b: what it devoured, for "for each creature it devoured"
    )

    if choices and devour.picked(choices.get(devour.WHAT)):
        plan.rules.devoured[plan.oid(card)] = len(devour.picked(choices.get(devour.WHAT)))
        plan.rules.devoured_ids[plan.oid(card)] = devour.picked(choices.get(devour.WHAT))  # (wave 48B: the objects they were, devour.sacrifice)
    from app.rules import layers, riot  # -- keywords (wave 15E) -- 702.136a: "If you don't, it gains haste."

    ch = prepared[0] if prepared is not None else dataclasses.replace(plan.ch(card), abilities=()) if bare else plan.ch(card)  # (-- review 35 -- ``bare``: no "enters with" of its own)
    if riot.gains_haste(ch, choices):
        layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=None, controller=controller,
                          add_keywords=("haste",), duration="permanent", label="Haste (riot)")
    if not preview:
        from app.rules import wave110a_enter  # -- entry types (wave 110A) --

        wave110a_enter.apply(plan, card)
    from app.rules import tribute  # -- keywords (wave 50H) -- 702.104b: "if tribute wasn't paid" reads this

    if tribute.counters(ch, choices):
        plan.rules.tribute_paid.append(plan.oid(card))
        plan.note(f"{plan.name((choices or {})[tribute.OPP])} pays tribute: {card.name} enters with {tribute.counters(ch, choices)} additional +1/+1 counters", [card.id])
    from app.rules import mana_units

    mana_units.entered(plan, card, controller)  # -- mana provenance (wave 18B) -- 106.6: "it gains haste"
    counters = {} if prepared is not None else entering_counters(plan, card, controller, ch, x=x, extra=extra_counters, choices=choices, newcomers=newcomers)
    puts = [(card_id, kind, n) for kind, n in counters.items() if n > 0]
    from app.rules import replace

    # (-- counters (wave 5H) -- with none, other permanents' "enters with an additional …" statics may still add some;
    # ``newcomers``: the permanents entering with it, whose statics don't apply to it, 614.12)
    # -- counters (wave 7C) -- "If ~ was kicked, it enters with two +1/+1 counters on it and with flying" (614.1c, 613.1f)
    if not plan.manual(card):
        from app.rules import layers

        for d in scripts.definitions(ch).values():
            if d["kind"] == "replacement" and d.get("replacement") == "enters_with_counters" and (d.get("grant") or d.get("grant_abilities")) and not d.get("self_in_group") \
                    and _counter_amount(plan, card.id, controller, {**d, "n": 1}, x, newcomers) > 0:
                layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=None, controller=controller,
                                  add_keywords=tuple(d.get("grant") or ()), add_abilities=list(d.get("grant_abilities") or ()),  # (wave 50H: a granted ability)
                                  duration="permanent", label=f"Enters with {(d.get('grant') or d['grant_abilities'])[0]}")
            elif d["kind"] == "replacement" and d.get("replacement") == "enters_prepared":  # -- prepared (wave 13C) -- 722.3a
                from app.rules import keyword_actions

                keyword_actions.become_prepared(plan, card)
    if prepared is not None:
        if prepared[1] is not None:
            replace.do_counters(plan, prepared[1], by=controller)
    elif puts or replace.entering_kinds(plan, replace.candidates(plan, "counters")):
        orders = {k[len(ORDER):]: v for k, v in (choices or {}).items() if k.startswith(ORDER)}
        if preview:
            counter_plan = replace.plan_counters(plan, puts, by=controller, effect=True, entering={card_id: controller},
                                                answers=orders, ask=False, newcomers=newcomers)
            if isinstance(counter_plan, replace.Ask):
                raise counter_plan
            return ch, counter_plan
        replace.put_counters(plan, puts, by=controller, effect=True, entering={card_id: controller}, answers=orders,
                             newcomers=newcomers)
    return (ch, None) if preview else None


def _token_probe(controller: str, spec: dict[str, Any]) -> CardInstance:
    return CardInstance(id="token-probe", name=spec["name"], owner=controller, controller=controller,
                        zone=zone_key(controller, "battlefield"), is_token=True,
                        token=TokenDef(name=spec["name"], power=spec.get("power"), toughness=spec.get("toughness"),
                                       colors=list(spec.get("colors") or []), type_line=spec.get("type_line") or "Token Creature",
                                       text=spec.get("text") or ""))


# -- token entering choices (wave 34A) ----------------------------------------------------------------------
# 614.12 / 614.12a: "As this enters, choose …" applies as ANY permanent enters, a token included: a token copy of Metallic Mimic, a Siege or
# Pithing Needle (707.2: it has the copiable ability, 707.6: it makes its own choice) is asked, by its controller, before it is created (the
# questions come first and the creation instruction then runs once with the answers: replace.create_token_batch).
ENTER = "enter:"  # an answer of a token's entering choice: "enter:<n-th token of the call>:<what>"


def token_entering(plan: Plan, controller: str, spec: dict[str, Any]) -> tuple[CardInstance, list[dict[str, Any]]] | None:
    """The token about to be created as an object (a token copy: its copiable values, 707.2; else its own text) and its "As ~ enters, choose …"
    definitions as it would exist on the battlefield (614.12), or None when it has none."""
    t = spec
    if spec.get("_copy") is not None:
        from app.rules import copying

        ch = copying.characteristics(CopyRecipe.model_validate(spec["_copy"]), plan.info)
        t = {"name": ch.name, "power": ch.power, "toughness": ch.toughness, "colors": sorted(ch.colors), "type_line": copying.type_line(ch),
             "text": ch.oracle_text}
    from app.rules import chosen_forms95

    if "choose" not in (t.get("text") or "").lower() and not any(chosen_forms95.form(line.replace("this creature", "~")) for line in (t.get("text") or "").splitlines()):
        from app.rules import copiable_coin_entry, token_copy_entry

        if not any(copiable_coin_entry.definition(line.replace("this creature", "~"))
                   for line in (t.get("text") or "").splitlines()):
            return None
        incoming = token_copy_entry.probe(plan, controller, spec)
        defs = [d for d in scripts.definitions(plan.ch(incoming)).values()
                if d.get("replacement") == "enters_choice"
                and any(e.get("what") == copiable_coin_entry.WHAT for e in d.get("effects", []))]
        return (incoming, defs) if defs else None
    probe = _token_probe(controller, t)
    defs = [d for d in scripts.definitions(plan.ch(probe)).values() if d["kind"] == "replacement" and d["replacement"] == "enters_choice"]
    return (probe, defs) if defs else None


def token_choices(plan: Plan, evs: list[dict[str, Any]], answers: dict[str, str]) -> tuple[list[list[dict[str, str]]], dict[str, Any] | None]:
    """The entering choices of the tokens these final creation events make, in creation order (APNAP between players, 616.1; each token its own
    question): per event, per token, {"creature type": "Elf", …}; and the first question still open ({"key", "player", "prompt", "options",
    "source"}) or None. A question with no option (no opponent left, 800.4) is skipped."""
    from app.rules import token_copy_entry

    rows, question = token_copy_entry.copy_choices(plan, evs, answers)
    if question is not None:
        return rows, question
    n = 0
    for index, ev in enumerate(evs):
        pid, row = ev["player"], rows[index]
        for k in range(ev['count']):
            if (one := token_entering(plan, pid, token_copy_entry.effective(ev, row[k]))) is not None:
                probe, defs = one
                got: dict[str, str] = {}
                while True:
                    out: dict[str, Any] = {}
                    named_choices(plan, pid, defs, got, out)
                    if (choice := out.get("choice")) is None:
                        break
                    what, key = choice["what"], f"{ENTER}{n + k}:{choice['what']}"
                    if key in answers:
                        got[what] = answers[key]
                        continue
                    from app.rules import copiable_coin_entry, random_entry_choice

                    if what == copiable_coin_entry.WHAT:
                        return rows, {"key": key, "player": pid, "coin_form": True, "source": ev.get("source")}
                    if (value := random_entry_choice.answer(plan, choice, pid)) is not None:
                        answers[key] = got[what] = value
                        continue
                    prompt, options = choice_prompt(plan, probe, pid, choice)
                    if not options:
                        got[what] = ""
                        continue
                    return rows, {"key": key, "player": pid, "prompt": prompt, "options": options, "source": ev.get("source")}
                row[k] = {**row[k], **(out.get("choices") or {})}
                from app.rules import chosen_forms95

                for what95, answer95 in row[k].copy().items():
                    if what95.startswith(chosen_forms95.PREFIX):
                        spec95 = token_copy_entry.effective(ev, row[k])
                        recipe95 = CopyRecipe.model_validate(spec95["_copy"])
                        row[k][token_copy_entry.COPY] = chosen_forms95.recipe(plan, recipe95, what95, answer95).model_dump_json()
                from app.rules import copiable_coin_entry

                if (answer := row[k].get(copiable_coin_entry.WHAT)) in ("heads", "tails"):
                    spec = token_copy_entry.effective(ev, row[k])
                    recipe = CopyRecipe.model_validate(spec["_copy"])
                    row[k][token_copy_entry.COPY] = copiable_coin_entry.form_recipe(plan, recipe, answer).model_dump_json()
        n += ev["count"]
    from app.rules import token_copy_entry

    return token_copy_entry.hosts(plan, evs, rows, answers)


def token_enters_tapped(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    """A token about to be created: does its own text say it enters tapped? (Its creator saying
    "create … tapped" is the effect's own business; both count.)"""
    probe = _token_probe(controller, spec)
    for d in scripts.definitions(chars.of(probe, plan.info)).values():
        if d["kind"] != "replacement":
            continue
        if d["replacement"] == "enters_tapped" and (d.get("unless") is None or not unless_holds(plan, controller, probe, d["unless"])):
            return True
        if d["replacement"] == "enters_with_counters" and d.get("tapped"):
            return True
    return others_enter_tapped(plan, probe, controller)  # -- replacement effects stage 2 (wave 2E): 614.1d --


def token_enters_untapped(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    """-- most-played cards II (wave 45A) -- a token about to be created, under "Lands you control enter untapped" (Horizon Explorer: a tapped Mutavault token enters untapped)."""
    return others_enter_untapped(plan, _token_probe(controller, spec), controller)


# -- zone changes (614.1a "instead", 702.84a, 702.35a, 903.9b) ------------------------------------------
def _from_zone(card: CardInstance) -> str:
    return card.zone.rsplit(":", 1)[-1]


def _self_exile_instead(plan: Plan, card: CardInstance) -> bool:
    """"If ~ would die, exile it instead." (from the battlefield) / "If ~ would be put into a
    graveyard from anywhere, exile it instead." — the object's own replacement effect."""
    frm = _from_zone(card)
    return any(d["kind"] == "replacement" and d.get("replacement") == "exile_instead"
               and (d.get("from") == "anywhere" or frm == "battlefield") for d in _definitions(plan, card).values())


def _self_library_instead(plan: Plan, card: CardInstance) -> str | None:
    """-- instead (wave 20B) -- "If ~ would die, put it on top of / on the bottom of its owner's library instead." (614.1a): where."""
    if _from_zone(card) != "battlefield":
        return None
    return next((str(d["position"]) for d in _definitions(plan, card).values()
                 if d["kind"] == "replacement" and d.get("replacement") == "library_instead"), None)


def _static_exile_all(plan: Plan, card: CardInstance) -> list[tuple[CardInstance, dict[str, Any]]]:
    """The permanents on the battlefield whose static abilities replace this card's trip to the
    graveyard ("If a creature an opponent controls would die, exile it instead.", "If a card or
    token would be put into a graveyard from anywhere, exile it instead."), with the definition that applies."""
    frm = _from_zone(card)
    found: list[tuple[CardInstance, dict[str, Any]]] = []
    for src in plan.state.cards.values():
        if not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) or plan.manual(src):
            continue
        for d in scripts.definitions(plan.ch(src)).values():
            if d["kind"] != "static" or d.get("static") not in ("exile_instead", "hand_instead"):  # (wave 100K: hand_instead, Necromancer's Magemark)
                continue
            if d.get("from") == "battlefield" and frm != "battlefield":
                continue
            whose = d.get("graveyard_of", "any")  # "your graveyard" / "an opponent's graveyard"
            if whose == "you" and card.owner != src.controller or whose == "opponent" and card.owner == src.controller:
                continue
            if d.get("cycling_not_cycled") and (plan.cycling_card == card.id or not any(k.endswith("cycling") for k in plan.ch(card).keywords)):
                continue
            who = d.get("who", "any")
            if who == "card" and card.is_token:
                continue  # "If a card would be put into …": tokens aren't cards (108.2a)
            if who == "card:uncontrolled":  # -- linked exile (wave 30H) -- "a card you didn't control": one in a graveyard, a hand or a library has no controller
                if card.is_token or (frm in ("battlefield", "stack") and card.controller == src.controller):
                    continue
            elif who.startswith("types:"):  # -- instead (wave 20B) -- "an instant or sorcery card": a card (not a token) with one of the types
                if card.is_token or not set(who[6:].split("|")) & plan.ch(card).types:
                    continue
            elif who.startswith("colors:"):  # (wave 100K) Sanctifier en-Vec: any object of those colors, tokens too
                if not set(who[7:].split("|")) & plan.ch(card).colors:
                    continue
            elif who not in ("any", "card"):
                if frm != "battlefield":
                    continue
                if not selectors.matches(plan, selectors.from_key(who), card, plan.ch(card), src.controller, src.id):
                    continue
            if d.get('damaged_source_scope'):
                from app.rules import damage_exile_statics65

                if not damage_exile_statics65.matches(plan, src, card, d['damaged_source_scope']):
                    continue
            found.append((src, d))
    return found


def _record_exile_instead(plan: Plan, card: CardInstance) -> str | None:
    """-- replacement effects stage 2 (wave 2E) -- This turn's "If that creature / a creature dealt
    damage this way / a creature would die this turn, exile it instead" (effects.exile_if_dies):
    the name of the spell or ability whose effect applies, or None. Like every other "exile
    instead" here they agree on what happens, so there is no 616.1 choice between them."""
    turn = plan.state.turn.number
    oid = plan.oid(card)
    for rec in plan.rules.replacements:
        if rec.get("kind") != "exile_if_dies" or rec.get("turn") != turn:
            continue
        ch = plan.ch(card)
        if "oids" in rec:
            if oid not in rec["oids"] or (rec.get("types") and not set(rec["types"]) & ch.types):
                continue
        elif not rec.get("each") or not selectors.matches(plan, selectors.from_key(rec["each"]), card, ch,
                                                          rec["controller"], None):
            continue
        return rec.get("label") or "a replacement effect"
    return None


def _record_exile_cards(plan: Plan, card: CardInstance) -> str | None:
    """-- zone replacements (wave 37B) -- This turn's "If a card would be put into your graveyard from anywhere this turn, exile that card instead"
    (effects.exile_if_dies "cards": Yawgmoth's Will): the name of the spell or ability whose effect applies, or None. It is about cards, so a token
    (111.1) and a copy of a spell (707.10a) are not affected; "your graveyard" is where a card goes whose owner is the effect's controller (400.3)."""
    if card.is_token or card.copy_of is not None:
        return None
    turn = plan.state.turn.number
    for rec in plan.rules.replacements:
        if rec.get("kind") == "exile_cards" and rec.get("turn") == turn and rec.get("whose") == "your" and card.owner == rec["controller"]:
            return rec.get("label") or "a replacement effect"
    return None


# -- zone replacements (wave 22C) -- 614.1a, 616.1: every replacement effect that would put a card into a graveyard.
# They agree (all send it to exile: no choice), or their results differ (exile vs "reveal it and shuffle it into its owner's
# library", top / bottom of the library) and the affected object's controller (its owner if it has none) chooses which
# applies first (616.1); the others then no longer apply, the event being a different one (614.5). A table step can't pause
# (like 903.9b): the card stays where it is, nothing has happened to it yet, and ``offer_616`` asks before anyone gets priority.
class Cand(NamedTuple):
    """One replacement effect that applies: its source's name, its result ("exile" | "library:top" | "library:bottom" |
    "library:shuffle"), whether it is a spell's one-shot "exile it instead" (used up when it applies, 614.5), and the
    effects its controller's replacement adds to the event (Kalitas's token: ``rider``: {"source", "controller",
    "effects", "reflexive"})."""

    label: str
    outcome: str
    used: bool = False
    rider: dict[str, Any] | None = None
    link: str = ""  # -- linked exile (wave 30H) -- 607.2b: the object whose linked replacement effect this is: the card it exiles is "exiled with" it
    counter: str = ""  # -- exile with a counter (wave 50J) -- "exile that card with a blood counter on it instead" (Rayami): the kind of counter the exiled card gets

    @property
    def sig(self) -> str:
        """What the effect does, for the 616.1 question: the same result with the same rider needs no choice."""
        if self.rider is not None and self.rider.get('resolve_exile_record'):
            key = json.dumps(self.rider['resolve_exile_record'], sort_keys=True, default=str)
            return f"{self.outcome}+resolve:{hashlib.sha256(key.encode()).hexdigest()[:32]}"
        if self.rider is None:  # (-- linked exile (wave 30H) -- a linked replacement is another result: what it exiles is "exiled with" its object, so 616.1 asks)
            return f"{self.outcome}+{self.link}" if self.link else self.outcome + (f"+{self.counter}" if self.counter else "")
        key = json.dumps([self.rider["controller"], self.rider["effects"], self.rider["reflexive"], self.link], sort_keys=True, default=str)
        return f"{self.outcome}+{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def _self_shuffle_instead(plan: Plan, card: CardInstance) -> bool:
    """"If ~ would be put into a graveyard from anywhere, reveal ~ and shuffle it into its owner's library instead." (Blightsteel)"""
    return any(d["kind"] == "replacement" and d.get("replacement") == "shuffle_instead" for d in _definitions(plan, card).values())


def zone_candidates(plan: Plan, card: CardInstance, dest: str = "graveyard") -> list[Cand]:
    """The replacement effects that apply to ``card`` going to ``dest`` now (a graveyard, or for a permanent anywhere but
    exile: "if it would leave the battlefield, exile it instead"), in no particular order."""
    frm = _from_zone(card)
    out: list[Cand] = []
    if frm == "battlefield" and dest not in ("exile", "battlefield"):
        if plan.oid(card) in plan.rules.exile_if_leaves:  # 702.84a: "If it would leave the battlefield, exile it instead of putting it anywhere else."
            out.append(Cand("unearth / \"exile it if it would leave the battlefield\"", "exile"))
        if any(d["kind"] == "replacement" and d.get("replacement") == "exile_instead" and d.get("from") == "leaves"
               for d in _definitions(plan, card).values()):
            out.append(Cand(card.name or "its own ability", "exile"))
    # -- Attractions (wave 100L) -- 717.6: to the command zone (its junkyard) instead
    from app.rules import attractions100l

    if dest not in ("battlefield", "exile", "command") and attractions100l.astrotorium(plan, card):
        out.append(Cand("its Astrotorium card back (717.6)", "command"))
    if dest != "graveyard":
        return out
    leaves = any(c.outcome == "exile" for c in out)
    out += _graveyard_candidates(plan, card, frm)
    if leaves:  # (review 22C) 616.1e: a library result still leaves the battlefield, so "exile it if it would leave" applies after it
        out = [c for c in out if not c.outcome.startswith("library:")]  # anyway: no choice between them (a rider still is one)
    return out


def _graveyard_candidates(plan: Plan, card: CardInstance, frm: str) -> list[Cand]:
    out: list[Cand] = []
    if frm == "stack" and plan.oid(card) in plan.rules.bottom_if_graveyard:
        out.append(Cand("its own cast", "library:bottom", True))
    if frm == "stack" and plan.oid(card) in plan.rules.exile_if_graveyard:  # -- refused look/cast-free (wave 3R5) -- a spell cast
        out.append(Cand("its own cast", "exile", True))  # "without paying …": "If that spell would be put into your graveyard, exile it instead"
    if frm == "battlefield" and card.counters.get("finality", 0) > 0:  # 122.1h (-- refused zones/sized (wave 3R4) --)
        out.append(Cand("finality counter", "exile"))
    if _self_exile_instead(plan, card):
        out.append(Cand(card.name or "its own ability", "exile"))
    if (where := _self_library_instead(plan, card)) is not None:  # -- instead (wave 20B) --
        out.append(Cand(card.name or "its own ability", f"library:{where}"))
    if _self_shuffle_instead(plan, card):
        out.append(Cand(card.name or "its own ability", "library:shuffle"))
    for src, d in _static_exile_all(plan, card):
        rider = {"source": src.id, "controller": src.controller, **d["rider"]} if d.get("rider") else None
        out.append(Cand(src.name or "a static ability", "hand" if d["static"] == "hand_instead" else "exile", False, rider, plan.oid(src) if d.get("link") else "", d.get("counter", "")))
    if frm == "battlefield" and (why := _record_exile_instead(plan, card)) is not None:  # -- replacement effects stage 2 (wave 2E) --
        out.append(Cand(why, "exile"))
    if (why := _record_exile_cards(plan, card)) is not None:  # -- zone replacements (wave 37B) -- from any zone
        out.append(Cand(why, "exile"))
    return out


def _pick(plan: Plan, card: CardInstance, cands: list[Cand], dest: str) -> Cand | None:
    """The one result to apply, or None (the card is held and its controller asked: 616.1)."""
    outcomes: dict[str, Cand] = {}
    for c in cands:
        outcomes.setdefault(c.sig, c)
    if len(outcomes) == 1:
        return cands[0]
    plan.rules.pending_616[card.id] = {"oid": plan.oid(card), "dest": dest, "options": {o: c.label for o, c in outcomes.items()},
                                       "cands": {o: c._asdict() for o, c in outcomes.items()},  # (review 22C: as they were when the event happened)
                                       "texts": {o: _OUTCOME_TEXT.get(c.outcome, c.outcome) + (" and " + rider_text(c.rider) if c.rider else "")
                                                 for o, c in outcomes.items()}}
    return None


def rider_text(rider: dict[str, Any]) -> str:
    from app.rules.effects import describe

    return ("later " if rider["reflexive"] else "") + describe(rider["effects"])


def mark_exiled_counters(plan: Plan, card_ids: list[str], kind: str, *, actor: str) -> None:
    """Mark cards exiled by a prepared zone replacement (Rayami / Voidwalker).

    These are cards in exile, not permanents or players receiving counters.
    Call immediately after the committed route, before its rider can move them.
    """
    if not card_ids or not kind or any((c := plan.state.cards.get(cid)) is None or not c.zone.endswith(':exile') for cid in card_ids):
        raise ValueError('Replacement counter marks require current exiled cards')
    plan.do({'type': 'counter', 'card_ids': card_ids, 'kind': kind, 'delta': 1}, actor=actor)


def move_instead(plan: Plan, cid: str, outcome: str | Cand, actor: str | None, *,
                 shuffle_after: list[str] | None = None) -> None:
    """Carry out a replacement's result for a card that was about to go to a graveyard (and what it adds: a token, life)."""
    if isinstance(outcome, Cand):
        if outcome.rider is not None and (outcome.rider.get('resolve_exile_record') or {}).get('optional'):
            from app.rules import resolve_exile

            resolve_exile.offer_optional(plan, cid, outcome, actor)
            return
        move_instead(plan, cid, outcome.outcome, actor, shuffle_after=shuffle_after)
        _record_link(plan, cid, outcome)
        if outcome.counter:  # (it is in exile now: the counter goes on that object)
            plan.do({"type": "counter", "card_ids": [cid], "kind": outcome.counter, "delta": 1}, actor=actor)
        if outcome.rider is not None:
            run_rider(plan, outcome.rider)
        return
    card = plan.state.cards[cid]
    owner = card.owner
    if outcome in ("exile", "battlefield", "hand", "command"):  # (review 23D: battlefield, a discard's "put it onto the battlefield instead"; wave 100K: hand; wave 100L: 717.6)
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": outcome}}, actor=actor)
        return
    where = outcome.split(":", 1)[1]
    if where == "shuffle":  # 701.24 (shuffle), "reveal": its name is public as it goes (a card from a hidden zone shows itself)
        plan.note(f"{card.name or 'The card'} is revealed and shuffled into its owner's library instead", [cid])
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "top"}, actor=actor)
        if shuffle_after is None:
            plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)
        else:
            shuffle_after.append(owner)
        return
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": where}, actor=actor)


def _record_link(plan: Plan, cid: str, cand: Cand) -> None:
    """-- linked exile (wave 30H) -- 607.2b: what a linked replacement effect exiled is "exiled with" the object it belongs to (as it was: 608.2h)."""
    if cand.link and cand.outcome == "exile":
        from app.rules import exiled_with

        exiled_with.record(plan, {"source_object": cand.link}, [cid])


def run_rider(plan: Plan, rider: dict[str, Any]) -> None:
    """The extra effects of a replacement ("… and create a 2/2 black Zombie creature token"): part of the replacing event, so
    carried out now by the replacement's controller (614.6); "When you do, …" (603.12) is a reflexive triggered ability."""
    if rider.get('resolve_exile_record') is not None:
        from app.rules import resolve_exile

        resolve_exile.after_exile(plan, rider['card'], rider['resolve_exile_record'])
        return
    src = plan.state.cards.get(rider["source"])
    if src is None:
        return
    ctx = {"controller": rider["controller"], "source_card": src.id, "source_object": plan.oid(src), "name": src.name or "",
           "targets": [], "stack_id": "", "kind": "replacement", "effects": rider["effects"], "next": len(rider["effects"]), "x": None,
           "event": None}
    if rider["reflexive"]:
        from app.rules.triggers import _add

        _add(plan, controller=rider["controller"], source_card=src.id, source_object=ctx["source_object"], name=ctx["name"], index=7300,
             definition={"kind": "triggered", "trigger": "reflexive", "effects": rider["effects"], "optional": False})
        return
    from app.rules.effects import PRIMITIVES

    for e in rider["effects"]:
        if not PRIMITIVES[e["do"]](plan, ctx, e):
            break


_OUTCOME_TEXT = {"exile": "Exile it", "battlefield": "Put it onto the battlefield", "hand": "Return it to its owner's hand","library:top": "Put it on top of its owner's library", "library:bottom":
                 "Put it on the bottom of its owner's library", "library:shuffle": "Reveal it and shuffle it into its owner's library",
                 "command": "Put it into its owner's command zone"}  # (wave 100L: 717.6)


def offer_616(plan: Plan) -> bool:
    """Ask the controller (616.1) of a held card which replacement applies. True while a question is open."""
    from app.rules.plan import decide

    r = plan.rules
    for cid, p in list(r.pending_616.items()):
        card = plan.state.cards.get(cid)
        if card is None or plan.oid(card) != p["oid"]:
            r.pending_616.pop(cid, None)  # (it went on elsewhere: the moment has passed)
            continue
        chooser = card.controller if _from_zone(card) in ("battlefield", "stack") else card.owner  # (a spell has a controller too: 110.2, 616.1)
        decide(plan, player=chooser, kind="choose_one",
               prompt=f"{card.name or 'A card'} would be put into a graveyard: which replacement effect applies first? (616.1)",
               options=[DecisionOption(id=o, label=f"{src}: {p['texts'][o]}",
                                       card_id=(((p.get('cands') or {}).get(o) or {}).get('rider') or {}).get('source') or None)
                        for o, src in p["options"].items()],
               resume={"step": "zone_replace_order", "card": cid}, source=card)
        return True
    return False


def resume_616(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import replace

    cid = d.resume["card"]
    p = plan.rules.pending_616.pop(cid, None)
    card = plan.state.cards.get(cid)
    if p is None or card is None or plan.oid(card) != p["oid"] or chosen[0] not in p["options"]:
        replace.run_then(plan, d.resume.get('abort_then') or d.resume.get('then'))
        return
    commander_key = card.commander_key
    # (review 22C) the effects that applied when the event happened (614.1, 616.1): a source that left with it (Rest in Peace
    # destroyed alongside Progenitus) still applies; recomputing them now could leave the card stranded where it was
    cand = Cand(**p["cands"][chosen[0]]) if chosen[0] in (p.get("cands") or {}) else \
        next((c for c in zone_candidates(plan, card, p["dest"]) if c.sig == chosen[0]), None)
    if cand is None:  # (nothing applies any more: the event goes on as it was, its replacements looked at again)
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": p["dest"]}}, actor=card.controller)
        _finish_616_then(plan, cid, d.resume.get('then'), commander_key)
        return
    if cand.used:  # (a spell cast "without paying …": its one-shot "exile it instead" is used up, 614.5)
        plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != p["oid"]]
        plan.rules.bottom_if_graveyard = [o for o in plan.rules.bottom_if_graveyard if o != p["oid"]]
    from app.game.rules_state import ObjectRef

    saved_after = plan.shuffle_after
    plan.shuffle_after = [] if p.get("defer_shuffle") else saved_after
    saved_retained = plan.shuffle_retained
    plan.shuffle_retained = tuple(ObjectRef.model_validate(ref) for ref in p.get('shuffle_retained', ()))
    try:
        move_instead(plan, cid, cand, p.get("actor") or card.controller, shuffle_after=plan.shuffle_after)
    finally:
        plan.shuffle_retained = saved_retained
        deferred = plan.shuffle_after
        plan.shuffle_after = saved_after
    if p.get('defer_shuffle') and deferred and d.resume.get('then'):
        d.resume['then'].setdefault('shuffle_after', []).extend(deferred)
    _finish_616_then(plan, cid, d.resume.get('then'), commander_key)


def _finish_616_then(plan: Plan, cid: str, then: dict[str, Any] | None, commander_key: str | None) -> None:
    """A resolving caller waits for the selected move's native commander choice too."""
    from app.rules import replace

    if not then:
        return
    # Shuffling gives hidden cards new opaque IDs. Native commander designation
    # follows that same physical card through this completed zone change.
    if commander_key:
        destination = plan.rules.pending_903_9b.get(cid)
        current = next((c for c in plan.state.cards.values() if c.commander_key == commander_key), None)
        if destination and current is not None and current.id != cid and _from_zone(current) == destination:
            plan.rules.pending_903_9b[current.id] = plan.rules.pending_903_9b.pop(cid)
            cid = current.id
        cid = next((c for c in plan.rules.pending_903_9b
                    if c in plan.state.cards and plan.state.cards[c].commander_key == commander_key), cid)
    if then and cid in plan.rules.pending_903_9b and offer_903_9b(plan, only=cid):
        assert plan.rules.decision is not None
        assert plan.rules.decision.resume is not None
        plan.rules.decision.resume['then'] = then
        card = plan.state.cards.get(plan.rules.decision.resume['card'])
        if card is not None:
            plan.rules.decision.resume['then_object'] = plan.oid(card)
        return
    replace.run_then(plan, then)


def leave_stack_instead(plan: Plan, card: CardInstance, controller: str) -> bool:
    """A spell leaving the stack for a graveyard (resolved or countered) that a replacement sends elsewhere. True: handled
    (moved, or held for a 616.1 choice)."""
    cands = zone_candidates(plan, card)
    if not cands:
        return False
    pick = _pick(plan, card, cands, "graveyard")
    if pick is not None:
        if pick.used:
            plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != plan.oid(card)]
            plan.rules.bottom_if_graveyard = [o for o in plan.rules.bottom_if_graveyard if o != plan.oid(card)]
        move_instead(plan, card.id, pick, controller)
    return True


def _commander_instead(plan: Plan, card: CardInstance, dest: str) -> bool | None:
    """903.9b: a commander that would be put into its owner's hand or library may go to the command
    zone instead. True: a remembered answer ("always" / "this turn", the same memory key as 903.9a
    with the destination as its context) says so and the move is replaced. None: no answer is known
    — a ``Plan.do`` step can't pause for a decision, so the move happens as asked and its owner is
    asked right after (``pending_903_9b``, offered by app/rules/sba.py before anyone gets priority)
    whether it goes to the command zone instead; the answer is remembered for the next time."""
    from app.rules.engine import remembered

    if not card.commander_key or card.owner not in plan.live():
        return False
    given = plan.rules.answers_903_9b.pop(f"{plan.oid(card)}>{dest}", None)  # asked before the move
    if given is not None:
        return given == "yes"
    answer = remembered(plan, card.owner, f"commander_zone:{card.commander_key}", dest)
    if answer is None and plan.probe_903 is not None:
        plan.probe_903.append((card.id, dest))  # (a look ahead: ask_903_9b_first asks before the real move)
    return True if answer == "yes" else False if answer == "no" else None


def kept_counters(plan: Plan, payload: dict[str, Any]) -> dict[str, Any]:
    """-- counters (wave 51E) -- "Counters remain on ~ as it moves to any zone other than a player's hand or library." (Skullbriar, Me the Immortal): its ability
    works in the zone it moves from (the rulings: not with it lost there, Yixlid Jailer), and the counters aren't put on it again (122.6: no doubling, no trigger)."""
    if payload.get("type") != "move" or (payload.get("to") or {}).get("zone") in ("hand", "library"):
        return payload
    keep = [cid for cid in payload.get("card_ids") or [] if (payload.get("routes", {}).get(cid, payload.get("to") or {})).get("zone") not in ("hand", "library")
            and (c := plan.state.cards.get(cid)) is not None and c.counters
            and any(d.get("static") == "keep_counters" for d in _definitions(plan, c).values())]
    return {**payload, "keep_counters": keep} if keep else payload


def replace_move(plan: Plan, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Apply the zone-change replacements to a ``move`` (or ``mill``) step before it happens. Cards
    whose move is replaced are moved separately to where the replacement says; the rest move as
    asked. Self-replacement first (614.15), then the object's own and the statics' "exile instead"
    (all of which agree, so there is no 616.1 choice to make), then madness, then 903.9b."""
    kind = payload.get("type")
    if kind == "move":
        from app.rules import creature_entry_redirect

        payload = creature_entry_redirect.move(plan, payload)
    if kind == "mill":
        return _replace_mill(plan, payload, actor)
    if kind != "move":
        return payload
    if payload.get("routes"):
        # Each route was prepared against the same pre-event environment.
        return payload
    dest = (payload.get("to") or {}).get("zone")
    r = plan.rules
    if dest == "graveyard" and payload.get("index") is not None and (who := payload["to"].get("player")) and all(
            (c := plan.state.cards.get(cid)) is not None and c.zone == zone_key(who, "graveyard") for cid in payload.get("card_ids") or []):
        return payload  # -- graveyard order (wave 40C) -- 404.3: arranging a graveyard moves nothing between zones: no replacement applies
    replaced: list[tuple[str, str, str]] = []  # (card, zone it goes to instead, why)
    riders: list[dict[str, Any]] = []  # -- zone replacements (wave 22C) -- what the replacements add (a token): after the moves
    held: list[str] = []  # -- zone replacements (wave 22C) -- cards waiting for their controller's 616.1 choice
    madness: list[tuple[str, str]] = []
    links: dict[str, Cand] = {}  # -- linked exile (wave 30H) -- the linked replacement effects that apply (607.2b)
    marks: dict[str, str] = {}  # -- exile with a counter (wave 50J) -- the card -> the kind of counter its exiling puts on it
    for cid in payload.get("card_ids") or []:
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        frm = _from_zone(card)
        oid = plan.oid(card)
        if dest == "graveyard" and frm == "hand" and actor not in (None, card.owner) and any(
                d["kind"] == "replacement" and d.get("replacement") == "discard_battlefield" for d in _definitions(plan, card).values()):
            # -- discard causes (wave 23D) -- 614.1a: "If a spell or ability an opponent controls causes you to discard this card, put it onto
            # the battlefield instead": a static ability of the card, not a self-replacement effect (614.15), so with Rest in Peace its
            # owner chooses which applies (616.1, review 23D)
            pick = _pick(plan, card, [*zone_candidates(plan, card, dest), Cand(card.name or "its own ability", "battlefield")], dest)
            if pick is None:
                held.append(cid)
            else:
                replaced.append((cid, pick.outcome, pick.label))
                riders += [pick.rider] if pick.rider is not None else []
            continue
        if dest == "graveyard" and frm == "hand":
            # 616.1: madness and an "exile instead" static (Rest in Peace) would both replace a
            # discard; the card's owner chooses. Only madness leads anywhere different (the
            # card is exiled either way, and may then be cast), so it is applied first.
            cost = _madness_cost(plan, card)
            if cost is not None:
                madness.append((cid, cost))
                continue
        if cands := zone_candidates(plan, card, dest or ""):  # -- zone replacements (wave 22C) -- 616.1 among the candidates
            pick = _pick(plan, card, cands, dest or "")
            if pick is None:
                held.append(cid)  # two different results: its controller chooses (asked before priority)
                continue
            if pick.used:  # (a spell cast "without paying …": its one-shot "exile it instead" is used up, 614.5)
                r.exile_if_graveyard = [o for o in r.exile_if_graveyard if o != oid]
                r.bottom_if_graveyard = [o for o in r.bottom_if_graveyard if o != oid]
            if frm == "battlefield":  # (it leaves: the object is gone, and a "leaves the battlefield" record with it)
                r.exile_if_leaves = [o for o in r.exile_if_leaves if o != oid]
            replaced.append((cid, pick.outcome, pick.label))
            if pick.link:
                links[cid] = pick
            if pick.counter:
                marks[cid] = pick.counter
            if pick.rider is not None:
                riders.append(pick.rider)
            continue
        if dest in ("hand", "library"):
            answer = _commander_instead(plan, card, dest)
            if answer:
                replaced.append((cid, "command", "903.9b"))
            elif answer is None:
                r.pending_903_9b[cid] = dest  # asked right after the move (sba → offer_903_9b)
    for cid in held:  # (review 23D: who moved it, for "a spell or ability an opponent controls causes you to discard", 701.9)
        r.pending_616[cid]["actor"] = actor
        if plan.shuffle_after is not None:
            r.pending_616[cid]["defer_shuffle"] = True
        if plan.shuffle_retained:
            r.pending_616[cid]['shuffle_retained'] = [ref.model_dump(mode='json') for ref in plan.shuffle_retained]
    if held:  # -- zone replacements (wave 22C) -- they stay put until chosen (616.1: offer_616, before anyone gets priority)
        if dest == "graveyard":  # (review 22C: a held discard is discarded all the same, 701.9a, whichever replacement applies)
            from app.rules import history

            history.note_discards(plan, [cid for cid in held if _from_zone(plan.state.cards[cid]) == "hand"])
        payload = {**payload, "card_ids": [c for c in payload["card_ids"] if c not in held]}
        if not payload["card_ids"] and not replaced and not madness:
            return {"type": "rules_log", "text": "Two replacement effects apply: the choice comes first (616.1)", "card_ids": held[:20]}
    if not replaced and not madness:
        return payload
    if dest == "graveyard":  # -- this-turn history (wave 4D) -- a discard put elsewhere instead is still a discard (701.9a)
        from app.rules import history

        history.note_discards(plan, [cid for cid in [c for c, _, _ in replaced] + [c for c, _ in madness]
                                     if _from_zone(plan.state.cards[cid]) == "hand"])
    if (dest == "library" and payload.get("library_positions") is not None and replaced
            and not held and not madness and not riders and not links and not marks
            and all(zone in ("command", "exile") for _, zone, _ in replaced)):
        # All choices and native replacements were prepared against the same table above.
        # Keep this opt-in event atomic, including merged commanders' other physical cards.
        outcomes = {cid: zone for cid, zone, _ in replaced}
        routes = {cid: {"player": plan.state.cards[cid].owner, "zone": outcomes.get(cid, "library")}
                  for cid in payload["card_ids"]}
        return {**payload, "routes": routes, "rest_zone": "library"}
    for cid, zone, _why in replaced:
        owner = plan.state.cards[cid].owner
        # (-- merged permanents (wave 18D) -- 903.9c: the cards of a merged / melded commander that aren't commanders go where it was headed)
        also = {"rest_zone": dest, **{k: payload[k] for k in ("position", "index") if payload.get(k) is not None}} \
            if zone == "command" and plan.state.cards[cid].merged and dest in ("hand", "library") else {}  # (review 18D: top / bottom too)
        if zone.startswith("library:"):  # -- instead (wave 20B) -- on top of / on the bottom of its owner's library (22C: or shuffled in)
            move_instead(plan, cid, zone, actor, shuffle_after=plan.shuffle_after)
            continue
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": zone}, **also}, actor=actor)
        if cid in links:
            _record_link(plan, cid, links[cid])
        if cid in marks:  # (it is in exile now: the counter goes on that object)
            plan.do({"type": "counter", "card_ids": [cid], "kind": marks[cid], "delta": 1}, actor=actor)
    for rider in riders:  # -- zone replacements (wave 22C) -- "… instead exile it and create a token": part of the replacing event
        run_rider(plan, rider)
    for cid, cost in madness:
        _discard_into_exile(plan, cid, cost, actor)
    taken = {cid for cid, _, _ in replaced} | {cid for cid, _ in madness}
    rest = [c for c in payload["card_ids"] if c not in taken]
    if rest:
        return {**payload, "card_ids": rest}
    whys = sorted({why for _, _, why in replaced})
    text = ("Exiled instead" + (f" ({', '.join(whys)})" if whys and whys != ["903.9b"] else "")) if replaced else "Discarded into exile (madness)"
    if replaced and all(zone.startswith("library:") for _, zone, _ in replaced):
        text = "Put into its owner's library instead"
    if replaced and all(zone == "battlefield" for _, zone, _ in replaced):  # (review 23D: Obstinate Baloth)
        text = "Put onto the battlefield instead"
    if replaced and all(zone == "command" for _, zone, _ in replaced):
        text = f"Put into the command zone instead ({', '.join(whys)})"  # (903.9b; wave 100L: 717.6)
    ids = [cid for cid, _, _ in replaced] + [cid for cid, _ in madness]
    return {"type": "rules_log", "text": text, "card_ids": ids[:20]}  # (a log line names at most 20 cards)


def _replace_mill(plan: Plan, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Milled cards that would be exiled instead ("If ~ would be put into a graveyard from anywhere",
    a Rest in Peace on the battlefield): the mill becomes one move per card, in library order."""
    if payload.get("to", "graveyard") != "graveyard":
        return payload
    pid = payload.get("player") or actor or plan.actor
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    top = library[: int(payload.get("count", 1))]
    picks = {cid: zone_candidates(plan, plan.state.cards[cid]) for cid in top}  # -- zone replacements (wave 22C) --
    if not any(picks.values()):
        return payload
    changed: list[str] = []
    # Finish the simultaneous mill before shuffling: shuffles replace hidden IDs,
    # and the other cards selected for this mill must still go to their destinations.
    shuffle_after: list[str] = []
    for cid in top:
        card = plan.state.cards[cid]
        pick = _pick(plan, card, picks[cid], "graveyard") if picks[cid] else ""
        if pick is None:
            continue  # (waits for its controller's 616.1 choice; it stays in the library meanwhile)
        if not isinstance(pick, Cand):  # (no replacement: it is milled)
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "graveyard"}}, actor=actor)
            continue
        changed.append(cid)
        move_instead(plan, cid, pick, actor, shuffle_after=shuffle_after)
    for owner in shuffle_after:
        plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)
    return {"type": "rules_log", "text": f"{plan.name(pid)} milled {len(top)}: replaced by other effects", "card_ids": changed[:20]}


def _madness_cost(plan: Plan, card: CardInstance) -> str | None:
    """702.35a madness: a card discarded from a hand is discarded into exile instead."""
    from app.rules import madness_costs

    if plan.manual(card):
        return None
    from app.rules import wave110a_grants  # -- grants (wave 110A) -- a static gives the card madness

    return next((cost for ab in plan.ch(card).abilities if ab.kind == "keywords" and "madness" in ab.keywords
                 and (cost := madness_costs.line(ab.text)) is not None), None) or wave110a_grants.madness(plan, card)


def _discard_into_exile(plan: Plan, cid: str, cost: str, actor: str | None, *, already_moved: bool = False) -> None:
    """702.35a: "… discard it into exile. When this card is exiled this way, its owner may cast it by
    paying [cost] rather than its mana cost. If that player doesn't, they put this card into their
    graveyard." — the exile, then the reflexive trigger that offers the cast."""
    from app.rules.triggers import _add

    card = plan.state.cards[cid]
    if not already_moved:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    plan.rules.free_casts.append(cid)
    plan.rules.alt_costs[cid] = cost
    _add(plan, controller=card.owner, source_card=cid, source_object=plan.oid(cid), name=card.name, index=8000,
         definition={"kind": "triggered", "trigger": "madness", "optional": False, "target": None,
                     "effects": [{"do": "madness_offer", "card": cid, "cost": cost}]})


def offer_903_9b(plan: Plan, *, only: str | None = None) -> bool:
    """A commander that was just put into its owner's hand or library without a known answer to
    903.9b: ask its owner now (the one place, whatever moved it). Returns True while a question is
    open. The answer is remembered (the 903.9a memory key with the destination as its context), so
    the next such move is replaced outright."""
    from app.rules.plan import decide

    r = plan.rules
    for cid, dest in list(r.pending_903_9b.items()):
        if only is not None and cid != only:
            continue
        card = plan.state.cards.get(cid)
        if card is None or _from_zone(card) != dest or not card.commander_key or card.owner not in plan.live():
            r.pending_903_9b.pop(cid, None)  # it went on elsewhere: the moment has passed
            continue
        where = "your library" if dest == "library" else "your hand"
        decide(plan, player=card.owner, kind="confirm",
               prompt=f"{card.name} was put into {where}: put it into the command zone instead? (903.9b)",
               options=[DecisionOption(id="yes", label="Command zone"), DecisionOption(id="no", label=f"Keep it in {where}")],
               resume={"step": "commander_instead", "card": cid, "dest": dest}, source=card,
               memory_key=f"commander_zone:{card.commander_key}", memory_context=dest)
        return True
    return False


# Effect primitives that may put a card from a public zone into its owner's hand or library.
MOVERS_903_9B = frozenset({"bounce", "return_card", "return_choice", "return_yours", "to_library", "shuffle_library",
                           "delayed_move", "counter"})


def ask_903_9b_first(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """903.9b is a replacement effect ("… may put it into the command zone instead"): its owner
    chooses before the commander moves, not after it has landed in a hand or library. Before a
    resolving instruction that may move a commander there runs, it is looked ahead on a scratch
    copy of the table; a commander it would move without a known answer has its owner asked now
    (the decision's resume runs the instruction for real, the answer applying to that move).
    True while the question is open. Moves made outside a resolution (by hand, as a cost) are
    still asked right after (``offer_903_9b``)."""
    import copy

    from app.rules.effects import PRIMITIVES  # (effects imports this module)
    from app.rules.engine import remembered
    from app.rules.plan import Plan, decide

    if e.get("do") not in MOVERS_903_9B:
        return False
    if e.get("do") == "counter" and e.get("to") not in ("hand", "top", "bottom"):
        return False
    live = plan.live()
    r = plan.rules
    waiting = [c for c in plan.state.cards.values()
               if c.commander_key and c.owner in live and _from_zone(c) not in ("hand", "library", "command")
               and any(remembered(plan, c.owner, f"commander_zone:{c.commander_key}", dest) is None
                       and f"{plan.oid(c)}>{dest}" not in r.answers_903_9b for dest in ("hand", "library"))]
    if not waiting:
        return False
    probe = Plan.__new__(Plan)
    probe.__dict__.update(plan.__dict__)
    probe.state = plan.state.model_copy(deep=True)
    probe.steps = list(plan.steps)
    probe.rng = plan.rng  # (an entropy source: what is random is recorded as the steps, never replayed from it)
    probe.probe_903 = []
    pctx = copy.deepcopy(ctx)
    pctx["next"] = int(pctx.get("next") or 0) + 1
    try:
        PRIMITIVES[e["do"]](probe, pctx, copy.deepcopy(e))
    except Exception:  # noqa: BLE001  (a look ahead only: the real run reports its own problems)
        return False
    for cid, dest in probe.probe_903:
        card = plan.state.cards.get(cid)
        if card is None or _from_zone(card) in ("hand", "library", "command"):
            continue
        key = f"{plan.oid(card)}>{dest}"
        if key in r.answers_903_9b:
            continue
        where = "your library" if dest == "library" else "your hand"
        name = "Your commander" if card.face_down else card.name
        decide(plan, player=card.owner, kind="confirm",
               prompt=f"{name} would be put into {where}: put it into the command zone instead? (903.9b)",
               options=[DecisionOption(id="yes", label="Command zone"), DecisionOption(id="no", label=f"Into {where}")],
               resume={"step": "commander_first", "ctx": ctx, "key": key}, source=card,
               memory_key=f"commander_zone:{card.commander_key}", memory_context=dest)
        return True
    return False


def resume_commander_first(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects  # (effects imports this module)

    plan.rules.answers_903_9b[d.resume["key"]] = chosen[0]
    continue_effects(plan, d.resume["ctx"])  # (the instruction runs now, with the answer)


def resume_commander_instead(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import replace

    cid = d.resume["card"]
    plan.rules.pending_903_9b.pop(cid, None)
    card = plan.state.cards.get(cid)
    if chosen[0] == "yes" and card is not None and _from_zone(card) == d.resume["dest"] \
            and (not d.resume.get('then_object') or plan.oid(card) == d.resume['then_object']):
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "command"}}, actor=card.owner)
    replace.run_then(plan, d.resume.get('then'))


# -- damage prevention (615) ------------------------------------------------------------------------
DamageEvent = dict[str, Any]  # {"source_card", "source_oid", "target" (player id or card id), "amount", "combat", "prevented"}


def _static_records(plan: Plan) -> list[dict[str, Any]]:
    out = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d["kind"] == "static" and d.get("static") == "prevent" and statics.static_if_holds(plan, d, c):  # (wave 35D: "As long as …", 611.3a)
                out.append({"kind": "prevent", "controller": c.controller, "source": plan.oid(c), "source_card": c.id,
                            "scope": d["scope"]})
    return out


def _records(plan: Plan) -> list[dict[str, Any]]:
    """Prevention effects in force: statics of permanents on the battlefield, then this turn's
    records (a record from another turn has expired: "this turn")."""
    from app.rules.timed_damage_replacements import active

    r = plan.rules
    r.replacements = [rec for rec in r.replacements if active(plan, rec)]
    return _static_records(plan) + [rec for rec in r.replacements if rec.get("kind") == "prevent"]


def _source_card(plan: Plan, ev: DamageEvent) -> CardInstance | None:
    card = plan.state.cards.get(ev.get("source_card") or "")
    return card if card is not None and plan.oid(card) == ev.get("source_oid") else None


def _object_matches(plan: Plan, spec: str, card: CardInstance, you: str, source_card: str | None) -> bool:
    if spec == "self":
        return card.id == source_card
    if spec == "attached":  # "enchanted creature" / "equipped creature": what the source is attached to now
        src = plan.state.cards.get(source_card or "")
        return src is not None and src.attached_to == card.id
    return selectors.matches(plan, selectors.from_key(spec), card, plan.ch(card), you, source_card)


def _target_in_scope(plan: Plan, sc: dict[str, Any], you: str, source_card: str | None, target: str) -> bool:
    if target in plan.state.players:
        want = sc.get("to_players")
        if want is None:
            return bool(sc.get("any_target"))
        return not (want == "you" and target != you or want == "opponent" and target == you)
    card = plan.state.cards.get(target)
    if card is None:
        return False
    if sc.get("to_oids"):
        return plan.oid(card) in sc["to_oids"]
    if sc.get("to_objects"):
        return _object_matches(plan, sc["to_objects"], card, you, source_card)
    return bool(sc.get("any_target"))


def _source_in_scope(plan: Plan, sc: dict[str, Any], you: str, source_card: str | None, ev: DamageEvent) -> bool:
    if sc.get("by_oids"):
        return ev.get("source_oid") in sc["by_oids"]
    if sc.get("by_source"):  # -- prevention riders (wave 17A) -- "red sources", "sources you don't control" (609.7c)
        from app.rules import replace

        who = replace.Candidate(id="", event="damage", match={}, op={}, controller=you, source_card=source_card, source_oid=None,
                                seq=(0,), label="")
        return replace._source_matches(plan, sc["by_source"], who, ev)
    if sc.get("by_objects"):
        src = _source_card(plan, ev)
        return src is not None and _object_matches(plan, sc["by_objects"], src, you, source_card)
    return True


def _applies(plan: Plan, rec: dict[str, Any], ev: DamageEvent) -> bool:
    """Does a "prevent all …" effect apply to this damage event? Its scope names what the damage
    would be dealt to and/or by; combat / noncombat when it says so (609.7c: a static's source
    filter applies to any source with the property, on the battlefield or not)."""
    sc = rec["scope"]
    you, source_card = rec["controller"], rec.get("source_card")
    if sc.get("combat") is not None and bool(sc["combat"]) != bool(ev.get("combat")):
        return False
    if sc.get("to_or_by"):  # "… dealt to and dealt by ~" (Fog Bank): either side
        return _target_in_scope(plan, sc, you, source_card, ev["target"]) or _source_in_scope(plan, sc, you, source_card, ev)
    return _target_in_scope(plan, sc, you, source_card, ev["target"]) and _source_in_scope(plan, sc, you, source_card, ev)


def _label(plan: Plan, key: str) -> str:
    if key in plan.state.players:
        return plan.name(key)
    card = plan.state.cards.get(key)
    return (card.name if card is not None else None) or "the permanent"


def _shield_signature(plan: Plan, ev: DamageEvent) -> tuple[Any, ...]:
    """What makes two sources' damage to a shielded target interchangeable: the same amount from
    literally identical objects (same card or token definition, controller, counters, attachments,
    continuous effects on them) — anything else (a damage trigger, a keyword) could make the outcome
    differ, so the choice is asked (615.7)."""
    src = _source_card(plan, ev)
    if src is None:
        return (ev["amount"] - ev["prevented"], None)
    token = src.token
    identity = (src.card_id, src.face, src.face_down, token.name if token else None, token.text if token else None,
                token.power if token else None, token.toughness if token else None, tuple(token.colors) if token else ())
    return (ev["amount"] - ev["prevented"], src.controller, src.commander_key, identity,
            tuple(sorted(src.counters.items())), src.attached_to,
            tuple(sorted(o.id for o in plan.state.cards.values() if o.attached_to == src.id)),
            tuple(sorted(e.id for e in plan.rules.effects if plan.oid(src) in e.affected)),
            tuple(sorted(m.value or m.name for m in src.effects)))


# -- replacement effects stage 2 (wave 2E) -- The prevention of one damage batch (the "prevent all
# …" statics and records above, the 615.7 shields) now happens together with the damage replacement
# effects, event by event in the order the affected player chooses (616.1): app/rules/replace.py
# ``plan_damage`` (combat damage and the damage / fight primitives call it). The 615.7 choice of
# which source's damage a shield prevents first keeps its decision ("shield_order").
def resume_shield_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import replace

    order = [*(d.resume.get("order") or []), chosen[0]]
    replace.resume_site(plan, d.resume, dict(d.resume.get("answers") or {}), order)


def prevent_all(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Prevent all [combat] damage that would be dealt [to …] [by …] this turn": a record for this
    turn, with its source (the object and the card: "other creatures you control" is judged from
    it, and the prevention effect is named after it). A targeted one locks its target (the object
    it is now: 400.7); with no legal target left nothing is recorded. "~" ("him" / "her" for a
    planeswalker: Gideon Jura) is the source as the object it is now (400.7: once it left, a new
    object isn't protected)."""
    from app.rules.effects import _cards

    scope = dict(e["scope"])
    if e.get("role") == "both":  # -- combat (wave 5C) -- "dealt to and dealt by that creature" (Maze of Ith)
        oids = [plan.oid(c) for c in _cards(plan, ctx, e["who"])]
        if not oids:
            return True
        scope["to_oids"] = scope["by_oids"] = oids
    elif e.get("who"):  # (-- prevention variants (wave 12B) -- "to it": what an earlier instruction named)
        oids = [plan.oid(c) for c in _cards(plan, ctx, e["who"])]
        if not oids:
            return True
        scope["by_oids" if e.get("role") == "by" else "to_oids"] = oids
    source = ctx.get("source_object")
    for side, locked in (("to_objects", "to_oids"), ("by_objects", "by_oids")):
        if scope.get(side) == "self" and source:
            del scope[side]
            scope[locked] = [source]
    plan.rules.replacements.append({"id": secrets.token_hex(4), "kind": "prevent", "turn": plan.state.turn.number,
                                    "controller": ctx["controller"], "source": source,
                                    "source_card": ctx.get("source_card"), "scope": scope,
                                    **({"until": "next_turn", "until_player": ctx["controller"]} if e.get("duration") == "next_turn" else {}),
                                    **({"rider": e["rider"]} if e.get("rider") else {})})  # (wave 17A) 615.5
    return True
