"""Hand-reveal mana abilities resolve without the stack, including nested payments."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Metalworker', 'Sacellum Godspeaker', 'Rosheen, Roaring Prophet']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/reveal_hand_mana_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def setup(cards, name, supports=()):
    names = [name, 'Sol Ring', 'Mind Stone', 'Gigantosaurus', 'Siege Wurm', 'Stonecoil Serpent', 'Fireball', *supports]
    s = table(cards, list(dict.fromkeys(names)))
    source = put(s, name, 'battlefield')
    settle(s)
    # Rosheen's real ETB is resolved separately; avoid a library-selection prompt here.
    if s.state.rules.decision is not None:
        answer(s, [])
        settle(s)
    to_phase(s, 'main1', turn=4)
    return s, source


def activate(s, source):
    wait_priority(s, 'p1')
    assert source.id not in {x.card_id for x in casting.mana_sources(s.state, 'p1', s.cards)}
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1 if source.name == NAMES[2] else 0)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'reveal_mana' and d.min_choices == 0
    assert s.state.cards[source.id].tapped and not s.state.zones.get('stack')
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert source.id not in {x.card_id for x in casting.mana_sources(s.state, 'p1', s.cards)}
    return d


@pytest.mark.parametrize('name,matching,symbol,per', [
    ('Metalworker', ['Sol Ring', 'Mind Stone'], 'C', 2),
    ('Sacellum Godspeaker', ['Gigantosaurus', 'Siege Wurm'], 'G', 1),
    ('Rosheen, Roaring Prophet', ['Stonecoil Serpent', 'Fireball'], 'C', 2),
])
@pytest.mark.parametrize('n', [0, 1, 2])
def test_immediate_private_reveal_produces_exact_amount(cards, name, matching, symbol, per, n):
    s, source = setup(cards, name)
    chosen = [put(s, name, 'hand').id for name in matching]
    d = activate(s, source)
    assert set(chosen) <= {o.id for o in d.options}
    answer(s, chosen[:n])
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    if name == NAMES[2]:
        assert len(s.state.players['p1'].mana_units) == per*n
    else:
        assert mana_pool(s) == ({symbol: per*n} if n else {})
    assert all(s.state.cards[c].zone == 'p1:hand' for c in chosen)
    assert all('*' in s.state.cards[c].revealed_to for c in chosen[:n])
    assert all('*' not in s.state.cards[c].revealed_to for c in chosen[n:])
    assert s.state.rules.priority == 'p1'
    units = s.state.players['p1'].mana_units
    if name == NAMES[2] and n:
        assert all(u.only and 'cost_x' in u.only for u in units)
    roundtrip(s)


def test_metalworker_whole_production_doubles_then_bonus_once(cards):
    s, source = setup(cards, 'Metalworker', ['Mana Reflection', 'Forsaken Monument'])
    put(s, 'Mana Reflection', 'battlefield')
    put(s, 'Forsaken Monument', 'battlefield')
    hand = [put(s, n, 'hand').id for n in ['Sol Ring', 'Mind Stone']]
    activate(s, source)
    answer(s, hand)
    assert mana_pool(s) == {'C': 9}  # 2 cards ×2 mana ×2 replacement +1 triggered mana
    assert s.state.rules.decision is None
    roundtrip(s)


def test_zero_reveal_does_not_trigger_forsaken_monument(cards):
    s, source = setup(cards, 'Metalworker', ['Forsaken Monument'])
    put(s, 'Forsaken Monument', 'battlefield')
    activate(s, source)
    answer(s, [])
    assert mana_pool(s) == {} and s.state.rules.decision is None
    roundtrip(s)


def test_native_self_payment_nests_reveal_and_resumes_cast(cards):
    s, source = setup(cards, 'Metalworker')
    hand = [put(s, n, 'hand').id for n in ['Sol Ring', 'Mind Stone']]
    spell = put(s, 'Stonecoil Serpent', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=3)
    outer = s.state.rules.decision
    assert outer.resume['step'] == 'pay_mana' and source.id in outer.display['sources']
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.rules.payment_outer.id == outer.id
    assert s.state.rules.decision.resume['step'] == 'reveal_mana'
    answer(s, hand)
    assert s.state.rules.payment_outer is None
    assert s.state.cards[spell.id].zone == 'stack' and mana_pool(s) == {'C': 1}
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].counters['+1/+1'] == 3
    roundtrip(s)


def test_rosheen_mana_restriction_is_on_cost_not_only_x_portion(cards):
    s, source = setup(cards, NAMES[2])
    revealed = put(s, 'Fireball', 'hand')
    stone = put(s, 'Mind Stone', 'hand')
    activate(s, source)
    answer(s, [revealed.id])
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=stone.id)
    spell = put(s, 'Stonecoil Serpent', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2)
    settle(s)
    assert s.state.cards[spell.id].counters['+1/+1'] == 2
    assert not mana_pool(s)
    roundtrip(s)


def test_empty_matching_hand_still_private_and_activation_cannot_be_responded_to(cards):
    s, source = setup(cards, 'Metalworker')
    for cid in list(s.state.zones['p1:hand']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    d = activate(s, source)
    assert d.options == [] and d.max_choices == 0
    with pytest.raises(ActionError):
        act(s, 'p2', type='pass_priority')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s, [])
    assert not mana_pool(s) and s.state.cards[source.id].tapped
    roundtrip(s)


def test_real_mana_ability_obeys_tap_sickness(cards):
    s = table(cards, ['Metalworker', 'Sol Ring'])
    source = put(s, 'Metalworker', 'battlefield')
    put(s, 'Sol Ring', 'hand')
    with pytest.raises(ActionError, match='sick|turn|haste'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert not s.state.cards[source.id].tapped and s.state.rules.decision is None
    roundtrip(s)


def test_rosheen_multiplier_keeps_restriction_on_every_generated_unit(cards):
    s, source = setup(cards, NAMES[2], ['Mana Reflection'])
    put(s, 'Mana Reflection', 'battlefield')
    revealed = put(s, 'Fireball', 'hand')
    activate(s, source)
    answer(s, [revealed.id])
    assert not mana_pool(s)
    assert len(s.state.players['p1'].mana_units) == 4
    assert all('cost_x' in unit.only for unit in s.state.players['p1'].mana_units)
    roundtrip(s)


def test_native_nested_zero_reveal_restores_original_unpaid_prompt(cards):
    s, source = setup(cards, 'Metalworker')
    spell = put(s, 'Stonecoil Serpent', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=3)
    outer = s.state.rules.decision
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s, [])
    assert s.state.rules.payment_outer is None
    assert s.state.rules.decision.id == outer.id
    assert s.state.cards[spell.id].zone == 'p1:hand' and not mana_pool(s)
    mana(s, C=3)
    # Adding external mana is a table tool; clicking Done asks the ordinary payer to recheck it.
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_godspeaker_requires_creature_card_power_at_least_five(cards):
    s, source = setup(cards, 'Sacellum Godspeaker', [NAMES[2]])
    for cid in list(s.state.zones['p1:hand']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    high = put(s, 'Gigantosaurus', 'hand')
    for name in [NAMES[2], 'Mind Stone', 'Stonecoil Serpent']:
        put(s, name, 'hand')
    d = activate(s, source)
    assert {o.id for o in d.options} == {high.id}
    answer(s, [high.id])
    assert mana_pool(s) == {'G': 1}
    roundtrip(s)


def test_rosheen_counts_cards_not_number_of_x_symbols(cards):
    s, source = setup(cards, NAMES[2], ['Hangarback Walker', 'Hydra Broodmaster'])
    for cid in list(s.state.zones['p1:hand']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    double_x = put(s, 'Hangarback Walker', 'hand')
    put(s, 'Hydra Broodmaster', 'hand')
    d = activate(s, source)
    assert {o.id for o in d.options} == {double_x.id}
    answer(s, [double_x.id])
    assert len(s.state.players['p1'].mana_units) == 2
    roundtrip(s)


def test_actual_rosheen_cast_mills_six_and_optionally_recovers_x_card(cards):
    names = [NAMES[2], 'Fireball', 'Stonecoil Serpent', 'Mind Stone', 'Gigantosaurus', 'Sol Ring', 'Siege Wurm']
    s = table(cards, names)
    source = put(s, NAMES[2], 'hand')
    for cid in list(s.state.zones['p1:library']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    top = [put(s, name, 'library').id for name in names[1:]]
    mana(s, C=2, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == set(top[:2])
    answer(s, [top[0]])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[top[0]].zone == 'p1:hand'
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in top[1:])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_two_whole_production_replacements_persist_the_order_choice(cards):
    s, source = setup(cards, 'Metalworker', ['Mana Reflection', 'Nyxbloom Ancient'])
    put(s, 'Mana Reflection', 'battlefield')
    put(s, 'Nyxbloom Ancient', 'battlefield')
    hand = [put(s, n, 'hand').id for n in ['Sol Ring', 'Mind Stone']]
    activate(s, source)
    answer(s, hand)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'reveal_mana_replace' and len(d.options) == 2
    answer(s, [d.options[-1].id])
    assert mana_pool(s) == {'C': 24} and s.state.rules.decision is None
    roundtrip(s)


def test_rosheen_trigger_bonus_is_unrestricted_and_not_doubled(cards):
    s, source = setup(cards, NAMES[2], ['Mana Reflection', 'Forsaken Monument'])
    put(s, 'Mana Reflection', 'battlefield')
    put(s, 'Forsaken Monument', 'battlefield')
    revealed = put(s, 'Fireball', 'hand')
    ring = put(s, 'Sol Ring', 'hand')
    activate(s, source)
    answer(s, [revealed.id])
    assert mana_pool(s) == {'C': 1}
    assert sum(bool(u.only) for u in s.state.players['p1'].mana_units) == 4
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    assert not mana_pool(s)
    assert len(s.state.players['p1'].mana_units) == 4
    roundtrip(s)


@pytest.mark.parametrize('blocked', [False, True])
def test_real_mana_classification_distinguishes_activation_prohibitions(cards, blocked):
    s, source = setup(cards, 'Metalworker', ["Faith's Fetters", 'Collector Ouphe'])
    revealed = put(s, 'Sol Ring', 'hand')
    if blocked:
        put(s, 'Collector Ouphe', 'battlefield')
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        assert not s.state.cards[source.id].tapped and s.state.rules.decision is None
    else:
        fetters = put(s, "Faith's Fetters", 'hand')
        mana(s, C=3, W=1)
        act(s, 'p1', type='cast_spell', card_id=fetters.id, targets=[source.id])
        settle(s)
        assert s.state.cards[fetters.id].attached_to == source.id
        activate(s, source)
        answer(s, [revealed.id])
        assert mana_pool(s) == {'C': 2}
    roundtrip(s)


def test_mana_resolution_retains_original_source_oid_after_departure(cards):
    s, source = setup(cards, 'Metalworker')
    revealed = put(s, 'Sol Ring', 'hand')
    old = s.state.rules.object_id(source.id)
    activate(s, source)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s, [revealed.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert mana_pool(s) == {'C': 2}
    assert all(u.src == old for u in s.state.players['p1'].mana_units)
    roundtrip(s)


def test_attached_land_bonus_uses_final_production_once(cards):
    s, source = setup(cards, 'Metalworker', ['Ashaya, Soul of the Wild', 'Wild Growth'])
    put(s, 'Ashaya, Soul of the Wild', 'battlefield')
    aura = put(s, 'Wild Growth', 'hand')
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[source.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == source.id
    hand = [put(s, n, 'hand').id for n in ['Sol Ring', 'Mind Stone']]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s, hand)
    assert mana_pool(s) == {'C': 4, 'G': 1}
    assert any(u.src == s.state.rules.object_id(aura.id) for u in s.state.players['p1'].mana_units if u.sym == 'G')
    roundtrip(s)


def test_creature_mana_trigger_adds_once_not_once_per_revealed_card(cards):
    s, source = setup(cards, 'Sacellum Godspeaker', ['Kinnan, Bonder Prodigy'])
    put(s, 'Kinnan, Bonder Prodigy', 'battlefield')
    hand = [put(s, n, 'hand').id for n in ['Gigantosaurus', 'Siege Wurm']]
    activate(s, source)
    answer(s, hand)
    assert mana_pool(s) == {'G': 3}
    roundtrip(s)


@pytest.mark.parametrize('payment', ['pay', 'decline', 'empty_decline', 'empty_pay'])
def test_mana_ability_can_be_activated_during_resolving_unless_payment(cards, payment):
    s = table(cards, ['Metalworker', 'Sol Ring', 'Mind Stone', 'Hangarback Walker'], ['Mana Leak'])
    source = put(s, 'Metalworker', 'battlefield')
    revealed = put(s, 'Sol Ring', 'hand')
    extra = put(s, 'Hangarback Walker', 'hand')
    spell = put(s, 'Mind Stone', 'hand')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='set_prefs', payment='self', hold_priority=True)
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    if payment.startswith('empty'):
        for cid in list(s.state.zones['p1:hand']):
            act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    wait_priority(s, 'p2')
    leak = put(s, 'Mana Leak', 'hand', 'p2')
    mana(s, 'p2', C=1, U=1)
    act(s, 'p2', type='cast_spell', card_id=leak.id, targets=[spell.id])
    settle(s)
    outer = s.state.rules.decision
    assert outer and outer.player == 'p1' and outer.resume['step'] == 'pay_or_sacrifice'
    assert outer.resume['cost'] == '{3}'
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.rules.payment_outer.id == outer.id
    if payment.startswith('empty'):
        assert s.state.rules.decision.options == []
    answer(s, [] if payment.startswith('empty') else [revealed.id, extra.id])
    assert s.state.rules.decision.id == outer.id
    assert mana_pool(s) == ({} if payment.startswith('empty') else {'C': 4})
    if payment == 'empty_pay':
        d = s.state.rules.decision
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
        assert s.state.rules.decision.id == outer.id
    answer(s, ['pay' if payment == 'pay' else 'decline'])
    settle(s)
    assert s.state.cards[spell.id].zone == ('p1:battlefield' if payment == 'pay' else 'p1:graveyard')
    assert s.state.rules.decision is None and s.state.rules.payment_outer is None
    assert mana_pool(s) == ({'C': 1} if payment == 'pay' else {'C': 4} if payment == 'decline' else {})
    roundtrip(s)


def test_amount_replacement_becomes_applicable_only_after_doubler(cards):
    s, source = setup(cards, 'Sacellum Godspeaker', ['Ashaya, Soul of the Wild', 'Mana Reflection', 'Damping Sphere'])
    for name in ['Ashaya, Soul of the Wild', 'Mana Reflection', 'Damping Sphere']:
        put(s, name, 'battlefield')
    revealed = put(s, 'Gigantosaurus', 'hand')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s, [revealed.id])
    # The initial one G cannot apply Sphere first to dodge it; Reflection makes two,
    # at which point Sphere becomes applicable and replaces them with one C.
    assert s.state.rules.decision is None and mana_pool(s) == {'C': 1}
    roundtrip(s)


@pytest.mark.parametrize('empty', [False, True])
def test_generic_optional_payment_uses_opponents_manual_mana_and_preserves_decline(cards, empty):
    s = table(cards, ['Rites of Refusal', 'Fireball'], ['Metalworker', 'Sol Ring', 'Mind Stone', 'Grizzly Bears'])
    source = put(s, 'Metalworker', 'battlefield', 'p2')
    hand = [put(s, name, 'hand', 'p2').id for name in ['Sol Ring', 'Mind Stone']]
    rites = put(s, 'Rites of Refusal', 'hand')
    discard = put(s, 'Fireball', 'hand')
    to_phase(s, 'main1', turn=5)
    spell = put(s, 'Grizzly Bears', 'hand', 'p2')
    mana(s, 'p2', C=1, G=1)
    act(s, 'p2', type='set_prefs', hold_priority=True, payment='self')
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    if empty:
        for cid in list(s.state.zones['p2:hand']):
            act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'graveyard'})
    wait_priority(s, 'p1')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=rites.id, targets=[spell.id])
    settle(s)
    answer(s, [discard.id])
    outer = s.state.rules.decision
    assert outer and outer.player == 'p2' and outer.resume.get('opt') is not None
    assert outer.display['cost'] == '{3}'
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=0)
    if empty:
        assert s.state.rules.decision.options == []
    answer(s, [] if empty else hand)
    assert s.state.rules.decision.id == outer.id
    answer(s, ['decline' if empty else 'pay'])
    settle(s)
    assert s.state.rules.decision is None and s.state.rules.payment_outer is None
    assert s.state.cards[spell.id].zone == ('p2:graveyard' if empty else 'p2:battlefield')
    assert mana_pool(s, 'p2') == ({} if empty else {'C': 1})
    roundtrip(s)
