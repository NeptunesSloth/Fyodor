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
    data = json.loads((Path(__file__).parent / 'fixtures/coin_outcomes_cards.json').read_text())
    existing = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(data):
        existing[c['name']] = card(c['name'], set_code='coi', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/coin_outcomes_cards.json').read_text())]
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


def test_thumb_actual_choice_ignores_other_flip_and_emits_only_one_win(cards, monkeypatch):
    s = setup(cards)
    put(s, "Krark's Thumb", 'battlefield')
    encounter = put(s, 'Chance Encounter', 'battlefield')
    faces(monkeypatch, [1, 0])
    saucer(s)
    assert s.state.rules.decision.resume['phase'] == 'ignore'
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 2
    answer(s, ['0'])
    assert s.state.cards[encounter.id].counters.get('luck') == 1
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 1
    roundtrip(s)


@pytest.mark.parametrize('edgar', [False, True])
def test_ral_heads_only_group_extra_turns_and_edgar_explicit_wins(cards, monkeypatch, edgar):
    s = setup(cards)
    encounter = put(s, 'Chance Encounter', 'battlefield')
    if edgar:
        put(s, 'Edgar, King of Figaro', 'battlefield')
    ral = put(s, 'Ral Zarek', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=ral.id, kind='loyalty', value=7)
    faces(monkeypatch, [1, 0, 1, 0, 1, 0])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=ral.id, ability=2)
    settle(s)
    assert s.state.cards[ral.id].zone == 'p1:graveyard'
    assert len(s.state.rules.extra_turns) == (5 if edgar else 3)
    assert s.state.cards[encounter.id].counters.get('luck', 0) == (5 if edgar else 0)
    saucer(s)  # A later distinct group isn't forced by Edgar.
    assert not [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']
    roundtrip(s)


def test_mana_clash_continue_does_not_run_sba_mid_resolution_below_zero(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Mana Clash', 'hand')
    encounter = put(s, 'Chance Encounter', 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=-39)
    faces(monkeypatch, [v for _ in range(16) for v in (0, 1)] + [1, 1])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'coin_process'
    assert s.state.players['p1'].life == -15
    assert 'p1' not in s.state.rules.lost
    assert s.state.cards[source.id].zone == 'stack'
    roundtrip(s)
    answer(s, ['continue'])
    assert 'p1' in s.state.rules.lost
    assert s.state.players['p2'].life == 40
    assert s.state.cards[encounter.id].counters.get('luck', 0) == 0
    roundtrip(s)


def test_mana_clash_thumb_sees_opponent_result_before_ignoring_own_flip(cards, monkeypatch):
    s = setup(cards)
    put(s, "Krark's Thumb", 'battlefield')
    faces(monkeypatch, [1, 1, 0])  # Opponent leaf, then the two leaves of the controller's original coin.
    spell(s, 'Mana Clash', {'R': 1}, ['p2'])
    assert s.state.rules.decision.resume['phase'] == 'ignore'
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 3
    assert any(e.actor == 'p2' and any('heads' in (p.t or '') for p in e.parts) for e in s.state.log)
    answer(s, ['0'])
    assert s.state.players['p1'].life == s.state.players['p2'].life == 40
    roundtrip(s)


def test_crazed_firecat_more_than_old_thousand_flip_cap_finishes_only_on_loss(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1] * 1001 + [0])
    source = spell(s, 'Crazed Firecat', {'R': 2, 'C': 5})
    checkpoints = 0
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] in ('coin_loop', 'coin_group')
        assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
        answer(s, ['continue'])
        checkpoints += 1
    assert checkpoints >= 2
    assert s.state.cards[source.id].counters.get('+1/+1') == 1001
    roundtrip(s)


def test_ral_guest_skips_exact_heads_count_for_target_opponent(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Ral Zarek, Guest Lecturer', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=7)
    faces(monkeypatch, [1, 1, 0, 0, 1])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3, targets=['p3'])
    settle(s)
    assert len(s.state.rules.skips) == 3
    assert all(d['player'] == 'p3' and d['what'] == 'turn' for d in s.state.rules.skips)
    roundtrip(s)


