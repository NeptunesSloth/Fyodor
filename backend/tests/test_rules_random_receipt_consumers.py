"""Canonical roll receipts feed native actions, with no additional die rolls for random choices."""
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
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/random_receipt_consumers_cards.json').read_text())
    from tests.test_rules_wave24b_dice import EXTRA
    existing = {c['name']: c for c in [*fixture_cards(), *EXTRA]}
    for i, c in enumerate(data):
        existing[c['name']] = card(c['name'], set_code='r40', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    scales = next(c for c in json.loads((Path(__file__).parent / 'fixtures/large_counter_placement_cards.json').read_text()) if c['name'] == 'Hardened Scales')
    existing['Hardened Scales'] = card('Hardened Scales', set_code='r4s', number='1', **{k: v for k, v in scales.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/random_receipt_consumers_cards.json').read_text())]
    names += ['Sol Ring', 'Lightning Bolt', "Diviner's Portent", 'Dregscape Zombie', 'Dregscape Zombie', 'Twisted Abomination', 'Hardened Scales']
    s = three(cards, names, names, names)
    hold(s)
    return s


def activate(s, name, mana, *, ability=0, targets=()):
    source = put(s, name, 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability, sources=[], targets=list(targets))
    settle(s)
    return source


def test_purse_creates_then_passes_right(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [4])
    source = activate(s, "Bucknard's Everfull Purse", {'C': 1})
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.controller == 'p1' and c.zone.endswith(':battlefield')]) == 4
    assert s.state.cards[source.id].controller == 'p3'
    roundtrip(s)


@pytest.mark.parametrize('choice,beasts,lands', [('0', 1, 3), ('1', 3, 1)])
def test_wild_pair_preserves_both_results(cards, monkeypatch, choice, beasts, lands):
    s = setup(cards)
    faces(monkeypatch, [1, 3])
    spell(s, 'Wild Endeavor', {'G': 2, 'C': 4})
    answer(s, [choice])
    assert len([c for c in s.state.cards.values() if c.name == 'Beast' and c.zone.endswith(':battlefield')]) == beasts
    d = s.state.rules.decision
    assert d is not None and d.max_choices == lands
    answer(s, [])
    roundtrip(s)


@pytest.mark.parametrize('result,expected', [(1, 3), (6, 2)])
def test_clowns_count_actual_robot_subtypes(cards, monkeypatch, result, expected):
    s = setup(cards)
    faces(monkeypatch, [result])
    spell(s, 'Clowning Around', {'W': 1, 'C': 1})
    assert len([c for c in s.state.cards.values() if c.name == 'Clown Robot' and c.zone.endswith(':battlefield')]) == expected
    roundtrip(s)


def test_pair_untargeted_total_allows_zero_mana_cards(cards, monkeypatch):
    s = setup(cards)
    land = put(s, 'Forest', 'graveyard')
    bears = put(s, 'Grizzly Bears', 'graveyard')
    faces(monkeypatch, [1, 1])
    source = spell(s, "Pair o' Dice Lost", {'G': 2, 'C': 3})
    answer(s, [land.id, bears.id])
    assert s.state.cards[land.id].zone == s.state.cards[bears.id].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('accept', [True, False])
def test_fly_optional_animation_after_actual_roll(cards, monkeypatch, accept):
    s = setup(cards)
    faces(monkeypatch, [5])
    source = activate(s, 'Ebony Fly', {'C': 4}, ability=2)
    answer(s, ['yes' if accept else 'no'])
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.is_creature == accept
    if accept:
        assert ch.pt == (5, 5) and 'flying' in ch.keywords
    roundtrip(s)


def test_waltz_only_remaining_two_targets_both_return(cards):
    s = setup(cards)
    chosen = [put(s, name, 'graveyard') for name in ("Grizzly Bears", "Farideh, Devil's Chosen", "Chaos Dragon")]
    source = spell(s, 'Sinister Waltz', {'B': 1, 'R': 1, 'C': 3}, [c.id for c in chosen], target_counts=[3], finish=False)
    act(s, 'p1', type='move', card_ids=[chosen[-1].id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in chosen[:2])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_wild_swing_one_legal_target_no_random_choice(cards):
    s = setup(cards)
    chosen = [put(s, name, 'battlefield', 'p2') for name in ("Grizzly Bears", "Farideh, Devil's Chosen", "Chaos Dragon")]
    spell(s, 'Wild Swing', {'R': 1, 'C': 3}, [c.id for c in chosen], target_counts=[3], finish=False)
    act(s, 'p1', type='move', card_ids=[c.id for c in chosen[:2]], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    assert s.state.cards[chosen[-1].id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('natural,expected', [(19, False), (20, True)])
def test_critical_hit_uses_natural_face_not_modified_result(cards, monkeypatch, natural, expected):
    s = setup(cards)
    critical = put(s, 'Critical Hit', 'graveyard')
    # One other card remains in hand as the printed d20 modifier.
    put(s, 'Lightning Bolt', 'hand')
    faces(monkeypatch, [natural])
    spell(s, "Diviner's Portent", {'U': 3}, x_value=0)
    assert (s.state.cards[critical.id].zone == 'p1:hand') == expected
    roundtrip(s)


@pytest.mark.parametrize('tagged,departed', [(False, False), (True, False), (False, True), (True, True)])
def test_house_roll_count_consumes_exact_activation_payment(cards, monkeypatch, tagged, departed):
    from app.game.rules_state import turn_log_now
    from tests.test_rules_wave18b_mana import treasure
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Mr. House, President and CEO', 'battlefield')
    to_phase(s, 'main1', turn=4)
    if tagged:
        token = treasure(s)
        act(s, 'p1', type='activate_ability', card_id=token.id, ability=0, mana_choice='R')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3 if tagged else 4})
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    if departed:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    faces(monkeypatch, [4, 6] if tagged else [4])
    settle(s)
    assert turn_log_now(s.state).rolled['p1'] == (2 if tagged else 1)
    if not departed:
        robots = [c for c in s.state.cards.values() if c.name == 'Robot' and c.zone == 'p1:battlefield']
        assert len(robots) == (2 if tagged else 1)
        assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (3, 3) for c in robots)
        assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == int(tagged)
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 4, 8])
def test_bag_reveals_until_exact_mana_value_or_bottoms_whole_library(cards, monkeypatch, result):
    s = setup(cards)
    faces(monkeypatch, [result])
    before = list(s.state.zones['p1:library'])
    source = activate(s, 'Bag of Tricks', {'G': 1, 'C': 4})
    matches = [c for c in before if Plan(s.state, 'p1', cards, None).ch(s.state.cards[c]).is_creature and Plan(s.state, 'p1', cards, None).ch(s.state.cards[c]).mana_value == result]
    if matches:
        assert s.state.cards[matches[0]].zone == 'p1:battlefield'
    else:
        assert set(s.state.zones['p1:library']) == set(before) - {source.id}
    roundtrip(s)


