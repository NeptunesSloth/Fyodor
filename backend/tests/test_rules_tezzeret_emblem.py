"""CR 114.4, 608.2c, 611.2a: Tezzeret's lasting, conditional Robot animation emblem."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/tezzeret_emblem_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Tezzeret, Cruel Captain'


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, artifact='Sol Ring', *, solemnity=False, walker=NAME):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    s = table(cards, [walker, artifact, 'Solemnity'], ['Disenchant'])
    source = put(s, walker, 'battlefield')
    target = put(s, artifact, 'battlefield')
    if solemnity:
        put(s, 'Solemnity', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=7)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    emblems = [c for c in s.state.cards.values() if c.zone == 'p1:command' and c.token is not None and c.token.type_line == 'Emblem']
    assert len(emblems) == 1
    return s, target


def combat_trigger(s, target):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])


def test_noncreature_becomes_robot_and_stays_animated(cards):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase
    s, target = setup(cards)
    combat_trigger(s, target)
    settle(s)
    ch = chars(s, s.state.cards[target.id])
    assert ch.pt == (3, 3) and 'Robot' in ch.subtypes and {'Artifact', 'Creature'} <= ch.types
    assert s.state.cards[target.id].counters['+1/+1'] == 3
    to_phase(s, 'end', turn=1)
    assert chars(s, s.state.cards[target.id]).pt == (3, 3)
    roundtrip(s)


@pytest.mark.parametrize(('artifact', 'pt'), [('Ornithopter', (3, 5)), ('Solemn Simulacrum', (5, 5))])
def test_existing_creature_retains_base_stats_and_subtypes(cards, artifact, pt):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, target = setup(cards, artifact)
    combat_trigger(s, target)
    settle(s)
    ch = chars(s, s.state.cards[target.id])
    assert ch.pt == pt and 'Robot' not in ch.subtypes
    roundtrip(s)


def test_counter_prohibition_still_animates_then_zero_toughness_dies(cards):
    from tests.test_rules_designations import roundtrip, settle
    s, target = setup(cards, solemnity=True)
    combat_trigger(s, target)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_artifact_land_keeps_land_type_and_mana_ability(cards):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, target = setup(cards, 'Darksteel Citadel')
    combat_trigger(s, target)
    settle(s)
    ch = chars(s, s.state.cards[target.id])
    assert {'Land', 'Artifact', 'Creature'} <= ch.types
    assert 'Robot' in ch.subtypes and ch.pt == (3, 3)
    assert any('Add {C}' in a.text for a in ch.abilities)
    roundtrip(s)


def test_removed_target_makes_emblem_trigger_fail(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    s, target = setup(cards)
    combat_trigger(s, target)
    wait_priority(s, 'p2')
    spell = put(s, 'Disenchant', 'hand', 'p2')
    mana(s, 'p2', W=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_control_changed_target_is_illegal_on_resolution(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, target = setup(cards)
    combat_trigger(s, target)
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    settle(s)
    assert not s.state.cards[target.id].counters
    assert 'Creature' not in chars(s, s.state.cards[target.id]).types
    roundtrip(s)


def test_emblem_triggers_only_on_owners_combat_and_again_after_source_left(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase
    s, target = setup(cards)
    combat_trigger(s, target)
    settle(s)
    to_phase(s, 'begin_combat', turn=2)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].counters['+1/+1'] == 3
    to_phase(s, 'begin_combat', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].counters['+1/+1'] == 6
    assert chars(s, s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


def test_schemer_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Tezzeret the Schemer')).level == 'FULL'


@pytest.mark.parametrize('artifact', ['Sol Ring', 'Ornithopter', 'Darksteel Citadel'])
def test_schemer_emblem_sets_five_five_including_existing_creatures(cards, artifact):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase
    s, target = setup(cards, artifact, walker='Tezzeret the Schemer')
    combat_trigger(s, target)
    settle(s)
    ch = chars(s, s.state.cards[target.id])
    assert ch.pt == (5, 5) and {'Artifact', 'Creature'} <= ch.types
    if artifact == 'Ornithopter':
        assert 'Thopter' in ch.subtypes and 'flying' in ch.keywords
    to_phase(s, 'end', turn=1)
    assert chars(s, s.state.cards[target.id]).pt == (5, 5)
    roundtrip(s)


def test_schemer_artifact_land_remains_land_and_can_still_produce_mana(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, target = setup(cards, 'Darksteel Citadel', walker='Tezzeret the Schemer')
    combat_trigger(s, target)
    settle(s)
    to_phase(s, 'main1', turn=4)
    assert {'Land', 'Artifact', 'Creature'} <= chars(s, s.state.cards[target.id]).types
    before = s.state.players['p1'].mana.get('C', 0) + sum(u.sym == 'C' for u in s.state.players['p1'].mana_units)
    act(s, 'p1', type='activate_ability', card_id=target.id, ability=ability_index(s, target, 'Add {C}'))
    after = s.state.players['p1'].mana.get('C', 0) + sum(u.sym == 'C' for u in s.state.players['p1'].mana_units)
    assert after == before + 1
    assert s.state.cards[target.id].tapped
    roundtrip(s)
