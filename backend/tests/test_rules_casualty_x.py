"""CR 107.3a, 702.153a, 707.9: casualty X and starting loyalty."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/casualty_x_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Ob Nixilis, the Adversary'


def test_ob_nixilis_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, power=None, doubling=False, free=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter', 'Doubling Season', 'Omniscience', 'Electrodominance', 'Clever Impersonator'], ['Counterspell', 'Stifle'])
    spell = put(s, NAME, 'hand')
    creature = put(s, 'Grizzly Bears', 'battlefield')
    if power is not None:
        act(s, 'p1', type='set_counter', card_id=creature.id, kind='+1/+1', value=power-2)
    if doubling:
        put(s, 'Doubling Season', 'battlefield')
    if free:
        put(s, 'Omniscience', 'battlefield')
    return s, spell, creature


def cast(s, spell, *, x=None, casualty=True, **extra):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    mana(s, C=1, B=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id,
        optional_costs=[f'{spell.id}:casualty'] if casualty else [],
        **({'x_value': x} if x is not None else {}), **extra)


def copies(s):
    return [c for c in s.state.cards.values() if c.name == NAME and c.is_token and c.zone == 'p1:battlefield']


@pytest.mark.parametrize('x,power', [(1, 2), (2, 2), (4, 5)])
def test_chosen_x_not_sacrificed_power_sets_nonlegendary_copy_starting_loyalty(cards, x, power):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, creature = setup(cards, power=power)
    cast(s, spell, x=x)
    settle(s)
    tokens = copies(s)
    assert len(tokens) == 1
    assert tokens[0].counters['loyalty'] == x and chars(s, tokens[0]).loyalty == str(x)
    assert 'Legendary' not in chars(s, tokens[0]).supertypes
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].counters['loyalty'] == 3
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_x_zero_creates_zero_loyalty_copy_that_dies(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards)
    cast(s, spell, x=0)
    settle(s)
    assert not copies(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield' and s.state.cards[spell.id].counters['loyalty'] == 3
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_declining_casualty_creates_no_copy_and_requires_no_x(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards)
    cast(s, spell, casualty=False)
    settle(s)
    assert not copies(s) and s.state.cards[creature.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].counters['loyalty'] == 3
    roundtrip(s)


def test_x_above_any_eligible_power_rejects_without_payment(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards)
    with pytest.raises(ActionError):
        cast(s, spell, x=3)
    assert s.state.cards[spell.id].zone == 'p1:hand' and s.state.cards[creature.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].mana == {'C': 1, 'B': 1, 'R': 1}
    roundtrip(s)


def test_missing_x_prompts_before_any_cost_is_paid(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards)
    cast(s, spell)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'casualty_x'
    assert {o.id for o in d.options} == {'x:0', 'x:1', 'x:2'}
    assert s.state.cards[spell.id].zone == 'p1:hand' and s.state.cards[creature.id].zone == 'p1:battlefield'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:1'])
    settle(s)
    assert copies(s)[0].counters['loyalty'] == 1
    roundtrip(s)


def test_doubling_season_doubles_entry_loyalty_without_making_extra_spell_copy_tokens(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, doubling=True)
    cast(s, spell, x=2)
    settle(s)
    assert len(copies(s)) == 1 and copies(s)[0].counters['loyalty'] == 4
    assert s.state.cards[spell.id].counters['loyalty'] == 6
    roundtrip(s)


@pytest.mark.parametrize('counter_trigger', [False, True])
def test_countering_original_or_casualty_trigger_preserves_the_other(cards, counter_trigger):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, creature = setup(cards)
    cast(s, spell, x=2)
    wait_priority(s, 'p2')
    counter = put(s, 'Stifle' if counter_trigger else 'Counterspell', 'hand', pid='p2')
    mana(s, pid='p2', U=1 if counter_trigger else 2)
    target = next(cid for cid in s.state.zones['stack'] if s.state.cards[cid].ability is not None) if counter_trigger else spell.id
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[target])
    roundtrip(s)
    settle(s)
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    assert len(copies(s)) == (0 if counter_trigger else 1), [(c.id, c.zone, c.is_token, c.counters, c.name) for c in s.state.cards.values() if c.name == NAME]
    assert s.state.cards[spell.id].zone == ('p1:battlefield' if counter_trigger else 'p1:graveyard')
    if not counter_trigger:
        assert copies(s)[0].counters['loyalty'] == 2
    roundtrip(s)


def test_casualty_x_prompt_can_cancel_without_sacrificing_or_spending_mana(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards)
    cast(s, spell)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[spell.id].zone == 'p1:hand' and s.state.cards[creature.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].mana == {'C': 1, 'B': 1, 'R': 1}
    roundtrip(s)


def test_large_x_choice_is_paginated_without_losing_replay_state(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, power=105)
    cast(s, spell)
    d = s.state.rules.decision
    assert d is not None and 'page:100' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['page:100'])
    d = s.state.rules.decision
    assert 'x:105' in {o.id for o in d.options} and 'page:0' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:104'])
    settle(s)
    assert copies(s)[0].counters['loyalty'] == 104
    roundtrip(s)


def test_omniscience_still_pays_casualty_with_chosen_nonzero_x(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, creature = setup(cards, free=True)
    act(s, 'p1', type='cast_spell', card_id=spell.id, free=True,
        optional_costs=[f'{spell.id}:casualty'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'casualty_x'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:2'])
    settle(s)
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    assert copies(s)[0].counters['loyalty'] == 2
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_casualty_x_on_a_spell_cast_while_electrodominance_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle

    s, spell, creature = setup(cards)
    from tests.test_rules_bandmate_references import mana

    electro = put(s, 'Electrodominance', 'hand')
    mana(s, C=3, R=2)
    act(s, 'p1', type='cast_spell', card_id=electro.id, x_value=3, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and spell.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[spell.id])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'free_optional'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[f'{spell.id}:casualty'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'casualty_x'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:2'])
    # The chosen casualty creature is paid with the free cast's additional cost.
    d = s.state.rules.decision
    if d is not None:
        assert creature.id in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[creature.id])
    from tests.test_rules_conditionals import settle as finish
    finish(s)
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    assert copies(s)[0].counters['loyalty'] == 2
    assert s.state.cards[spell.id].counters['loyalty'] == 3
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_starting_loyalty_exception_is_copiable_but_current_loyalty_counters_are_not(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_designations import settle as until_choice
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, _ = setup(cards)
    cast(s, spell, x=2)
    settle(s)
    original_copy = copies(s)[0]
    act(s, 'p1', type='set_counter', card_id=original_copy.id, kind='loyalty', value=7)
    wait_priority(s, 'p1')
    clone = put(s, 'Clever Impersonator', 'hand')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=clone.id)
    until_choice(s)
    d = s.state.rules.decision
    assert d is not None and original_copy.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[original_copy.id])
    settle(s)
    assert s.state.cards[clone.id].zone == 'p1:battlefield'
    assert s.state.cards[clone.id].counters['loyalty'] == 2
    assert chars(s, clone).loyalty == '2' and 'Legendary' not in chars(s, clone).supertypes
    assert s.state.cards[original_copy.id].counters['loyalty'] == 7
    roundtrip(s)
