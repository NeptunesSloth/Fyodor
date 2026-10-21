"""Canonical optional hand reveals size native payments and non-targeted returns."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/reveal_hand_count_family_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Scent of Brine', 'Brine Seer', "Rofellos's Gift"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def brine(cards, ability=False, target='Grizzly Bears', vanished=False, empty=False):
    s = table(cards, ['Scent of Brine', 'Brine Seer', 'Counterspell', 'Opt', 'Giant Growth', 'Grizzly Bears'], [target])
    source = put(s, 'Brine Seer' if ability else 'Scent of Brine', 'battlefield' if ability else 'hand')
    put(s, 'Scent of Brine' if ability else 'Brine Seer', 'graveyard')
    blue = [put(s, n, 'hand').id for n in ['Counterspell', 'Opt']]
    green = put(s, 'Giant Growth', 'hand')
    if target == 'Abrupt Decay':
        green = put(s, 'Grizzly Bears', 'battlefield')
    if empty:
        for cid in blue:
            act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p2')
    spell = put(s, target, 'hand', 'p2')
    mana(s, 'p2', C=1, G=2, B=1)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    act(s, 'p2', type='cast_spell', card_id=spell.id, **({'targets': [green.id]} if target == 'Abrupt Decay' else {}))
    wait_priority(s, 'p1')
    mana(s, C=2 if ability else 1, U=1)
    sid = spell.id
    act(s, 'p1', type='activate_ability' if ability else 'cast_spell', card_id=source.id,
        **({'ability': 0} if ability else {}), targets=[sid])
    if vanished:
        act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    return s, source, spell, blue, green


@pytest.mark.parametrize('ability', [False, True])
@pytest.mark.parametrize('payment', ['pay', 'decline', 'unavailable'])
def test_blue_reveals_size_actual_counter_payment(cards, ability, payment):
    s, source, spell, blue, green = brine(cards, ability)
    d = s.state.rules.decision
    assert d.resume['step'] == 'reveal_hand_cards' and d.player == 'p1'
    assert set(blue) <= {o.id for o in d.options} and green.id not in {o.id for o in d.options}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert green.id not in s.view('p2')['cards']
    # Remove the leftover mana from the spell payment before supplying the tax.
    act(s, 'p2', type='clear_mana', player='p2')
    if payment != 'unavailable':
        mana(s, 'p2', C=2)
    choose(s, blue)
    assert all(s.state.cards[c].zone == 'p1:hand' and '*' in s.state.cards[c].revealed_to for c in blue)
    if payment != 'unavailable':
        d = s.state.rules.decision
        assert d and d.player == 'p2' and d.resume['step'] == 'pay_or_sacrifice'
        assert d.display['cost'] == '{2}'
        choose(s, [payment])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == ('p2:battlefield' if payment == 'pay' else 'p2:graveyard')
    if payment == 'pay':
        assert not mana_pool(s, 'p2')
    if ability:
        assert s.state.cards[source.id].tapped and not mana_pool(s)
    roundtrip(s)


@pytest.mark.parametrize('empty', [False, True])
def test_zero_reveals_offer_zero_payment_without_forced_counter(cards, empty):
    s, _, spell, blue, _ = brine(cards, empty=empty)
    if empty:
        assert s.state.rules.decision.options == []
    choose(s, [])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and 'pay' in {o.id for o in d.options}
    assert d.display['cost'] == '{0}'
    choose(s, ['pay'])
    assert s.state.cards[spell.id].zone == 'p2:battlefield'
    roundtrip(s)


def gift(cards, n=2, available=3):
    names = ["Rofellos's Gift", 'Grizzly Bears', 'Giant Growth', 'Llanowar Elves', 'Counterspell',
             'Oblivion Ring', 'Pacifism', 'Wild Growth']
    s = table(cards, names, ['Wild Growth'])
    greens = [put(s, name, 'hand').id for name in ['Grizzly Bears', 'Giant Growth', 'Llanowar Elves']]
    blue = put(s, 'Counterspell', 'hand')
    gy = [put(s, name, 'graveyard').id for name in ['Oblivion Ring', 'Pacifism', 'Wild Growth'][:available]]
    foreign = put(s, 'Wild Growth', 'graveyard', 'p2')
    source = put(s, "Rofellos's Gift", 'hand')
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert {o.id for o in s.state.rules.decision.options} == set(greens)
    assert blue.id not in {o.id for o in s.state.rules.decision.options}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    choose(s, greens[:n])
    return s, gy, foreign, greens


@pytest.mark.parametrize('n,available', [(0, 3), (1, 3), (2, 3), (3, 2), (3, 0)])
def test_green_reveals_return_exactly_available_count_without_targeting(cards, n, available):
    s, gy, foreign, greens = gift(cards, n, available)
    count = min(n, available)
    if 0 < count < available:
        d = s.state.rules.decision
        assert d.resume['step'] == 'return_choice' and d.min_choices == d.max_choices == count
        assert {o.id for o in d.options} == set(gy)
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        choose(s, gy[:count])
    assert s.state.rules.decision is None
    assert sum(s.state.cards[c].zone == 'p1:hand' for c in gy) == count
    assert s.state.cards[foreign.id].zone == 'p2:graveyard'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in greens)
    roundtrip(s)


def test_illegal_counter_target_fizzles_before_hand_reveal(cards):
    s, source, spell, blue, _ = brine(cards, vanished=True)
    assert s.state.rules.decision is None and not s.state.zones['stack']
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all('*' not in s.state.cards[c].revealed_to for c in blue)
    roundtrip(s)


def test_uncounterable_spell_still_allows_reveal_and_payment_decline(cards):
    s, _, spell, blue, creature = brine(cards, target='Abrupt Decay')
    choose(s, blue[:1])
    d = s.state.rules.decision
    if d:
        assert d.resume['step'] == 'pay_or_sacrifice'
        choose(s, ['decline'])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_seer_is_a_real_tap_ability_with_sickness_and_mana_cost(cards):
    s = table(cards, ['Brine Seer'], ['Opt'])
    to_phase(s, 'main1', turn=2)
    source = put(s, 'Brine Seer', 'battlefield')
    spell = put(s, 'Opt', 'hand', 'p2')
    mana(s, 'p2', U=1)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    sid = spell.id
    wait_priority(s, 'p1')
    mana(s, C=2, U=1)
    with pytest.raises(ActionError, match='sick|turn|haste'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[sid])
    assert not s.state.cards[source.id].tapped and mana_pool(s) == {'C': 2, 'U': 1}
    roundtrip(s)


def test_return_prompt_rejects_duplicate_cards(cards):
    s, gy, _, _ = gift(cards, 2, 3)
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[gy[0], gy[0]])
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in gy)
    choose(s, gy[:2])
    assert all(s.state.cards[c].zone == 'p1:hand' for c in gy[:2])
    roundtrip(s)
