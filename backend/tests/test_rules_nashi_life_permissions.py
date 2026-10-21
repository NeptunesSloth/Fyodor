"""Nashi grants one shared land or life-paid spell play, following the exact exiled objects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, coverage, view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_reflexive_roll import combat
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/nashi_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NASHI = "Nashi, Moon Sage's Scion"


def resolved_trigger(cards, top='Lightning Bolt', *, own=(), blink=False):
    s = table(cards, list(dict.fromkeys([NASHI, 'Forest', 'Island', *own])), [top], ['Forest'])
    ninja = put(s, NASHI, 'battlefield')
    to_phase(s, 'main1', turn=4)
    cards_top = []
    for pid, name in [('p1', 'Forest'), ('p2', top), ('p3', 'Forest')]:
        card = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name)
        act(s, pid, type='move', card_ids=[card.id], to={'player': pid, 'zone': 'library'}, position='top')
        cards_top.append(card.id)
    combat(s, ninja)
    roundtrip(s)
    if blink:
        oid = s.state.rules.object_id(ninja.id)
        flicker = put(s, 'Ephemerate', 'hand')
        mana(s, W=1)
        act(s, 'p1', type='cast_spell', card_id=flicker.id, targets=[ninja.id])
        settle(s)
        assert s.state.rules.object_id(ninja.id) != oid
    settle(s)
    to_phase(s, 'main2', turn=4)
    assert all(s.state.cards[c].zone.endswith(':exile') for c in cards_top)
    grants = [p for p in s.state.rules.permissions if p.card in cards_top]
    assert len(grants) == 3 and len({p.group for p in grants}) == 1 and all(p.left == 1 for p in grants)
    return s, ninja, cards_top


def test_nashi_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NASHI)).level == 'FULL'


def test_one_spell_uses_life_and_consumes_shared_land_and_spell_group(cards):
    s, _, top = resolved_trigger(cards)
    life = s.state.players['p1'].life
    assert top[1] in view.hints(s.state, 'p1', cards)['free_castable']
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], targets=['p2'])
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    assert s.state.players['p1'].life == life - 1
    assert not [p for p in s.state.rules.permissions if p.card in top]
    settle(s)
    assert s.state.cards[top[1]].zone == 'p2:graveyard'
    roundtrip(s)


def test_one_land_costs_no_life_and_consumes_same_group(cards):
    s, _, top = resolved_trigger(cards)
    life = s.state.players['p1'].life
    act(s, 'p1', type='play_land', card_id=top[0])
    assert s.state.players['p1'].life == life
    assert not [p for p in s.state.rules.permissions if p.card in top]
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    roundtrip(s)


def test_x_is_zero_for_life_alternative(cards):
    s, _, top = resolved_trigger(cards, 'Blaze')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, x_value=4, targets=['p2'])
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, x_value=0, targets=['p2'])
    assert s.state.players['p1'].life == life - 1
    settle(s)
    roundtrip(s)


def test_hints_and_cast_both_reject_insufficient_life_without_spending_use(cards):
    s, _, top = resolved_trigger(cards, 'Grizzly Bears')
    act(s, 'p1', type='life', player='p1', delta=1 - s.state.players['p1'].life)
    assert top[1] not in view.hints(s.state, 'p1', cards)['free_castable']
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True)
    assert s.state.players['p1'].life == 1
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 3
    roundtrip(s)



@pytest.mark.parametrize('blocker', ['Angel of Jubilation', 'Platinum Emperion'])
@pytest.mark.parametrize('zero', [False, True])
def test_life_payment_restrictions_block_positive_cost_but_never_zero_life(cards, blocker, zero):
    name = 'Ancestral Vision' if zero else 'Grizzly Bears'
    s, _, top = resolved_trigger(cards, name, own=[blocker])
    put(s, blocker, 'battlefield')
    before = s.state.players['p1'].life
    offered = top[1] in view.hints(s.state, 'p1', cards)['free_castable']
    assert offered == zero
    if zero:
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p1'])
        settle(s)
        assert s.state.cards[top[1]].zone == 'p2:graveyard'
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=top[1], free=True)
        assert len([p for p in s.state.rules.permissions if p.card in top]) == 3
    assert s.state.players['p1'].life == before
    roundtrip(s)


@pytest.mark.parametrize('static,cost', [('Thalia, Guardian of Thraben', 1), ('Trinisphere', 3)])
def test_life_alternative_still_requires_final_mana_tax_or_floor(cards, static, cost):
    s, _, top = resolved_trigger(cards, own=[static])
    put(s, static, 'battlefield')
    life = s.state.players['p1'].life
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    assert s.state.players['p1'].life == life
    mana(s, C=cost)
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    assert s.state.players['p1'].life == life - 1
    settle(s)
    roundtrip(s)


def test_optional_additional_kicker_is_paid_in_addition_to_life(cards):
    s, _, top = resolved_trigger(cards, 'Burst Lightning')
    life, theirs = s.state.players['p1'].life, s.state.players['p2'].life
    mana(s, C=4)
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, kicker=1, targets=['p2'])
    assert s.state.players['p1'].life == life - 1
    settle(s)
    assert s.state.players['p2'].life == theirs - 4
    roundtrip(s)


def test_printed_alternative_cannot_replace_nashis_required_life_payment(cards):
    from app.rules.characteristics import as_cast

    s, _, top = resolved_trigger(cards, 'Force of Will', own=['Counterspell', 'Lightning Bolt'])
    blue = put(s, 'Counterspell', 'hand')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    spell = s.state.cards[top[1]]
    offer = next(o for o in alt_costs.offers(s.state, 'p1', spell, as_cast(spell, s.cards, None), s.cards) if o.key.startswith(spell.id + ":"))
    life = s.state.players['p1'].life
    with pytest.raises(ActionError, match='alternative cost'):
        act(s, 'p1', type='cast_spell', card_id=spell.id, free=True, alt_cost=offer.key, targets=[bolt.id])
    assert s.state.cards[blue.id].zone == 'p1:hand' and s.state.players['p1'].life == life
    act(s, 'p1', type='cast_spell', card_id=spell.id, free=True, targets=[bolt.id])
    assert s.state.players['p1'].life == life - 5
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name,face,expected', [('Fire // Ice', 0, 2), ('Fire // Ice', 1, 2),
    ('Valakut Awakening // Valakut Stoneforge', 0, 3), ('Bonecrusher Giant // Stomp', 0, 3), ('Bonecrusher Giant // Stomp', 1, 2)])
def test_life_uses_chosen_spell_face_mana_value(cards, name, face, expected):
    s, _, top = resolved_trigger(cards, name)
    life = s.state.players['p1'].life
    extra = {'targets': ['p2']} if name.startswith('Fire') or (name.startswith('Bonecrusher') and face == 1) else {}
    if name == 'Fire // Ice' and face == 0:
        extra['target_counts'] = [1]
    if name == 'Fire // Ice' and face == 1:
        extra = {'targets': [s.state.cards[next(c.id for c in s.state.cards.values() if c.name == NASHI)].id]}
    act(s, 'p1', type='cast_spell', card_id=top[1], face=face, free=True, **extra)
    assert s.state.players['p1'].life == life - expected
    settle(s)
    roundtrip(s)


def test_back_face_land_uses_shared_permission_without_life_cost(cards):
    s, _, top = resolved_trigger(cards, 'Valakut Awakening // Valakut Stoneforge')
    life = s.state.players['p1'].life
    act(s, 'p1', type='play_land', card_id=top[1], face=1)
    assert s.state.players['p1'].life == life and s.state.cards[top[1]].zone == 'p1:battlefield'
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_source_departure_does_not_end_grant_and_a_new_exile_object_does_not_inherit_it(cards):
    s, ninja, top = resolved_trigger(cards)
    act(s, 'p1', type='move', card_ids=[ninja.id], to={'zone': 'hand', 'player': 'p1'})
    assert top[1] in view.hints(s.state, 'p1', cards)['free_castable']
    act(s, 'p2', type='move', card_ids=[top[1]], to={'zone': 'hand', 'player': 'p2'})
    act(s, 'p2', type='move', card_ids=[top[1]], to={'zone': 'exile', 'player': 'p2'})
    assert top[1] not in view.hints(s.state, 'p1', cards)['free_castable']
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    act(s, 'p1', type='play_land', card_id=top[0])
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)


def test_permission_expires_at_end_of_turn(cards):
    s, _, top = resolved_trigger(cards)
    to_phase(s, 'main1', turn=5)
    assert not [p for p in s.state.rules.permissions if p.card in top]
    roundtrip(s)



def test_life_payment_can_equal_total_and_zero_does_not_forbid_it(cards):
    s, _, top = resolved_trigger(cards, 'Grizzly Bears', own=['Platinum Angel'])
    put(s, 'Platinum Angel', 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=2 - s.state.players['p1'].life)
    assert top[1] in view.hints(s.state, 'p1', cards)['free_castable']
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True)
    assert s.state.players['p1'].life == 0 and 'p1' not in s.state.rules.lost
    settle(s)
    assert s.state.cards[top[1]].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name,instant', [('Lightning Bolt', True), ('Grizzly Bears', False)])
def test_grant_preserves_normal_end_step_timing(cards, name, instant):
    s, _, top = resolved_trigger(cards, name)
    to_phase(s, 'end', turn=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=top[0])
    if instant:
        act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
        settle(s)
    else:
        assert top[1] not in view.hints(s.state, 'p1', cards)['free_castable']
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=top[1], free=True)
    roundtrip(s)


def test_exiled_land_does_not_grant_an_additional_land_play(cards):
    s, _, top = resolved_trigger(cards)
    ordinary = put(s, 'Island', 'hand')
    act(s, 'p1', type='play_land', card_id=ordinary.id)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=top[0])
    assert len([p for p in s.state.rules.permissions if p.card in top]) == 3
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    settle(s)
    roundtrip(s)



def test_copied_trigger_grants_independent_shared_one_card_groups(cards):
    s = table(cards, [NASHI, 'Strionic Resonator', 'Forest', 'Island'], ['Lightning Bolt', 'Grizzly Bears'], ['Forest', 'Island'])
    ninja = put(s, NASHI, 'battlefield')
    resonator = put(s, 'Strionic Resonator', 'battlefield')
    to_phase(s, 'main1', turn=4)
    for pid, names in [('p1', ['Forest', 'Island']), ('p2', ['Lightning Bolt', 'Grizzly Bears']), ('p3', ['Forest', 'Island'])]:
        for name in reversed(names):
            card = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name)
            act(s, pid, type='move', card_ids=[card.id], to={'player': pid, 'zone': 'library'}, position='top')
    combat(s, ninja)
    trigger = s.state.zones['stack'][-1]
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=resonator.id, ability=0, targets=[trigger])
    settle(s)
    to_phase(s, 'main2', turn=4)
    grants = [p for p in s.state.rules.permissions if p.life_mv]
    assert len(grants) == 6 and len({p.group for p in grants}) == 2
    bolt = next(p for p in grants if s.state.cards[p.card].name == 'Lightning Bolt')
    bears = next(p for p in grants if s.state.cards[p.card].name == 'Grizzly Bears')
    assert bolt.group != bears.group
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=bolt.card, free=True, targets=['p2'])
    settle(s)
    assert len([p for p in s.state.rules.permissions if p.life_mv]) == 3
    assert not any(p.group == bolt.group for p in s.state.rules.permissions)
    act(s, 'p1', type='cast_spell', card_id=bears.card, free=True)
    settle(s)
    assert s.state.players['p1'].life == life - 3
    assert not [p for p in s.state.rules.permissions if p.life_mv]
    roundtrip(s)


def test_adventure_creates_its_own_independent_normal_cost_permission(cards):
    s, _, top = resolved_trigger(cards, 'Bonecrusher Giant // Stomp')
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, face=1, targets=['p2'])
    settle(s)
    assert s.state.players['p1'].life == life - 2 and s.state.cards[top[1]].zone == 'p2:exile'
    assert not [p for p in s.state.rules.permissions if p.life_mv]
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=top[1], face=0)
    settle(s)
    assert s.state.cards[top[1]].zone == 'p1:battlefield' and s.state.cards[top[1]].owner == 'p2'
    assert s.state.players['p1'].life == life - 2
    roundtrip(s)



def test_blink_before_trigger_resolution_does_not_change_its_permission_controller(cards):
    s, ninja, top = resolved_trigger(cards, own=['Ephemerate'], blink=True)
    assert s.state.cards[ninja.id].zone == 'p1:battlefield'
    grants = [p for p in s.state.rules.permissions if p.card in top]
    assert len(grants) == 3 and all(p.player == 'p1' for p in grants)
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True, targets=['p2'])
    settle(s)
    assert s.state.players['p1'].life == life - 1
    roundtrip(s)
