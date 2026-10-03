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

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, TokenDef, zone_key
from app.rules import characteristics as chars
from app.rules import conditions, scripts, selectors, values

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


def entry_plan(plan: Plan, card: CardInstance, controller: str, *, pay_life: bool | None = None,
               tapped: bool = False, answers: dict[str, str] | None = None, x: int | None = None,
               extra: dict[str, int] | None = None, reserved: set[str] | None = None) -> dict[str, Any]:
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
    # -- copy system (wave 2F): "You may have ~ enter as a copy of …" (707.5, 614.12a): chosen first;
    # then the rest of this plan reads the copied text (app/rules/copying.py) --
    from app.rules import copying

    if copying.entering(plan, card, controller, answers, out):
        return out
    defs = [d for d in _definitions(plan, card).values() if d["kind"] == "replacement"]
    answers = dict(answers or {})
    for d in defs:  # "As ~ enters, choose a color." (614.1c): the answer is recorded on the permanent
        if d["replacement"] != "enters_choice":
            continue
        for e in d.get("effects") or []:
            what = e.get("what")
            if e.get("do") != "choose_value" or not what:
                continue
            if what in answers:
                out.setdefault("choices", {})[what] = answers[what]
            elif "choice" not in out:
                out["choice"] = {"what": what}
    from app.rules import battles  # 310.9a: a battle's protector is chosen as it enters

    battles.entry_choice(plan, plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"),
                                                                "controller": controller})), controller, answers, out)
    for d in defs:
        kind = d["replacement"]
        if kind == "enters_tapped":
            unless = d.get("unless")
            if unless is None or not unless_holds(plan, controller, card, unless):
                out["tapped"] = True
        # "~ enters tapped with two charge counters on it."; -- entry forms (wave 5F) -- the Thriving lands
        elif kind in ("enters_with_counters", "enters_choice") and d.get("tapped"):
            out["tapped"] = True
    if not out["tapped"] and others_enter_tapped(plan, card, controller):  # -- replacement effects stage 2 (wave 2E) --
        out["tapped"] = True
    for d in defs:
        if d["replacement"] != "pay_life_or_tapped":
            continue
        life = int(d["life"])
        if out["tapped"] or "choice" in out:
            continue  # it enters tapped anyway ("put it onto the battlefield tapped"), or another choice comes first
        player = plan.state.players.get(controller)
        if player is None or player.life < life:
            out["tapped"] = True  # 119.4: life can be paid only from a life total of at least that much
            continue
        if pay_life is None:
            out["choice"] = {"life": life}
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
    if out.get("choice", {}).get("what") == enter_cost.WHAT and reserved:
        out["choice"]["reserved"] = sorted(reserved)
    # -- replacement effects stage 2 (wave 2E): the counters it enters with (122.6) --
    orders = {k: v for k, v in answers.items() if k.startswith(ORDER)}
    if orders:
        out.setdefault("choices", {}).update(orders)
    if "choice" not in out:
        order = _entering_order_choice(plan, card, controller, x=x, extra=extra, answers=orders,
                                       choices=answers)  # (wave 3S: the read-ahead number chosen first)
        if order is not None:
            out["choice"] = order
    return out


# -- replacement effects stage 2 (wave 2E) -----------------------------------------------------------
ORDER = "order:"  # an entering answer that is a 616.1 order: "order:<question>" -> the effect applied first


def others_enter_tapped(plan: Plan, card: CardInstance, controller: str) -> bool:
    """614.1d: "Creatures your opponents control enter tapped." — statics of permanents on the
    battlefield, checked against the permanent as it would exist on the battlefield under the
    player it enters under (614.12; it doesn't see itself: "Permanents enter tapped" doesn't make
    its own permanent enter tapped, 614.12 example)."""
    from app.rules.replace import conditional_lines

    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    ch = None
    for src in plan.state.cards.values():
        if src.id == card.id or not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) \
                or plan.manual(src):
            continue
        src_ch = plan.ch(src)
        for i, d in scripts.definitions(src_ch).items():
            if d["kind"] != "static" or d.get("static") != "enters_tapped_others":
                continue
            if i in conditional_lines(src_ch) or "Room" in src_ch.subtypes:
                continue  # (a level's or an unlocked door's ability: not tracked, never applied)
            ch = ch if ch is not None else plan.ch(probe)
            if any(selectors.matches(plan, selectors.from_key(key), probe, ch, src.controller, src.id) for key in d["who"]):
                return True
    return False


