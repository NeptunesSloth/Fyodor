"""Wave 22E: event history and batched triggers (CR 2026-09-25). Real Oracle text (tests/fixtures/wave22e_cards.json);
every scenario checks the replay and a save and a load.

* 500.4 / 603.4: werewolves - "At the beginning of each upkeep, if no spells were cast last turn, transform this creature"
  and "... if a player cast two or more spells last turn, transform ..." read the turn before this one, any player's casts;
  the second is ONE player's own count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import ch, drive, find, game, mana, put, roundtrip
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, pt, to_hand, zone_of
from tests.wave9c_kit import put as kit_put

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave22e_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t22e", number=f"E{i:02d}", **({"image_uris": None} if c.get("card_faces") else {}),
              **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [card("Probe Cantrip", set_code="t22e", number="E90", mana_cost="{U}", cmc=1.0, type_line="Instant", colors=["U"],
               color_identity=["U"], oracle_text="Scry 1."),
          card("Probe Burst", set_code="t22e", number="E91", mana_cost="{R}", cmc=1.0, type_line="Instant", colors=["R"],
               color_identity=["R"], oracle_text="Probe Burst deals 1 damage to any target."),
          card("Probe Soldier", set_code="t22e", number="E92", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Human Soldier",
               colors=["W"], color_identity=["W"], oracle_text="", power="1", toughness="1"),
          card("Probe Goblin", set_code="t22e", number="E95", mana_cost="{R}", cmc=1.0, type_line="Creature — Goblin", colors=["R"],
               color_identity=["R"], oracle_text="", power="1", toughness="1"),
          card("Probe Reanimate", set_code="t22e", number="E93", mana_cost="{B}", cmc=1.0, type_line="Sorcery", colors=["B"],
               color_identity=["B"], oracle_text="Return target creature card from your graveyard to the battlefield."),
          card("Probe Cheat", set_code="t22e", number="E94", mana_cost="{G}", cmc=1.0, type_line="Sorcery", colors=["G"],
               color_identity=["G"], oracle_text="You may put a creature card from your hand onto the battlefield.")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(name):
    assert level(name) == "FULL", name


def to_turn(s, n, phase="main1"):
    until(s, lambda s: s.state.turn.number == n and s.state.turn.phase == phase, limit=400)


def front(s, c):
    return ch(s, c).name


def test_werewolf_transforms_on_a_quiet_turn_and_back_when_one_player_cast_two(cards):
    s = game(cards, ["Mayor of Avabruck // Howlpack Alpha"], ["Probe Cantrip", "Probe Cantrip"])
    mayor = put(s, "Mayor of Avabruck // Howlpack Alpha")
    assert front(s, mayor) == "Mayor of Avabruck"
    to_turn(s, 2)  # nobody cast a spell on turn 1: Bob's upkeep transformed it
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    roundtrip(s)
    for c in [c for c in s.state.cards.values() if c.name == "Probe Cantrip" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=c.id)
        drive(s)
    to_turn(s, 3)  # Bob alone cast two on turn 2: Alice's upkeep transforms it back
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    roundtrip(s)
    to_turn(s, 4)  # turn 3 was quiet: it turns over again
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    to_turn(s, 5)  # (turn 4 had no spells, but the night side only turns back for two by one player)
    drive(s)
    assert front(s, mayor) == "Howlpack Alpha"
    roundtrip(s)


def test_two_spells_by_two_players_are_not_two_by_one(cards):
    s = game(cards, ["Mayor of Avabruck // Howlpack Alpha", "Probe Cantrip"], ["Probe Cantrip"])
    mayor = put(s, "Mayor of Avabruck // Howlpack Alpha")
    mine = put(s, "Probe Cantrip", "hand")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=mine.id)  # turn 1: one spell
    drive(s)
    to_turn(s, 2)
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    theirs = put(s, "Probe Cantrip", "hand", "p2")
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id)
    drive(s)
    to_turn(s, 3)
    drive(s)
    assert front(s, mayor) == "Mayor of Avabruck"
    roundtrip(s)
    assert find(s, "Probe Cantrip", "p2")


# -- 115.1 / 603.2e: becomes the target ------------------------------------------------------------------------------
def burst_at(s, target, pid):
    """``pid`` casts a Probe Burst at ``target`` (the stack isn't passed)."""
    c = next(c for c in s.state.cards.values() if c.name == "Probe Burst" and c.owner == pid and c.zone == f"{pid}:hand")
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    return c


def settle_stack(s, limit=14):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None or not s.state.rules.stack:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def table(cards, mine=(), theirs=()):
    s = build(cards, [*mine, "Probe Burst"], [*theirs, "Probe Burst"])
    for name in mine:
        kit_put(s, name)
    to_hand(s, "Probe Burst"), to_hand(s, "Probe Burst", "p2")
    for pid in ("p1", "p2"):  # (mana in the pool: each stops to answer a spell)
        act(s, pid, type="add_mana", player=pid, mana={"R": 1, "C": 1})
    return s


def test_a_player_becomes_the_target_amulet_of_safekeeping(cards):
    s = table(cards, ["Amulet of Safekeeping"])
    burst_at(s, "p2", "p1")  # Alice's spell on Bob ...
    burst_at(s, "p1", "p2")  # ... Bob answers it at Alice: countered unless he pays {1}
    d = settle_stack(s)
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "decline")
    settle_stack(s)
    assert life(s, "p1") == 40 and life(s, "p2") == 40 - 1  # only her spell resolved
    assert zone_of(s, "Probe Burst", "p2") == "p2:graveyard"
    check(s)


