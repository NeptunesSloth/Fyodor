"""Wave 50H: "Kicker {A} and/or {B}" (CR 702.33b, 702.33f, 2026-09-25), real Oracle text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 702.33b: "Kicker {A} and/or {B}" is two kicker costs, each paid at most once: the cast's ``kicker`` is a mask (1: the first, 2: the second, 3: both).
* 702.33d / 702.33f: "if it was kicked", "if it was kicked twice" and "if it was kicked with its {R} kicker" read which costs were paid (Thornscape Battlemage,
  Archangel of Wrath, Illuminate); "it enters with … if it was kicked with its {1}{R} kicker" (Cetavolver) and its granted ability (Rakavolver) as it enters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until_asked
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BEAR = card("Runeclaw Bear", set_code="w50h", number="P01", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", oracle_text="", power="2", toughness="2",
            colors=["G"], color_identity=["G"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, BEAR], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def level(cards, name):
    return coverage.of_card_data(cards.resolve(name)).level


def pool(s, **m):
    mana(s, **{k: v for k, v in m.items() if v})


def triggers_target(s, *picks):
    """Answer the targets of the enters triggers: for each question the first of ``picks`` that is among its options."""
    for _ in range(12):
        d = until_asked(s)
        if d is None:
            return
        want = next((p for p in picks if p in {o.id for o in d.options}), None)
        act(s, d.player, type="choose", decision_id=d.id,
            option_ids=[want] if want and d.min_choices <= 1 else [o.id for o in d.options][: max(1, d.min_choices)])  # (two triggers: their order, 603.3b)


@pytest.mark.parametrize("name", ["Thornscape Battlemage", "Archangel of Wrath", "Illuminate", "Cetavolver", "Rakavolver", "Vodalian Mindsinger"])
def test_two_kicker_cards_are_full(cards, name):
    assert level(cards, name) == "FULL"


# -- the cost: the costs of the kickers that were chosen ----------------------------------------------------------
@pytest.mark.parametrize("mask,paid", [(1, {"R": 1}), (2, {"W": 1}), (3, {"R": 1, "W": 1})])
def test_the_chosen_kicker_costs_are_added_to_the_cost(cards, mask, paid):
    s = build(cards, ["Thornscape Battlemage"])
    bat = to_hand(s, "Thornscape Battlemage")
    pool(s, G=1, C=2, **paid)  # {2}{G} plus the kicker costs: no mana to spare
    act(s, "p1", type="cast_spell", card_id=bat.id, kicker=mask)
    assert s.state.players["p1"].mana == {}
    check(s)


def test_a_kicker_cost_that_isnt_paid_for_isnt_added_and_the_mask_is_checked(cards):
    s = build(cards, ["Thornscape Battlemage"])
    bat = to_hand(s, "Thornscape Battlemage")
    pool(s, G=1, C=2, R=1)  # only the {R} kicker is paid for
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bat.id, kicker=3)  # both: {W} too
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bat.id, kicker=4)  # there are only two costs
    check(s)


# -- "if it was kicked with its {R} kicker" -----------------------------------------------------------------------
@pytest.mark.parametrize("mask", [0, 1, 2, 3])
def test_each_enters_trigger_reads_its_own_kicker(cards, mask):
    s = build(cards, ["Thornscape Battlemage", "Sol Ring"], ["Sol Ring"])
    ring = put(s, "Sol Ring", "p2")
    bat = to_hand(s, "Thornscape Battlemage")
    pool(s, G=1, C=2, R=mask & 1, W=int(bool(mask & 2)))
    theirs = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=bat.id, kicker=mask)
    triggers_target(s, "p2", ring.id)
    settle(s)
    assert life(s, "p2") == theirs - (2 if mask & 1 else 0)  # {R}: "it deals 2 damage to any target"
    assert zone_of(s, "Sol Ring", "p2") == ("p2:graveyard" if mask & 2 else "p2:battlefield")  # {W}: "destroy target artifact"
    check(s)
    assert zone_of(reloaded(s), "Sol Ring", "p2") == ("p2:graveyard" if mask & 2 else "p2:battlefield")


def test_kicked_twice_needs_both_costs(cards):
    s = build(cards, ["Archangel of Wrath"], ["Runeclaw Bear"])
    put(s, "Runeclaw Bear", "p2")
    angel = to_hand(s, "Archangel of Wrath")
    pool(s, W=2, C=2, B=1, R=1)
    theirs = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=angel.id, kicker=3)  # {B} and/or {R}: kicked twice
    triggers_target(s, "p2")
    settle(s)
    assert life(s, "p2") == theirs - 4  # "if it was kicked": 2 damage, "if it was kicked twice": 2 more
    check(s)


def test_kicked_once_is_not_kicked_twice(cards):
    s = build(cards, ["Archangel of Wrath"])
    angel = to_hand(s, "Archangel of Wrath")
    pool(s, W=2, C=2, B=1)
    theirs = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=angel.id, kicker=1)
    triggers_target(s, "p2")
    settle(s)
    assert life(s, "p2") == theirs - 2
    check(s)


def test_a_spell_sentence_reads_which_kicker_was_paid(cards):
    # Illuminate {X}{R}, kickers {2}{R} and {3}{U}: "If this spell was kicked with its {2}{R} kicker, it deals X damage to that creature's controller."
    s = build(cards, ["Illuminate"], ["Runeclaw Bear"])
    bear = put(s, "Runeclaw Bear", "p2")
    ill = to_hand(s, "Illuminate")
    pool(s, R=2, C=4)  # {X}{R} with X = 2, and the {2}{R} kicker
    theirs = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=ill.id, kicker=1, x_value=2, targets=[bear.id])
    settle(s)
    assert zone_of(s, "Runeclaw Bear", "p2") == "p2:graveyard" and life(s, "p2") == theirs - 2  # the {2}{R} kicker: the controller takes X too
    check(s)


# -- "it enters with … if it was kicked with its {1}{R} kicker" (Cetavolver) and a granted ability (Rakavolver) ----------------
@pytest.mark.parametrize("mask,counters,first_strike,trample", [(0, 0, False, False), (1, 2, True, False), (2, 1, False, True), (3, 3, True, True)])
def test_the_volver_enters_with_what_each_kicker_gives(cards, mask, counters, first_strike, trample):
    s = build(cards, ["Cetavolver"])
    vol = to_hand(s, "Cetavolver")
    pool(s, U=1, C=1 + (1 if mask & 1 else 0), R=mask & 1, G=int(bool(mask & 2)))  # {1}{U}, and the kickers {1}{R} and {G}
    act(s, "p1", type="cast_spell", card_id=vol.id, kicker=mask)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[vol.id])
    assert pt(s, "Cetavolver") == (1 + counters, 1 + counters)
    assert ("first strike" in ch.keywords, "trample" in ch.keywords) == (first_strike, trample)
    check(s)


def test_the_volver_enters_with_the_ability_its_kicker_names(cards):
    s = build(cards, ["Rakavolver"])
    vol = to_hand(s, "Rakavolver")
    pool(s, R=1, C=3, W=1)  # {2}{R}, and the {1}{W} kicker
    act(s, "p1", type="cast_spell", card_id=vol.id, kicker=1)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, "Rakavolver").id])
    assert pt(s, "Rakavolver") == (4, 4)
    assert any("deals damage" in a.text and "gain that much life" in a.text for a in ch.abilities)  # '… and with "Whenever this creature deals damage, you gain that much life."'
    check(s)


def test_an_ability_it_enters_with_works_and_a_static_one_other_objects_depend_on_stays_manual(cards):
    # Rakavolver, kicked with {1}{W}: two +1/+1 counters and "Whenever this creature deals damage, you gain that much life." (a triggered ability: it runs); Prison
    # Barricade enters with "This creature can attack as though it didn't have defender." (a static that combat reads from printed text, 113.10: refused)
    from tests.test_rules_wave34b_activated import attack, next_turn

    assert level(cards, "Prison Barricade") != "FULL"
    s = build(cards, ["Rakavolver"])
    vol = to_hand(s, "Rakavolver")
    pool(s, R=1, C=3, W=1)
    act(s, "p1", type="cast_spell", card_id=vol.id, kicker=1)
    settle(s)
    next_turn(s)
    mine, theirs = life(s, "p1"), life(s, "p2")
    attack(s, vol)
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (mine + 4, theirs - 4)  # 4 damage dealt (a 2/2 with two counters): that much life gained
    check(s)


# -- a free cast (118.9d): the optional kicker costs are offered one by one, only the payable ones --------------------------------------------------
def test_a_free_cast_offers_only_the_kicker_masks_the_caster_can_pay(cards):
    gandalf = "Gandalf, Party Guest"
    alice = deck(cards, "Krenko, Mob Boss", [(1, gandalf), (1, "Illuminate"), (9, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, gandalf)
    bear = put(s, "Runeclaw Bear", "p2")
    for m in [c for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p1"][:3]:
        act(s, "p1", type="move", card_ids=[m.id], to={"player": "p1", "zone": "battlefield"})
    spell = to_hand(s, "Illuminate")
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        if s.state.rules.decision is not None:
            break
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[spell.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [(o.id, o.label) for o in d.options] == [("kicker:1", "Kicker {2}{R}")]  # {3}{U}: no blue mana to pay it
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    assert all(c.tapped for c in s.state.cards.values() if c.name == "Mountain" and c.zone == "p1:battlefield")  # the {2}{R} kicker, paid by the three Mountains
    assert any("Kicked" in str(e) for e in s.state.log)  # cast kicked (once: 702.33d)
    check(s)


# -- "Kicker—{2}{R}, Sacrifice a land." (702.33a): mana and a part, paid together ----------------------------------------------------------------------
def test_dwarven_landslide_is_full(cards):
    assert level(cards, "Dwarven Landslide") == "FULL"


def lands_of(s, pid, n):
    out = [c for c in s.state.cards.values() if c.owner == pid and c.name in ("Forest", "Island") and c.zone == f"{pid}:library"][:n]
    for c in out:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return out


def test_dwarven_landslide_kicked_pays_the_mana_and_sacrifices_a_land_and_destroys_two(cards):
    s = build(cards, ["Dwarven Landslide"])
    mine, theirs = lands_of(s, "p1", 1), lands_of(s, "p2", 2)
    spell = to_hand(s, "Dwarven Landslide")
    pool(s, R=2, C=5)  # {3}{R} and the {2}{R} of the kicker
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=[theirs[0].id, theirs[1].id], target_counts=[1, 1])
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[mine[0].id])
    settle(s)
    assert zone_of(s, "Forest") == "p1:graveyard" or s.state.cards[mine[0].id].zone == "p1:graveyard"  # sacrificed to pay the kicker (601.2h)
    assert all(s.state.cards[c.id].zone == "p2:graveyard" for c in theirs)  # "destroy another target land"
    check(s)


def test_dwarven_landslide_unkicked_destroys_one_and_sacrifices_nothing(cards):
    s = build(cards, ["Dwarven Landslide"])
    mine, theirs = lands_of(s, "p1", 1), lands_of(s, "p2", 2)
    spell = to_hand(s, "Dwarven Landslide")
    pool(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[theirs[0].id], target_counts=[1])
    settle(s)
    assert s.state.cards[mine[0].id].zone == "p1:battlefield"
    assert [s.state.cards[c.id].zone for c in theirs] == ["p2:graveyard", "p2:battlefield"]
    check(s)
