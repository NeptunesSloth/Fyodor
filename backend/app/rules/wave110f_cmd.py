"""Faceless One, The Prismatic Piper (wave 110F), Clara Oswald (wave 110E, "Impossible Girl — ..."): "If ~ is your commander, choose a color before the
game begins. ~ is the chosen color."

607.2p: the choice is made before the game begins and stays linked as the object changes zones; 604.3 / 113.6a: "is the chosen color" is a
characteristic-defining ability that works in every zone, so the commander is that color in the command zone too (layers._derive); 903.4: that color is part
of its color identity (casting.commander_identity). The choice is asked right after the mulligans (103.5), before the opening-hand actions (103.6);
nothing else happens between the two, so no player can tell the difference (903.4b: the choice is revealed). Stored by card id in
``RulesState.commander_color110f`` (a copy of the card has another id and never gets the color); saves made before the 110E copy was merged here keep Clara's
choice in ``commander_color110e``, read as well. Not read: the same line on a card that is not a commander (it does nothing then, 903.3)."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LINE = "If ~ is your commander, choose a color before the game begins. ~ is the chosen color."
LINES = (LINE, "Impossible Girl — " + LINE)  # Clara Oswald's ability word (207.2c: no rules meaning)
NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    return {"kind": "static", "static": "commander_color110f", "effects": []} if ability.kind == "static" and scripts.self_text(ability.text, ch.name) in LINES else None


def has_line(ch: Characteristics) -> bool:
    return any(a.kind == "static" and a.text.replace(ch.name, "~") in LINES for a in ch.abilities if ch.name)


def chosen(rules: Any) -> dict[str, str]:
    """Card id -> chosen color letter (the 110E field of older saves included)."""
    return {**rules.commander_color110e, **rules.commander_color110f} if rules.commander_color110e else rules.commander_color110f


def pending(plan: Plan) -> list[CardInstance]:
    """The live players' commanders in the command zone with the line and no color yet, in turn order."""
    done = chosen(plan.rules)
    out = []
    for pid in plan.live():
        for c in plan.state.cards.values():
            if c.owner == pid and c.commander_key and c.zone == f"{pid}:command" and c.id not in done and has_line(plan.ch(c)):
                out.append(c)
    return out


def ask(plan: Plan) -> bool:
    """True when a color question is pending (the opening-hand questions wait for it)."""
    from app.rules.plan import decide

    todo = pending(plan)
    if not todo:
        return False
    c = todo[0]
    decide(plan, player=c.owner, kind="choose_one", prompt=f"{c.name} (your commander): choose a color before the game begins",
           options=[DecisionOption(id=k, label=v) for k, v in NAMES.items()], resume={"step": "cmd_color110f", "card": c.id})
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import opening_hand

    if chosen and chosen[0] in NAMES:
        plan.rules.commander_color110f[d.resume["card"]] = chosen[0]
        plan.note(f"{plan.name(plan.state.cards[d.resume['card']].owner)} chooses a color for {plan.state.cards[d.resume['card']].name}")
    opening_hand.start(plan)


def resume_old(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A Clara Oswald question saved before the merge (step "clara110e": a queue of card ids); the rest is asked again from opening_hand.start."""
    from app.rules import opening_hand

    card = d.resume["queue"][0]
    if chosen and chosen[0] in NAMES and card in plan.state.cards:
        plan.rules.commander_color110f[card] = chosen[0]
    opening_hand.start(plan)


def color(state: GameState, card: CardInstance, ch: Characteristics) -> Characteristics:
    """The characteristic-defining color (604.3, 613.3: before the other layer-5 effects)."""
    c = chosen(state.rules).get(card.id) if state.rules is not None else None
    return replace(ch, colors=frozenset({c})) if c and has_line(ch) else ch


def identity(state: GameState, player: str, base: tuple[str, ...]) -> tuple[str, ...]:
    """903.4: the chosen colors of the player's commanders join the identity (WUBRG order)."""
    colors = chosen(state.rules) if state.rules is not None else {}
    mine = {colors.get(c.id) for c in state.cards.values() if c.owner == player and c.commander_key}
    return tuple(k for k in NAMES if k in base or k in mine)