def test_for_the_first_time_each_turn_counts_every_controller_glyph_keeper(cards):
    """603.2: Alice's own spell is the first time it became a target this turn (any controller), so it is countered; Bob's is the second."""
    s = table(cards, ["Glyph Keeper"])
    keeper = card_named(s, "Glyph Keeper")
    burst_at(s, keeper.id, "p1")
    burst_at(s, keeper.id, "p2")
    settle_stack(s)
    assert s.state.cards[keeper.id].damage == 1 and zone_of(s, "Glyph Keeper") == "p1:battlefield"  # Bob's resolved, Alice's didn't
    check(s)


def test_kira_gives_every_creature_the_first_target_counter(cards):
    s = table(cards, ["Kira, Great Glass-Spinner", "Probe Soldier"])
    soldier = card_named(s, "Probe Soldier")
    burst_at(s, soldier.id, "p1")  # the first time it became a target: countered
    burst_at(s, soldier.id, "p2")  # the second: it resolves (and the 1/1 dies)
    settle_stack(s)
    assert zone_of(s, "Probe Soldier") == "p1:graveyard"
    assert life(s, "p1") == 40
    check(s)


def test_the_kind_of_spell_wild_defiance(cards):
    s = table(cards, ["Wild Defiance", "Probe Soldier"])
    burst_at(s, card_named(s, "Probe Soldier").id, "p1")  # an instant: +3/+3 until end of turn, so the 1/1 survives the 1 damage
    settle_stack(s)
    assert zone_of(s, "Probe Soldier") == "p1:battlefield" and pt(s, "Probe Soldier") == (4, 4)
    check(s)


def test_you_or_a_permanent_unsettled_mariner(cards):
    s = table(cards, ["Unsettled Mariner", "Probe Soldier"])
    soldier = card_named(s, "Probe Soldier")
    burst_at(s, "p2", "p1")
    burst_at(s, soldier.id, "p2")  # Bob's answer, on her permanent: countered unless he pays {1}
    d = settle_stack(s)
    assert d is not None and d.player == "p2"
    answer(s, "decline")
    settle_stack(s)
    assert s.state.cards[soldier.id].zone == "p1:battlefield" and s.state.cards[soldier.id].damage == 0
    check(s)


def test_attacks_blocks_or_becomes_the_target_giggling_skitterspike(cards):
    s = table(cards, ["Giggling Skitterspike"])
    spike = card_named(s, "Giggling Skitterspike")
    burst_at(s, "p2", "p1")
    burst_at(s, spike.id, "p2")  # Bob's own spell on it: it deals damage equal to its power (1) to each opponent of its controller
    settle_stack(s)
    assert life(s, "p2") == 40 - 1 - 1 and zone_of(s, "Giggling Skitterspike") == "p1:battlefield"
    check(s)