def test_boarding_decline_does_not_consume_acceptance(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Priority Boarding', 'battlefield')
    faces(monkeypatch, [4])
    activate(s, "Bucknard's Everfull Purse", {'C': 1})
    assert s.state.rules.decision.resume['step'] == 'receipt_boarding'
    answer(s, ['no'])
    assert not any(k.startswith('receipt_boarding:') for k in s.state.rules.once_per_turn)
    roundtrip(s)


@pytest.mark.parametrize('result,scales', [(1, False), (10, False), (10, True), (20, False)])
def test_journey_current_packet_and_return_branches(cards, monkeypatch, result, scales):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Journey to the Lost City', 'battlefield')
    if scales:
        put(s, 'Hardened Scales', 'battlefield')
    packet = [put(s, n, 'hand') for n in ('Forest', 'Grizzly Bears', 'Chaos Dragon', 'Lightning Bolt')]
    faces(monkeypatch, [result])
    # The draw in turns 2 and 3 belongs to the opponents, so this packet stays intact.
    for c in reversed(packet):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    if result == 1:
        answer(s, [packet[0].id])
        assert s.state.cards[packet[0].id].zone == 'p1:battlefield'
        assert all(s.state.cards[c.id].zone == 'p1:exile' for c in packet[1:])
    elif result == 10:
        wolf = next(c for c in s.state.cards.values() if c.name == 'Wolf' and c.zone == 'p1:battlefield')
        assert wolf.counters.get('+1/+1') == (3 if scales else 2)
    else:
        assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in packet[:3])
        assert s.state.cards[packet[3].id].zone == 'p1:exile'
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_boarding_pending_rolls_allow_decline_then_once_accepted_exile(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Priority Boarding', 'battlefield')
    land = put(s, 'Forest', 'hand')
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    faces(monkeypatch, [2, 6])
    spell(s, "Pair o' Dice Lost", {'G': 2, 'C': 3})
    answer(s, ['no'])
    assert s.state.rules.decision.resume['kind'] == 'boarding'
    answer(s, ['yes'])
    assert s.state.rules.decision.resume['kind'] == 'boarding_exile'
    answer(s, ['yes'])
    assert s.state.cards[land.id].zone == 'p1:exile'
    permission = next(p for p in s.state.rules.permissions if p.object_id == s.state.rules.object_id(land.id))
    assert permission.play and permission.until == 'end_of_turn'
    assert s.state.rules.once_per_turn['receipt_boarding:' + s.state.rules.object_id(source.id)] == s.state.turn.number
    roundtrip(s)


@pytest.mark.parametrize('result', [1, 10])
def test_rift_exiles_real_source_cost_and_inserts_without_shuffle(cards, monkeypatch, result):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, 'Underdark Rift', 'battlefield')
    library = list(s.state.zones['p2:library'])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    faces(monkeypatch, [result])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], targets=[target.id])
    assert s.state.cards[source.id].zone == 'p1:exile'
    settle(s)
    expected = list(library)
    expected.insert(min(result, len(expected)), target.id)
    assert s.state.zones['p2:library'] == expected
    roundtrip(s)


