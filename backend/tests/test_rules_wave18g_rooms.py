"""Wave 18G: Rooms (CR 709.5). A Room is a split permanent card with one shared type line; each half is a door that is locked or
unlocked (a designation of the permanent). A locked door has no name, mana cost or rules text; casting a half unlocks it as the Room
enters (709.5d); a locked door can be unlocked for its mana cost as a special action (116.2m, 709.5e); "When you unlock this door"
triggers when that door gets the designation (709.5h). Real Oracle text, a replay and a save/load round trip each."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, on_field, settle, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave15d_activated import roundtrip

REMINDER = "(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)"


def room(name, left, right, colors):
    (ln, lc, lt), (rn, rc, rt) = left, right
    return card(f"{ln} // {rn}", set_code="dsk", number=f"R-{ln[:5]}", layout="split", mana_cost=f"{lc} // {rc}", cmc=0.0,
                type_line="Enchantment — Room // Enchantment — Room", colors=colors, color_identity=colors, oracle_text=f"{lt}\n//\n{rt}",
                card_faces=[{"object": "card_face", "name": ln, "mana_cost": lc, "type_line": "Enchantment — Room",
                             "oracle_text": f"{lt}\n{REMINDER}", "colors": [c for c in colors if c in lc]},
                            {"object": "card_face", "name": rn, "mana_cost": rc, "type_line": "Enchantment — Room",
                             "oracle_text": f"{rt}\n{REMINDER}", "colors": [c for c in colors if c in rc]}])


EXTRA = [
    room("Grand Entryway", ("Grand Entryway", "{1}{W}", "When you unlock this door, create a 1/1 white Glimmer enchantment creature token."),
         ("Elegant Rotunda", "{2}{W}", "When you unlock this door, put a +1/+1 counter on each of up to two target creatures."), ["W"]),
    room("Dazzling", ("Dazzling Theater", "{3}{W}", "Creature spells you cast have convoke. (Your creatures can help cast those spells. Each "
                                                    "creature you tap while casting a creature spell pays for {1} or one mana of that creature's color.)"),
         ("Prop Room", "{2}{W}", "Untap each creature you control during each other player's untap step."), ["W"]),
    room("Smoky", ("Smoky Lounge", "{2}{R}", "At the beginning of your first main phase, add {R}{R}. Spend this mana only to cast Room spells "
                                              "and unlock doors."),
         ("Misty Salon", "{3}{U}", "When you unlock this door, create an X/X blue Spirit creature token with flying, where X is the number "
                                   "of unlocked doors among Rooms you control."), ["R", "U"]),
]
GRAND = "Grand Entryway // Elegant Rotunda"


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def doors(s, c):
    return s.state.rules.unlocked.get(s.state.rules.object_id(c.id), [])


def view(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def glimmers(s):
    return [c for c in s.state.cards.values() if c.name == "Glimmer" and c.zone.endswith(":battlefield")]


@pytest.mark.parametrize("name", [GRAND, "Dazzling Theater // Prop Room"])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_casting_a_half_unlocks_that_door_as_it_enters_and_triggers(cards):
    s = build(cards, GRAND)
    c = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, face=0)
    settle(s)
    assert doors(s, c) == [1]
    assert len(glimmers(s)) == 1  # "When you unlock this door" (709.5h) of the left door only
    ch = view(s, c)
    assert (ch.name, ch.mana_cost, ch.mana_value) == ("Grand Entryway", "{1}{W}", 2.0)  # 709.5: the locked half isn't there
    assert sorted(scripts.definitions(ch)) == [0]
    roundtrip(s)


def test_the_right_door_cast_unlocks_only_the_right_door(cards):
    s = build(cards, GRAND)
    c = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, face=1)
    settle(s)
    assert doors(s, c) == [2] and not glimmers(s)
    ch = view(s, c)
    assert (ch.name, ch.mana_value) == ("Elegant Rotunda", 3.0) and sorted(scripts.definitions(ch)) == [1]
    roundtrip(s)


def test_unlock_a_locked_door_for_its_cost_as_a_special_action(cards):
    s = build(cards, GRAND)
    c = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, face=0)
    settle(s)
    with pytest.raises(ActionError):  # the door is already unlocked
        act(s, "p1", type="unlock_door", card_id=c.id, door=1)
    with pytest.raises(ActionError):  # {2}{W} isn't there
        act(s, "p1", type="unlock_door", card_id=c.id, door=2)
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=c.id, door=2)
    settle(s)
    assert doors(s, c) == [1, 2]
    ch = view(s, c)
    assert (ch.name, ch.mana_cost, ch.mana_value) == ("Grand Entryway // Elegant Rotunda", "{1}{W}{2}{W}", 5.0)
    assert sorted(scripts.definitions(ch)) == [0, 1]
    roundtrip(s)


def test_a_room_that_enters_without_being_cast_has_both_doors_locked(cards):
    s = build(cards, GRAND)
    c = on_field(s, GRAND)
    settle(s)
    ch = view(s, c)
    assert doors(s, c) == [] and ch.name == "" and ch.mana_value == 0 and not scripts.definitions(ch)  # 709.5d
    assert not glimmers(s)  # nothing was unlocked: no trigger
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="unlock_door", card_id=c.id, door=1)  # (709.5e: even a Room that wasn't cast)
    settle(s)
    assert len(glimmers(s)) == 1
    roundtrip(s)


def test_unlocking_is_a_sorcery_speed_special_action_of_the_controller(cards):
    s = build(cards, GRAND, "Sol Ring")
    c = on_field(s, GRAND)
    mana(s, "p1", W=1, C=1)
    with pytest.raises(ActionError):  # (only its controller)
        act(s, "p2", type="unlock_door", card_id=c.id, door=1)
    spell = to_hand(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "stack"})  # a spell on the stack: not with the stack empty
    with pytest.raises(ActionError):
        act(s, "p1", type="unlock_door", card_id=c.id, door=1)
    assert doors(s, c) == []


def test_a_locked_door_has_no_rules_text_and_an_unlocked_one_does(cards):
    """709.5: Dazzling Theater's convoke grant is there only while its door is unlocked."""
    s = build(cards, "Dazzling Theater // Prop Room")
    c = on_field(s, "Dazzling Theater // Prop Room")
    assert not scripts.definitions(view(s, c))
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="unlock_door", card_id=c.id, door=1)
    assert [d["kind"] for d in scripts.definitions(view(s, c)).values()] == ["static"] and doors(s, c) == [1]
    roundtrip(s)


def test_each_door_triggers_only_when_it_is_the_one_unlocked(cards):
    s = build(cards, GRAND)
    c = on_field(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="unlock_door", card_id=c.id, door=1)
    settle(s)
    assert len(glimmers(s)) == 1  # the left door's trigger only
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="unlock_door", card_id=c.id, door=2)
    settle(s)
    assert len(glimmers(s)) == 1  # (the right door's trigger put counters on up to two creatures: the Glimmer)
    glimmer = glimmers(s)[0]
    assert s.state.cards[glimmer.id].counters == {"+1/+1": 1}
    roundtrip(s)


def test_a_copy_of_a_room_has_neither_door_unlocked(cards):
    """709.5c: the unlocked designations aren't copiable values (709.5b: the halves are)."""
    from app.rules import copying

    s = build(cards, GRAND, "Sol Ring")
    c = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, face=0)
    settle(s)
    ring = on_field(s, "Sol Ring")
    plan = Plan.view(s.state, "p1", s.cards)
    copying.add_copy_effect(plan, [plan.oid(ring.id)], copying.recipe_of(plan, s.state.cards[c.id]), "p1")
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ring.id])
    assert ch.name == "" and not scripts.definitions(ch) and doors(s, ring) == []
