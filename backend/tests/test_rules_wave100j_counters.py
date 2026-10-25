"""Wave 100J: counter lines the grammar didn't read (app/rules/counters100j.py), on real Oracle text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave100e_kit import answer, hand, library, pick, to_phase, tokens

# Real Oracle data (tests/fixtures/wave100j_cards.json, copied from the card database) plus a few plain probe cards.
REAL = json.loads((Path(__file__).parent / "fixtures" / "wave100j_cards.json").read_text("utf-8"))
EXTRA = [
    real("Probe Spider", "{1}{G}", 2, "Creature — Spider", "", ("2", "2"), "G"),
    real("Probe Legend", "{1}{G}", 2, "Legendary Creature — Elf", "", ("2", "2"), "G"),
    real("Probe Zombie", "{1}{B}", 2, "Creature — Zombie", "", ("2", "2"), "B"),
    real("Probe Ogre", "{2}{R}", 3, "Creature — Ogre", "", ("3", "3"), "R"),
    real("Probe Angel", "{2}{W}", 3, "Creature — Angel", "", ("3", "3"), "W"),
    real("Probe Drake", "{2}{U}", 3, "Creature — Drake", "Flying, trample", ("2", "2"), "U"),
    # (the text Valor's Reach Tag Team's Warrior tokens have, as a card: "this token" reads as "this creature", oracle.py)
    real("Probe Tag", "{2}{R}", 3, "Creature — Warrior", "Whenever this creature and at least one other creature token attack, put a +1/+1 counter "
         "on this creature.", ("3", "2"), "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    real_cards = [card(c["name"], number=f"100J-{i}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(REAL)]
    build_database([*fixture_cards(), *EXTRA, *real_cards], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in REAL])
def test_wave100j_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def res(s, pid, key):
    return s.state.players[pid].resources.get(key, 0)


def combat(s, attackers, chooser=None, turn=2):
    """Alice attacks Bob with ``attackers`` (no blocks) on her turn ``turn`` turns from now; ``chooser(d)`` answers decisions (None: first options)."""
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase in ("end_combat", "main2") and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            got = chooser(d) if chooser else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def murder(s, victim, *prefer):
    """Alice casts Murder on ``victim``; the decisions that follow are answered with ``prefer`` (when offered) or their first options."""
    m = next(c for c in s.state.cards.values() if c.name == "Murder" and c.zone in ("p1:library", "p1:hand"))
    act(s, "p1", type="move", card_ids=[m.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=m.id, targets=[victim.id])
    answer(s, *prefer)


# -- Decimator Web ---------------------------------------------------------------------------------------------------------------------------------
def test_decimator_web_drains_poisons_and_mills_the_target_opponent(cards):
    s = build(cards, ["Decimator Web"])
    web = put(s, "Decimator Web")
    top = library(s, "p2")[:6]
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=web.id, ability=0, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == 38 and res(s, "p2", "poison") == 1
    assert all(s.state.cards[c].zone == "p2:graveyard" for c in top) and s.state.players["p1"].life == 40
    check(s)


# -- Necrogen Rotpriest ------------------------------------------------------------------------------------------------------------------------------
def test_necrogen_rotpriest_adds_a_poison_counter_only_for_creatures_with_toxic(cards):
    s = build(cards, ["Necrogen Rotpriest", "Grizzly Bears"])
    priest, bear = put(s, "Necrogen Rotpriest"), put(s, "Grizzly Bears")
    combat(s, [priest, bear])
    assert res(s, "p2", "poison") == 3  # toxic 2 (702.164c) and the trigger's one; the Bears have no toxic
    check(s)


# -- Trygon Prime -------------------------------------------------------------------------------------------------------------------------------------
def test_trygon_prime_counters_itself_and_another_attacker_that_cant_be_blocked(cards):
    s = build(cards, ["Trygon Prime", "Grizzly Bears"], ["Llanowar Elves"])
    trygon, bear = put(s, "Trygon Prime"), put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (trygon, bear)])
    while (d := s.state.rules.decision) is None or d.kind != "declare_blockers":
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id] if bear.id in [o.id for o in d.options] else [d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert counters(s, trygon) == 1 and counters(s, bear) == 1
    with pytest.raises(ActionError):  # the Bears can't be blocked this turn
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": bear.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": trygon.id}])
    check(s)


# -- Ultimate Spider-Man -----------------------------------------------------------------------------------------------------------------------------
def test_ultimate_spider_man_doubles_counters_on_spiders_and_legends_only(cards):
    s = build(cards, ["Miles Morales // Ultimate Spider-Man", "Probe Spider", "Probe Legend", "Grizzly Bears"], ["Probe Spider"])
    miles = put(s, "Miles Morales // Ultimate Spider-Man")
    answer(s)
    act(s, "p1", type="set_face", card_id=miles.id, face=1)
    mine = [put(s, n) for n in ("Probe Spider", "Probe Legend", "Grizzly Bears")]
    theirs = put(s, "Probe Spider", "p2")
    for c in (*mine, theirs, miles):
        act(s, c.controller, type="counter", card_ids=[c.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[mine[0].id], kind="stun", delta=1)
    combat(s, [mine[2]])
    spider, legend, bear = mine
    assert (counters(s, spider), counters(s, spider, "stun"), counters(s, legend), counters(s, miles)) == (4, 2, 4, 4)  # Miles: a legendary Spider, once
    assert counters(s, bear) == 2 and counters(s, theirs) == 2  # neither a Spider nor legendary; another player's Spider
    check(s)


# -- Vexing Radgull -----------------------------------------------------------------------------------------------------------------------------------
def test_vexing_radgull_gives_two_rad_counters_or_else_proliferates(cards):
    s = build(cards, ["Vexing Radgull", "Grizzly Bears"])
    gull, bear = put(s, "Vexing Radgull"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    combat(s, [gull])
    assert res(s, "p2", "rad") == 2 and counters(s, bear) == 1  # no rad counters: two, no proliferate
    act(s, "p2", type="resource", player="p2", key="rad", delta=-1)
    seen = []

    def choose(d):
        seen.append(d.kind)
        return [o.id for o in d.options] if d.kind == "choose_cards" else None

    combat(s, [gull], choose)
    assert "choose_cards" in seen and res(s, "p2", "rad") == 2 and counters(s, bear) == 2  # it had one: proliferate (701.34a)
    check(s)


# -- Bounty Board -------------------------------------------------------------------------------------------------------------------------------------
def test_bounty_board_rewards_the_dying_creatures_controllers_opponents(cards):
    s = build(cards, ["Bounty Board", "Grizzly Bears", "Murder", "Murder"], ["Grizzly Bears"])
    put(s, "Bounty Board")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    for c in (mine, theirs):
        act(s, c.controller, type="counter", card_ids=[c.id], kind="bounty", delta=1)
    for m in [c for c in s.state.cards.values() if c.name == "Murder"]:
        act(s, "p1", type="move", card_ids=[m.id], to={"zone": "hand"})
    hands = hand(s, "p1"), hand(s, "p2")
    murder(s, theirs)  # Bob's creature: Alice, his opponent, draws and gains 2
    assert (hand(s, "p1"), s.state.players["p1"].life, hand(s, "p2"), s.state.players["p2"].life) == (hands[0], 42, hands[1], 40)
    murder(s, mine)  # Alice's own: Bob
    assert (hand(s, "p1"), s.state.players["p1"].life, hand(s, "p2"), s.state.players["p2"].life) == (hands[0] - 1, 42, hands[1] + 1, 42)
    check(s)


# -- Lightshield Array ------------------------------------------------------------------------------------------------------------------------------
def test_lightshield_array_counters_each_creature_that_attacked_this_turn(cards):
    s = build(cards, ["Invasion of Gobakhan // Lightshield Array", "Grizzly Bears", "Llanowar Elves"])
    array = put(s, "Invasion of Gobakhan // Lightshield Array")
    answer(s)
    act(s, "p1", type="set_face", card_id=array.id, face=1)
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    combat(s, [bear])
    to_phase(s, "end")
    answer(s)
    assert counters(s, bear) == 1 and counters(s, elves) == 0
    check(s)


# -- Erithizon / Ley Line: another player chooses the target ----------------------------------------------------------------------------------------
def test_erithizon_lets_the_defending_player_choose_the_target(cards):
    s = build(cards, ["Erithizon"], ["Grizzly Bears"])
    eri, theirs = put(s, "Erithizon"), put(s, "Grizzly Bears", "p2")
    chooser = []

    def choose(d):
        chooser.append(d.player)
        return [theirs.id] if theirs.id in [o.id for o in d.options] else None

    combat(s, [eri], choose)
    assert chooser[0] == "p2" and counters(s, theirs) == 1 and counters(s, eri) == 0
    check(s)


def test_ley_line_lets_the_upkeep_player_choose_the_target_and_whether(cards):
    s = build(cards, ["Ley Line", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Ley Line")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_phase(s, "upkeep", turn=1)  # Bob's upkeep
    d = pick(s, "choose_one", theirs.id)
    assert d.player == "p2"
    d = pick(s, "choose_one", "pay")
    assert d.player == "p2"
    answer(s)
    assert counters(s, theirs) == 1 and counters(s, mine) == 0
    to_phase(s, "upkeep", turn=1)  # Alice's upkeep: she declines
    assert pick(s, "choose_one", mine.id).player == "p1"
    assert pick(s, "choose_one", "decline").player == "p1"
    answer(s)
    assert counters(s, mine) == 0
    check(s)


# -- The Ghoul, Gunslinger ---------------------------------------------------------------------------------------------------------------------------
def test_the_ghoul_gives_rad_counters_and_a_treasure_only_when_targeting_you(cards):
    s = build(cards, ["The Ghoul, Gunslinger", "Probe Zombie", "Grizzly Bears", "Murder", "Murder", "Murder"])
    ghoul = put(s, "The Ghoul, Gunslinger")
    zombie, bear = put(s, "Probe Zombie"), put(s, "Grizzly Bears")
    murder(s, bear)
    assert not s.state.zones.get("p1:graveyard", []) or s.state.cards[bear.id].zone == "p1:graveyard"
    assert res(s, "p1", "rad") == 0 and res(s, "p2", "rad") == 0  # not a Zombie or Mutant: no trigger
    murder(s, zombie, "p2")
    assert res(s, "p2", "rad") == 2 and not tokens(s, "Treasure", "p1")
    murder(s, ghoul, "p1")
    assert res(s, "p1", "rad") == 2 and len(tokens(s, "Treasure", "p1")) == 1
    check(s)


# -- Obscura Ascendancy ------------------------------------------------------------------------------------------------------------------------------
def test_obscura_ascendancy_checks_the_mana_value_at_trigger_and_resolution(cards):
    s = build(cards, ["Obscura Ascendancy", "Lightning Bolt", "Lightning Bolt", "Rampant Growth", "Lightning Bolt"])
    asc = put(s, "Obscura Ascendancy")
    act(s, "p1", type="set_prefs", hold_priority=True)
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for b in bolts[:2]:  # two mana value 1 instants in a row: both trigger, only the first to resolve finds 1 = 1 + 0 (the ruling)
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    assert len(s.state.zones["stack"]) == 4
    act(s, "p1", type="set_prefs", hold_priority=False)
    answer(s)
    assert counters(s, asc, "soul") == 1 and len(tokens(s, "Spirit", "p1")) == 1
    act(s, "p1", type="move", card_ids=[bolts[2].id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolts[2].id, targets=["p2"])
    answer(s)
    assert counters(s, asc, "soul") == 1  # mana value 1 is not 1 + 1: no trigger
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rampant Growth").id)
    answer(s)
    assert counters(s, asc, "soul") == 2 and len(tokens(s, "Spirit", "p1")) == 2
    check(s)
