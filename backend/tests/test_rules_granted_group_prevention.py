"""CR 611.2c, 615: prevention for the group that gained abilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/granted_group_prevention_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Mutational Advantage'


def setup(cards, *, proliferate=()):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Wall of Stone', 'Fortress Crab', 'Sol Ring', 'Shock', 'Shock', 'Pyroclasm',
                      'Ghostly Flicker', 'Murder', 'Skullcrack'], ['Wall of Stone', 'Shock'])
    protected = put(s, 'Wall of Stone', 'battlefield')
    excluded = put(s, 'Fortress Crab', 'battlefield')
    artifact = put(s, 'Sol Ring', 'battlefield')
    opponent = put(s, 'Wall of Stone', 'battlefield', 'p2')
    for obj in [protected, artifact, opponent]:
        act(s, 'p1', type='set_counter', card_id=obj.id, kind='charge', value=1)
    spell = put(s, NAME, 'hand')
    mana(s, G=1, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    decision = s.state.rules.decision
    assert decision and decision.resume['step'] == 'proliferate'
    roundtrip(s)
    chosen = [card.id for card in [protected, artifact, opponent] if card.name in proliferate]
    act(s, 'p1', type='choose', decision_id=decision.id, option_ids=chosen)
    settle(s)
    return s, protected, excluded, artifact, opponent


def cast(s, name, targets=(), *, player='p1'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    spell = next(c for c in s.state.cards.values() if c.name == name and c.owner == player
                 and c.zone not in ('stack', f'{player}:graveyard', f'{player}:exile'))
    act(s, player, type='move', card_ids=[spell.id], to={'player': player, 'zone': 'hand'})
    mana(s, player, R=3, B=3, U=3)
    wait_priority(s, player)
    kwargs = {'target_counts': [len(targets)]} if len(targets) > 1 else {}
    act(s, player, type='cast_spell', card_id=spell.id, targets=list(targets), **kwargs)
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_exact_group_gains_keywords_and_prevention_before_proliferate(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, protected, excluded, artifact, opponent = setup(cards, proliferate=['Sol Ring', 'Wall of Stone'])
    for obj in [protected, artifact]:
        assert {'hexproof', 'indestructible'} <= chars(s, obj).keywords
        assert s.state.cards[obj.id].counters['charge'] == 2
    assert not {'hexproof', 'indestructible'} & chars(s, excluded).keywords
    assert not {'hexproof', 'indestructible'} & chars(s, opponent).keywords
    assert s.state.cards[opponent.id].counters['charge'] == 2
    cast(s, 'Pyroclasm')
    assert s.state.cards[protected.id].damage == 0
    assert s.state.cards[excluded.id].damage == s.state.cards[opponent.id].damage == 2
    roundtrip(s)


def test_counter_removal_keeps_protection_and_new_counter_does_not_gain_it(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, protected, excluded, _, _ = setup(cards)
    act(s, 'p1', type='set_counter', card_id=protected.id, kind='charge', value=0)
    act(s, 'p1', type='set_counter', card_id=excluded.id, kind='charge', value=1)
    cast(s, 'Shock', [protected.id])
    cast(s, 'Shock', [excluded.id])
    assert s.state.cards[protected.id].damage == 0 and s.state.cards[excluded.id].damage == 2
    assert {'hexproof', 'indestructible'} <= chars(s, protected).keywords
    assert not {'hexproof', 'indestructible'} & chars(s, excluded).keywords
    roundtrip(s)


def test_blinked_new_objects_do_not_keep_old_protection(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, protected, _, artifact, _ = setup(cards)
    old = s.state.rules.object_id(protected.id)
    cast(s, 'Ghostly Flicker', [protected.id, artifact.id])
    assert s.state.rules.object_id(protected.id) != old
    act(s, 'p1', type='set_counter', card_id=protected.id, kind='charge', value=1)
    assert not {'hexproof', 'indestructible'} & chars(s, protected).keywords
    cast(s, 'Shock', [protected.id])
    assert s.state.cards[protected.id].damage == 2
    roundtrip(s)


def test_counter_bearing_permanent_entering_later_is_not_protected(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _, excluded, _, _ = setup(cards)
    act(s, 'p1', type='move', card_ids=[excluded.id], to={'player': 'p1', 'zone': 'hand'})
    fresh = put(s, 'Fortress Crab', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=fresh.id, kind='charge', value=1)
    cast(s, 'Shock', [fresh.id])
    assert s.state.cards[fresh.id].damage == 2
    assert not {'hexproof', 'indestructible'} & chars(s, fresh).keywords
    roundtrip(s)


def test_unpreventable_damage_is_dealt_while_granted_keywords_remain(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, protected, _, _, _ = setup(cards)
    cast(s, 'Skullcrack', ['p3'])
    cast(s, 'Shock', [protected.id])
    assert s.state.cards[protected.id].damage == 2
    assert {'hexproof', 'indestructible'} <= chars(s, protected).keywords
    roundtrip(s)


def test_granted_indestructible_stops_destruction_and_everything_expires_at_end_of_turn(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase
    s, protected, _, _, _ = setup(cards)
    cast(s, 'Murder', [protected.id])
    assert s.state.cards[protected.id].zone == 'p1:battlefield'
    to_phase(s, 'main1', turn=2)
    assert not {'hexproof', 'indestructible'} & chars(s, protected).keywords
    cast(s, 'Shock', [protected.id], player='p2')
    assert s.state.cards[protected.id].damage == 2
    roundtrip(s)


def test_opponents_cannot_target_affected_permanent(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip
    s, protected, _, _, _ = setup(cards)
    with pytest.raises(ActionError, match='legal target|hexproof'):
        cast(s, 'Shock', [protected.id], player='p2')
    assert s.state.cards[protected.id].damage == 0
    roundtrip(s)


def test_empty_permanent_group_still_proliferates_player_and_triggers_aspirant(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import chars
    s = table(cards, [NAME, 'Scheming Aspirant'], [])
    aspirant = put(s, 'Scheming Aspirant', 'battlefield')
    act(s, 'p1', type='resource', player='p1', key='energy', delta=1)
    spell = put(s, NAME, 'hand')
    mana(s, G=1, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'proliferate'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 2
    assert s.state.players['p1'].life == 42 and s.state.players['p2'].life == s.state.players['p3'].life == 38
    assert not {'hexproof', 'indestructible'} & chars(s, aspirant).keywords
    roundtrip(s)


def test_changing_control_keeps_protection_on_the_same_object(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, protected, _, _, opponent = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[protected.id], player='p2')
    cast(s, 'Pyroclasm')
    assert s.state.cards[protected.id].damage == 0 and s.state.cards[opponent.id].damage == 2
    assert {'hexproof', 'indestructible'} <= chars(s, protected).keywords
    roundtrip(s)
