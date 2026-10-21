"""CR 702.168d, 118.7: reduced disguise special-action costs."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/reduced_disguise_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Fugitive Codebreaker'


def test_codebreaker_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_disguise(cards, count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    names = [['Lightning Bolt', 'Opt', 'Divination', 'Fire // Ice'][i % 4] for i in range(count)]
    s = table(cards, [NAME, *names, 'Sol Ring'], ['Opt'])
    source = put(s, NAME, 'hand')
    picked = []
    for name in names:
        picked.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in picked))
    if picked:
        act(s, 'p1', type='move', card_ids=picked, to={'player': 'p1', 'zone': 'graveyard'})
    put(s, 'Sol Ring', 'graveyard')
    put(s, 'Opt', 'graveyard', 'p2')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face_down=True)
    settle(s)
    assert s.state.cards[source.id].face_down and s.state.cards[source.id].face_down_kind == 'disguise'
    assert s.state.players['p1'].mana.get('C', 0) == 0  # The reduction never changes the {3} casting cost.
    return s, source, picked


@pytest.mark.parametrize('count', [0, 1, 2, 4, 5, 8])
def test_only_own_instant_sorcery_cards_reduce_generic_face_up_cost(cards, count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, _ = setup_disguise(cards, count)
    mana(s, C=max(0, 5 - count), R=1)
    cost = ('{' + str(5 - count) + '}' if count < 5 else '') + '{R}'
    assert s.view('p1')['rules']['stats'][source.id]['turn_up'] == [{'method': 'disguise', 'cost': cost}]
    assert source.id not in s.view('p2')['rules']['stats']
    roundtrip(s)
    act(s, 'p1', type='turn_face_up', card_id=source.id, method='disguise')
    assert not s.state.cards[source.id].face_down and chars(s, source).pt == (2, 1)
    assert not any(s.state.players['p1'].mana.values())
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    settle(s)
    assert len(s.state.zones['p1:hand']) == 3  # Its turned-face-up trigger discards the old hand, then draws three.
    roundtrip(s)


def test_reduction_cannot_pay_the_red_symbol(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, _ = setup_disguise(cards, 8)
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='turn_face_up', card_id=source.id, method='disguise')
    assert s.state.cards[source.id].face_down and s.state.players['p1'].mana == {'C': 1}
    mana(s, R=1)
    act(s, 'p1', type='turn_face_up', card_id=source.id, method='disguise')
    assert s.state.players['p1'].mana == {'C': 1}
    settle(s)
    roundtrip(s)


def test_graveyard_count_is_recomputed_when_paying_not_when_casting_face_down(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, picked = setup_disguise(cards, 2)
    mana(s, C=3, R=1)
    act(s, 'p1', type='move', card_ids=[picked[0]], to={'player': 'p1', 'zone': 'exile'})
    with pytest.raises(ActionError):
        act(s, 'p1', type='turn_face_up', card_id=source.id, method='disguise')
    assert s.state.cards[source.id].face_down
    mana(s, C=1)
    roundtrip(s)
    act(s, 'p1', type='turn_face_up', card_id=source.id, method='disguise')
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    roundtrip(s)
