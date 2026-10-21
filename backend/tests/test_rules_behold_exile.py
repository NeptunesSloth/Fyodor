"""Cumulative exile thresholds reset per opponent; Dream's free casts retain normal timing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

NAMES = ['Champions of the Perfect', 'Champion of the Path', 'Champion of the Weird', 'Champions of the Shoal', 'Champion of the Clachan']
DONORS = ['Llanowar Elves', 'Mulldrifter', 'Goblin Arsonist', 'Merfolk Looter', 'Goldmeadow Harrier']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/behold_exile_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='emt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, name=NAMES[0], donor=DONORS[0], zone='hand', extra=()):
    s = table(cards, [name, donor, 'Universal Automaton', 'Grizzly Bears', 'Unsummon', *extra], ['Counterspell', donor], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    chosen = put(s, donor, zone)
    source = put(s, name, 'hand')
    mana(s, C=20, W=10, U=10, B=10, R=10, G=10)
    return s, source, chosen


def cast(s, source, chosen=None):
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = s.state.rules.decision
    if d is not None:
        assert d.resume['step'] == 'ability_cost'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen.id])
    settle(s)


def bounce(s, source):
    spell = put(s, 'Unsummon', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_all_five_champions_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,donor', list(zip(NAMES, DONORS, strict=True)))
@pytest.mark.parametrize('zone', ['hand', 'battlefield'])
def test_native_composite_cost_exiles_matching_object_and_leaving_returns_owner_hand(cards, name, donor, zone):
    s, source, chosen = setup(cards, name, donor, zone)
    cast(s, source, chosen)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    key = s.state.rules.object_id(source.id)
    assert s.state.rules.exiled_with[key] == [s.state.rules.object_id(chosen.id)]
    assert s.state.rules.payments[key].revealed == ([chosen.id] if zone == 'hand' else [])
    bounce(s, source)
    assert s.state.cards[chosen.id].zone == 'p1:hand'
    roundtrip(s)


def test_choice_can_use_held_kindred_noncreature_elf_card(cards):
    s, source, chosen = setup(cards, donor='Elvish Promenade')
    cast(s, source, chosen)
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    bounce(s, source)
    assert s.state.cards[chosen.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_changeling_in_hand_satisfies_every_champion_tribe(cards, name):
    s, source, chosen = setup(cards, name, 'Universal Automaton')
    cast(s, source, chosen)
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    bounce(s, source)
    assert s.state.cards[chosen.id].zone == 'p1:hand'
    roundtrip(s)


def test_private_union_choice_can_cancel_without_exiling_or_spending(cards):
    s, source, chosen = setup(cards)
    other = put(s, 'Universal Automaton', 'hand')
    before = mana_pool(s)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = s.state.rules.decision
    assert d.resume['step'] == 'ability_cost'
    assert {o.id for o in d.options} == {chosen.id, other.id}
    hidden = json.dumps(s.view('p2')['rules']['decision'])
    assert chosen.id not in hidden and other.id not in hidden and source.name not in hidden
    assert s.state.cards[chosen.id].zone == s.state.cards[other.id].zone == 'p1:hand'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[source.id].zone == 'p1:hand' and mana_pool(s) == before
    roundtrip(s)


def test_nonmatching_card_and_the_source_itself_cannot_pay_atomic_cost(cards):
    s, source, wrong = setup(cards, donor='Grizzly Bears')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.model_dump(mode='json') == before
    assert s.state.cards[wrong.id].zone == s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)


def test_invalid_private_choice_is_atomic_and_valid_choice_can_follow(cards):
    s, source, chosen = setup(cards)
    put(s, 'Universal Automaton', 'hand')
    wrong = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    d = s.state.rules.decision
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[wrong.id])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    roundtrip(s)


def test_stolen_controlled_elf_returns_to_its_original_owner_hand(cards):
    s, source, held = setup(cards, extra=('Act of Treason',))
    act(s, 'p1', type='move', card_ids=[held.id], to={'player': 'p1', 'zone': 'library'})
    donor = put(s, DONORS[0], 'battlefield', 'p2')
    steal = put(s, 'Act of Treason', 'hand')
    act(s, 'p1', type='cast_spell', card_id=steal.id, targets=[donor.id])
    settle(s)
    assert s.state.cards[donor.id].controller == 'p1'
    cast(s, source, donor)
    assert s.state.cards[donor.id].zone == 'p2:exile'
    bounce(s, source)
    assert s.state.cards[donor.id].zone == 'p2:hand'
    roundtrip(s)


def test_token_can_pay_but_ceases_and_cannot_return(cards):
    s, source, held = setup(cards)
    act(s, 'p1', type='move', card_ids=[held.id], to={'player': 'p1', 'zone': 'library'})
    donor = put(s, DONORS[0], 'battlefield', 'p2')
    act(s, 'p1', type='copy_card', card_id=donor.id)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == DONORS[0])
    cast(s, source, token)
    assert token.id not in s.state.cards
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    bounce(s, source)
    assert token.id not in s.state.cards
    roundtrip(s)


def test_countered_champion_keeps_paid_card_exiled_and_reanimation_gets_no_old_link(cards):
    s, source, chosen = setup(cards, extra=('Reanimate',))
    act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.cards[source.id].zone == 'stack' and s.state.cards[chosen.id].zone == 'p1:exile'
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, pid='p2', U=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    reanimate = put(s, 'Reanimate', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=reanimate.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    bounce(s, source)
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    roundtrip(s)


def test_blink_returns_old_cost_card_without_paying_a_new_enter_cost(cards):
    s, source, chosen = setup(cards, extra=('Ephemerate',))
    cast(s, source, chosen)
    old = s.state.rules.object_id(source.id)
    blink = put(s, 'Ephemerate', 'hand')
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.object_id(source.id) != old
    assert s.state.cards[chosen.id].zone == 'p1:hand'
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    roundtrip(s)


def test_copy_of_champion_has_no_original_paid_exile_link(cards):
    s, source, chosen = setup(cards)
    cast(s, source, chosen)
    act(s, 'p1', type='copy_card', card_id=source.id)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == source.name)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(token.id))
    bounce(s, token)
    assert chosen.id in s.state.zones['p1:exile']
    bounce(s, source)
    assert chosen.id in s.state.zones['p1:hand']
    roundtrip(s)


@pytest.mark.parametrize('stage', ['cost_choice', 'ltb_pending'])
def test_cold_native_cost_and_old_source_link_resume_without_duplicate_payment(cards, tmp_path, stage):
    import subprocess
    import sys

    from tests.test_rules_conditionals import until

    s, source, chosen = setup(cards)
    put(s, 'Universal Automaton', 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.rules.decision.resume['step'] == 'ability_cost'
    if stage == 'ltb_pending':
        act(s, 'p1', type='choose', decision_id=s.state.rules.decision.id, option_ids=[chosen.id])
        settle(s)
        unsummon = put(s, 'Unsummon', 'hand')
        act(s, 'p1', type='cast_spell', card_id=unsummon.id, targets=[source.id])
        until(s, lambda s: s.state.cards[source.id].zone == 'p1:hand')
        assert s.state.zones.get('stack')
    saved = tmp_path / f'behold-exile-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, source, chosen, stage = sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
if stage=='cost_choice':
    d=s.state.rules.decision
    assert d.resume['step']=='ability_cost'
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[chosen]})
for _ in range(90):
    if not s.state.zones.get('stack'):break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:raise AssertionError('did not settle')
if stage=='cost_choice':
    assert s.state.cards[source].zone=='p1:battlefield'
    assert s.state.cards[chosen].zone=='p1:exile'
    oid=s.state.rules.object_id(source)
    assert s.state.rules.exiled_with[oid]==[s.state.rules.object_id(chosen)]
    assert s.state.rules.payments[oid].revealed==[chosen]
else:
    assert s.state.cards[source].zone=='p1:hand'
    assert s.state.cards[chosen].zone=='p1:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, chosen.id, stage],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_cost_exile_object_that_leaves_and_returns_before_resolution_is_not_linked(cards):
    s, source, chosen = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    original = s.state.rules.object_id(chosen.id)
    act(s, 'p1', type='move', card_ids=[chosen.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[chosen.id], to={'player': 'p1', 'zone': 'exile'})
    assert s.state.rules.object_id(chosen.id) != original
    settle(s)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    bounce(s, source)
    assert s.state.cards[chosen.id].zone == 'p1:exile'
    roundtrip(s)
