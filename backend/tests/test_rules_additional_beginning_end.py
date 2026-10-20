"""CR 500.8-9: additional beginning phases and end steps stay within one turn."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/additional_beginning_end_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Sphinx of the Second Sun', "Y'shtola Rhul"])
def test_additional_step_sources_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    names = [name, 'Sol Ring', 'Grizzly Bears', 'Phyrexian Arena', 'Howling Mine', 'Sandbar Crocodile', 'Getaway Glamer', 'Giant Growth', 'Aggravated Assault', 'Stasis', 'Seedborn Muse', 'Vedalken Shackles', 'Hollow Trees', 'Winter Orb', 'Glimmerpost', 'Island', "Teferi's Protection", 'Slaughter Pact', 'Opera Love Song']
    s = table(cards, names, [], [])
    source = put(s, name, 'battlefield')
    rock = put(s, 'Sol Ring', 'battlefield')
    to_phase(s, 'main1', turn=4)
    return s, source, rock


def test_sphinx_queues_beginning_then_ending_without_new_main_or_turn(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, rock = setup(cards, 'Sphinx of the Second Sun')
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert s.state.rules.extra_phases == ['untap', 'end']
    act(s, 'p1', type='tap', card_ids=[rock.id], tapped=True)
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=4)
    assert not s.state.cards[rock.id].tapped
    assert len(s.state.zones['p1:hand']) == before + 1
    assert s.state.turn.number == 4
    roundtrip(s)


def test_extra_beginning_runs_upkeep_and_draw_triggers(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    put(s, 'Phyrexian Arena', 'battlefield')
    put(s, 'Howling Mine', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    life = s.state.players['p1'].life
    to_phase(s, 'end', turn=4)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 3
    assert s.state.players['p1'].life == life - 1
    roundtrip(s)


def test_extra_untap_consumes_stun_instead_of_untapping(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, rock = setup(cards, 'Sphinx of the Second Sun')
    act(s, 'p1', type='tap', card_ids=[rock.id], tapped=True)
    act(s, 'p1', type='set_counter', card_id=rock.id, kind='stun', value=1)
    to_phase(s, 'end', turn=4)
    assert s.state.cards[rock.id].tapped
    assert not s.state.cards[rock.id].counters.get('stun')
    roundtrip(s)


def test_yshtola_adds_exactly_one_extra_end_step(cards):
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, "Y'shtola Rhul")
    put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.rules.extra_phases == ['end', 'cleanup']
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'end' and s.state.rules.extra_phases == ['cleanup'])
    settle(s)
    assert s.state.rules.extra_phases == ['cleanup']
    assert s.state.turn.number == 4
    roundtrip(s)


def test_yshtola_second_end_step_triggers_next_end_step_created_in_first(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, "Y'shtola Rhul")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Getaway Glamer', 'hand')
    to_phase(s, 'end', turn=4)
    settle(s)
    mana(s, W=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[0], targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:exile'
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'end' and s.state.rules.extra_phases == ['cleanup'])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.turn.number == 4
    roundtrip(s)


def test_extra_end_step_preserves_damage_and_until_end_of_turn_until_cleanup(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, "Y'shtola Rhul")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    growth = put(s, 'Giant Growth', 'hand')
    to_phase(s, 'end', turn=4)
    settle(s)
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[bear.id])
    settle(s)
    assert chars(s, s.state.cards[bear.id]).pt[0] == 5
    act(s, 'p1', type='set_damage', card_ids=[bear.id], value=1)
    until(s, lambda s: s.state.turn.phase == 'end' and s.state.rules.extra_phases == ['cleanup'])
    # The turn-based cleanup action has not happened between the end steps.
    assert s.state.cards[bear.id].damage == 1
    assert chars(s, s.state.cards[bear.id]).pt[0] == 5
    roundtrip(s)
    settle(s)
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[bear.id].damage == 0
    assert chars(s, s.state.cards[bear.id]).pt[0] == 2
    roundtrip(s)


def test_later_added_combat_precedes_already_queued_beginning(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    assault = put(s, 'Aggravated Assault', 'battlefield')
    to_phase(s, 'main2', turn=4)
    settle(s)
    mana(s, C=3, R=2)
    act(s, 'p1', type='activate_ability', card_id=assault.id, ability=ability_index(s, assault, 'Untap'))
    settle(s)
    assert s.state.rules.extra_phases == ['begin_combat', 'main2', 'untap', 'end']
    roundtrip(s)


def test_extra_untap_really_performs_phasing(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    crocodile = put(s, 'Sandbar Crocodile', 'battlefield')
    to_phase(s, 'end', turn=4)
    assert s.state.cards[crocodile.id].zone == 'p1:phased'
    roundtrip(s)


def test_same_turn_untap_choice_resumes_into_upkeep_without_new_turn(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    tree = put(s, 'Hollow Trees', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[tree.id], tapped=True)
    to_phase(s, 'main2', turn=4)
    settle(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'untap_keep')
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {tree.id}
    assert s.state.turn.number == 4
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[tree.id])
    settle(s)
    assert s.state.turn.phase == 'upkeep' and s.state.turn.number == 4
    assert s.state.cards[tree.id].tapped and s.state.cards[tree.id].counters['storage'] == 1
    roundtrip(s)


def test_same_turn_untap_limit_choice_does_not_advance_turn(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    put(s, 'Winter Orb', 'battlefield')
    lands = [put(s, n, 'battlefield') for n in ['Glimmerpost', 'Island']]
    act(s, 'p1', type='tap', card_ids=[c.id for c in lands], tapped=True)
    to_phase(s, 'main2', turn=4)
    settle(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'untap_limit')
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {c.id for c in lands}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[lands[0].id])
    settle(s)
    assert s.state.turn.number == 4 and s.state.turn.phase == 'upkeep'
    assert not s.state.cards[lands[0].id].tapped and s.state.cards[lands[1].id].tapped
    roundtrip(s)


def test_extra_beginning_preserves_until_next_turn_effects_and_phases_cards_in(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, source, rock = setup(cards, 'Sphinx of the Second Sun')
    spell = put(s, "Teferi's Protection", 'hand')
    to_phase(s, 'main2', turn=4)
    settle(s)
    mana(s, C=2, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:phased'
    assert s.state.cards[rock.id].zone == 'p1:phased'
    to_phase(s, 'end', turn=4)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[rock.id].zone == 'p1:battlefield'
    assert [x['until'] for x in s.state.rules.life_locks] == ['next_turn']
    assert any(x['shield'] == 'protection' and x['quality'] == 'everything' for x in s.state.rules.player_shields)
    assert s.state.turn.number == 4
    roundtrip(s)


def test_next_upkeep_created_in_main_fires_in_same_turn_added_beginning(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, 'Sphinx of the Second Sun')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    pact = put(s, 'Slaughter Pact', 'hand')
    to_phase(s, 'main2', turn=4)
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=pact.id, targets=[bear.id])
    settle(s)
    assert len(s.state.rules.delayed) == 1
    roundtrip(s)
    to_phase(s, 'upkeep', turn=4)
    assert s.state.turn.number == 4
    assert s.state.zones.get('stack')
    assert not s.state.rules.delayed
    mana(s, C=2, B=1)
    settle(s)
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_next_end_permission_granted_in_first_end_expires_in_second(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = setup(cards, "Y'shtola Rhul")
    spell = put(s, 'Opera Love Song', 'hand')
    to_phase(s, 'end', turn=4)
    settle(s)
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[0])
    settle(s)
    assert len(s.state.rules.permissions) == 2
    assert all(p.until == 'next_end_step' for p in s.state.rules.permissions)
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'end' and s.state.rules.extra_phases == ['cleanup'])
    assert not s.state.rules.permissions
    assert s.state.turn.number == 4
    roundtrip(s)


def test_yshtola_illegal_sole_target_does_not_add_end_step(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_wave30m_durations import to_phase

    s, source, _ = setup(cards, "Y'shtola Rhul")
    to_phase(s, 'end', turn=4)
    until(s, lambda s: bool(s.state.zones.get('stack')) and s.state.rules.decision is None)
    # Y'shtola is the only creature, so its trigger necessarily targeted itself.
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert not s.state.rules.extra_phases
    assert s.state.turn.phase == 'end' and s.state.turn.number == 4
