"""-- wave 110G -- exact Oracle wordings of single cards, read as a wording the grammar reads or built from parts of it (as wave110b_cards)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def _keep_revealed(d: Def) -> Def:
    """The first choice leaves the rest of the revealed hand revealed for the second (701.20a)."""
    first = next(e for e in d["effects"] if e["do"] == "choose_from_hand")
    first["keep110g"] = True
    return d


def _controlled_since_turn_start(d: Def) -> Def:
    """"Except for creatures the player hasn't controlled continuously since the beginning of the turn": only those controlled since then are destroyed."""
    from app.rules import controller_turn_history69, selectors

    eff = d["effects"][0]
    head, _, key = eff["who"].partition("|sel:")
    sel = selectors.from_key("sel:" + key)
    return {**d, "effects": [{**eff, "who": f"{head}|" + replace(sel, extras=(*sel.extras, controller_turn_history69.EXTRA)).key()}]}


def _twin(d: Def) -> Def:
    """The token is named Twin and copies the attacker's power and toughness once, as it is created (111.1)."""
    token = d["effects"][0]["token"]
    token.update(name="Twin", toughness={"toughness": "self"})
    return d


def _pay_life_reveal(d: Def) -> Def:
    """Pay any amount of life (119.4, 0 up to the life total), then reveal that many cards (701.20a): the payment's amount sizes the reveal."""
    pay = {"do": "optional_payment", "who": "you", "cost": "", "bind": "viz110g", "choose_x": {"max": {"life": "you"}, "life": True}}
    reveal, *rest = d["effects"]
    return {**d, "effects": [pay, {**reveal, "n": {"paid_x": "viz110g"}}, *rest]}


def _walls_only(d: Def) -> Def:
    return {**d, "if": {"w110g": "walls_block"}}


def walls_block(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """509.1g / 509.3b: another Wall blocks the attacker this creature blocks, and every creature blocking it is a Wall."""
    attacker = ((ctx.get("event") or {}).get("other") or {}).get("card")
    blockers = [c for c in plan.state.cards.values() if attacker and c.blocks(attacker)]
    return any(c.id != ctx.get("source_card") for c in blockers) and all("Wall" in plan.ch(c).subtypes for c in blockers)


def holds(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    return bool({"walls_block": walls_block}[cond["w110g"]](plan, ctx, cond))


def _exchange_power(d: Def) -> Def:
    """701.12g: exchanging two powers makes a continuous effect setting each (613.4b) to the other's previous value."""
    return {**d, "effects": [{"do": "exchange_power110g", "duration": "end_of_combat"}]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Portcullis: "two or more other creatures" is three or more with the entering one; the card returns when the artifact leaves (610.3)
    "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield "
    "under its owner's control when this artifact leaves the battlefield.":
        "Whenever a creature enters, if there are three or more creatures on the battlefield, exile it until this artifact leaves the battlefield.",
    # Acquisitions Expert: the opponent reveals that many cards of their choice (701.20a); "those cards" read as "them"
    "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
    "You choose one of those cards. That player discards that card.":
        "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
        "You choose one of them. That player discards that card.",
}

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Serene Master
    "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.":
        ("Whenever this creature blocks, target creature it's blocking has base power 3 until end of combat.", _exchange_power),
    # Total War: attack declaration (508.1); "didn't attack" is read as this turn's declaration
    "Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack, except for creatures "
    "the player hasn't controlled continuously since the beginning of the turn.":
        ("Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack this turn.",
         _controlled_since_turn_start),
    # Gemini Engine: "X/X where X is its power", toughness patched
    "Whenever this creature attacks, create a colorless Construct artifact creature token named Twin that's attacking. Its power is equal to this creature's power "
    "and its toughness is equal to this creature's toughness. Sacrifice the token at end of combat.":
        ("Whenever this creature attacks, create an X/X colorless Construct artifact creature token that's attacking, where X is this creature's power. "
         "Sacrifice it at end of combat.", _twin),
    # Vizkopa Confessor
    "When this creature enters, pay any amount of life. Target opponent reveals that many cards from their hand. You choose one of them and exile it.":
        ("When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures you control. "
         "You choose one of them. Exile that card.", _pay_life_reveal),
    # Wall of Caltrops
    "Whenever this creature blocks a creature, if at least one other Wall creature is blocking that creature and no non-Wall creatures are blocking that creature, "
    "this creature gains banding until end of turn.":
        ("Whenever this creature blocks a creature, this creature gains banding until end of turn.", _walls_only),
    # Distended Mindbender: two sequential choices from the revealed hand (701.9)
    "When you cast this spell, target opponent reveals their hand. You choose from it a nonland card with mana value 3 or less and a card with mana value 4 or greater. "
    "That player discards those cards.":
        ("When you cast this spell, target opponent reveals their hand. You choose a nonland card with mana value 3 or less from it. That player discards that card. "
         "You choose a card with mana value 4 or greater from it. That player discards that card.", _keep_revealed),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (same := _AS.get(ability.text.strip())) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def exchange_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Both powers are read before either is set (701.12g)."""
    from app.rules import effects, values

    mine, theirs = (values.evaluate(plan, ctx, {"power": who}) for who in ("self", "target"))
    base = {"do": "become", "types": [], "duration": e["duration"]}
    effects.become(plan, ctx, {**base, "who": "self", "p": theirs})
    return effects.become(plan, ctx, {**base, "who": "target", "p": mine})


PRIMITIVES: dict[str, Any] = {"exchange_power110g": exchange_power}
