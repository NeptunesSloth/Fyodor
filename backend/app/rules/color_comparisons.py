"""Resolution and continuous conditions comparing current object color sets."""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.rules.plan import Plan

MOST = 'the most common color among all permanents or a color tied for most common'
STRICT = "the chosen color is the most common color among nontoken permanents the chosen player controls but isn't tied for most common"
NOT_STRICT = "the chosen color isn't the most common color among nontoken permanents the chosen player controls or is tied for most common"


def colors(plan: Plan, cid: str) -> frozenset[str]:
    from app.rules import layers

    # Read through layers four/five without recursively evaluating P/T statics
    # whose condition is this same color histogram (613.1d-f).
    layers._T.depth += 1
    try:
        return plan.ch(plan.state.cards[cid]).colors
    finally:
        layers._T.depth -= 1


def histogram(plan: Plan, player: str | None = None, *, nontoken: bool = False) -> Counter[str]:
    counts: Counter[str] = Counter({c: 0 for c in 'WUBRG'})
    for card in plan.state.cards.values():
        if (not card.zone.endswith(':battlefield') or not plan.in_game(card)
                or (player is not None and card.controller != player) or (nontoken and card.is_token)):
            continue
        counts.update(colors(plan, card.id))
    return counts


def comparison(who: str, kind: str = 'most_common') -> dict[str, Any]:
    return {'object': who, 'color_comparison': kind}


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    from app.rules import chosen, effects, protection

    if 'color_rank_choice' in cond:
        card = plan.state.cards.get(ctx.get('source_card') or '')
        if card is None:
            return False
        player = chosen.player_of(plan, card.id, ctx.get('source_object'))
        color = protection.COLORS.get(card.choices.get('Chosen color', '').lower())
        if player is None or color is None:
            return False
        counts = histogram(plan, player, nontoken=True)
        strict = all(counts[color] > counts[other] for other in counts if other != color)
        return strict if cond['color_rank_choice'] else not strict
    who = cond['object']
    if who == 'host':
        source = plan.state.cards.get(ctx.get('source_card') or '')
        host = plan.state.cards.get(source.attached_to or '') if source is not None else None
        ids = [host.id] if host is not None and host.zone.endswith(':battlefield') else []
    else:
        ids = effects._cards(plan, ctx, who)
    own = {color for cid in ids for color in colors(plan, cid)}
    if cond['color_comparison'] == 'most_common':
        counts = histogram(plan)
        return any(counts[color] == max(counts.values()) for color in own)
    available = {color for c in plan.state.cards.values() if c.controller == ctx['controller']
                 and c.zone.endswith(':battlefield') and plan.in_game(c) and 'Creature' in plan.ch(c).types
                 for color in colors(plan, c.id)}
    return bool(own & available)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    if body == f'Destroy target creature if it shares a color with {MOST}. A creature destroyed this way can\'t be regenerated.':
        return ([{'do': 'only_if', 'cond': comparison('target'), 'skip': 1},
                 {'do': 'destroy', 'who': 'target'}, {'do': 'no_regen'}], 'creature', False)
    if body == f"Return target permanent to its owner's hand if that permanent shares a color with {MOST}.":
        return ([{'do': 'only_if', 'cond': comparison('target'), 'skip': 1},
                 {'do': 'bounce', 'who': 'target'}], 'permanent', False)
    if body == 'Counter target spell if it shares a color with a creature you control.':
        return ([{'do': 'only_if', 'cond': comparison('target', 'controlled_creatures'), 'skip': 1},
                 {'do': 'counter', 'who': 'target'}], 'spell', False)
    return None


def static(text: str) -> dict[str, Any] | None:
    from app.rules import selectors, statics

    if text == f'Enchanted creature gets +3/+3 unless it shares a color with {MOST}.':
        return statics._definition('attached', 'creature', [{'not': comparison('host')}], p=3, t=3)
    if text == f'White creatures get +1/+1 as long as {STRICT}.':
        sel = selectors.parse('white creatures')
        assert sel is not None
        return statics._definition(sel.key(), None, [{'color_rank_choice': True}], p=1, t=1)
    return None


def state(text: str) -> dict[str, Any] | None:
    if text == f'When {NOT_STRICT}, sacrifice ~.':
        return {'kind': 'triggered', 'trigger': 'state', 'state': {'color_rank_choice': False},
                'effects': [{'do': 'sacrifice', 'who': 'self'}], 'optional': False, 'target': None}
    return None


def linked_ok(d: dict[str, Any], ch: Any) -> bool:
    import json

    if 'color_rank_choice' not in json.dumps(d):
        return True
    from app.rules import chosen

    return chosen.chooses_player(ch) and chosen._enters_choices(ch).count('color') == 1
