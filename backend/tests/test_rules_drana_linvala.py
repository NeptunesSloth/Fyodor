"""CR 113.10, 613.8: borrow actual abilities, preserving their grant provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import abilities_of, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/drana_linvala_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='drl', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, own=(), enemy=()):
    return build(cards, ['Drana and Linvala', *own], bob=[(1, n) for n in enemy] + [(10, 'Island')])


def borrowed(s, source, cards):
    return [a for a in Plan(s.state, source.controller, cards, None).ch(s.state.cards[source.id]).abilities
            if a.index >= abilities_of.BORROWED]


def test_card_is_supported(cards):
    assert coverage.of_card_data(cards.resolve('Drana and Linvala')).level == 'FULL'


def test_borrowed_self_regeneration_can_use_another_color(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, enemy=['Cudgel Troll'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    (ab,) = borrowed(s, drana, cards)
    assert 'this permanent' in ab.text
    mana(s, R=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    settle(s)
    assert s.state.rules.regen_shields == {s.state.rules.object_id(drana.id): 1}
    assert not s.state.cards[troll.id].tapped
    roundtrip(s)


def test_borrowed_mana_abilities_are_present_but_lenders_cannot_activate(cards):
    s = game(cards, enemy=['Llanowar Elves'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    (ab,) = borrowed(s, drana, cards)
    assert ab.kind == 'mana'
    from app.rules.casting import mana_abilities

    assert mana_abilities(s.state, elf, cards) == []
    roundtrip(s)


def test_static_granted_mana_ability_is_borrowed_and_removed_with_attachment(cards):
    s = game(cards, enemy=['Cudgel Troll', 'Paradise Mantle'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    mantle = put(s, 'Paradise Mantle', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[mantle.id], to=troll.id)
    lines = borrowed(s, drana, cards)
    assert len(lines) == 2 and len([a for a in lines if a.kind == 'mana']) == 1
    act(s, 'p2', type='move', card_ids=[mantle.id], to={'player': 'p2', 'zone': 'graveyard'})
    assert len(borrowed(s, drana, cards)) == 1
    roundtrip(s)


def test_lender_ability_loss_applies_before_borrowing(cards):
    s = game(cards, enemy=['Cudgel Troll', 'Darksteel Mutation'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    aura = put(s, 'Darksteel Mutation', 'battlefield', 'p2')
    assert borrowed(s, drana, cards)
    act(s, 'p2', type='attach', card_ids=[aura.id], to=troll.id)
    assert not borrowed(s, drana, cards)
    roundtrip(s)


def test_recursive_lender_includes_an_ability_from_a_nonopponent_creature(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Cudgel Troll'], enemy=['Experiment Kraj'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield')
    put(s, 'Experiment Kraj', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[troll.id], kind='+1/+1', delta=1)
    lines = borrowed(s, drana, cards)
    regen = next(a for a in lines if 'Regenerate' in a.text)
    assert regen.index > 10_000_000
    mana(s, R=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=regen.index)
    settle(s)
    assert s.state.rules.regen_shields == {s.state.rules.object_id(drana.id): 1}
    roundtrip(s)


def test_spending_permission_does_not_cover_another_static_granted_ability(cards):
    from app.rules.casting import ability_cost
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Dragon Mantle'], enemy=['Cudgel Troll'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    aura = put(s, 'Dragon Mantle', 'battlefield')
    put(s, 'Cudgel Troll', 'battlefield', 'p2')
    act(s, 'p1', type='attach', card_ids=[aura.id], to=drana.id)
    plan = Plan(s.state, 'p1', cards, None)
    ch = plan.ch(s.state.cards[drana.id])
    own_untap = next(a for a in ch.abilities if a.kind == 'activated' and a.index < abilities_of.BORROWED and '+1/+0' in a.text)
    assert ability_cost(ch, own_untap, state=s.state, card=s.state.cards[drana.id], info=cards).mana == '{R}'
    mana(s, U=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=drana.id, ability=own_untap.index)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_dependency_cycles_apply_each_borrowing_effect_once_in_timestamp_order(cards):
    s = game(cards, own=['Experiment Kraj'], enemy=['Experiment Kraj'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    first = put(s, 'Experiment Kraj', 'battlefield')
    second = put(s, 'Experiment Kraj', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[first.id, second.id], kind='+1/+1', delta=1)
    assert len(borrowed(s, first, cards)) == 1
    assert len(borrowed(s, second, cards)) == 2
    assert len(borrowed(s, drana, cards)) == 3  # only the opposing Kraj's three abilities
    roundtrip(s)


def test_borrowed_colored_mana_ability_can_use_another_color(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, enemy=['Orochi Leafcaller'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    put(s, 'Orochi Leafcaller', 'battlefield', 'p2')
    (ab,) = borrowed(s, drana, cards)
    assert ab.kind == 'mana'
    mana(s, R=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index, mana_choice='U')
    assert mana_pool(s, 'p1') == {'U': 1}
    roundtrip(s)


def test_borrowed_counter_cost_and_effect_use_the_borrower(cards):
    s = game(cards, enemy=['Devoted Druid'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    druid = put(s, 'Devoted Druid', 'battlefield', 'p2')
    ab = next(a for a in borrowed(s, drana, cards) if a.kind == 'activated')
    act(s, 'p1', type='tap', card_ids=[drana.id], tapped=True)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    settle(s)
    assert s.state.cards[drana.id].counters == {'-1/-1': 1}
    assert s.state.cards[druid.id].counters == {}
    assert not s.state.cards[drana.id].tapped
    roundtrip(s)


def test_lender_departure_does_not_remove_an_ability_already_on_the_stack(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, enemy=['Cudgel Troll'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    (ab,) = borrowed(s, drana, cards)
    mana(s, R=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    act(s, 'p2', type='move', card_ids=[troll.id], to={'player': 'p2', 'zone': 'graveyard'})
    assert not borrowed(s, drana, cards)
    settle(s)
    assert s.state.rules.regen_shields == {s.state.rules.object_id(drana.id): 1}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_more_than_thirty_two_lender_abilities_are_preserved_without_index_aliases(cards):
    s = game(cards, enemy=['Cudgel Troll', *['Paradise Mantle'] * 33])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    mantles = [c.id for c in s.state.cards.values() if c.name == 'Paradise Mantle']
    assert len(mantles) == 33
    act(s, 'p2', type='move', card_ids=mantles, to={'player': 'p2', 'zone': 'battlefield'})
    act(s, 'p2', type='attach', card_ids=mantles, to=troll.id)
    lines = borrowed(s, drana, cards)
    assert len(lines) == 34
    assert len({a.index for a in lines}) == 34
    assert len([a for a in lines if a.kind == 'mana']) == 33
    assert len([a for a in lines if a.index >= 1 << 40]) == 2
    roundtrip(s)


def test_controller_not_owner_determines_which_lender_is_available(cards):
    s = game(cards, own=['Cudgel Troll'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield')
    assert not borrowed(s, drana, cards)
    act(s, 'p1', type='set_controller', card_ids=[troll.id], player='p2')
    assert len(borrowed(s, drana, cards)) == 1
    assert s.state.cards[troll.id].owner == 'p1'
    act(s, 'p2', type='set_controller', card_ids=[troll.id], player='p1')
    assert not borrowed(s, drana, cards)
    roundtrip(s)


def test_another_borrower_does_not_inherit_drana_spending_permission(cards):
    from app.rules.casting import ability_cost

    s = game(cards, own=['Experiment Kraj'], enemy=['Cudgel Troll'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    kraj = put(s, 'Experiment Kraj', 'battlefield')
    put(s, 'Cudgel Troll', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[drana.id], kind='+1/+1', delta=1)
    plan = Plan(s.state, 'p1', cards, None)
    ch = plan.ch(s.state.cards[kraj.id])
    (regen,) = [a for a in ch.abilities if 'Regenerate' in a.text]
    assert regen.borrowed_color is None
    assert ability_cost(ch, regen, state=s.state, card=s.state.cards[kraj.id], info=cards).mana == '{G}'
    roundtrip(s)


def test_large_dependency_chains_are_iterative_and_cycles_keep_timestamp_order():
    deps = {i: ({i + 1} if i < 1499 else set()) for i in range(1500)}
    times = {i: (i,) for i in deps}
    assert abilities_of._dependency_order(deps, times) == list(reversed(range(1500)))
    assert abilities_of._dependency_order({0: {1}, 1: {0}, 2: {0}}, {0: (2,), 1: (1,), 2: (0,)}) == [1, 0, 2]


def test_colliding_provenance_indices_remain_distinct_and_replay_stable(cards, monkeypatch):
    monkeypatch.setattr(abilities_of, '_provenance_index', lambda origin: abilities_of._PROVENANCE_BASE)
    s = game(cards, own=['Experiment Kraj'], enemy=['Experiment Kraj'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    first = put(s, 'Experiment Kraj', 'battlefield')
    second = put(s, 'Experiment Kraj', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[first.id, second.id], kind='+1/+1', delta=1)
    lines = borrowed(s, drana, cards)
    assert len(lines) == len({a.index for a in lines}) == 3
    before = [(a.index, a.borrowed_origin) for a in lines]
    roundtrip(s)
    assert [(a.index, a.borrowed_origin) for a in borrowed(s, drana, cards)] == before


@pytest.mark.parametrize('payer', ['mana', 'life', 'mana_with_life_banned'])
def test_borrowed_phyrexian_cost_preserves_life_option_and_other_color_payment(cards, payer):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Angel of Jubilation'], enemy=['Moltensteel Dragon'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    put(s, 'Moltensteel Dragon', 'battlefield', 'p2')
    if payer == 'mana_with_life_banned':
        put(s, 'Angel of Jubilation', 'battlefield')
    if payer != 'life':
        mana(s, U=1)
    (ab,) = borrowed(s, drana, cards)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    d = s.state.rules.decision
    if payer == 'mana':
        assert d and d.resume['step'] == 'phyrexian'
        assert 'one mana of any type or 2 life' in d.prompt
        option = next(o for o in d.options if 'one mana of any type' in o.label)
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[drana.id]).pt == (4, 4), (ab, s.state.rules.effects, s.state.rules.decision)
    assert s.state.players['p1'].life == (38 if payer == 'life' else 40)
    assert mana_pool(s, 'p1') == {}
    roundtrip(s)


def test_any_color_phyrexian_internal_choice_does_not_widen_other_colored_costs():
    from app.rules import mana

    original = mana.parse_cost('{C}{2/W}{R/P}')
    changed = mana.spend_as(original, 'color')
    assert changed.colored == ('C',)
    assert changed.hybrid == (('2', 'W'),)
    assert changed.phyrexian == (mana.ANY_PHYREXIAN,)
    assert mana.parse_cost(changed.text()) == changed
    assert not mana.parse_cost('{C/P}').phyrexian  # no new printed Phyrexian symbol family


def test_canceling_phyrexian_mana_payment_spends_neither_life_nor_mana(cards):
    s = game(cards, own=['Island'], enemy=['Moltensteel Dragon'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    island = put(s, 'Island', 'battlefield')
    put(s, 'Moltensteel Dragon', 'battlefield', 'p2')
    act(s, 'p1', type='set_prefs', payment='self')
    (ab,) = borrowed(s, drana, cards)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'phyrexian'
    option = next(o for o in d.options if 'one mana of any type' in o.label)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pay_mana'
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.rules.decision is None
    assert not s.state.zones.get('stack')
    assert not s.state.cards[island.id].tapped
    assert s.state.players['p1'].life == 40 and mana_pool(s, 'p1') == {}
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[drana.id]).pt == (3, 4)
    roundtrip(s)


def test_face_down_creature_lends_visible_granted_abilities_without_its_hidden_text(cards):
    s = game(cards, enemy=['Cudgel Troll', 'Paradise Mantle'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    troll = put(s, 'Cudgel Troll', 'battlefield', 'p2')
    mantle = put(s, 'Paradise Mantle', 'battlefield', 'p2')
    act(s, 'p2', type='face_down', card_ids=[troll.id], face_down=True, kind='morph')
    assert not borrowed(s, drana, cards)
    act(s, 'p2', type='attach', card_ids=[mantle.id], to=troll.id)
    (ab,) = borrowed(s, drana, cards)
    assert ab.kind == 'mana' and 'Regenerate' not in ab.text
    assert 'Cudgel Troll' not in ab.text
    roundtrip(s)
