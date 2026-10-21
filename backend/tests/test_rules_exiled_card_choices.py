"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exiled_card_choices_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_voidwalker_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Dauthi Voidwalker')).level == 'FULL'


@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
def test_void_replacement_exiles_opponents_discards_with_counters(cards, pid):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Dauthi Voidwalker', 'One with Nothing', 'Grizzly Bears'],
              ['One with Nothing', 'Grizzly Bears'], ['One with Nothing', 'Grizzly Bears'])
    put(s, 'Dauthi Voidwalker', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand', pid)
    spell = put(s, 'One with Nothing', 'hand', pid)
    wait_priority(s, pid)
    mana(s, pid, B=1)
    act(s, pid, type='cast_spell', card_id=spell.id)
    settle(s)
    for c in [bear, spell]:
        moved = s.state.cards[c.id]
        assert moved.zone == f'{pid}:' + ('graveyard' if pid == 'p1' else 'exile')
        assert moved.counters.get('void', 0) == (0 if pid == 'p1' else 1)
    roundtrip(s)


def test_voidwalker_selects_opponents_countered_cards_and_casts_after_source_sacrifice(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Dauthi Voidwalker', 'Sol Ring'], ['Grizzly Bears', 'Sol Ring'], ['Grizzly Bears'])
    source = put(s, 'Dauthi Voidwalker', 'battlefield')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=4)
    own = put(s, 'Sol Ring', 'exile')
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    unmarked = put(s, 'Sol Ring', 'exile', 'p2')
    other = put(s, 'Grizzly Bears', 'exile', 'p3')
    for c in [own, bear, other]:
        act(s, 'p1', type='counter', card_ids=[c.id], kind='void', delta=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Choose an exiled'))
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert {o.id for o in d.options} == {bear.id, other.id}
    assert unmarked.id not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    roundtrip(s)
    act(s, 'p1', type='cast_spell', card_id=bear.id, free=True)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].controller == 'p1'
    roundtrip(s)


def test_voidwalker_can_play_a_chosen_land_and_permission_expires(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Dauthi Voidwalker'], ['Forest'], [])
    source = put(s, 'Dauthi Voidwalker', 'battlefield')
    to_phase(s, 'main1', turn=4)
    land = put(s, 'Forest', 'exile', 'p2')
    act(s, 'p1', type='counter', card_ids=[land.id], kind='void', delta=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Choose an exiled'))
    settle(s)
    # The only eligible card is chosen automatically, as for other public-zone choices.
    roundtrip(s)
    act(s, 'p1', type='play_land', card_id=land.id)
    assert s.state.cards[land.id].zone == 'p1:battlefield'
    roundtrip(s)
    # Moving the card back creates a new object: the permission must not follow it.
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p2', 'zone': 'exile'})
    to_phase(s, 'main1', turn=7)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    roundtrip(s)


def test_voidwalker_permission_cannot_be_used_on_later_turn(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Dauthi Voidwalker'], ['Grizzly Bears'], [])
    source = put(s, 'Dauthi Voidwalker', 'battlefield')
    to_phase(s, 'main1', turn=4)
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='void', delta=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Choose an exiled'))
    settle(s)
    to_phase(s, 'main1', turn=7)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, free=True)
    roundtrip(s)


@pytest.mark.parametrize('replacement,marked', [('Dauthi Voidwalker', True), ('Rest in Peace', False)])
def test_affected_player_chooses_between_void_counter_and_plain_exile(cards, replacement, marked):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Dauthi Voidwalker', 'Rest in Peace'], ['One with Nothing', 'Grizzly Bears'], [])
    put(s, 'Dauthi Voidwalker', 'battlefield')
    put(s, 'Rest in Peace', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    spell = put(s, 'One with Nothing', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', B=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    for _ in range(8):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == 'p2'
        assert '616.1' in d.prompt
        option = next(o for o in d.options if replacement in o.label)
        roundtrip(s)
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[option.id])
    assert s.state.cards[bear.id].zone == 'p2:exile'
    assert s.state.cards[bear.id].counters.get('void', 0) == int(marked)
    roundtrip(s)
