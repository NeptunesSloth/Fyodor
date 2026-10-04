"""Wave 16A: Class cards (CR 716). A class level bar is an activated ability (sorcery speed, only at the level before) that sets
the permanent's level; the lines under a bar are the Class's only at that level or above (716.2a); the level is a designation of
the permanent (716.2b), none is level 1 (716.2d), not copied, lost with the object (400.7). Real Oracle text, a replay and a
save/load round trip each."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, on_field, settle, token_of
from tests.test_rules_effects import mana
from tests.test_rules_wave15d_activated import roundtrip


def real(name, cost, cmc, text, colors):
    return card(name, set_code="tst", number=f"16A-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line="Enchantment — Class",
                oracle_text=text, colors=list(colors), color_identity=list(colors))


EXTRA = [
    real("Wizard Class", "{U}", 1,
         "(Gain the next level as a sorcery to add its ability.)\nYou have no maximum hand size.\n{2}{U}: Level 2\nWhen this Class "
         "becomes level 2, draw two cards.\n{4}{U}: Level 3\nWhenever you draw a card, put a +1/+1 counter on target creature you "
         "control.", "U"),
    real("Caretaker's Talent", "{2}{W}", 3,
         "(Gain the next level as a sorcery to add its ability.)\nWhenever one or more tokens you control enter, draw a card. This "
         "ability triggers only once each turn.\n{W}: Level 2\nWhen this Class becomes level 2, create a token that's a copy of "
         "target token you control.\n{3}{W}: Level 3\nCreature tokens you control get +2/+2.", "W"),
    real("Artist's Talent", "{1}{R}", 2,
         "(Gain the next level as a sorcery to add its ability.)\nWhenever you cast a noncreature spell, you may discard a card. If "
         "you do, draw a card.\n{2}{R}: Level 2\nNoncreature spells you cast cost {1} less to cast.\n{2}{R}: Level 3\nIf a source "
         "you control would deal noncombat damage to an opponent or a permanent an opponent controls, it deals that much damage "
         "plus 2 instead.", "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def bar(s, c, n):
    """The index of the "Level N" bar's activated ability (716.2a)."""
    from app.rules import characteristics as chars

    return next(a.index for a in chars.of(s.state.cards[c.id], s.cards).abilities
                if a.text.endswith(f"becomes {n}. Activate only if this Class is level {n - 1} and only as a sorcery."))


def level(s, c):
    return s.state.rules.levels.get(s.state.rules.object_id(c.id), 1)


def visible(s, c):
    return sorted(scripts.definitions(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])))


@pytest.mark.parametrize("name", ["Wizard Class", "Caretaker's Talent", "Artist's Talent"])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_levels_unlock_abilities_in_order_and_trigger_on_becoming_a_level(cards):
    s = build(cards, "Wizard Class")
    wiz = on_field(s, "Wizard Class")
    assert visible(s, wiz) == [0, 1]  # the static and bar 2; bar 3 and the level 3 trigger are hidden
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, 2))
    settle(s)
    assert level(s, wiz) == 2
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 2  # "When this Class becomes level 2"
    assert visible(s, wiz) == [0, 1, 2, 3]
    with pytest.raises(ActionError):  # level 2 is reached: bar 2 can't be used again
        act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, 2))
    roundtrip(s)


def test_bar_needs_the_previous_level_and_level_resets_off_the_battlefield(cards):
    s = build(cards, "Wizard Class")
    wiz = on_field(s, "Wizard Class")
    mana(s, "p1", U=2, C=6)
    with pytest.raises(ActionError):  # level 1 -> level 3 isn't allowed
        act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, 3))
    act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, 2))
    settle(s)
    act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, 3))
    settle(s)
    assert level(s, wiz) == 3
    act(s, "p1", type="move", card_ids=[wiz.id], to={"zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[wiz.id], to={"player": "p1", "zone": "battlefield"})
    assert level(s, wiz) == 1 and visible(s, wiz) == [0, 1]  # a new object (400.7)
    roundtrip(s)


def test_a_static_at_level_3_applies_only_from_level_3(cards):
    s = build(cards, "Caretaker's Talent")
    talent = on_field(s, "Caretaker's Talent")
    goblin = token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")

    def pt():
        return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[goblin.id]).pt

    assert pt() == (1, 1)
    mana(s, "p1", W=3, C=2)
    for n in (2, 3):
        act(s, "p1", type="activate_ability", card_id=talent.id, ability=bar(s, talent, n))
        settle(s)
        if n == 2:
            assert sum(c.name == "Goblin" for c in s.state.cards.values()) == 2  # the token copy
            assert pt() == (1, 1)
    assert pt() == (3, 3)
    roundtrip(s)


def test_a_copy_of_a_class_has_its_own_level_not_the_copied_one(cards):
    """716.2b: levels are not a copiable characteristic - a permanent copying a level 3 Class is level 1 (716.2d)."""
    from app.rules import copying

    s = build(cards, "Wizard Class")
    wiz = on_field(s, "Wizard Class")
    mana(s, "p1", U=2, C=6)
    for n in (2, 3):
        act(s, "p1", type="activate_ability", card_id=wiz.id, ability=bar(s, wiz, n))
        settle(s)
    goblin = token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")
    plan = Plan.view(s.state, "p1", s.cards)
    copying.add_copy_effect(plan, [plan.oid(goblin.id)], copying.recipe_of(plan, s.state.cards[wiz.id]), "p1")
    assert visible(s, goblin) == [0, 1] and level(s, goblin) == 1 and visible(s, wiz) == [0, 1, 2, 3, 4]


def test_a_cost_reduction_under_level_2_applies_only_from_level_2(cards):
    s = build(cards, "Artist's Talent", "Sol Ring")
    talent = on_field(s, "Artist's Talent")
    ring = next(c for c in s.state.cards.values() if c.name == "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "hand"})
    with pytest.raises(ActionError):  # {1} with no mana: level 1 has no cost reduction
        act(s, "p1", type="cast_spell", card_id=ring.id)
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=talent.id, ability=bar(s, talent, 2))
    settle(s)
    act(s, "p1", type="cast_spell", card_id=ring.id)  # {1} less: free
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    roundtrip(s)
