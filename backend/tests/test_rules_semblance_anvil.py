"""CR 607.2a/601.2f: linked shared-card-type reductions apply once per source."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_defined_activation_x import imprinted
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/semblance_anvil_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='san', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, names, extra=(), doubled=False):
    if names:
        return imprinted(cards, 'Semblance Anvil', names, doubled=doubled, extra=extra)
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ['Semblance Anvil', *extra])
    source = put(s, 'Semblance Anvil', 'hand')
    hold(s)
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    decline = next(o.id for o in d.options if o.id in ('no', 'skip', 'decline'))
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[decline])
    settle(s)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    return s, s.state.cards[source.id], []


def cost(s, cards, spell, player='p1'):
    ch = Plan(s.state, player, cards, None).ch(s.state.cards[spell.id])
    return casting.spell_cost(s.state, s.state.cards[spell.id], ch, 0, cards, player=player).text()


def test_canonical_card_is_supported(cards):
    assert coverage.of_card_data(cards.resolve('Semblance Anvil')).level == 'FULL'


def test_actual_imprint_reduces_a_shared_type_even_when_creature_subtypes_differ(cards):
    from tests.test_rules_bandmate_references import mana

    s, source, linked = setup(cards, ['Llanowar Elves'], extra=['Grizzly Bears'])
    spell = put(s, 'Grizzly Bears', 'hand')
    assert cost(s, cards, spell) == '{G}'
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert s.state.cards[linked[0]].zone == 'p1:exile'
    assert s.state.cards[source.id].zone == 'p1:battlefield' and mana_pool(s, 'p1') == {}
    roundtrip(s)


def test_multiple_shared_card_types_reduce_only_once(cards):
    from tests.test_rules_bandmate_references import mana

    s, _, _ = setup(cards, ['Myr Sire'], extra=['Filigree Familiar'])
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{1}'
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert mana_pool(s, 'p1') == {} and s.state.players['p1'].life == 42
    roundtrip(s)


def test_multiple_linked_cards_do_not_multiply_one_anvils_reduction(cards):
    s, source, linked = setup(cards, ['Myr Sire', 'Ornithopter'], extra=['Filigree Familiar'], doubled=True)
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(source.id)]) == 2
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{1}'
    assert all(s.state.cards[c].zone == 'p1:exile' for c in linked)
    roundtrip(s)


def test_no_imprint_means_no_reduction(cards):
    s, _, _ = setup(cards, [], extra=['Filigree Familiar'])
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{3}'
    roundtrip(s)


def test_sharing_only_a_subtype_does_not_qualify_and_colored_cost_is_not_reduced(cards):
    s, _, _ = setup(cards, ['Desperate Ritual'], extra=['Lava Spike', 'Counterspell'])
    # Ritual is Instant — Arcane; Spike is Sorcery — Arcane. Arcane is not a card type.
    spike = put(s, 'Lava Spike', 'hand')
    counter = put(s, 'Counterspell', 'hand')
    assert cost(s, cards, spike) == '{R}'
    assert cost(s, cards, counter) == '{U}{U}'
    roundtrip(s)


@pytest.mark.parametrize('return_to_exile', [False, True])
def test_departing_exiled_card_stops_reduction_even_if_the_same_card_returns(cards, return_to_exile):
    s, _, linked = setup(cards, ['Myr Sire'], extra=['Filigree Familiar'])
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{1}'
    act(s, 'p1', type='move', card_ids=linked, to={'player': 'p1', 'zone': 'graveyard'})
    if return_to_exile:
        act(s, 'p1', type='move', card_ids=linked, to={'player': 'p1', 'zone': 'exile'})
    assert cost(s, cards, spell) == '{3}'
    roundtrip(s)


def test_new_anvil_object_does_not_reuse_the_old_imprint(cards):
    s, source, linked = setup(cards, ['Myr Sire'], extra=['Filigree Familiar'])
    spell = put(s, 'Filigree Familiar', 'hand')
    old = s.state.rules.object_id(source.id)
    assert cost(s, cards, spell) == '{1}'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    assert cost(s, cards, spell) == '{3}' and s.state.cards[linked[0]].zone == 'p1:exile'
    roundtrip(s)


def test_linked_card_current_types_are_reread_when_static_type_effects_change(cards):
    s, _, _ = setup(cards, ['Grizzly Bears'], extra=['Ichor Wellspring', 'Encroaching Mycosynth'])
    spell = put(s, 'Ichor Wellspring', 'hand')
    assert cost(s, cards, spell) == '{2}'
    mycosynth = put(s, 'Encroaching Mycosynth', 'battlefield')
    assert cost(s, cards, spell) == '{0}'
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[mycosynth.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert cost(s, cards, spell) == '{2}'
    roundtrip(s)


def test_imprinted_split_card_supplies_both_card_types_in_exile(cards):
    s, _, _ = setup(cards, ['Discovery // Dispersal'], extra=['Divination', 'Counterspell'])
    sorcery = put(s, 'Divination', 'hand')
    instant = put(s, 'Counterspell', 'hand')
    assert cost(s, cards, sorcery) == '{U}'
    assert cost(s, cards, instant) == '{U}{U}'
    roundtrip(s)


def test_reduction_follows_anvil_controller_not_owner_of_the_exiled_card(cards):
    s, source, linked = setup(cards, ['Myr Sire'], extra=['Filigree Familiar'])
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{1}'
    assert cost(s, cards, spell, 'p2') == '{3}'
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert s.state.cards[linked[0]].owner == 'p1'
    assert cost(s, cards, spell) == '{3}'
    assert cost(s, cards, spell, 'p2') == '{1}'
    roundtrip(s)


def test_two_independent_anvils_stack_their_reductions(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import pick

    s, first, _ = setup(cards, ['Myr Sire'], extra=['Semblance Anvil', 'Ornithopter', 'Filigree Familiar'])
    second = next(c for c in s.state.cards.values() if c.name == 'Semblance Anvil' and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'hand'})
    imprint = put(s, 'Ornithopter', 'hand')
    assert cost(s, cards, second) == '{1}'
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=second.id)
    for _ in range(8):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        pick(s, ['pay'] if 'pay' in ids else ['yes'] if 'yes' in ids else [imprint.id])
    assert s.state.cards[imprint.id].zone == 'p1:exile'
    spell = put(s, 'Filigree Familiar', 'hand')
    assert cost(s, cards, spell) == '{0}'
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield' and mana_pool(s, 'p1') == {}
    roundtrip(s)
