"""Reanimation wordings (wave 10A), the activated and X forms: one target group per kind in an activated ability
(115.1, 601.2c), an activation restriction, and "mana value X" taken from the {X} of the activation (107.3f, 602.2b).
Real Oracle text; the cards and the table come from test_rules_wave10a_reanimation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave10a_reanimation import REAL, build, put, settle, zone


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize(("name", "cost", "kind", "text"), [
    # an X that is not announced with the spell or ability: the target can't be judged against it (107.3f)
    ("Chthonian Nightmare", "{1}{B}", "Enchantment",
     "When this enchantment enters, you get {E}{E}{E} (three energy counters).\nPay X {E}, Sacrifice a creature, Return this "
     "enchantment to its owner's hand: Return target creature card with mana value X from your graveyard to the battlefield. "
     "Activate only as a sorcery."),
    ("Relentless Dead", "{B}{B}", "Creature — Zombie",
     "Menace\nWhen this creature dies, you may pay {B}. If you do, return it to its owner's hand.\nWhen this creature dies, you "
     "may pay {X}. If you do, return another target Zombie creature card with mana value X from your graveyard to the battlefield."),
    # "mana value X" exactly is read for graveyard cards only
    ("Disembowel", "{X}{B}", "Instant", "Destroy target creature with mana value X."),
    # a comparison with the source is read for graveyard cards only
])
def test_wordings_that_are_not_read_stay_manual(name, cost, kind, text):
    data = card(name, set_code="tst", number="N1", mana_cost=cost, type_line=kind, oracle_text=text,
                power="2" if "Creature" in kind else None, toughness="2" if "Creature" in kind else None)
    assert coverage.of_characteristics(printed_from_data(data, 0)).level != "FULL"


def test_crop_sigil_needs_four_card_types_in_the_graveyard_then_returns_a_creature_and_a_land(cards):
    s = build(cards)
    sigil = put(s, "Crop Sigil", "battlefield")
    elves = put(s, "Llanowar Elves", "graveyard")
    forest = put(s, "Forest", "graveyard")
    put(s, "Lightning Bolt", "graveyard")
    mana(s, G=1, C=2)
    with pytest.raises(ActionError):  # creature, land, instant: three types
        act(s, "p1", type="activate_ability", card_id=sigil.id, ability=1, targets=[elves.id, forest.id], target_counts=[1, 1])
    put(s, "Postmortem Lunge", "graveyard")  # a sorcery: four types
    act(s, "p1", type="activate_ability", card_id=sigil.id, ability=1, targets=[elves.id, forest.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert zone(s, elves) == "p1:hand" and zone(s, forest) == "p1:hand" and zone(s, sigil) == "p1:graveyard"
    settle(s)


def test_retrieve_takes_a_creature_and_a_noncreature_permanent_and_exiles_itself(cards):
    s = build(cards)
    elves = put(s, "Llanowar Elves", "graveyard")
    sigil = put(s, "Crop Sigil", "graveyard")
    bolt = put(s, "Lightning Bolt", "graveyard")  # not a permanent card
    mana(s, G=1, C=2)
    c = put(s, "Retrieve", "hand")
    with pytest.raises(ActionError):  # an instant is not a noncreature permanent card
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[elves.id, bolt.id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[elves.id, sigil.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert zone(s, elves) == "p1:hand" and zone(s, sigil) == "p1:hand" and zone(s, bolt) == "p1:graveyard"
    assert zone(s, c) == "p1:exile"
    settle(s)


def test_restoration_specialist_sacrifices_itself_to_return_an_artifact_and_an_enchantment(cards):
    s = build(cards)
    sigil = put(s, "Crop Sigil", "graveyard")
    sol = put(s, "Sol Ring", "graveyard")
    spec = put(s, "Restoration Specialist", "battlefield")
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=spec.id, ability=0, targets=[sol.id, sigil.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert zone(s, sol) == "p1:hand" and zone(s, sigil) == "p1:hand" and zone(s, spec) == "p1:graveyard"
    settle(s)


def test_shreds_of_sanity_returns_both_then_discards_and_exiles_itself(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    lunge = put(s, "Postmortem Lunge", "graveyard")
    mana(s, R=1, C=2)
    c = put(s, "Shreds of Sanity", "hand")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bolt.id, lunge.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None  # "then discard a card": chosen from the hand, which now holds both
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bolt.id])
    pass_until_stack_empty(s)
    assert zone(s, bolt) == "p1:graveyard" and zone(s, lunge) == "p1:hand" and zone(s, c) == "p1:exile"
    settle(s)


def test_druidic_ritual_mills_by_choice_then_returns_up_to_one_creature_and_one_land(cards):
    s = build(cards)
    elves = put(s, "Llanowar Elves", "graveyard")
    forest = put(s, "Forest", "graveyard")
    mana(s, G=1, C=2)
    c = put(s, "Druidic Ritual", "hand")
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(10):
        pass_until_stack_empty(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        want = [x for x in (elves.id, forest.id) if x in ids]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=want or ([i for i in ids if i == "yes"] or ids[:1]))
    assert zone(s, elves) == "p1:hand" and zone(s, forest) == "p1:hand"
    settle(s)


def test_sequence_engine_exiles_a_creature_card_with_mana_value_x_from_any_graveyard(cards):
    s = build(cards)
    engine = put(s, "Sequence Engine", "battlefield")
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")  # mana value 2
    mana(s, C=2)
    with pytest.raises(ActionError):  # X = 1: nothing with mana value 1 there
        act(s, "p1", type="activate_ability", card_id=engine.id, ability=0, targets=[bears.id], x_value=1)
    act(s, "p1", type="activate_ability", card_id=engine.id, ability=0, targets=[bears.id], x_value=2)
    pass_until_stack_empty(s)
    assert zone(s, bears) == "p2:exile"
    fractal = next(c for c in s.state.cards.values() if c.name == "Fractal")
    assert fractal.counters.get("+1/+1") == 2
    settle(s)


def test_lazotep_quarry_exiles_by_mana_value_x_and_makes_a_4_4_zombie_copy(cards):
    s = build(cards)
    quarry = put(s, "Lazotep Quarry", "battlefield")
    elves = put(s, "Llanowar Elves", "graveyard")  # mana value 1
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=quarry.id, ability=2, targets=[elves.id], x_value=1)
    pass_until_stack_empty(s)
    assert zone(s, elves) == "p1:exile" and zone(s, quarry) == "p1:graveyard"
    token = next(c for c in s.state.cards.values() if c.is_token and c.controller == "p1")
    assert token.zone == "p1:battlefield"
    (copy,) = [e for e in s.state.rules.effects if e.copy_recipe is not None and e.affected[0].startswith(token.id)]
    (exc,) = copy.copy_recipe.excepts  # the copy exceptions: 4/4, black, a Zombie (707.9b)
    assert (exc.power, exc.toughness, exc.set_colors, exc.set_creature_types) == ("4", "4", ["B"], ["Zombie"])
    settle(s)
