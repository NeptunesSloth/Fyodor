"""CR 201.2 name-equivalence instructions bind actual objects before moving them."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.context import Context
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    text = text.replace('Delirium — ', '')
    hand_start = 'Target opponent reveals their hand. You choose '
    brain = hand_start + "a nonland card from it and exile that card. If there are four or more card types among cards in your graveyard, search that player's graveyard, hand, and library for any number of cards with the same name as the exiled card, exile those cards, then that player shuffles."
    reap = hand_start + "up to X nonland cards from it and exile them. For each card exiled this way, search that player's graveyard, hand, and library for any number of cards with the same name as that card and exile them. Then that player shuffles."
    if text in (brain, reap):
        from app.rules import selectors

        selector = selectors.Selector(card=True, zones=(), not_types=('Land',))
        return ([{'do': 'reveal_hand', 'who': 'target'},
                 {'do': 'choose_from_hand', 'who': 'you', 'sel': selector.key(), 'n': {'x': 1} if text == reap else 1,
                  'optional': text == reap, 'label': 'nonland cards', 'as': 'name_hand'},
                 {'do': 'exile', 'who': 'ref:name_hand', 'as': 'name_exiled'},
                 {'do': 'name_equivalence', 'kind': 'hand_search', 'delirium': text == brain, 'who': 'ref:name_exiled'}], 'opponent', False)
    forms: dict[str, tuple[str, Any]] = {
        'Exile target creature. If that creature was a God, its controller reveals their hand and exiles all cards from it with the same name as that creature.': ('god_hand', 'creature'),
        "Exile target creature an opponent controls with mana value 2 or less and all other creatures that player controls with the same name as that creature. Then that player reveals their hand and exiles all cards with that name from their hand and graveyard.": ('legion', 'creature an opponent controls with mana value 2 or less'),
        "Choose target permanent an opponent controls. Search that player's library for a card with the same name and put it onto the battlefield under your control. Then that player shuffles.": ('tutor_permanent', 'permanent an opponent controls'),
        "For each tapped nonland permanent target opponent controls, search that player's library for a card with the same name as that permanent. Put those cards onto the battlefield under your control, then that player shuffles.": ('tutor_tapped', 'opponent'),
        "Return target creature an opponent controls to its owner's hand. That creature's owner can't cast spells with the same name as that creature until your next turn.": ('bounce_ban', 'creature an opponent controls'),
        "Exile target enchantment. If the exiled card is a God card, search its controller's graveyard, hand, and library for any number of cards with the same name as that card and exile them. Then that player shuffles.": ('god_search', 'enchantment'),
        "Destroy each permanent with the same name as another permanent, except for basic lands. They can't be regenerated.": ('destroy_duplicates', None),
        "Destroy all other permanents with that name. They can't be regenerated.": ('destroy_event_matches', None),
        'Counter it if a card with the same name is in a graveyard or a nontoken permanent with the same name is on the battlefield.': ('counter_duplicate', None),
        'Counter that spell if a card with the same name is in a graveyard or a nontoken permanent with the same name is on the battlefield.': ('counter_duplicate', None),
        "Counter target sorcery spell. If there are four or more card types among cards in your graveyard, search the graveyard, hand, and library of that spell's controller for any number of cards with the same name as that spell, exile those cards, then that player shuffles.": ('counter_search', 'sorcery spell'),
        '~ and each other creature with the same name as it get +3/+3 until end of turn.': ('source_pump', None),
        'Destroy target nonland permanent if another permanent with the same name is on the battlefield.': ('conditional_destroy_only', 'nonland permanent'),
        'Destroy target nonland permanent if another permanent with the same name is on the battlefield. Draw a card.': ('conditional_destroy', 'nonland permanent'),
        'Each player returns all cards with the same name as that spell from their graveyard to the battlefield.': ('return_each', None),
        'Exile target nonland card from a graveyard, all other cards from graveyards with the same name as that card, and all permanents with that name.': ('exile_all_zones', 'nonland card in a graveyard'),
    }
    if text in ('You may exile target nonland permanent not named Detention Sphere and all other permanents with the same name as that permanent.', 'You may exile target nonland permanent not named ~ and all other permanents with the same name as that permanent.'):
        from app.rules import selectors

        target = selectors.parse('nonland permanent not named Detention Sphere')
        assert target is not None
        return ([{'do': 'name_equivalence', 'kind': 'sphere', 'as': 'name_matching'}, {'do': 'exile', 'who': 'ref:name_matching', 'link': True}], target.key(), True)
    if text == "Choose a nonland card name. Opponents can't cast spells with the chosen name until your next turn.":
        from app.rules import selectors

        named_selector = selectors.parse('spells with the chosen name')
        assert named_selector is not None
        return ([{'do': 'choose_value', 'who': 'you', 'what': 'nonland card name'},
                 {'do': 'cast_limit', 'who': 'each_opponent', 'until': 'next_turn', 'filter': named_selector.key()}], None, False)
    if text == "Choose target nonland permanent. Until your next turn, it can't attack or block, and its activated abilities can't be activated.":
        from app.rules import selectors

        permanent_selector = selectors.parse('nonland permanent')
        assert permanent_selector is not None
        return ([{'do': 'restrict', 'who': 'target', 'rules': ['cant_attack_or_block', 'cant_activate'],
                  'duration': 'next_turn'}], permanent_selector.key(), False)
    found = forms.get(text)
    if not found:
        return None
    from app.rules import selectors

    target = selectors.parse(found[1]) if found[1] and found[1] != 'opponent' else None
    return ([{'do': 'name_equivalence', 'kind': found[0]}], target.key() if target else found[1] if found[1] == 'opponent' else None, False)


def _insert(ctx: Context, instructions: list[dict[str, Any]]) -> None:
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *instructions, *ctx['effects'][at:]]


def execute(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import card_names, context, effects

    kind = e['kind']
    if kind == 'hand_search':
        from app.rules import conditions

        cond = conditions.parse('there are four or more card types among cards in your graveyard')
        assert cond is not None
        if not e.get('delirium') or conditions.holds(plan, ctx, cond):
            names = sorted({name for c in effects._cards(plan, ctx, e['who'])
                            if plan.state.cards[c].zone.endswith(':exile') for name in card_names.names_of(plan.ch(plan.state.cards[c]))})
            context.bind_players(ctx, 'name_controller', effects._players(plan, ctx, 'target'))
            if names:
                _insert(ctx, [{'do': 'name_search', 'by': 'bound', 'player': 'name_controller', 'names': names, 'all': False}])
            elif not e.get('delirium'):
                _insert(ctx, [{'do': 'shuffle_library', 'who': 'ref:name_controller'}])
        return True
    if kind == 'destroy_duplicates':
        battlefield = [c for c in plan.state.cards.values() if c.zone.endswith(':battlefield')]
        duplicates = [c.id for c in battlefield if not {'Basic'} <= plan.ch(c).supertypes or 'Land' not in plan.ch(c).types
                      if any(c.id != other.id and card_names.share(plan.ch(c), plan.ch(other)) for other in battlefield)]
        context.bind_objects(plan, ctx, 'name_matching', duplicates)
        _insert(ctx, [{'do': 'destroy', 'who': 'ref:name_matching'}, {'do': 'no_regen'}])
        return True
    if kind == 'god_search_after':
        exiled = context.objects(plan, ctx, 'name_exiled')
        cards = [plan.state.cards[c] for c in exiled if plan.state.cards[c].zone.endswith(':exile') and not plan.state.cards[c].token]
        if cards and 'God' in plan.ch(cards[0]).subtypes:
            _insert(ctx, [{'do': 'name_search', 'by': 'bound', 'player': 'name_controller',
                           'names': card_names.names_of(plan.ch(cards[0])), 'all': False}])
        return True
    if kind == 'tutor_tapped':
        from app.rules import qualified_search_packets

        players = effects._players(plan, ctx, 'target')
        if not players:
            return True
        controller = players[0]
        groups = [card_names.reference_names(plan.ch(c)) for c in plan.state.cards.values()
                  if c.controller == controller and c.zone.endswith(':battlefield') and c.tapped and 'Land' not in plan.ch(c).types]
        context.bind_players(ctx, 'name_controller', [controller])
        if not groups:
            _insert(ctx, [{'do': 'shuffle_library', 'who': 'ref:name_controller'}])
        else:
            key = qualified_search_packets.key('card')
            _insert(ctx, [{'do': 'search', 'who': 'you', 'library': 'ref:name_controller', 'sel': key,
                           'parts': [key] * len(groups), 'name_groups': groups, 'qualified_packet': True,
                           'to': 'battlefield', 'under': 'you', 'shuffle': True, 'label': 'card with the same name'}])
        return True
    source_ref = 'self' if kind == 'source_pump' else 'event' if kind in ('return_each', 'destroy_event_matches', 'counter_duplicate') else 'target'
    if source_ref == 'target':
        targets = effects._cards(plan, ctx, 'target')
        context.bind_objects(plan, ctx, 'name_subject', targets)
        subject = context.info(plan, ctx, 'name_subject')
    elif source_ref == 'event':
        subject = context.info(plan, ctx, 'event')
    else:
        subject = context.info(plan, ctx, 'source')
        if subject is None:
            card = plan.state.cards.get(ctx.get('source_card') or '')
            subject = (card, plan.ch(card)) if card is not None and plan.oid(card) == ctx.get('source_object') else None
            if subject is None and (snap := plan.rules.lki.get(ctx.get('source_object') or '')) is not None:
                from app.rules.triggers import _snapshot_card
                subject = _snapshot_card(plan, snap)
    if subject is None:
        return True
    original, characteristics = subject
    matching = [c.id for c in plan.state.cards.values() if card_names.share(characteristics, plan.ch(c))]
    instructions: list[dict[str, Any]] = []
    if kind == 'sphere':
        context.bind_objects(plan, ctx, e['as'], [c for c in matching if plan.state.cards[c].zone.endswith(':battlefield')])
    elif kind == 'destroy_event_matches':
        event_refs = context._object_refs(ctx, 'event')
        old_oid = event_refs[0].object_id if event_refs else None
        found = [c for c in matching if plan.state.cards[c].zone.endswith(':battlefield')
                 and not (c == original.id and plan.oid(c) == old_oid)]
        context.bind_objects(plan, ctx, 'name_matching', found)
        instructions = [{'do': 'destroy', 'who': 'ref:name_matching'}, {'do': 'no_regen'}]
    elif kind == 'counter_duplicate':
        if any(plan.state.cards[c].zone.endswith(':graveyard') or
               (plan.state.cards[c].zone.endswith(':battlefield') and not plan.state.cards[c].token) for c in matching):
            instructions = [{'do': 'counter', 'who': 'event_spell'}]
    elif kind == 'source_pump':
        found = [c for c in matching if plan.state.cards[c].zone.endswith(':battlefield') and 'Creature' in plan.ch(plan.state.cards[c]).types]
        if original.id in plan.state.cards and plan.state.cards[original.id].zone.endswith(':battlefield') and plan.oid(original.id) == ctx.get('source_object'):
            found = list(dict.fromkeys([original.id, *found]))
        context.bind_objects(plan, ctx, 'name_matching', found)
        instructions = [{'do': 'pump', 'who': 'ref:name_matching', 'p': 3, 't': 3}]
    elif kind in ('conditional_destroy', 'conditional_destroy_only'):
        if any(c != original.id and plan.state.cards[c].zone.endswith(':battlefield') for c in matching):
            instructions.append({'do': 'destroy', 'who': 'ref:name_subject'})
        if kind == 'conditional_destroy':
            instructions.append({'do': 'draw', 'who': 'you', 'n': 1})
    elif kind == 'return_each':
        found = [c for c in matching if plan.state.cards[c].zone.endswith(':graveyard')]
        context.bind_objects(plan, ctx, 'name_matching', found)
        instructions = [{'do': 'return_card', 'who': 'ref:name_matching', 'to': 'battlefield', 'under_owner': True}]
    elif kind == 'counter_search':
        from app.rules import conditions

        context.bind_players(ctx, 'name_controller', [original.controller])
        cond = conditions.parse('there are four or more card types among cards in your graveyard')
        assert cond is not None
        instructions = [{'do': 'counter', 'who': 'target'}, {'do': 'only_if', 'cond': cond, 'skip': 1},
                        {'do': 'name_search', 'by': 'bound', 'player': 'name_controller',
                         'names': card_names.names_of(characteristics), 'all': False}]
    elif kind == 'god_search':
        context.bind_players(ctx, 'name_controller', [original.controller])
        instructions = [{'do': 'exile', 'who': 'ref:name_subject', 'as': 'name_exiled'},
                        {'do': 'name_equivalence', 'kind': 'god_search_after'}]
    elif kind == 'tutor_permanent':
        from app.rules import qualified_search_packets

        context.bind_players(ctx, 'name_controller', [original.controller])
        instructions = [{'do': 'search', 'who': 'you', 'library': 'ref:name_controller',
                         'sel': qualified_search_packets.key('card'), 'name_in': card_names.reference_names(characteristics),
                         'max': 1, 'to': 'battlefield', 'under': 'you', 'shuffle': True, 'label': 'card with the same name'}]
    elif kind == 'bounce_ban':
        from app.rules import selectors

        context.bind_players(ctx, 'name_owner', [original.owner])
        instructions = [{'do': 'bounce', 'who': 'ref:name_subject'}]
        for name in card_names.names_of(characteristics):
            selector = selectors.Selector(zones=('stack',), extras=('name:' + name,)).key()
            instructions.append({'do': 'cast_limit', 'who': 'ref:name_owner', 'until': 'next_turn', 'filter': selector})
    elif kind in ('god_hand', 'legion'):
        controller = original.controller
        context.bind_players(ctx, 'name_controller', [controller])
        if kind == 'legion':
            matching_battlefield = [c for c in matching if plan.state.cards[c].controller == controller
                           and plan.state.cards[c].zone.endswith(':battlefield') and 'Creature' in plan.ch(plan.state.cards[c]).types]
            context.bind_objects(plan, ctx, 'name_battlefield', matching_battlefield)
            instructions.append({'do': 'exile', 'who': 'ref:name_battlefield'})
        else:
            instructions.append({'do': 'exile', 'who': 'ref:name_subject'})
        if kind == 'legion' or 'God' in characteristics.subtypes:
            zones = ('hand', 'graveyard') if kind == 'legion' else ('hand',)
            hand = [c for c in matching if plan.state.cards[c].zone in [f'{controller}:{z}' for z in zones]]
            context.bind_objects(plan, ctx, 'name_hidden', hand)
            instructions.extend([{'do': 'reveal_hand', 'who': 'ref:name_controller'}, {'do': 'exile', 'who': 'ref:name_hidden'}])
    elif kind == 'exile_all_zones':
        found = [c for c in matching if plan.state.cards[c].zone.rsplit(':', 1)[-1] in ('graveyard', 'battlefield')]
        context.bind_objects(plan, ctx, 'name_matching', found)
        instructions = [{'do': 'exile', 'who': 'ref:name_matching'}]
    _insert(ctx, instructions)
    return True


PRIMITIVES = {'name_equivalence': execute}


def duplicate_permanents(plan: Plan, controller: str) -> bool:
    from app.rules import card_names

    seen: set[str] = set()
    for card in plan.state.cards.values():
        if card.controller != controller or not card.zone.endswith(':battlefield') or card.token or 'Land' in plan.ch(card).types:
            continue
        names = {n.casefold() for n in card_names.names_of(plan.ch(card))}
        if names & seen:
            return True
        seen.update(names)
    return False


def definition(text: str) -> dict[str, Any] | None:
    if text == "Whenever a permanent other than a basic land enters, destroy all other permanents with that name. They can't be regenerated.":
        from app.rules import events, selectors

        cond = events.parse_condition('a permanent enters')
        assert cond is not None
        sel = selectors.from_key(cond['sel'])
        cond = {**cond, 'sel': selectors.replace(sel, extras=(*sel.extras, 'foreign_not_basic_land')).key()}
        return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'optional': False, 'target': None,
                'effects': [{'do': 'name_equivalence', 'kind': 'destroy_event_matches'}]}
    if text != 'When ~ enters, if you control two or more nonland, nontoken permanents with the same name as one another, create a 4/4 colorless Construct artifact creature token.':
        return None
    cond = {'name_duplicate_permanents': True}
    token = {'do': 'create_token', 'who': 'you', 'n': 1,
             'token': {'name': 'Construct', 'power': '4', 'toughness': '4', 'colors': [],
                       'type_line': 'Token Artifact Creature — Construct', 'text': ''}}
    return {'kind': 'triggered', 'trigger': 'enters_self', 'optional': False, 'target': None,
            'if': cond, 'effects': [{'do': 'only_if', 'cond': cond, 'skip': 1}, token]}
