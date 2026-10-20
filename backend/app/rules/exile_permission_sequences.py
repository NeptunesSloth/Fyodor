"""Exact-object exile permissions composed with native choices, costs and casting."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.context import Context
    from app.rules.plan import Plan


def _grant(name: str, until: str = 'end_of_turn', *, play: bool = True, **extra: Any) -> dict[str, Any]:
    return {'do': 'grant_play', 'who': 'ref:' + name, 'play': play, 'cast': True, 'until': until, **extra}


def _top(n: Any = 1, name: str = 'permission_exiled', **extra: Any) -> dict[str, Any]:
    return {'do': 'exile_top', 'player': 'you', 'n': n, 'as': name, **extra}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import conditions, selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    text = text.replace('Exile the top that many cards of your library.', 'Exile that many cards from the top of your library.')
    text = text.replace('cards exiled with ~ without paying', 'cards exiled with this enchantment without paying')
    if text == 'Exile target nonland permanent. For as long as that card remains exiled, its owner may play it. A spell cast by an opponent this way costs {2} more to cast.':
        return ([{'do': 'exile', 'who': 'target', 'as': 'permission_exiled'},
                 _grant('permission_exiled', 'permanent', owner=True, generic_extra_opponents=2)], 'nonland_permanent', False)
    if text == 'Exile target nonland permanent and the top card of your library. For each of those cards, its owner may play it until the end of their next turn.':
        return ([{'do': 'exile', 'who': 'target', 'as': 'permission_target'}, _top(),
                 _grant('permission_target', 'end_of_next_turn', owner=True),
                 _grant('permission_exiled', 'end_of_next_turn', owner=True)], 'nonland_permanent', False)
    if text == "Exile all opponents' graveyards. Choose a nonland card exiled this way. You may cast that card for as long as it remains exiled, and you may spend mana as though it were mana of any color to cast that spell.":
        from app.rules import player_zones

        sel = selectors.Selector(card=True, zones=('exile',), not_types=('Land',))
        return ([{'do': 'exile', 'who': player_zones.key(['graveyard'], 'each_opponent'), 'as': 'permission_exiled'},
                 {'do': 'foreign_choose_exiled', 'who': 'ref:permission_exiled', 'as': 'permission_chosen', 'filter': sel.key()},
                 _grant('permission_chosen', 'permanent', play=False, spend='color')], None, False)
    if text == 'Add {R}{R}{R}. Exile the top three cards of your library. Choose one. You may play that card this turn.':
        return ([{'do': 'add_mana', 'mana': ['R', 'R', 'R']}, _top(3),
                 {'do': 'foreign_choose_exiled', 'who': 'ref:permission_exiled', 'as': 'permission_chosen'},
                 _grant('permission_chosen')], None, False)
    if text == "Look at the top three cards of your library. Exile one face down and put the rest on the bottom of your library in any order. For as long as it remains exiled, you may cast it if it's a creature spell.":
        creature = selectors.Selector(zones=('stack',), types=('Creature',))
        return ([{'do': 'look_top', 'player': 'you', 'n': 3, 'reveal': False},
                 {'do': 'pick_looked', 'n': 1, 'sel': None, 'to': 'exile', 'optional': False,
                  'reveal': False, 'face_down': True, 'as': 'permission_exiled'},
                 {'do': 'look_exiled', 'who': 'ref:permission_exiled'},
                 {'do': 'rest_looked', 'to': 'bottom_any'},
                 _grant('permission_exiled', 'permanent', play=False, filter=creature.key())], None, False)
    if text == 'Exile the top card of your library. You may play that card this turn. You may cast Equipment spells this way without paying their mana costs.':
        equipment = selectors.Selector(zones=('stack',), subtypes=('Equipment',))
        return ([_top(), _grant('permission_exiled'), _grant('permission_exiled', play=False, free=True, filter=equipment.key())], None, False)
    if text == 'Target opponent sacrifices a creature or planeswalker they control with the greatest mana value among creatures and planeswalkers they control.':
        sel = selectors.Selector(types=('Creature', 'Planeswalker'), controller='you',
                                 extras=('greatest_own:mana_value:Creature|Planeswalker',))
        return ([{'do': 'edict', 'who': 'target', 'sel': sel.key(), 'n': 1, 'label': 'creature or planeswalker with greatest mana value'}], 'opponent', False)
    if re.fullmatch(r"Exile the top card of your library\. (?:~|This creature) gets \+X/\+0 until end of turn, where X is that card's mana value\. You may play that card this turn\.", text):
        return ([_top(), {'do': 'permission_freeze_value', 'value': {'mana_value': 'ref:permission_exiled'}, 'as': 'permission_mv'},
                 {'do': 'pump', 'who': 'self', 'p': {'ref_amount': 'permission_mv'}, 't': 0, 'until': 'end_of_turn'},
                 _grant('permission_exiled')], None, False)
    if re.fullmatch(r'You may sacrifice another creature\. If you do, put a \+1/\+1 counter on (?:~|this creature) and exile the top card of your library\. You may play that card this turn\.', text):
        return ([{'do': 'optional_payment', 'who': 'you', 'cost': 'Sacrifice another creature', 'bind': 'permission_paid'},
                 {'do': 'only_if', 'cond': {'succeeded': 'permission_paid'}, 'skip': 3},
                 {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1}, _top(), _grant('permission_exiled')], None, False)
    if text == "Exile the top card of your library. You may get {E}{E}. If you don't, you may play that card this turn.":
        return ([_top(), {'do': 'permission_optional_energy', 'bind': 'permission_accepted', 'n': 2},
                 {'do': 'only_if', 'cond': {'succeeded': 'permission_accepted', 'negate': True}, 'skip': 1},
                 _grant('permission_exiled')], None, False)
    if text == 'You may put an instant or sorcery card from your graveyard on the bottom of your library. If you do, exile the top two cards of your library. You may play those cards this turn.':
        return ([{'do': 'permission_optional_bottom', 'bind': 'permission_paid'},
                 {'do': 'only_if', 'cond': {'succeeded': 'permission_paid'}, 'skip': 2},
                 _top(2), _grant('permission_exiled')], None, False)
    if text == "Exile the top card of target opponent's library. You may play that card for as long as it remains exiled, and mana of any type can be spent to cast it. If you're the monarch, until end of turn, you may cast a spell from among cards exiled with this enchantment without paying its mana cost.":
        return ([{**_top(link=True), 'player': 'target'}, _grant('permission_exiled', 'permanent', spend='type'),
                 {'do': 'only_if', 'cond': conditions.parse("you're the monarch"), 'skip': 2},
                 {'do': 'permission_bind_linked', 'as': 'permission_linked'},
                 _grant('permission_linked', play=False, free=True, limit=1)], 'opponent', False)
    if text == "Exile the top card of target opponent's library and create a Treasure token. Then you may cast the exiled card without paying its mana cost if it's a spell with mana value less than the number of artifacts you control. If you don't cast it this way, you may cast it this turn.":
        from app.rules import scripts

        created = scripts.parse_effects('Create a Treasure token.')
        assert created is not None
        artifacts = selectors.Selector(types=('Artifact',), controller='you')
        return ([{**_top(), 'player': 'target'}, *created[0],
                 {'do': 'permission_freeze_value', 'value': {'count': artifacts.key()}, 'as': 'permission_limit'},
                 {'do': 'free_cast', 'who': 'ref:permission_exiled', 'zone': 'that', 'filter': None,
                  'mv_lt': {'ref_amount': 'permission_limit'}, 'n': 1, 'optional': True, 'did': 'permission_cast'},
                 {'do': 'only_if', 'cond': {'succeeded': 'permission_cast', 'negate': True}, 'skip': 1},
                 _grant('permission_exiled', play=False)], 'opponent', False)
    return None


def trigger(cond: dict[str, Any] | None, body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Only a singular death explicitly qualified by counters supplies this count."""
    from app.rules import selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    text = text.replace('Exile the top that many cards of your library.', 'Exile that many cards from the top of your library.')
    if text != 'Exile that many cards from the top of your library. Until your next end step, you may play those cards.':
        return None
    if cond is None or cond.get('event') != 'die' or cond.get('subject') != 'sel' or cond.get('aggregate') or not cond.get('sel'):
        return None
    sel = selectors.from_key(cond['sel'])
    if 'counter:*' not in sel.extras:
        return None
    return ([_top({'counters': None, 'on': 'event'}), _grant('permission_exiled', 'next_end_step')], None, False)


