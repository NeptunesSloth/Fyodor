"""Chosen-player records are source-object keyed, not controller or display-name guesses."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, hand_size
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/keyed_player_bindings_cards.json'
NAMES = ['Sewer Nemesis', 'Sawhorn Nemesis', 'Triarch Stalker', "Beckoning Will-o'-Wisp", 'Cursed Rack']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='kpb', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ["Praetor's Counsel"]
    s = three(cards, names, names, names)
    hold(s)
    return s


def maximum(s, player='p1'):
    return hand_size.maximum(Plan(s.state, player, s.cards, None), player)


def sewer(s, player='p2'):
    put(s, 'Lightning Bolt', 'graveyard', player)
    c = spell(s, 'Sewer Nemesis', {'B': 1, 'C': 3})
    answer(s, [player])
    return s.state.cards[c.id]


def saw(s, player='p2'):
    c = spell(s, 'Sawhorn Nemesis', {'R': 1, 'C': 3})
    answer(s, [player])
    return s.state.cards[c.id]


def rack(s, player='p2'):
    c = spell(s, 'Cursed Rack', {'C': 4})
    answer(s, [player])
    return s.state.cards[c.id]


@pytest.mark.parametrize('name', NAMES)
def test_canonical_five_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_sewer_chosen_cast_player_mills_even_after_source_leaves(cards):
    s = setup(cards)
    source = sewer(s)
    growth = spell(s, 'Giant Growth', {'G': 1}, [source.id], player='p2', finish=False)
    before = len(s.state.zones['p2:library'])
    # The actual cast event queued its trigger already; its source is now removed.
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    settle(s)
    assert len(s.state.zones['p2:library']) == before - 1
    assert s.state.cards[growth.id].zone == 'p2:graveyard'
    # A different caster does not match the chosen player.
    other = len(s.state.zones['p2:library'])
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p3')
    assert len(s.state.zones['p2:library']) == other
    roundtrip(s)


def test_sewer_last_graveyard_card_cast_still_triggers_before_zero_toughness_sba(cards):
    s = setup(cards)
    twice = put(s, 'Think Twice', 'graveyard', 'p2')
    source = spell(s, 'Sewer Nemesis', {'B': 1, 'C': 3})
    answer(s, ['p2'])
    assert ch(s, source).pt == (1, 1)
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1, 'C': 2})
    before = len(s.state.zones['p2:library'])
    act(s, 'p2', type='cast_spell', card_id=twice.id)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    settle(s)
    assert len(s.state.zones['p2:library']) == before - 2  # One mill, one Think Twice draw.
    assert s.state.cards[twice.id].zone == 'p2:exile'
    roundtrip(s)


def test_sawhorn_only_chosen_player_and_currently_controlled_permanents(cards):
    s = setup(cards)
    saw(s)
    spell(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 34
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p3')
    assert s.state.players['p3'].life == 37
    mine = put(s, 'Giant Spider', 'battlefield')
    theirs = put(s, 'Giant Spider', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[mine.id], player='p2')
    act(s, 'p1', type='set_controller', card_ids=[theirs.id], player='p3')
    spell(s, 'Lightning Bolt', {'R': 1}, [mine.id], player='p2')
    assert s.state.cards[mine.id].zone == 'p1:graveyard'
    spell(s, 'Lightning Bolt', {'R': 1}, [theirs.id], player='p1')
    assert s.state.cards[theirs.id].zone == 'p3:battlefield' and s.state.cards[theirs.id].damage == 3
    roundtrip(s)


@pytest.mark.parametrize('name,keyword,pt', [('Triarch Stalker', 'menace', (2, 2)), ("Beckoning Will-o'-Wisp", None, (3, 2))])
def test_native_combat_choice_updates_attacking_player_qualifier(cards, name, keyword, pt):
    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    source = put(s, name, 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p1')
    stops(s, 'main1', 'begin_combat', 'declare_attackers', 'declare_blockers')
    to_phase(s, 'begin_combat')
    settle(s)
    answer(s, ['p2'])
    assert s.state.cards[source.id].choices['Chosen opponent'] == s.state.players['p2'].name
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': first.id, 'target': 'p2'}, {'card_id': second.id, 'target': 'p3'}])
    assert ch(s, first).pt == pt
    assert ch(s, second).pt == (2, 2)
    if keyword:
        assert keyword in ch(s, first).keywords and keyword not in ch(s, second).keywords
    roundtrip(s)


def test_rack_chosen_player_fixed_limit_and_source_controller_change(cards):
    s = setup(cards)
    source = rack(s)
    assert maximum(s, 'p2') == 4 and maximum(s, 'p1') == 7 and maximum(s, 'p3') == 7
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    assert maximum(s, 'p2') == 4 and maximum(s, 'p3') == 7
    roundtrip(s)


@pytest.mark.parametrize('tower_last', [True, False])
def test_fixed_limit_and_no_maximum_follow_permanent_timestamp_order(cards, tower_last):
    s = setup(cards)
    if tower_last:
        put(s, 'Null Profusion', 'battlefield')
        put(s, 'Reliquary Tower', 'battlefield')
    else:
        put(s, 'Reliquary Tower', 'battlefield')
        put(s, 'Null Profusion', 'battlefield')
    assert maximum(s) == (None if tower_last else 2)
    roundtrip(s)


def test_resolved_counsel_and_later_set_then_repeated_counsel_have_fresh_timestamps(cards):
    s = setup(cards)
    spell(s, "Praetor's Counsel", {'G': 3, 'C': 5})
    assert maximum(s) is None and 'p1' in s.state.rules.no_max_hand_at
    put(s, 'Null Profusion', 'battlefield')
    assert maximum(s) == 2
    original = s.state.rules.no_max_hand_at['p1']
    spell(s, "Praetor's Counsel", {'G': 3, 'C': 5})
    assert s.state.rules.no_max_hand_at['p1'] > original and maximum(s) is None
    roundtrip(s)


@pytest.mark.parametrize('rack_last', [True, False])
def test_rack_and_no_maximum_follow_actual_source_order(cards, rack_last):
    s = setup(cards)
    if rack_last:
        put(s, 'Reliquary Tower', 'battlefield', 'p2')
        rack(s)
    else:
        rack(s)
        put(s, 'Reliquary Tower', 'battlefield', 'p2')
    assert maximum(s, 'p2') == (4 if rack_last else None)
    roundtrip(s)


def test_no_maximum_ignores_later_deltas_but_fixed_limit_then_delta_is_finite(cards):
    s = setup(cards)
    put(s, 'Reliquary Tower', 'battlefield')
    put(s, 'Gnat Miser', 'battlefield', 'p2')
    put(s, 'Trusted Advisor', 'battlefield')
    assert maximum(s) is None
    put(s, 'Null Profusion', 'battlefield')
    assert maximum(s) == 2
    # A later delta applies after the setting, rather than moving before it.
    other = put(s, 'Trusted Advisor', 'battlefield', 'p2')
    act(s, 'p2', type='set_controller', card_ids=[other.id], player='p1')
    assert maximum(s) == 4
    roundtrip(s)


def test_chosen_rack_limit_drives_native_cleanup(cards):
    s = setup(cards)
    rack(s)
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='move', card_ids=s.state.zones['p2:library'][:9], to={'zone': 'hand'})
    to_phase(s, 'main1', turn=3)
    assert len(s.state.zones['p2:hand']) == 4
    roundtrip(s)


def test_legacy_no_maximum_keeps_uncertain_order_but_later_native_setting_wins(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    put(s, 'Null Profusion', 'battlefield')
    raw = s.state.model_dump(mode='json')
    raw['rules']['no_max_hand'] = ['p1']
    raw['rules'].pop('no_max_hand_at')
    raw['rules'].pop('no_max_hand_legacy_bound')
    s = GameSession(GameState.model_validate(raw), cards=cards)
    before = s.state.model_dump_json()
    assert maximum(s) is None
    assert s.state.model_dump_json() == before  # Queries do not invent history.
    act(s, 'p1', type='pass_priority')
    assert 'p1' in s.state.rules.no_max_hand_legacy_bound
    assert maximum(s) is None
    plan = Plan(s.state, 'p1', cards, None)
    assert hand_size.maximum(plan, 'p1', warn_legacy=True) is None
    assert any('untimestamped' in str(a) for a in plan.steps)
    to_phase(s, 'main1', turn=2)
    source = spell(s, 'Cursed Rack', {'C': 4}, player='p2')
    answer(s, ['p1'])
    assert s.state.cards[source.id].zone == 'p2:battlefield'
    assert maximum(s) == 4
    roundtrip(s)


def test_remembered_combat_choice_cold_resume_uses_player_id(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, 'Triarch Stalker', 'battlefield')
    stops(s, 'main1', 'begin_combat')
    to_phase(s, 'begin_combat')
    settle(s)
    assert s.state.rules.decision is not None
    path = tmp_path / 'combat-opponent.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import chosen
from app.rules.plan import Plan
path, database, source = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['p3']})
for _ in range(12):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('combat choice did not resolve')
assert chosen.player_of(Plan(s.state, 'p1', repo, None), source) == 'p3'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', ['Triarch Stalker', "Beckoning Will-o'-Wisp"])
def test_departed_pending_combat_choice_does_not_bind_new_incarnation(cards, name):
    from app.rules import chosen

    s = setup(cards)
    source = put(s, name, 'battlefield')
    stops(s, 'main1', 'begin_combat', 'declare_attackers')
    to_phase(s, 'begin_combat')
    settle(s)
    assert s.state.rules.decision is not None
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    answer(s, ['p2'])
    assert chosen.player_of(Plan(s.state, 'p1', cards, None), source.id) is None
    roundtrip(s)


def test_later_combat_choice_replaces_earlier_player_without_accumulating(cards):
    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    source = put(s, "Beckoning Will-o'-Wisp", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    stops(s, 'main1', 'begin_combat', 'declare_attackers')
    to_phase(s, 'begin_combat')
    settle(s)
    answer(s, ['p2'])
    to_phase(s, 'main1', turn=4)
    to_phase(s, 'begin_combat', turn=4)
    settle(s)
    answer(s, ['p3'])
    assert s.state.cards[source.id].choices['Chosen opponent'] == s.state.players['p3'].name
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    assert ch(s, bear).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('name,mana', [('Cursed Rack', {'C': 4}), ('Sawhorn Nemesis', {'R': 1, 'C': 3})])
def test_reentry_replaces_source_choice_instead_of_inheriting_old_player(cards, name, mana):
    from app.rules import chosen

    s = setup(cards)
    source = spell(s, name, mana)
    answer(s, ['p2'])
    old = Plan(s.state, 'p1', cards, None).oid(s.state.cards[source.id])
    if name == 'Cursed Rack':
        act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
        spell(s, name, mana)
    else:
        spell(s, 'Flicker of Fate', {'W': 1, 'C': 1}, [source.id])
    answer(s, ['p3'])
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.oid(s.state.cards[source.id]) != old
    assert chosen.player_of(plan, source.id) == 'p3'
    assert chosen.player_of(plan, source.id, old) == 'p2'  # Old-object LKI remains distinct.
    if name == 'Cursed Rack':
        assert maximum(s, 'p2') == 7 and maximum(s, 'p3') == 4
    else:
        spell(s, 'Lightning Bolt', {'R': 1}, ['p2'])
        spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p3')
        assert s.state.players['p2'].life == 37 and s.state.players['p3'].life == 34
    roundtrip(s)


def test_sawhorn_doubles_damage_to_chosen_players_planeswalker(cards):
    s = setup(cards)
    saw(s)
    walker = put(s, 'Karn Liberated', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=walker.id, kind='loyalty', value=7)
    spell(s, 'Lightning Bolt', {'R': 1}, [walker.id])
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    roundtrip(s)


def test_copied_rack_chooses_independently_and_both_sources_apply(cards):
    from app.rules import chosen

    s = setup(cards)
    original = rack(s)
    copied = spell(s, 'Clever Impersonator', {'U': 2, 'C': 2})
    answer(s, [original.id])
    answer(s, ['p3'])
    plan = Plan(s.state, 'p1', cards, None)
    assert chosen.player_of(plan, original.id) == 'p2'
    assert chosen.player_of(plan, copied.id) == 'p3'
    assert maximum(s, 'p2') == maximum(s, 'p3') == 4
    act(s, 'p1', type='move', card_ids=[original.id], to={'zone': 'exile'})
    assert maximum(s, 'p2') == 7 and maximum(s, 'p3') == 4
    roundtrip(s)


@pytest.mark.parametrize('name', ['Triarch Stalker', "Beckoning Will-o'-Wisp"])
def test_attacking_chosen_players_planeswalker_does_not_count_as_attacking_player(cards, name):
    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    walker = put(s, 'Karn Liberated', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=walker.id, kind='loyalty', value=7)
    stops(s, 'main1', 'begin_combat', 'declare_attackers')
    to_phase(s, 'begin_combat')
    settle(s)
    answer(s, ['p2'])
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': walker.id}])
    assert ch(s, bear).pt == (2, 2) and 'menace' not in ch(s, bear).keywords
    roundtrip(s)


def test_chosen_hand_limit_cleanup_choice_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    rack(s)
    to_phase(s, 'main1', turn=2)
    need = 9 - len(s.state.zones['p2:hand'])
    act(s, 'p2', type='move', card_ids=s.state.zones['p2:library'][:need], to={'zone': 'hand'})
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None and d.resume.get('step') == 'cleanup_discard':
            break
        if d is not None:
            assert d.kind == 'declare_attackers'
            act(s, d.player, type='declare_attackers', attackers=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('cleanup discard choice never appeared')
    assert d.player == 'p2' and d.min_choices == d.max_choices == 5
    path = tmp_path / 'rack-cleanup.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import hand_size
from app.rules.plan import Plan
path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
assert hand_size.maximum(Plan(s.state, 'p2', repo, None), 'p2') == 4
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o.id for o in d.options][:5]})
assert len(s.state.zones['p2:hand']) == 4
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
