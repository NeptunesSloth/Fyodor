"""A selected card's land branch and native cast-now branch, with explicit actors."""
from __future__ import annotations

from typing import Any

CARD = 'land_or_cast_card'
OWNER = 'land_or_cast_owner'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    text = body.strip().lower().rstrip('.').replace('the player', 'that player')
    play: dict[str, Any] = {'do': 'land_or_cast', 'ref': 'ref:' + CARD, 'actor': 'you', 'required': False, 'may_land': False}
    if text == "that player exiles the top card of their library. if it's a land card, that player puts it onto the battlefield. otherwise, that player casts it without paying its mana cost if able":
        return ([{'do': 'exile_top', 'n': 1, 'player': 'event_player', 'as': CARD},
                 {**play, 'actor': 'event_player', 'required': True}], None, False)
    if text == "that player reveals a card at random from their hand. if it's a land card, that player puts it onto the battlefield. otherwise, that player casts it without paying its mana cost if able":
        return ([{'do': 'reveal_random', 'n': 1, 'who': 'event_player', 'as': CARD},
                 {**play, 'actor': 'event_player', 'required': True}], None, False)
    if text in ("shuffle your library, then reveal the top card. if it's a nonland card, you may cast it without paying its mana cost. if it's a land card, you may put it onto the battlefield and return ~ to its owner's hand",
                "shuffle your library, then reveal the top card. if it's a nonland card, you may cast it without paying its mana cost. if it's a land card, you may put it onto the battlefield and return unexpected results to its owner's hand"):
        return ([{'do': 'shuffle_library', 'who': 'you'},
                 {'do': 'look_top', 'n': 1, 'player': 'you', 'reveal': True, 'exact_look': True, 'as': CARD},
                 {**play, 'may_land': True, 'return_source': True, 'cleanup': True}], None, False)
    if text == "the owner of target nonenchantment permanent shuffles it into their library, then exiles the top card of their library. if it's a land card, they put it onto the battlefield. otherwise, they may cast it without paying its mana cost":
        target = language._one(language.ref('target nonenchantment permanent')[2])
        return ([{'do': 'land_cast_owner', 'as': OWNER}, {'do': 'to_library', 'who': 'target', 'place': 'shuffle'},
                 {'do': 'exile_top', 'n': 1, 'player': 'ref:' + OWNER, 'as': CARD},
                 {**play, 'actor': 'ref:' + OWNER}], target, False)
    text = text.replace("that source's controller", 'that player')
    if text == "that player exiles a card from their hand at random. if it's a land card, you may put it onto the battlefield under your control. otherwise, you may cast it without paying its mana cost":
        return ([{'do': 'land_cast_random_exile', 'player': 'event_player', 'as': CARD},
                 {**play, 'may_land': True}], None, False)
    return None


def _splice(ctx: dict[str, Any], body: list[dict[str, Any]]) -> None:
    at = ctx['next']
    ctx['effects'][at:at] = body


def owner(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    cards = effects._cards(plan, ctx, 'target')
    context.bind_players(ctx, e['as'], [plan.state.cards[cards[0]].owner] if cards else [])
    return True


def random_exile(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors

    players = effects._players(plan, ctx, e['player'])
    if not players:
        return True
    sel = selectors.parse('card in your hand')
    assert sel is not None
    _splice(ctx, [{'do': 'as_player', 'player': players[0]},
                  {'do': 'return_choice', 'sel': sel.key(), 'to': 'exile', 'n': 1, 'random': True,
                   'upto': False, 'label': 'card', 'as': e['as']}, {'do': 'as_player_end'}])
    return True


def run(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    cards = context.objects(plan, ctx, e['ref'].removeprefix('ref:'))
    players = effects._players(plan, ctx, e['actor'])
    if len(cards) != 1 or not players:
        return True
    actor = players[0]
    body: list[dict[str, Any]]
    if 'Land' in plan.ch(plan.state.cards[cards[0]]).types:
        put = {'do': 'return_card', 'who': e['ref'], 'to': 'battlefield', 'under': 'you'}
        if e.get('may_land'):
            following = [put, *([{'do': 'bounce', 'who': 'self_stack'}] if e.get('return_source') else [])]
            body = [{'do': 'optional_payment', 'who': 'you', 'cost': '', 'ask': 'put that land onto the battlefield',
                     'bind': 'land_cast_accept'},
                    {'do': 'only_if', 'cond': {'succeeded': 'land_cast_accept'}, 'skip': len(following)}, *following]
        else:
            body = [put]
    else:
        body = [{'do': 'free_cast', 'zone': 'that', 'who': e['ref'], 'n': 1,
                 'exact_refs': True, 'required': bool(e.get('required'))}]
    cleanup = [{'do': 'hide_revealed', 'refs': e['ref'].removeprefix('ref:'), 'zone': 'library'}] if e.get('cleanup') else []
    _splice(ctx, [{'do': 'as_player', 'player': actor}, *body, {'do': 'as_player_end'}, *cleanup])
    return True


PRIMITIVES = {'land_or_cast': run, 'land_cast_owner': owner, 'land_cast_random_exile': random_exile}
