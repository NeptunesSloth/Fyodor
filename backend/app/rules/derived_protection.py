"""Protection derived from current color sets or an exact referenced object's colors."""
from __future__ import annotations

from typing import Any

from app.rules.characteristics import Characteristics
from app.rules.plan import Plan

OWN = 'Protection from each of its colors'
CONTROLLED = 'Protection from each color among permanents you control'
EVENT = "Protection from each of that spell's colors"
WORDS = {'W': 'white', 'U': 'blue', 'B': 'black', 'R': 'red', 'G': 'green'}


def lines(colors: set[str] | frozenset[str]) -> list[str]:
    return [f'Protection from {word}' for letter, word in WORDS.items() if letter in colors]


def static_lines(plan: Plan, text: str, source: str, recipient: Characteristics) -> list[str]:
    from app.rules import source_qualities

    if (bound := source_qualities.lines(plan, text, source, recipient)) is not None:
        return bound
    if text == OWN:
        return lines(recipient.colors)
    if text != CONTROLLED:
        return [text]
    owner = plan.state.cards.get(source)
    if owner is None:
        return []
    colors = {color for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
              and c.controller == owner.controller and plan.in_game(c) for color in plan.ch(c).colors}
    return lines(colors)


def event_colors(plan: Plan, ctx: dict[str, Any]) -> set[str]:
    from app.rules import context, triggers

    refs = context._object_refs(ctx, context.EVENT)
    if len(refs) != 1:
        return set()
    ref = refs[0]
    card = plan.state.cards.get(ref.card)
    if card is not None and plan.oid(card) == ref.object_id and card.zone == 'stack':
        return set(plan.ch(card).colors)
    snap = plan.rules.lki.get(ref.object_id) or ref.snapshot
    return set(triggers._snapshot_card(plan, snap)[1].colors) if snap is not None else set()


def bind_animation(plan: Plan, ctx: dict[str, Any], abilities: list[str]) -> list[str]:
    return [line for text in abilities for line in (lines(event_colors(plan, ctx)) if text == EVENT else [text])]


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    first = 'Exile target creature an opponent controls with greater power. '
    rider = "Legendary creatures you control gain protection from each of that creature's colors until end of turn."
    if body[:1].upper() + body[1:] != first + rider:
        return None
    from app.rules import selectors

    sel = selectors.parse("creature an opponent controls with power greater than ~'s power")
    receivers = selectors.parse('legendary creatures you control')
    assert sel is not None and receivers is not None
    return ([{'do': 'remember_protection_colors', 'who': 'target'}, {'do': 'exile', 'who': 'target'},
             {'do': 'derived_protection', 'who': receivers.key(), 'colors': 'remembered'}], sel.key(), False)


def remember(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ctx['derived_protection_colors'] = sorted({color for cid in effects._cards(plan, ctx, e['who'])
                                              for color in plan.ch(plan.state.cards[cid]).colors})
    return True


def grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    colors = (set(ctx.get('derived_protection_colors') or []) if e['colors'] == 'remembered'
              else {color for cid in effects._cards(plan, ctx, e['colors']) for color in plan.ch(plan.state.cards[cid]).colors})
    return effects.grant(plan, ctx, {'do': 'grant', 'who': e['who'], 'abilities': lines(colors), 'keywords': []})


PRIMITIVES = {'remember_protection_colors': remember, 'derived_protection': grant}
