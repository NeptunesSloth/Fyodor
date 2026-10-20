"""CR 601.2b/f/h: Trinisphere after announcements/reductions and before payment."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / 'fixtures/spell_mana_floor_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='tmf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name='Lightning Bolt', *, tapped=False, sphere=True):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [c['name'] for c in DATA], ['Counterspell', 'Grizzly Bears'])
    stone = put(s, 'Trinisphere', 'battlefield') if sphere else None
    if tapped:
        act(s, 'p1', type='tap', card_ids=[stone.id], tapped=True)
    spell = put(s, name, 'hand')
    return s, spell, stone


def cast(s, spell, *, targets=(), symbols=None, free=False, **pool):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=list(targets), free=free,
        **({'mana_symbols': symbols} if symbols is not None else {}))


def finish(s):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    settle(s)
    roundtrip(s)


def test_real_oracle_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve('Trinisphere')).level == 'FULL'


@pytest.mark.parametrize('tapped,generic', [(False, 2), (True, 0)])
def test_untapped_floor_preserves_colored_cost(cards, tapped, generic):
    s, spell, _ = setup(cards, tapped=tapped)
    cast(s, spell, targets=['p3'], C=generic, R=1)
    finish(s)
    assert s.state.players['p3'].life == 37
    assert not any(s.state.players['p1'].mana.values())


def test_zero_cost_spell_costs_three(cards):
    s, spell, _ = setup(cards, 'Ornithopter')
    cast(s, spell, C=3)
    finish(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())


def test_floor_hints_reject_insufficient_generic(cards):
    from app.rules.casting import castable
    from tests.test_rules_bandmate_references import mana

    s, spell, _ = setup(cards)
    mana(s, R=1)
    assert not castable(s.state, 'p1', spell, s.cards)
    mana(s, C=2, R=1)
    assert castable(s.state, 'p1', spell, s.cards)


@pytest.mark.parametrize('symbols,pool,life', [(['U'], {'C': 2, 'U': 1}, 40), (['life'], {'C': 3}, 38)])
def test_phyrexian_choices_precede_floor(cards, symbols, pool, life):
    s, spell, _ = setup(cards, 'Gitaxian Probe')
    cast(s, spell, targets=['p2'], symbols=symbols, **pool)
    finish(s)
    assert s.state.players['p1'].life == life
    assert not any(s.state.players['p1'].mana.values())


@pytest.mark.parametrize('symbols,pool,life', [(['B', 'B'], {'C': 1, 'B': 2}, 40),
                                             (['life', 'B'], {'C': 2, 'B': 1}, 38),
                                             (['life', 'life'], {'C': 3}, 36)])
def test_dismember_counts_only_announced_mana(cards, symbols, pool, life):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Dismember')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, spell, targets=[victim.id], symbols=symbols, **pool)
    finish(s)
    assert s.state.players['p1'].life == life
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    assert not any(s.state.players['p1'].mana.values())


def test_phyrexian_prompt_saved_and_cancellable(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, 'Gitaxian Probe')
    cast(s, spell, targets=['p2'], C=3, U=1)
    d = s.state.rules.decision
    assert d.resume['step'] == 'spell_symbols'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 40
    assert sum(s.state.players['p1'].mana.values()) == 4
    roundtrip(s)


def test_hybrid_generic_choice_announced_before_reduction(cards):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Beseech the Queen')
    put(s, 'Jet Medallion', 'battlefield')
    cast(s, spell, symbols=['2', '2', '2'], C=5)
    finish(s)
    assert not any(s.state.players['p1'].mana.values())


def test_omniscience_still_pays_floor(cards):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Grizzly Bears')
    put(s, 'Omniscience', 'battlefield')
    cast(s, spell, free=True, C=3)
    finish(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())


def test_flashback_reduction_precedes_floor_and_life_cost_remains(cards):
    from tests.test_rules_designations import put

    s, _, _ = setup(cards, 'Grizzly Bears')
    put(s, 'Catalyst Stone', 'battlefield')
    spell = put(s, 'Deep Analysis', 'graveyard')
    cast(s, spell, targets=['p1'], C=2, U=1)
    finish(s)
    assert s.state.players['p1'].life == 37
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert not any(s.state.players['p1'].mana.values())


def test_delve_pays_cost_after_floor_without_reflooring(cards):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Treasure Cruise')
    for name in ('Forest', 'Island', 'Ornithopter', 'Grizzly Bears', 'Sol Ring', 'Lightning Bolt', 'Naturalize'):
        put(s, name, 'graveyard')
    cast(s, spell, U=1)
    finish(s)
    assert not any(s.state.players['p1'].mana.values())
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:exile']) == 7


def test_convoke_pays_added_generic_after_floor(cards):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Ornithopter')
    engineer = put(s, 'Chief Engineer', 'battlefield')
    bears = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    cast(s, spell)
    finish(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert all(s.state.cards[c.id].tapped for c in (engineer, bears, elf))


def test_krrik_life_substitution_is_after_floor(cards):
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Jet Medallion')
    put(s, "K'rrik, Son of Yawgmoth", 'battlefield')
    # Beseech chooses BBB: those three mana count even if K'rrik pays six life instead.
    spell = put(s, 'Beseech the Queen', 'hand')
    cast(s, spell, symbols=['B', 'B', 'B'])
    finish(s)
    assert s.state.players['p1'].life == 34
    assert not any(s.state.players['p1'].mana.values())


def test_resolving_free_cast_pays_its_own_floor(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, spell, _ = setup(cards, 'Ornithopter')
    electro = put(s, 'Electrodominance', 'hand')
    mana(s, C=4, R=2)
    act(s, 'p1', type='cast_spell', card_id=electro.id, x_value=0, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert spell.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[spell.id])
    finish(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_improvise_pays_generic_added_by_floor(cards):
    from tests.test_rules_designations import put

    s, spell, stone = setup(cards)
    statuary = put(s, 'Inspiring Statuary', 'battlefield')
    cast(s, spell, targets=['p3'], R=1)
    finish(s)
    assert s.state.cards[statuary.id].tapped and s.state.cards[stone.id].tapped
    assert s.state.players['p3'].life == 37
    assert not any(s.state.players['p1'].mana.values())


def test_activated_ability_is_not_floored(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _ = setup(cards)
    collar = put(s, 'Basilisk Collar', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=collar.id, ability=ability_index(s, collar, 'Equip {2}'), targets=[bear.id])
    finish(s)
    assert s.state.cards[collar.id].attached_to == bear.id
    assert not any(s.state.players['p1'].mana.values())


def test_mana_ability_is_not_floored(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s, _, _ = setup(cards)
    ring = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=ring.id, ability=0)
    from tests.game_helpers import mana_pool

    assert mana_pool(s, 'p1') == {'C': 2}
    finish(s)


def test_spend_permission_does_not_erase_colored_only_reduction(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, "Elspeth, Sun's Champion")
    defiler = put(s, 'Defiler of Faith', 'battlefield')
    put(s, 'Oath of Nissa', 'battlefield')
    mana(s, C=5)
    act(s, 'p1', type='cast_spell', card_id=spell.id, optional_costs=[defiler.id])
    finish(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == 38
    assert not any(s.state.players['p1'].mana.values())


def test_offering_reduces_before_floor(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, 'Patron of the Moon')
    savant = put(s, 'Soratami Savant', 'battlefield')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, optional_costs=[f'{spell.id}:offering'])
    finish(s)
    assert s.state.cards[savant.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())


def test_assist_pays_the_floor_before_casters_share_is_locked(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s, spell, _ = setup(cards, 'Huddle Up')
    mana(s, U=1)
    mana(s, pid='p2', C=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1', 'p2'], target_counts=[2], assist='p2', assist_amount=2)
    finish(s)
    assert not any(s.state.players['p1'].mana.values())
    assert not any(s.state.players['p2'].mana.values())


def test_mana_floor_remains_locked_when_ironworks_sacrifices_trinisphere(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, spell, stone = setup(cards, 'Ornithopter')
    ironworks = put(s, 'Krark-Clan Ironworks', 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self')
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    d = s.state.rules.decision
    assert d.display['cost'] == '{3}'
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=ironworks.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [stone.id]}])
    finish(s)
    assert s.state.cards[stone.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert not any(s.state.players['p1'].mana.values())


def test_answering_saved_symbol_prompt_pays_chosen_life_and_floor(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, 'Gitaxian Probe')
    cast(s, spell, targets=['p2'], C=3)
    d = s.state.rules.decision
    roundtrip(s)
    choice = d.resume['options'].index(['life'])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[str(choice)])
    finish(s)
    assert s.state.players['p1'].life == 38
    assert not any(s.state.players['p1'].mana.values())


@pytest.mark.parametrize('name,life,legal', [('Gitaxian Probe', 1, False), ('Gitaxian Probe', 2, True),
                                          ('Dismember', 3, False), ('Dismember', 4, True)])
def test_life_announcements_hint_requires_whole_payment_and_allows_exact_life(cards, name, life, legal):
    from app.rules.casting import castable
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, name)
    act(s, 'p1', type='set_life', player='p1', value=life)
    mana(s, C=3)
    assert castable(s.state, 'p1', spell, s.cards) is legal
    roundtrip(s)


def test_unpayable_explicit_life_announcement_spends_nothing(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, 'Gitaxian Probe')
    act(s, 'p1', type='set_life', player='p1', value=1)
    with pytest.raises(ActionError, match='life payment cannot be paid'):
        cast(s, spell, targets=['p2'], symbols=['life'], C=3)
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 1
    assert s.state.players['p1'].mana == {'C': 3}
    roundtrip(s)
