"""Quoted loyalty abilities and exact planeswalker hosts for Teferi Talent."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/teferi_talent_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    s = table(cards, ['Jace Beleren', "Teferi's Talent", 'Divination', 'Koth of the Hammer', 'Mountain', 'Displacer Kitten', 'Shock'], ['Disenchant', 'Inspiration', 'Stifle'], ['Shock'])
    walker = put(s, 'Jace Beleren', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=walker.id, sources=[])
    settle(s)
    aura = put(s, "Teferi's Talent", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[walker.id], sources=[])
    settle(s)
    assert s.state.cards[aura.id].attached_to == walker.id
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    return s, walker, aura


def ultimate(s, walker):
    from tests.test_rules_wave7b_activation import ability_index
    return ability_index(s, walker, 'You get an emblem')


def emblems(s):
    return [c for c in s.state.cards.values() if c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem']


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Teferi's Talent")).level == 'FULL'


def test_each_draw_puts_a_loyalty_counter_on_exact_enchanted_planeswalker(cards):
    s, walker, _ = setup(cards)
    other = put(s, 'Koth of the Hammer', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=other.id, kind='loyalty', value=3)
    spell = put(s, 'Divination', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 5
    assert s.state.cards[other.id].counters['loyalty'] == 3
    roundtrip(s)


def test_granted_ultimate_pays_native_loyalty_and_emblem_outlives_both_sources(cards):
    s, walker, aura = setup(cards)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=12)
    index = ultimate(s, walker)
    assert index >= 100
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    assert s.state.cards[walker.id].zone == 'p1:graveyard'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert s.state.rules.stack and not emblems(s)
    roundtrip(s)
    settle(s)
    assert len(emblems(s)) == 1
    assert "any player's turn" in emblems(s)[0].token.text
    roundtrip(s)


def test_granted_ultimate_still_requires_twelve_loyalty(cards):
    from app.game.errors import ActionError
    s, walker, _ = setup(cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='loyalty'):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ultimate(s, walker))
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_printed_loyalty_and_granted_loyalty_share_once_per_turn_limit(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=12)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Target player draws'), targets=['p1'])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 12  # minus one, then Talent's draw counter
    with pytest.raises(ActionError, match='already used'):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ultimate(s, walker))
    roundtrip(s)


def test_removing_aura_removes_the_granted_loyalty_ability(cards):
    s, walker, aura = setup(cards)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    with pytest.raises(StopIteration):
        ultimate(s, walker)
    roundtrip(s)


def test_aura_destroyed_in_response_does_not_stop_activated_ultimate(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, aura = setup(cards)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=13)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ultimate(s, walker))
    spell = put(s, 'Disenchant', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1, 'C': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[aura.id], sources=[])
    roundtrip(s)
    settle(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    assert len(emblems(s)) == 1
    roundtrip(s)


def test_granted_ultimate_can_be_countered_and_cost_stays_paid(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, aura = setup(cards)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=13)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ultimate(s, walker))
    ability = next(iter(s.state.rules.stack))
    spell = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[ability], sources=[])
    settle(s)
    assert not emblems(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    assert s.state.cards[aura.id].attached_to == walker.id
    roundtrip(s)


@pytest.mark.parametrize('aura_controller', ['p1', 'p2'])
@pytest.mark.parametrize('drawer', ['p1', 'p2'])
def test_draw_trigger_uses_aura_controller_and_can_put_counters_on_opponents_walker(cards, aura_controller, drawer):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, aura = setup(cards)
    if aura_controller != 'p1':
        act(s, 'p1', type='set_controller', card_ids=[aura.id], player=aura_controller)
    spell = put(s, 'Inspiration', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1, 'C': 3})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[drawer], sources=[])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == (5 if drawer == aura_controller else 3)
    roundtrip(s)


def test_talent_emblem_really_enables_another_planeswalker_on_opponents_turn(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=12)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ultimate(s, walker))
    settle(s)
    assert len(emblems(s)) == 1
    other = put(s, 'Koth of the Hammer', 'battlefield')
    mountain = put(s, 'Mountain', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=other.id, kind='loyalty', value=3)
    act(s, 'p1', type='next_turn', player='p2', force=True)
    act(s, 'p2', type='pass_priority')
    wait_priority(s, 'p1')
    assert s.state.turn.active_player == 'p2'
    act(s, 'p1', type='activate_ability', card_id=other.id, ability=ability_index(s, other, 'Untap target Mountain'), targets=[mountain.id])
    assert s.state.cards[other.id].counters['loyalty'] == 4
    settle(s)
    roundtrip(s)


def test_nested_quote_restoration_preserves_possessive_and_native_loyalty(cards):
    from app.rules import granted, scripts
    quote = "[−12]: You get an emblem with 'You may activate loyalty abilities of planeswalkers you control on any player's turn any time you could cast an instant.'"
    normalized = granted.quote(quote)
    assert normalized and "any player's turn" in normalized
    assert normalized.startswith('−12: You get an emblem with "')
    assert scripts.granted_ability(normalized).kind == 'loyalty'
    assert granted.quote(quote[:-1]) is None  # missing the inner closing delimiter
    assert granted.quote('[−12]: Unrecognized impossible instruction.') is None
    assert granted.quote('[−1]: Draw a card.') == '−1: Draw a card.'


@pytest.mark.parametrize('blink_host,change_controller', [(False, False), (False, True), (True, False)])
def test_departed_aura_uses_last_host_object_not_later_incarnation(cards, blink_host, change_controller):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, aura = setup(cards)
    put(s, 'Displacer Kitten', 'battlefield')
    spell = put(s, 'Divination', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    # Decline the Kitten's first blink, then stop as Divination finishes, leaving
    # Talent's draw triggers on the stack for ordinary responses.
    for _ in range(30):
        d = s.state.rules.decision
        if s.state.cards[spell.id].zone == 'p1:graveyard' and d is None:
            break
        if d:
            act(s, d.player, type='choose', decision_id=d.id,
                option_ids=[o.id for o in d.options] if d.kind == 'order' else [])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    destroy = put(s, 'Disenchant', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1, 'C': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=destroy.id, targets=[aura.id], sources=[])
    for _ in range(12):
        if s.state.cards[aura.id].zone == 'p1:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    if change_controller:
        act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    if blink_host:
        old = s.state.rules.object_id(walker.id)
        burn = put(s, 'Shock', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
        wait_priority(s, 'p1')
        act(s, 'p1', type='cast_spell', card_id=burn.id, targets=['p3'], sources=[])
        d = s.state.rules.decision
        assert d
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[walker.id])
        settle(s)
        assert s.state.rules.object_id(walker.id) != old
    else:
        settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == (3 if blink_host else 5)
    roundtrip(s)
