"""Canonical unconditional prevention bodies through native production continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import prevention_unpreventable_outcomes44 as leaf
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_abundance import set_library
from tests.test_rules_damage_redirection import activate, attack, cast, damage
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

ROOT = Path(__file__).parent / 'fixtures'
DATA = json.loads((ROOT / 'prevention_outcomes_cards.json').read_text()) + json.loads((ROOT / 'prevention_unpreventable44_cards.json').read_text())
for filename, wanted in [('populate_sequences_cards.json', 'Doubling Season'), ('review32_cards.json', 'Rest in Peace'),
                         ('mill_pair_repeat_cards.json', 'Bruvac the Grandiloquent'), ('mana_source_cast_cards.json', 'Twiddle'),
                         ('review33_cards.json', 'Hardened Scales')]:
    path = ROOT / filename
    if path.exists():
        rows = json.loads(path.read_text())
        found = next((r for r in rows if r.get('name') == wanted), None)
        if found is not None:
            DATA.append(found)
NAMES = ['Angel of Suffering', 'Gatta and Luzzu', 'Sokrates, Athenian Teacher', 'Grizzly Bears', 'Centaur Courser',
         'Forest', 'Island', 'Mountain', 'Lightning Bolt', 'Skullcrack', 'Pestilence', 'Revitalize', 'Abundance',
         'Turn to Frog', 'Furnace of Rath', 'Black Knight', "Healer's Hawk", "Harm's Way",
         'Doubling Season', 'Rest in Peace', 'Bruvac the Grandiloquent', 'Twiddle', 'Hardened Scales']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], set_code='u44', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def game(cards):
    return table(cards, NAMES, NAMES, NAMES)


@pytest.mark.parametrize('unpreventable', [False, True])
@pytest.mark.parametrize('size', [0, 3, 8])
def test_angel_actual_prevention_and_mill_original_damage_even_unpreventable_or_short_library(cards, unpreventable, size):
    s = game(cards)
    put(s, 'Angel of Suffering', 'battlefield')
    names = ['Forest', 'Island', 'Mountain', 'Grizzly Bears', 'Lightning Bolt', 'Revitalize', 'Centaur Courser', 'Black Knight']
    top = set_library(s, names[:size])
    if unpreventable:
        cast(s, 'Skullcrack', ['p3'], pid='p2')
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == (37 if unpreventable else 40)
    assert len(s.state.zones['p1:library']) == max(0, size - 6)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top[:6])
    assert s.state.rules.decision is None and 'p1' not in s.state.rules.lost
    roundtrip(s)


def gatta(cards, *, self_target=False):
    s = game(cards)
    target = None if self_target else put(s, 'Grizzly Bears', 'battlefield')
    holder = cast(s, 'Gatta and Luzzu')
    target = holder if target is None else target
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id,
            option_ids=[next(o.id for o in d.options if o.card_id == target.id or o.id == target.id)])
        settle(s)
    assert any(r.get('source_card') == holder.id for r in s.state.rules.replacements)
    return s, target, holder


@pytest.mark.parametrize('unpreventable', [False, True])
@pytest.mark.parametrize('self_target', [False, True])
def test_gatta_actual_target_counters_original_damage_and_saves_unpreventable_lethal_before_sbas(cards, unpreventable, self_target):
    s, target, _ = gatta(cards, self_target=self_target)
    if unpreventable:
        cast(s, 'Skullcrack', ['p3'], pid='p2')
    cast(s, 'Lightning Bolt', [target.id], pid='p2')
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1') == 3
    assert s.state.cards[target.id].damage == (3 if unpreventable else 0)
    assert s.state.rules.decision is None


@pytest.mark.parametrize('unpreventable', [False, True])
def test_sokrates_actual_native_grant_prevents_combat_and_both_players_draw_even_unpreventable(cards, unpreventable):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    assert s.state.cards[holder.id].tapped
    if unpreventable:
        cast(s, 'Skullcrack', ['p3'], pid='p1')
    hand1, hand2 = (len(s.state.zones[p + ':hand']) for p in ('p1', 'p2'))
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == (38 if unpreventable else 40)
    assert len(s.state.zones['p1:hand']) == hand1 + 1
    assert len(s.state.zones['p2:hand']) == hand2 + 1
    assert s.state.rules.decision is None


@pytest.mark.parametrize('cold', [False, True])
def test_live_joint_unpreventable_redirect_keeps_gatta_zero_prevention_rider_and_sba_waits(cards, tmp_path, cold):
    from tests.test_rules_prevention_frontier_bridge import answer
    from tests.test_rules_prevention_outcomes import source_choice
    s, target, _ = gatta(cards, self_target=True)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    cast(s, 'Skullcrack', ['p3'], pid='p2')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    cast(s, "Harm's Way", [target.id])
    source_choice(s, bolt)
    answer(s, 2)
    d = s.state.rules.decision
    assert d is not None, 'unpreventable Gatta rider must reach the native counter chooser'
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].damage == 2
    assert not s.state.cards[target.id].counters.get('+1/+1', 0)
    assert s.state.players['p1'].life == 39
    if cold:
        import subprocess
        import sys
        saved = tmp_path / 'gatta-counter.json'
        saved.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
saved,db,target=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
assert s.state.cards[target].damage==2 and s.state.cards[target].zone=='p1:battlefield'
option=next(o for o in d.options if 'Hardened Scales' in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option.id])
settle(s)
assert s.state.cards[target].counters['+1/+1']==6
assert s.state.cards[target].zone=='p1:battlefield'
assert s.state.rules.decision is None and not s.state.rules.stack
assert s.state.players['p1'].life==39
roundtrip(s)
settle(s)
assert s.state.cards[target].counters['+1/+1']==6
repo.close()
'''
        result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
                                cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    option = next(o for o in d.options if 'Hardened Scales' in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    assert s.state.cards[target.id].counters['+1/+1'] == 6
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is None


@pytest.mark.parametrize('name', ['Lightning Bolt', 'Skullcrack'])
def test_sokrates_grant_does_not_prevent_noncombat_damage_or_draw(cards, name):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    hand = len(s.state.zones['p1:hand'])
    cast(s, name, ['p1'], pid='p2')
    assert s.state.players['p1'].life == 37
    assert len(s.state.zones['p1:hand']) == hand


def test_sokrates_zero_half_does_not_draw_empty_libraries(cards):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, "Healer's Hawk", 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    set_library(s, [])
    for cid in list(s.state.zones['p2:library']):
        act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'graveyard'})
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 40
    assert not s.state.rules.lost


def test_sokrates_later_native_layer6_ability_loss_removes_prevention(cards):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    cast(s, 'Turn to Frog', [attacker.id])
    hands = tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2'))
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 39
    assert tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2')) == hands


def test_gatta_full_turn_shield_repeats_after_source_departure(cards):
    s, target, holder = gatta(cards)
    act(s, 'p1', type='move', card_ids=[holder.id], to={'player': 'p1', 'zone': 'graveyard'})
    cast(s, 'Lightning Bolt', [target.id], pid='p2')
    cast(s, 'Lightning Bolt', [target.id], pid='p2')
    assert s.state.cards[target.id].counters['+1/+1'] == 6
    assert s.state.cards[target.id].damage == 0


@pytest.mark.parametrize('mutation', ['combat', 'source', 'body', 'aggregation'])
def test_quoted_full_definition_validation_rejects_changed_semantics(mutation):
    import copy
    definition = copy.deepcopy(leaf._quoted_definition())
    if mutation == 'combat':
        definition['match']['combat'] = False
    elif mutation == 'source':
        definition['match']['source'] = {'controller': 'you'}
    elif mutation == 'body':
        definition['op']['rider']['effects'][0]['n'] = 1
    else:
        definition['op']['rider']['aggregation'] = 'packet'
    assert not leaf.supported_quote(leaf.QUOTE, definition)
    assert leaf.supported_quote(leaf.QUOTE, leaf._quoted_definition())


def test_gatta_tracks_original_target_oid_after_blink(cards):
    s, target, _ = gatta(cards)
    original = s.state.rules.object_id(target.id)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(target.id) != original
    cast(s, 'Lightning Bolt', [target.id], pid='p2')
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert not s.state.cards[target.id].counters


def test_gatta_keeps_original_target_after_control_change(cards):
    s, target, _ = gatta(cards)
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    cast(s, 'Lightning Bolt', [target.id], pid='p3')
    assert s.state.cards[target.id].controller == 'p2'
    assert s.state.cards[target.id].counters['+1/+1'] == 3
    assert s.state.cards[target.id].damage == 0


def test_angel_prevention_and_mill_follow_current_controller(cards):
    s = game(cards)
    angel = put(s, 'Angel of Suffering', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[angel.id], player='p2')
    before = len(s.state.zones['p2:library'])
    cast(s, 'Lightning Bolt', ['p2'], pid='p3')
    assert s.state.players['p2'].life == 40
    assert len(s.state.zones['p2:library']) == before - 6
    hand = len(s.state.zones['p1:library'])
    cast(s, 'Lightning Bolt', ['p1'], pid='p3')
    assert s.state.players['p1'].life == 37
    assert len(s.state.zones['p1:library']) == hand


def test_sokrates_grant_expires_at_end_of_turn_even_after_grantor_departure(cards):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    act(s, 'p2', type='move', card_ids=[holder.id], to={'player': 'p2', 'zone': 'graveyard'})
    to_phase(s, 'main1', turn=3)
    # The grant expired at end of turn two; a native later-turn attack is ordinary.
    hands = tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2', 'p3'))
    attack(s, [attacker], pid='p3', target='p1', turn=3)
    damage(s)
    assert s.state.players['p1'].life == 38
    assert tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2', 'p3')) == hands


@pytest.mark.parametrize('replacement', ['Rest in Peace', 'Bruvac the Grandiloquent'])
def test_angel_rider_uses_native_mill_replacements(cards, replacement):
    s = game(cards)
    put(s, 'Angel of Suffering', 'battlefield')
    put(s, replacement, 'battlefield', 'p2' if replacement == 'Bruvac the Grandiloquent' else 'p1')
    top = set_library(s, ['Forest', 'Island', 'Mountain', 'Grizzly Bears', 'Lightning Bolt', 'Revitalize', 'Centaur Courser', 'Black Knight'])
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    count = 8 if replacement == 'Bruvac the Grandiloquent' else 6
    zone = 'p1:exile' if replacement == 'Rest in Peace' else 'p1:graveyard'
    assert all(s.state.cards[c].zone == zone for c in top[:count])
    assert len(s.state.zones['p1:library']) == 8 - count
    assert s.state.players['p1'].life == 40


def test_sokrates_native_draw_replacement_cold_resume_once_without_child_adapters(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Centaur Courser', 'battlefield', 'p2')
    put(s, 'Abundance', 'battlefield')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    hand1, hand2 = (len(s.state.zones[p + ':hand']) for p in ('p1', 'p2'))
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and any(o.id == 'decline' for o in d.options)
    assert s.state.players['p1'].life == 40
    saved = tmp_path / 'sokrates-draw.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
saved,db,h1,h2=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['decline'])
settle(s)
assert s.state.rules.decision is None
assert len(s.state.zones['p1:hand'])==int(h1)+1
assert len(s.state.zones['p2:hand'])==int(h2)+1
assert s.state.players['p1'].life==40
roundtrip(s)
settle(s)
assert len(s.state.zones['p1:hand'])==int(h1)+1
assert len(s.state.zones['p2:hand'])==int(h2)+1
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), str(hand1), str(hand2)],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sokrates_printed_hexproof_is_conditional_on_native_tap_cost(cards):
    from app.game.errors import ActionError
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError):
        cast(s, 'Lightning Bolt', [holder.id], pid='p1')
    assert not s.state.cards[holder.id].tapped
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    cast(s, 'Lightning Bolt', [holder.id], pid='p1')
    assert s.state.cards[holder.id].damage == 3
    with pytest.raises(ActionError):
        activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')


def test_sokrates_new_native_grant_after_layer6_ability_loss_restores_prevention(cards):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    cast(s, 'Turn to Frog', [attacker.id])
    cast(s, 'Twiddle', [holder.id])
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        option = next(o for o in d.options if 'untap' in (o.id + o.label).lower())
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
        settle(s)
    assert not s.state.cards[holder.id].tapped
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    hands = tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2'))
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 40
    assert tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2')) == hands


def test_sokrates_resolved_grant_survives_grantor_departure(cards):
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    act(s, 'p2', type='move', card_ids=[holder.id], to={'player': 'p2', 'zone': 'graveyard'})
    hands = tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2'))
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == 40
    assert tuple(len(s.state.zones[p + ':hand']) for p in ('p1', 'p2')) == tuple(n + 1 for n in hands)


@pytest.mark.parametrize('double_first', [False, True])
def test_angel_native616_order_sets_original_amount_for_mill(cards, double_first):
    s = game(cards)
    put(s, 'Angel of Suffering', 'battlefield')
    put(s, 'Furnace of Rath', 'battlefield')
    before = len(s.state.zones['p1:library'])
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    d = s.state.rules.decision
    assert d is not None
    label = 'Furnace of Rath' if double_first else 'Angel of Suffering'
    option = next(o for o in d.options if label in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    assert s.state.players['p1'].life == 40
    assert len(s.state.zones['p1:library']) == before - (12 if double_first else 6)
    assert s.state.rules.decision is None


@pytest.mark.parametrize('name', ['Angel of Suffering', 'Gatta and Luzzu', 'Sokrates, Athenian Teacher'])
def test_whole_canonical_printed_definition_coverage(cards, name):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_sokrates_defender_and_summoning_sickness_remain_native(cards):
    from app.game.errors import ActionError
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    with pytest.raises(ActionError):
        activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError):
        attack(s, [holder], pid='p2', target='p1', turn=2)


def test_angel_native616_cold_rediscovers_exact_source(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    put(s, 'Angel of Suffering', 'battlefield')
    put(s, 'Furnace of Rath', 'battlefield')
    before = len(s.state.zones['p1:library'])
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.rules.decision is not None
    saved = tmp_path / 'angel-order.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
saved,db,before=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
option=next(o for o in d.options if 'Furnace of Rath' in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option.id])
settle(s)
assert s.state.players['p1'].life==40
assert len(s.state.zones['p1:library'])==int(before)-12
assert s.state.rules.decision is None
roundtrip(s)
settle(s)
assert len(s.state.zones['p1:library'])==int(before)-12
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), str(before)],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sokrates_grant_fresh_load_before_combat_rediscovers_native_static(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    holder = put(s, 'Sokrates, Athenian Teacher', 'battlefield', 'p2')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    activate(s, holder, 'Sokratic Dialogue', [attacker.id], pid='p2')
    hands = [len(s.state.zones[p + ':hand']) for p in ('p1', 'p2')]
    saved = tmp_path / 'sokrates-before-combat.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_damage_redirection import attack,damage
from tests.test_rules_designations import settle,roundtrip
saved,db,attacker,h1,h2=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
attack(s,[s.state.cards[attacker]],pid='p2',target='p1',turn=2)
damage(s)
assert s.state.players['p1'].life==40
assert len(s.state.zones['p1:hand'])==int(h1)+1
assert len(s.state.zones['p2:hand'])==int(h2)+1
assert s.state.rules.decision is None
roundtrip(s)
settle(s)
assert len(s.state.zones['p1:hand'])==int(h1)+1
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), attacker.id, *map(str, hands)],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
