"""-- playtest fixes (nov 5) -- Tapping a permanent for mana from the table (a click, a double-click, the T key).

The table can't tell which mana ability a gesture means: a Forest under Chromatic Lantern has two ({T}: Add {G}, its basic land type's
ability, 305.6; and the Lantern's granted "{T}: Add one mana of any color.", 613.1f), and so does a creature under Cryptolith Rite with a
printed mana ability, or a pain land. The gesture is sent as ``tap_for_mana`` and the engine reads the permanent's mana abilities with {T}
in their cost that can be activated now (605.1a, 605.3a):

* one ability: that one (as before);
* several, outside a payment: the player picks the mana — one option per (ability, mana) pair, an ability whose activation does anything
  more than tap for mana (a pain land's damage, a spending restriction, a sacrifice …) named in its option; identical mana from abilities
  that do nothing else is offered once;
* several while a "tap your mana" prompt is open: when they all do nothing but tap for mana, the one whose mana helps the payment most is
  used (the engine already picks the color of an "any color" ability that way); otherwise (a pain land's damage is the player's call) the
  same question is nested in the payment prompt (``payment_outer``, as app/rules/casting.py nests a mana ability's own choices), which
  comes back once the mana is added.

The question can be cancelled: nothing is tapped.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import CardInstance
from app.rules import mana as M
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan, decide

_VANILLA = M.parse_mana_ability("{T}: Add {C}.")


def _plain(parsed: M.ManaAbility) -> bool:
    """Does activating it do nothing but tap the permanent for mana (no other cost, rider, restriction or condition)?"""
    return _VANILLA is not None and replace(parsed, options=_VANILLA.options, output_producers=_VANILLA.output_producers) == _VANILLA


def _candidates(plan: Plan, card: CardInstance, ch: Characteristics) -> list[tuple[int, M.ManaAbility, str]]:
    from app.rules.casting import mana_abilities

    texts = {ab.index: ab.text for ab in ch.abilities}
    return [(i, parsed, texts.get(i, "")) for i, parsed in mana_abilities(plan.state, card, plan.info) if parsed.tap and not parsed.from_hand]


def _choice(option: tuple[str, ...]) -> str | None:
    """The ``mana_choice`` that selects this option ("C" for {C}{C}), or None for mixed mana."""
    return option[0] if option and len(set(option)) == 1 else None


def _intent(a: A.ActivateAbility, index: int, option: tuple[str, ...] | None) -> A.ActivateAbility:
    return a.model_copy(update={"ability": index, "tap_for_mana": False, "mana_choice": _choice(option) if option is not None else a.mana_choice})


def _count(option: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in option:
        out[m] = out.get(m, 0) + 1
    return out


def resolve(plan: Plan, card: CardInstance, ch: Characteristics, a: A.ActivateAbility, *, paying: bool) -> A.ActivateAbility | None:
    """The activation the gesture stands for, or None when the player was asked which mana."""
    found = _candidates(plan, card, ch)
    if not found:
        return a.model_copy(update={"tap_for_mana": False})  # (the usual refusal follows: tapped, summoning sick, no mana ability …)
    if a.mana_choice is not None:
        for i, parsed, _ in found:
            if any(o and all(sym == a.mana_choice for sym in o) for o in parsed.options):
                return _intent(a, i, None)
        raise ActionError(f"{ch.name} can't add {{{a.mana_choice}}}")
    if len(found) == 1:
        return _intent(a, found[0][0], None)
    if paying and all(_plain(parsed) for _, parsed, _ in found):
        from app.rules.casting import _best_option_index

        pairs = [(i, o) for i, parsed, _ in found for o in parsed.options]
        i, option = pairs[_best_option_index(plan, tuple(o for _, o in pairs))]
        return _intent(a, i, option)
    options: list[DecisionOption] = []
    seen: set[str] = set()
    for i, parsed, text in found:
        if parsed.chooses or parsed.reveal_hand is not None or parsed.count:
            # its mana (or its cost) is chosen as it's activated: one option, the ability's own question follows
            options.append(DecisionOption(id=f"{i}:", label=text))
            continue
        for k, o in enumerate(parsed.options):
            label = M.symbols(_count(o))
            if not _plain(parsed):
                label = f"{label} ({text})"
            elif label in seen:
                continue
            seen.add(label)
            options.append(DecisionOption(id=f"{i}:{k}", label=label))
    if len(options) == 1:
        si, _, sk = options[0].id.partition(":")
        only = next(p for j, p, _ in found if j == int(si))
        return _intent(a, int(si), only.options[int(sk)] if sk else None)
    options.append(DecisionOption(id="cancel", label="Cancel"))
    if paying:  # nested in the payment prompt, which comes back afterwards (app/rules/engine.py: resume_outer)
        plan.rules.payment_outer, plan.rules.decision = plan.rules.decision, None
    decide(plan, player=plan.actor, kind="choose_one", prompt=f"Which mana should {ch.name} add?", options=options,
           resume={"step": "tap_for_mana", "intent": a.model_dump(mode="json"), "paying": paying}, source=card)
    return None


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The mana picked: activate that ability (checked again: the permanent may have changed since the question)."""
    from app.rules.casting import _mana_while_paying, activate_ability, mana_abilities

    if chosen[0] == "cancel":
        return  # (a payment prompt set aside comes back: app/rules/engine.py)
    a = A.parse_action(d.resume["intent"])
    assert isinstance(a, A.ActivateAbility)
    i, _, k = chosen[0].partition(":")
    card = plan.state.cards.get(a.card_id)
    parsed = dict(mana_abilities(plan.state, card, plan.info)).get(int(i)) if card is not None else None
    if parsed is None:
        raise ActionError("That mana ability can't be activated any more")
    option = parsed.options[int(k)] if k and int(k) < len(parsed.options) else None
    intent = _intent(a, int(i), option)  # (mixed mana from a choice of several isn't selectable by color: the ability asks again)
    if d.resume.get("paying"):
        r = plan.rules
        if r.payment_outer is None:
            raise ActionError("That payment is over")
        r.decision, r.payment_outer = r.payment_outer, None  # back in the payment: the mana ability is activated while paying (605.3a)
        _mana_while_paying(plan, intent)
        return
    plan.rules.priority = d.player
    activate_ability(plan, intent)
