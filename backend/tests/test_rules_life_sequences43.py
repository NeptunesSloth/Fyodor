"""Canonical native whole-card life sequences and saved continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/life_sequences43_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    return s


def test_worldfire_all_zones_order_and_spell_goes_to_graveyard(cards):
    s = game(cards)
    put(s, 'Lich\'s Tomb', 'battlefield')
    put(s, 'Platinum Emperion', 'battlefield')
    permanents = [put(s, 'Grizzly Bears', 'battlefield', p) for p in ('p1', 'p2', 'p3')]
    hands = [put(s, 'Llanowar Elves', 'hand', p) for p in ('p1', 'p2', 'p3')]
    graves = [put(s, 'Forest', 'graveyard', p) for p in ('p1', 'p2', 'p3')]
    untouched = put(s, 'Sol Ring', 'exile', 'p3')
    phased = put(s, 'Sol Ring', 'battlefield')
    from tests.game_helpers import act
    act(s, 'p1', type='phase_shift', card_ids=[phased.id], out=True)
    spell = cast(s, 'Worldfire')
    assert spell.zone == 'p1:graveyard'
    assert all(s.state.players[p].life == 1 for p in ('p1', 'p2', 'p3'))
    assert all(c.zone == c.owner + ':exile' for c in permanents + hands + graves)
    assert untouched.zone == 'p3:exile'
    assert phased.zone == 'p1:phased'
    assert all(not s.state.zones[p + ':battlefield'] and not s.state.zones[p + ':hand'] for p in ('p1', 'p2', 'p3'))
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('origin', ['hand', 'graveyard'])
@pytest.mark.parametrize('x', [0, 2])
def test_legion_graveyard_native_paid_cast_tokens_life_and_exile(cards, origin, x):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import mana, wait_priority
    from tests.test_rules_designations import settle

    s = game(cards)
    put(s, 'Sol Ring', 'battlefield')
    spell = put(s, 'Their Number Is Legion', origin)
    mana(s, C=x, B=4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[], sources=[], x_value=x)
    settle(s)
    assert spell.zone == 'p1:exile'
    tokens = [c for c in s.state.cards.values() if c.token and c.zone == 'p1:battlefield']
    assert len(tokens) == x and all(c.tapped for c in tokens)
    assert s.state.players['p1'].life == 41 + x
    roundtrip(s)


@pytest.mark.parametrize('mode,keyword', [(0, 'first strike'), (1, 'vigilance'), (2, 'lifelink')])
def test_skirmisher_each_combat_current_cohort_only(cards, mode, keyword):
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source = cast(s, 'Angelic Skirmisher')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'begin_combat')
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    choose(s, [d.options[mode].id])
    assert keyword in chars(s, source).keywords
    assert keyword in chars(s, bear).keywords
    assert keyword not in chars(s, enemy).keywords
    late = put(s, 'Llanowar Elves', 'battlefield')
    assert keyword not in chars(s, late).keywords
    roundtrip(s)


def test_skirmisher_source_gone_choice_at_resolution(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source = cast(s, 'Angelic Skirmisher')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_prefs', auto_resolve_own_triggers='off', hold_priority=True)
    to_phase(s, 'begin_combat')
    assert s.state.zones['stack'] and not s.state.rules.decision
    cast(s, 'Murder', [source.id])
    assert source.zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    choose(s, ['vigilance'])
    assert 'vigilance' in chars(s, bear).keywords
    roundtrip(s)


def test_skirmisher_opponent_combat_new_cohort_and_cleanup(cards):
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    cast(s, 'Angelic Skirmisher')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'begin_combat')
    settle(s)
    choose(s, ['first strike'])
    late = put(s, 'Llanowar Elves', 'battlefield')
    to_phase(s, 'begin_combat', turn=5)
    settle(s)
    assert 'first strike' not in chars(s, bear).keywords
    d = s.state.rules.decision
    assert d and d.player == 'p1' and s.state.turn.active_player == 'p2'
    choose(s, ['lifelink'])
    assert all('lifelink' in chars(s, c).keywords for c in (bear, late))
    roundtrip(s)


def test_cruel_ultimatum_native_sequence_and_only_opponent_target(cards):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    returned = put(s, 'Llanowar Elves', 'graveyard')
    for name in ('Forest', 'Sol Ring', 'Llanowar Elves', 'Healing Salve'):
        put(s, name, 'hand', 'p2')
    hand_before = len(s.state.zones['p1:hand'])
    before = len(s.state.zones['p2:hand'])
    spell = cast(s, 'Cruel Ultimatum', ['p2'])
    assert victim.zone == 'p2:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p2' and d.min_choices == d.max_choices == 3
    choose(s, [o.id for o in d.options[:3]])
    assert len(s.state.zones['p2:hand']) == before - 3
    assert s.state.players['p2'].life == 35
    if s.state.rules.decision:
        choose(s, [returned.id])
    assert returned.zone == 'p1:hand'
    assert spell.zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == hand_before + 4
    assert s.state.players['p1'].life == 45
    roundtrip(s)


def test_cruel_returns_own_creature_sacrificed_by_opponent(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    stolen = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[stolen.id], player='p2')
    cast(s, 'Cruel Ultimatum', ['p2'])
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [o.id for o in d.options[:d.min_choices]])
    assert stolen.zone == 'p1:hand'
    assert s.state.players['p1'].life == 45 and s.state.players['p2'].life == 35
    roundtrip(s)


def test_cruel_only_target_becomes_illegal_fizzles_every_instruction(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    before = len(s.state.zones['p1:hand'])
    returned = put(s, 'Llanowar Elves', 'graveyard')
    spell = cast(s, 'Cruel Ultimatum', ['p2'], resolve=False)
    act(s, 'p2', type='concede')
    settle(s)
    assert spell.zone == 'p1:graveyard' and returned.zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 40
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_cruel_finishes_draw_and_gain_before_simultaneous_losses(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    put(s, 'Cruel Ultimatum', 'hand')
    act(s, 'p1', type='set_life', player='p2', value=5)
    excess = list(s.state.zones['p1:library'][2:])
    if excess:
        act(s, 'p1', type='move', card_ids=excess, to={'player': 'p1', 'zone': 'exile'})
    assert len(s.state.zones['p1:library']) == 2
    cast(s, 'Cruel Ultimatum', ['p2'])
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [o.id for o in d.options[:d.min_choices]])
    assert {'p1', 'p2'} <= set(s.state.rules.lost)
    assert s.state.players['p1'].life == 45
    assert 'p3' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('name', ['Worldfire', 'Their Number Is Legion', 'Cruel Ultimatum', 'Angelic Skirmisher', 'Cosmic Rebirth', 'Benevolent Offering', "Erebos's Intervention"])
def test_canonical_full_printed_card(cards, name):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('stage', ['worldfire', 'legion', 'cruel', 'skirmisher', 'cosmic', 'cosmic_aura', 'offering', 'offering_second'])
def test_actual_pending_native_fresh_process(cards, stage, tmp_path):
    import subprocess
    import sys

    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if stage == 'worldfire':
        put(s, 'Llanowar Elves', 'hand', 'p2')
        source = cast(s, 'Worldfire', resolve=False)
    elif stage == 'legion':
        source = put(s, 'Their Number Is Legion', 'graveyard')
        mana(s, C=2, B=4)
        wait_priority(s, 'p1')
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[], x_value=2)
    elif stage in ('offering', 'offering_second'):
        put(s, 'Llanowar Elves', 'battlefield', 'p3')
        source = cast(s, 'Benevolent Offering')
        if stage == 'offering_second':
            from tests.test_rules_conditional_prevention import choose
            choose(s, ['p2'])
        assert s.state.rules.decision
    elif stage in ('cosmic', 'cosmic_aura'):
        target = put(s, 'Pacifism' if stage == 'cosmic_aura' else 'Llanowar Elves', 'graveyard')
        if stage == 'cosmic_aura':
            put(s, 'Rumbling Baloth', 'battlefield')
        source = cast(s, 'Cosmic Rebirth', [target.id])
        if stage == 'cosmic_aura':
            from tests.test_rules_conditional_prevention import choose
            choose(s, ['yes'])
        assert s.state.rules.decision
    elif stage == 'cruel':
        for name in ('Forest', 'Sol Ring', 'Llanowar Elves', 'Healing Salve'):
            put(s, name, 'hand', 'p2')
        put(s, 'Llanowar Elves', 'graveyard')
        put(s, 'Rumbling Baloth', 'graveyard')
        source = cast(s, 'Cruel Ultimatum', ['p2'])
        assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    else:
        source = cast(s, 'Angelic Skirmisher')
        to_phase(s, 'begin_combat')
        settle(s)
        assert s.state.rules.decision
    saved = tmp_path / 'pending.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip,settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,source,bear=sys.argv[3:]
if stage in ('offering','offering_second'):
 if stage=='offering':choose(s,['p2'])
 assert s.state.rules.decision and s.state.rules.decision.player=='p1'
 assert s.state.players['p1'].life==40
 assert sum(c.token is not None and c.zone.endswith(':battlefield') for c in s.state.cards.values())==6
 choose(s,['p3'])
 assert s.state.players['p1'].life==48 and s.state.players['p2'].life==40 and s.state.players['p3'].life==42
elif stage in ('cosmic','cosmic_aura'):
 if stage=='cosmic':
  choose(s,['yes'])
 else:
  d=s.state.rules.decision
  assert d and any(o.id==bear for o in d.options)
  choose(s,[bear])
 target=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name==('Pacifism' if stage=='cosmic_aura' else 'Llanowar Elves'))
 assert target.zone=='p1:battlefield' and s.state.players['p1'].life==43
 if stage=='cosmic_aura':assert target.attached_to==bear
elif stage=='skirmisher':
 d=s.state.rules.decision
 assert d and d.player=='p1'
 choose(s,['lifelink'])
 assert 'lifelink' in Plan(s.state,'p1',repo,None).ch(s.state.cards[bear]).keywords
elif stage=='cruel':
 d=s.state.rules.decision
 assert d and d.player=='p2' and d.min_choices==d.max_choices==3
 choose(s,[o.id for o in d.options[:3]])
 d=s.state.rules.decision
 assert d and d.player=='p1'
 choose(s,[d.options[0].id])
 assert s.state.players['p1'].life==45 and s.state.players['p2'].life==35
else:
 if stage=='legion':
  records=[p for p in s.state.rules.payments.values() if p.card==source]
  assert records and sum(records[-1].mana_spent.values())==6
  assert s.state.cards[source].stack_info.x==2
 settle(s)
 if stage=='worldfire':
  assert all(p.life==1 for p in s.state.players.values())
  assert s.state.cards[source].zone=='p1:graveyard'
  assert s.state.cards[bear].zone=='p1:exile'
 else:
  assert s.state.cards[source].zone=='p1:exile'
  tokens=[c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield']
  assert len(tokens)==2 and all(c.tapped for c in tokens)
  assert s.state.players['p1'].life==42
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, source.id, bear.id], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('accept', [False, True])
def test_cosmic_rebirth_eligible_optional_return_and_life(cards, accept):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'graveyard')
    cast(s, 'Cosmic Rebirth', [target.id])
    assert s.state.rules.decision
    choose(s, ['yes' if accept else 'no'])
    assert target.zone == ('p1:battlefield' if accept else 'p1:hand')
    assert s.state.players['p1'].life == 43
    roundtrip(s)


@pytest.mark.parametrize('case', ['expensive', 'prohibited', 'hostless', 'replacement'])
def test_cosmic_rebirth_native_payment_and_unavailable_return(cards, case):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    name = 'Rumbling Baloth' if case == 'expensive' else 'Pacifism' if case == 'hostless' else 'Grizzly Bears'
    target = put(s, name, 'graveyard')
    if case == 'prohibited':
        put(s, "Grafdigger's Cage", 'battlefield')
    if case == 'replacement':
        put(s, 'Containment Priest', 'battlefield')
    cast(s, 'Cosmic Rebirth', [target.id])
    if case == 'replacement':
        assert s.state.rules.decision
        choose(s, ['yes'])
        assert target.zone == 'p1:exile'
    else:
        assert not s.state.rules.decision
        assert target.zone == 'p1:hand'
    assert s.state.players['p1'].life == 43
    roundtrip(s)


def test_cosmic_sole_target_removed_fizzles_life_gain(cards):
    from tests.game_helpers import act

    s = game(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    target = put(s, 'Grizzly Bears', 'graveyard')
    spell = cast(s, 'Cosmic Rebirth', [target.id], resolve=False)
    cast(s, 'Cremate', [target.id])
    assert target.zone == 'p1:exile' and spell.zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 40
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('same', [False, True])
def test_benevolent_two_independent_nontarget_opponent_choices(cards, same):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast(s, 'Benevolent Offering')
    d = s.state.rules.decision
    assert d and d.player == 'p1' and {o.id for o in d.options} == {'p2', 'p3'}
    choose(s, ['p2'])
    tokens = [c for c in s.state.cards.values() if c.token and c.zone.endswith(':battlefield')]
    assert len(tokens) == 6
    assert sum(c.controller == 'p1' for c in tokens) == 3
    assert sum(c.controller == 'p2' for c in tokens) == 3
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    choose(s, ['p2' if same else 'p3'])
    assert s.state.players['p1'].life == 48
    assert s.state.players['p2'].life == (48 if same else 40)
    assert s.state.players['p3'].life == (40 if same else 42)
    roundtrip(s)


def test_benevolent_counts_doomed_tokens_before_sba(cards):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    put(s, 'Elesh Norn, Grand Cenobite', 'battlefield', 'p3')
    cast(s, 'Benevolent Offering')
    choose(s, ['p2'])
    assert s.state.rules.decision
    assert sum(c.token is not None and c.zone.endswith(':battlefield') for c in s.state.cards.values()) == 6
    choose(s, ['p2'])
    assert s.state.players['p1'].life == s.state.players['p2'].life == 46
    assert not any(c.token and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


def test_benevolent_actual_gain_replacement(cards):
    from tests.test_rules_conditional_prevention import choose

    s = game(cards)
    put(s, "Alhammarret's Archive", 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast(s, 'Benevolent Offering')
    choose(s, ['p2'])
    choose(s, ['p3'])
    assert s.state.players['p1'].life == 52
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 42
    roundtrip(s)


@pytest.mark.parametrize('x,count', [(0, 0), (1, 0), (1, 2), (2, 4)])
def test_erebos_actual_announced_twice_x_graveyard_targets(cards, x, count):
    s = game(cards)
    available = [put(s, name, 'graveyard', pid) for pid in ('p1', 'p2')
                 for name in ('Grizzly Bears', 'Llanowar Elves')]
    chosen = available[:count]
    spell = cast(s, "Erebos's Intervention", [c.id for c in chosen], modes=[1], x_value=x, target_counts=[count])
    assert spell.zone == 'p1:graveyard'
    assert all(c.zone == c.owner + (':exile' if c in chosen else ':graveyard') for c in available)
    roundtrip(s)


def test_erebos_twice_x_bound_rejects_excess_atomically(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import mana, wait_priority

    s = game(cards)
    available = [put(s, name, 'graveyard', pid) for pid in ('p1', 'p2')
                 for name in ('Grizzly Bears', 'Llanowar Elves')]
    spell = put(s, "Erebos's Intervention", 'hand')
    mana(s, C=1, B=1)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, modes=[1], x_value=1,
            targets=[c.id for c in available[:3]], target_counts=[3], sources=[])
    assert spell.zone == 'p1:hand'
    assert all(c.zone == c.owner + ':graveyard' for c in available)
    roundtrip(s)


def test_erebos_first_mode_actual_x_life_and_death(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, "Erebos's Intervention", [bear.id], modes=[0], x_value=2)
    assert bear.zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 42
    roundtrip(s)


@pytest.mark.parametrize('mode', [0, 1])
def test_erebos_target_incarnation_fizzle_or_partial_legality(cards, mode):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield' if mode == 0 else 'graveyard', 'p2')
    other = put(s, 'Llanowar Elves', 'graveyard', 'p3')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, "Erebos's Intervention", [target.id] + ([other.id] if mode == 1 else []),
                  modes=[mode], x_value=2, target_counts=[2] if mode == 1 else [], resolve=False)
    if mode == 0:
        cast(s, 'Murder', [target.id])
    else:
        cast(s, 'Cremate', [target.id])
    settle(s)
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [o.id for o in d.options[:d.min_choices]])
    assert source.zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 40
    assert target.zone == ('p2:graveyard' if mode == 0 else 'p2:exile')
    assert other.zone == ('p3:graveyard' if mode == 0 else 'p3:exile')
    roundtrip(s)


def test_erebos_saved_announced_x_and_targets_native_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    victims = [put(s, name, 'graveyard', pid) for pid in ('p1', 'p2')
               for name in ('Grizzly Bears', 'Llanowar Elves')]
    source = cast(s, "Erebos's Intervention", [c.id for c in victims], modes=[1], x_value=2, target_counts=[4], resolve=False)
    assert source.stack_info and source.stack_info.x == 2
    saved = tmp_path / 'pending.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=sys.argv[3]
assert s.state.cards[source].stack_info.x==2
settle(s)
assert s.state.cards[source].zone=='p1:graveyard'
assert all(s.state.cards[c].zone==s.state.cards[c].owner+':exile' for c in sys.argv[4:])
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id,
                             *[c.id for c in victims]], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_erebos_actual_twincast_retains_x_mode_and_independent_resolution(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle

    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    original = cast(s, "Erebos's Intervention", [bear.id], modes=[0], x_value=1, resolve=False)
    twin = cast(s, 'Twincast', [original.id])
    while s.state.rules.decision:
        d = s.state.rules.decision
        keep = next(o.id for o in d.options if o.id in ('keep', 'same'))
        choose(s, [keep])
    settle(s)
    assert twin.zone == 'p1:graveyard' and original.zone == 'p1:graveyard'
    assert bear.zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 42
    roundtrip(s)