def entering_counters(plan: Plan, card: CardInstance, controller: str, ch: Any, *, x: int | None = None,
                      extra: dict[str, int] | None = None, choices: dict[str, str] | None = None) -> dict[str, int]:
    """The counters a permanent enters with (122.6): its "enters with" counters (614.1c; the X its
    spell was cast with, 107.3), a planeswalker's loyalty (306.5b), bloodthirst (702.54) and what
    the effect putting it there adds (persist / undying)."""
    counters: dict[str, int] = {k: n for k, n in (extra or {}).items() if n > 0}
    if "Planeswalker" in ch.types:  # 306.5b: intrinsic, however it enters (even a card taken out of automation)
        # (a printed loyalty of X is the X its spell was cast with, 107.3; 0 when it wasn't cast)
        loyalty = int(ch.loyalty) if ch.loyalty and ch.loyalty.isdigit() else int(x or 0) if ch.loyalty == "X" else 0
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
        for ab in ch.abilities:  # -- keyword pieces (wave 8A) -- 702.43a modular N: "This permanent enters with N +1/+1 counters"
            for kw in ("modular", "graft"):  # (-- keyword mechanics (wave 9D) -- 702.58a graft N: the same)
                if ab.kind == "keywords" and kw in ab.keywords:
                    from app.rules import keyword_triggers

                    for piece in keyword_triggers.pieces(kw, ab.text):
                        counters["+1/+1"] = counters.get("+1/+1", 0) + int(piece.split()[1])
        from app.rules import (
            devour,  # -- keyword mechanics (wave 9D) -- 702.82a: N for each permanent sacrificed as it entered
        )

        if devour.counters(ch, choices):
            counters["+1/+1"] = counters.get("+1/+1", 0) + devour.counters(ch, choices)
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
                n = _counter_amount(plan, card.id, controller, d, x)
                if n > 0:
                    counters[d["counter"]] = counters.get(d["counter"], 0) + n
        # -- counters (wave 7C) -- the kind its controller chose as it enters
        from app.rules import counter_choice

        for kind, n in counter_choice.entering(list(scripts.definitions(ch).values()), choices).items():
            counters[kind] = counters.get(kind, 0) + n
        # -- sagas & attached-object triggers (wave 3S): a Saga's lore counters (714.3a; read ahead 714.3b) --
        from app.rules import sagas

        lore = sagas.entering_lore(ch, choices)
        if lore:
            counters[sagas.LORE] = counters.get(sagas.LORE, 0) + lore
    return counters


def _entering_order_choice(plan: Plan, card: CardInstance, controller: str, *, x: int | None,
                           extra: dict[str, int] | None, answers: dict[str, str],
                           choices: dict[str, str] | None = None) -> dict[str, Any] | None:
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
    return entry_plan(plan, card, entry["player"], pay_life=entry.get("pay_life"), tapped=bool(entry.get("tapped")),
                      answers=entry.get("choices"), x=entry.get("x"), extra=_extra(entry),
                      reserved=set(entry.get("reserved") or ())).get("choice")  # (reserved: wave 5G)


def _extra(entry: Entry) -> dict[str, int] | None:
    """The counters the effect putting it onto the battlefield adds (persist / undying: 702.79a, 702.93a)."""
    # (counter_n: wave 3E, "onto the battlefield with three +1/+1 counters on it")
    return {entry["counter"]: int(entry.get("counter_n") or 1)} if entry.get("counter") else None


def choice_prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    """The prompt and options for one entering choice (a shock land's life, or a named choice)."""
    if "order" in choice:  # -- replacement effects stage 2 (wave 2E): 616.1 before it enters (614.12a) --
        return choice["order"]["prompt"], [DecisionOption(id=cid, label=label) for cid, label in choice["order"]["options"]]
    if "life" in choice:
        n = choice["life"]
        return (f"{card.name}: pay {n} life, or it enters tapped?",
                [DecisionOption(id="pay", label=f"Pay {n} life (untapped)"), DecisionOption(id="tapped", label="Enters tapped")])
    from app.rules.effects import _choice_options

    what = choice["what"]
    from app.rules import battles, reveal_lands

    if reveal_lands.is_choice(what):  # -- "this way" outcomes (wave 4A) -- private: the cards in their hand
        return reveal_lands.prompt(plan, card, controller, what)
    from app.rules import enter_cost

    if enter_cost.is_choice(what):  # -- entering for a cost (wave 5G) -- private: the cards in their hand
        return enter_cost.prompt(plan, card, controller, set(choice.get("reserved") or ()))
    from app.rules import devour  # -- keyword mechanics (wave 9D) --

    if devour.is_choice(what):
        return devour.prompt(plan, card, controller, choice)

    if what == battles.PROTECTOR:  # 310.9a / 310.12a
        return f"{card.name}: as it enters, choose its protector", battles.choice_options(plan, controller, card)
    article = "an" if what[:1] in "aeiou" else "a"
    return (f"{card.name}: as it enters, choose {article} {what}",  # (-- enter as copy (wave 5F) --: the entering card)
            _choice_options(plan, {"controller": controller, "source_card": card.id}, what))


