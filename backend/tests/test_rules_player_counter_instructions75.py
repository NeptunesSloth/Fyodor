"""Player-relative counter and tap choices retain actual chooser and putter."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Gluntch, the Bestower', 'Tangle Wire', 'Mikey & Mona, Mutant Sitters']
DATA = json.loads((Path(__file__).parent / 'fixtures/player_counter_instructions75_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [*NAMES, 'Llanowar Elves', 'Sol Ring', 'Bold Plagiarist'], ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest'])
    start(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical_is_read(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_gluntch_distinct_players_and_first_player_chooses_own_creature(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'end', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[first.id])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'p2' not in [o.id for o in d.options]
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    d = s.state.rules.decision
    assert d and [o.id for o in d.options] == ['p3']
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert first.counters == {'+1/+1': 2}
    assert len(s.state.zones['p1:hand']) == before + 1
    assert len([c for c in s.state.cards.values() if c.zone == 'p3:battlefield' and c.name == 'Treasure']) == 2
    roundtrip(s)


def test_tangle_wire_native_fading_and_other_player_tap_choice(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert source.counters == {'fade': 4}
    chosen = [put(s, name, 'battlefield', 'p2') for name in ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']]
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert all(c.tapped for c in chosen)
    assert source.counters == {'fade': 4}
    roundtrip(s)


def test_mikey_both_modes_native_target_and_choice_probe(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p2')
    grave = put(s, 'Forest', 'graveyard', 'p1')
    source = put(s, NAMES[2], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['0:0', '1:0'])
    d = s.state.rules.decision
    assert d.player == 'p1'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    d = s.state.rules.decision
    assert d.player == 'p1' and 'p2' not in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is None or d.player == 'p1'
    if d:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[grave.id])
        settle(s)
    assert target.counters == {'+1/+1': 2}
    assert grave.zone == 'p1:hand'
    roundtrip(s)


def answer_gluntch(s, first='p2', second='p1'):
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[first])
    d = s.state.rules.decision
    if d and d.kind == 'choose_cards':
        assert d.player == first
        act(s, first, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d and first not in [o.id for o in d.options]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[second])
    d = s.state.rules.decision
    if d:
        assert d.player == 'p1'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)


def test_gluntch_actual_first_player_putter_triggers_opponents_bold_plagiarist(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    watcher = put(s, 'Bold Plagiarist', 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert recipient.counters == {'+1/+1': 2}
    assert watcher.counters == {'+1/+1': 2}
    roundtrip(s)


def test_gluntch_two_remaining_players_skip_third_token_instruction(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    act(s, 'p3', type='leave')
    put(s, NAMES[0], 'battlefield')
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert not any(c.name == 'Treasure' and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


def test_tangle_wire_fading_removes_counter_on_actual_own_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    to_phase(s, 'main1', turn=7)
    assert source.counters == {'fade': 3} and source.zone == 'p1:battlefield'
    roundtrip(s)
