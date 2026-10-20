"""CR 614.8: only the selected shield carries out its creating effect's rider."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/regeneration_rider_cards.json'
NAMES = ['Matopi Golem', 'Skeleton Scavengers', 'Soldevi Sentry', 'Debt of Loyalty']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='rgr', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name='Matopi Golem'):
    s = build(cards, [c['name'] for c in json.loads(DATA.read_text())])
    hold(s)
    if name == 'Skeleton Scavengers':
        source = put(s, name, 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 2})
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
    else:
        source = put(s, name, 'battlefield')
    return s, s.state.cards[source.id]


def activate(s, source, *, targets=(), mana=1):
    ab = next(a for a in Plan(s.state, source.controller, s.cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, source.controller, type='add_mana', player=source.controller, mana={'C': mana})
    act(s, source.controller, type='activate_ability', card_id=source.id, ability=ab.index, targets=list(targets))
    settle(s)


def cast(s, name, source):
    mana = {'Murder': {'B': 2, 'C': 1}, 'Debt of Loyalty': {'W': 2, 'C': 1}, 'Regenerate': {'G': 1, 'C': 1},
            'Hyena Umbra': {'W': 1}, 'Wrath of God': {'W': 2, 'C': 2}, 'Withstand Death': {'G': 1},
            'Day of Judgment': {'W': 2, 'C': 2}}[name]
    spell = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[] if name in ('Wrath of God', 'Day of Judgment') else [source.id])
    settle(s)
    return spell


def choose_shield(s, key):
    d = s.state.rules.decision
    assert d.resume['step'] == 'regeneration_replacement'
    candidates = s.state.rules.destruction_replacements['candidates'][d.resume['card']]
    option = next(str(i) for i, c in enumerate(candidates) if c['key'] == key)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_fully_supported(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('name,counter', [('Matopi Golem', '-1/-1'), ('Skeleton Scavengers', '+1/+1')])
def test_counter_rider_waits_for_its_shield_to_actually_regenerate(cards, name, counter):
    s, source = setup(cards, name)
    before = s.state.cards[source.id].counters.get(counter, 0)
    activate(s, source)
    assert s.state.cards[source.id].counters.get(counter, 0) == before
    assert len(s.state.rules.regeneration_riders) == 1
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters.get(counter, 0) == before + 1
    assert not s.state.rules.regeneration_riders and not s.state.rules.regen_shields
    roundtrip(s)


def test_debt_changes_control_only_when_its_shield_is_used(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Debt of Loyalty', source)
    assert s.state.cards[source.id].controller == 'p2'
    assert not s.state.cards[source.id].tapped
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].controller == 'p1' and s.state.cards[source.id].tapped
    assert not s.state.zones.get('stack') and not s.state.rules.pending_triggers
    roundtrip(s)


@pytest.mark.parametrize('selected', ['anonymous', 'rider'])
def test_controller_selects_between_a_debt_shield_and_an_unrelated_shield(cards, selected):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Debt of Loyalty', source)
    rider = s.state.rules.regeneration_riders[0].id
    cast(s, 'Regenerate', source)
    cast(s, 'Murder', source)
    assert s.state.rules.decision.player == 'p2'
    choose_shield(s, 'shield' if selected == 'anonymous' else 'rider:' + rider)
    assert s.state.cards[source.id].controller == ('p2' if selected == 'anonymous' else 'p1')
    assert len(s.state.rules.regeneration_riders) == (1 if selected == 'anonymous' else 0)
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].controller == 'p1'
    assert not s.state.rules.regeneration_riders and not s.state.rules.regen_shields
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_sentrys_delayed_trigger_offers_the_chosen_opponent_a_draw(cards, accept):
    s, source = setup(cards, 'Soldevi Sentry')
    before = len(s.state.zones['p2:hand'])
    activate(s, source, targets=['p2'])
    assert len(s.state.zones['p2:hand']) == before
    cast(s, 'Murder', source)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2', d
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay' if accept else 'decline'])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + int(accept)
    roundtrip(s)


def test_delayed_counter_rider_uses_stack_instead_of_happening_during_regeneration(cards):
    s, source = setup(cards)
    activate(s, source)
    spell = put(s, 'Murder', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    for _ in range(8):
        if s.state.cards[source.id].tapped:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].tapped and s.state.cards[source.id].counters.get('-1/-1', 0) == 0
    assert s.state.zones.get('stack')
    # The trigger exists independently of its source and follows only that old
    # object; the returning permanent is not the regenerated permanent.
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    settle(s)
    assert s.state.cards[source.id].counters.get('-1/-1', 0) == 0
    roundtrip(s)


def test_each_skeleton_activation_cost_counts_current_counters_and_rider_is_delayed(cards):
    from app.game.errors import ActionError

    s, source = setup(cards, 'Skeleton Scavengers')
    assert s.state.cards[source.id].counters['+1/+1'] == 1
    activate(s, source, mana=1)
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].counters['+1/+1'] == 2
    ab = next(a for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id]).abilities if a.kind == 'activated')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    with pytest.raises(ActionError, match='Not enough mana'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ab.index)
    activate(s, source, mana=1)  # The previous unspent one plus this one pays two.
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].counters['+1/+1'] == 3
    roundtrip(s)


def test_two_identical_rider_shields_are_consumed_once_each(cards):
    s, source = setup(cards)
    activate(s, source)
    activate(s, source)
    ids = [r.id for r in s.state.rules.regeneration_riders]
    cast(s, 'Murder', source)
    choose_shield(s, 'rider:' + ids[1])
    assert [r.id for r in s.state.rules.regeneration_riders] == ids[:1]
    assert s.state.cards[source.id].counters['-1/-1'] == 1
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].counters['-1/-1'] == 2
    assert not s.state.rules.regeneration_riders
    roundtrip(s)


def test_unselected_rider_shield_does_not_trigger_when_armor_is_used(cards):
    s, source = setup(cards)
    activate(s, source)
    aura = cast(s, 'Hyena Umbra', source)
    rider = s.state.rules.regeneration_riders[0].id
    cast(s, 'Murder', source)
    choose_shield(s, 'aura:' + s.state.rules.object_id(aura.id))
    assert s.state.cards[source.id].counters.get('-1/-1', 0) == 0
    assert [r.id for r in s.state.rules.regeneration_riders] == [rider]
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].counters['-1/-1'] == 1
    roundtrip(s)


def test_cannot_regenerate_never_uses_a_rider_shield(cards):
    s, source = setup(cards)
    activate(s, source)
    cast(s, 'Wrath of God', source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].counters.get('-1/-1', 0) == 0
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_a_blinked_permanent_cannot_use_its_old_rider_shield(cards):
    s, source = setup(cards)
    activate(s, source)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_sentry_keeps_original_chooser_after_source_control_changes(cards):
    s, source = setup(cards, 'Soldevi Sentry')
    activate(s, source, targets=['p2'])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Murder', source)
    assert s.state.rules.decision.player == 'p2'
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.cards[source.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('sba', [False, True])
def test_rider_shield_selection_and_delayed_trigger_resume_in_a_fresh_process(cards, tmp_path, sba):
    import subprocess
    import sys

    s, source = setup(cards)
    activate(s, source)
    rider = s.state.rules.regeneration_riders[0].id
    cast(s, 'Regenerate', source)
    if sba:
        act(s, 'p1', type='set_damage', card_ids=[source.id], value=4)
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        cast(s, 'Murder', source)
    d = s.state.rules.decision
    assert d.resume['step'] == 'regeneration_replacement'
    candidates = s.state.rules.destruction_replacements['candidates'][source.id]
    option = next(str(i) for i, c in enumerate(candidates) if c['key'] == 'rider:' + rider)
    roundtrip(s)
    saved = tmp_path / 'rider.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, option = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(12):
    if not s.state.zones.get('stack'):
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[source].zone == 'p1:battlefield' and s.state.cards[source].tapped
assert s.state.cards[source].counters['-1/-1'] == 1
assert not s.state.rules.regeneration_riders
assert s.state.rules.regen_shields[s.state.rules.object_id(source)] == 1
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, option],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_indestructibility_does_not_consume_debts_shield_or_change_control(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Debt of Loyalty', source)
    cast(s, 'Withstand Death', source)
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].controller == 'p2' and not s.state.cards[source.id].tapped
    assert len(s.state.rules.regeneration_riders) == 1
    roundtrip(s)


def test_unused_rider_shields_expire_at_cleanup(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    activate(s, source)
    to_phase(s, 'main1', turn=2)
    assert not s.state.rules.regeneration_riders and not s.state.rules.regen_shields
    roundtrip(s)


def test_native_counter_replacements_apply_to_a_delayed_regeneration_rider(cards):
    s, source = setup(cards, 'Skeleton Scavengers')
    put(s, 'Hardened Scales', 'battlefield')
    activate(s, source)
    cast(s, 'Murder', source)
    assert s.state.cards[source.id].counters['+1/+1'] == 3
    roundtrip(s)


def test_simultaneous_destruction_prepares_each_rider_before_any_are_consumed(cards):
    s, source = setup(cards)
    other = put(s, 'Soldevi Sentry', 'battlefield')
    activate(s, source)
    activate(s, other, targets=['p2'])
    ids = {r.object_id: r.id for r in s.state.rules.regeneration_riders}
    cast(s, 'Regenerate', source)
    cast(s, 'Regenerate', other)
    cast(s, 'Day of Judgment', None)
    for _ in range(2):
        d = s.state.rules.decision
        assert d.resume['step'] == 'regeneration_replacement'
        assert len(s.state.rules.regeneration_riders) == 2
        choose_shield(s, 'rider:' + ids[d.resume['object']])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' and s.state.cards[c.id].tapped for c in [source, other])
    assert s.state.cards[source.id].counters['-1/-1'] == 1
    assert not s.state.rules.regeneration_riders
    roundtrip(s)


def test_borrowed_regeneration_rider_protects_the_borrower_and_keeps_its_identity(cards):
    s, lender = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[lender.id], player='p2')
    borrower = put(s, 'Drana and Linvala', 'battlefield')
    activate(s, borrower)
    assert s.state.rules.regeneration_riders[0].object_id == s.state.rules.object_id(borrower.id)
    act(s, 'p2', type='move', card_ids=[lender.id], to={'zone': 'exile'})
    cast(s, 'Murder', borrower)
    assert s.state.cards[borrower.id].zone == 'p1:battlefield'
    assert s.state.cards[borrower.id].counters['-1/-1'] == 1
    roundtrip(s)


def test_old_saves_without_rider_field_keep_anonymous_shields(cards):
    from app.game.state import GameState

    s, source = setup(cards)
    cast(s, 'Regenerate', source)
    raw = s.state.model_dump(mode='json')
    del raw['rules']['regeneration_riders']
    restored = GameState.model_validate(raw)
    assert restored.rules.regeneration_riders == []
    assert restored.rules.regen_shields == s.state.rules.regen_shields
    assert restored == s.state


def test_borrowed_scavengers_cost_uses_borrowers_counter_count_including_zero(cards):
    from app.game.errors import ActionError

    s, lender = setup(cards, 'Skeleton Scavengers')
    act(s, 'p1', type='set_controller', card_ids=[lender.id], player='p2')
    borrower = put(s, 'Drana and Linvala', 'battlefield')
    ab = next(a for a in Plan(s.state, 'p1', s.cards, None).ch(borrower).abilities if a.kind == 'activated')
    with pytest.raises(ActionError, match="X is 0"):
        act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ab.index, x_value=1)
    act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ab.index)
    settle(s)
    assert len(s.state.rules.regeneration_riders) == 1
    cast(s, 'Murder', borrower)
    assert s.state.cards[borrower.id].counters['+1/+1'] == 1
    with pytest.raises(ActionError, match='Not enough mana'):
        act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ab.index)
    roundtrip(s)