def test_rakdos_destroys_all_tails_creatures_simultaneously_but_never_demons(cards, monkeypatch):
    s = setup(cards)
    bears = [put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p1', 'p2', 'p3']]
    faces(monkeypatch, [0, 0, 0])
    source = spell(s, 'Rakdos, the Showstopper', {'B': 1, 'R': 1, 'C': 4})
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert all(s.state.cards[c.id].zone == c.owner + ':graveyard' for c in bears)
    deaths = [e for e in s.state.rules.turn_log.left if e.card in {c.id for c in bears}]
    assert len(deaths) == 3
    roundtrip(s)


def test_mutalith_keeps_each_opponents_own_coin_association(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 0])
    spell(s, 'Mutalith Vortex Beast', {'U': 1, 'R': 1, 'C': 4}, finish=False)
    before = len(s.state.zones.get('p1:hand', []))
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before + 1
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_goblin_assassin_all_players_flip_before_apnap_sacrifices(cards, monkeypatch):
    s = setup(cards)
    bears = {p: put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p1', 'p2', 'p3']}
    for player in ['p2', 'p3']:
        put(s, 'Okaun, Eye of Chaos', 'battlefield', player)
    faces(monkeypatch, [1, 0, 0])
    source = spell(s, 'Goblin Assassin', {'R': 2, 'C': 3})
    assert s.state.rules.decision.player == 'p2'
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 3
    answer(s, [bears['p2'].id])
    assert s.state.rules.decision.player == 'p3'
    assert s.state.cards[bears['p2'].id].zone == 'p2:battlefield'  # Decisions before one simultaneous sacrifice.
    answer(s, [bears['p3'].id])
    assert s.state.cards[source.id].zone == s.state.cards[bears['p1'].id].zone == 'p1:battlefield'
    assert all(s.state.cards[bears[p].id].zone == p + ':graveyard' for p in ['p2', 'p3'])
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_planar_chaos_uses_actual_casting_player_and_kept_result(cards, monkeypatch, heads):
    s = setup(cards)
    put(s, 'Planar Chaos', 'battlefield', 'p2')
    source = put(s, 'Sol Ring', 'hand')
    faces(monkeypatch, [int(heads)])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:battlefield' if heads else 'p1:graveyard')
    assert any(e.actor == 'p1' and any('flipped a coin:' in (p.t or '') for p in e.parts) for e in s.state.log)
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_fiery_gambit_actual_stop_or_loss_branches(cards, monkeypatch, heads):
    s = setup(cards)
    victim = put(s, 'Rakdos, the Showstopper', 'battlefield', 'p2')
    settle(s)  # No eligible creatures, no coin needed for Rakdos.
    faces(monkeypatch, [int(heads)] * 4)
    spell(s, 'Fiery Gambit', {'R': 1, 'C': 2}, [victim.id])
    if heads:
        for _ in range(3):
            answer(s, ['continue'])
        before = len(s.state.zones.get('p1:hand', []))
        answer(s, ['stop'])
        assert len(s.state.zones.get('p1:hand', [])) == before + 9
        assert s.state.players['p2'].life == s.state.players['p3'].life == 34
        assert s.state.cards[victim.id].damage == 3
    else:
        assert s.state.players['p2'].life == s.state.players['p3'].life == 40
        assert s.state.cards[victim.id].damage == 0
    roundtrip(s)


def attack_ready(s, source):
    from tests.test_rules_wave30m_durations import stops, to_phase
    stops(s, 'declare_attackers', 'declare_blockers', 'end_combat', 'end')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)


