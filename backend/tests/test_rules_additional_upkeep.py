"""CR 500.9-10a: inserted upkeep steps and upkeep-only beginning phases."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/additional_upkeep_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Paradox Haze', 'Obeka, Splitter of Seconds', 'The Ninth Doctor'])
def test_additional_upkeep_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    names = [name, 'Paradox Haze', 'Obeka, Splitter of Seconds', 'The Ninth Doctor', 'Sphinx of the Second Sun', 'Phyrexian Arena', 'Grizzly Bears', 'Fireshrieker', 'Aggravated Assault', 'Stasis', 'Seedborn Muse', 'Return the Favor', 'Great Train Heist', 'Eon Hub', 'Dragon Appeasement']
    s = table(cards, names, ['Return the Favor'], [])
    source = put(s, name, 'battlefield')
    if name == 'Paradox Haze':
        from tests.game_helpers import act

        act(s, 'p1', type='attach', card_ids=[source.id], to='p1')
    to_phase(s, 'main1', turn=4)
    return s, source


def test_haze_adds_upkeep_for_enchanted_player_instead_of_its_controller(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, haze = setup(cards, 'Paradox Haze')
    act(s, 'p1', type='attach', card_ids=[haze.id], to='p2')
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert s.state.rules.extra_steps == ['upkeep', 'draw']
    assert s.state.turn.active_player == 'p2'
    roundtrip(s)


def test_haze_first_upkeep_is_not_recursive_in_sphinx_beginning(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, sphinx = setup(cards, 'Sphinx of the Second Sun')
    haze = put(s, 'Paradox Haze', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[haze.id], to='p1')
    # Turn four already had its first upkeep before Haze entered.
    to_phase(s, 'main2', turn=4)
    settle(s)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert not s.state.rules.extra_steps
    assert s.state.rules.extra_phases == ['end']
    assert s.state.cards[sphinx.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_ninth_doctor_untap_trigger_waits_for_upkeep_and_adds_step_after_it(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, doctor = setup(cards, 'The Ninth Doctor')
    act(s, 'p1', type='tap', card_ids=[doctor.id], tapped=True)
    to_phase(s, 'upkeep', turn=7)
    assert not s.state.cards[doctor.id].tapped
    assert s.state.turn.phase == 'upkeep'
    assert s.state.zones.get('stack')
    settle(s)
    assert s.state.rules.extra_steps == ['upkeep', 'draw']
    assert s.state.turn.number == 7
    roundtrip(s)


def test_ninth_doctor_does_not_trigger_for_ordinary_main_phase_untap(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, doctor = setup(cards, 'The Ninth Doctor')
    act(s, 'p1', type='tap', card_ids=[doctor.id], tapped=True)
    act(s, 'p1', type='tap', card_ids=[doctor.id], tapped=False)
    settle(s)
    assert not s.state.rules.extra_steps
    assert not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('double_strike,upkeeps', [(False, 2), (True, 4)])
def test_obeka_adds_upkeep_only_phases_without_untap_or_draw_steps(cards, double_strike, upkeeps):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, obeka = setup(cards, 'Obeka, Splitter of Seconds')
    put(s, 'Phyrexian Arena', 'battlefield')
    idle = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[idle.id], tapped=True)
    if double_strike:
        equipment = put(s, 'Fireshrieker', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[equipment.id], to=obeka.id)
    hand, life = len(s.state.zones['p1:hand']), s.state.players['p1'].life
    declare_only(s, [obeka], [])
    to_phase(s, 'main2', turn=4)
    assert len(s.state.zones['p1:hand']) == hand + upkeeps
    assert s.state.players['p1'].life == life - upkeeps
    assert s.state.cards[idle.id].tapped
    assert s.state.rules.step_counts['upkeep'] == 1 + upkeeps
    assert s.state.rules.step_counts['draw'] == 1
    assert s.state.turn.number == 4
    roundtrip(s)


def test_ninth_doctor_triggers_during_added_untap_and_resumes_original_draw(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, doctor = setup(cards, 'The Ninth Doctor')
    put(s, 'Sphinx of the Second Sun', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[doctor.id], tapped=True)
    to_phase(s, 'main2', turn=4)
    settle(s)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.rules.extra_steps == ['upkeep', 'draw']
    assert s.state.rules.extra_phases == ['end']
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=4)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert s.state.rules.step_counts['upkeep'] == 3
    assert s.state.rules.step_counts['draw'] == 2
    roundtrip(s)


def test_two_hazes_add_two_upkeeps_without_retriggering(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, first = setup(cards, 'Paradox Haze')
    second = next(c for c in s.state.cards.values() if c.name == 'Paradox Haze' and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='attach', card_ids=[first.id, second.id], to='p2')
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert s.state.rules.extra_steps == ['upkeep', 'upkeep', 'draw']
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert s.state.rules.step_counts['upkeep'] == 3
    assert s.state.rules.step_counts['draw'] == 1
    assert not s.state.rules.extra_steps
    roundtrip(s)


def test_obeka_trigger_copied_by_nonactive_player_adds_no_steps_for_that_player(cards):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, obeka = setup(cards, 'Obeka, Splitter of Seconds')
    spell = put(s, 'Return the Favor', 'hand', 'p2')
    declare_only(s, [obeka], [])
    until(s, lambda s: any(s.state.cards[cid].ability is not None and s.state.cards[cid].name == obeka.name
                          for cid in s.state.zones.get('stack', [])))
    trigger = next(cid for cid in s.state.zones['stack'] if s.state.cards[cid].ability is not None and s.state.cards[cid].name == obeka.name)
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=1, R=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, modes=[0], targets=[trigger])
    settle(s)
    # CR 500.10a: only the original trigger's active controller gets upkeeps.
    assert len(s.state.rules.extra_phases) == 3
    assert s.state.rules.extra_phases[-1] == 'main2'
    assert s.state.turn.active_player == 'p1'
    roundtrip(s)


def test_ninth_doctor_ignores_seedborn_untap_in_another_players_untap(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, doctor = setup(cards, 'The Ninth Doctor')
    put(s, 'Seedborn Muse', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[doctor.id], tapped=True)
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert not s.state.cards[doctor.id].tapped
    assert not s.state.rules.extra_steps
    assert s.state.turn.active_player == 'p2'
    roundtrip(s)


def test_combat_created_later_precedes_already_queued_obeka_upkeeps(cards):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, obeka = setup(cards, 'Obeka, Splitter of Seconds')
    spell = put(s, 'Great Train Heist', 'hand')
    declare_only(s, [obeka], [])
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert len(s.state.rules.extra_phases) == 3
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[0])
    settle(s)
    assert s.state.rules.extra_phases[0] == 'begin_combat'
    assert len(s.state.rules.extra_phases) == 4
    assert s.state.rules.extra_phases[-1] == 'main2'
    roundtrip(s)
    to_phase(s, 'main2', turn=4)
    assert s.state.rules.combats == 2
    assert s.state.rules.step_counts['upkeep'] == 3
    roundtrip(s)


def test_skipped_obeka_upkeep_only_phases_do_not_create_draw_steps(cards):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, obeka = setup(cards, 'Obeka, Splitter of Seconds')
    act(s, 'p1', type='set_counter', card_id=obeka.id, kind='+1/+1', value=1)
    put(s, 'Eon Hub', 'battlefield')
    put(s, 'Phyrexian Arena', 'battlefield')
    equipment = put(s, 'Fireshrieker', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=obeka.id)
    before = len(s.state.zones['p1:hand'])
    declare_only(s, [obeka], [])
    to_phase(s, 'main2', turn=4)
    assert len(s.state.zones['p1:hand']) == before
    assert s.state.rules.step_counts['upkeep'] == 1
    assert s.state.rules.step_counts['draw'] == 1
    assert not s.state.rules.extra_phases
    roundtrip(s)


@pytest.mark.parametrize('skip,draws,upkeeps', [('Eon Hub', 1, 1), ('Dragon Appeasement', 0, 2)])
def test_skipped_added_beginning_step_preserves_phase_return(cards, skip, draws, upkeeps):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _ = setup(cards, 'Sphinx of the Second Sun')
    put(s, skip, 'battlefield')
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=4)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + draws
    assert s.state.rules.step_counts['upkeep'] == upkeeps
    assert s.state.rules.step_counts['draw'] == 1 + draws
    assert not s.state.rules.extra_phases
    assert s.state.turn.number == 4
    roundtrip(s)
