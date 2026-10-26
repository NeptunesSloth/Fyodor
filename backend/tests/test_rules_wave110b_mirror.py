"""Wave 110B: Mystic Reflection (614.1c, 614.12, 707.5): the next entry event of creatures / planeswalkers this turn enters as copies of the chosen creature."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, cast, ch, check, mana, put, to_hand

MR = ("Choose target nonlegendary creature. The next time one or more creatures or planeswalkers enter this turn, they enter as copies of the chosen creature.\n"
      "Foretell {U} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)")


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real

    settings.ensure_dirs()
    extra = [real("Mystic Reflection", "{1}{U}", 2, "Instant", MR, None, "U"), real("Mass Rise", "{4}{B}", 5, "Sorcery", "Return all creature cards from your graveyard to the battlefield.", None, "B"),
             real("Test Giant", "{3}{G}", 4, "Creature — Giant", "", ("4", "4"), "G")]
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def reflect(cards, *hand):
    """Alice casts Mystic Reflection on Bob's Test Giant (so the next creatures to enter are Test Giant copies)."""
    s = build(cards, ["Mystic Reflection", *hand], ["Test Giant"], forests=30)
    giant = put(s, "Test Giant", "p2")
    mana(s, U=2)
    cast(s, "Mystic Reflection", [giant.id])
    return s, giant


def mine(s):
    """Names (as they are now) of Alice's permanents on the battlefield, in id order."""
    return sorted(ch(s, c).name for c in s.state.cards.values() if c.zone == "p1:battlefield")


def test_mystic_reflection_full_and_next_creature_copies(cards):
    """614.1c / 707.5: the next creature to enter is a Test Giant copy (4/4); the one after is itself again (614.5: used up)."""
    assert coverage.of_card_data(cards.resolve("Mystic Reflection")).level == "FULL"
    s, _ = reflect(cards, "Grizzly Bears", "Llanowar Elves")
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert mine(s) == ["Test Giant"]
    assert ch(s, next(c for c in s.state.cards.values() if c.zone == "p1:battlefield")).power == "4"
    mana(s, G=2)
    cast(s, "Llanowar Elves")
    assert mine(s) == ["Llanowar Elves", "Test Giant"]
    check(s)


def test_mystic_reflection_one_event_copies_every_token(cards):
    """614.12: Raise the Alarm makes two Soldier tokens at once; both enter as Test Giants (one event), the later token doesn't."""
    s, _ = reflect(cards, "Raise the Alarm", "Grizzly Bears")
    mana(s, W=1, G=1)
    cast(s, "Raise the Alarm")
    assert mine(s) == ["Test Giant", "Test Giant"]
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert mine(s) == ["Grizzly Bears", "Test Giant", "Test Giant"]
    check(s)


def test_mystic_reflection_ignores_noncreature_and_chosen_creature_gone(cards):
    """A land entering isn't a creature or planeswalker (effect waits); if the chosen creature left, the new creature enters as itself."""
    s, giant = reflect(cards, "Grizzly Bears", "Forest")
    put(s, "Forest")
    assert mine(s) == ["Forest"]
    act(s, "p2", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert mine(s) == ["Forest", "Grizzly Bears"]
    check(s)


def test_mystic_reflection_copies_a_whole_batch_of_cards(cards):
    """614.12: Mass Rise puts two cards onto the battlefield in one event: both enter as Test Giants."""
    s, _ = reflect(cards, "Grizzly Bears", "Llanowar Elves", "Mass Rise")
    ids = [to_hand(s, n).id for n in ("Grizzly Bears", "Llanowar Elves")]
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, G=4)
    cast(s, "Mass Rise")
    assert mine(s) == ["Test Giant", "Test Giant"]
    check(s)


def reflect_twice(cards, second):
    """Alice casts two Mystic Reflections, on Bob's Test Giant and on the named other creature of his; then a Grizzly Bears is the next entry."""
    s = build(cards, ["Mystic Reflection", "Mystic Reflection", "Grizzly Bears"], ["Test Giant", "Grizzly Bears"], forests=30)
    giant = put(s, "Test Giant", "p2")
    other = giant if second == "same" else put(s, "Grizzly Bears", "p2")
    for target in (giant, other):
        mana(s, U=2)
        cast(s, "Mystic Reflection", [target.id])
    return s


def test_two_reflections_on_the_same_creature_both_apply_to_one_event(cards):
    """614.5, 616.1: both waiting effects are used up by the one event; same creature, so the order does not matter."""
    s = reflect_twice(cards, "same")
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert mine(s) == ["Test Giant"]
    check(s)


def test_two_reflections_on_different_creatures_leave_the_order_to_the_controller(cards):
    """616.1: the order is the affected object's controller's choice; handled by hand (a note), and both effects are used up (614.5)."""
    s = reflect_twice(cards, "other")
    mana(s, G=2)
    cast(s, "Grizzly Bears")
    assert mine(s) == ["Grizzly Bears"]
    assert any("copy by hand" in str(e) for e in s.state.log)
    from app.game.rules_state import turn_log_now

    assert not turn_log_now(s.state).mirror110b
    check(s)
