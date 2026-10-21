"""CR 707.12, 608.2g: copies are cast individually, with the printed payment."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = Path(__file__).parent / 'fixtures/card_copy_casting_family_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ccf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, names=()):
    from tests.test_rules_shared_damage_choices import table

    extras = [c['name'] for c in json.loads(DATA.read_text())]
    s = table(cards, [*extras, *names], [], [])
    from tests.game_helpers import act

    originals = []
    used = set()
    for name in names:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == 'p1' and c.id not in used)
        used.add(c.id)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'graveyard'})
        originals.append(s.state.cards[c.id])
    return s, originals


def answer(s, ids):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    d = s.state.rules.decision
    assert d
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def chapter(cards, names=()):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, settle

    s, originals = setup(cards, names)
    saga = put(s, 'The Tale of Tamiyo', 'battlefield')
    spell = put(s, 'Contentious Plan', 'hand')
    library = list(s.state.zones['p1:library'])
    forest = next(c for c in library if s.state.cards[c].name == 'Forest')
    act(s, 'p1', type='move', card_ids=[c for c in library if c != forest], to={'player': 'p1', 'zone': 'exile'})
    # Manual setup establishes three lore counters; an actual proliferate effect
    # adds the fourth and triggers the real chapter, without fabricating a stack ability.
    act(s, 'p1', type='counter', card_ids=[saga.id], kind='lore', delta=3)
    from tests.test_rules_bandmate_references import mana

    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'proliferate'
    answer(s, [saga.id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'trigger_group'
    return s, saga, originals


@pytest.mark.parametrize('name', ['The Tale of Tamiyo', 'Arcane Bombardment', 'Isochron Scepter'])
def test_family_is_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_tamiyo_can_select_zero_targets_and_finishes_without_copies(cards):
    from tests.test_rules_designations import roundtrip

    s, saga, _ = chapter(cards, ['Lightning Bolt'])
    answer(s, [])
    assert s.state.cards[saga.id].zone == 'p1:graveyard'
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_tamiyo_target_union_excludes_other_planeswalkers_and_nonspells(cards):
    s, _, originals = chapter(cards, ['Lightning Bolt', 'Tamiyo, the Moon Sage', 'Jace Beleren', 'Sol Ring', 'Llanowar Elves'])
    opts = {o.id for o in s.state.rules.decision.options}
    assert {c.id for c in originals[:2]} <= opts
    assert not {c.id for c in originals[2:]} & opts
    answer(s, [originals[0].id, originals[1].id])
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in originals[:2])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    answer(s, [])
    assert not [c for c in s.state.cards.values() if c.copy_of]


def test_tamiyo_copies_are_cast_with_mana_paid_and_trigger_cast_abilities(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, _, originals = chapter(cards, ['Lightning Bolt'])
    put(s, 'Guttersnipe', 'battlefield')
    mana(s, R=1)
    answer(s, [originals[0].id])
    d = s.state.rules.decision
    copy_id = d.options[0].id
    answer(s, [copy_id])
    assert s.state.rules.decision and 'p2' in {o.id for o in s.state.rules.decision.options}
    answer(s, ['p2'])
    assert s.state.players['p1'].mana.get('R', 0) == 0
    assert s.state.players['p2'].life == 35 and s.state.players['p3'].life == 38
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    assert copy_id not in s.state.cards
    roundtrip(s)


def test_tamiyo_planeswalker_copy_becomes_a_token_with_initial_loyalty(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, _, originals = chapter(cards, ['Tamiyo, the Moon Sage'])
    mana(s, C=3, U=2)
    answer(s, [originals[0].id])
    copy_id = s.state.rules.decision.options[0].id
    answer(s, [copy_id])
    token = s.state.cards[copy_id]
    assert token.zone == 'p1:battlefield' and token.is_token and token.copy_of
    assert token.counters.get('loyalty') == 4
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    roundtrip(s)


def bombardment(cards, names=('Lightning Bolt',), *, before_resolve=None):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle

    s, originals = setup(cards, names)
    source = put(s, 'Arcane Bombardment', 'battlefield')
    excluded = {c.id for c in originals}
    spell = next(c for c in s.state.cards.values() if c.name == 'Shock' and c.owner == 'p1' and c.id not in excluded)
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    if before_resolve:
        before_resolve(s, source, originals)
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step'] == 'free_cast_pick'
    return s, source, originals, spell


@pytest.mark.parametrize('cast', [False, True])
def test_bombardment_random_exile_links_and_optional_casts_are_real_spells(cards, cast):
    from tests.test_rules_designations import roundtrip

    s, source, originals, _ = bombardment(cards)
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    assert any(originals[0].id in oid for oids in s.state.rules.exiled_with.values() for oid in oids)
    copy_id = s.state.rules.decision.options[0].id
    answer(s, [copy_id] if cast else [])
    if cast:
        answer(s, ['p2'])
    assert s.state.players['p2'].life == (37 if cast else 40)
    assert s.state.players['p3'].life == 38
    assert copy_id not in s.state.cards
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def recast_shock_next_turn(s, spell, turn):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=turn)
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)


def test_bombardment_accumulates_links_across_turns_and_triggers_only_for_first_spell(cards):
    s, _, originals, spell = bombardment(cards, ['Lightning Bolt', 'Counterspell'])
    answer(s, [])
    recast_shock_next_turn(s, spell, 1)
    assert s.state.rules.decision is None  # second spell this turn does not trigger
    recast_shock_next_turn(s, spell, 4)
    assert len(s.state.rules.decision.options) == 2
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in originals)
    answer(s, [])
    recast_shock_next_turn(s, spell, 7)  # empty graveyard still copies both linked cards
    assert len(s.state.rules.decision.options) == 2
    answer(s, [])


def test_tamiyo_paid_x_announces_above_forty_and_charges_the_announced_cost(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, _, originals = chapter(cards, ['Blaze'])
    mana(s, C=41, R=1)
    answer(s, [originals[0].id])
    copy_id = s.state.rules.decision.options[0].id
    answer(s, [copy_id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'free_x'
    assert 'x:41' in {o.id for o in d.options}
    answer(s, ['x:41'])
    d = s.state.rules.decision
    assert d and 'p2' in {o.id for o in d.options}
    answer(s, ['p2'])
    assert s.state.players['p2'].life == -1
    assert sum(s.state.players['p1'].mana.values()) == 0
    assert copy_id not in s.state.cards
    roundtrip(s)


def test_paid_no_mana_cost_copy_is_not_offered_for_casting(cards):
    s, _, originals = chapter(cards, ['Living End'])
    answer(s, [originals[0].id])
    assert s.state.rules.decision is None
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    assert not [c for c in s.state.cards.values() if c.copy_of]


def test_mdfc_card_copy_offers_spell_face_but_no_land_face(cards):
    s, _, _, _ = bombardment(cards, ['Jwari Disruption // Jwari Ruins'])
    d = s.state.rules.decision
    assert len(d.options) == 1 and d.options[0].id.endswith('@0')
    assert 'Jwari Disruption' in d.options[0].label
    answer(s, [])


def test_split_card_copy_can_cast_its_other_half_without_paying(cards):
    from tests.test_rules_designations import put, roundtrip

    s, _, _, _ = bombardment(cards, ['Fire // Ice'])
    permanent = put(s, 'Sol Ring', 'battlefield')
    d = s.state.rules.decision
    assert len(d.options) == 2
    ice = next(o.id for o in d.options if o.label == 'Ice')
    answer(s, [ice])
    answer(s, [permanent.id])
    assert s.state.cards[permanent.id].tapped
    assert s.state.players['p3'].life == 38
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_copy_creation_checkpoints_and_more_than_99_cast_choices_remain_available(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, _, originals = chapter(cards, ['Strike It Rich'] * 101)
    mana(s, R=100)
    mana(s, R=1)
    answer(s, [c.id for c in originals])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'card_copy_continue'
    assert len([c for c in s.state.cards.values() if c.copy_of]) == 64
    answer(s, ['continue'])
    assert len(s.state.rules.decision.options) == 101
    for _ in range(100):
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'free_cast_pick'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'free_cast_pick' and len(d.options) == 1
    assert s.state.players['p1'].mana.get('R') == 1
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    for _ in range(12):
        settle(s)
        if not s.state.zones.get('stack'):
            break
    assert not s.state.zones.get('stack')
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure']) == 100
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_canceling_one_paid_cast_returns_to_the_remaining_copy_choices(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, _, originals = chapter(cards, ['Lightning Bolt', 'Strike It Rich'])
    act(s, 'p1', type='set_prefs', payment='self')
    answer(s, [c.id for c in originals])
    copy_id = next(o.id for o in s.state.rules.decision.options if o.label == 'Strike It Rich')
    answer(s, [copy_id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pay_mana'
    assert 'cancel' in {o.id for o in d.options}
    answer(s, ['cancel'])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert len(s.state.rules.decision.options) == 2
    answer(s, [])
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_mdfc_copy_is_actually_cast_and_counters_the_original_spell(cards):
    from tests.test_rules_designations import roundtrip

    s, _, _, spell = bombardment(cards, ['Jwari Disruption // Jwari Ruins'])
    copy_id = s.state.rules.decision.options[0].id
    answer(s, [copy_id])
    answer(s, [spell.id])
    d = s.state.rules.decision
    if d is not None:
        assert d.kind == 'confirm' and 'no' in {o.id for o in d.options}
        answer(s, ['no'])
    assert s.state.players['p3'].life == 40
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_bombardment_blink_retains_old_trigger_links_but_new_object_does_not_inherit_them(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    seen = {}

    def blink(s, source, originals):
        seen['old'] = s.state.rules.object_id(source.id)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
        seen['new'] = s.state.rules.object_id(source.id)

    s, _, originals, spell = bombardment(cards, before_resolve=blink)
    assert seen['old'] != seen['new']
    assert len(s.state.rules.exiled_with[seen['old']]) == 1
    assert not s.state.rules.exiled_with.get(seen['new'])
    answer(s, [])
    recast_shock_next_turn(s, spell, 4)
    assert s.state.rules.decision is None
    assert not s.state.rules.exiled_with.get(seen['new'])
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('remove_all', [False, True])
def test_tamiyo_only_copies_targets_still_legal_when_the_chapter_resolves(cards, remove_all):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, originals = chapter(cards, ['Lightning Bolt', 'Strike It Rich'])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in originals])
    removed = originals if remove_all else originals[:1]
    act(s, 'p1', type='move', card_ids=[c.id for c in removed], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:hand' for c in removed)
    if remove_all:
        assert s.state.rules.decision is None
    else:
        assert [o.label for o in s.state.rules.decision.options] == ['Strike It Rich']
        answer(s, [])
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_aftermath_copy_in_exile_does_not_offer_its_graveyard_only_half(cards):
    s, _, _, _ = bombardment(cards, ['Commit // Memory'])
    assert len(s.state.rules.decision.options) == 1
    option = s.state.rules.decision.options[0]
    assert option.label == 'Commit' and option.id.endswith('@0')
    answer(s, [])


def test_fuse_copy_in_exile_offers_individual_halves_only(cards):
    from tests.test_rules_designations import put

    s, _, _, _ = bombardment(cards, ['Wear // Tear'])
    put(s, 'Sol Ring', 'battlefield')
    # The enchantment source is a legal Tear target; Sol Ring makes Wear legal.
    # Fuse is restricted to casting from hand, never a third option from exile.
    d = s.state.rules.decision
    assert {o.label for o in d.options} == {'Tear'}  # Wear wasn't legal when this choice was formed
    answer(s, [])


def test_cost_increases_apply_even_when_the_card_copy_is_cast_for_free(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, _, _, _ = bombardment(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield')
    mana(s, C=1)
    answer(s, [s.state.rules.decision.options[0].id])
    answer(s, ['p2'])
    assert sum(s.state.players['p1'].mana.values()) == 0
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_changing_bombardment_controller_does_not_change_the_existing_trigger_controller(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    def steal(s, source, originals):
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')

    s, source, _, _ = bombardment(cards, before_resolve=steal)
    assert s.state.cards[source.id].controller == 'p2'
    assert s.state.rules.decision.player == 'p1'
    copy_id = s.state.rules.decision.options[0].id
    assert s.state.cards[copy_id].owner == 'p1'
    answer(s, [copy_id])
    answer(s, ['p2'])
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_state_based_cleanup_deletes_more_than_one_action_capacity_of_uncast_copies(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, originals = setup(cards, ['Lightning Bolt'])
    for _ in range(6):
        act(s, 'p1', type='copy_card', card_id=originals[0].id, player='p1', zone='exile', count=50)
    assert len([c for c in s.state.cards.values() if c.copy_of]) == 300
    act(s, s.state.rules.priority, type='pass_priority')
    assert not [c for c in s.state.cards.values() if c.copy_of]
    assert s.state.cards[originals[0].id].zone == 'p1:graveyard'
    roundtrip(s)


def force_copy(cards, *, blue=True):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put

    s, _, originals = chapter(cards, ['Force of Will', 'Strike It Rich'])
    pitched = put(s, 'Opt', 'hand') if blue else None
    mana(s, R=1)
    answer(s, [c.id for c in originals])
    d = s.state.rules.decision
    # Cast the sorcery first; it becomes a legal target for the subsequent Force.
    answer(s, [next(o.id for o in d.options if o.label == 'Strike It Rich')])
    d = s.state.rules.decision
    force = next(o.id for o in d.options if o.label == 'Force of Will')
    return s, force, pitched


def test_paid_copy_can_choose_force_of_will_alternative_and_pays_life_plus_exile(cards):
    from tests.test_rules_designations import roundtrip

    s, force, pitched = force_copy(cards)
    answer(s, [force])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'paid_effect_cost'
    alt = next(o.id for o in d.options if 'Exile' in o.label or 'exile' in o.label)
    answer(s, [alt])
    d = s.state.rules.decision
    target = next(o.id for o in d.options if 'Strike It Rich' in o.label)
    answer(s, [target])
    d = s.state.rules.decision
    if d is not None:
        assert pitched.id in {o.id for o in d.options}
        answer(s, [pitched.id])
    assert s.state.players['p1'].life == 39
    assert s.state.cards[pitched.id].zone == 'p1:exile'
    assert not [c for c in s.state.cards.values() if c.name == 'Treasure']
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_canceling_alternative_cost_selection_returns_to_copy_selection(cards):
    s, force, _ = force_copy(cards)
    answer(s, [force])
    assert s.state.rules.decision.resume['step'] == 'paid_effect_cost'
    answer(s, ['cancel'])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert any(o.label == 'Force of Will' for o in s.state.rules.decision.options)
    answer(s, [])
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure']) == 1


def test_alternative_requiring_a_missing_blue_card_is_not_offered(cards):
    from tests.test_rules_bandmate_references import mana

    s, force, _ = force_copy(cards, blue=False)
    mana(s, C=3, U=2)
    answer(s, [force])
    d = s.state.rules.decision
    assert d and d.resume['step'] != 'paid_effect_cost'
    answer(s, [next(o.id for o in d.options if 'Strike It Rich' in o.label)])
    assert s.state.players['p1'].life == 40
    assert sum(s.state.players['p1'].mana.values()) == 0


def test_waived_cost_copy_does_not_offer_a_second_alternative_cost(cards):
    from tests.test_rules_designations import put

    s, _, _, spell = bombardment(cards, ['Force of Will'])
    pitched = put(s, 'Opt', 'hand')
    answer(s, [s.state.rules.decision.options[0].id])
    assert s.state.rules.decision.resume['step'] != 'paid_effect_cost'
    answer(s, [spell.id])
    assert s.state.players['p1'].life == 40
    assert s.state.cards[pitched.id].zone == 'p1:hand'
    assert s.state.players['p3'].life == 40


def test_missing_mana_cost_copy_can_use_a_legal_table_alternative(cards):
    from tests.test_rules_designations import put, roundtrip

    s, _, originals = chapter(cards, ['Ancestral Vision'])
    put(s, 'As Foretold', 'battlefield')
    hand = len(s.state.zones.get('p2:hand', []))
    answer(s, [originals[0].id])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    answer(s, [s.state.rules.decision.options[0].id])
    d = s.state.rules.decision
    assert d.resume['step'] == 'paid_effect_cost'
    assert 'normal' not in {o.id for o in d.options}
    answer(s, [next(o.id for o in d.options if o.id != 'cancel')])
    answer(s, ['p2'])
    assert len(s.state.zones.get('p2:hand', [])) == hand + 3
    assert s.state.rules.once_per_turn
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_paid_copy_pays_mandatory_additional_cost_and_reductions_apply_before_sacrifice(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, _, originals = chapter(cards, ['Fling'])
    creature = put(s, 'Goblin Electromancer', 'battlefield')
    mana(s, R=1, C=1)
    answer(s, [originals[0].id])
    answer(s, [s.state.rules.decision.options[0].id])
    answer(s, ['p2'])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step'] == 'ability_cost'
        answer(s, [creature.id])
    assert s.state.cards[creature.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].mana.get('C') == 1  # Electromancer reduced the announced cost
    assert not [c for c in s.state.cards.values() if c.copy_of]
    roundtrip(s)


def test_paid_graveyard_permission_uses_normal_cost_not_printed_flashback(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, originals = setup(cards, ['Strike It Rich'])
    chandra = put(s, 'Chandra, Acolyte of Flame', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=chandra.id, kind='loyalty', value=3)
    mana(s, R=1)
    act(s, 'p1', type='activate_ability', card_id=chandra.id, ability=2, targets=[originals[0].id])
    settle(s)
    answer(s, [originals[0].id])
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure']) == 1
    assert s.state.players['p1'].mana.get('R', 0) == 0
    assert s.state.cards[originals[0].id].zone == 'p1:exile'
    roundtrip(s)


def test_canceling_nonmana_alternative_payment_spends_nothing_and_keeps_remaining_choices(cards):
    from tests.test_rules_designations import put, roundtrip

    s, force, pitched = force_copy(cards)
    other = put(s, 'Counterspell', 'hand')
    answer(s, [force])
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if 'exile' in o.label.lower())])
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if 'Strike It Rich' in o.label)])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'ability_cost'
    answer(s, [])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    assert s.state.players['p1'].life == 40
    assert s.state.cards[pitched.id].zone == s.state.cards[other.id].zone == 'p1:hand'
    answer(s, [])
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure']) == 1
    roundtrip(s)


def test_paid_copy_can_activate_a_land_mana_ability_during_payment(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, originals = chapter(cards, ['Strike It Rich', 'Mountain'])
    mountain = originals[1]
    act(s, 'p1', type='move', card_ids=[mountain.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_prefs', payment='self')
    answer(s, [originals[0].id])
    copy_id = s.state.rules.decision.options[0].id
    answer(s, [copy_id])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=0)
    settle(s)
    d = s.state.rules.decision
    if d and d.resume['step'] == 'pay_mana':
        answer(s, ['pay'])
    assert s.state.cards[mountain.id].tapped
    assert copy_id not in s.state.cards
    assert len([c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']) == 1
    assert s.state.rules.decision is None
    roundtrip(s)