def test_goblin_traprunner_creates_actual_tapped_attacking_tokens_without_attack_events(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Goblin Traprunner', 'battlefield')
    faces(monkeypatch, [1, 0, 1])
    attack_ready(s, source)
    while s.state.rules.decision is not None and s.state.rules.decision.kind != 'declare_blockers':
        d = s.state.rules.decision
        assert any(o.id == 'p3' for o in d.options)
        answer(s, ['p3'])
    tokens = [c for c in s.state.cards.values() if c.token and c.name == 'Goblin' and c.zone == 'p1:battlefield']
    assert len(tokens) == 2
    assert all(c.tapped and c.is_attacking for c in tokens)
    assert s.state.rules.turn_log.attackers['p1'] == [s.state.rules.object_id(source.id)]
    roundtrip(s)


@pytest.mark.parametrize('values,keyword', [([1, 1], 'double strike'), ([0, 0], 'menace'), ([1, 0], None)])
def test_two_headed_giant_uses_both_actual_faces(cards, monkeypatch, values, keyword):
    from app.rules.plan import Plan
    s = setup(cards)
    source = put(s, 'Two-Headed Giant', 'battlefield')
    faces(monkeypatch, values)
    attack_ready(s, source)
    keywords = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    assert ('double strike' in keywords) == (keyword == 'double strike')
    assert ('menace' in keywords) == (keyword == 'menace')
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_tide_of_war_sacrifices_exact_blocking_or_blocked_creatures(cards, monkeypatch, heads):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    put(s, 'Tide of War', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack_ready(s, attacker)
    to_phase(s, 'declare_blockers', turn=4)
    faces(monkeypatch, [int(heads)])
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    assert s.state.cards[blocker.id].zone == ('p2:graveyard' if heads else 'p2:battlefield')
    assert s.state.cards[attacker.id].zone == ('p1:battlefield' if heads else 'p1:graveyard')
    if heads:
        assert attacker.id in s.state.rules.blocked
    roundtrip(s)


def test_fickle_efreet_delays_flip_until_end_of_combat_then_opponent_control(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Fickle Efreet', 'battlefield')
    faces(monkeypatch, [0])
    attack_ready(s, source)
    assert s.state.rules.delayed
    assert not [e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    answer(s, ['p3'])
    assert s.state.cards[source.id].controller == 'p3'
    roundtrip(s)


def test_goblin_kites_actual_granted_flying_and_delayed_losing_sacrifice(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import stops, to_phase
    s = setup(cards)
    source = put(s, 'Goblin Kites', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[bear.id], sources=[])
    settle(s)
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).keywords
    faces(monkeypatch, [0])
    stops(s, 'end')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_frenetic_sliver_stacked_abilities_only_flip_once_after_source_departure(cards, monkeypatch, heads):
    from app.rules.plan import Plan
    s = setup(cards)
    source = put(s, 'Frenetic Sliver', 'battlefield')
    index = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated' and 'flip a coin' in a.text.lower())
    faces(monkeypatch, [int(heads)])
    priority(s, 'p1')
    for _ in range(2):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:exile' if heads else 'p1:graveyard')
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 1
    if heads:
        from tests.test_rules_wave30m_durations import stops, to_phase
        stops(s, 'end')
        to_phase(s, 'end', turn=1)
        settle(s)
        assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('retry', [True, False])
def test_crooked_scales_pays_real_repeat_cost_keeps_original_targets(cards, monkeypatch, retry):
    from tests.game_helpers import mana_pool
    s = setup(cards)
    source = put(s, 'Crooked Scales', 'battlefield')
    mine = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [0, 1] if retry else [0])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 7})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[theirs.id, mine.id], target_counts=[1, 1], sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'pay_or_sacrifice'
    roundtrip(s)
    answer(s, ['pay' if retry else 'decline'])
    assert s.state.cards[mine.id].zone == ('p1:battlefield' if retry else 'p1:graveyard')
    assert s.state.cards[theirs.id].zone == ('p2:graveyard' if retry else 'p2:battlefield')
    assert mana_pool(s) == ({} if retry else {'C': 3})
    assert s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_goblin_lyre_sacrificed_source_uses_native_lki_and_correct_creature_controller(cards, monkeypatch, heads):
    s = setup(cards)
    source = put(s, 'Goblin Lyre', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Frenetic Sliver', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    faces(monkeypatch, [int(heads)])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'], sources=[])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    settle(s)
    assert s.state.players['p1'].life == (40 if heads else 39)
    assert s.state.players['p2'].life == (38 if heads else 40)
    roundtrip(s)


