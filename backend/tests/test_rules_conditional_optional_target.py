"""CR 601.2c, 608.2d: conditional optional second target."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_optional_target_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Return to Dust'


def test_return_to_dust_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_spell(cards, phase='main1', turn=1, *, second=True, hold=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Twincast'], ['Sol Ring', 'Arcane Signet'])
    source = put(s, NAME, 'hand')
    a = put(s, 'Sol Ring', 'battlefield', 'p2')
    b = put(s, 'Arcane Signet', 'battlefield', 'p2')
    to_phase(s, phase, turn=turn)
    wait_priority(s, 'p1')
    if hold:
        act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, W=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[a.id, *([b.id] if second else [])], target_counts=[1, int(second)])
    return s, source, a, b


@pytest.mark.parametrize('phase,turn,bonus', [('main1', 1, True), ('main2', 1, True), ('begin_combat', 1, False),
                                           ('main1', 2, False), ('end', 1, False)])
@pytest.mark.parametrize('accept', [True, False])
def test_cast_timing_gates_second_exile_and_controller_may_still_decline(cards, phase, turn, bonus, accept):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, a, b = setup_spell(cards, phase, turn)
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:exile'
    if bonus:
        d = s.state.rules.decision
        assert d and d.player == 'p1'
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if accept else 'decline'])
        settle(s)
    else:
        assert s.state.rules.decision is None
    assert s.state.cards[b.id].zone == ('p2:exile' if bonus and accept else 'p2:battlefield')
    roundtrip(s)


def test_zero_optional_targets_needs_no_choice(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, _, a, b = setup_spell(cards, second=False)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == 'p2:exile' and s.state.cards[b.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('gone', ['first', 'second', 'both'])
def test_departed_targets_do_not_invalidate_the_other_instruction(cards, gone):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, a, b = setup_spell(cards)
    departed = [a.id] if gone == 'first' else [b.id] if gone == 'second' else [a.id, b.id]
    act(s, 'p2', type='move', card_ids=departed, to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    if gone == 'first':
        d = s.state.rules.decision
        assert d
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
        settle(s)
        assert s.state.cards[b.id].zone == 'p2:exile'
    else:
        assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == ('p2:exile' if gone == 'second' else 'p2:graveyard')
    roundtrip(s)


def test_optional_target_must_differ_from_the_first_before_payment(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME], ['Sol Ring'])
    source = put(s, NAME, 'hand')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    mana(s, W=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[ring.id, ring.id], target_counts=[1, 1])
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.players['p1'].mana == {'W': 4}
    roundtrip(s)


@pytest.mark.parametrize('main', [False, True])
def test_cast_phase_is_remembered_when_resolution_phase_changes(cards, main):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, a, b = setup_spell(cards, 'main1' if main else 'begin_combat')
    act(s, 'p1', type='phase', to='end' if main else 'main1')
    # The first rules intent reconciles a manual phase change to active-player priority.
    act(s, 'p1', type='pass_priority')
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:exile'
    if main:
        d = s.state.rules.decision
        assert d
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
        settle(s)
    assert s.state.cards[b.id].zone == ('p2:exile' if main else 'p2:battlefield')
    roundtrip(s)


def test_spell_copy_was_not_cast_but_original_retains_main_phase_option(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, source, a, b = setup_spell(cards, hold=True)
    twincast = put(s, 'Twincast', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=twincast.id, targets=[source.id])
    settle(s)
    while (d := s.state.rules.decision) is not None and any(o.id == 'keep' for o in d.options):
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
        settle(s)
    d = s.state.rules.decision
    assert d and d.resume['ctx']['source_card'] == source.id
    assert s.state.cards[a.id].zone == 'p2:exile' and s.state.cards[b.id].zone == 'p2:battlefield'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[b.id].zone == 'p2:exile'
    roundtrip(s)