def _answer(entry_or_answers: dict[str, Any], choice: dict[str, Any], chosen: str) -> dict[str, Any]:
    """Record an answer: a shock land's ``pay_life``, or a named choice under ``choices``."""
    if "life" in choice:
        return {**entry_or_answers, "pay_life": chosen == "pay"}
    from app.rules import devour  # -- keyword mechanics (wave 9D) -- devour's picks pile up

    if devour.is_choice(choice["what"]):
        chosen = devour.merge((entry_or_answers.get("choices") or {}).get(choice["what"]), chosen)
    return {**entry_or_answers, "choices": {**(entry_or_answers.get("choices") or {}), choice["what"]: chosen}}


def ask_entry_choice(plan: Plan, entries: list[Entry], index: int, ctx: dict[str, Any] | None, shuffle: str | None) -> None:
    """A permanent put onto the battlefield by an effect asks its controller before it enters
    (614.12a) — before any of the permanents entering with it does (they enter together): in
    private (the card may come from a hidden zone: the prompt names it only to them)."""
    from app.rules.plan import decide

    entry = entries[index]
    card = plan.state.cards[entry["card"]]
    choice = choice_needed(plan, card, entry) or {"life": 0}
    prompt, options = choice_prompt(plan, card, entry["player"], choice)
    if not options:  # (no opponent left to choose, 800.4: the choice is skipped)
        _enter_again(plan, entries, index, _answer(entry, choice, ""), ctx, shuffle)
        return
    decide(plan, player=entry["player"], kind="choose_one", prompt=prompt, options=options,
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
    if choice is None or "what" not in choice:
        return False  # (a shock land's question is never asked on the stack: the wording is printed on lands)
    prompt, options = choice_prompt(plan, card, controller, choice)
    if not options:
        r.entry_choices.setdefault(card.id, {})[choice["what"]] = ""
        return stack_entry_choice(plan, card, controller)
    decide(plan, player=controller, kind="choose_one", prompt=prompt, options=options,
           resume={"step": "stack_enter_choice", "card": card.id, "what": choice["what"]}, source=card)
    return True


def _picked(plan: Plan, d: Any, chosen: str) -> str:
    from app.rules import devour  # -- keyword mechanics (wave 9D) --

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


def move_together(plan: Plan, entries: list[Entry]) -> None:
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
        # (-- transform, wave 11A -- 712.14a: it enters with its back face up, so that face's replacement effects apply)
        planned.append((entry, card, entry_plan(plan, card.model_copy(update={"face": 1}) if entry.get("transformed") else card,
                                                 entry["player"], pay_life=entry.get("pay_life"),
                                                 tapped=bool(entry.get("tapped")), answers=entry.get("choices"),
                                                 x=entry.get("x"), extra=_extra(entry),
                                                 reserved=set(entry.get("reserved") or ()))))  # (reserved: wave 5G)
    # -- entering for a cost (wave 5G) -- the payment first, or it goes to its owner's graveyard instead (614.6)
    from app.rules import enter_cost

    kept = []
    for entry, card, ep in planned:
        if ep.get("pay") and not enter_cost.pay(plan, card, entry["player"], ep["pay"], entry["actor"]):
            ep["divert"] = True
        if ep.get("divert"):
            enter_cost.divert(plan, card.id, entry["actor"])
        else:
            kept.append((entry, card, ep))
    planned = kept
    for entry, _card, ep in planned:  # -- keyword mechanics (wave 9D) -- devour: sacrificed as it enters (702.82a)
        from app.rules import devour

        devour.sacrifice(plan, ep, entry["player"])
    # -- end entering for a cost (wave 5G) --
    if not planned:
        return
    for entry, _card, ep in planned:
        if ep.get("life"):
            plan.do({"type": "life", "player": entry["player"], "delta": -int(ep["life"])}, actor=entry["actor"])
    first = planned[0][0]
    payload: dict[str, Any] = {"type": "move", "card_ids": [c.id for _, c, _ in planned],
                               "to": {"player": first["player"], "zone": "battlefield"}}
    tapped = [c.id for _, c, ep in planned if ep["tapped"]]
    if tapped:
        payload["tapped_ids"] = tapped
    back = [c.id for e, c, _ in planned if e.get("transformed")]
    if back:
        payload["back_ids"] = back
    if any(e["player"] != first["player"] for e, _, _ in planned):
        payload["controllers"] = {c.id: e["player"] for e, c, _ in planned}
    plan.do(payload, actor=first["actor"])
    together = [c.id for _, c, _ in planned]  # (wave 5H: 614.12)
    for entry, card, ep in planned:
        _after_move(plan, entry, card.id, ep, together)


def _after_move(plan: Plan, entry: Entry, card_id: str, ep: dict[str, Any], together: list[str] | None = None) -> None:
    controller = entry["player"]
    after_entry(plan, card_id, controller, x=entry.get("x"), extra_counters=_extra(entry), choices=ep.get("choices"),
                newcomers=together)
    entered = plan.state.cards.get(card_id)
    if entered is None or not entered.zone.endswith(":battlefield"):
        return
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


def _counter_amount(plan: Plan, card_id: str, controller: str, d: dict[str, Any], x: int | None) -> int:
    n = d["n"]
    if n == "X":  # the X its spell was cast with (107.3); 0 when it wasn't cast (put onto the battlefield)
        amount = int(x or 0)
    elif isinstance(n, dict):  # "for each creature card in your graveyard": the values grammar
        amount = values.evaluate(plan, {"controller": controller, "source_card": card_id,  # (wave 4F: converge's record)
                                        "source_object": plan.oid(card_id), "x": x}, n)  # (x: "twice X", wave 4K)
    else:
        amount = int(n)
    # -- review (wave 4R) -- a spell cast by hand has no payment known (engine.absorb_manual_events): X, converge's
    # kicks read 0 (converge's colors: values.evaluate says so) — say so; its controller adds the counters by hand.
    manual = plan.rules.payments.get(plan.oid(card_id))
    if manual is not None and not manual.mana_known and (n == "X" or "'x'" in str(n) or d.get("per_kick")
                                                          or d.get("if_kicked")):
        plan.note(f"{plan.state.cards[card_id].name or 'It'} was cast by hand: what was paid for it isn't known — "
                  "put its counters on by hand", [card_id])
    # -- end review (wave 4R) --
    if d.get("if_kicked") or d.get("per_kick"):  # 702.33e: how its spell was cast (the payment record)
        record = plan.rules.payments.get(plan.oid(card_id))
        kicked = record.kicked if record is not None else 0
        amount = 0 if d.get("if_kicked") and not kicked else amount * kicked if d.get("per_kick") else amount
    if d.get("if_cast") is not None:  # -- refused modal/conditional (wave 3R1) -- adamant: how its spell was paid (601.2h)
        from app.rules import conditions

        ctx = {"controller": controller, "source_card": card_id, "source_object": plan.oid(card_id)}
        amount = amount if conditions.holds(plan, ctx, d["if_cast"]) else 0
    return amount


def after_entry(plan: Plan, card_id: str, controller: str, *, x: int | None = None,
                extra_counters: dict[str, int] | None = None, choices: dict[str, str] | None = None,
                newcomers: list[str] | None = None) -> None:
    """The "enters with" part of entering (122.6: counters put on it as it enters, by its controller;
    306.5b: a planeswalker's loyalty), right after the move that put it onto the battlefield, and the
    record of what was chosen as it entered ("Chosen color: Blue" on the permanent, 614.12a)."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(":battlefield"):
        return
    from app.rules import battles

    battles.entered(plan, card_id, choices)  # 310.9a: the protector chosen as it entered
    # -- "this way" outcomes (wave 4A) -- the card revealed as it entered (701.20a)
    from app.rules import reveal_lands

    reveal_lands.after_entry(plan, controller, choices)
    if choices:
        from app.rules.effects import CHOICE_LABELS

        for what, value in choices.items():
            if not value or what not in CHOICE_LABELS:
                continue
            shown = plan.name(value) if what in ("opponent", "player") and value in plan.state.players else value
            plan.do({"type": "set_choice", "card_id": card_id, "key": CHOICE_LABELS[what], "value": shown}, actor=controller)
            if what in ("opponent", "player") and value in plan.state.players:  # -- chosen player (wave 4J) --
                from app.rules import chosen

                chosen.record(plan, card_id, value)
    # -- replacement effects stage 2 (wave 2E): the counters it enters with, through the counter
    # choke point (122.6, 614.16), in the order its controller chose before it entered (614.12a) --
    from app.rules import (
        devour,  # -- keyword mechanics (wave 9D) -- 702.82b: what it devoured, for "for each creature it devoured"
    )

    if choices and devour.picked(choices.get(devour.WHAT)):
        plan.rules.devoured[plan.oid(card)] = len(devour.picked(choices.get(devour.WHAT)))
    counters = entering_counters(plan, card, controller, plan.ch(card), x=x, extra=extra_counters, choices=choices)
    puts = [(card_id, kind, n) for kind, n in counters.items() if n > 0]
    from app.rules import replace

    # (-- counters (wave 5H) -- with none, other permanents' "enters with an additional …" statics may still add some;
    # ``newcomers``: the permanents entering with it, whose statics don't apply to it, 614.12)
    # -- counters (wave 7C) -- "If ~ was kicked, it enters with two +1/+1 counters on it and with flying" (614.1c, 613.1f)
    if not plan.manual(card):
        from app.rules import layers

        for d in scripts.definitions(plan.ch(card)).values():
            if d["kind"] == "replacement" and d.get("replacement") == "enters_with_counters" and d.get("grant") \
                    and _counter_amount(plan, card.id, controller, d, x) > 0:
                layers.add_effect(plan, affected=[plan.oid(card)], layer="6", source=None, controller=controller,
                                  add_keywords=tuple(d["grant"]), duration="permanent", label=f"Enters with {d['grant'][0]}")
    if puts or replace.entering_kinds(plan, replace.candidates(plan, "counters")):
        orders = {k[len(ORDER):]: v for k, v in (choices or {}).items() if k.startswith(ORDER)}
        replace.put_counters(plan, puts, by=controller, effect=True, entering={card_id: controller}, answers=orders,
                             newcomers=newcomers)


def token_enters_tapped(plan: Plan, controller: str, spec: dict[str, Any]) -> bool:
    """A token about to be created: does its own text say it enters tapped? (Its creator saying
    "create … tapped" is the effect's own business; both count.)"""
    probe = CardInstance(id="token-probe", name=spec["name"], owner=controller, controller=controller,
                         zone=zone_key(controller, "battlefield"), is_token=True,
                         token=TokenDef(name=spec["name"], power=spec.get("power"), toughness=spec.get("toughness"),
                                        colors=list(spec.get("colors") or []), type_line=spec["type_line"], text=spec.get("text") or ""))
    for d in scripts.definitions(chars.of(probe, plan.info)).values():
        if d["kind"] != "replacement":
            continue
        if d["replacement"] == "enters_tapped" and (d.get("unless") is None or not unless_holds(plan, controller, probe, d["unless"])):
            return True
        if d["replacement"] == "enters_with_counters" and d.get("tapped"):
            return True
    return others_enter_tapped(plan, probe, controller)  # -- replacement effects stage 2 (wave 2E): 614.1d --


# -- zone changes (614.1a "instead", 702.84a, 702.35a, 903.9b) ------------------------------------------
def _from_zone(card: CardInstance) -> str:
    return card.zone.rsplit(":", 1)[-1]


def _self_exile_instead(plan: Plan, card: CardInstance) -> bool:
    """"If ~ would die, exile it instead." (from the battlefield) / "If ~ would be put into a
    graveyard from anywhere, exile it instead." — the object's own replacement effect."""
    frm = _from_zone(card)
    return any(d["kind"] == "replacement" and d.get("replacement") == "exile_instead"
               and (d.get("from") == "anywhere" or frm == "battlefield") for d in _definitions(plan, card).values())


def _static_exile_instead(plan: Plan, card: CardInstance) -> CardInstance | None:
    """A permanent on the battlefield whose static ability replaces this card's trip to the
    graveyard ("If a creature an opponent controls would die, exile it instead.", "If a card or
    token would be put into a graveyard from anywhere, exile it instead."): the first that applies."""
    frm = _from_zone(card)
    for src in plan.state.cards.values():
        if not src.zone.endswith(":battlefield") or src.face_down or not plan.in_game(src) or plan.manual(src):
            continue
        for d in scripts.definitions(plan.ch(src)).values():
            if d["kind"] != "static" or d.get("static") != "exile_instead":
                continue
            if d.get("from") == "battlefield" and frm != "battlefield":
                continue
            whose = d.get("graveyard_of", "any")  # "your graveyard" / "an opponent's graveyard"
            if whose == "you" and card.owner != src.controller or whose == "opponent" and card.owner == src.controller:
                continue
            who = d.get("who", "any")
            if who == "card" and card.is_token:
                continue  # "If a card would be put into …": tokens aren't cards (108.2a)
            if who not in ("any", "card"):
                if frm != "battlefield":
                    continue
                if not selectors.matches(plan, selectors.from_key(who), card, plan.ch(card), src.controller, src.id):
                    continue
            return src
    return None


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


def replace_move(plan: Plan, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """Apply the zone-change replacements to a ``move`` (or ``mill``) step before it happens. Cards
    whose move is replaced are moved separately to where the replacement says; the rest move as
    asked. Self-replacement first (614.15), then the object's own and the statics' "exile instead"
    (all of which agree, so there is no 616.1 choice to make), then madness, then 903.9b."""
    kind = payload.get("type")
    if kind == "mill":
        return _replace_mill(plan, payload, actor)
    if kind != "move":
        return payload
    dest = (payload.get("to") or {}).get("zone")
    r = plan.rules
    replaced: list[tuple[str, str, str]] = []  # (card, zone it goes to instead, why)
    madness: list[tuple[str, str]] = []
    for cid in payload.get("card_ids") or []:
        card = plan.state.cards.get(cid)
        if card is None:
            continue
        frm = _from_zone(card)
        oid = plan.oid(card)
        if frm == "battlefield" and dest not in ("exile", "battlefield") and oid in r.exile_if_leaves:
            r.exile_if_leaves = [o for o in r.exile_if_leaves if o != oid]  # used up (614.5)
            replaced.append((cid, "exile", "unearth"))
            continue
        if dest == "graveyard":
            if frm == "hand":
                # 616.1: madness and an "exile instead" static (Rest in Peace) would both replace a
                # discard; the card's owner chooses. Only madness leads anywhere different (the
                # card is exiled either way, and may then be cast), so it is applied first.
                cost = _madness_cost(plan, card)
                if cost is not None:
                    madness.append((cid, cost))
                    continue
            if frm == "stack" and oid in r.exile_if_graveyard:  # -- refused look/cast-free (wave 3R5) -- a spell cast
                r.exile_if_graveyard = [o for o in r.exile_if_graveyard if o != oid]  # "without paying …": "If that spell
                replaced.append((cid, "exile", "its own cast"))  # would be put into your graveyard, exile it instead"
                continue
            if frm == "battlefield" and card.counters.get("finality", 0) > 0:  # -- refused zones/sized (wave 3R4) --
                # 122.1h: "If this permanent would be put into a graveyard from the battlefield, exile it
                # instead" (it agrees with every other "exile instead" here: no 616.1 choice)
                replaced.append((cid, "exile", "finality counter"))
                continue
            if _self_exile_instead(plan, card):
                replaced.append((cid, "exile", card.name or "its own ability"))
                continue
            src = _static_exile_instead(plan, card)
            if src is not None:
                replaced.append((cid, "exile", src.name or "a static ability"))
                continue
            why = _record_exile_instead(plan, card) if frm == "battlefield" else None  # -- replacement effects stage 2 (wave 2E) --
            if why is not None:
                replaced.append((cid, "exile", why))
                continue
        if dest in ("hand", "library"):
            answer = _commander_instead(plan, card, dest)
            if answer:
                replaced.append((cid, "command", "903.9b"))
            elif answer is None:
                r.pending_903_9b[cid] = dest  # asked right after the move (sba → offer_903_9b)
    if not replaced and not madness:
        return payload
    if dest == "graveyard":  # -- this-turn history (wave 4D) -- a discard put elsewhere instead is still a discard (701.9a)
        from app.rules import history

        history.note_discards(plan, [cid for cid in [c for c, _, _ in replaced] + [c for c, _ in madness]
                                     if _from_zone(plan.state.cards[cid]) == "hand"])
    for cid, zone, _why in replaced:
        owner = plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": zone}}, actor=actor)
    for cid, cost in madness:
        _discard_into_exile(plan, cid, cost, actor)
    taken = {cid for cid, _, _ in replaced} | {cid for cid, _ in madness}
    rest = [c for c in payload["card_ids"] if c not in taken]
    if rest:
        return {**payload, "card_ids": rest}
    whys = sorted({why for _, _, why in replaced})
    text = ("Exiled instead" + (f" ({', '.join(whys)})" if whys and whys != ["903.9b"] else "")) if replaced else "Discarded into exile (madness)"
    if replaced and all(zone == "command" for _, zone, _ in replaced):
        text = "Put into the command zone instead (903.9b)"
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
    exiled = [cid for cid in top if _self_exile_instead(plan, plan.state.cards[cid]) or _static_exile_instead(plan, plan.state.cards[cid]) is not None]
    if not exiled:
        return payload
    for cid in top:
        zone = "exile" if cid in exiled else "graveyard"
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": zone}}, actor=actor)
    return {"type": "rules_log", "text": f"{plan.name(pid)} milled {len(top)}: exiled instead", "card_ids": exiled[:20]}


def _madness_cost(plan: Plan, card: CardInstance) -> str | None:
    """702.35a madness: a card discarded from a hand is discarded into exile instead."""
    from app.rules.casting import MADNESS, keyword_cost  # casting → plan → this module

    if plan.manual(card):
        return None
    return keyword_cost(plan.ch(card), "madness", MADNESS)


def _discard_into_exile(plan: Plan, cid: str, cost: str, actor: str | None) -> None:
    """702.35a: "… discard it into exile. When this card is exiled this way, its owner may cast it by
    paying [cost] rather than its mana cost. If that player doesn't, they put this card into their
    graveyard." — the exile, then the reflexive trigger that offers the cast."""
    from app.rules.triggers import _add

    card = plan.state.cards[cid]
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    plan.rules.free_casts.append(cid)
    plan.rules.alt_costs[cid] = cost
    _add(plan, controller=card.owner, source_card=cid, source_object=plan.oid(cid), name=card.name, index=8000,
         definition={"kind": "triggered", "trigger": "madness", "optional": False, "target": None,
                     "effects": [{"do": "madness_offer", "card": cid, "cost": cost}]})


def offer_903_9b(plan: Plan) -> bool:
    """A commander that was just put into its owner's hand or library without a known answer to
    903.9b: ask its owner now (the one place, whatever moved it). Returns True while a question is
    open. The answer is remembered (the 903.9a memory key with the destination as its context), so
    the next such move is replaced outright."""
    from app.rules.plan import decide

    r = plan.rules
    for cid, dest in list(r.pending_903_9b.items()):
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
                           "delayed_move"})


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
    cid = d.resume["card"]
    plan.rules.pending_903_9b.pop(cid, None)
    card = plan.state.cards.get(cid)
    if chosen[0] == "yes" and card is not None and _from_zone(card) == d.resume["dest"]:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "command"}}, actor=card.owner)


# -- damage prevention (615) ------------------------------------------------------------------------
DamageEvent = dict[str, Any]  # {"source_card", "source_oid", "target" (player id or card id), "amount", "combat", "prevented"}


def _static_records(plan: Plan) -> list[dict[str, Any]]:
    out = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        for d in scripts.definitions(plan.ch(c)).values():
            if d["kind"] == "static" and d.get("static") == "prevent":
                out.append({"kind": "prevent", "controller": c.controller, "source": plan.oid(c), "source_card": c.id,
                            "scope": d["scope"]})
    return out


def _records(plan: Plan) -> list[dict[str, Any]]:
    """Prevention effects in force: statics of permanents on the battlefield, then this turn's
    records (a record from another turn has expired: "this turn")."""
    turn = plan.state.turn.number
    r = plan.rules
    if any(rec.get("turn") != turn for rec in r.replacements):
        r.replacements = [rec for rec in r.replacements if rec.get("turn") == turn]
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
    elif e.get("who") == "target":
        oids = [plan.oid(c) for c in _cards(plan, ctx, "target")]
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
                                    "source_card": ctx.get("source_card"), "scope": scope})
    return True
