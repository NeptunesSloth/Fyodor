"""One source's once-per-own-turn free permission covers hand and library top together."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/one_multiverse_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'One with the Multiverse'


def setup(cards, *, top='Grizzly Bears', hand='Lightning Bolt', extra=()):
    s = table(cards, list(dict.fromkeys([NAME, top, hand, 'Forest', 'Island', *extra])), ['Counterspell', NAME])
    source = put(s, NAME, 'battlefield')
    spell = put(s, hand, 'hand')
    top_card = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == top and c.id != spell.id)
    act(s, 'p1', type='move', card_ids=[top_card.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    return s, source, spell, top_card


def use_key(s, source):
    return f"{s.state.rules.object_id(source.id)}:permission:2"


def cast(s, card, **kw):
    targets = ['p2'] if card.name in ('Lightning Bolt', 'Burst Lightning', 'Blaze') else []
    act(s, 'p1', type='cast_spell', card_id=card.id, targets=targets, **kw)


def test_one_with_multiverse_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('top_first', [False, True])
def test_hand_and_library_top_share_one_free_cast_each_own_turn(cards, top_first):
    s, source, hand, top = setup(cards)
    assert {hand.id, top.id} <= set(view.hints(s.state, 'p1', cards)['free_castable'])
    first, second = (top, hand) if top_first else (hand, top)
    cast(s, first, free=True)
    settle(s)
    assert s.state.rules.once_per_turn[use_key(s, source)] == s.state.turn.number
    assert second.id not in view.hints(s.state, 'p1', cards)['free_castable']
    with pytest.raises(ActionError):
        cast(s, second, free=True)
    roundtrip(s)


def test_paying_for_top_spell_and_playing_top_land_do_not_consume_free_use(cards):
    s, source, hand, top = setup(cards, top='Forest', extra=['Grizzly Bears'])
    life = s.state.players['p1'].life
    act(s, 'p1', type='play_land', card_id=top.id)
    bears = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Grizzly Bears')
    act(s, 'p1', type='move', card_ids=[bears.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    mana(s, G=1, C=1)
    cast(s, bears)
    settle(s)
    assert use_key(s, source) not in s.state.rules.once_per_turn
    cast(s, hand, free=True)
    settle(s)
    assert s.state.players['p1'].life == life
    roundtrip(s)


def test_top_look_and_hints_are_private_and_only_current_top_is_castable(cards):
    s, _, _, top = setup(cards)
    assert s.view('p1')['cards'][top.id]['name'] == 'Grizzly Bears'
    assert not s.view('p2')['cards'].get(top.id, {}).get('name')
    assert top.id in view.hints(s.state, 'p1', cards)['free_castable']
    buried = next(c for c in s.state.zones['p1:library'] if c != top.id)
    assert buried not in view.hints(s.state, 'p1', cards)['free_castable']
    roundtrip(s)


def test_normal_paid_top_instant_works_on_opponents_turn_but_free_use_does_not(cards):
    s, source, hand, top = setup(cards, top='Lightning Bolt', hand='Grizzly Bears')
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p1')
    assert top.id not in view.hints(s.state, 'p1', cards)['free_castable']
    with pytest.raises(ActionError):
        cast(s, top, free=True)
    mana(s, R=1)
    cast(s, top)
    settle(s)
    assert use_key(s, source) not in s.state.rules.once_per_turn
    roundtrip(s)


def test_countered_free_spell_still_consumes_its_use(cards):
    s, source, hand, top = setup(cards)
    cast(s, top, free=True)
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[top.id])
    settle(s)
    assert s.state.cards[top.id].zone == 'p1:graveyard'
    assert s.state.rules.once_per_turn[use_key(s, source)] == s.state.turn.number
    assert hand.id not in view.hints(s.state, 'p1', cards)['free_castable']
    roundtrip(s)


def test_source_blink_creates_new_use_but_control_changes_preserve_same_use(cards):
    s, source, hand, top = setup(cards, extra=['Flicker of Fate'])
    cast(s, top, free=True)
    settle(s)
    oid = s.state.rules.object_id(source.id)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p2', type='set_controller', card_ids=[source.id], player='p1')
    assert s.state.rules.object_id(source.id) == oid
    assert hand.id not in view.hints(s.state, 'p1', cards)['free_castable']
    blink = put(s, 'Flicker of Fate', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id) != oid
    cast(s, hand, free=True)
    settle(s)
    roundtrip(s)


def test_two_sources_allow_two_uses_and_explicit_source_choice_is_saved(cards):
    s, source, hand, top = setup(cards)
    second = put(s, NAME, 'battlefield', 'p2')
    act(s, 'p2', type='set_controller', card_ids=[second.id], player='p1')
    cast(s, top, free=True)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'slot' and len(d.options) == 2
    assert {o.card_id for o in d.options} == {source.id, second.id}
    roundtrip(s)
    chosen = use_key(s, source)
    assert chosen in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert use_key(s, source) in s.state.rules.once_per_turn and use_key(s, second) not in s.state.rules.once_per_turn
    cast(s, hand, free=True)
    settle(s)
    assert use_key(s, second) in s.state.rules.once_per_turn
    roundtrip(s)


@pytest.mark.parametrize('life_first', [False, True])
def test_citadel_life_alternative_is_a_real_choice_and_spends_only_chosen_permission(cards, life_first):
    s, source, hand, top = setup(cards, extra=["Bolas's Citadel"])
    put(s, "Bolas's Citadel", 'battlefield')
    life = s.state.players['p1'].life
    cast(s, top, free=True)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'slot' and len(d.options) == 2
    prefix = "Bolas's Citadel" if life_first else NAME
    chosen = next(o.id for o in d.options if o.label.startswith(prefix))
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.players['p1'].life == life - (2 if life_first else 0)
    assert (use_key(s, source) in s.state.rules.once_per_turn) != life_first
    if life_first:
        cast(s, hand, free=True)
        settle(s)
        assert use_key(s, source) in s.state.rules.once_per_turn
    else:
        assert hand.id not in view.hints(s.state, 'p1', cards)['free_castable']
    roundtrip(s)


def test_unaffordable_life_alternative_does_not_hide_valid_free_permission(cards):
    s, _, _, top = setup(cards, extra=["Bolas's Citadel"])
    put(s, "Bolas's Citadel", 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=1 - s.state.players['p1'].life)
    assert top.id in view.hints(s.state, 'p1', cards)['free_castable']
    cast(s, top, free=True)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(NAME))])
    settle(s)
    assert s.state.players['p1'].life == 1
    roundtrip(s)


def test_unlimited_identical_omniscience_does_not_spend_multiverse_use(cards):
    s, source, hand, top = setup(cards, extra=['Omniscience'])
    put(s, 'Omniscience', 'battlefield')
    cast(s, hand, free=True)
    assert s.state.rules.decision is None
    settle(s)
    assert use_key(s, source) not in s.state.rules.once_per_turn
    cast(s, top, free=True)
    settle(s)
    assert use_key(s, source) in s.state.rules.once_per_turn
    roundtrip(s)


def test_use_refreshes_next_own_turn(cards):
    s, source, hand, top = setup(cards)
    cast(s, top, free=True)
    settle(s)
    to_phase(s, 'main1', turn=4)
    cast(s, hand, free=True)
    settle(s)
    assert s.state.rules.once_per_turn[use_key(s, source)] == 4
    roundtrip(s)


def test_prototype_works_with_free_cast_permission(cards):
    s, _, _, top = setup(cards, top='Phyrexian Fleshgorger', hand='Burst Lightning')
    cast(s, top, free=True, prototype=True)
    settle(s)
    card_now = s.state.cards[top.id]
    from app.rules.plan import Plan
    assert Plan(s.state, 'p1', s.cards, None).ch(card_now).power == '3'
    roundtrip(s)



@pytest.mark.parametrize('life_first', [False, True])
def test_limited_life_alternative_consumes_only_its_own_source(cards, life_first):
    s, source, _, top = setup(cards, top='Omniscience', extra=["Demon of Fate's Design"])
    demon = put(s, "Demon of Fate's Design", 'battlefield')
    # Demon's alternative applies only to spells cast from hand.
    act(s, 'p1', type='move', card_ids=[top.id], to={'player': 'p1', 'zone': 'hand'})
    life = s.state.players['p1'].life
    cast(s, top, free=True)
    d = s.state.rules.decision
    assert d and len(d.options) == 2
    prefix = "Demon of Fate's Design" if life_first else NAME
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(prefix))])
    settle(s)
    assert s.state.players['p1'].life == life - (10 if life_first else 0)
    assert (use_key(s, source) in s.state.rules.once_per_turn) != life_first
    assert any(k.startswith(s.state.rules.object_id(demon.id) + ':permission:') for k in s.state.rules.once_per_turn) == life_first
    roundtrip(s)


def test_forbidden_life_payment_does_not_hide_available_free_permission(cards):
    s, _, _, top = setup(cards, extra=["Bolas's Citadel", 'Angel of Jubilation'])
    put(s, "Bolas's Citadel", 'battlefield')
    put(s, 'Angel of Jubilation', 'battlefield')
    assert top.id in view.hints(s.state, 'p1', cards)['free_castable']
    cast(s, top, free=True)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(NAME))])
    settle(s)
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('static,cost', [('Thalia, Guardian of Thraben', 1), ('Trinisphere', 3)])
def test_free_cast_still_pays_required_tax_or_floor_and_failed_payment_keeps_use(cards, static, cost):
    s, source, _, top = setup(cards, top='Lightning Bolt', hand='Grizzly Bears', extra=[static])
    put(s, static, 'battlefield')
    with pytest.raises(ActionError):
        cast(s, top, free=True)
    assert use_key(s, source) not in s.state.rules.once_per_turn
    mana(s, C=cost)
    cast(s, top, free=True)
    settle(s)
    assert use_key(s, source) in s.state.rules.once_per_turn
    roundtrip(s)


def test_free_spell_allows_additional_kicker_and_forces_printed_x_to_zero(cards):
    s, source, hand, _ = setup(cards, top='Blaze', hand='Burst Lightning')
    top = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Blaze')
    with pytest.raises(ActionError):
        cast(s, top, free=True, x_value=5)
    assert use_key(s, source) not in s.state.rules.once_per_turn
    mana(s, C=4)
    cast(s, hand, free=True, kicker=1)
    settle(s)
    assert s.state.players['p2'].life == 36
    roundtrip(s)


def test_middle_paid_top_permission_allows_printed_alternative_without_using_free_ability(cards):
    s, source, bolt, force = setup(cards, top='Force of Will', extra=['Counterspell', 'Grizzly Bears'])
    blue = put(s, 'Counterspell', 'hand')
    bears = put(s, 'Grizzly Bears', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast(s, bolt)
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=force.id, alt_cost=f'{force.id}:0', targets=[bolt.id])
    settle(s)
    assert s.state.players['p1'].life == life - 1 and s.state.cards[blue.id].zone == 'p1:exile'
    assert use_key(s, source) not in s.state.rules.once_per_turn
    cast(s, bears, free=True)
    settle(s)
    assert use_key(s, source) in s.state.rules.once_per_turn
    roundtrip(s)
