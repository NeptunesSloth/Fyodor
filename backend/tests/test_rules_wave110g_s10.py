"""Wave 110G session 10: foundations for trains / flashback loyalty cost.

* Light Up the Night: 702.34a / 118.3 flashback removes X loyalty counters from your planeswalkers (X >= 1); 107.3a that X is the spell's.
* Savior of Ollenbock: 702.149c it trains only when a resolving training ability puts counters on it; its exile is returned when it leaves (607.2a, 610.3).
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, life
from tests.wave110b_kit import attack, cast, check, mana, pt, put

EXTRA = [
    real("Savior of Ollenbock", "{1}{W}{W}", 3, "Creature — Human Soldier", "Training (Whenever this creature attacks with another creature with greater power, put a +1/+1 counter on this creature.)\n"
         "Whenever this creature trains, exile up to one other target creature from the battlefield or creature card from a graveyard.\n"
         "When this creature leaves the battlefield, put the exiled cards onto the battlefield under their owners' control.", ("1", "2"), "W"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
    real("Squire", "{W}", 1, "Creature \u2014 Human", "", ("1", "1"), "W"),
    real("Light Up the Night", "{X}{R}", 1, "Sorcery", "Light Up the Night deals X damage to any target. It deals X plus 1 damage instead if that target is a creature or planeswalker.\n"
         "Flashback\u2014{3}{R}, Remove X loyalty counters from among planeswalkers you control. If you cast this spell this way, X can't be 0. (You may cast this card from your graveyard for its "
         "flashback cost. Then exile it.)", None, "R"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
]
NAMES = ["Savior of Ollenbock", "Light Up the Night"]


def drive(s, pick=None, limit=80):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            ids = ([i for i in ids if pick(i)] if pick else ids)[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("partner, exiled", [("Hill Giant", True), ("Squire", False)])
def test_savior_trains_only_with_a_bigger_attacker_and_gives_the_exile_back(cards, partner, exiled):
    """Savior: attacking with a bigger creature trains it (counter, exile the Bears); an equal-power partner does not train; Murder returns the Bears."""
    s = build(cards, ["Savior of Ollenbock", "Hill Giant", "Squire", "Grizzly Bears", "Murder"], ["Grizzly Bears"])
    sav, other, theirs = put(s, "Savior of Ollenbock"), put(s, partner), put(s, "Grizzly Bears", "p2")
    attack(s, sav, other)
    drive(s, lambda i: theirs.id in i)
    assert pt(s, "Savior of Ollenbock") == ((2, 3) if exiled else (1, 2))
    assert s.state.cards[theirs.id].zone == ("p2:exile" if exiled else "p2:battlefield")
    mana(s, "p1", C=1, B=2)
    cast(s, "Murder", [sav.id])
    drive(s)
    assert s.state.cards[sav.id].zone == "p1:graveyard"
    assert s.state.cards[theirs.id].zone == "p2:battlefield"
    check(s)


def test_savior_can_exile_a_creature_card_from_a_graveyard_and_returns_it_to_the_battlefield(cards):
    """Savior: the target may be a creature card in a graveyard; when Savior leaves it enters the battlefield under its owner's control (610.3)."""
    s = build(cards, ["Savior of Ollenbock", "Hill Giant", "Grizzly Bears", "Murder"], ["Grizzly Bears"])
    sav, other = put(s, "Savior of Ollenbock"), put(s, "Hill Giant")
    dead = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[dead.id], to={"zone": "graveyard"})
    attack(s, sav, other)
    drive(s, lambda i: dead.id in i)
    assert s.state.cards[dead.id].zone == "p2:exile"
    mana(s, "p1", C=1, B=2)
    cast(s, "Murder", [sav.id])
    drive(s)
    assert s.state.cards[dead.id].zone == "p2:battlefield"
    check(s)


def _flashback(cards, x, target_creature=False, loyalty=3):
    s = build(cards, ["Light Up the Night", "Test Walker Card"], ["Grizzly Bears"])
    walker = put(s, "Test Walker Card")
    act(s, "p1", type="counter", card_ids=[walker.id], kind="loyalty", delta=loyalty)
    spell = card_named(s, "Light Up the Night")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "graveyard"})
    bears = put(s, "Grizzly Bears", "p2") if target_creature else None
    mana(s, "p1", R=1, C=3)
    return s, walker, spell, bears


@pytest.mark.parametrize("x, target_creature, damage", [(2, False, 2), (2, True, 3)])
def test_light_up_the_night_flashback_removes_x_loyalty_and_is_exiled(cards, x, target_creature, damage):
    """Light Up the Night: flashback with X = 2 removes two loyalty from the walker; X damage to a player, X + 1 to a creature; the card is exiled."""
    s, walker, spell, bears = _flashback(cards, x, target_creature)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x, targets=[bears.id if bears else "p2"])
    drive(s)
    assert s.state.cards[spell.id].zone == "p1:exile"
    assert s.state.cards[walker.id].counters.get("loyalty") == 1
    if bears:
        assert s.state.cards[bears.id].zone == "p2:graveyard" if damage >= 2 else True
    else:
        assert life(s, "p2") == 40 - damage
    check(s)


def test_light_up_the_night_flashback_needs_x_of_at_least_one_and_loyalty_to_remove(cards):
    """Light Up the Night: X = 0 can't pay the flashback; X = 4 with only 3 loyalty can't either (118.3)."""
    from app.game.errors import ActionError

    s, walker, spell, _ = _flashback(cards, 0)
    for x in (0, 4):
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x, targets=["p2"])
    assert s.state.cards[spell.id].zone == "p1:graveyard"


def test_light_up_the_night_cast_from_hand_removes_no_loyalty(cards):
    """Light Up the Night: the hard cast has no loyalty cost; X = 0 deals 0."""
    s, walker, spell, _ = _flashback(cards, 1)
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3, targets=["p2"])
    drive(s)
    assert life(s, "p2") == 37 and s.state.cards[walker.id].counters.get("loyalty") == 3 and s.state.cards[spell.id].zone == "p1:graveyard"
    check(s)
