"""Player-relative counter and tap choices retain actual chooser and putter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Gluntch, the Bestower', 'Tangle Wire', 'Mikey & Mona, Mutant Sitters']
DATA = json.loads((Path(__file__).parent / 'fixtures/player_counter_instructions75_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [*NAMES, 'Llanowar Elves', 'Sol Ring', 'Bold Plagiarist', 'Solemnity'], ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest'])
    start(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical_is_read(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_gluntch_distinct_players_and_first_player_chooses_own_creature(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'end', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[first.id])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'p2' not in [o.id for o in d.options]
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    d = s.state.rules.decision
    assert d and [o.id for o in d.options] == ['p3']
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert first.counters == {'+1/+1': 2}
    assert len(s.state.zones['p1:hand']) == before + 1
    assert len([c for c in s.state.cards.values() if c.zone == 'p3:battlefield' and c.name == 'Treasure']) == 2
    roundtrip(s)


def test_tangle_wire_native_fading_and_other_player_tap_choice(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert source.counters == {'fade': 4}
    chosen = [put(s, name, 'battlefield', 'p2') for name in ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']]
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert all(c.tapped for c in chosen)
    assert source.counters == {'fade': 4}
    roundtrip(s)


def test_mikey_both_modes_native_target_and_choice_probe(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p2')
    grave = put(s, 'Forest', 'graveyard', 'p1')
    source = put(s, NAMES[2], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['0:0', '1:0'])
    d = s.state.rules.decision
    assert d.player == 'p1'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    d = s.state.rules.decision
    assert d.player == 'p1' and 'p2' not in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is None or d.player == 'p1'
    if d:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[grave.id])
        settle(s)
    assert target.counters == {'+1/+1': 2}
    assert grave.zone == 'p1:hand'
    roundtrip(s)


def answer_gluntch(s, first='p2', second='p1'):
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[first])
    d = s.state.rules.decision
    if d and d.kind == 'choose_cards':
        assert d.player == first
        act(s, first, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d and first not in [o.id for o in d.options]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[second])
    d = s.state.rules.decision
    if d:
        assert d.player == 'p1'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)


def test_gluntch_actual_first_player_putter_triggers_opponents_bold_plagiarist(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    watcher = put(s, 'Bold Plagiarist', 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert recipient.counters == {'+1/+1': 2}
    assert watcher.counters == {'+1/+1': 2}
    roundtrip(s)


def test_gluntch_two_remaining_players_skip_third_token_instruction(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    act(s, 'p3', type='concede')
    put(s, NAMES[0], 'battlefield')
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert not any(c.name == 'Treasure' and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


def test_tangle_wire_fading_removes_counter_on_actual_own_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    to_phase(s, 'main1', turn=7)
    assert source.counters == {'fade': 3} and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_native_player_relative_choice(cards, tmp_path, name):
    import subprocess
    import sys

    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, name, 'hand')
    pools = {NAMES[0]: {'C': 1, 'G': 1, 'W': 1}, NAMES[1]: {'C': 3}, NAMES[2]: {'C': 2, 'G': 1}}
    wait_priority(s, 'p1')
    mana(s, **pools[name])
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    ids = []
    if name == NAMES[0]:
        recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        watcher = put(s, 'Bold Plagiarist', 'battlefield')
        to_phase(s, 'end', turn=4)
        settle(s)
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
        assert recipient.counters == {'+1/+1': 2}
        ids = [recipient.id, watcher.id]
    elif name == NAMES[1]:
        ids = [put(s, n, 'battlefield', 'p2').id for n in ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']]
        to_phase(s, 'upkeep', turn=5)
        settle(s)
        assert s.state.rules.decision.player == 'p2'
    else:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['0:0'])
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
        # Add two legal public choices before resolving the targeted first mode.
        ids = [put(s, n, 'battlefield', 'p2').id for n in ['Grizzly Bears', 'Llanowar Elves']]
        settle(s)
        assert s.state.rules.decision.player == 'p2'
    saved = tmp_path / 'player75.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name=sys.argv[3];ids=json.loads(sys.argv[4]);d=s.state.rules.decision
if name=='Gluntch, the Bestower':
 assert d.player=='p1' and 'p2' not in [o.id for o in d.options]
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['p1'])
 d=s.state.rules.decision
 assert [o.id for o in d.options]==['p3']
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['p3'])
 settle(s)
 assert s.state.cards[ids[0]].counters=={'+1/+1':2}
 assert s.state.cards[ids[1]].counters=={'+1/+1':2}
 assert len([c for c in s.state.cards.values() if c.zone=='p3:battlefield' and c.name=='Treasure'])==2
elif name=='Tangle Wire':
 assert d.player=='p2' and d.min_choices==d.max_choices==4
 act(s,'p2',type='choose',decision_id=d.id,option_ids=ids[:4])
 settle(s)
 assert all(s.state.cards[c].tapped for c in ids[:4]) and not s.state.cards[ids[4]].tapped
else:
 assert d.player=='p2'
 act(s,'p2',type='choose',decision_id=d.id,option_ids=[ids[0]])
 settle(s)
 assert s.state.cards[ids[0]].counters=={'+1/+1':2} and not s.state.cards[ids[1]].counters
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, json.dumps(ids)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tangle_wire_fading_without_counter_sacrifices_on_actual_own_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='fade', delta=-4)
    to_phase(s, 'main1', turn=7)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_gluntch_prohibited_counter_effect_does_not_stop_other_player_instructions(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    put(s, 'Solemnity', 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    watcher = put(s, 'Bold Plagiarist', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert not recipient.counters and not watcher.counters
    assert len(s.state.zones['p1:hand']) == before + 1
    assert len([c for c in s.state.cards.values() if c.zone == 'p3:battlefield' and c.name == 'Treasure']) == 2
    roundtrip(s)


def test_native_definition_namespace_rewrites_all_gluntch_exclusion_refs(cards):
    from app.rules import scripts
    from app.rules.characteristics import printed_from_data

    ch = printed_from_data(cards.resolve(NAMES[0]))
    ability = next(a for a in ch.abilities if a.kind == 'triggered')
    definition = scripts.define(ability, ch)
    assert definition is not None
    prefixed = scripts.rename_bindings(definition, 'clause75_')
    es = prefixed['effects']
    assert es[0]['as'] == 'clause75_gluntch75_1'
    assert es[3]['exclude_players'] == {'first': 'ref:clause75_gluntch75_1'}
    assert es[5]['exclude_players'] == {'first': 'ref:clause75_gluntch75_1', 'second': 'ref:clause75_gluntch75_2'}
    assert es[1]['who'] == es[2]['by'] == 'ref:clause75_gluntch75_1'


@pytest.mark.parametrize('fade_first', [False, True])
def test_tangle_actual_own_upkeep_trigger_order_locks_correct_tap_count(cards, fade_first):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, NAMES[1], 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    for n in ['Sol Ring', 'Llanowar Elves', NAMES[0], NAMES[2]]:
        put(s, n, 'battlefield')
    to_phase(s, 'upkeep', turn=7)
    d = s.state.rules.decision
    assert d and d.kind == 'order'
    pending = {t.id: t for t in s.state.rules.pending_triggers}
    fade = next(t.id for t in pending.values() if any(e['do'] == 'remove_counters' for e in t.ability['effects']))
    tap = next(t.id for t in pending.values() if any(e['do'] == 'player_chooses' for e in t.ability['effects']))
    # First placed goes on the stack first and resolves last.
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[tap, fade] if fade_first else [fade, tap])
    settle(s)
    d = s.state.rules.decision
    want = 3 if fade_first else 4
    assert d and d.player == 'p1' and d.min_choices == d.max_choices == want
    assert source.counters == {'fade': want}
    picked = [o.id for o in d.options[:want]]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=picked)
    settle(s)
    assert all(s.state.cards[cid].tapped for cid in picked)
    assert source.counters == {'fade': 3}
    roundtrip(s)


def test_gluntch_three_players_first_has_no_creature_still_draws_and_creates_treasure(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=4)
    settle(s)
    answer_gluntch(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert len([c for c in s.state.cards.values() if c.zone == 'p3:battlefield' and c.name == 'Treasure']) == 2
    roundtrip(s)