def test_capricious_efreet_can_destroy_itself_as_only_target(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Capricious Efreet', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    d = s.state.rules.decision
    assert d is not None
    # The native target-group chooser asks for the mandatory own permanent first.
    answer(s, [source.id])
    if s.state.rules.decision is not None:
        answer(s, [])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_giant_chooses_a_missing_counter_kind_on_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Crystalline Giant', 'battlefield')
    to_phase(s, 'begin_combat')
    settle(s)
    source = s.state.cards[source.id]
    assert sum(source.counters.values()) == 1
    assert set(source.counters) <= {'flying', 'first strike', 'deathtouch', 'hexproof', 'lifelink', 'menace', 'reach', 'trample', 'vigilance', '+1/+1'}
    roundtrip(s)


@pytest.mark.parametrize('kind', ['boarding', 'waltz'])
def test_receipt_pending_choice_survives_fresh_process(cards, monkeypatch, tmp_path, kind):
    import subprocess
    import sys
    s = setup(cards)
    if kind == 'boarding':
        put(s, 'Priority Boarding', 'battlefield')
        land = put(s, 'Forest', 'hand')
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'library'}, index=0)
        faces(monkeypatch, [4])
        activate(s, "Bucknard's Everfull Purse", {'C': 1})
        answer(s, ['yes'])
        assert s.state.rules.decision.resume['kind'] == 'boarding_exile'
        expected = [land.id]
    else:
        import secrets
        targets = [put(s, name, 'graveyard') for name in ('True-Name Nemesis', 'Grizzly Bears', "Farideh, Devil's Chosen")]
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, population, k: list(population)[:k])
        spell(s, 'Sinister Waltz', {'B': 1, 'R': 1, 'C': 3}, [c.id for c in targets], target_counts=[3])
        assert s.state.rules.decision is not None
        expected = [c.id for c in targets]
    saved = tmp_path / (kind + '.json')
    saved.write_text(s.state.model_dump_json())
    code = r'''
import json, secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, kind, expected = sys.argv[1:]
expected = json.loads(expected)
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
secrets.SystemRandom.sample = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('random partition repeated'))
d = s.state.rules.decision
option = 'yes' if kind == 'boarding' else next(o.id for o in d.options if o.id == 'p2')
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(30):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
if kind == 'boarding':
    assert s.state.cards[expected[0]].zone == 'p1:exile'
    assert any(p.object_id == s.state.rules.object_id(expected[0]) for p in s.state.rules.permissions)
else:
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in expected[:2])
    assert s.state.cards[expected[2]].zone == 'p1:library'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), kind, json.dumps(expected)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_wild_swing_all_targets_illegal_fizzles_without_randomizing(cards, monkeypatch):
    import secrets
    s = setup(cards)
    targets = [put(s, name, 'battlefield', 'p2') for name in ('Grizzly Bears', 'Chaos Dragon', "Farideh, Devil's Chosen")]
    spell(s, 'Wild Swing', {'R': 1, 'C': 3}, [c.id for c in targets], target_counts=[3], finish=False)
    for target in targets:
        act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'hand'})
    monkeypatch.setattr(secrets.SystemRandom, 'choice', lambda *a: (_ for _ in ()).throw(AssertionError('fizzled ability randomized')))
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p2:hand' for c in targets)
    roundtrip(s)


def test_purse_source_blinked_does_not_pass_new_incarnation(cards, monkeypatch):
    s = setup(cards)
    source = put(s, "Bucknard's Everfull Purse", 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    faces(monkeypatch, [3])
    settle(s)
    assert s.state.cards[source.id].controller == 'p1'
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 3
    roundtrip(s)


def test_tyrant_requires_three_before_sacrifice_then_can_return_sacrificed_source(cards, monkeypatch):
    import secrets

    from app.game.errors import ActionError
    from app.rules import costs, scripts
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Tomb Tyrant', 'battlefield')
    to_phase(s, 'main1', turn=4)
    zombies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name in ('Dregscape Zombie', 'Twisted Abomination')]
    assert len(zombies) == 3
    for c in zombies[:2]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 2})
    ab = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities[1]
    cost = scripts.parse_ability_cost(ab.cost, card_name=source.name)
    index = next(i for i, c in enumerate(cost.components) if c.kind == costs.SACRIFICE and c.selector)
    choices = [{'component': index, 'cards': [source.id]}]
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], cost_choices=choices)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[zombies[2].id], to={'player': 'p1', 'zone': 'graveyard'})
    monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda self, population, k: [source.id])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], cost_choices=choices)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('result,expected', [(1, 3), (6, 6), (12, 26)])
def test_sword_attack_counter_then_frozen_combat_damage_roll(cards, monkeypatch, result, expected):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    sword = put(s, 'Sword of Hours', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=12 if result == 12 else 2)
    act(s, 'p1', type='attach', card_ids=[sword.id], to=bear.id)
    to_phase(s, 'declare_attackers', turn=4)
    faces(monkeypatch, [result])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == expected
    roundtrip(s)


def test_farideh_group_trigger_draws_after_source_departure(cards, monkeypatch):
    s = setup(cards)
    source = put(s, "Farideh, Devil's Chosen", 'battlefield')
    faces(monkeypatch, [20])
    rolling_spell = spell(s, "Diviner's Portent", {'U': 3}, x_value=0, finish=False)
    before = len(s.state.zones.get('p1:hand', []))
    while s.state.cards[rolling_spell.id].zone == 'stack':
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before + 1
    roundtrip(s)


@pytest.mark.parametrize('name', [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/random_receipt_consumers_cards.json').read_text())[:21] if c['name'] not in ('Chaos Dragon', 'Celebr-8000', 'Slight Malfunction')])
def test_canonical_complete_printed_lines_are_supported(cards, name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_boarding_acceptance_consumes_turn_even_when_revealed_mana_value_too_high(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Priority Boarding', 'battlefield')
    top = put(s, 'Wild Endeavor', 'hand')
    act(s, 'p1', type='move', card_ids=[top.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    faces(monkeypatch, [2, 6])
    spell(s, "Pair o' Dice Lost", {'G': 2, 'C': 3})
    assert s.state.rules.decision.resume['kind'] == 'boarding'
    answer(s, ['yes'])
    assert s.state.rules.decision is None
    assert s.state.rules.once_per_turn['receipt_boarding:' + s.state.rules.object_id(source.id)] == s.state.turn.number
    assert s.state.zones['p1:library'][0] == top.id
    assert not s.state.rules.permissions
    roundtrip(s)


def test_house_treasure_payment_receipt_survives_fresh_process_before_roll(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_wave18b_mana import treasure
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Mr. House, President and CEO', 'battlefield')
    to_phase(s, 'main1', turn=4)
    token = treasure(s)
    act(s, 'p1', type='activate_ability', card_id=token.id, ability=0, mana_choice='R')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    saved = tmp_path / 'house.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: 4
for _ in range(30):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.rules.turn_log.rolled['p1'] == 2
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('natural,draws', [(1, 0), (20, 1)])
def test_farideh_live_source_gains_keywords_even_on_low_group(cards, monkeypatch, natural, draws):
    s = setup(cards)
    source = put(s, "Farideh, Devil's Chosen", 'battlefield')
    faces(monkeypatch, [natural])
    spell(s, "Diviner's Portent", {'U': 3}, x_value=0, finish=False)
    before = len(s.state.zones.get('p1:hand', []))
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before + draws
    assert {'flying', 'menace'} <= Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    roundtrip(s)


def test_sword_still_rolls_after_equipped_host_dies_in_combat(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    sword = put(s, 'Sword of Hours', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[sword.id], to=bear.id)
    to_phase(s, 'declare_attackers', turn=4)
    blocker = put(s, 'Chaos Dragon', 'battlefield', 'p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': bear.id}])
    faces(monkeypatch, [12])
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)
