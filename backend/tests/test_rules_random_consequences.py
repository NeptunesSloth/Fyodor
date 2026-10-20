"""Actual replacement-aware coin groups preserve public outcomes and saved continuations."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/random_consequences_cards.json').read_text())
    existing = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(data):
        existing[c['name']] = card(c['name'], set_code='coi', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/random_consequences_cards.json').read_text())]
    names += ['Sol Ring', 'Lightning Bolt']
    s = three(cards, names, names, names)
    hold(s)
    return s


def faces(monkeypatch, values):
    values = iter(values)
    monkeypatch.setattr('app.game.resolve._rng_int', lambda rng, lo, hi: next(values))


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def saucer(s):
    source = put(s, 'The Gold Saucer', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    settle(s)



def test_luck_actual_even_results_create_tapped_treasures(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Luck Bobblehead', 'battlefield')
    faces(monkeypatch, [2])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']
    assert len(treasures) == 1 and treasures[0].tapped
    roundtrip(s)


def test_valiant_actual_pair_choice_destroys_then_creates_other_result(cards, monkeypatch):
    s = setup(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [2, 4])
    spell(s, 'Valiant Endeavor', {'W': 2, 'C': 4})
    assert s.state.rules.decision.resume['step'] == 'roll_choose'
    answer(s, ['0'])
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    knights = [c for c in s.state.cards.values() if c.name == 'Knight' and c.zone == 'p1:battlefield']
    assert len(knights) == 4
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_impulsive_actual_attack_next_damage_double_or_prevent(cards, monkeypatch, heads):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, 'Impulsive Maneuvers', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    faces(monkeypatch, [int(heads)])
    attack_ready(s, attacker)
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (36 if heads else 40)
    roundtrip(s)


def test_psychopath_actual_attack_loss_redirects_to_original_controller(cards, monkeypatch):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    attacker = put(s, 'Goblin Psychopath', 'battlefield')
    faces(monkeypatch, [0])
    attack_ready(s, attacker)
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p1'].life == 35
    assert s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 2, 3, 4, 5, 6])
def test_six_sided_actual_closed_branches(cards, monkeypatch, result):
    from app.rules.plan import Plan

    s = setup(cards)
    victim = put(s, 'Rakdos, the Showstopper', 'battlefield', 'p2')
    faces(monkeypatch, [result])
    spell(s, 'Six-Sided Die', {'B': 1, 'C': 5}, [victim.id])
    current = s.state.cards[victim.id]
    if result == 1:
        assert Plan(s.state, 'p1', cards, None).ch(current).pt[1] == 1
    elif result == 2:
        assert current.counters.get('-1/-1') == 2
    elif result == 3:
        assert current.damage == 3 and s.state.players['p1'].life == 43
    elif result == 4:
        assert Plan(s.state, 'p1', cards, None).ch(current).pt == (2, 2)
    else:
        assert current.zone == ('p2:graveyard' if result == 5 else 'p2:exile')
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 10, 20])
def test_cone_actual_taps_and_freezes_only_resolution_creatures(cards, monkeypatch, result):
    s = setup(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [result])
    spell(s, 'Cone of Cold', {'U': 1, 'C': 3})
    assert s.state.cards[victim.id].tapped
    records = [r for r in s.state.rules.stay_tapped if r.get('oid') == s.state.rules.object_id(victim.id)]
    assert bool(records) == (result >= 10)
    assert bool([r for r in s.state.rules.replacements if r.get('event') == 'enters_tapped']) == (result == 20)
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_song_actual_target_mana_value_modifier_and_high_life(cards, monkeypatch, result):
    s = setup(cards)
    victim = put(s, 'Grizzly Bears', 'graveyard')
    faces(monkeypatch, [result])
    spell(s, 'Song of Inspiration', {'G': 2, 'C': 3}, [victim.id], target_counts=[1])
    assert s.state.cards[victim.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == (42 if result == 20 else 40)
    roundtrip(s)



@pytest.mark.parametrize('result', [1, 10])
def test_acrobatics_actual_owner_returns_and_high_double_zone_change(cards, monkeypatch, result):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    stops(s, 'end')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    original = s.state.rules.object_id(victim.id)
    faces(monkeypatch, [result])
    spell(s, "Lae'zel's Acrobatics", {'W': 1, 'C': 3})
    assert s.state.cards[victim.id].zone == 'p1:exile'
    after = s.state.rules.object_id(victim.id)
    assert after != original
    departures = [e for e in s.state.rules.turn_log.left if e.card == victim.id]
    assert len(departures) == (2 if result == 10 else 1)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_aberrant_actual_optional_top_or_hand(cards, monkeypatch, result):
    s = setup(cards)
    victim = put(s, 'Six-Sided Die', 'graveyard')
    faces(monkeypatch, [result])
    spell(s, 'Aberrant Mind Sorcerer', {'U': 1, 'C': 4})
    if s.state.rules.decision and s.state.rules.decision.resume['step'] in ('trigger_target', 'trigger_targets'):
        answer(s, [victim.id])
    if result == 1:
        assert s.state.rules.decision.resume['step'] == 'random_optional_top'
        answer(s, ['yes'])
        assert s.state.cards[victim.id].zone == 'p1:library'
        assert s.state.zones['p1:library'][0] == victim.id
    else:
        assert s.state.cards[victim.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_revivify_actual_battlefield_arrival_and_modifier(cards, monkeypatch, result):
    s = setup(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield')
    faces(monkeypatch, [5, result])
    spell(s, 'Six-Sided Die', {'B': 1, 'C': 5}, [victim.id])
    spell(s, 'Revivify', {'W': 1, 'C': 2})
    assert s.state.cards[victim.id].zone == ('p1:hand' if result == 1 else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_danse_actual_simultaneous_sacrifice_then_choose_current_graveyard_cards(cards, monkeypatch, result):
    s = setup(cards)
    victims = [put(s, 'Grizzly Bears', 'battlefield', p) for p in ('p1', 'p2', 'p3')]
    faces(monkeypatch, [result])
    spell(s, 'Danse Macabre', {'B': 2, 'C': 3})
    assert all(s.state.cards[v.id].zone.endswith(':graveyard') for v in victims)
    answer(s, [victims[1].id] if result == 1 else [v.id for v in victims[:2]])
    assert s.state.cards[victims[1].id].zone == 'p1:battlefield'
    assert sum(s.state.cards[v.id].zone.endswith(':battlefield') for v in victims) == (1 if result == 1 else 2)
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 10, 20])
def test_thunder_actual_closed_damage_or_untargeted_exception(cards, monkeypatch, result):
    s = setup(cards)
    own = put(s, 'Rakdos, the Showstopper', 'battlefield')
    other = put(s, 'Mutalith Vortex Beast', 'battlefield', 'p2')
    faces(monkeypatch, [result])
    spell(s, 'Thunderwave', {'R': 2, 'C': 2})
    if result == 10:
        answer(s, [own.id])
    assert s.state.cards[own.id].damage == (3 if result == 1 else 0)
    if result == 20:
        assert s.state.cards[other.id].zone == 'p2:graveyard'
    else:
        assert s.state.cards[other.id].damage == 3
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 10, 20])
def test_mastiff_actual_attack_result_damage(cards, monkeypatch, result):
    from tests.test_rules_coin_outcomes import attack_ready

    s = setup(cards)
    source = put(s, 'Iron Mastiff', 'battlefield')
    faces(monkeypatch, [result])
    attack_ready(s, source)
    assert s.state.players['p1'].life == (36 if result == 1 else 40)
    assert s.state.players['p2'].life == (40 if result == 1 else 36)
    assert s.state.players['p3'].life == (36 if result == 20 else 40)
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_wyll_actual_retarget_then_copy_under_our_controller(cards, monkeypatch, result):
    s = setup(cards)
    original = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2', finish=False)
    faces(monkeypatch, [result])
    spell(s, "Wyll's Reversal", {'R': 1, 'C': 2}, [original.id])
    assert s.state.rules.decision.resume['step'] == 'choose_new_targets'
    answer(s, ['keep'])
    if result == 20:
        assert s.state.rules.decision is not None
        # Native copied-spell retargeter keeps its original target.
        while s.state.rules.decision:
            d = s.state.rules.decision
            ids = [o.id for o in d.options]
            answer(s, ['keep' if 'keep' in ids else 'no' if 'no' in ids else ids[0]])
    assert s.state.players['p3'].life == (34 if result == 20 else 37)
    roundtrip(s)


@pytest.mark.parametrize('heads', [False, True])
def test_artisans_actual_artifact_spell_target_draw_or_counter(cards, monkeypatch, heads):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    artisan = put(s, 'Goblin Artisans', 'battlefield')
    stops(s, 'main1')
    to_phase(s, 'main1', turn=4)
    hold(s)
    original = spell(s, 'Sol Ring', {'C': 1}, finish=False)
    before = len(s.state.zones['p1:hand'])
    faces(monkeypatch, [int(heads)])
    priority(s, 'p1')
    assert s.state.cards[original.id].zone == 'stack', (s.state.cards[original.id].zone, s.state.rules.priority)
    act(s, 'p1', type='activate_ability', card_id=artisan.id, ability=0, targets=[original.id])
    settle(s)
    assert s.state.cards[original.id].zone == ('p1:battlefield' if heads else 'p1:graveyard')
    assert len(s.state.zones['p1:hand']) == before + int(heads)
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 20])
def test_gale_actual_exile_receipt_paid_any_color_or_free_cast(cards, monkeypatch, result):
    s = setup(cards)
    original = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2', finish=False)
    faces(monkeypatch, [result])
    spell(s, "Gale's Redirection", {'U': 2, 'C': 3}, [original.id])
    assert s.state.cards[original.id].zone == 'p2:exile'
    priority(s, 'p1')
    if result == 1:
        act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='cast_spell', card_id=original.id, targets=['p3'], free=result == 20)
    settle(s)
    assert s.state.players['p3'].life == 37
    assert s.state.cards[original.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_risky_actual_upkeep_gain_control_from_other_player_then_loss_transfer(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    source = put(s, 'Risky Move', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [0])
    stops(s, 'upkeep')
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[source.id].controller == 'p2'
    assert s.state.rules.decision.player == 'p2'
    answer(s, ['p3'])
    assert s.state.cards[victim.id].controller == 'p3'
    roundtrip(s)


@pytest.mark.parametrize('heads', [False, True])
def test_plasma_actual_energy_payment_and_original_host_constraint(cards, monkeypatch, heads):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    equipment = put(s, 'Plasma Caster', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=host.id)
    attack_ready(s, host)
    assert s.state.players['p1'].resources.get('energy') == 2
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': host.id}])
    priority(s, 'p1')
    faces(monkeypatch, [int(heads)])
    act(s, 'p1', type='activate_ability', card_id=equipment.id, ability=2, targets=[blocker.id])
    assert s.state.players['p1'].resources.get('energy', 0) == 0
    # Official ruling: moving the Equipment doesn't rebind the original host.
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=blocker.id)
    settle(s)
    assert s.state.cards[blocker.id].zone == ('p2:exile' if heads else 'p2:battlefield')
    if not heads:
        assert s.state.cards[blocker.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize('heads', [False, True])
def test_desperate_actual_untargeted_stack_source_and_whole_next_damage(cards, monkeypatch, heads):
    s = setup(cards)
    original = spell(s, 'Lightning Bolt', {'R': 1}, ['p2'], finish=False)
    faces(monkeypatch, [int(heads)])
    spell(s, 'Desperate Gambit', {'R': 1})
    d = s.state.rules.decision
    assert d.resume['step'] == 'random_choose_source'
    selected = next(o.id for o in d.options if o.card_id == original.id)
    answer(s, [selected])
    assert s.state.players['p2'].life == (34 if heads else 40)
    roundtrip(s)


@pytest.mark.parametrize('heads', [False, True])
def test_fighting_chance_actual_blocker_coin_prevents_its_combat_damage(cards, monkeypatch, heads):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Mutalith Vortex Beast', 'battlefield', 'p2')
    attack_ready(s, attacker)
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    faces(monkeypatch, [int(heads)])
    spell(s, 'Fighting Chance', {'R': 1})
    to_phase(s, 'end_combat', turn=4)
    assert s.state.cards[attacker.id].zone == ('p1:battlefield' if heads else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('kind', ['source', 'optional_top', 'large_roll'])
def test_new_random_decisions_resume_cold_with_recorded_receipts(cards, monkeypatch, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'source':
        source = spell(s, 'Lightning Bolt', {'R': 1}, ['p2'], finish=False)
        spell(s, 'Desperate Gambit', {'R': 1})
        option = next(o.id for o in s.state.rules.decision.options if o.card_id == source.id)
        expected = 'source'
    elif kind == 'optional_top':
        victim = put(s, 'Six-Sided Die', 'graveyard')
        faces(monkeypatch, [1])
        spell(s, 'Aberrant Mind Sorcerer', {'U': 1, 'C': 4})
        if s.state.rules.decision.resume['step'] != 'random_optional_top':
            answer(s, [victim.id])
        option, expected = 'yes', 'top'
    else:
        from app.rules import dice

        monkeypatch.setattr(dice, 'ROLL_CHUNKS', 1)
        source = put(s, 'Luck Bobblehead', 'battlefield')
        act(s, 'p1', type='create_token', player='p1', count=100, stacked=False,
            token={'name': 'Bobblehead', 'type_line': 'Token Artifact — Bobblehead', 'text': ''})
        from app.rules.plan import Plan
        plan = Plan(s.state, 'p1', cards, None)
        assert sum(c.zone == 'p1:battlefield' and 'Bobblehead' in plan.ch(c).subtypes for c in s.state.cards.values()) == 101
        faces(monkeypatch, [2] * 100)
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
        settle(s)
        d = s.state.rules.decision
        assert d.resume['step'] == 'roll_group_continue'
        assert len(d.resume['results']) == 100
        assert not [f for f in s.state.rules.events if f.counter == 'roll_die']
        option, expected = 'continue', 'large'
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, option, expected = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: (1 if expected == 'large' else 1)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(60):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
if expected == 'large':
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 100
    assert s.state.rules.turn_log.rolled['p1'] == 101
elif expected == 'top':
    c = next(c for c in s.state.cards.values() if c.name == 'Six-Sided Die' and c.owner == 'p1')
    assert c.zone == 'p1:library' and s.state.zones['p1:library'][0] == c.id
else:
    assert s.state.players['p2'].life == 34
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), option, expected],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_acrobatics_high_retains_first_return_replaced_by_exile(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    priest = put(s, 'Containment Priest', 'battlefield', 'p2')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    stops(s, 'end')
    faces(monkeypatch, [20])
    spell(s, "Lae'zel's Acrobatics", {'W': 1, 'C': 3})
    assert s.state.cards[victim.id].zone == 'p1:exile'
    act(s, 'p2', type='move', card_ids=[priest.id], to={'zone': 'graveyard'})
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('n', [7, 8])
def test_luck_exactly_seven_kept_sixes_not_eight(cards, monkeypatch, n):
    s = setup(cards)
    source = put(s, 'Luck Bobblehead', 'battlefield')
    act(s, 'p1', type='create_token', player='p1', count=n - 1, stacked=False,
        token={'name': 'Bobblehead', 'type_line': 'Token Artifact — Bobblehead', 'text': ''})
    faces(monkeypatch, [6] * n)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    settle(s)
    assert s.state.rules.winner == ('p1' if n == 7 else None)
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == n
    roundtrip(s)


def test_luck_zero_count_after_source_departure_rolls_nothing(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Luck Bobblehead', 'battlefield')
    faces(monkeypatch, [])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    settle(s)
    assert not s.state.rules.turn_log.rolled.get('p1')
    assert not [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']
    roundtrip(s)


def test_iron_highest_ignores_other_players_roll_before_events(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    source = put(s, 'Iron Mastiff', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield')
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    faces(monkeypatch, [1, 20])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': other.id, 'target': 'p3'}])
    settle(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 36
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_acrobatics_exiles_own_die_replacements_before_roll(cards, monkeypatch):
    s = setup(cards)
    guide = put(s, 'Pixie Guide', 'battlefield')
    faces(monkeypatch, [10])  # A retained Guide would demand an extra physical die and fail.
    spell(s, "Lae'zel's Acrobatics", {'W': 1, 'C': 3})
    assert s.state.cards[guide.id].zone == 'p1:exile'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_large_kept_fact_cursor_resumes_cold_after_eight_hundred_without_repeating_group(cards, monkeypatch, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, 'Luck Bobblehead', 'battlefield')
    for _ in range(8):
        act(s, 'p1', type='create_token', player='p1', count=100, stacked=False,
            token={'name': 'Bobblehead', 'type_line': 'Token Artifact — Bobblehead', 'text': ''})
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Roll Counter', 'power': '2', 'toughness': '2',
        'type_line': 'Token Creature', 'text': 'Whenever you roll one or more dice, put a +1/+1 counter on this creature.'})
    faces(monkeypatch, [1] * 801)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'roll_group_continue'
    assert s.state.rules.decision.resume.get('phase') is None
    answer(s, ['continue'])
    d = s.state.rules.decision
    assert d.resume['phase'] == 'emit' and d.resume['start'] == 800
    assert len(d.resume['results']) == len(d.resume['naturals']) == 801
    assert s.state.rules.turn_log.rolled['p1'] == 801
    watcher = next(c for c in s.state.cards.values() if c.name == 'Roll Counter')
    assert watcher.counters.get('+1/+1', 0) == 0
    assert not [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']
    path = tmp_path / 'large-emission.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
def forbidden(*args):
    raise AssertionError('Completed raw dice were rolled again during kept-fact resume')
importlib.import_module('app.game.resolve')._rng_int = forbidden
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['continue']})
for _ in range(80):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert not [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']
assert s.state.rules.turn_log.rolled['p1'] == 801
watcher = next(c for c in s.state.cards.values() if c.name == 'Roll Counter')
assert watcher.counters.get('+1/+1', 0) == 1
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=300)
    assert result.returncode == 0, result.stderr


def test_danse_can_return_actual_sacrificed_commander_before_903_9_choice(cards, monkeypatch):
    s = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    key = commander.commander_key
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [20])
    spell(s, 'Danse Macabre', {'B': 2, 'C': 3})
    assert s.state.rules.decision.resume['step'] != 'commander_zone'
    answer(s, [commander.id])
    assert s.state.cards[commander.id].zone == 'p1:battlefield'
    assert s.state.cards[commander.id].commander_key == key
    assert s.state.rules.decision is None
    roundtrip(s)


def test_revivify_counts_creature_front_mdfc_that_was_a_land_not_a_dying_creature(cards, monkeypatch):
    s = setup(cards)
    name = next(c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/random_consequences_cards.json').read_text()) if c['name'].startswith('Tangled Florahedron'))
    victim = put(s, name, 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=victim.id, face=1)
    from app.rules.plan import Plan

    # A native effect puts the land into its owner's graveyard, recording its arrival.
    plan = Plan(s.state, 'p1', cards, None)
    assert not plan.ch(s.state.cards[victim.id]).is_creature
    spell(s, 'Stone Rain', {'R': 1, 'C': 2}, [victim.id])
    faces(monkeypatch, [14])  # One qualifying arrival adds1 and crosses the15 threshold.
    spell(s, 'Revivify', {'W': 1, 'C': 2})
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[victim.id]).is_creature
    roundtrip(s)


def test_wyll_uses_original_controller_for_retarget_and_copy_controller_for_new_copy(cards, monkeypatch):
    s = setup(cards)
    protected = spell(s, 'True-Name Nemesis', {'U': 2, 'C': 1})
    answer(s, ['p1'])
    original = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2', finish=False)
    faces(monkeypatch, [20])
    spell(s, "Wyll's Reversal", {'R': 1, 'C': 2}, [original.id])
    assert protected.id in {o.id for o in s.state.rules.decision.options}  # Original spell is controlled byp2.
    answer(s, [protected.id])
    assert s.state.rules.stack[original.id].controller == "p2"
    copies = [e for e in s.state.rules.stack.values() if e.copy_of is not None and e.name == "Lightning Bolt"]
    assert len(copies) == 1 and copies[0].controller == "p1"
    while s.state.rules.decision:
        d = s.state.rules.decision
        ids = {o.id for o in d.options}
        assert protected.id not in ids  # Thep1 copy cannot choose the protected creature as a new target.
        answer(s, ['keep'] if 'keep' in ids else ['no'] if 'no' in ids else [next(iter(ids))])
    assert s.state.cards[protected.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 40
    roundtrip(s)


def finish_combat_with_trample_split(s):
    for _ in range(100):
        if s.state.turn.phase == 'end_combat' and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == 'divide':
            assert len(d.options) == 2
            act(s, d.player, type='choose', decision_id=d.id, amounts=[2, d.display['total'] - 2])
        elif d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            assert d is None
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Combat did not finish')


@pytest.mark.parametrize('heads', [False, True])
def test_impulsive_whole_trample_occurrence_and_only_first_double_strike_step(cards, monkeypatch, heads):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, 'Impulsive Maneuvers', 'battlefield')
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Trampler', 'power': '5', 'toughness': '5',
        'type_line': 'Token Creature', 'text': 'Double strike, trample'})
    attacker = next(c for c in s.state.cards.values() if c.name == 'Trampler')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [int(heads)])
    attack_ready(s, attacker)
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    finish_combat_with_trample_split(s)
    assert s.state.players['p2'].life == (29 if heads else 37)
    assert s.state.cards[blocker.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_psychopath_redirects_all_trample_recipients_in_one_occurrence(cards, monkeypatch):
    from tests.test_rules_coin_outcomes import attack_ready
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    attacker = put(s, 'Goblin Psychopath', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Trample Banner', 'type_line': 'Token Enchantment',
        'text': 'Creatures you control have trample.'})
    faces(monkeypatch, [0])
    attack_ready(s, attacker)
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    finish_combat_with_trample_split(s)
    assert s.state.players['p1'].life == 35 and s.state.players['p2'].life == 40
    assert s.state.cards[blocker.id].zone == 'p2:battlefield'
    assert s.state.cards[blocker.id].damage == 0
    roundtrip(s)


@pytest.mark.parametrize('departed', [False, True])
def test_artisans_another_creature_source_exclusion_and_same_source_exception(cards, monkeypatch, departed):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = setup(cards)
    first = put(s, 'Goblin Artisans', 'battlefield')
    second = put(s, 'Goblin Artisans', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p1')
    stops(s, 'main1')
    to_phase(s, 'main1', turn=4)
    hold(s)
    original = spell(s, 'Sol Ring', {'C': 1}, finish=False)
    faces(monkeypatch, [1, 1])
    act(s, 'p1', type='activate_ability', card_id=first.id, ability=0, targets=[original.id])
    if departed:
        act(s, 'p1', type='move', card_ids=[first.id], to={'zone': 'graveyard'})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='legal target'):
        act(s, 'p1', type='activate_ability', card_id=second.id, ability=0, targets=[original.id])
    assert s.state.model_dump(mode='json') == before
    if not departed:
        act(s, 'p1', type='tap', card_ids=[first.id], tapped=False)
        act(s, 'p1', type='activate_ability', card_id=first.id, ability=0, targets=[original.id])
    settle(s)
    assert s.state.cards[original.id].zone == 'p1:battlefield'
    roundtrip(s)
