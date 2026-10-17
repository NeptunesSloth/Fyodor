"""Wave 45C: "is destroyed" as a trigger event (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json).
Every scenario checks the replay and a save and a load.

* 701.8a-b: a permanent is destroyed by an effect that says "destroy" (or by the state-based destruction of damage, not recorded: only a noncreature subject is
  read, Jaws): "Whenever a noncreature artifact is sacrificed or destroyed, Jaws deals 1 damage to each opponent", any player's, looking back in time (603.10a).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, check, life, mana, put, to_hand
from tests.wave36a_kit import resolve_stack
from tests.wave45c_kit import ability, make_repo, zone


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


def test_jaws_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Jaws, Relentless Predator")).level == "FULL"


def shatter(s, target):
    to_hand(s, "Shatter")
    mana(s, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shatter").id, targets=[target.id])
    resolve_stack(s)


def test_jaws_pings_each_opponent_when_a_noncreature_artifact_is_destroyed(cards):
    s = table(cards, ["Jaws, Relentless Predator", "Shatter"], ["Sol Ring"], players=3)
    put(s, "Jaws, Relentless Predator")
    ring = put(s, "Sol Ring", "p2")  # (any player's artifact)
    shatter(s, ring)
    assert zone(s, "Sol Ring", "p2") == "p2:graveyard"
    assert life(s, "p2") == 39 and life(s, "p3") == 39 and life(s) == 40
    check(s)


def test_jaws_sees_a_creature_destroyed_as_nothing(cards):
    s = table(cards, ["Jaws, Relentless Predator", "Murder"], ["Grizzly Bears"])
    put(s, "Jaws, Relentless Predator")
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Murder")
    mana(s, B=2, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[bears.id])
    resolve_stack(s)
    assert zone(s, "Grizzly Bears", "p2") == "p2:graveyard" and life(s, "p2") == 40
    check(s)


def test_jaws_pings_when_a_noncreature_artifact_is_sacrificed(cards):
    """Tavern Scoundrel's cost sacrifices another permanent: Sol Ring (not Jaws, nor the Scoundrel)."""
    s = table(cards, ["Jaws, Relentless Predator", "Tavern Scoundrel", "Sol Ring"])
    put(s, "Jaws, Relentless Predator")
    scoundrel = put(s, "Tavern Scoundrel")
    put(s, "Sol Ring")
    s.state.rules.controlled_since[scoundrel.id].turn = 0
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=scoundrel.id, ability=ability(s, scoundrel, "Flip a coin"))
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Sol Ring")])
    resolve_stack(s)
    assert zone(s, "Sol Ring") == "p1:graveyard" and life(s, "p2") == 39
    check(s)
