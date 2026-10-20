"""Explicit player-owned zones with a distinct searching/choosing controller."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.context import Context
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == "Search target player's library for up to three cards with flashback and put them into that player's graveyard. Then the player shuffles.":
        sel = selectors.parse('card with flashback in your library')
        if sel is None:
            return None
        return ([{'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(), 'label': 'cards with flashback',
                  'max': 3, 'upto': True, 'to': 'graveyard', 'shuffle': False},
                 {'do': 'shuffle_library', 'who': 'target'}], 'player', False)
    if text == "Search target opponent's library for an instant or sorcery card. You may cast that card without paying its mana cost. Then that player shuffles.":
        sel = selectors.parse('instant or sorcery card in your library')
        assert sel is not None
        return ([{'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(), 'label': 'instant or sorcery card',
                  'max': 1, 'to': 'library', 'shuffle': False, 'as': 'foreign_searched'},
                 {'do': 'free_cast', 'zone': 'that', 'who': 'ref:foreign_searched', 'filter': None, 'n': 1,
                  'optional': True, 'source_zone': 'library', 'source_owner': 'target'},
                 {'do': 'shuffle_library', 'who': 'target'}], 'opponent', False)
    if text == "Search target player's library for up to X cards, where X is the number of Swamps you control, and exile them. Then that player shuffles.":
        swamp = selectors.parse('Swamps you control')
        sel = selectors.parse('card in your library')
        assert swamp is not None and sel is not None
        return ([{'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(), 'label': 'cards',
                  'max': {'count': swamp.key()}, 'upto': True, 'to': 'exile', 'shuffle': False},
                 {'do': 'shuffle_library', 'who': 'target'}], 'player', False)
    if text == "For each artifact or creature card in target opponent's graveyard, add {C} and you gain 1 life.":
        return ([{'do': 'foreign_zone_count', 'kind': 'artifact_or_creature', 'as': 'foreign_count'},
                 {'do': 'add_mana', 'sym': 'C', 'n': {'ref_amount': 'foreign_count'}},
                 {'do': 'gain_life', 'who': 'you', 'n': {'ref_amount': 'foreign_count'}}], 'opponent', False)
    if text == "Draw X cards, where X is the number of cards that were put into target player's graveyard from their library this turn.":
        return ([{'do': 'foreign_zone_count', 'kind': 'library_arrivals', 'as': 'foreign_count'},
                 {'do': 'draw', 'who': 'you', 'n': {'ref_amount': 'foreign_count'}}], 'player', False)
    if text == "If the top card of target player's graveyard is a creature card, put that card on top of that player's library.":
        return ([{'do': 'foreign_graveyard_top'}], 'player', False)
    if text == "Look at target player's hand and choose two cards from it. Put them on top of that player's library in any order.":
        return ([{'do': 'reveal_hand', 'who': 'target', 'private': True},
                 {'do': 'choose_from_hand', 'who': 'you', 'sel': selectors.Selector(card=True, zones=()).key(), 'n': 2, 'label': 'cards', 'as': 'foreign_hand'},
                 {'do': 'to_library', 'who': 'ref:foreign_hand', 'place': 'top'}], 'player', False)
    if text in ("Exile X target cards from target player's graveyard. For each card exiled this way, that player loses 1 life and you gain 1 life.",
                "Put any number of target artifact cards from target player's graveyard on top of their library in any order."):
        from app.game.actions import MAX_TARGETS

        suffer = text.startswith('Exile X')
        sel = selectors.Selector(zones=('graveyard',), zone_owner=selectors.THAT_PLAYER, card=True,
                                 types=() if suffer else ('Artifact',))
        n = 1 if suffer else MAX_TARGETS
        groups: list[dict[str, Any]] = [{'what': 'player', 'min': 1, 'max': 1},
                  {'what': sel.key(), 'of': 0, 'min': n if suffer else 0, 'max': n, **({'x_count': 'exact'} if suffer else {})}]
        effects: list[dict[str, Any]]
        if suffer:
            amount = {'ref_count': 'foreign_exiled', 'this_way': 'exiled', 'of': None}
            effects = [{'do': 'exile', 'who': 'target:1', 'as': 'foreign_exiled'},
                       {'do': 'lose_life', 'who': 'target', 'n': amount},
                       {'do': 'gain_life', 'who': 'you', 'n': amount}]
        else:
            effects = [{'do': 'to_library', 'who': 'target:1', 'place': 'top'}]
        return effects, groups, False
    if text == "Look at target opponent's hand. You may exile a nonland card from it. For as long as that card remains exiled, its owner may play it. A spell cast this way costs {2} more to cast.":
        sel = selectors.Selector(card=True, zones=(), not_types=('Land',))
        return ([{'do': 'reveal_hand', 'who': 'target', 'private': True},
                 {'do': 'choose_from_hand', 'who': 'you', 'sel': sel.key(), 'n': 1, 'optional': True,
                  'label': 'nonland card', 'as': 'foreign_hand'},
                 {'do': 'exile', 'who': 'ref:foreign_hand', 'as': 'foreign_exiled'},
                 {'do': 'grant_play', 'who': 'ref:foreign_exiled', 'owner': True, 'play': True, 'cast': True,
                  'until': 'permanent', 'generic_extra': 2}], 'opponent', False)
    if text == "Search target opponent's library for a card and exile it. Then that player shuffles. Until the beginning of your next upkeep, you may play that card. At the beginning of your next upkeep, if you haven't played it, put it into its owner's graveyard.":
        sel = selectors.parse('card in your library')
        assert sel is not None
        return ([{'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(), 'label': 'card',
                  'max': 1, 'upto': False, 'to': 'exile', 'shuffle': False, 'as': 'foreign_exiled'},
                 {'do': 'shuffle_library', 'who': 'target'},
                 {'do': 'grant_play', 'who': 'ref:foreign_exiled', 'play': True, 'cast': True, 'until': 'next_upkeep'},
                 {'do': 'foreign_return_next_upkeep', 'who': 'ref:foreign_exiled'}], 'opponent', False)
    if text == "Exile all cards from target player's graveyard other than basic land cards. For each card exiled this way, search that player's library for all cards with the same name as that card and exile them. Then that player shuffles.":
        from app.rules import player_zones

        sel = selectors.Selector(card=True, zones=(), extras=('foreign_not_basic_land',))
        return ([{'do': 'exile', 'who': player_zones.key(['graveyard'], 'target', sel.key()), 'as': 'foreign_exiled'},
                 {'do': 'foreign_matching_name_search', 'who': 'ref:foreign_exiled'},
                 {'do': 'shuffle_library', 'who': 'target'}], 'player', False)
    if text == "Exile the top three cards of target opponent's library. Choose one of them. Until the end of your next turn, you may play that card, and you may spend mana as though it were mana of any color to cast it.":
        return ([{'do': 'exile_top', 'n': 3, 'player': 'target', 'as': 'foreign_exiled'},
                 {'do': 'foreign_choose_exiled', 'who': 'ref:foreign_exiled', 'as': 'foreign_chosen'},
                 {'do': 'grant_play', 'who': 'ref:foreign_chosen', 'play': True, 'cast': True,
                  'until': 'end_of_next_turn', 'spend': 'color'}], 'opponent', False)
    return None


def count(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects, history

    players = effects._players(plan, ctx, 'target')
    if e['kind'] == 'library_arrivals':
        n = sum(a.owner in players and a.from_zone == 'library' for a in history.log_for(plan).entered_graveyard)
    else:
        n = sum(bool({'Artifact', 'Creature'} & plan.ch(plan.state.cards[c]).types)
                for p in players for c in plan.state.zones.get(f'{p}:graveyard', []))
    context.bind_amount(ctx, e['as'], n)
    return True


def graveyard_top(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    players = effects._players(plan, ctx, 'target')
    for pid in players:
        yard = plan.state.zones.get(f'{pid}:graveyard', [])
        if yard and 'Creature' in plan.ch(plan.state.cards[yard[-1]]).types:
            context.bind_objects(plan, ctx, 'foreign_top_card', [yard[-1]])
            return effects.to_library(plan, ctx, {'do': 'to_library', 'who': 'ref:foreign_top_card', 'place': 'top'})
    return True


def matching_name_search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import card_names, effects, selectors

    names = sorted({n for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')
                    for n in card_names.names_of(plan.ch(plan.state.cards[cid]))})
    if not names:
        return True
    branches = [selectors.Selector(card=True, zones=('library',), zone_owner='you', extras=('name:' + n,)).key() for n in names]
    sel = selectors.Selector(zones=('library',), card=True, either=tuple(branches))
    return effects.search(plan, ctx, {'do': 'search', 'who': 'you', 'library': 'target', 'sel': sel.key(),
                                     'label': 'cards sharing an exiled card name',
                                     'max': sum(len(plan.state.zones.get(f'{p}:library', [])) for p in effects._players(plan, ctx, 'target')), 'upto': True,
                                     'to': 'exile', 'shuffle': False})


def choose_exiled(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.plan import decide

    ids = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':exile')]
    if e.get('filter'):
        from app.rules import selectors

        sel = selectors.from_key(e['filter'])
        ids = [cid for cid in ids if selectors.matches(plan, sel, plan.state.cards[cid], plan.ch(plan.state.cards[cid]), ctx['controller'], ctx.get('source_card'))]
    if not ids:
        context.bind_objects(plan, ctx, e['as'], [])
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose one of the exiled cards',
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in ids],
           min_choices=1, max_choices=1, resume={'step': 'foreign_choose_exiled', 'ctx': ctx, 'e': e})
    return False


def resume_choose_exiled(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx, e = d.resume['ctx'], d.resume['e']
    context.bind_objects(plan, ctx, e['as'], chosen)
    effects.continue_effects(plan, ctx)


def return_next_upkeep(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    from app.game.rules_state import DelayedTrigger

    plan.rules.delayed.append(DelayedTrigger(id=secrets.token_hex(4), controller=ctx['controller'],
        source_card=ctx.get('source_card'), source_object=ctx.get('source_object'), name=ctx.get('name') or '',
        when={'kind': 'step', 'step': 'upkeep', 'whose': 'you'},
        effects=[{'do': 'return_card', 'who': e['who'], 'to': 'graveyard'}],
        refs=dict(ctx.get('refs') or {}), turn=plan.state.turn.number, step=plan.state.turn.phase,
        created_step=plan.rules.step_serial))
    return True


PRIMITIVES = {'foreign_zone_count': count, 'foreign_graveyard_top': graveyard_top,
              'foreign_matching_name_search': matching_name_search, 'foreign_choose_exiled': choose_exiled,
              'foreign_return_next_upkeep': return_next_upkeep}
RESUME = {'foreign_choose_exiled': resume_choose_exiled}
