"""CR 118.3, 702.24a: counter costs on opponents and repeated choices."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/opponent_counter_cost_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Sheltering Ancient'


def test_ancient_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, opponents=1, age=0, modifier=None):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Solemnity', 'Vorinclex, Monstrous Raider', 'Doubling Season'],
              ['Grizzly Bears'], ['Grizzly Bears'])
    source = put(s, NAME, 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    recipients = [put(s, 'Grizzly Bears', 'battlefield', pid=pid) for pid in ['p2', 'p3'][:opponents]]
    if age:
        act(s, 'p1', type='set_counter', card_id=source.id, kind='age', value=age)
    if modifier:
        put(s, modifier, 'battlefield')
    return s, source, own, recipients


@pytest.mark.parametrize('age', [0, 1, 3])
def test_each_age_cost_can_use_the_same_opponent_creature(cards, age):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_upkeep_costs import until_prompt

    s, source, own, recipients = setup(cards, age=age)
    d = until_prompt(s)
    assert d.player == 'p1' and {o.id for o in d.options} == {'pay', 'decline'}
    assert s.state.cards[source.id].counters['age'] == age + 1
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[recipients[0].id].counters['+1/+1'] == age + 1
    assert not s.state.cards[own.id].counters
    roundtrip(s)


@pytest.mark.parametrize('same', [False, True])
def test_each_age_choice_can_pick_a_different_opponent_and_pays_together(cards, same):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_upkeep_costs import until_prompt

    s, source, own, recipients = setup(cards, opponents=2, age=1)
    d = until_prompt(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    for recipient in ([recipients[0]] * 2 if same else recipients):
        d = s.state.rules.decision
        assert d is not None and d.player == 'p1'
        assert {o.id for o in d.options} == {c.id for c in recipients}
        assert own.id not in {o.id for o in d.options}
        assert all(not s.state.cards[c.id].counters for c in recipients)
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[recipient.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert [s.state.cards[c.id].counters.get('+1/+1', 0) for c in recipients] == ([2, 0] if same else [1, 1])
    roundtrip(s)


@pytest.mark.parametrize('modifier,expected', [('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 4)])
def test_cost_counters_use_payer_and_cost_not_effect_replacements(cards, modifier, expected):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_upkeep_costs import until_prompt

    s, source, _, recipients = setup(cards, modifier=modifier)
    d = until_prompt(s)
    # Age is placed by an effect, so both double it. Cost counters are placed
    # by p1, but Doubling Season only affects effects on permanents p1 controls.
    assert s.state.cards[source.id].counters['age'] == 2
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[recipients[0].id].counters['+1/+1'] == expected
    roundtrip(s)


@pytest.mark.parametrize('mode', ['decline', 'none', 'prohibited'])
def test_declined_or_unpayable_whole_cost_sacrifices_ancient(cards, mode):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_upkeep_costs import until_prompt

    s, source, _, recipients = setup(cards, opponents=0 if mode == 'none' else 1,
                                    age=1 if mode == 'prohibited' else 0,
                                    modifier='Solemnity' if mode == 'prohibited' else None)
    if mode == 'decline':
        d = until_prompt(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
        settle(s)
    else:
        from tests.test_rules_wave30m_durations import to_phase
        to_phase(s, 'upkeep', turn=4)
        settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert all(not s.state.cards[c.id].counters for c in recipients)
    roundtrip(s)
