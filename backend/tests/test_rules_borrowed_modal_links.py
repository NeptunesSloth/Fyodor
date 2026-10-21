"""CR 607.5/700.2: supported inherited abilities keep fresh links and mode identities."""
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
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_drana_linvala import borrowed

DATA = Path(__file__).parent / 'fixtures/borrowed_modal_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='bml', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, own=(), enemy=()):
    return build(cards, ['Drana and Linvala', *own], bob=[(1, n) for n in enemy] + [(10, 'Island')])


def pick(s, ids):
    d = s.state.rules.decision
    assert d
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


@pytest.mark.parametrize('name', ['Cankerbloom', 'Kargan Intimidator', 'Breya, Etherium Shaper', 'Oona, Queen of the Fae', 'Sliversmith', 'Elite Arcanist', 'Sisters of Stone Death'])
def test_native_lenders_are_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_cankerbloom_modes_and_targets_are_announced_before_borrower_sacrifice(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Sol Ring'], enemy=['Cankerbloom'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    lender = put(s, 'Cankerbloom', 'battlefield', 'p2')
    ring = put(s, 'Sol Ring', 'battlefield')
    (ab,) = borrowed(s, drana, cards)
    assert abilities_of.modal_definition(ab, Plan(s.state, 'p1', cards, None).ch(s.state.cards[drana.id]))
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    assert s.state.rules.decision.resume['step'] == 'cast_modes'
    assert s.state.cards[drana.id].zone == 'p1:battlefield'
    pick(s, ['0:0'])
    assert s.state.rules.decision.resume['step'] == 'cast_slot_target'
    pick(s, [ring.id])
    assert s.state.cards[drana.id].zone == s.state.cards[ring.id].zone == 'p1:graveyard'
    assert s.state.cards[lender.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_separately_inherited_kargan_abilities_have_separate_mode_memory(cards):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import mana

    s = game(cards, enemy=['Kargan Intimidator', 'Kargan Intimidator'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    lenders = [c.id for c in s.state.cards.values() if c.name == 'Kargan Intimidator']
    act(s, 'p2', type='move', card_ids=lenders, to={'player': 'p2', 'zone': 'battlefield'})
    lines = borrowed(s, drana, cards)
    assert len(lines) == 2
    mana(s, C=3)
    for ab in lines:
        act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index, modes=[0])
        settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[drana.id]).pt == (5, 6)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=drana.id, ability=lines[0].index, modes=[0])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_breya_modal_additional_cost_and_damage_use_the_borrower(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Sol Ring', "Tormod's Crypt"], enemy=['Breya, Etherium Shaper'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    put(s, 'Breya, Etherium Shaper', 'battlefield', 'p2')
    artifacts = [put(s, n, 'battlefield').id for n in ['Sol Ring', "Tormod's Crypt"]]
    (ab,) = borrowed(s, drana, cards)
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index, modes=[0], targets=['p2'])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step'] == 'ability_cost'
        pick(s, artifacts)
    else:
        settle(s)
    assert s.state.players['p2'].life == 37
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in artifacts)
    assert s.state.cards[drana.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_self_contained_chosen_color_is_chosen_when_oona_ability_resolves(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, enemy=['Oona, Queen of the Fae', 'Lightning Bolt', 'Shock'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    put(s, 'Oona, Queen of the Fae', 'battlefield', 'p2')
    reds = [put(s, n, 'library', 'p2').id for n in ['Lightning Bolt', 'Shock']]
    act(s, 'p2', type='move', card_ids=reds, to={'player': 'p2', 'zone': 'library'}, position='top')
    (ab,) = borrowed(s, drana, cards)
    assert not abilities_of.manual(ab)
    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index, targets=['p2'], x_value=2)
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.label.lower() == 'red' for o in d.options)
    pick(s, [next(o.id for o in d.options if o.label.lower() == 'red')])
    assert all(s.state.cards[c].zone == 'p2:exile' for c in reds)
    assert len([c for c in s.state.cards.values() if c.name == 'Faerie Rogue' and c.zone == 'p1:battlefield']) == 2
    roundtrip(s)


def test_named_token_instruction_does_not_require_prior_lender_choice(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave34b_activated import next_turn

    s = game(cards, own=['Lightning Bolt'], enemy=['Sliversmith'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    put(s, 'Sliversmith', 'battlefield', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand')
    next_turn(s)
    (ab,) = borrowed(s, drana, cards)
    assert not abilities_of.manual(ab)
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    assert s.state.rules.decision.resume['step'] == 'ability_cost'
    pick(s, [bolt.id])
    assert s.state.cards[drana.id].tapped and s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert len([c for c in s.state.cards.values() if c.name == 'Metallic Sliver' and c.zone == 'p1:battlefield']) == 1
    roundtrip(s)


def test_elite_arcanist_does_not_inherit_the_donors_exiled_card_or_its_x(cards):
    from tests.test_rules_defined_activation_x import imprinted
    from tests.test_rules_wave34b_activated import next_turn

    s, arcanist, linked = imprinted(cards, 'Elite Arcanist', ['Lightning Bolt'], extra=['Drana and Linvala'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[arcanist.id], player='p2')
    next_turn(s)
    (ab,) = borrowed(s, drana, cards)
    assert not abilities_of.manual(ab)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[drana.id].tapped
    assert s.state.cards[linked[0]].zone == 'p1:exile'
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def sisters_game(cards, own=()):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave34b_activated import attack, block, next_turn, priority_to, stops

    s = game(cards, own=own, enemy=['Sisters of Stone Death', 'Ornithopter'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    sisters = put(s, 'Sisters of Stone Death', 'battlefield', 'p2')
    victim = put(s, 'Ornithopter', 'battlefield', 'p2')
    stops(s)
    next_turn(s)
    attack(s, drana)
    block(s, (victim, drana))
    priority_to(s, 'p1')
    exile = next(a for a in borrowed(s, drana, cards) if 'Exile target' in a.text)
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=exile.index, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:exile'
    return s, drana, sisters, victim


@pytest.mark.parametrize('depart', ['none', 'donor', 'borrower'])
def test_acquired_linked_pair_shares_only_its_fresh_link_and_pending_ability_survives_departure(cards, depart):
    from tests.test_rules_bandmate_references import mana

    s, drana, sisters, victim = sisters_game(cards)
    ret = next(a for a in borrowed(s, drana, cards) if 'Put a creature card' in a.text)
    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ret.index)
    if depart != 'none':
        gone = sisters if depart == 'donor' else drana
        act(s, gone.controller, type='move', card_ids=[gone.id], to={'player': gone.owner, 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert [o.id for o in d.options] == [victim.id]
        pick(s, [victim.id])
    assert s.state.cards[victim.id].zone == 'p1:battlefield', (ret, s.state.rules.exiled_with)
    assert s.state.cards[victim.id].owner == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('blink', ['donor', 'borrower'])
def test_reacquiring_the_pair_after_a_new_object_cannot_use_its_old_exiles(cards, blink):
    from tests.test_rules_bandmate_references import mana

    s, drana, sisters, victim = sisters_game(cards)
    prior = next(a for a in borrowed(s, drana, cards) if 'Put a creature card' in a.text)
    old_scope = abilities_of.link_scope(prior)
    gone = sisters if blink == 'donor' else drana
    act(s, gone.controller, type='move', card_ids=[gone.id], to={'player': gone.owner, 'zone': 'exile'})
    act(s, gone.owner, type='move', card_ids=[gone.id], to={'player': gone.owner, 'zone': 'battlefield'})
    ret = next(a for a in borrowed(s, s.state.cards[drana.id], cards) if 'Put a creature card' in a.text)
    assert abilities_of.link_scope(ret) != old_scope
    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ret.index)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[victim.id].zone == 'p2:exile'
    roundtrip(s)


def test_borrower_cannot_reuse_its_own_unrelated_native_imprint_record(cards):
    from tests.test_rules_defined_activation_x import imprinted
    from tests.test_rules_wave34b_activated import next_turn

    s, borrower, linked = imprinted(cards, 'Elite Arcanist', ['Lightning Bolt'], extra=['Drana and Linvala', 'Elite Arcanist'])
    # Copying changes copiable values without making a new object: the old native
    # imprint remains, but the independently acquired Elite Arcanist ability has no link to it.
    template = put(s, 'Drana and Linvala', 'exile')
    act(s, 'p1', type='set_copy_source', card_id=borrower.id, source_id=template.id)
    other = next(c for c in s.state.cards.values() if c.name == 'Elite Arcanist')
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_controller', card_ids=[other.id], player='p2')
    next_turn(s)
    (ab,) = borrowed(s, s.state.cards[borrower.id], cards)
    act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ab.index)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.cards[linked[0]].zone == 'p1:exile'
    assert not [c for c in s.state.cards.values() if c.copy_of and c.id != borrower.id]
    roundtrip(s)


def test_copied_pending_ability_keeps_its_link_after_the_source_leaves_and_original_is_countered(cards):
    from tests.test_rules_bandmate_references import mana

    s, drana, _, victim = sisters_game(cards, own=['Lithoform Engine', 'Stifle'])
    engine = put(s, 'Lithoform Engine', 'battlefield')
    stifle = put(s, 'Stifle', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    ret = next(a for a in borrowed(s, drana, cards) if 'Put a creature card' in a.text)
    mana(s, C=5, U=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ret.index)
    original = next(cid for cid, e in s.state.rules.stack.items() if e.source_card == drana.id)
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=0, targets=[original])
    for _ in range(12):
        if len([e for e in s.state.rules.stack.values() if e.source_card == drana.id]) == 2:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert len([e for e in s.state.rules.stack.values() if e.source_card == drana.id]) == 2
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[original])
    act(s, 'p1', type='move', card_ids=[drana.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    assert s.state.cards[drana.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 40
    roundtrip(s)


def test_recursive_borrowing_preserves_the_native_modal_frame(cards):
    from tests.test_rules_bandmate_references import mana

    s = game(cards, own=['Cankerbloom'], enemy=['Experiment Kraj'])
    drana = put(s, 'Drana and Linvala', 'battlefield')
    bloom = put(s, 'Cankerbloom', 'battlefield')
    kraj = put(s, 'Experiment Kraj', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[bloom.id], kind='+1/+1', delta=1)
    ab = next(a for a in borrowed(s, drana, cards) if '\n• ' in a.text)
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=drana.id, ability=ab.index, modes=[2])
    settle(s)
    assert s.state.cards[drana.id].zone == 'p1:graveyard'
    assert s.state.rules.decision.resume['step'] == 'proliferate'
    pick(s, [bloom.id])
    assert s.state.cards[bloom.id].counters == {'+1/+1': 2}
    assert s.state.cards[kraj.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_targeted_link_selector_reads_only_the_corresponding_acquired_group(cards):
    from app.rules import targets

    s, drana, _, victim = sisters_game(cards)
    ret = next(a for a in borrowed(s, drana, cards) if 'Put a creature card' in a.text)
    scope = abilities_of.link_scope(ret)
    plan = Plan(s.state, 'p1', cards, None)
    assert targets.legal_targets(plan, f'borrowed_exiled|{scope}|exiled_with', 'p1', source_card=drana.id) == [victim.id]
    assert targets.legal_targets(plan, 'borrowed_exiled|unrelated|exiled_with', 'p1', source_card=drana.id) == []
    assert targets.legal_targets(plan, 'exiled_with', 'p1', source_card=drana.id) == []
    roundtrip(s)
