"""Derived source qualities use actual spell X, live static values and exact own choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, player_shields, protection, replacements, targets
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/source_quality_protection_cards.json'
NAMES = ['Rebbec, Architect of Ascension', 'Haktos the Unscarred', 'Lavabrink Venturer', 'Mirror Golem', 'Runed Halo', 'Tam, Mindful First-Year']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='sqp', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Island']
    s = three(cards, names, names, names)
    hold(s)
    return s


def ch(s, c):
    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id])


def protects(s, c, mv):
    return bool(protection.protected_from(ch(s, c), Characteristics(name='Source', mana_value=mv)))


def spell(s, name, mana, target=(), player='p1', finish=True, **extra):
    priority(s, player)
    c = put(s, name, 'hand', player)
    act(s, player, type='add_mana', player=player, mana=mana)
    act(s, player, type='cast_spell', card_id=c.id, targets=list(target), **extra)
    if finish:
        settle(s)
    return s.state.cards[c.id]


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_fully_supported(cards, name):
    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == 'FULL', r.manual_parts


def test_rebbec_current_artifact_values_include_zero_and_change_with_controller(cards):
    s = setup(cards)
    source = put(s, 'Rebbec, Architect of Ascension', 'battlefield')
    target = put(s, 'Ornithopter', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    assert protects(s, target, 0) and protects(s, target, 1) and not protects(s, target, 2)
    act(s, 'p1', type='set_controller', card_ids=[ring.id], player='p2')
    assert not protects(s, target, 1) and protects(s, target, 0)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    assert not protects(s, target, 0)
    roundtrip(s)


def test_rebbec_prospective_and_resolving_x_use_announced_value(cards):
    s = setup(cards)
    put(s, 'Rebbec, Architect of Ascension', 'battlefield')
    target = put(s, 'Ornithopter', 'battlefield')
    put(s, 'Sol Ring', 'battlefield')
    blocked = put(s, 'Blaze', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    with pytest.raises(ActionError, match='legal target'):
        act(s, 'p1', type='cast_spell', card_id=blocked.id, x_value=0, targets=[target.id])
    spell(s, 'Blaze', {'R': 1, 'C': 1}, [target.id], x_value=1)
    assert s.state.cards[target.id].damage == 1
    roundtrip(s)


def test_rebbec_x_above_forty_and_multiple_x_symbols_do_not_change_base_mv(cards):
    s = setup(cards)
    put(s, 'Rebbec, Architect of Ascension', 'battlefield')
    target = put(s, 'Ornithopter', 'battlefield')
    spell(s, 'Blaze', {'R': 1, 'C': 41}, [target.id], x_value=41)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    source = spell(s, 'Astral Cornucopia', {'C': 6}, x_value=2, finish=False)
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.ch(s.state.cards[source.id]).mana_value == 0
    assert targets.source_of(plan, source.id, True).mana_value == 6
    settle(s)
    assert ch(s, source).mana_value == 0
    roundtrip(s)


@pytest.mark.parametrize('parity', ['Odd', 'Even'])
def test_lavabrink_native_enter_choice_zero_and_unbounded_parity(cards, parity):
    s = setup(cards)
    source = spell(s, 'Lavabrink Venturer', {'W': 1, 'C': 2})
    answer(s, [parity])
    assert s.state.cards[source.id].choices['Chosen quality'] == parity
    for value in [0, 1, 2, 49, 1000, 1001]:
        assert protects(s, source, value) == (value % 2 == (1 if parity == 'Odd' else 0))
    roundtrip(s)


def test_lavabrink_no_choice_gives_no_protection_and_copies_choose_anew(cards):
    s = setup(cards)
    original = put(s, 'Lavabrink Venturer', 'battlefield')
    assert not protects(s, original, 0) and not protects(s, original, 1)
    clone = spell(s, 'Clone', {'U': 1, 'C': 3})
    answer(s, [original.id])
    answer(s, ['Even'])
    assert protects(s, clone, 0) and not protects(s, clone, 1)
    assert not protects(s, original, 0)
    roundtrip(s)


def test_haktos_random_before_entry_is_recorded_once_and_preview_is_entropy_free(cards):
    s = setup(cards)
    source = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2}, finish=False)
    before = s.state.model_dump_json()
    class NoEntropy:
        def choice(self, values):
            raise AssertionError('read-only entry preview consumed entropy')
    view = Plan(s.state, 'p1', cards, NoEntropy())
    preview = replacements.entry_plan(view, s.state.cards[source.id], 'p1')
    assert preview['choice']['random'] and preview['choice']['options'] == ['2', '3', '4']
    assert s.state.model_dump_json() == before
    settle(s)
    number = int(s.state.cards[source.id].choices['Chosen number'])
    assert number in {2, 3, 4}
    for value in [0, 1, 2, 3, 4, 41, 1001]:
        assert protects(s, source, value) == (value != number)
    assert len([entry for entry in s.state.log if 'Random entering choice' in str(entry)]) == 1
    roundtrip(s)


def test_haktos_no_choice_and_ability_loss_do_not_invent_protection(cards):
    s = setup(cards)
    source = put(s, 'Haktos the Unscarred', 'battlefield')
    assert not protects(s, source, 0)
    source = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2})
    put(s, 'Humility', 'battlefield')
    assert not protects(s, source, 0)
    roundtrip(s)


def test_runed_halo_name_choice_protects_player_and_follows_source_control(cards):
    s = setup(cards)
    source = spell(s, 'Runed Halo', {'W': 2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, name='Lightning Bolt')
    settle(s)
    plan = Plan(s.state, 'p1', cards, None)
    bolt = Characteristics(name='Lightning Bolt', colors=frozenset('R'))
    assert not player_shields.can_target(plan, 'p2', 'p1', bolt)
    assert player_shields.can_target(plan, 'p2', 'p1', Characteristics(name='Blaze'))
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    plan = Plan(s.state, 'p1', cards, None)
    assert player_shields.can_target(plan, 'p2', 'p1', bolt) and not player_shields.can_target(plan, 'p1', 'p2', bolt)
    roundtrip(s)


def test_mirror_golem_actual_imprint_grants_all_linked_types_then_loses_them(cards):
    s = setup(cards)
    target = put(s, 'Ornithopter', 'graveyard', 'p2')
    source = spell(s, 'Mirror Golem', {'C': 6})
    answer(s, [target.id])
    d = s.state.rules.decision
    if d is not None:
        answer(s, [next(o.id for o in d.options if o.id not in ('no', 'decline'))])
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert protection.protected_from(ch(s, source), Characteristics(name='Artifact', types=frozenset({'Artifact'})))
    assert protection.protected_from(ch(s, source), Characteristics(name='Creature', types=frozenset({'Creature'})))
    assert not protection.protected_from(ch(s, source), Characteristics(name='Instant', types=frozenset({'Instant'})))
    act(s, 'p2', type='move', card_ids=[target.id], to={'zone': 'hand'})
    assert not protection.protected_from(ch(s, source), Characteristics(name='Creature', types=frozenset({'Creature'})))
    roundtrip(s)


def test_tam_live_own_colors_limit_opposing_targeting_only(cards):
    s = setup(cards)
    source = put(s, 'Tam, Mindful First-Year', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    colorless = put(s, 'Ornithopter', 'battlefield')
    def legal(c, player, color):
        return c.id in targets.legal_targets(Plan(s.state, player, cards, None), 'creature', player,
                                             Characteristics(name='Spell', colors=frozenset(color)))
    assert not legal(own, 'p2', 'G') and legal(own, 'p1', 'G')
    assert legal(own, 'p2', 'R') and legal(other, 'p1', 'G') and legal(source, 'p2', 'G')
    assert legal(colorless, 'p2', 'G')
    assert not protection.protected_from(ch(s, own), Characteristics(name='Creature', colors=frozenset('G')))
    roundtrip(s)


@pytest.mark.parametrize('number', [2, 3, 4])
def test_haktos_each_finite_random_result_is_automatic_and_not_a_die_roll(cards, monkeypatch, number):
    s = setup(cards)
    put(s, 'Wyll, Blade of Frontiers', 'battlefield')
    put(s, 'Pixie Guide', 'battlefield')
    calls = []
    class Fixed:
        def choice(self, values):
            calls.append(tuple(values))
            return str(number)
    import app.game.resolve as resolver

    monkeypatch.setattr(resolver._rng, 'choice', Fixed().choice)
    source = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2})
    assert calls == [('2', '3', '4')]
    assert s.state.cards[source.id].choices['Chosen number'] == str(number)
    assert not protects(s, source, number) and protects(s, source, number + 1)
    assert not any(e.counter == 'roll_die' for e in s.state.rules.events)
    roundtrip(s)


def test_actual_lavabrink_x_targeting_and_damage_use_same_effective_mv(cards):
    s = setup(cards)
    source = spell(s, 'Lavabrink Venturer', {'W': 1, 'C': 2})
    answer(s, ['Odd'])
    spell(s, 'Blaze', {'R': 1, 'C': 1}, [source.id], x_value=1)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 1
    with pytest.raises(ActionError, match='legal target'):
        spell(s, 'Blaze', {'R': 1, 'C': 2}, [source.id], x_value=2)
    roundtrip(s)


def test_actual_crackle_multiple_x_targeting_uses_three_x_symbols(cards):
    s = setup(cards)
    source = spell(s, 'Lavabrink Venturer', {'W': 1, 'C': 2})
    answer(s, ['Odd'])
    # {X}{X}{X}{R}{R}: X1 has MV5 and is protected, X2 has MV8 and is legal.
    with pytest.raises(ActionError):
        spell(s, 'Crackle with Power', {'R': 2, 'C': 3}, [source.id], x_value=1, target_counts=[1])
    spell(s, 'Crackle with Power', {'R': 2, 'C': 6}, [source.id], x_value=2, target_counts=[1])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_runed_halo_actual_damage_and_real_illegal_spell_target(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    halo = spell(s, 'Runed Halo', {'W': 2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, name='Goblin Chainwhirler')
    settle(s)
    to_phase(s, 'main1', turn=2)
    spell(s, 'Goblin Chainwhirler', {'R': 3}, player='p2')
    assert s.state.players['p1'].life == 40 and s.state.players['p3'].life == 39
    act(s, 'p1', type='move', card_ids=[halo.id], to={'zone': 'hand'})
    roundtrip(s)


def test_runed_halo_split_name_quality_uses_actual_cast_face(cards):
    s = setup(cards)
    spell(s, 'Runed Halo', {'W': 2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, name='Tear')
    settle(s)
    split = put(s, 'Wear // Tear', 'hand', 'p2')
    plan = Plan(s.state, 'p2', cards, None)
    assert player_shields.can_target(plan, 'p2', 'p1', targets.source_of(plan, split.id, True, face=0))
    assert not player_shields.can_target(plan, 'p2', 'p1', targets.source_of(plan, split.id, True, face=1))
    assert not player_shields.can_target(plan, 'p2', 'p1', targets.source_of(plan, split.id, True, fused=True))
    roundtrip(s)


def test_tam_native_all_colors_changes_hexproof_then_allows_own_spells(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, 'Tam, Mindful First-Year', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])
    settle(s)
    assert ch(s, target).colors == frozenset('WUBRG')
    with pytest.raises(ActionError, match='legal target'):
        spell(s, 'Lightning Bolt', {'R': 1}, [target.id], player='p2')
    spell(s, 'Giant Growth', {'G': 1}, [target.id])
    assert ch(s, target).pt == (5, 5)
    roundtrip(s)


def test_mirror_golem_copy_has_its_own_linked_imprint(cards):
    s = setup(cards)
    first = put(s, 'Ornithopter', 'graveyard', 'p2')
    golem = spell(s, 'Mirror Golem', {'C': 6})
    answer(s, [first.id])
    if s.state.rules.decision:
        answer(s, [next(o.id for o in s.state.rules.decision.options if o.id not in ('no', 'decline'))])
    second = put(s, 'Lightning Bolt', 'graveyard', 'p3')
    clone = spell(s, 'Clone', {'U': 1, 'C': 3})
    answer(s, [golem.id])
    answer(s, [second.id])
    if s.state.rules.decision:
        answer(s, [next(o.id for o in s.state.rules.decision.options if o.id not in ('no', 'decline'))])
    creature = Characteristics(name='Creature', types=frozenset({'Creature'}))
    instant = Characteristics(name='Instant', types=frozenset({'Instant'}))
    assert protection.protected_from(ch(s, golem), creature) and not protection.protected_from(ch(s, golem), instant)
    assert protection.protected_from(ch(s, clone), instant) and not protection.protected_from(ch(s, clone), creature)
    roundtrip(s)


def test_paid_x_copy_is_offered_when_zero_x_has_no_legal_target(cards):
    s = setup(cards)
    target = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2})
    number = int(s.state.cards[target.id].choices['Chosen number'])
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    for player in ['p1', 'p2', 'p3']:
        put(s, 'Ivory Mask', 'battlefield', player)
    original = put(s, 'Blaze', 'graveyard')
    saga = put(s, 'The Tale of Tamiyo', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[saga.id], kind='lore', delta=3)
    spell(s, 'Contentious Plan', {'U': 1, 'C': 1})
    answer(s, [saga.id])
    answer(s, [original.id])
    d = s.state.rules.decision
    assert d is not None and d.options, d
    copy = d.options[0].id
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': number - 1})
    answer(s, [copy])
    assert s.state.rules.decision.resume['step'] == 'free_x'
    answer(s, [f'x:{number - 1}'])
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {target.id}
    answer(s, [target.id])
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert copy not in s.state.cards
    roundtrip(s)


def test_haktos_enters_under_humility_has_no_random_answer_after_ability_returns(cards):
    s = setup(cards)
    humility = put(s, 'Humility', 'battlefield')
    source = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2})
    assert 'Chosen number' not in s.state.cards[source.id].choices
    act(s, 'p1', type='move', card_ids=[humility.id], to={'zone': 'exile'})
    assert not protects(s, source, 0) and not protects(s, source, 4)
    roundtrip(s)


def test_haktos_real_reanimation_uses_automatic_entry_runner(cards):
    s = setup(cards)
    source = put(s, 'Haktos the Unscarred', 'graveyard')
    spell(s, 'Reanimate', {'B': 1}, [source.id])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    number = int(s.state.cards[source.id].choices['Chosen number'])
    assert number in {2, 3, 4} and not protects(s, source, number)
    assert s.state.players['p1'].life == 36
    roundtrip(s)


def test_saved_clone_of_haktos_chooses_fresh_number_once_in_new_process(cards, tmp_path, monkeypatch):
    import subprocess
    import sys

    import app.game.resolve as resolver

    s = setup(cards)
    monkeypatch.setattr(resolver._rng, 'choice', lambda values: '2')
    original = spell(s, 'Haktos the Unscarred', {'R': 2, 'W': 2})
    assert s.state.cards[original.id].choices['Chosen number'] == '2'
    clone = spell(s, 'Clone', {'U': 1, 'C': 3})
    assert s.state.rules.decision is not None
    roundtrip(s)
    path = tmp_path / 'haktos-clone.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
import app.game.resolve as resolver
path, database, original, clone = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
calls = []
def pick(values):
    calls.append(tuple(values))
    return '3'
resolver._rng.choice = pick
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [original]})
for _ in range(20):
    d = s.state.rules.decision
    if d is not None:
        assert clone in {o.id for o in d.options}, d
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [clone]})
    elif s.state.zones['stack']:
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert calls == [('2','3','4')]
assert s.state.cards[clone].choices['Chosen number'] == '3'
assert s.state.cards[original].zone == 'p1:graveyard'
from app.rules import protection
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
ch = Plan(s.state, 'p1', repo, None).ch(s.state.cards[clone])
assert protection.protected_from(ch, Characteristics(name='Two', mana_value=2))
assert not protection.protected_from(ch, Characteristics(name='Three', mana_value=3))
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), original.id, clone.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_real_split_spell_targeting_uses_selected_halfs_mana_value(cards):
    s = setup(cards)
    put(s, 'Rebbec, Architect of Ascension', 'battlefield', 'p2')
    put(s, 'Coalition Relic', 'battlefield', 'p2')  # Protects from combined Wear+Tear MV3.
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    spell(s, 'Wear // Tear', {'R': 1, 'C': 1}, [target.id], face=0)  # Wear alone has MV2.
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_real_adventure_spell_targeting_uses_adventure_not_creature_mana_value(cards):
    s = setup(cards)
    target = spell(s, 'Lavabrink Venturer', {'W': 1, 'C': 2})
    answer(s, ['Odd'])
    spell(s, 'Bonecrusher Giant // Stomp', {'R': 1, 'C': 1}, [target.id], face=1)  # Stomp MV2, Giant MV3.
    assert s.state.cards[target.id].zone == 'p1:battlefield' and s.state.cards[target.id].damage == 2
    roundtrip(s)


def test_spell_snare_counters_actual_wear_half_by_its_shared_base_value(cards):
    from app.rules import stack_interaction

    s = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    wear = spell(s, 'Wear // Tear', {'R': 1, 'C': 1}, [target.id], face=0, finish=False)
    assert ch(s, wear).name == 'Wear' and ch(s, wear).mana_value == 2
    assert stack_interaction.mana_value(s.state.cards[wear.id], ch(s, wear)) == 2
    oid = s.state.rules.object_id(wear.id)
    spell(s, 'Spell Snare', {'U': 1}, [wear.id], player='p2')
    source = targets.source_of(Plan(s.state, 'p1', cards, None), wear.id, True, object_id=oid)
    assert source.name == 'Wear' and source.mana_value == 2 and source.colors == frozenset('R')
    assert s.state.cards[wear.id].zone == 'p1:graveyard' and s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_negate_counters_actual_stomp_adventure_by_its_instant_type(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    stomp = spell(s, 'Bonecrusher Giant // Stomp', {'R': 1, 'C': 1}, [target.id], face=1, finish=False)
    assert ch(s, stomp).name == 'Stomp' and ch(s, stomp).types == frozenset({'Instant'})
    spell(s, 'Negate', {'U': 1, 'C': 1}, [stomp.id], player='p2')
    assert s.state.cards[stomp.id].zone == 'p1:graveyard' and not s.state.cards[target.id].damage
    roundtrip(s)


def test_copied_selected_split_spell_keeps_half_characteristics(cards):
    s = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    wear = spell(s, 'Wear // Tear', {'R': 1, 'C': 1}, [target.id], face=0, finish=False)
    favor = put(s, 'Return the Favor', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0], targets=[wear.id])
    for _ in range(12):
        copies = [cid for cid, entry in s.state.rules.stack.items() if cid != wear.id and entry.kind == 'spell' and entry.name == 'Wear']
        if copies:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert len(copies) == 1
    copied = s.state.cards[copies[0]]
    assert ch(s, copied).name == 'Wear' and ch(s, copied).mana_value == 2 and ch(s, copied).colors == frozenset('R')
    if s.state.rules.decision is not None:
        answer(s, [target.id])
    else:
        settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_actual_fused_split_spell_keeps_combined_base_value(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    halo = put(s, 'Runed Halo', 'battlefield', 'p2')
    fused = spell(s, 'Wear // Tear', {'R': 1, 'W': 1, 'C': 1}, [ring.id, halo.id],
                  fuse=True, target_counts=[1, 1], finish=False)
    assert ch(s, fused).name == 'Wear // Tear' and ch(s, fused).mana_value == 3
    assert ch(s, fused).colors == frozenset('RW')
    settle(s)
    assert s.state.cards[ring.id].zone == 'p2:graveyard' and s.state.cards[halo.id].zone == 'p2:graveyard'
    roundtrip(s)