def freeze_value(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, values

    context.bind_amount(ctx, e['as'], values.evaluate(plan, ctx, e['value']))
    return True


def bind_linked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with

    context.bind_objects(plan, ctx, e['as'], exiled_with.cards(plan, ctx))
    return True


def optional_energy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, prohibitions
    from app.rules.plan import decide

    if prohibitions.cant_get_counters(plan, ctx['controller'], 'energy'):
        context.bind_payment(ctx, e['bind'], False)
        return True
    decide(plan, player=ctx['controller'], kind='confirm', prompt=f"Get {e['n']} energy instead of permission to play the card?",
           options=[DecisionOption(id='yes', label='Get energy'), DecisionOption(id='no', label='Decline energy')],
           resume={'step': 'permission_optional_energy', 'ctx': ctx, 'e': e})
    return False


def resume_energy(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx, e = d.resume['ctx'], d.resume['e']
    accepted = chosen == ['yes']
    context.bind_payment(ctx, e['bind'], accepted)
    if accepted:
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'player_counter', 'who': 'you', 'counter': 'energy', 'n': e['n']}, *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


def optional_bottom(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    options = [c for c in plan.state.zones.get(f"{ctx['controller']}:graveyard", [])
               if plan.ch(plan.state.cards[c]).types & {'Instant', 'Sorcery'}]
    if not options:
        context.bind_payment(ctx, e['bind'], False)
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='You may put an instant or sorcery card on the bottom of your library',
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or 'Card', card_id=c) for c in options],
           min_choices=0, max_choices=1, resume={'step': 'permission_optional_bottom', 'ctx': ctx, 'e': e,
                                              'objects': {c: plan.oid(plan.state.cards[c]) for c in options}})
    return False


def resume_bottom(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx, e = d.resume['ctx'], d.resume['e']
    selected = [c for c in chosen if c in plan.state.cards and plan.oid(plan.state.cards[c]) == d.resume['objects'].get(c)
                and plan.state.cards[c].zone == f"{d.player}:graveyard"]
    context.bind_payment(ctx, e['bind'], bool(selected))
    if selected:
        context.bind_objects(plan, ctx, e['bind'] + '.card', selected)
        at = ctx['next']
        ctx['effects'] = [*ctx['effects'][:at], {'do': 'to_library', 'who': 'ref:' + e['bind'] + '.card', 'place': 'bottom'}, *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'permission_freeze_value': freeze_value, 'permission_bind_linked': bind_linked,
              'permission_optional_energy': optional_energy, 'permission_optional_bottom': optional_bottom}
RESUME = {'permission_optional_energy': resume_energy, 'permission_optional_bottom': resume_bottom}
