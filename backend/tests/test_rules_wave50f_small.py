"""Wave 50F: sole-line commanders (CR 2026-09-25), real Oracle text (tests/fixtures/wave50f_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 118.12, 603.12: "you may have her deal 2 damage to you. When you do, she deals 4 damage to target creature." (Elektra, Femme Fatale) - the damage
  to yourself is the optional cost (paid by the source), the reflexive ability follows only if it was paid.
* 603.12, 115.1, 601.2c: "you may exile it. When you do, for each opponent, exile up to one target creature that player controls." (The Balrog of
  Moria), "you may pay {2}. When you do, for each opponent, destroy up to one target …" (Lich's Relic) - the reflexive ability has a target group per opponent.
* 608.2c: "target creature gets +1/+0 until end of turn for each creature you control and can't be blocked this turn." (Invisible Woman) and
  "destroy target nonbasic land defending player controls, and creatures that player controls without flying can't block this turn." (The Motherlode):
  two instructions, the second about the same target / the defending player.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attack, next_turn, stops
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50f_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50f", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["The Balrog of Moria", "Elektra, Femme Fatale", "Invisible Woman", "The Motherlode, Excavator", "Lich's Relic"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, answer="yes", target=None, limit=60):
    """Resolve everything: an optional ability is answered ``answer``, a target choice picks the option named ``target``, any other choice its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for o in d.options if o.label == target]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else want or ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast_from_hand(s, name, **m):
    to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)


def murder_own(s, victim):
    to_hand(s, "Murder")
    mana(s, B=2, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[victim.id])


def test_elektra_hurts_herself_to_deal_four(cards):
    s = build(cards, ["Elektra, Femme Fatale"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Elektra, Femme Fatale", R=1, G=3)
    settle(s, answer="pay", target="Grizzly Bears")
    assert life(s) == 38 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_elektra_declined_deals_nothing(cards):
    s = build(cards, ["Elektra, Femme Fatale"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Elektra, Femme Fatale", R=1, G=3)
    settle(s, answer="decline", target="Grizzly Bears")
    assert life(s) == 40 and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_balrog_exiles_the_opponents_creature_when_it_exiles_itself(cards):
    s = build(cards, ["The Balrog of Moria", "Murder"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    murder_own(s, put(s, "The Balrog of Moria"))
    settle(s, answer="yes")
    assert zone_of(s, "The Balrog of Moria") == "p1:exile" and s.state.cards[bears.id].zone == "p2:exile"
    check(s)


def test_balrog_declined_stays_in_the_graveyard_and_exiles_nothing(cards):
    s = build(cards, ["The Balrog of Moria", "Murder"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    murder_own(s, put(s, "The Balrog of Moria"))
    settle(s, answer="no")
    assert zone_of(s, "The Balrog of Moria") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_lich_relic_pays_two_then_destroys_one_target_per_opponent(cards):
    s = build(cards, ["Lich's Relic"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Lich's Relic", B=1, G=2)
    settle(s, answer="pay")
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def to_blockers(s, limit=40):
    """Pass priority until Bob is asked to declare blockers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers asked")


def test_invisible_woman_pumps_and_makes_the_target_unblockable(cards):
    s = build(cards, ["Invisible Woman", "Grizzly Bears"], ["Grizzly Bears"])
    stops(s)
    woman = put(s, "Invisible Woman")
    put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, woman)
    mana(s, R=1, G=1, W=1, U=1)
    settle(s, answer="pay", target="Invisible Woman")
    assert pt(s, "Invisible Woman") == (5, 3)  # +1/+0 for each of the two creatures Alice controls
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": woman.id}])
    check(s)


def test_invisible_woman_unpaid_changes_nothing(cards):
    s = build(cards, ["Invisible Woman"], ["Grizzly Bears"])
    stops(s)
    woman = put(s, "Invisible Woman")
    theirs = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, woman)
    settle(s, answer="decline")
    assert pt(s, "Invisible Woman") == (3, 3)
    to_blockers(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": woman.id}])  # nothing stops the block
    check(s)


def test_motherlode_destroys_a_nonbasic_land_and_stops_blockers_without_flying(cards):
    s = build(cards, ["The Motherlode, Excavator"], ["Grizzly Bears", "Command Tower"])
    stops(s)
    lode = put(s, "The Motherlode, Excavator")
    theirs = put(s, "Grizzly Bears", "p2")
    tower = put(s, "Command Tower", "p2")
    next_turn(s)
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)
    attack(s, lode)
    settle(s, answer="pay", target="Command Tower")
    assert s.state.cards[tower.id].zone == "p2:graveyard"
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": lode.id}])
    check(s)


def test_motherlode_without_energy_leaves_the_land_and_the_blockers(cards):
    s = build(cards, ["The Motherlode, Excavator"], ["Grizzly Bears", "Command Tower"])
    stops(s)
    lode = put(s, "The Motherlode, Excavator")
    theirs = put(s, "Grizzly Bears", "p2")
    tower = put(s, "Command Tower", "p2")
    next_turn(s)
    attack(s, lode)
    settle(s, answer="pay")
    assert s.state.cards[tower.id].zone == "p2:battlefield"
    to_blockers(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": lode.id}])
    check(s)
