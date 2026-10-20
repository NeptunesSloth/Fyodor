"""CR 603.7: chosen recipients are frozen for a turn-long combat-damage watch."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/targeted_damage_watch_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Great Train Heist'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Grizzly Bears', 'Runeclaw Bear', 'Fencing Ace', 'Lightning Bolt', 'Reverberate', 'Aggravated Assault'], ['Leyline of Sanctity'], [])
    spell = put(s, NAME, 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    ace = put(s, 'Fencing Ace', 'battlefield')
    to_phase(s, 'main1', turn=4)
    return s, spell, bear, other, ace


def cast(s, spell, modes, target='p2'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle

    mana(s, C=(2 if 0 in modes else 0)+(2 if 1 in modes else 0), R=1+int(0 in modes)+int(2 in modes))
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=modes, **({'targets': [target]} if 2 in modes else {}))
    settle(s)


def treasures(s):
    return [c for c in s.state.cards.values() if c.name == 'Treasure' and c.controller == 'p1' and c.zone == 'p1:battlefield']


def declare(s, attackers):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': pid} for c, pid in attackers])


def test_heist_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('phase,turn,adds', [('main1', 4, False), ('begin_combat', 4, True), ('begin_combat', 5, False)])
def test_first_mode_untaps_everywhere_but_adds_combat_only_in_your_combat(cards, phase, turn, adds):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, bear, other, _ = setup(cards)
    to_phase(s, phase, turn=turn)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    act(s, 'p1', type='tap', card_ids=[bear.id, other.id], tapped=True)
    cast(s, spell, [0])
    assert not s.state.cards[bear.id].tapped and not s.state.cards[other.id].tapped
    assert s.state.rules.extra_phases == (['begin_combat', 'main2'] if adds else [])
    roundtrip(s)


def test_chosen_opponent_only_and_one_tapped_treasure_per_creature_damage(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, bear, other, ace = setup(cards)
    cast(s, spell, [2])
    assert s.state.rules.delayed[0].when.get('recipient_players') == ['p2'], s.state.rules.delayed[0].model_dump()
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    declare(s, [(bear, 'p2'), (other, 'p3'), (ace, 'p2')])
    to_phase(s, 'main2', turn=4)
    # Bears deals once; Fencing Ace deals in first strike and regular damage.
    assert len(treasures(s)) == 3
    assert all(c.tapped for c in treasures(s))
    roundtrip(s)
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == 'main1')
    assert not s.state.rules.delayed
    roundtrip(s)


def test_all_modes_pay_their_cost_and_modes_resolve_in_order(cards):
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip

    s, spell, bear, other, _ = setup(cards)
    declare(s, [(bear, 'p2'), (other, 'p2')])
    cast(s, spell, [0, 1, 2])
    assert not any(s.state.players['p1'].mana.values()) and not s.state.players['p1'].mana_units
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    assert len(treasures(s)) == 2
    assert s.state.rules.combats == 2
    roundtrip(s)


def test_second_mode_affects_only_creatures_present_when_it_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, bear, _, ace = setup(cards)
    act(s, 'p1', type='move', card_ids=[ace.id], to={'player': 'p1', 'zone': 'hand'})
    cast(s, spell, [1])
    act(s, 'p1', type='move', card_ids=[ace.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert chars(s, bear).pt == (3, 2) and 'first strike' in chars(s, bear).keywords
    assert chars(s, ace).pt == (1, 1) and 'first strike' not in chars(s, ace).keywords
    roundtrip(s)


def test_all_target_modes_illegal_stops_untap_and_watch(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, bear, _, _ = setup(cards)
    act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
    mana(s, C=2, R=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[0, 2], targets=['p2'])
    put(s, 'Leyline of Sanctity', 'battlefield', 'p2')
    settle(s)
    assert s.state.cards[bear.id].tapped
    assert not s.state.rules.delayed and not s.state.rules.extra_phases
    roundtrip(s)


def test_copied_spell_binds_its_changed_opponent_separately(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, bear, other, _ = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, R=4)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[2], targets=['p2'])
    copy = put(s, 'Reverberate', 'hand')
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[spell.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert 'p3' in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert sorted(t.when.get('recipient_players') for t in s.state.rules.delayed) == [['p2'], ['p3']]
    roundtrip(s)
    declare(s, [(bear, 'p2'), (other, 'p3')])
    to_phase(s, 'main2', turn=4)
    assert len(treasures(s)) == 2
    assert all(c.tapped for c in treasures(s))
    roundtrip(s)


def test_first_mode_can_add_another_combat_during_an_extra_combat(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, _, _, _ = setup(cards)
    enchantment = put(s, 'Aggravated Assault', 'battlefield')
    to_phase(s, 'main2', turn=4)
    mana(s, C=3, R=2)
    act(s, 'p1', type='activate_ability', card_id=enchantment.id, ability=0)
    settle(s)
    until(s, lambda s: s.state.turn.phase == 'begin_combat' and s.state.rules.combats == 2)
    cast(s, spell, [0])
    assert s.state.rules.extra_phases == ['begin_combat', 'main2', 'end']
    roundtrip(s)
