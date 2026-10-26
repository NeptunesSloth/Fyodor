"""Cryptic Spires (wave 110G): "As you create your deck, circle two of the colors below. ... {T}: Add one mana of either of the circled colors."

The Scryfall rulings (2024-11-08): the colors are circled as the card goes into the deck, before any game; they must be clear to all players (public); they are part of the
card's copiable characteristics; they only change what the mana ability produces. Modelled like the commander color choices (wave 110E/110F): the owner chooses two colors
right after the mulligans (103.5), before the opening-hand actions (103.6), nothing happening in between. ``RulesState.circled110g[card id]`` keeps them; the card's mana
ability reads "Add {A} or {B}" from then on (layers._derive). A copy of the card gets the colors too: they are copiable values (CopyRecipe.circled110g, stamped by ``stamp`` wherever a recipe is built from a card)."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LINE = "As you create your deck, circle two of the colors below."
MANA = "{T}: Add one mana of either of the circled colors."
NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": "pregame_circle110g", "effects": []} if text.strip() == LINE else None


def mana_ok(text: str) -> bool:
    """coverage: the circled-colors mana ability is carried out by ``apply`` once the colors are chosen."""
    return text.strip() == MANA


def _has_line(ch: Characteristics) -> bool:
    return any(a.text.strip() == LINE for a in ch.abilities)


def pending(plan: Plan, order: list[str]) -> list[str]:
    """The cards (ids) whose owner has still to circle colors, owners in turn order."""
    return [c.id for pid in order for c in plan.state.cards.values()
            if c.owner == pid and c.id not in plan.rules.circled110g and LINE in (plan.ch(c).oracle_text or "") and _has_line(plan.ch(c))]


def ask(plan: Plan, queue: list[str]) -> bool:
    """Ask for the next pair of colors; False when none is left to ask."""
    from app.rules.plan import decide

    if not queue:
        return False
    card = plan.state.cards[queue[0]]
    decide(plan, player=card.owner, kind="choose_cards", prompt=f"{plan.ch(card).name or card.name}: circle two colors as you create your deck",
           options=[DecisionOption(id=k, label=v) for k, v in NAMES.items()], min_choices=2, max_choices=2, source=card,
           resume={"step": "spires110g", "queue": queue})
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import opening_hand

    queue = list(d.resume["queue"])
    if len(set(chosen)) == 2 and set(chosen) <= set(NAMES) and queue[0] in plan.state.cards:
        plan.rules.circled110g[queue[0]] = "".join(c for c in NAMES if c in chosen)
        plan.note(f"{plan.name(plan.state.cards[queue[0]].owner)} circles {' and '.join(NAMES[c] for c in NAMES if c in chosen)} for {plan.state.cards[queue[0]].name}", [queue[0]])
    if not ask(plan, queue[1:]):
        opening_hand.start(plan)  # (the other pregame questions, then the opening-hand actions)


def stamp(rules: Any, recipe: Any, card_id: str) -> Any:
    """A copy recipe of a card carries that card's circled colors (they are copiable values)."""
    colors = rules.circled110g.get(card_id) if rules is not None else None
    return recipe.model_copy(update={"circled110g": colors}) if colors else recipe


def apply(state: GameState, card: Any, ch: Characteristics) -> Characteristics:
    """layers._derive: the mana ability produces one of the two circled colors."""
    rules = state.rules
    from app.game.rules_state import copy_recipe_of

    recipe = copy_recipe_of(rules, rules.object_id(card.id)) if rules is not None else None
    colors = (recipe.circled110g if recipe is not None else rules.circled110g.get(card.id)) if rules is not None else None
    if not colors:
        return ch
    return replace(ch, abilities=tuple(replace(a, text=f"{{T}}: Add {{{colors[0]}}} or {{{colors[1]}}}.") if a.kind == "mana" and a.text.strip() == MANA else a
                                       for a in ch.abilities))