@pytest.mark.parametrize('heads', [True, False])
def test_breeches_actual_optional_artifact_payment_and_separate_coin_reflexive(cards, monkeypatch, heads):
    s = setup(cards)
    source = put(s, 'Breeches, the Blastmaker', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    faces(monkeypatch, [int(heads)])
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    saw_reflexive = False
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        saw_reflexive |= any(t.ability.get('trigger') == 'reflexive' for t in s.state.rules.pending_triggers)
        saw_reflexive |= any(t.kind == 'trigger' and t.source_card == source.id and any(e.get('do') in ('copy_spell', 'damage') for e in t.effects) for t in s.state.rules.stack.values())
        ids = {o.id for o in d.options}
        if 'pay' in ids:
            answer(s, ['pay'])
        elif ring.id in ids:
            answer(s, [ring.id])
        elif 'keep' in ids:
            answer(s, ['keep'])
        elif 'same' in ids:
            answer(s, ['same'])
        elif 'p2' in ids:
            answer(s, ['p2'])
        else:
            raise AssertionError(d)
    assert saw_reflexive
    assert s.state.cards[ring.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.players['p2'].life == (40 if heads else 39)
    assert s.state.players['p3'].life == (31 if heads else 34)
    roundtrip(s)


@pytest.mark.parametrize('kind', ['ignore', 'stop', 'clash'])
def test_native_coin_decisions_resume_in_fresh_process(cards, monkeypatch, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'ignore':
        put(s, "Krark's Thumb", 'battlefield')
        faces(monkeypatch, [1, 0])
        saucer(s)
        option = '0'
    elif kind == 'stop':
        target = put(s, 'Rakdos, the Showstopper', 'battlefield', 'p2')
        faces(monkeypatch, [1])
        spell(s, 'Fiery Gambit', {'R': 1, 'C': 2}, [target.id])
        option = 'stop'
    else:
        act(s, 'p1', type='life', player='p1', delta=-39)
        faces(monkeypatch, [v for _ in range(16) for v in [0, 1]])
        spell(s, 'Mana Clash', {'R': 1}, ['p2'])
        assert s.state.players['p1'].life == -15 and 'p1' not in s.state.rules.lost
        option = 'continue'
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind, option = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
if kind == 'clash':
    assert s.state.players['p1'].life == -15 and 'p1' not in s.state.rules.lost
    importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: 1
else:
    def forbidden(*args):
        raise AssertionError('A recorded coin was resampled on resume')
    importlib.import_module('app.game.resolve')._rng_int = forbidden
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
for _ in range(60):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
if kind == 'ignore':
    assert len([c for c in s.state.cards.values() if c.token and c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 1
elif kind == 'stop':
    victim = next(c for c in s.state.cards.values() if c.name == 'Rakdos, the Showstopper' and c.owner == 'p2')
    assert victim.damage == 3
else:
    assert 'p1' in s.state.rules.lost
    assert s.state.players['p2'].life == 40
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, option],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('first', ['thumb', 'edgar'])
def test_thumb_and_edgar_native_616_order_preserves_forced_heads_and_one_win(cards, monkeypatch, first):
    s = setup(cards)
    put(s, "Krark's Thumb", 'battlefield')
    put(s, 'Edgar, King of Figaro', 'battlefield')
    encounter = put(s, 'Chance Encounter', 'battlefield')
    faces(monkeypatch, [0, 0])
    saucer(s)
    d = s.state.rules.decision
    assert d.resume['phase'] == 'replace'
    label = "Krark's Thumb" if first == 'thumb' else 'Edgar, King of Figaro'
    answer(s, [next(o.id for o in d.options if o.label == label)])
    assert s.state.rules.decision is None
    assert s.state.cards[encounter.id].counters.get('luck') == 1
    assert len([c for c in s.state.cards.values() if c.token and c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 1
    roundtrip(s)


def test_multiple_thumbs_preserve_recursive_pairs_and_only_final_kept_loss(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Mirror Gallery', 'battlefield')
    put(s, "Krark's Thumb", 'battlefield')
    other = put(s, "Krark's Thumb", 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[other.id], player='p1')
    encounter = put(s, 'Chance Encounter', 'battlefield')
    faces(monkeypatch, [1, 0, 0, 1])
    saucer(s)
    d = s.state.rules.decision
    assert d.resume['phase'] == 'replace' and len(d.options) == 2
    answer(s, [d.options[0].id])
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 4
    for expected, selected in [(['Tails', 'Heads'], '0'), (['Heads', 'Tails'], '0'), (['Heads', 'Tails'], '1')]:
        d = s.state.rules.decision
        assert d.resume['phase'] == 'ignore'
        assert [o.label for o in d.options] == expected
        answer(s, [selected])
    assert s.state.cards[encounter.id].counters.get('luck', 0) == 0
    assert not [c for c in s.state.cards.values() if c.token and c.name == 'Treasure' and c.zone == 'p1:battlefield']
    roundtrip(s)


def test_thumb_two_simultaneous_original_coins_cannot_mix_heads_across_pairs(cards, monkeypatch):
    from app.rules.plan import Plan
    s = setup(cards)
    put(s, "Krark's Thumb", 'battlefield')
    source = put(s, 'Two-Headed Giant', 'battlefield')
    faces(monkeypatch, [1, 1, 0, 0])
    attack_ready(s, source)
    keywords = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    assert 'double strike' not in keywords and 'menace' not in keywords
    assert len([e for e in s.state.log if any('flipped a coin:' in (p.t or '') for p in e.parts)]) == 4
    roundtrip(s)
