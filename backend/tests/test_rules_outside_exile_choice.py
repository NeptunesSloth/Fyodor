"""CR 903.11, 406.3: Karn can choose owned face-up exiled artifacts in Commander."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import CollectionCard
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/outside_exile_choice_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='oec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, ['Karn, the Great Creator', 'Sol Ring', 'Lightning Bolt'], ['Sol Ring'])
    c = cards.resolve('Sol Ring')
    s.state.collections['p1'] = [CollectionCard(printing_id=c['id'], oracle_id=c['oracle_id'], name=c['name'], quantity=2)]
    s = GameSession(s.state, cards=cards)
    to_phase(s, 'main1')
    karn = put(s, 'Karn, the Great Creator', 'hand')
    mana(s, C=4)
    act(s, 'p1', type='cast_spell', card_id=karn.id)
    settle(s)
    assert s.state.cards[karn.id].counters['loyalty'] == 5
    return s, karn


def activate(s, karn):
    act(s, 'p1', type='activate_ability', card_id=karn.id, ability=2)
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Karn, the Great Creator')).level == 'FULL'


def test_no_exile_options_does_not_import_owned_collection(cards):
    s, karn = setup(cards)
    before = set(s.state.cards)
    activate(s, karn)
    assert s.state.rules.decision is None
    assert set(s.state.cards) == before
    assert s.state.cards[karn.id].counters['loyalty'] == 3
    assert s.state.collections['p1'][0].quantity == 2
    assert 'collections' not in s.view('p2')
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_owned_exiled_artifact_is_optional_nontargeted_choice(cards, accept):
    s, karn = setup(cards)
    owned = put(s, 'Sol Ring', 'exile')
    rival = put(s, 'Sol Ring', 'exile', 'p2')
    nonartifact = put(s, 'Lightning Bolt', 'exile')
    activate(s, karn)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == 0
    assert {o.card_id for o in d.options} == {owned.id}
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[rival.id])
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[owned.id] if accept else [])
    settle(s)
    assert s.state.cards[owned.id].zone == ('p1:hand' if accept else 'p1:exile')
    assert s.state.cards[rival.id].zone == 'p2:exile'
    assert s.state.cards[nonartifact.id].zone == 'p1:exile'
    roundtrip(s)


def test_face_down_exiled_owned_artifact_cannot_be_chosen(cards):
    s, karn = setup(cards)
    owned = put(s, 'Sol Ring', 'exile')
    act(s, 'p1', type='face_down', card_ids=[owned.id], face_down=True)
    activate(s, karn)
    assert s.state.rules.decision is None
    assert not any(c.name == 'Sol Ring' and c.zone == 'p1:hand' for c in s.state.cards.values())
    roundtrip(s)
