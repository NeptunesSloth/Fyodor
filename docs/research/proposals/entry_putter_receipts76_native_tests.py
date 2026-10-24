"""Chants observe the actual per-entry putter and native full counter payment."""
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

NAMES = ["Tourach's Chant", "Thelon's Chant"]
DATA = json.loads((Path(__file__).parent / 'fixtures/entry_putter_receipts76_cards.json').read_text())


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


ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest']


def setup(cards):
    s = table(cards, ALL, ALL, ALL)
    start(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical_is_read(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_actual_other_player_land_play_decline_damages_putter(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 40
    roundtrip(s)


def pay_counter(s, payer, recipient):
    d = s.state.rules.decision
    assert d and d.player == payer and 'pay' in [o.id for o in d.options]
    act(s, payer, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    if d:
        assert d.player == payer and recipient.id in [o.id for o in d.options]
        act(s, payer, type='choose', decision_id=d.id, option_ids=[recipient.id])
    settle(s)


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_actual_putter_pays_counter_cost_on_own_creature(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Llanowar Elves', 'battlefield')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    pay_counter(s, 'p2', recipient)
    assert recipient.counters == {'-1/-1': 1} and not other.counters
    assert s.state.players['p2'].life == s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_without_creature_cost_is_not_offered_and_actual_putter_takes_damage(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 40
    roundtrip(s)


def decline_all(s):
    payers = []
    for _ in range(20):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return payers
        if 'decline' in [o.id for o in d.options]:
            payers.append(d.player)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
        elif d.min_choices == 0:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        else:
            raise AssertionError((d.kind, d.prompt))
    raise AssertionError('Unexpected repeated decision')


@pytest.mark.parametrize('spell,pool', [('Exhume', {'C': 1, 'B': 1}), ('Living Death', {'C': 3, 'B': 2})])
def test_simultaneous_actual_two_player_putters_are_not_first_mover(cards, spell, pool):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Dryad Arbor', 'graveyard')
    b = put(s, 'Dryad Arbor', 'graveyard', 'p2')
    source = put(s, spell, 'hand')
    wait_priority(s, 'p1')
    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    payers = decline_all(s)
    assert sorted(payers) == ['p1', 'p2']
    assert a.zone == 'p1:battlefield' and b.zone == 'p2:battlefield'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    assert s.state.players['p3'].life == 40
    roundtrip(s)


def test_jailbreak_actual_putter_differs_from_returned_forest_controller(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    incoming = put(s, 'Forest', 'graveyard', 'p2')
    put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Jailbreak', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[incoming.id])
    payers = decline_all(s)
    assert payers == ['p1']
    assert incoming.zone == 'p2:battlefield' and incoming.controller == 'p2'
    assert s.state.players['p1'].life == 37 and s.state.players['p2'].life == 40
    roundtrip(s)


def test_actual_forest_token_creation_has_creator_putter_receipt(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    source = put(s, 'Awaken the Woods', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, G=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=2)
    payers = decline_all(s)
    assert payers == ['p1', 'p1']
    assert s.state.players['p1'].life == 34 and s.state.players['p3'].life == 40
    forests = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(forests) == 2
    roundtrip(s)


@pytest.mark.parametrize('name,color,land', [(NAMES[0], 'B', 'Swamp'), (NAMES[1], 'G', 'Forest')])
@pytest.mark.parametrize('pay', [False, True])
def test_printed_own_upkeep_native_payment_or_sacrifice(cards, name, color, land, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, name, 'hand')
    mana(s, C=1, **{color: 2})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    resource = put(s, land, 'battlefield')
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    if pay:
        act(s, 'p1', type='activate_ability', card_id=resource.id, ability=0)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'sacrifice'])
    settle(s)
    assert source.zone == ('p1:battlefield' if pay else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('support,paid', [('Solemnity', False), ('Vizier of Remedies', True)])
def test_optional_counter_cost_distinguishes_forbidden_placement_and_zero_replacement(cards, support, paid):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, support, 'battlefield', 'p2')
    incoming = put(s, 'Forest', 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    if paid:
        pay_counter(s, 'p2', recipient)
    else:
        assert s.state.rules.decision is None
    assert not recipient.counters
    assert s.state.players['p2'].life == (40 if paid else 37)
    roundtrip(s)


def test_manual_move_cannot_forge_server_entry_putter_receipt(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    incoming = put(s, 'Forest', 'hand')
    act(s, 'p1', type='move', card_ids=[incoming.id], to={'player': 'p1', 'zone': 'battlefield'},
        entry_putters={incoming.id: 'p2'})
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p2'].life == 40
    roundtrip(s)


def test_second_sunrise_retains_each_actual_owner_putter(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Dryad Arbor', 'battlefield')
    b = put(s, 'Dryad Arbor', 'battlefield', 'p2')
    removal = put(s, 'Pyroclasm', 'hand')
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=removal.id)
    settle(s)
    assert a.zone == 'p1:graveyard' and b.zone == 'p2:graveyard'
    source = put(s, 'Second Sunrise', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    assert sorted(decline_all(s)) == ['p1', 'p2']
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    assert a.zone == 'p1:battlefield' and b.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_true_cold_putter_payment_preserves_actor_and_own_recipient(cards, tmp_path, name, land):
    import subprocess
    import sys

    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    saved = tmp_path / 'putter76.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_entry_putter_receipts76 import pay_counter
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
recipient=s.state.cards[sys.argv[3]]
pay_counter(s,'p2',recipient)
assert recipient.counters=={'-1/-1':1}
assert s.state.players['p1'].life==s.state.players['p2'].life==40
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), recipient.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_patriarchs_bidding_actual_type_choices_preserve_both_putters(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Dryad Arbor', 'graveyard')
    b = put(s, 'Dryad Arbor', 'graveyard', 'p2')
    source = put(s, "Patriarch's Bidding", 'hand')
    mana(s, C=3, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    for who in ['p1', 'p2', 'p3']:
        settle(s)
        d = s.state.rules.decision
        assert d and d.player == who and 'Dryad' in [o.id for o in d.options]
        act(s, who, type='choose', decision_id=d.id, option_ids=['Dryad'])
    assert sorted(decline_all(s)) == ['p1', 'p2']
    assert a.zone == 'p1:battlefield' and b.zone == 'p2:battlefield'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    roundtrip(s)


def test_parallax_tide_explicit_each_owner_return_has_distinct_putters(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Forest', 'battlefield')
    b = put(s, 'Forest', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, 'Parallax Tide', 'hand')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    for target in [a, b]:
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])
        settle(s)
        assert target.zone.endswith(':exile')
    removal = put(s, 'Disenchant', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    assert sorted(decline_all(s)) == ['p1', 'p2']
    assert a.zone == 'p1:battlefield' and b.zone == 'p2:battlefield'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    roundtrip(s)


def test_true_cold_pending_mixed_return_keeps_serialized_owner_instructions(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Dryad Arbor', 'graveyard')
    b = put(s, 'Dryad Arbor', 'graveyard', 'p2')
    source = put(s, 'Exhume', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    assert source.zone.endswith(':stack') and a.zone.endswith(':graveyard')
    saved = tmp_path / 'mixed76.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_entry_putter_receipts76 import decline_all
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert sorted(decline_all(s))==['p1','p2']
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
assert s.state.cards[sys.argv[4]].zone=='p2:battlefield'
assert s.state.players['p1'].life==s.state.players['p2'].life==37
assert s.state.players['p3'].life==40
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), a.id, b.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
