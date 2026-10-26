"""Exact exile packets, resolution offers and ordinary timed permissions.

The native primitives own movement/replacements, casting, costs and timing. Bindings keep
only actual final exile objects: a departed/reentered card is never silently recovered.
Canonical grammar delegates to native movement, casting and stored permission primitives.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import replace as dc_replace
from typing import Any

from app.game.rules_state import Permission
from app.rules import context, selectors
from app.rules.plan import Plan

BINDING = 'ref:exile_packet40'
_PARSE = {
    "exile the top two cards of your library. if this spell's additional cost was paid, exile the top three cards instead. until the end of your next turn, you may play those cards": 'burning',
    "exile the top two cards of your library. if this spell's freerunning cost was paid, exile the top x cards of your library instead. you may play the exiled cards until the end of your next turn": 'monastery_raid',  # -- freerunning (wave 110I) --
    'exile the top ten cards of your library. you may cast spells with exactly three colors from among them this turn. add {w}{w}{u}{u}{b}{b}{r}{r}{g}{g}. spend this mana only to cast spells with exactly three colors': 'meeting',
    "destroy all artifacts you don't control, then exile the top x cards of your library, where x is the number of artifacts that were put into graveyards from the battlefield this turn. you may put a creature card exiled this way onto the battlefield. it gains haste. return it to your hand at the beginning of the next end step": 'rampage',
    'target opponent exiles cards from the top of their library until they exile a nonland card. until end of turn, you may cast that card without paying its mana cost': 'stolen',
    'exile the top x cards of your library. you may cast an instant or sorcery spell with mana value x or less from among them without paying its mana cost. then put the exiled instant and sorcery cards that weren\'t cast this way into your hand and the rest on the bottom of your library in a random order': 'muse',
    'exile the top eight cards of your library. you may put a land card from among them onto the battlefield. until end of turn, for each nonland card type, you may cast a spell of that type from among the exiled cards without paying its mana cost': 'augury',
}
_DEFINITIONS = {
    '−8: for each player, search that player\'s library for a nonland card and exile it, then that player shuffles. you may cast those cards without paying their mana costs': ('jace_ultimate', '−8: You gain 1 life.'),
    "whenever you attack, spells you cast from exile this turn cost {x} less to cast, where x is the number of players being attacked. exile the top x cards of your library. until end of turn, you may cast spells from among those exiled cards": ('liara', 'Whenever you attack, you gain 1 life.'),
    "when enchanted creature dies, exile cards equal to its power from the top of its owner's library. you may cast spells from among those cards for as long as they remain exiled, and mana of any type can be spent to cast them": ('chest', 'When enchanted creature dies, you gain 1 life.'),
    "at the beginning of your end step, if you gained life this turn, exile cards from the top of your library until you exile a nonland card. you may cast that card without paying its mana cost if the spell's mana value is less than or equal to the amount of life you gained this turn. otherwise, put it into your hand": ('bre', 'At the beginning of your end step, if you gained life this turn, you gain 1 life.'),
    '{2}{r}, {t}: target opponent exiles cards from the top of their library until they exile an instant, sorcery, or creature card. you may cast that card without paying its mana cost. if you cast a creature spell this way, it gains haste and "at the beginning of the end step, sacrifice ~." activate only as a sorcery': ('strago', '{2}{R}, {T}: Target opponent gains 1 life. Activate only as a sorcery.'),
    'when ~ enters, target opponent exiles the top card of their library, a card at random from their graveyard, and a card at random from their hand. you may cast a spell from among cards exiled this way without paying its mana cost': ('crab', 'When ~ enters, target opponent gains 1 life.'),
    "at the beginning of your end step, exile the bottom card of each opponent's library face down. for as long as those cards remain exiled, you may look at them, you may cast permanent spells from among them, and you may spend mana as though it were mana of any color to cast those spells": ('arvinox', 'At the beginning of your end step, you gain 1 life.'),
    "{2}{u}{r}, {t}: exile the top card of your library. until your next turn, you may cast it if it's an instant or sorcery spell": ('nivix', '{2}{U}{R}, {T}: You gain 1 life.'),
    "whenever ~ attacks, exile the top card of each player's library. you may play those cards this turn, and you may spend mana as though it were mana of any color to cast those spells": ('mezzio', 'Whenever ~ attacks, you gain 1 life.'),
    '{u}, {t}, sacrifice ~: shuffle your library, then exile the top x cards, where x is one plus the number of spells cast this turn. until end of turn, you may play lands and cast spells from among cards exiled this way without paying their mana costs': ('magus', '{U}, {T}, Sacrifice this creature: You gain 1 life.'),
    '+1: discard your hand, then exile the top three cards of your library. until end of turn, you may play cards exiled this way': ('chandra_plus', '+1: You gain 1 life.'),
    '−9: search your graveyard and library for any number of red instant and/or sorcery cards, exile them, then shuffle. you may cast them this turn. add six {r}': ('chandra_ultimate', '−9: You gain 1 life.'),
    'at the beginning of your upkeep, each player exiles the top card of their library. until end of turn, you may play the card you own exiled this way and each other card exiled this way with lesser mana value than it without paying their mana costs': ('triad', 'At the beginning of your upkeep, you gain 1 life.'),
}


def normalize(text: str) -> str:
    return ' '.join(text.lower().split()).rstrip('.')


def descriptor(mode: str) -> dict[str, Any]:
    return {'do': 'exile_packet_continuation', 'mode': mode, 'binding': BINDING}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    mode = _PARSE.get(normalize(body))
    if mode is None:
        return None
    target = None
    if mode == 'stolen':
        native = scripts.parse_effects('Target opponent gains 1 life.')
        assert native is not None
        target = native[1]
    return [descriptor(mode)], target, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = normalize(scripts.self_text(ability.text, ch.name))
    if text == 'creatures attacking enchanted player have trample':
        from app.rules import statics

        who = selectors.Selector(types=('Creature',), attacking_player='enchanted_player').key()
        return statics._definition(who, None, [], keywords=['trample'])
    if text == "~ isn't a creature unless you control three or more permanents you don't own":
        from app.rules import statics

        return {**statics._definition('self', None, [{'foreign_permanents_below': 3}]),
                'remove_types': ['Creature'], 'add_subtypes': []}
    if text == "whenever a player casts a spell they don't own, that player creates a treasure token":
        from app.rules import events

        condition = events.parse_condition('a player casts a spell')
        assert condition is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {**condition, 'cast_foreign_owned': True},
                'effects': [descriptor('gonti_cast')], 'optional': False}
    if text.startswith('whenever a creature deals combat damage to '):
        from app.rules import events

        damage_modes = {
            "whenever a creature deals combat damage to one of your opponents, its controller looks at the top card of that opponent's library and exiles it face down. they may play that card for as long as it remains exiled. mana of any type can be spent to cast a spell this way": ('gonti_damage', 'a creature deals combat damage to one of your opponents'),
            "whenever a creature deals combat damage to enchanted player, that player exiles the top card of their library. until end of turn, that creature's controller may play that card and they may spend mana as though it were mana of any color to cast that spell": ('curse_damage', 'a creature deals combat damage to enchanted player'),
        }
        if text in damage_modes:
            damage_mode, trigger_text = damage_modes[text]
            condition = events.parse_condition(trigger_text)
            assert condition is not None
            return {'kind': 'triggered', 'trigger': 'event', 'cond': condition,
                    'effects': [descriptor(damage_mode)], 'optional': False}
    found = _DEFINITIONS.get(text)
    if found is None:
        return None
    mode, template = found
    native = scripts.define(dc_replace(ability, text=template), ch)
    return {**native, 'effects': [descriptor(mode)]} if native is not None else None


def bind(e: dict[str, Any], suffix: str = '') -> str:
    return e['binding'].removeprefix('ref:') + suffix


def ref(e: dict[str, Any], suffix: str = '') -> str:
    return 'ref:' + bind(e, suffix)


def insert(ctx: dict[str, Any], effects: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']] = effects
    return True


def step(e: dict[str, Any], stage: str, **fields: Any) -> dict[str, Any]:
    return {'do': 'exile_packet_stage', 'binding': e['binding'], 'mode': e['mode'], 'stage': stage, **fields}


def selector(phrase: str, **fields: Any) -> str:
    parsed = selectors.parse(phrase)
    assert parsed is not None, phrase
    return selectors.replace(parsed, **fields).key()


def remaining(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], suffix: str = '_packet') -> list[str]:
    return [cid for cid in context.objects(plan, ctx, bind(e, suffix)) if plan.state.cards[cid].zone.endswith(':exile')]


def grant(e: dict[str, Any], suffix: str = '_packet', **fields: Any) -> dict[str, Any]:
    return {'do': 'grant_play', 'who': ref(e, suffix), 'from_exile': True, 'play': False, 'cast': True,
            'until': 'end_of_turn', **fields}


def offer(e: dict[str, Any], suffix: str = '_packet', **fields: Any) -> dict[str, Any]:
    return {'do': 'free_cast', 'zone': 'that', 'who': ref(e, suffix), 'exact_refs': True, 'optional': True,
            'did': bind(e, '_cast'), **fields}


def top_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owners: list[str], n: int = 1,
               *, bottom: bool = False, face_down: bool = False, suffix: str = '_packet') -> list[str]:
    """One simultaneous native move for each player's selected top/bottom objects."""
    from app.rules import effects

    chosen: list[str] = []
    for owner in owners:
        cards = plan.state.zones.get(owner + ':library', [])
        count = max(0, n)
        chosen += list(cards[-count:] if bottom and count else cards[:count])
    effects.exile_cards(plan, ctx, {'as': bind(e, suffix), 'face_down': face_down, 'blind': face_down}, chosen)
    actual = remaining(plan, ctx, e, suffix)
    context.bind_objects(plan, ctx, bind(e, suffix), actual)
    return actual


