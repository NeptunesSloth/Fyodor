"""CR 111.3, 205.3i, 305.6: nonbasic land tokens with all five basic land types."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/all_basic_land_token_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Overlord of the Hauntwoods'
BASICS = {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, impending=False, double=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave43d_cast_keywords import alt_key
    s = table(cards, [NAME, 'Tribal Flames', 'Blood Moon', 'Doubling Season'], [])
    if double:
        put(s, 'Doubling Season', 'battlefield')
    source = put(s, NAME, 'hand')
    mana(s, G=5)
    extra = {'alt_cost': alt_key(s, NAME, 'impending')} if impending else {}
    act(s, 'p1', type='cast_spell', card_id=source.id, **extra)
    settle(s)
    return s, source


def lands(s):
    return [c for c in s.state.cards.values() if c.name == 'Everywhere' and c.zone == 'p1:battlefield']


@pytest.mark.parametrize('impending', [False, True])
@pytest.mark.parametrize('double', [False, True])
def test_etb_creates_tapped_colorless_nonbasic_land_with_all_basic_types(cards, impending, double):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, source = setup(cards, impending=impending, double=double)
    made = lands(s)
    assert sum(c.quantity for c in made) == (2 if double else 1)
    for token in made:
        ch = chars(s, token)
        assert token.is_token and token.tapped
        assert ch.types == {'Land'} and ch.subtypes == BASICS and not ch.colors
        assert 'Basic' not in ch.supertypes
    if impending:
        assert 'Creature' not in chars(s, s.state.cards[source.id]).types
        assert s.state.cards[source.id].counters['time'] == (8 if double else 4)
    roundtrip(s)


@pytest.mark.parametrize('symbol', ['W', 'U', 'B', 'R', 'G'])
def test_each_intrinsic_basic_land_mana_ability_is_usable(cards, symbol):
    from tests.game_helpers import act, mana_pool
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, _ = setup(cards)
    to_phase(s, 'main1', turn=4)
    token = lands(s)[0]
    before = mana_pool(s).get(symbol, 0)
    act(s, 'p1', type='activate_ability', card_id=token.id, ability=ability_index(s, token, f'Add {{{symbol}}}'))
    assert mana_pool(s).get(symbol, 0) == before + 1
    assert s.state.cards[token.id].tapped
    roundtrip(s)


def test_one_everywhere_land_satisfies_all_five_domain_types(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, _ = setup(cards)
    wait_priority(s, 'p1')
    spell = put(s, 'Tribal Flames', 'hand')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 35
    roundtrip(s)


def test_blood_moon_overwrites_types_and_intrinsic_mana_because_token_is_nonbasic(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _ = setup(cards)
    token = lands(s)[0]
    put(s, 'Blood Moon', 'battlefield')
    ch = chars(s, s.state.cards[token.id])
    assert ch.subtypes == {'Mountain'} and 'Basic' not in ch.supertypes
    intrinsic = [a.text for a in ch.abilities if a.intrinsic]
    assert intrinsic == ['{T}: Add {R}.']
    roundtrip(s)


def test_attacking_creates_another_tapped_everywhere(cards):
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import roundtrip, settle
    s, source = setup(cards)
    declare_only(s, [s.state.cards[source.id]], [])
    settle(s)
    assert sum(c.quantity for c in lands(s)) == 2
    assert sum(c.quantity for c in lands(s) if c.tapped) == 1
    roundtrip(s)


def test_creating_land_token_does_not_use_normal_land_play(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s, _ = setup(cards)
    to_phase(s, 'main2', turn=1)
    forests = [c.id for c in s.state.cards.values() if c.name == 'Forest' and c.zone == 'p1:library'][:2]
    assert len(forests) == 2
    act(s, 'p1', type='move', card_ids=forests, to={'player': 'p1', 'zone': 'hand'})
    assert s.state.rules.lands_this_turn('p1', s.state.turn.number) == 0
    act(s, 'p1', type='play_land', card_id=forests[0])
    assert s.state.rules.lands_this_turn('p1', s.state.turn.number) == 1
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=forests[1])
    assert s.state.cards[forests[0]].zone == 'p1:battlefield'
    assert sum(c.quantity for c in lands(s)) == 1
    roundtrip(s)
