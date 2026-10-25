"""-- multi (wave 100N) -- exact Oracle wordings whose parts the grammar already reads, put together here.

Each entry matches one whole ability (or spell body, ``~`` for the card's name) exactly and is built from what scripts.parse_effects reads
for its parts, with existing primitives; any other wording stays unsupported."""
from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"multi100n: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _cond(text: str) -> dict[str, Any]:
    from app.rules import conditions

    got = conditions.parse(text)
    assert got is not None, text
    return got


def _instead(cond: dict[str, Any], base: list[dict[str, Any]], alt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"X. If C, instead Y.": C judged once as the spell resolves (608.2c), then exactly one of X and Y."""
    return [{"do": "only_if", "cond": {"not": cond}, "skip": len(base), "bind": "cond0"}, *base,
            {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": len(alt)}, *alt]


def _blaze() -> Parsed:
    """Searing Blaze: a player or planeswalker and a creature that player (or that planeswalker's controller) controls, both required (its
    2010-03-01 rulings: no such pair, no cast; one target illegal, the other is still dealt damage); one damage event (120.3)."""
    from app.rules import selectors

    effects, groups, optional = _p("~ deals 1 damage to target player or planeswalker and 1 damage to target creature an opponent controls.")
    assert [e["who"] for e in effects] == ["target:0", "target:1"] and len(groups) == 2
    groups[1] = {**groups[1], "what": selectors.Selector(controller=selectors.THAT_PLAYER, types=("Creature",)).key(), "of": 0}  # (player_relative)
    return effects, groups, optional


def _searing_blaze() -> Parsed:
    """… landfall judged as it resolves, 3 to each instead (its 2024-11-08 rulings)."""
    effects, groups, optional = _blaze()
    landfall = _cond("you had a land enter the battlefield under your control this turn")
    return _instead(landfall, effects, [{**e, "n": 3} for e in effects]), groups, optional


def _concussive_bolt() -> Parsed:
    """Concussive Bolt: metalcraft checked once as it resolves; the creatures that player (or that planeswalker's controller, as it last existed:
    608.2h) controls can't block this turn, the set not locked in (its 2011-06-01 rulings, 611.2c)."""
    effects, target, optional = _p("~ deals 4 damage to target player or planeswalker. If you control three or more artifacts, creatures that player "
                                   "controls can't block this turn.")
    restrict = effects[-1]
    assert restrict["do"] == "restrict" and restrict["who"].startswith("controlled:event_player|")
    restrict["who"] = "controlled:target_player_or_controller|" + restrict["who"].partition("|")[2]
    return effects, target, optional


def _to_the_slaughter() -> Parsed:
    """To the Slaughter: delirium judged as it resolves; instead one creature and one planeswalker of their choice, a permanent that is both
    chosen once only (its 2016-04-08 rulings; edict_kinds100c, 701.21a)."""
    from app.rules import selectors

    base, target, optional = _p("Target player sacrifices a creature or planeswalker of their choice.")
    kinds = [selectors.Selector(types=("Creature",)).key(), selectors.Selector(types=("Planeswalker",)).key()]
    alt = {"do": "edict_kinds100c", "who": "target", "sels": kinds, "labels": ["creature", "planeswalker"], "n": 1, "sel": kinds[0],
           "label": "creature", "distinct": True}
    return _instead(_cond("there are four or more card types among cards in your graveyard"), base, [alt]), target, optional


def _thought_distortion() -> Parsed:
    """Thought Distortion: the hand revealed (701.20a), then those cards of its hand and graveyard exiled face up (player_zones; the sentence
    splitter can't take the comma of "noncreature, nonland")."""
    from app.rules import selectors

    effects, target, optional = _p("Target opponent reveals their hand. Exile all cards from that player's hand and graveyard.")
    assert effects[1]["who"].endswith("|")
    effects[1]["who"] += selectors.Selector(card=True, zones=(), not_types=("Land", "Creature")).key()
    return effects, target, optional


def _swallow_whole() -> Parsed:
    """Swallow Whole: the creature tapped for its additional cost, if it is still that object (400.7; a copy reads the original's payment: its
    2020-04-17 rulings), gets the counter after the exile."""
    effects, target, optional = _p("Exile target tapped creature.")
    counter = _p("Put a +1/+1 counter on target creature.")[0]
    assert len(effects) == len(counter) == 1 and counter[0]["do"] == "add_counters"
    return [*effects, {"do": "tapped_cost100n", "as": "tapped100n"}, {**counter[0], "who": "ref:tapped100n"}], target, optional


def _vengeful_rebirth() -> Parsed:
    """Vengeful Rebirth: damage only if a nonland card was returned this way — not when the card target became illegal, nor for a land (its
    2018-12-07 rulings); "that card's mana value" as it is in the hand (608.2h)."""
    from app.rules import selectors

    effects, groups, optional = _p("Return target card from your graveyard to your hand. ~ deals damage equal to that card's mana value to any target.")
    back, hit = effects
    assert back["do"] == "return_card" and hit["n"] == {"mana_value": f"ref:{back['as']}"}
    nonland = {"object": f"ref:{back['as']}", "is": selectors.Selector(card=True, not_types=("Land",), zones=()).key()}
    return [back, {"do": "only_if", "cond": nonland, "skip": 1}, hit], groups, optional


def _mega_flare() -> Parsed:
    """Mega Flare: up to one creature of each opponent (Shellshock's groups), one damage event to all of them (120.3), the greatest power among
    creatures you control as it resolves (its 2025-10-02 ruling) — the kicker's Dragon, created by the line before, too (608.2c)."""
    effects, groups, optional = _p("For each opponent, choose up to one target creature that player controls.")
    amount = _p("~ deals damage equal to the greatest power among creatures you control to target creature.")[0][0]["n"]
    assert effects == [{"do": "choose_targets", "who": "target:0"}] and groups[0].get("opponent_group")
    return [*effects, {"do": "damage", "who": "target:0", "n": amount}], groups, optional


def _gruesome_discovery() -> Parsed:
    """Gruesome Discovery: morbid judged as it resolves (608.2c); instead the hand is revealed (701.20a), you choose two cards, they discard those."""
    base, target, optional = _p("Target player discards two cards.")
    alt = _p("Target player reveals their hand. You choose two cards from it. That player discards those cards.")[0]
    assert [e["do"] for e in alt] == ["reveal_hand", "choose_from_hand", "discard_named"]
    return _instead(_cond("a creature died this turn"), base, alt), target, optional


BUILDERS: dict[str, Callable[[], Parsed]] = {
    # Encircling Fissure: the opponent is fixed as it resolves, their creatures are read as each damage would be dealt (615, not locked: 611.2c)
    "Prevent all combat damage that would be dealt this turn by creatures target opponent controls.":
        lambda: ([{"do": "prevent_target_creatures100n", "scope": {"combat": True, "any_target": True}}], "opponent", False),
    "Simultaneously untap all tapped creatures and tap all untapped creatures.": lambda: ([{"do": "swap_tapped100n"}], None, False),  # (Breaking Wave)
    "Target player discards two cards. If a creature died this turn, instead that player reveals their hand, you choose two cards from it, then that "
    "player discards those cards.": _gruesome_discovery,
    "For each opponent, choose up to one target creature that player controls. ~ deals damage equal to the greatest power among creatures you "
    "control to each of the chosen creatures.": _mega_flare,
    "Return target card from your graveyard to your hand. If you return a nonland card to your hand this way, ~ deals damage equal to that card's "
    "mana value to any target.": _vengeful_rebirth,
    "Target opponent reveals their hand. Exile all noncreature, nonland cards from that player's hand and graveyard.": _thought_distortion,
    "Exile target tapped creature. Put a +1/+1 counter on the creature tapped to pay this spell's additional cost.": _swallow_whole,
    "~ deals 1 damage to target player or planeswalker and 1 damage to target creature that player or that planeswalker's controller controls.": _blaze,
    "~ deals 1 damage to target player or planeswalker and 1 damage to target creature that player or that planeswalker's controller controls. "
    "If you had a land enter the battlefield under your control this turn, ~ deals 3 damage to that player or planeswalker and 3 damage to that "
    "creature instead.": _searing_blaze,
    "~ deals 4 damage to target player or planeswalker. If you control three or more artifacts, creatures controlled by that player or by that "
    "planeswalker's controller can't block this turn.": _concussive_bolt,
    "Target player sacrifices a creature or planeswalker of their choice. If there are four or more card types among cards in your graveyard, "
    "instead that player sacrifices a creature and a planeswalker of their choice.": _to_the_slaughter,
}


def parse(body: str) -> Parsed | None:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None


def tapped_cost(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind what the spell's cost tapped (its payment record, this_way.cost_objects)."""
    from app.rules import context, this_way

    context.refs(ctx)[e["as"]] = {"kind": "objects", **this_way.cost_objects(plan, ctx, this_way.COST, "tapped")}
    return True


def swap_tapped(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Breaking Wave: the creatures tapped and untapped are read once, then both groups change in the one instruction (701.26a; a stunned one
    loses a stun counter instead of untapping, 122.1d)."""
    from app.rules import keyword_actions, selectors

    ids = [c for c in selectors.candidates(plan, selectors.Selector(types=("Creature",)), ctx["controller"], ctx.get("source_card"))
           if plan.state.cards[c].zone.endswith(":battlefield")]
    tapped = [c for c in ids if plan.state.cards[c].tapped]
    untapped = [c for c in ids if not plan.state.cards[c].tapped]
    tapped = keyword_actions.untap_stunned(plan, tapped, ctx["controller"])
    if untapped:
        plan.do({"type": "tap", "card_ids": untapped, "tapped": True}, actor=ctx["controller"])
    if tapped:
        plan.do({"type": "tap", "card_ids": tapped, "tapped": False}, actor=ctx["controller"])
    return True


def prevent_target_creatures(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"… by creatures target opponent controls": replacements.prevent_all with the creatures that player controls (player:<id>)."""
    from app.rules import effects, replacements, selectors

    for pid in effects._players(plan, ctx, "target:0" if ctx.get("groups") else "target"):  # (awaken adds the land's group, 702.113a)
        sel = selectors.Selector(controller=f"player:{pid}", types=("Creature",)).key()
        replacements.prevent_all(plan, ctx, {"do": "prevent_all", "scope": {**e["scope"], "by_objects": sel}})
    return True


PRIMITIVES = {"tapped_cost100n": tapped_cost, "swap_tapped100n": swap_tapped, "prevent_target_creatures100n": prevent_target_creatures}


# "When you cast this spell while …": the condition is part of the trigger event, checked only as the spell is cast (like "attacks while …",
# triggers.py) — not again as the ability resolves (no intervening "if", 603.4). "this spell" is the spell the trigger is about; with one target
# "a new target" is the new targets of 707.10c.
_WHILE = {
    "When you cast this spell while you control your commander, copy this spell. You may choose a new target for the copy.":
        ("you control your commander", "When you cast this spell, copy it. You may choose new targets for the copy."),  # (Ancestral Communion; 903.3)
    "When you cast this spell while you control a creature, you may copy this spell.":
        ("you control a creature", "When you cast this spell, you may copy it."),  # (Social Snub)
}


# "When you lose control of this artifact, …" (Gustha's Scepter, Duplicity): you lose control of it when it leaves the battlefield or another
# player — in Commander an opponent (102.2) — gains control of it (Gustha's Scepter's 2004-10-04 ruling, Duplicity's 2008-04-01 ruling); the
# control change looks back in time (603.10d), so the ability is its old controller's
_LOSE = re.compile(r"When you lose control of this (?P<t>artifact|enchantment), (?P<body>put all cards exiled with this (?P=t) into their owner's graveyard\.)")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if (lose := _LOSE.fullmatch(ability.text)) is not None:
        return scripts.define(replace(ability, text=f"When an opponent gains control of this {lose['t']} from you and when this {lose['t']} leaves the "
                                                    f"battlefield, {lose['body']}"), ch)
    found = _WHILE.get(ability.text)
    if found is None:
        return None
    d = scripts.define(replace(ability, text=found[1]), ch)
    return None if d is None or d.get("trigger") != "cast_self" else {**d, "while": _cond(found[0])}
