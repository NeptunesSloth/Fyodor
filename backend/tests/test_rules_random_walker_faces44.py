"""Production native gameplay for every line of Ral's two faces."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_coin_outcomes import faces
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_native_outcomes42 import DATA
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

NAME = 'Ral, Monsoon Mage // Ral, Leyline Prodigy'
ROWS = json.loads((Path(__file__).parent / 'fixtures/random_walker_faces44_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate([*DATA, *ROWS]):
        base[c['name']] = card(c['name'], set_code='r44', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [r['name'] for r in [*DATA, *ROWS]] + ['Grizzly Bears', 'Lightning Bolt', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    return s


def test_front_cost_reduction_applies_on_opponent_turn_without_coin_trigger(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=2)
    faces(monkeypatch, [])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})  # Real 2U reduced to 1U during Bob's turn.
    assert s.state.players['p1'].life == 40
    assert s.state.cards[source.id].face == 0
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('won', [False, True])
def test_actual_front_coin_loss_or_optional_transformed_entry_has_cast_history_loyalty(cards, monkeypatch, won):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [int(won)])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    if won:
        assert s.state.rules.decision is not None
        answer(s, ['pay'])
        settle(s)
        assert s.state.cards[source.id].face == 1
        assert s.state.cards[source.id].counters.get('loyalty') == 3  # Base2 plus the real spell still on stack.
        assert s.state.players['p1'].life == 40
    else:
        assert s.state.cards[source.id].face == 0
        assert s.state.players['p1'].life == 39
    roundtrip(s)


def test_winning_front_trigger_can_decline_exile_and_stay_front(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['decline'])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].face == 0
    assert not s.state.cards[source.id].counters
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('response', ['Beast Within', 'Flicker of Fate'])
@pytest.mark.parametrize('won', [False, True])
def test_original_front_trigger_survives_departure_but_never_exiles_new_source(cards, monkeypatch, response, won):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    old_oid = s.state.rules.object_id(source.id)
    faces(monkeypatch, [int(won)])
    spell(s, 'Lightning Bolt', {'R': 1}, target=['p3'], finish=False)
    spell(s, response, {'C': 2, 'G': 1} if response == 'Beast Within' else {'C': 1, 'W': 1},
          target=[source.id], player='p2')
    if s.state.rules.decision is not None:
        answer(s, ['decline'])
    settle(s)
    assert s.state.rules.object_id(source.id) != old_oid
    assert s.state.cards[source.id].zone == ('p1:graveyard' if response == 'Beast Within' else 'p1:battlefield')
    assert s.state.cards[source.id].face == 0
    assert s.state.players['p1'].life == (40 if won else 39)
    assert s.state.players['p3'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('blue', [False, True])
def test_actual_divided_damage_then_draw_requires_another_current_blue_permanent(cards, monkeypatch, blue):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    if blue:
        put(s, 'Notion Thief', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        targets=['p2', 'p3'], target_counts=[2], division=[1, 1])
    settle(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 39
    assert len(s.state.zones['p1:hand']) == before + int(blue)
    assert s.state.cards[source.id].counters['loyalty'] == 1
    roundtrip(s)


def test_back_entry_counts_real_countered_spell_and_current_spell_still_on_stack(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    first = spell(s, 'Quick Study', {'C': 2, 'U': 1}, finish=False)
    spell(s, 'Counterspell', {'U': 2}, target=[first.id], player='p2')
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Lightning Bolt', {'R': 1}, target=['p2'])
    answer(s, ['pay'])
    assert s.state.cards[source.id].face == 1
    assert s.state.cards[source.id].counters['loyalty'] == 4
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def new_blue_source_before_old_ability(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    kitten = put(s, 'Displacer Kitten', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'], target_counts=[1])
    before = len(s.state.zones['p1:hand'])
    old_oid = s.state.rules.object_id(source.id)
    spell(s, 'Beast Within', {'C': 2, 'G': 1}, target=[kitten.id], finish=False)
    # Kitten blinks Ral before Beast Within destroys Kitten. Keep the old -2 pending.
    for _ in range(30):
        decision = s.state.rules.decision
        if decision is not None:
            options = [o.id for o in decision.options]
            chosen = options if decision.kind == 'order' else [source.id]
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=chosen)
        elif len(s.state.zones.get('stack', [])) > 1:
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            break
    assert s.state.cards[kitten.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].face == 0
    assert s.state.rules.object_id(source.id) != old_oid
    assert len(s.state.zones['stack']) == 1
    # The returned front wins a new flip, becoming the only blue permanent in play.
    faces(monkeypatch, [1])
    spell(s, 'Lightning Bolt', {'R': 1}, target=['p3'])
    decision = s.state.rules.decision
    act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['pay'])
    for _ in range(20):
        if len(s.state.zones.get('stack', [])) <= 1:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].face == 1
    assert s.state.rules.object_id(source.id) != old_oid
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 37
    assert len(s.state.zones['stack']) == 1
    return s, source, before


def test_old_divided_damage_counts_new_blue_ral_incarnation_as_another_permanent(cards, monkeypatch):
    s, source, before = new_blue_source_before_old_ability(cards, monkeypatch)
    settle(s)
    assert s.state.players['p2'].life == 38
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_plus_one_reduction_persists_through_opponent_turn_and_expires_at_next_own_turn(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.cards[source.id].counters['loyalty'] == 4
    for turn, generic in [(1, 1), (2, 1), (4, 2)]:
        if turn != 1:
            to_phase(s, 'main1', turn=turn)
        study = spell(s, 'Quick Study', {'C': generic, 'U': 1}, finish=False)
        paid = s.state.rules.payments[s.state.rules.object_id(study.id)]
        assert paid.mana_spent == {'C': generic, 'U': 1}
        settle(s)
    assert s.state.cards[source.id].face == 1
    roundtrip(s)


def ultimate_ready(s, monkeypatch):
    from tests.test_rules_random_consequences import answer

    # Five real casts before Ral arrives, then the sixth cast causes the winning entry.
    for _ in range(5):
        spell(s, 'Quick Study', {'C': 2, 'U': 1})
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Lightning Bolt', {'R': 1}, target=['p2'])
    answer(s, ['pay'])
    assert s.state.cards[source.id].counters['loyalty'] == 8
    names = ['Reap the Past', 'Lightning Bolt', 'Quick Study', 'Grave Endeavor',
             'Neverwinter Hydra', 'Grizzly Bears', 'Forest', 'The Deck of Many Things']
    chosen = {}
    for name in reversed(names):
        card = put(s, name, 'library')
        act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p1', 'zone': 'library'}, position='top')
        chosen[name] = card
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in chosen.values())
    return source, chosen


def test_actual_six_casts_enable_eight_loyalty_ultimate_grants_only_normal_timing_free_instants_sorceries_until_eot(cards, monkeypatch):
    from app.game.errors import ActionError
    from app.rules.mana_units import visible_pool

    s = setup(cards)
    _, chosen = ultimate_ready(s, monkeypatch)
    assert visible_pool(s.state, 'p1') == {}
    for name in ['Neverwinter Hydra', 'Grizzly Bears']:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=chosen[name].id, free=True)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=chosen['Forest'].id)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=chosen['Reap the Past'].id, free=True, x_value=1)
    act(s, 'p1', type='cast_spell', card_id=chosen['Reap the Past'].id, free=True, x_value=0)
    settle(s)
    act(s, 'p1', type='cast_spell', card_id=chosen['Lightning Bolt'].id, free=True, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 34
    assert visible_pool(s.state, 'p1') == {}
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=chosen['Quick Study'].id, free=True)
    roundtrip(s)


@pytest.mark.parametrize('change', ['other_colorless', 'other_stolen', 'source_colorless', 'source_destroyed'])
def test_divided_damage_draw_checks_current_blue_objects_controller_and_old_source_oid(cards, monkeypatch, change):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    other = put(s, 'Notion Thief', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'], target_counts=[1])
    before = sum(s.state.rules.turn_log.drew.values())
    if change == 'other_stolen':
        spell(s, 'Act of Aggression', {'C': 3, 'R': 2}, target=[other.id], player='p2', life_symbols=[])
        assert s.state.cards[other.id].controller == 'p2'
    elif change == 'source_destroyed':
        spell(s, 'Beast Within', {'C': 2, 'G': 1}, target=[source.id], player='p2')
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    else:
        spell(s, 'Moonlace', {'U': 1}, target=[other.id if change == 'other_colorless' else source.id], player='p2')
    settle(s)
    expected = int(change in {'source_colorless', 'source_destroyed'})
    assert sum(s.state.rules.turn_log.drew.values()) == before + expected
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_native_copied_divided_ability_checks_its_own_controller_independently(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    put(s, 'Notion Thief', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p3'], target_counts=[1])
    original = s.state.zones['stack'][-1]
    before = sum(s.state.rules.turn_log.drew.values())
    spell(s, 'Return the Favor', {'C': 1, 'R': 2}, target=[original], player='p2', modes=[0])
    if s.state.rules.decision is not None:
        decision = s.state.rules.decision
        answer(s, ['keep'] if any(o.id == 'keep' for o in decision.options) else ['p3'])
    settle(s)
    assert sum(s.state.rules.turn_log.drew.values()) == before + 1
    assert s.state.players['p3'].life == 36
    assert s.state.cards[source.id].counters['loyalty'] == 1
    roundtrip(s)


def test_single_faced_clone_can_pay_exile_but_cannot_return_transformed(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    original = put(s, NAME, 'battlefield')
    clone = spell(s, 'Clone', {'C': 3, 'U': 1})
    for _ in range(5):
        decision = s.state.rules.decision
        if decision is None:
            break
        options = [o.id for o in decision.options]
        selected = original.id if original.id in options and clone.id not in options else clone.id
        answer(s, [selected])
    assert s.state.cards[original.id].zone == 'p1:graveyard'
    assert s.state.cards[clone.id].zone == 'p1:battlefield'
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    assert s.state.cards[clone.id].zone == 'p1:exile'
    assert not s.state.cards[clone.id].counters
    roundtrip(s)


@pytest.mark.parametrize('all_illegal', [False, True])
def test_partial_or_all_divided_targets_blinked_do_not_reassign_damage_or_invent_draw(cards, monkeypatch, all_illegal):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1})
    answer(s, ['pay'])
    put(s, 'Notion Thief', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    myr = put(s, 'Darksteel Myr', 'battlefield', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        targets=[bear.id, myr.id], target_counts=[2], division=[1, 1])
    before = sum(s.state.rules.turn_log.drew.values())
    if all_illegal:
        spell(s, 'Ghostly Flicker', {'C': 2, 'U': 1}, target=[bear.id, myr.id], player='p2', target_counts=[2])
    else:
        spell(s, 'Cloudshift', {'W': 1}, target=[bear.id], player='p2')
    settle(s)
    assert s.state.cards[bear.id].damage == 0
    assert s.state.cards[myr.id].damage == int(not all_illegal)
    assert sum(s.state.rules.turn_log.drew.values()) == before + int(not all_illegal)
    roundtrip(s)


def test_two_pending_front_triggers_flip_independently_without_exiling_new_back_object(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    faces(monkeypatch, [1, 1])
    spell(s, 'Quick Study', {'C': 1, 'U': 1}, finish=False)
    spell(s, 'Lightning Bolt', {'R': 1}, target=['p3'], finish=False)
    settle(s)
    answer(s, ['pay'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].face == 1
    assert s.state.cards[source.id].counters['loyalty'] == 4
    assert s.state.players['p1'].life == 40
    assert s.state.players['p3'].life == 37
    assert len([entry for entry in s.state.log if any('flipped a coin:' in (part.t or '') for part in entry.parts)]) == 2
    roundtrip(s)


@pytest.mark.parametrize('stage', ['winning_payment', 'old_source_new_blue', 'ultimate_permission'])
def test_fresh_process_retains_coin_payment_original_source_oid_or_free_permission(cards, monkeypatch, tmp_path, stage):
    import subprocess
    import sys

    if stage == 'old_source_new_blue':
        s, source, before = new_blue_source_before_old_ability(cards, monkeypatch)
        cid = source.id
    else:
        s = setup(cards)
        if stage == 'ultimate_permission':
            source, chosen = ultimate_ready(s, monkeypatch)
            cid = chosen['Quick Study'].id
        else:
            source = put(s, NAME, 'battlefield')
            faces(monkeypatch, [1])
            spell(s, 'Quick Study', {'C': 1, 'U': 1})
            assert s.state.rules.decision is not None
            cid = source.id
        before = len(s.state.zones['p1:hand'])
    path = tmp_path / (stage + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,stage,sid,cid,before=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('coin rerolled'))
if stage=='winning_payment':
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
elif stage=='ultimate_permission':
 s.perform('p1',{'type':'cast_spell','card_id':cid,'free':True})
for _ in range(40):
 assert s.state.rules.decision is None
 if not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert len(s.state.zones['p1:hand'])==int(before)+(1 if stage=='old_source_new_blue' else 2)
if stage=='winning_payment':
 assert s.state.cards[sid].face==1 and s.state.cards[sid].counters['loyalty']==3
elif stage=='old_source_new_blue':
 assert s.state.cards[sid].face==1 and s.state.cards[sid].counters['loyalty']==5
 assert s.state.players['p2'].life==38
else:
 assert s.state.cards[sid].zone=='p1:graveyard'
 assert s.state.cards[cid].zone=='p1:graveyard'
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), stage, source.id, cid, str(before)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_whole_printed_both_face_gate(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result
