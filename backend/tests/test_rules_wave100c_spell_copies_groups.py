"""Wave 100C: copies, payments, group references and per-player choices of instants and sorceries (app/rules/static_spell100c.py), real
Oracle text (tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 115.7d / 707.10: new targets for a spell, then a copy of it as it now is; "that player copies it": the caster controls the copy.
* 101.4: "if any player pays": each player in turn order may pay; "each player may exile any number": all choices, then one exile.
* 702.95: "the creature it's paired with"; 701.24a: each owner shuffles their own targeted cards in.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life
from tests.wave100c_kit import (
    cast,
    chars,
    move,
    named,
    one,
    open_repo,
    pt_of,
    put_on,
    start_cast,
    three,
    zone,
)

PROMOTED = ["Wild Ricochet", "Bonus Round", "Rhystic Scrying", "Become Brutes", "Fateful Handoff", "Joint Assault", "Quag Feast",
            "Grave Consequences", "Turn the Earth", "Mists of Lórien", "Brood Birthing", "Elephant Resurgence"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield")]


# -- stack ------------------------------------------------------------------------------------------------------------------------------
def answer_in_order(s, *answers):
    """Resolve everything, answering each decision with the next answer (an option id; None: the first option)."""
    queue = list(answers)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            want = queue.pop(0) if queue else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[want if want is not None else d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_wild_ricochet_redirects_the_spell_and_copies_it(cards):
    """Wild Ricochet on Alice's Lightning Bolt at Bob's creature: the Bolt is turned to Bob; the copy (of the Bolt as it now is: at Bob) is
    turned back to the creature."""
    s = build(cards, ["Wild Ricochet", "Lightning Bolt"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    bolt = start_cast(s, "Lightning Bolt", targets=[bear.id], R=1)
    start_cast(s, "Wild Ricochet", targets=[bolt.id], R=2, C=2)
    answer_in_order(s, "p2", bear.id)
    assert life(s, "p2") == 37 and zone(s, bear) == "p2:graveyard"
    check(s)


def test_bonus_round_each_caster_copies_their_own_spell(cards):
    """Bonus Round: Alice's Lightning Bolt at Bob is copied by Alice; Bob's Bolt at Alice, cast in response, is copied by Bob (he is asked
    about the copy's targets)."""
    s = build(cards, ["Bonus Round", "Lightning Bolt"], ["Lightning Bolt"])
    cast(s, "Bonus Round", R=2, C=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p2", type="set_stops", own=[], others=["main1"], smart_pass=False)
    start_cast(s, "Lightning Bolt", targets=["p2"], R=1)
    act(s, "p1", type="pass_priority")
    start_cast(s, "Lightning Bolt", "p2", targets=["p1"], R=1)
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 34 and life(s) == 34 and "p2" in asked and "p1" in asked
    check(s)


@pytest.mark.parametrize("pays", [True, False])
def test_rhystic_scrying_discards_three_only_if_someone_pays(cards, pays):
    """Rhystic Scrying: "Draw three cards. Then if any player pays {2}, discard three cards." Bob pays (or nobody does)."""
    s = build(cards, ["Rhystic Scrying"], [])
    if pays:
        act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Rhystic Scrying", prefer=["pay"] if pays else ["decline", "no", "dont"], U=2, C=2)
    assert len(s.state.zones["p1:hand"]) == hand + 3 - (3 if pays else 0)
    check(s)


# -- groups -----------------------------------------------------------------------------------------------------------------------------
def test_become_brutes_gives_each_target_haste_and_its_own_monster_role(cards):
    s = build(cards, ["Become Brutes", "Grizzly Bears", "Llanowar Elves"], [])
    bear, elves = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves")
    cast(s, "Become Brutes", targets=[bear.id, elves.id], target_counts=[2], R=1, C=1)
    roles = tokens(s, "Monster")
    assert sorted(r.attached_to for r in roles) == sorted([bear.id, elves.id])
    assert pt_of(s, bear) == (3, 3) and {"haste", "trample"} <= chars(s, bear).keywords and "haste" in chars(s, elves).keywords
    check(s)


def test_fateful_handoff_draws_its_mana_value_then_an_opponent_takes_it(cards):
    """Fateful Handoff on Alice's Sol Ring (mana value 1), three players: Alice draws one; she gives the Ring to Carol."""
    s = three(cards, ["Fateful Handoff", "Sol Ring"])
    ring = put_on(s, "Sol Ring")
    library = len(s.state.zones["p1:library"])
    cast(s, "Fateful Handoff", targets=[ring.id], prefer=["p3"], B=1, C=3)
    assert len(s.state.zones["p1:library"]) == library - 1 and s.state.cards[ring.id].controller == "p3"
    check(s)


def test_joint_assault_pumps_the_paired_creature_too(cards):
    """Joint Assault on Silverblade Paladin paired with Grizzly Bears: both +2/+2; an unpaired creature alone."""
    s = build(cards, ["Joint Assault", "Silverblade Paladin", "Grizzly Bears", "Llanowar Elves"], [])
    bear, elves = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves")
    paladin = cast(s, "Silverblade Paladin", prefer=["yes", bear.id], W=2, C=1)
    assert "double strike" in chars(s, bear).keywords  # (paired)
    cast(s, "Joint Assault", targets=[paladin.id], G=1)
    assert pt_of(s, paladin) == (4, 4) and pt_of(s, bear) == (4, 4) and pt_of(s, elves) == (1, 1)
    check(s)




@pytest.mark.parametrize(("in_yard", "dies"), [(1, True), (0, False)])
def test_quag_feast_destroys_only_if_mana_value_fits_the_graveyard_after_the_mill(cards, in_yard, dies):
    """Quag Feast at Bob's Wall of Stone (mana value 3): after the mill Alice's graveyard holds three cards with Opt there first, else two (the
    spell itself is still on the stack)."""
    s = build(cards, ["Quag Feast", "Opt"], ["Wall of Stone"])
    wall = put_on(s, "Wall of Stone", "p2")
    if in_yard:
        move(s, one(s, "Opt"), "graveyard")
    cast(s, "Quag Feast", targets=[wall.id], B=1, C=1)
    assert zone(s, wall) == ("p2:graveyard" if dies else "p2:battlefield")
    check(s)


def test_grave_consequences_each_player_exiles_what_they_choose_then_loses_life_per_card_left(cards):
    """Grave Consequences: Alice exiles both her cards, Bob keeps his two: Alice loses nothing, Bob 2; then Alice draws (the second line)."""
    s = build(cards, ["Grave Consequences", "Opt", "Lightning Bolt"], ["Opt", "Lightning Bolt"])
    mine = [move(s, one(s, n), "graveyard") for n in ("Opt", "Lightning Bolt")]
    theirs = [move(s, one(s, n, "p2"), "graveyard") for n in ("Opt", "Lightning Bolt")]
    start_cast(s, "Grave Consequences", B=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[c.id for c in mine] if d.player == "p1" else [])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert all(zone(s, c) == "p1:exile" for c in mine) and all(zone(s, c) == "p2:graveyard" for c in theirs)
    assert life(s) == 40 and life(s, "p2") == 38 and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_turn_the_earth_shuffles_each_card_into_its_owners_library(cards):
    s = build(cards, ["Turn the Earth", "Opt"], ["Lightning Bolt"])
    opt, bolt = move(s, one(s, "Opt"), "graveyard"), move(s, one(s, "Lightning Bolt", "p2"), "graveyard")
    cast(s, "Turn the Earth", targets=[opt.id, bolt.id], target_counts=[2], G=1)
    assert zone(s, opt) == "p1:library" and zone(s, bolt) == "p2:library" and life(s) == 42
    check(s)


def test_mists_of_lorien_bounces_every_nonland_permanent_with_the_targets_mana_value(cards):
    """Mists of Lórien at Bob's Grizzly Bears (2): Alice's Arcane Signet (2) goes too; Sol Ring (1) and lands stay."""
    s = build(cards, ["Mists of Lórien", "Arcane Signet", "Sol Ring"], ["Grizzly Bears"])
    bear, signet, ring = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Arcane Signet"), put_on(s, "Sol Ring")
    forest = move(s, named(s, "Forest")[0], "battlefield")
    cast(s, "Mists of Lórien", targets=[bear.id], U=1, C=2)
    assert zone(s, bear) == "p2:hand" and zone(s, signet) == "p1:hand"
    assert zone(s, ring) == "p1:battlefield" and zone(s, forest) == "p1:battlefield"
    check(s)


def test_brood_birthing_makes_three_spawn_only_with_a_spawn_already(cards):
    s = build(cards, ["Brood Birthing"], [])
    spell = cast(s, "Brood Birthing", R=1, C=1)
    assert len(tokens(s, "Eldrazi Spawn")) == 1
    move(s, spell, "hand")
    cast(s, "Brood Birthing", R=1, C=1)
    spawn = tokens(s, "Eldrazi Spawn")
    assert len(spawn) == 4 and all(pt_of(s, t) == (0, 1) for t in spawn)
    check(s)


def test_elephant_resurgence_each_token_counts_its_controllers_creature_cards(cards):
    """Elephant Resurgence: Alice has two creature cards in her graveyard, Bob one: a 2/2 and a 1/1."""
    s = build(cards, ["Elephant Resurgence", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    for c in (one(s, "Grizzly Bears"), one(s, "Llanowar Elves"), one(s, "Grizzly Bears", "p2")):
        move(s, c, "graveyard")
    cast(s, "Elephant Resurgence", G=1, C=1)
    assert {t.controller: pt_of(s, t) for t in tokens(s, "Elephant")} == {"p1": (2, 2), "p2": (1, 1)}
    check(s)
