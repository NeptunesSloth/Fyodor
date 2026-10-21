"""Canonical random-choice cards through production parsing, payments and saved native effects."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer, faces
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = json.loads((Path(__file__).parent / 'fixtures/random_choice_receipts_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='r41', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in DATA] + ['Sol Ring', 'Lightning Bolt', 'Grizzly Bears', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    return s


def activate(s, source, mana, targets=(), counts=(), ability=0, **kwargs):
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability, sources=[], targets=list(targets), target_counts=list(counts), **kwargs)
    settle(s)


def test_flay_first_discard_precedes_native_second_payment(cards, monkeypatch):
    import secrets
    s = setup(cards)
    hand = [put(s, n, 'hand', 'p2') for n in ('Flay', 'Lightning Bolt')]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [c for c in [hand[0].id] if c in pool][:n])
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    spell(s, 'Flay', {'B': 1, 'C': 3}, ['p2'])
    assert s.state.cards[hand[0].id].zone == 'p2:graveyard'
    assert s.state.cards[hand[1].id].zone == 'p2:hand'
    answer(s, ['pay'])
    assert s.state.cards[hand[1].id].zone == 'p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_wand_native_life_payment_keeps_or_discards_exact_revealed_card(cards, monkeypatch, pay):
    import secrets
    s = setup(cards)
    source = put(s, 'Wand of Ith', 'battlefield')
    revealed = put(s, 'Lightning Bolt', 'hand', 'p2')
    other = put(s, 'Forest', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [revealed.id])
    activate(s, source, {'C': 3}, ['p2'])
    assert s.state.rules.decision.player == 'p2'
    observer = s.view('p3')
    assert observer['cards'][revealed.id]['name'] == 'Lightning Bolt'
    assert other.id not in observer['cards']
    answer(s, ['pay' if pay else 'decline'])
    assert s.state.cards[revealed.id].zone == ('p2:hand' if pay else 'p2:graveyard')
    assert s.state.cards[other.id].zone == 'p2:hand'
    assert s.state.players['p2'].life == (39 if pay else 40)
    roundtrip(s)


@pytest.mark.parametrize('name,sign', [("Planeswalker's Favor", 1), ("Planeswalker's Scorn", -1)])
def test_random_reveal_captured_value_pumps_original_target(cards, monkeypatch, name, sign):
    import secrets
    s = setup(cards)
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    revealed = put(s, 'Flay', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [revealed.id])
    activate(s, source, {'C': 3, 'G' if sign == 1 else 'B': 1}, ['p2', bear.id], [1, 1])
    if sign == 1:
        assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).pt == (6, 6)
    else:
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.cards[revealed.id].zone == 'p2:hand'
    roundtrip(s)


def test_game_repeated_flip_keeps_original_roller_and_doubles_stakes(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [0, 1])
    spell(s, 'Game of Chaos', {'R': 3}, ['p2'])
    assert s.state.players['p1'].life == 39 and s.state.players['p2'].life == 41
    assert s.state.rules.decision.player == 'p2'
    answer(s, ['yes'])
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
    assert s.state.rules.decision.player == 'p1'
    answer(s, ['no'])
    roundtrip(s)


def test_fossil_returns_exact_card_then_orders_remaining_graveyard(cards, monkeypatch):
    import secrets
    s = setup(cards)
    cards_gy = [put(s, n, 'graveyard') for n in ('Flay', 'Lightning Bolt', 'Forest')]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [cards_gy[0].id])
    spell(s, 'Fossil Find', {'R': 1})
    assert s.state.cards[cards_gy[0].id].zone == 'p1:hand'
    # settle auto-orders ordinary order decisions; the native move must preserve their incarnations.
    assert set(s.state.zones['p1:graveyard']) == {cards_gy[1].id, cards_gy[2].id, next(c.id for c in s.state.cards.values() if c.name == 'Fossil Find' and c.owner == 'p1')}
    roundtrip(s)


def test_tyrant_repeats_nonland_sacrifices_until_land(cards, monkeypatch):
    import secrets
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    picks = iter([bear.id, land.id])
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: next(picks))
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    assert s.state.cards[bear.id].zone == s.state.cards[land.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_bully_random_cost_then_optional_native_source_damage_or_pump(cards, monkeypatch, accept):
    import secrets
    s = setup(cards)
    source = put(s, 'Barbarian Bully', 'battlefield')
    random_card = put(s, 'Forest', 'hand')
    other_card = put(s, 'Lightning Bolt', 'hand')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [random_card.id])
    activate(s, source, {})
    assert s.state.cards[random_card.id].zone == 'p1:graveyard'
    assert s.state.cards[other_card.id].zone == 'p1:hand'
    answer(s, ['decline'])
    assert s.state.rules.decision.player == 'p2'
    answer(s, ['pay' if accept else 'decline'])
    if not accept:
        answer(s, ['decline'])
    assert s.state.players['p2'].life == (36 if accept else 40)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == ((2, 2) if accept else (4, 4))
    roundtrip(s)


def test_flowstone_native_buyback_random_discard_and_life_payment(cards, monkeypatch):
    import secrets
    s = setup(cards)
    random_card = put(s, 'Lightning Bolt', 'hand')
    land = put(s, 'Forest', 'battlefield', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [random_card.id])
    source = spell(s, 'Flowstone Flood', {'R': 1, 'C': 3}, [land.id], buyback=True)
    assert s.state.cards[random_card.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 37
    assert s.state.cards[land.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)


def test_rag_man_reveals_entire_hand_but_randomly_discards_creature_card_only(cards, monkeypatch):
    import secrets
    s = setup(cards)
    source = put(s, 'Rag Man', 'battlefield')
    to_phase(s, 'main1', turn=4)
    target = put(s, 'Grizzly Bears', 'hand', 'p2')
    other = put(s, 'Lightning Bolt', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: target.id)
    activate(s, source, {'B': 3}, ['p2'])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.cards[other.id].zone == 'p2:hand'
    roundtrip(s)


def test_search_survivors_random_reorder_then_original_selected_creature_enters(cards, monkeypatch):
    import secrets
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'graveyard')
    other = put(s, 'Lightning Bolt', 'graveyard')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: target.id)
    spell(s, 'Search for Survivors', {'R': 1, 'C': 2})
    answer(s, ['p2'])
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[other.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_scrambleverse_assigns_each_nonland_and_untaps_even_unchanged_controller(cards, monkeypatch):
    import secrets
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[bear.id, ring.id, land.id], tapped=True)
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: 'p2')
    spell(s, 'Scrambleverse', {'R': 2, 'C': 6})
    assert s.state.cards[bear.id].controller == s.state.cards[ring.id].controller == 'p2'
    assert not s.state.cards[bear.id].tapped and not s.state.cards[ring.id].tapped
    assert s.state.cards[land.id].controller == 'p1' and s.state.cards[land.id].tapped
    roundtrip(s)


def mogg_table(cards):
    s = setup(cards)
    source = put(s, 'Mogg Assassin', 'battlefield')
    to_phase(s, 'main1', turn=4)
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Rag Man', 'battlefield')
    priority(s, 'p1')
    return s, source, first, second


@pytest.mark.parametrize('won', [False, True])
def test_mogg_opponent_chooses_second_target_before_coin_and_payment(cards, monkeypatch, won):
    s, source, first, second = mogg_table(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    d = s.state.rules.decision
    assert d.player == 'p1' and not s.state.cards[source.id].tapped
    answer(s, [first.id])
    d = s.state.rules.decision
    assert d.player == 'p2' and not s.state.cards[source.id].tapped
    faces(monkeypatch, [int(won)])
    answer(s, [second.id])
    assert s.state.cards[source.id].tapped
    assert s.state.cards[first.id if won else second.id].zone.endswith(':graveyard')
    assert s.state.cards[second.id if won else first.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_mogg_supplied_first_ref_delegates_to_frozen_controller_and_allows_same_target(cards, monkeypatch):
    s, source, first, _ = mogg_table(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[first.id], sources=[])
    assert s.state.rules.decision.player == 'p2'
    act(s, 'p1', type='set_controller', card_ids=[first.id], player='p3')
    assert s.state.rules.decision.player == 'p2'
    faces(monkeypatch, [0])
    answer(s, [first.id])
    assert s.state.cards[first.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_mogg_two_client_supplied_targets_cannot_choose_for_opponent(cards):
    from app.game.errors import ActionError
    s, source, first, second = mogg_table(cards)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[first.id, second.id], target_counts=[1, 1], sources=[])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('removed,won', [('first', True), ('first', False), ('second', True), ('both', True)])
def test_mogg_filters_original_target_legality_before_coin_and_branch(cards, monkeypatch, removed, won):
    s, source, first, second = mogg_table(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[first.id], sources=[])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    for target in ([first, second] if removed == 'both' else [first] if removed == 'first' else [second]):
        act(s, target.owner, type='move', card_ids=[target.id], to={'player': target.owner, 'zone': 'hand'})
    calls = []
    def coin(rng, lo, hi):
        calls.append(1)
        assert removed != 'both', 'all-illegal Mogg must fizzle before coin'
        return int(won)
    monkeypatch.setattr('app.game.resolve._rng_int', coin)
    settle(s)
    assert len(calls) == (0 if removed == 'both' else 1)
    if removed == 'first':
        assert s.state.cards[second.id].zone == ('p1:battlefield' if won else 'p1:graveyard')
    elif removed == 'second':
        assert s.state.cards[first.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_mogg_native_copied_ability_keeps_original_two_groups_and_flips_independently(cards, monkeypatch):
    s, source, first, second = mogg_table(cards)
    copier = put(s, 'Lithoform Engine', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[first.id], sources=[])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    original = s.state.zones['stack'][-1]
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=copier.id, ability=0, targets=[original], sources=[])
    faces(monkeypatch, [1, 0])
    settle(s)
    # Native copying may offer optional new targets; keeping original groups is the copy's default.
    d = s.state.rules.decision
    if d is not None:
        answer(s, [o.id for o in d.options if 'keep' in o.id.lower()][:1])
    assert s.state.cards[first.id].zone == 'p2:graveyard'
    assert s.state.cards[second.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_maddening_hex_rolls_real_die_damages_event_player_then_reattaches(cards, monkeypatch):
    import secrets
    s = setup(cards)
    source = spell(s, 'Maddening Hex', {'R': 2, 'C': 1}, ['p2'])
    assert s.state.cards[source.id].attached_player == 'p2'
    faces(monkeypatch, [6])
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: 'p3')
    spell(s, 'Lightning Bolt', {'R': 1}, ['p1'], player='p2')
    assert s.state.players['p2'].life == 34
    assert s.state.cards[source.id].attached_player == 'p3'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_infectious_rage_captures_native_fallen_aura_incarnation_and_reattaches_nontargeted(cards, monkeypatch):
    import secrets
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = spell(s, 'Infectious Rage', {'R': 1, 'C': 1}, [first.id])
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[first.id]).pt == (4, 1)
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: second.id)
    spell(s, 'Lightning Bolt', {'R': 1}, [first.id], player='p2')
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].attached_to == second.id
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[second.id]).pt == (4, 1)
    roundtrip(s)


def test_haphazard_non_target_aims_then_endstep_random_destroys_current_candidate(cards, monkeypatch):
    import secrets
    s = setup(cards)
    targets = [put(s, n, 'battlefield', 'p2') for n in ('Grizzly Bears', 'Rag Man', 'Sol Ring', 'Forest')]
    spell(s, 'Haphazard Bombardment', {'R': 1, 'C': 5})
    answer(s, [c.id for c in targets])
    assert all(s.state.cards[c.id].counters.get('aim') == 1 for c in targets)
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: targets[0].id)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[targets[0].id].zone == 'p2:graveyard'
    assert all(s.state.cards[c.id].zone == 'p2:battlefield' for c in targets[1:])
    roundtrip(s)


def test_fall_only_selected_nonland_cards_discard_and_rise_returns_from_both_zones(cards, monkeypatch):
    import secrets
    s = setup(cards)
    land = put(s, 'Forest', 'hand', 'p2')
    nonland = put(s, 'Lightning Bolt', 'hand', 'p2')
    hidden = put(s, 'Flay', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [land.id, nonland.id])
    fall = spell(s, 'Rise // Fall', {'R': 1, 'B': 1}, ['p2'], face=1, finish=False)
    settle(s)
    assert s.state.cards[land.id].zone == s.state.cards[hidden.id].zone == 'p2:hand'
    assert s.state.cards[nonland.id].zone == 'p2:graveyard'
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[fall.id], to={'player': 'p1', 'zone': 'hand'})
    gy = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    bf = put(s, 'Rag Man', 'battlefield', 'p2')
    spell(s, 'Rise // Fall', {'U': 1, 'B': 1}, [gy.id, bf.id], target_counts=[1, 1], face=0)
    assert s.state.cards[gy.id].zone == 'p3:hand' and s.state.cards[bf.id].zone == 'p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('phase', ['first', 'second'])
def test_mogg_delegated_announcement_survives_fresh_process_at_each_pause(cards, tmp_path, phase):
    import subprocess
    import sys
    s, source, first, second = mogg_table(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    if phase == 'second':
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[first.id])
    path = tmp_path / (phase + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, phase, source, first, second = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
if phase == 'first':
    d = s.state.rules.decision
    assert d.player == 'p1'
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [first]})
d = s.state.rules.decision
assert d.player == 'p2' and not s.state.cards[source].tapped
importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: 1
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [second]})
for _ in range(40):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[source].tapped
assert s.state.cards[first].zone == 'p2:graveyard'
assert s.state.cards[second].zone == 'p1:battlefield'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), phase, source.id, first.id, second.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kind', ['wand', 'game', 'survivors', 'buyback', 'bully'])
def test_random_receipt_actual_native_continuation_survives_fresh_process(cards, monkeypatch, tmp_path, kind):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    expected = []
    if kind == 'wand':
        source = put(s, 'Wand of Ith', 'battlefield')
        target = put(s, 'Lightning Bolt', 'hand', 'p2')
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [target.id])
        activate(s, source, {'C': 3}, ['p2'])
        expected = [target.id]
    elif kind == 'game':
        faces(monkeypatch, [0])
        spell(s, 'Game of Chaos', {'R': 3}, ['p2'])
    elif kind == 'survivors':
        target = put(s, 'True-Name Nemesis', 'graveyard')
        other = put(s, 'Lightning Bolt', 'graveyard')
        monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda self, pool: target.id)
        spell(s, 'Search for Survivors', {'R': 1, 'C': 2})
        answer(s, ['p2'])
        assert s.state.rules.decision is not None
        expected = [target.id, other.id]
    elif kind == 'buyback':
        target = put(s, 'Lightning Bolt', 'hand')
        land = put(s, 'Forest', 'battlefield', 'p2')
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [target.id])
        source = spell(s, 'Flowstone Flood', {'R': 1, 'C': 3}, [land.id], buyback=True, finish=False)
        assert s.state.cards[target.id].zone == 'p1:graveyard' and s.state.players['p1'].life == 37
        expected = [target.id, land.id, source.id]
    else:
        source = put(s, 'Barbarian Bully', 'battlefield')
        target = put(s, 'Lightning Bolt', 'hand')
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [target.id])
        activate(s, source, {})
        expected = [target.id, source.id]
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, json, secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, db, kind, expected = sys.argv[1:]
expected = json.loads(expected)
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
secrets.SystemRandom.sample = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('random sample repeated'))
secrets.SystemRandom.choice = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('random object choice repeated'))
importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: 1
if kind != 'buyback':
    d = s.state.rules.decision
    option = 'pay' if kind == 'wand' else 'yes' if kind == 'game' else 'p2' if kind == 'survivors' else 'decline'
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(60):
    d = s.state.rules.decision
    if d:
        assert kind in ('game', 'bully')
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['no' if kind == 'game' else 'decline']})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
if kind == 'wand':
    assert s.state.cards[expected[0]].zone == 'p2:hand' and s.state.players['p2'].life == 39
elif kind == 'game':
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
elif kind == 'survivors':
    assert s.state.cards[expected[0]].zone == 'p1:battlefield'
    assert s.state.cards[expected[1]].zone == 'p1:graveyard'
elif kind == 'buyback':
    assert s.state.cards[expected[0]].zone == 'p1:graveyard' and s.state.players['p1'].life == 37
    assert s.state.cards[expected[1]].zone == 'p2:graveyard' and s.state.cards[expected[2]].zone == 'p1:hand'
else:
    assert s.state.cards[expected[0]].zone == 'p1:graveyard'
    assert Plan(s.state, 'p1', repo, None).ch(s.state.cards[expected[1]]).pt == (4, 4)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, json.dumps(expected)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_zurzoth_first_offturn_draw_devils_group_attacks_only_actual_players(cards, monkeypatch):
    import secrets
    s = setup(cards)
    put(s, 'Zurzoth, Chaos Rider', 'battlefield')
    spell(s, 'Reach Through Mists', {'U': 1}, player='p2')
    devil = next(c for c in s.state.cards.values() if c.name == 'Devil' and c.zone == 'p1:battlefield')
    assert Plan(s.state, 'p1', cards, None).ch(devil).pt == (1, 1)
    # Summoning sickness expires before the real declaration. Other native off-turn draws may make extra Devils.
    to_phase(s, 'declare_attackers', turn=4)
    attacker = s.state.cards[devil.id]
    p1_hand = len(s.state.zones.get('p1:hand', []))
    p2_hand = len(s.state.zones.get('p2:hand', []))
    p3_hand = len(s.state.zones.get('p3:hand', []))
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: list(pool)[:n])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}])
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == p1_hand
    assert len(s.state.zones.get('p2:hand', [])) == p2_hand
    assert len(s.state.zones.get('p3:hand', [])) == p3_hand
    assert any(s.state.cards[c].zone == 'p2:graveyard' for c in s.state.zones.get('p2:graveyard', []))
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_cloak_accepted_assignment_none_causes_defending_player_random_discard(cards, monkeypatch, accept):
    import secrets
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Cloak of Confusion', {'B': 1, 'C': 1}, [bear.id])
    to_phase(s, 'declare_attackers', turn=4)
    discard = put(s, 'Lightning Bolt', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [discard.id])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers', turn=4)
    settle(s)
    answer(s, ['yes' if accept else 'no'])
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (40 if accept else 38)
    assert s.state.cards[discard.id].zone == ('p2:graveyard' if accept else 'p2:hand')
    roundtrip(s)


def test_fall_selected_subset_pauses_for_actual_discard_replacement(cards, monkeypatch):
    import secrets
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield', 'p2')
    baloth = put(s, 'Obstinate Baloth', 'hand', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    hidden = put(s, 'Forest', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [baloth.id, bolt.id])
    spell(s, 'Rise // Fall', {'R': 1, 'B': 1}, ['p2'], face=1)
    d = s.state.rules.decision
    assert d is not None
    assert s.state.cards[hidden.id].zone == 'p2:hand'


@pytest.mark.parametrize('name', ["Planeswalker's Favor", "Planeswalker's Scorn"])
def test_favor_and_scorn_empty_hand_have_zero_value(cards, name):
    s = setup(cards)
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    hand = list(s.state.zones.get('p2:hand', []))
    if hand:
        act(s, 'p2', type='move', card_ids=hand, to={'player': 'p2', 'zone': 'library'})
    activate(s, source, {'C': 3, 'G' if 'Favor' in name else 'B': 1}, ['p2', bear.id], [1, 1])
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Forest', 'Sol Ring'])
def test_wand_land_one_life_and_nonland_mana_value_payment(cards, monkeypatch, name):
    import secrets
    s = setup(cards)
    source = put(s, 'Wand of Ith', 'battlefield')
    target = put(s, name, 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [target.id])
    activate(s, source, {'C': 3}, ['p2'])
    answer(s, ['pay'])
    assert s.state.players['p2'].life == 39
    assert s.state.cards[target.id].zone == 'p2:hand'
    roundtrip(s)


def test_flay_cannot_pay_discards_two_separate_current_hand_samples(cards, monkeypatch):
    import secrets
    s = setup(cards)
    cards_hand = [put(s, n, 'hand', 'p2') for n in ('Lightning Bolt', 'Forest')]
    pools = []
    def sample(self, pool, n):
        pools.append(list(pool))
        return list(pool)[:n]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', sample)
    spell(s, 'Flay', {'B': 1, 'C': 3}, ['p2'])
    assert len(pools) == 2 and len(pools[1]) == len(pools[0]) - 1
    assert len(s.state.zones.get('p2:graveyard', [])) == 2
    assert any(s.state.cards[c.id].zone == 'p2:graveyard' for c in cards_hand)
    roundtrip(s)


def test_random_discard_buyback_and_activation_costs_cannot_be_paid_with_empty_hand(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    bully = put(s, 'Barbarian Bully', 'battlefield')
    land = put(s, 'Forest', 'battlefield', 'p2')
    hand = list(s.state.zones.get('p1:hand', []))
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    with pytest.raises(ActionError):
        activate(s, bully, {})
    with pytest.raises(ActionError):
        spell(s, 'Flowstone Flood', {'R': 1, 'C': 3}, [land.id], buyback=True)
    assert s.state.players['p1'].life == 40 and s.state.cards[land.id].zone == 'p2:battlefield'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bully.id]).pt == (2, 2)
    roundtrip(s)


def test_tyrant_prevented_sacrifice_stops_after_one_random_selection(cards, monkeypatch):
    import secrets
    s = setup(cards)
    source = put(s, 'Sigarda, Host of Herons', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    calls = []
    def choose(self, pool):
        calls.append(list(pool))
        return bear.id
    monkeypatch.setattr(secrets.SystemRandom, 'choice', choose)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    assert len(calls) == 1
    assert s.state.cards[source.id].zone == s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_haphazard_official_random_pool_excludes_indestructible(cards, monkeypatch):
    import secrets
    s = setup(cards)
    targets = [put(s, n, 'battlefield', 'p2') for n in ('Darksteel Ingot', 'Grizzly Bears', 'Sol Ring', 'Forest')]
    spell(s, 'Haphazard Bombardment', {'R': 1, 'C': 5})
    answer(s, [c.id for c in targets])
    def choose(self, pool):
        assert targets[0].id not in pool
        return targets[1].id
    monkeypatch.setattr(secrets.SystemRandom, 'choice', choose)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[targets[0].id].zone == 'p2:battlefield' and s.state.cards[targets[1].id].zone == 'p2:graveyard'
    roundtrip(s)


def test_game_may_recover_from_zero_life_before_resolution_finishes(cards, monkeypatch):
    s = setup(cards)
    act(s, 'p1', type='set_life', player='p1', value=1)
    faces(monkeypatch, [0, 1])
    spell(s, 'Game of Chaos', {'R': 3}, ['p2'])
    assert s.state.players['p1'].life == 0 and 'p1' in Plan(s.state, 'p1', cards, None).live()
    answer(s, ['yes'])
    answer(s, ['no'])
    assert s.state.players['p1'].life == 2 and 'p1' in Plan(s.state, 'p1', cards, None).live()
    roundtrip(s)


def test_fall_random_subset_survives_fresh_process_actual_discard_replacement(cards, monkeypatch, tmp_path):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield', 'p2')
    baloth = put(s, 'Obstinate Baloth', 'hand', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    hidden = put(s, 'Forest', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [baloth.id, bolt.id])
    spell(s, 'Rise // Fall', {'R': 1, 'B': 1}, ['p2'], face=1)
    assert s.state.rules.decision.resume['step'] == 'zone_replace_order'
    path = tmp_path / 'fall.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import json, secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, baloth, bolt, hidden = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
observer = s.view('p3')
assert hidden not in observer['cards']
assert observer['cards'][baloth]['name'] == 'Obstinate Baloth'
assert observer['cards'][bolt]['name'] == 'Lightning Bolt'
assert hidden not in json.dumps(observer)
secrets.SystemRandom.sample = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('revealed subset randomized again'))
d = s.state.rules.decision
assert d.player == 'p2' and d.resume['step'] == 'zone_replace_order'
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['battlefield']})
for _ in range(60):
    d = s.state.rules.decision
    if d:
        assert d.kind == 'order'
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o.id for o in d.options]})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert s.state.cards[baloth].zone == 'p2:battlefield' and s.state.players['p2'].life == 44
assert s.state.cards[bolt].zone == 'p2:exile'
assert not s.state.cards[baloth].revealed_to and not s.state.cards[bolt].revealed_to
assert s.state.cards[hidden].zone == 'p2:hand'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), baloth.id, bolt.id, hidden.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', [c['name'] for c in DATA[:22] if c['name'] not in ("Outlaws' Merriment", 'Molten Sentry', 'Ydwen Efreet')])
def test_production_all_canonical_printed_lines_supported(cards, name):
    from app.rules import coverage
    report = coverage.of_card_data(cards.resolve(name))
    assert report.level == 'FULL', (name, report)


def test_zurzoth_devil_at_planeswalker_does_not_borrow_other_creatures_player_attack(cards):
    s = setup(cards)
    put(s, 'Zurzoth, Chaos Rider', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Reach Through Mists', {'U': 1}, player='p2')
    devil = next(c for c in s.state.cards.values() if c.name == 'Devil' and c.zone == 'p1:battlefield')
    # A second off-turn draw by that same opponent is not their first draw this turn.
    spell(s, 'Reach Through Mists', {'U': 1}, player='p2')
    assert len([c for c in s.state.cards.values() if c.name == 'Devil' and c.zone == 'p1:battlefield']) == 1
    to_phase(s, 'main1', turn=4)
    walker = spell(s, 'Jace Beleren', {'U': 2, 'C': 1})
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    to_phase(s, 'declare_attackers', turn=4)
    hands = {pid: len(s.state.zones.get(pid + ':hand', [])) for pid in s.state.players}
    graves = {pid: len(s.state.zones.get(pid + ':graveyard', [])) for pid in s.state.players}
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': devil.id, 'target': walker.id}, {'card_id': bear.id, 'target': 'p3'}])
    settle(s)
    assert {pid: len(s.state.zones.get(pid + ':hand', [])) for pid in s.state.players} == hands
    assert {pid: len(s.state.zones.get(pid + ':graveyard', [])) for pid in s.state.players} == graves
    roundtrip(s)


def test_maddening_hex_departed_source_still_rolls_and_uses_damage_lki(cards, monkeypatch):
    s = setup(cards)
    source = spell(s, 'Maddening Hex', {'R': 2, 'C': 1}, ['p2'])
    spell(s, 'Lightning Bolt', {'R': 1}, ['p1'], player='p2', finish=False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    faces(monkeypatch, [3])
    settle(s)
    assert s.state.players['p2'].life == 37 and s.state.rules.turn_log.rolled['p1'] == 1
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_infectious_rage_new_graveyard_incarnation_cannot_be_returned(cards, monkeypatch):
    import secrets
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = spell(s, 'Infectious Rage', {'R': 1, 'C': 1}, [bear.id])
    bolt = spell(s, 'Lightning Bolt', {'R': 1}, [bear.id], player='p2', finish=False)
    while s.state.cards[bolt.id].zone == 'stack':
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda *a: (_ for _ in ()).throw(AssertionError('new aura incarnation incorrectly considered')))
    settle(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_fossil_remaining_graveyard_order_survives_fresh_process(cards, monkeypatch, tmp_path):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    chosen, bolt, land = [put(s, n, 'graveyard') for n in ('Flay', 'Lightning Bolt', 'Forest')]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [chosen.id])
    source = spell(s, 'Fossil Find', {'R': 1}, finish=False)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision.resume['step'] == 'r41_grave_order'
    path = tmp_path / 'fossil.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import json, secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, chosen, bolt, land, source = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
secrets.SystemRandom.sample = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('returned card sampled again'))
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [bolt, land]})
assert s.state.cards[chosen].zone == 'p1:hand'
assert s.state.zones['p1:graveyard'] == [land, bolt, source]
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), chosen.id, bolt.id, land.id, source.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kind', ['activation', 'buyback'])
def test_caller_cannot_choose_native_random_discard_cost_object(cards, kind):
    from app.game.errors import ActionError
    s = setup(cards)
    chosen = put(s, 'Lightning Bolt', 'hand')
    if kind == 'activation':
        source = put(s, 'Barbarian Bully', 'battlefield')
        with pytest.raises(ActionError, match='no such part to choose'):
            activate(s, source, {}, cost_choices=[{'component': 0, 'cards': [chosen.id]}])
    else:
        land = put(s, 'Forest', 'battlefield', 'p2')
        with pytest.raises(ActionError, match='no such part to choose'):
            spell(s, 'Flowstone Flood', {'R': 1, 'C': 3}, [land.id], buyback=True, cost_choices=[{'component': 1, 'cards': [chosen.id]}])
    assert s.state.cards[chosen.id].zone == 'p1:hand' and s.state.players['p1'].life == 40
    roundtrip(s)


def test_bully_departed_source_deals_native_damage_using_original_lki(cards, monkeypatch):
    import secrets
    s = setup(cards)
    source = put(s, 'Barbarian Bully', 'battlefield')
    discarded = put(s, 'Lightning Bolt', 'hand')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [discarded.id])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    answer(s, ['decline'])
    answer(s, ['pay'])
    assert s.state.players['p2'].life == 36 and s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_bully_once_per_turn_gate_checks_before_a_second_random_payment(cards, monkeypatch):
    import secrets

    from app.game.errors import ActionError
    s = setup(cards)
    source = put(s, 'Barbarian Bully', 'battlefield')
    discarded = put(s, 'Lightning Bolt', 'hand')
    retained = put(s, 'Forest', 'hand')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [discarded.id])
    activate(s, source, {})
    for _ in range(3):
        answer(s, ['decline'])
    with pytest.raises(ActionError):
        activate(s, source, {})
    assert s.state.cards[retained.id].zone == 'p1:hand'
    roundtrip(s)


def test_game_native_thumb_kept_outcome_supplies_life_and_continuation_chooser(cards, monkeypatch):
    s = setup(cards)
    put(s, "Krark's Thumb", 'battlefield')
    faces(monkeypatch, [0, 1])
    spell(s, 'Game of Chaos', {'R': 3}, ['p2'])
    assert s.state.rules.decision.resume['phase'] == 'ignore'
    answer(s, ['1'])
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
    assert s.state.rules.decision.player == 'p1'
    answer(s, ['no'])
    roundtrip(s)


@pytest.mark.parametrize('count', [0, 2])
def test_haphazard_aims_as_many_as_possible_and_only_triggers_at_two(cards, count):
    s = setup(cards)
    targets = [put(s, n, 'battlefield', 'p2') for n in ('Grizzly Bears', 'Forest')[:count]]
    spell(s, 'Haphazard Bombardment', {'R': 1, 'C': 5})
    if count:
        answer(s, [c.id for c in targets])
        assert all(s.state.cards[c.id].counters.get('aim') == 1 for c in targets)
        act(s, 'p2', type='counter', card_ids=[targets[0].id], kind='aim', delta=-1)
    to_phase(s, 'end')
    settle(s)
    assert not s.state.zones.get('stack') and all(s.state.cards[c.id].zone == 'p2:battlefield' for c in targets)
    roundtrip(s)


def test_wand_does_not_discard_a_new_incarnation_of_revealed_card(cards, monkeypatch):
    import secrets
    s = setup(cards)
    source = put(s, 'Wand of Ith', 'battlefield')
    revealed = put(s, 'Lightning Bolt', 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, pool, n: [revealed.id])
    activate(s, source, {'C': 3}, ['p2'])
    act(s, 'p2', type='move', card_ids=[revealed.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p2', type='move', card_ids=[revealed.id], to={'player': 'p2', 'zone': 'hand'})
    answer(s, ['decline'])
    assert s.state.cards[revealed.id].zone == 'p2:hand'
    roundtrip(s)


def test_cloak_departed_attacker_cannot_accept_assignment_or_discard(cards, monkeypatch):
    import secrets
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Cloak of Confusion', {'B': 1, 'C': 1}, [bear.id])
    to_phase(s, 'declare_attackers', turn=4)
    retained = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers', turn=4)
    settle(s)
    assert s.state.rules.decision is not None
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'hand'})
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda *args: pytest.fail('No accepted assignment means no discard'))
    answer(s, ['yes'])
    assert s.state.cards[retained.id].zone == 'p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', ["Planeswalker's Favor", "Planeswalker's Scorn"])
def test_random_reveal_resolves_legal_player_but_never_pumps_new_target_incarnation(cards, monkeypatch, name):
    import secrets
    s = setup(cards)
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    revealed = put(s, 'Flay', 'hand', 'p2')
    sampled = []
    def pick(rng, pool, n):
        sampled.append(tuple(pool))
        return [revealed.id]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', pick)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G' if name.endswith('Favor') else 'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[], targets=['p2', bear.id], target_counts=[1, 1])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert len(sampled) == 1
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Lightning Bolt', None])
def test_search_survivors_noncreature_is_exiled_and_empty_graveyard_invents_no_card(cards, monkeypatch, name):
    import secrets
    s = setup(cards)
    target = put(s, name, 'graveyard') if name else None
    def pick(rng, pool):
        assert target is not None and target.id in pool
        return target.id
    monkeypatch.setattr(secrets.SystemRandom, 'choice', pick)
    spell(s, 'Search for Survivors', {'R': 1, 'C': 2})
    answer(s, ['p2'])
    if target:
        assert s.state.cards[target.id].zone == 'p1:exile'
    assert not s.state.zones.get('p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('outcome,zone', [('exile', 'exile'), ('library:shuffle', 'library')])
def test_tyrant_waits_for_actual_sacrifice_replacement_before_repeating(cards, monkeypatch, outcome, zone):
    import secrets
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Blightsteel Colossus', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda rng, pool: chosen.id if chosen.id in pool else land.id)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    assert s.state.rules.decision.resume['step'] == 'zone_replace_order'
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    assert s.state.zones.get('stack')
    answer(s, [outcome])
    assert s.state.cards[chosen.id].zone == 'p2:' + zone
    assert s.state.cards[land.id].zone == 'p2:exile'
    roundtrip(s)


def test_tyrant_pending_sacrifice_replacement_survives_fresh_process(cards, monkeypatch, tmp_path):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Blightsteel Colossus', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda rng, pool: chosen.id)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    assert s.state.rules.decision.resume['step'] == 'zone_replace_order'
    path = tmp_path / 'tyrant616.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, chosen, land = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
picks = []
def pick(rng, pool):
    assert chosen not in pool and land in pool
    picks.append(tuple(pool))
    return land
secrets.SystemRandom.choice = pick
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['exile']})
assert len(picks) == 1
assert s.state.cards[chosen].zone == s.state.cards[land].zone == 'p2:exile'
assert not s.state.zones.get('stack') and s.state.rules.decision is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), chosen.id, land.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_tyrant_commander_replacement_finishes_native903_choice_before_next_sample(cards, monkeypatch, choice):
    import secrets
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Progenitus', 'battlefield', 'p2')
    act(s, 'p2', type='set_commander', card_id=chosen.id)
    land = put(s, 'Forest', 'battlefield', 'p2')
    picks = []
    def pick(rng, pool):
        picks.append(tuple(pool))
        return chosen.id if len(picks) == 1 else land.id
    monkeypatch.setattr(secrets.SystemRandom, 'choice', pick)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    answer(s, ['library:shuffle'])
    assert len(picks) == 1 and s.state.cards[land.id].zone == 'p2:battlefield'
    assert s.state.rules.decision.resume['step'] == 'commander_instead'
    answer(s, [choice])
    commander = next(c for c in s.state.cards.values() if c.name == 'Progenitus' and c.commander_key and c.owner == 'p2')
    assert commander.zone == 'p2:' + ('command' if choice == 'yes' else 'library')
    assert s.state.cards[land.id].zone == 'p2:exile' and len(picks) == 2
    roundtrip(s)


def test_tyrant_invalidated_held_object_aborts_only_pending_repeat_and_finishes_stack(cards, monkeypatch):
    import secrets
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Blightsteel Colossus', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda rng, pool: chosen.id)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    assert s.state.rules.decision.resume['step'] == 'zone_replace_order'
    act(s, 'p2', type='move', card_ids=[chosen.id], to={'player': 'p2', 'zone': 'hand'})
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda *args: pytest.fail('Invalidated sacrifice must not restart random selection'))
    answer(s, ['exile'])
    assert s.state.cards[chosen.id].zone == 'p2:hand'
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    assert not s.state.zones.get('stack') and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_tyrant_commander_second_native_pause_survives_fresh_process(cards, monkeypatch, tmp_path, choice):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Progenitus', 'battlefield', 'p2')
    act(s, 'p2', type='set_commander', card_id=chosen.id)
    land = put(s, 'Forest', 'battlefield', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda rng, pool: chosen.id)
    spell(s, 'Tyrant of Discord', {'R': 3, 'C': 4})
    answer(s, ['p2'])
    answer(s, ['library:shuffle'])
    assert s.state.rules.decision.resume['step'] == 'commander_instead'
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    key = next(c.commander_key for c in s.state.cards.values() if c.name == 'Progenitus' and c.owner == 'p2' and c.commander_key)
    path = tmp_path / ('tyrant903-' + choice + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, key, land, choice = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
picks = []
def pick(rng, pool):
    assert pool == [land]
    picks.append(tuple(pool))
    return land
secrets.SystemRandom.choice = pick
d = s.state.rules.decision
assert d.player == 'p2' and d.resume['step'] == 'commander_instead'
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [choice]})
assert len(picks) == 1
commander = next(c for c in s.state.cards.values() if c.commander_key == key)
assert commander.zone == 'p2:' + ('command' if choice == 'yes' else 'library')
assert s.state.cards[land].zone == 'p2:exile'
assert not s.state.zones.get('stack') and s.state.rules.decision is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), key, land.id, choice], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name,n', [('Rise // Fall', 4), ('Fireball', 1), ('Ancestral Vision', 0)])
def test_wand_uses_combined_split_value_zero_x_and_actual_optional_zero_life(cards, monkeypatch, name, n):
    import secrets
    s = setup(cards)
    source = put(s, 'Wand of Ith', 'battlefield')
    revealed = put(s, name, 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda rng, pool, count: [revealed.id])
    activate(s, source, {'C': 3}, ['p2'])
    assert s.state.rules.decision.player == 'p2'
    assert 'pay' in [o.id for o in s.state.rules.decision.options]
    answer(s, ['pay'])
    assert s.state.players['p2'].life == 40 - n
    assert s.state.cards[revealed.id].zone == 'p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Lightning Bolt', 'Ancestral Vision'])
def test_wand_native_life_prohibition_refuses_positive_payment_but_allows_zero(cards, monkeypatch, name):
    import secrets
    s = setup(cards)
    put(s, 'Platinum Emperion', 'battlefield', 'p2')
    source = put(s, 'Wand of Ith', 'battlefield')
    revealed = put(s, name, 'hand', 'p2')
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda rng, pool, count: [revealed.id])
    activate(s, source, {'C': 3}, ['p2'])
    if name == 'Ancestral Vision':
        assert s.state.rules.decision is not None
        answer(s, ['pay'])
        assert s.state.cards[revealed.id].zone == 'p2:hand'
    else:
        assert s.state.rules.decision is None
        assert s.state.cards[revealed.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('won', [False, True])
def test_game_native_life_change_prohibition_does_not_change_kept_flip_decider(cards, monkeypatch, won):
    s = setup(cards)
    put(s, 'Platinum Emperion', 'battlefield', 'p2')
    faces(monkeypatch, [int(won)])
    spell(s, 'Game of Chaos', {'R': 3}, ['p2'])
    assert s.state.players['p2'].life == 40
    assert s.state.players['p1'].life == (41 if won else 39)
    assert s.state.rules.decision.player == ('p1' if won else 'p2')
    answer(s, ['no'])
    roundtrip(s)