def until_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owner: str, key: str) -> list[str]:
    """Reuse the native exact prefix/found-card distinction from the earlier packet family."""
    from app.rules import reveal_cast_packets

    reveal_cast_packets.exile_packet(plan, ctx, e, owner, key)
    packet = remaining(plan, ctx, e, '_shown')
    context.bind_objects(plan, ctx, bind(e, '_packet'), packet)
    return packet


def typed_groups(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Independent one-use permissions for each nonland spell type (Aminatou/Muldrotha semantics)."""
    cards = remaining(plan, ctx, e)
    types = ('Artifact', 'Battle', 'Creature', 'Enchantment', 'Instant', 'Kindred', 'Planeswalker', 'Sorcery')
    for kind in types:
        group = secrets.token_hex(4)
        # Eligibility is checked against the actual spell face at announcement, not the found printing.
        key = selectors.Selector(zones=('stack',), types=(kind,), not_types=('Land',)).key()
        for cid in cards:
            if 'Land' in plan.ch(plan.state.cards[cid]).types:
                continue
            plan.rules.permissions.append(Permission(
                id=secrets.token_hex(4), player=ctx['controller'], card=cid, object_id=plan.oid(cid), zone='any',
                cast=True, play=False, filter=key, free=True, until='end_of_turn', turn=plan.state.turn.number,
                granted_step=plan.rules.step_serial, group=group, left=1, once=True,
                source=ctx.get('source_object'), label=f"{ctx.get('name') or 'The effect'}: {kind} permission"))
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values

    mode = e['mode']
    you = ctx['controller']
    if mode == 'liara':
        n = values.evaluate(plan, ctx, {'players_attacked': 1})
        top_packet(plan, ctx, e, [you], n)
        return insert(ctx, [{'do': 'cost_modifier', 'dir': -1, 'delta': -n,
                             'until': 'end_of_turn', 'from_zones': ['exile']}, grant(e)])
    if mode == 'burning':
        from app.rules import conditions

        paid = conditions.holds(plan, ctx, {'object': 'self', 'cast': {'optional': 'blight'}})
        top_packet(plan, ctx, e, [you], 3 if paid else 2)
        return insert(ctx, [grant(e, play=True, until='end_of_next_turn')])
    if mode == 'monastery_raid':  # 702.173a freerunning cost paid: X cards instead (107.3 X from the cast)
        from app.rules import conditions

        paid = conditions.holds(plan, ctx, {'object': 'self', 'cast': {'alt': 'freerunning'}})
        top_packet(plan, ctx, e, [you], max(0, int(ctx.get('x') or 0)) if paid else 2)
        return insert(ctx, [grant(e, play=True, until='end_of_next_turn')])
    if mode in ('gonti_cast', 'gonti_damage', 'curse_damage'):
        event = ctx.get('event') or {}
        holder = event.get('actor')
        if holder not in plan.live():
            return True
        if mode == 'gonti_cast':
            from app.rules import scripts

            native = scripts.parse_effects('You create a Treasure token.')
            assert native is not None
            return insert(ctx, [{'do': 'as_player', 'player': holder}, *native[0], {'do': 'as_player_end'}])
        damaged = [p for p in event.get('players') or [] if p in plan.live()]
        if not damaged:
            return True
        return insert(ctx, [{'do': 'as_player', 'player': holder},
                            step(e, 'damage_packet', owner=damaged[0]), {'do': 'as_player_end'}])
    if mode == 'meeting':
        top_packet(plan, ctx, e, [you], 10)
        spell_filter = selectors.Selector(zones=('stack',), compare=(('color_count', '==', 3),)).key()
        only = 'q:' + json.dumps({'cast': [{'color_count': 3}], 'ability': None}, sort_keys=True)
        return insert(ctx, [grant(e, filter=spell_filter),
                            {'do': 'add_mana', 'mana': list('WWUUBBRRGG')},
                            {'do': 'restrict_mana', 'only': only, 'note': 'Only spells with exactly three colors.'}])
    if mode == 'rampage':
        return insert(ctx, [{'do': 'destroy', 'who': selector("artifact you don't control")},
                            step(e, 'rampage_count')])
    if mode == 'chest':
        host = context.info(plan, ctx, context.EVENT)
        if host is None:
            return True
        n = max(0, values.evaluate(plan, ctx, {'power': 'event'}))
        top_packet(plan, ctx, e, [host[0].owner], n)
        return insert(ctx, [grant(e, until='permanent', spend='type')])
    if mode == 'bre':
        until_packet(plan, ctx, e, you, selector('nonland card', zones=('library',)))
        ceiling = values.evaluate(plan, ctx, {'turn_history': 'gained'})
        return insert(ctx, [offer(e, '_found', mv=ceiling), step(e, 'bre_rest')])
    if mode == 'strago':
        owners = effects._players(plan, ctx, 'target')
        if not owners:
            return True
        key = selectors.Selector(card=True, zones=('library',), types=('Instant', 'Sorcery', 'Creature')).key()
        until_packet(plan, ctx, e, owners[0], key)
        before = list(ctx.get('free_cast_done') or [])
        return insert(ctx, [offer(e, '_found'), step(e, 'strago_rider', before=before)])
    if mode == 'crab':
        owners = effects._players(plan, ctx, 'target')
        if not owners:
            return True
        owner = owners[0]
        top_packet(plan, ctx, e, [owner], suffix='_library')
        extra: list[dict[str, Any]] = []
        for zone in ('graveyard', 'hand'):
            context.bind_objects(plan, ctx, bind(e, '_' + zone + '_pool'), list(plan.state.zones.get(owner + ':' + zone, [])))
            extra.append({'do': 'return_choice', 'who': ref(e, '_' + zone + '_pool'), 'to': 'exile',
                          'under': 'owner', 'n': 1, 'upto': False, 'random': True, 'label': 'random card',
                          'as': bind(e, '_' + zone)})
        return insert(ctx, [*extra, step(e, 'crab_offer')])
    if mode == 'arvinox':
        packet = top_packet(plan, ctx, e, [p for p in plan.apnap() if p != you], bottom=True, face_down=True)
        if packet:
            plan.do({'type': 'reveal', 'card_ids': packet, 'to': [you]}, actor=you)
        return insert(ctx, [grant(e, until='permanent', spend='color', filter=selector('permanent spell', zones=('stack',)))])
    if mode == 'stolen':
        players = effects._players(plan, ctx, 'target')
        if not players:
            return True
        until_packet(plan, ctx, e, players[0], selector('nonland card', zones=('library',)))
        return insert(ctx, [grant(e, '_found', free=True)])
    if mode == 'nivix':
        top_packet(plan, ctx, e, [you])
        return insert(ctx, [grant(e, until='next_turn', filter=selector('instant or sorcery spell', zones=('stack',)))])
    if mode == 'mezzio':
        top_packet(plan, ctx, e, plan.apnap())
        return insert(ctx, [grant(e, play=True, spend='color')])
    if mode == 'chandra_ultimate':
        from app.rules import qualified_search_packets

        search_key = selectors.Selector(card=True, zones=('library', 'graveyard'), zone_owner='you',
                                        colors=('R',), types=('Instant', 'Sorcery')).key()
        maximum = sum(len(plan.state.zones.get(you + ':' + zone, [])) for zone in ('library', 'graveyard'))
        return insert(ctx, [qualified_search_packets.search(
            to='exile', sel=search_key, zones=['library', 'graveyard'], max=maximum, upto=True,
            outcome=ref(e, '_searched')), step(e, 'chandra_search')])
    if mode == 'jace_ultimate':
        from app.rules import player_control, prohibitions, qualified_search_packets

        # The player may inspect every searchable library before deciding any find.
        # Inspection itself is not a search event; the native searches below own
        # notifications, Agent replacement, choices, movement and each shuffle.
        owners = plan.apnap()
        for owner in owners:
            if prohibitions.cant_search(plan, you, you, owner) is not None:
                continue
            depth = prohibitions.search_depth(plan, you)
            library = list(plan.state.zones.get(owner + ':library', []))[:depth]
            viewer = (player_control.search_controller(plan, you) if owner == you else None) or you
            for at in range(0, len(library), 250):
                plan.do({'type': 'reveal', 'card_ids': library[at:at + 250], 'to': [viewer]}, actor=you)
        searches = [instruction for owner in owners for instruction in (
            qualified_search_packets.search(
                'nonland card', to='exile', library='player:' + owner, shuffle=False,
                outcome=ref(e, '_jace_' + owner)),
            {'do': 'shuffle_library', 'who': 'player:' + owner})]
        return insert(ctx, [*searches, step(e, 'jace_search', owners=owners)])
    if mode == 'chandra_plus':
        return insert(ctx, [{'do': 'discard', 'who': 'you', 'all': True, 'n': 0}, step(e, 'chandra_exile')])
    if mode == 'magus':
        n = 1 + values.evaluate(plan, ctx, {'spells_cast': 'all'})
        return insert(ctx, [{'do': 'shuffle_library', 'who': 'you'}, step(e, 'magus_exile', n=n)])
    if mode == 'triad':
        packet = top_packet(plan, ctx, e, plan.apnap())
        own = [cid for cid in packet if plan.state.cards[cid].owner == you]
        if not own:
            return True
        own_ceiling = plan.ch(plan.state.cards[own[0]]).mana_value
        permitted = [cid for cid in packet if cid in own or plan.ch(plan.state.cards[cid]).mana_value < own_ceiling]
        context.bind_objects(plan, ctx, bind(e, '_allowed'), permitted)
        return insert(ctx, [grant(e, '_allowed', free=True, play=True)])
    if mode == 'muse':
        top_packet(plan, ctx, e, [you], max(0, int(ctx.get('x') or 0)))
        return insert(ctx, [offer(e, filter=selector('instant or sorcery spell', zones=('stack',)), mv=int(ctx.get('x') or 0)),
                            step(e, 'muse_rest')])
    if mode == 'augury':
        packet = top_packet(plan, ctx, e, [you], 8)
        lands = [cid for cid in packet if plan.ch(plan.state.cards[cid]).is_land]
        context.bind_objects(plan, ctx, bind(e, '_lands'), lands)
        return insert(ctx, [{'do': 'return_choice', 'who': ref(e, '_lands'),
                             'to': 'battlefield', 'under': 'you', 'n': 1, 'upto': True,
                             'label': 'land card', 'as': bind(e, '_land')}, step(e, 'augury_groups')])
    raise AssertionError(mode)


def stage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context as bindings
    from app.rules import effects

    stage = e['stage']
    if stage == 'damage_packet':
        owner = e['owner']
        private = e['mode'] == 'gonti_damage'
        if private:
            top = list(plan.state.zones.get(owner + ':library', []))[:1]
            if top:
                plan.do({'type': 'reveal', 'card_ids': top, 'to': [ctx['controller']]}, actor=ctx['controller'])
        packet = top_packet(plan, ctx, e, [owner], face_down=private)
        if private and packet:
            plan.do({'type': 'reveal', 'card_ids': packet, 'to': [ctx['controller']]}, actor=ctx['controller'])
        return insert(ctx, [grant(e, play=True, until='permanent' if private else 'end_of_turn',
                                  spend='type' if private else 'color')])
    if stage == 'rampage_count':
        from app.rules import history

        n = sum(d.to == 'graveyard' and 'Artifact' in history.departed_types(plan, d)
                for d in history.log_for(plan).left)
        packet = top_packet(plan, ctx, e, [ctx['controller']], n)
        candidates = [cid for cid in packet if plan.ch(plan.state.cards[cid]).is_creature]
        context.bind_objects(plan, ctx, bind(e, '_creatures'), candidates)
        return insert(ctx, [{'do': 'return_choice', 'who': ref(e, '_creatures'), 'to': 'battlefield',
                             'under': 'you', 'n': 1, 'upto': True, 'label': 'creature card',
                             'as': bind(e, '_entered')}, step(e, 'rampage_entry')])
    if stage == 'rampage_entry':
        from app.rules import delayed, ordered_tutor_continuations

        entered = ordered_tutor_continuations.current(plan, ctx, ref(e, '_entered'))
        entered = [cid for cid in entered if plan.state.cards[cid].zone.endswith(':battlefield')]
        context.bind_objects(plan, ctx, bind(e, '_entered'), entered)
        for cid in entered:
            delayed.create_move(plan, ctx['controller'], cid, plan.oid(cid), 'hand', ctx.get('name') or 'The effect')
        return effects.grant(plan, ctx, {'who': ref(e, '_entered'), 'keywords': ['haste'], 'duration': 'permanent'})
    if stage == 'bre_rest':
        return insert(ctx, [{'do': 'return_card', 'who': ref(e, '_found'), 'to': 'hand', 'under': 'owner'}])
    if stage == 'strago_rider':
        for cid in ctx.get('free_cast_done') or []:
            card = plan.state.cards.get(cid)
            if cid in e['before'] or card is None or card.zone != 'stack' or not plan.ch(card).is_creature:
                continue
            rider = plan.rules.cast_enters.setdefault(plan.oid(card), {})
            rider['keywords'] = list(dict.fromkeys([*(rider.get('keywords') or []), 'haste']))
            rider['abilities'] = [*(rider.get('abilities') or []), 'At the beginning of the end step, sacrifice this creature.']
        return True
    if stage == 'crab_offer':
        packet = [cid for suffix in ('_library', '_graveyard', '_hand') for cid in remaining(plan, ctx, e, suffix)]
        context.bind_objects(plan, ctx, bind(e, '_packet'), list(dict.fromkeys(packet)))
        return insert(ctx, [offer(e)])
    if stage == 'chandra_search':
        from app.rules import ordered_tutor_continuations

        found = ordered_tutor_continuations.current(plan, ctx, ref(e, '_searched'))
        context.bind_objects(plan, ctx, bind(e, '_packet'),
                             [cid for cid in found if plan.state.cards[cid].zone.endswith(':exile')])
        return insert(ctx, [grant(e), {'do': 'add_mana', 'sym': 'R', 'n': 6}])
    if stage == 'jace_search':
        from app.rules import ordered_tutor_continuations

        found = [cid for owner in e['owners']
                 for cid in ordered_tutor_continuations.current(plan, ctx, ref(e, '_jace_' + owner))]
        context.bind_objects(plan, ctx, bind(e, '_packet'),
                             [cid for cid in found if plan.state.cards[cid].zone.endswith(':exile')])
        return insert(ctx, [offer(e, n=len(found))])
    if stage == 'chandra_exile':
        top_packet(plan, ctx, e, [ctx['controller']], 3)
        return insert(ctx, [grant(e, play=True)])
    if stage == 'magus_exile':
        top_packet(plan, ctx, e, [ctx['controller']], e['n'])
        return insert(ctx, [grant(e, free=True, play=True)])
    if stage == 'augury_groups':
        return typed_groups(plan, ctx, e)
    if stage == 'muse_rest':
        packet = remaining(plan, ctx, e)
        spells = [cid for cid in packet if plan.ch(plan.state.cards[cid]).types & {'Instant', 'Sorcery'}]
        rest = [cid for cid in packet if cid not in spells]
        if spells:
            plan.do({'type': 'move', 'card_ids': spells, 'to': {'player': ctx['controller'], 'zone': 'hand'}}, actor=ctx['controller'])
        if rest:
            effects.bottom_at_random(plan, ctx['controller'], rest, actor=ctx['controller'])
        bindings.bind_objects(plan, ctx, bind(e, '_packet'), [])
        return True
    raise AssertionError(stage)


PRIMITIVES = {'exile_packet_continuation': run, 'exile_packet_stage': stage}


def foreign_permanents_below(plan: Plan, ctx: dict[str, Any], n: int) -> bool:
    """Ownership/control alone can be read in layer4 without deriving other objects.

    Phased-out objects are absent and the source itself counts if foreign-owned.
    This is deliberately not a generic characteristic-dependent count in layer4.
    """
    controller = ctx['controller']
    return sum(c.zone.endswith(':battlefield') and c.controller == controller and c.owner != controller
               for c in plan.state.cards.values()) < n
