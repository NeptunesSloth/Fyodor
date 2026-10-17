"""Wave 48A: single-wording gaps of cards ranked 13,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave48a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2c, 608.2h: "Destroy target artifact. ~ deals damage to that artifact's controller equal to the artifact's mana value." (Viashino Heretic) - the artifact as it
  last existed; the damage goes to whoever controlled it, Alice for her own artifact.
* 601.2c, 400.1: "{1}{B}, {T}: Exile two target cards from an opponent's graveyard." (Deadeye Tracker, Lochmere Serpent, the Advocates) - rulings: the cards are in a single
  opponent's graveyard; the ability cannot be activated without two of them.
* 701.27a, 701.27f: "Transform up to one target Werewolf you control." (Waxing Moon), "{5}: Transform target Incubator token you control. Double the number of +1/+1
  counters on it." (Elvish Vatkeeper) - the chosen permanent turns over; a target that is not a Werewolf (an Incubator token) is no legal target.
* 701.53a: "Incubate X twice, where X is the number of lands you control." (Glistening Dawn) - two Incubator tokens, each with X counters (X read as it resolves);
  "you gain 5 life and incubate 5" (Tangled Skyline).
* 608.2c, 702.33e: "Counter target spell if its mana value is 2 or less. If this spell was kicked, counter that spell if its mana value is 4 or less instead." (Prohibit, Overload) - the
  limit is judged as the spell resolves: a three-mana spell survives it unkicked and is countered kicked.
* 115.3, 611.2c: "Until end of turn, target creature gets +0/+2 and another target creature gets -2/-0." (Rookie Mistake, Skulduggery) - two different targets, each its own pump;
  "+X/+0 and -0/-X, where X is the number of artifacts you control" (Monoist Circuit-Feeder) - one X for both halves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, next_turn, settle, stops
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand
from tests.wave43b_kit import cast, ch, move, names_in

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_viashino_heretic_damages_the_controller_of_the_artifact_by_its_mana_value(cards):
    s = build(cards, ["Viashino Heretic"], ["Arcane Signet"])
    heretic = put(s, "Viashino Heretic")
    signet = put(s, "Arcane Signet", "p2")
    next_turn(s)  # (summoning sickness: it has to be there since the turn began)
    mana(s, R=1, C=1)
    activate(s, "p1", heretic, targets=[signet.id])
    settle(s)
    assert s.state.cards[signet.id].zone == "p2:graveyard"
    assert life(s, "p2") == 38 and life(s, "p1") == 40  # Arcane Signet is mana value 2
    check(s)


def test_viashino_heretic_hurts_its_own_controller_for_an_artifact_of_theirs(cards):
    s = build(cards, ["Viashino Heretic", "Sol Ring"], [])
    heretic = put(s, "Viashino Heretic")
    ring = put(s, "Sol Ring")
    next_turn(s)  # (summoning sickness: it has to be there since the turn began)
    mana(s, R=1, C=1)
    activate(s, "p1", heretic, targets=[ring.id])
    settle(s)
    assert life(s, "p1") == 39 and life(s, "p2") == 40
    check(s)


def test_rookie_mistake_pumps_one_creature_and_shrinks_another(cards):
    s = build(cards, ["Rookie Mistake", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Rookie Mistake")
    mana(s, U=1)
    cast(s, "Rookie Mistake", targets=[mine.id, theirs.id], target_counts=[1, 1])
    assert pt(s, "Grizzly Bears") == (2, 4) and pt(s, "Grizzly Bears", "p2") == (0, 2)
    check(s)


def test_rookie_mistake_needs_two_different_creatures(cards):
    s = build(cards, ["Rookie Mistake", "Grizzly Bears"], [])
    only = put(s, "Grizzly Bears")
    to_hand(s, "Rookie Mistake")
    mana(s, U=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Rookie Mistake").id, targets=[only.id, only.id], target_counts=[1, 1])


def test_skulduggery_pumps_a_creature_you_control_and_shrinks_an_opponents(cards):
    s = build(cards, ["Skulduggery", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Skulduggery")
    mana(s, B=1)
    cast(s, "Skulduggery", targets=[mine.id, theirs.id], target_counts=[1, 1])
    assert pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Grizzly Bears", "p2") == (1, 1)
    check(s)


def test_monoist_circuit_feeder_counts_artifacts_once_for_both_halves(cards):
    s = build(cards, ["Monoist Circuit-Feeder", "Sol Ring", "Grizzly Bears"], ["Albino Troll"])
    put(s, "Sol Ring")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Albino Troll", "p2")
    to_hand(s, "Monoist Circuit-Feeder")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monoist Circuit-Feeder").id)
    for pick in (mine, theirs):  # the enters ability's two targets, one after the other
        d = ask(s)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])
    settle(s)
    # two artifacts (Sol Ring and the Feeder): +2/+0 on Alice's Bears, -0/-2 on Bob's Troll
    assert pt(s, "Grizzly Bears") == (4, 2) and pt(s, "Albino Troll", "p2") == (3, 1)
    check(s)


def test_deadeye_tracker_exiles_two_cards_of_one_opponents_graveyard_and_explores(cards):
    s = build(cards, ["Deadeye Tracker"], ["Grizzly Bears", "Elvish Visionary"])
    tracker = put(s, "Deadeye Tracker")
    move(s, "Grizzly Bears", pid="p2")
    move(s, "Elvish Visionary", pid="p2")
    next_turn(s)
    mana(s, B=1, C=1)
    a, b = card_named(s, "Grizzly Bears", "p2"), card_named(s, "Elvish Visionary", "p2")
    activate(s, "p1", tracker, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert names_in(s, "graveyard", "p2") == [] and names_in(s, "exile", "p2") == ["Elvish Visionary", "Grizzly Bears"]
    assert "Forest" in names_in(s, "hand")  # explores: the revealed land goes to hand
    check(s)


def test_deadeye_tracker_needs_two_cards_in_an_opponents_graveyard(cards):
    s = build(cards, ["Deadeye Tracker", "Grizzly Bears"], ["Elvish Visionary"])
    tracker = put(s, "Deadeye Tracker")
    move(s, "Elvish Visionary", pid="p2")
    move(s, "Grizzly Bears")  # (Alice's own graveyard)
    next_turn(s)
    mana(s, B=1, C=1)
    theirs, mine = card_named(s, "Elvish Visionary", "p2"), card_named(s, "Grizzly Bears")
    with pytest.raises(ActionError):
        activate(s, "p1", tracker, targets=[theirs.id], target_counts=[1])  # one card is not two
    with pytest.raises(ActionError):
        activate(s, "p1", tracker, targets=[theirs.id, mine.id], target_counts=[2])  # her own graveyard is no opponent's


def test_waxing_moon_turns_a_werewolf_over_and_gives_trample(cards):
    s = build(cards, ["Waxing Moon", "Villagers of Estwald // Howlpack of Estwald", "Grizzly Bears"], [])
    wolf, bears = put(s, "Villagers of Estwald // Howlpack of Estwald"), put(s, "Grizzly Bears")
    to_hand(s, "Waxing Moon")
    mana(s, G=2)
    cast(s, "Waxing Moon", targets=[wolf.id], target_counts=[1])
    assert s.state.cards[wolf.id].face == 1 and pt(s, "Villagers of Estwald // Howlpack of Estwald") == (4, 6)
    assert "trample" in ch(s, bears).keywords
    check(s)


def test_waxing_moon_cannot_target_a_creature_that_is_not_a_werewolf(cards):
    s = build(cards, ["Waxing Moon", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    to_hand(s, "Waxing Moon")
    mana(s, G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Waxing Moon").id, targets=[bears.id], target_counts=[1])


def test_elvish_vatkeeper_transforms_the_incubator_and_doubles_its_counters(cards):
    s = build(cards, ["Elvish Vatkeeper"], [])
    to_hand(s, "Elvish Vatkeeper")
    mana(s, B=1, G=1, C=1)
    cast(s, "Elvish Vatkeeper")  # incubate 2
    token = next(c for c in s.state.cards.values() if c.name == "Incubator")
    assert s.state.cards[token.id].counters.get("+1/+1") == 2
    mana(s, C=5)
    activate(s, "p1", card_named(s, "Elvish Vatkeeper"), "Transform target", targets=[token.id])
    settle(s)
    now = s.state.cards[token.id]
    assert now.face == 1 and now.counters.get("+1/+1") == 4 and "Creature" in ch(s, now).types
    check(s)


def incubators(s):
    return [c for c in s.state.cards.values() if c.name == "Incubator" and c.zone == "p1:battlefield"]


def test_glistening_dawn_makes_two_incubators_with_x_counters_each(cards):
    s = build(cards, ["Glistening Dawn"], [], forests=9)
    for forest in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]:
        act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Glistening Dawn")
    mana(s, G=2, C=2)
    cast(s, "Glistening Dawn")
    assert [c.counters.get("+1/+1") for c in incubators(s)] == [4, 4]  # four lands: X is 4 for both
    check(s)


def test_tangled_skyline_gains_life_and_incubates(cards):
    s = build(cards, ["Tangled Skyline"], [])
    to_hand(s, "Tangled Skyline")
    mana(s, G=1, C=4)
    cast(s, "Tangled Skyline")
    assert life(s) == 45 and [c.counters.get("+1/+1") for c in incubators(s)] == [5]
    check(s)


def prohibit(cards, kicked):
    """Alice casts Kitchen Finks (mana value 3); Bob answers with Prohibit, kicked or not."""
    s = build(cards, ["Kitchen Finks"], ["Prohibit"])
    stops(s)
    to_hand(s, "Kitchen Finks")
    to_hand(s, "Prohibit", "p2")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kitchen Finks").id)
    mana(s, "p2", U=1, C=1 + 2 * kicked)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Prohibit", "p2").id, targets=[card_named(s, "Kitchen Finks").id], kicker=kicked)
    settle(s)
    return s


def test_prohibit_does_not_counter_a_three_mana_spell_unless_kicked(cards):
    s = prohibit(cards, 0)
    assert s.state.cards[card_named(s, "Kitchen Finks").id].zone == "p1:battlefield"
    check(s)


def test_kicked_prohibit_counters_a_three_mana_spell(cards):
    s = prohibit(cards, 1)
    assert s.state.cards[card_named(s, "Kitchen Finks").id].zone == "p1:graveyard"
    check(s)
