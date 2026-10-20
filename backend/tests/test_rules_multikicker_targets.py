"""CR 601.2b-c, 702.33c, 707.10: target count follows the announced multikicker count."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / 'fixtures/multikicker_target_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='mkt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name='Comet Storm'):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [c['name'] for c in DATA], ['Grizzly Bears', 'Unsummon', 'Counterspell'])
    return s, put(s, name, 'hand')


def cast(s, spell, *, x=4, kicks=0, targets=(), generic=None, free=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    color = 'R' if spell.name == 'Comet Storm' else 'G'
    pool = {'C': x + kicks if generic is None else generic, color: 0 if free else 2}
    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, kicker=kicks, targets=list(targets),
        target_counts=[len(targets)] if targets else [], free=free)


def finish(s):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Comet Storm', 'Strength of the Tajuru'])
def test_real_oracle_is_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('kicks,targets', [(0, ['p3']), (1, ['p2', 'p3']), (2, ['p1', 'p2', 'p3'])])
def test_comet_storm_deals_full_x_to_one_more_target_than_kicks(cards, kicks, targets):
    s, spell = setup(cards)
    cast(s, spell, kicks=kicks, targets=targets)
    entry = s.state.rules.stack[spell.id]
    assert entry.kicked == kicks and entry.x == 4
    assert entry.group_specs[0]['min'] == entry.group_specs[0]['max'] == kicks + 1
    assert 'per_kick_targets' not in entry.group_specs[0]
    finish(s)
    for pid in ('p1', 'p2', 'p3'):
        assert s.state.players[pid].life == (36 if pid in targets else 40)
    assert not any(s.state.players['p1'].mana.values())


@pytest.mark.parametrize('targets', [['p2'], ['p2', 'p3', 'p1'], ['p2', 'p2']])
def test_target_count_and_distinctness_are_enforced_before_payment(cards, targets):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip

    s, spell = setup(cards)
    with pytest.raises(ActionError):
        cast(s, spell, kicks=1, targets=targets)
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {'C': 5, 'R': 2}
    roundtrip(s)


def test_target_prompt_uses_announced_kicks_and_saves_before_payment(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell = setup(cards)
    cast(s, spell, kicks=2)
    d = s.state.rules.decision
    assert d.kind == 'choose_cards' and d.min_choices == d.max_choices == 3
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {'C': 6, 'R': 2}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1', 'p2', 'p3'])
    finish(s)
    assert all(p.life == 36 for p in s.state.players.values())


def test_target_prompt_cancels_without_spending(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell = setup(cards)
    cast(s, spell, kicks=1)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {'C': 5, 'R': 2}
    roundtrip(s)


def test_illegal_target_does_not_change_damage_to_remaining_targets(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    s, spell = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, spell, x=3, kicks=1, targets=[bear.id, 'p3'])
    wait_priority(s, 'p2')
    bounce = put(s, 'Unsummon', 'hand', pid='p2')
    mana(s, pid='p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[bear.id])
    finish(s)
    assert s.state.cards[bear.id].zone == 'p2:hand'
    assert s.state.players['p3'].life == 37


@pytest.mark.parametrize('kicks', [0, 1])
def test_tajuru_puts_x_counters_on_each_chosen_creature(cards, kicks):
    from tests.test_rules_designations import put

    s, spell = setup(cards, 'Strength of the Tajuru')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    targets = [bear.id, other.id][:kicks+1]
    cast(s, spell, x=3, kicks=kicks, targets=targets)
    finish(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 3
    assert s.state.cards[other.id].counters.get('+1/+1', 0) == (3 if kicks else 0)


def test_tajuru_rejects_player_target(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip

    s, spell = setup(cards, 'Strength of the Tajuru')
    with pytest.raises(ActionError):
        cast(s, spell, targets=['p2'])
    assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)


def test_kicker_cost_joins_base_before_reduction(cards):
    from tests.test_rules_designations import put

    s, spell = setup(cards)
    put(s, 'Goblin Electromancer', 'battlefield')
    cast(s, spell, x=4, kicks=2, targets=['p1', 'p2', 'p3'], generic=5)
    finish(s)
    assert all(p.life == 36 for p in s.state.players.values())
    assert not any(s.state.players['p1'].mana.values())


def test_free_cast_still_pays_multikicker_with_x_zero(cards):
    from tests.test_rules_designations import put

    s, spell = setup(cards)
    put(s, 'Omniscience', 'battlefield')
    cast(s, spell, x=0, kicks=2, targets=['p1', 'p2', 'p3'], generic=2, free=True)
    finish(s)
    assert all(p.life == 40 for p in s.state.players.values())
    assert not any(s.state.players['p1'].mana.values())


def test_stack_copy_preserves_x_kicks_and_materialized_target_count(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_copy import resolve_top
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast(s, spell, x=3, kicks=1, targets=['p2', 'p3'])
    reverberate = put(s, 'Reverberate', 'hand')
    mana(s, R=2)
    act(s, 'p1', type='cast_spell', card_id=reverberate.id, targets=[spell.id])
    resolve_top(s)
    for chosen in ('p1', 'keep'):
        d = s.state.rules.decision
        assert d is not None and chosen in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    copies = [entry for cid, entry in s.state.rules.stack.items() if cid != spell.id and entry.copy_of is not None]
    assert len(copies) == 1
    copy = copies[0]
    assert copy.x == 3 and copy.kicked == 1
    assert len(copy.targets) == 2 and copy.group_specs[0]['min'] == copy.group_specs[0]['max'] == 2
    roundtrip(s)
    finish(s)
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    assert s.state.players['p3'].life == 34


def test_no_legal_set_of_enough_creatures_rejects_before_payment(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'Strength of the Tajuru')
    put(s, 'Grizzly Bears', 'battlefield')
    with pytest.raises(ActionError):
        cast(s, spell, kicks=1)
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].mana == {'C': 5, 'G': 2}
    roundtrip(s)


def test_all_targets_illegal_counters_spell_by_rules(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    s, spell = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, spell, targets=[bear.id])
    wait_priority(s, 'p2')
    bounce = put(s, 'Unsummon', 'hand', pid='p2')
    mana(s, pid='p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[bear.id])
    finish(s)
    assert s.state.cards[bear.id].zone == 'p2:hand'
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert all(p.life == 40 for p in s.state.players.values())
