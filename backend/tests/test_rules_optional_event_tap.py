"""CR 603.2, 118.12, 701.21: entering untapped and optional tapping."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/optional_event_tap_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_conqueror_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Charismatic Conqueror')).level == 'FULL'


def setup_entry(cards, name='Grizzly Bears', pid='p2', *, authority=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Charismatic Conqueror', 'Grizzly Bears', 'Authority of the Consuls'],
              ['Grizzly Bears', 'Sol Ring', 'Walking Ballista'], ['Grizzly Bears', 'Sol Ring', 'Walking Ballista'])
    source = put(s, 'Charismatic Conqueror', 'battlefield')
    if authority:
        put(s, 'Authority of the Consuls', 'battlefield')
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=int(pid[1:]))
    settle(s)
    entering = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    mana(s, pid, G=4)
    act(s, pid, type='cast_spell', card_id=entering.id, **({'x_value': 1} if name == 'Walking Ballista' else {}))
    settle(s)
    return s, source, entering


@pytest.mark.parametrize('name', ['Grizzly Bears', 'Sol Ring', 'Walking Ballista'])
@pytest.mark.parametrize('pid', ['p2', 'p3'])
@pytest.mark.parametrize('tap', [True, False])
def test_entering_opponents_choice_and_vampire_creation(cards, name, pid, tap):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, entering = setup_entry(cards, name, pid)
    d = s.state.rules.decision
    assert d and d.player == pid
    roundtrip(s)
    act(s, pid, type='choose', decision_id=d.id, option_ids=['tap' if tap else 'decline'])
    settle(s)
    assert s.state.cards[entering.id].tapped == tap
    vampires = [c for c in s.state.cards.values() if c.is_token and c.name == 'Vampire']
    assert len(vampires) == (0 if tap else 1)
    if vampires:
        assert vampires[0].controller == 'p1'
        assert vampires[0].token and vampires[0].token.text == 'Lifelink'
    roundtrip(s)


@pytest.mark.parametrize('authority', [False, True])
def test_own_permanents_and_tapped_opponents_do_not_trigger(cards, authority):
    from tests.test_rules_designations import roundtrip

    s, _, entering = setup_entry(cards, pid='p2' if authority else 'p1', authority=authority)
    assert s.state.rules.decision is None
    assert s.state.cards[entering.id].tapped == authority
    assert not any(c.is_token and c.name == 'Vampire' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('change', ['tap', 'leave', 'blink', 'control', 'source_leaves'])
def test_pending_choice_tracks_event_object_and_original_player(cards, change):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source, entering = setup_entry(cards)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    if change == 'tap':
        act(s, 'p2', type='tap', card_ids=[entering.id], tapped=True)
    elif change in {'leave', 'blink'}:
        act(s, 'p2', type='move', card_ids=[entering.id], to={'player': 'p2', 'zone': 'graveyard'})
        if change == 'blink':
            act(s, 'p2', type='move', card_ids=[entering.id], to={'player': 'p2', 'zone': 'battlefield'})
    elif change == 'control':
        act(s, 'p2', type='set_controller', card_ids=[entering.id], player='p3')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['tap'])
    settle(s)
    vampires = [c for c in s.state.cards.values() if c.is_token and c.name == 'Vampire']
    assert len(vampires) == (1 if change in {'tap', 'leave', 'blink'} else 0)
    if change == 'blink':
        assert not s.state.cards[entering.id].tapped
    roundtrip(s)