# -- 603.2 / 603.4: where it entered from, and whether it was cast ----------------------------------------------------
def cast_spell(s, name, mana_pool, targets=None, pid="p1"):
    c = card_named(s, name, pid)
    if c.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="add_mana", player=pid, mana=mana_pool)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def settle_for(s, *ids):
    """Resolve the stack, picking ``ids`` whenever a decision offers one of them."""
    drive(s, lambda d: [i for i in ids if any(o.id == i for o in d.options)][:1] or None)


def test_enters_from_a_graveyard_treacherous_pit_dweller(cards):
    s = build(cards, ["Treacherous Pit-Dweller", "Probe Reanimate", "Probe Cheat"], [])
    dweller = to_hand(s, "Treacherous Pit-Dweller")
    cast_spell(s, "Probe Cheat", {"G": 1})  # from a hand: nothing happens
    settle_for(s, dweller.id, "yes")
    assert s.state.cards[dweller.id].zone == "p1:battlefield" and s.state.cards[dweller.id].controller == "p1"
    act(s, "p1", type="move", card_ids=[dweller.id], to={"player": "p1", "zone": "graveyard"})
    cast_spell(s, "Probe Reanimate", {"B": 1}, targets=[dweller.id])  # from a graveyard: Bob takes it
    settle_for(s)
    assert s.state.cards[dweller.id].zone == "p2:battlefield" and s.state.cards[dweller.id].controller == "p2"
    check(s)


def test_if_it_entered_from_your_graveyard_or_you_cast_it_archfiends_vessel(cards):
    s = build(cards, ["Archfiend's Vessel", "Probe Reanimate", "Probe Cheat"], [])
    vessel = to_hand(s, "Archfiend's Vessel")
    cast_spell(s, "Probe Cheat", {"G": 1})
    settle_for(s, vessel.id, "yes")
    assert zone_of(s, "Archfiend's Vessel") == "p1:battlefield"  # (from a hand, not cast: the intervening "if" fails)
    act(s, "p1", type="move", card_ids=[vessel.id], to={"player": "p1", "zone": "graveyard"})
    cast_spell(s, "Probe Reanimate", {"B": 1}, targets=[vessel.id])  # from its owner's graveyard
    settle_for(s, "yes")
    assert zone_of(s, "Archfiend's Vessel") == "p1:exile"
    [demon] = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert demon.name == "Demon"
    check(s)


def test_if_it_wasnt_cast_preston_the_vanisher(cards):
    s = build(cards, ["Preston, the Vanisher", "Probe Soldier", "Probe Soldier", "Probe Cheat"], [])
    kit_put(s, "Preston, the Vanisher")
    first, second = [c for c in s.state.cards.values() if c.name == "Probe Soldier" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    cast_spell(s, "Probe Cheat", {"G": 1})  # put onto the battlefield, not cast: a copy
    settle_for(s, first.id, "yes")
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(copies) == 1 and ch(s, copies[0]).pt == (0, 1) and "Illusion" in ch(s, copies[0]).subtypes
    cast_spell(s, "Probe Soldier", {"W": 1, "C": 1})  # cast: no copy
    settle_for(s)
    assert zone_of(s, "Probe Soldier") == "p1:battlefield"
    assert len([c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]) == 1
    check(s)


# -- 106.6: "When that mana is spent to cast a creature spell that shares a creature type with your commander" ---------
def test_path_of_ancestry_scries_for_a_spell_sharing_a_type_with_the_commander(cards):
    for spell, scries in (("Probe Goblin", True), ("Probe Soldier", False)):  # (Krenko, Mob Boss is a Goblin Warrior)
        s = build(cards, ["Path of Ancestry", spell], [])
        kit_put(s, "Path of Ancestry")
        s.state.rules.controlled_since[card_named(s, "Path of Ancestry").id].turn = 0
        c = to_hand(s, spell)
        act(s, "p1", type="add_mana", player="p1", mana={} if spell == "Probe Goblin" else {"W": 1})
        act(s, "p1", type="cast_spell", card_id=c.id)  # the Path's {R} pays for it (any color in her commander's identity)
        assert s.state.cards[card_named(s, "Path of Ancestry").id].tapped
        d = settle_stack(s)
        assert (d is not None and d.prompt.startswith("Scry 1")) == scries, (spell, d)
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        settle_stack(s)
        assert zone_of(s, spell) == "p1:battlefield"
        check(s)


