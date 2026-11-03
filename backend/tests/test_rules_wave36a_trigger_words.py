"""Wave 36A: trigger wordings the event grammar did not read (CR 2026-09-25, real Oracle text, tests/fixtures/wave36a_cards.json from data/cards.sqlite).
Every scenario checks the replay and a save and a load; each new event has a case where it fires and one where it does not.

* 508.3a, 508.5: "attacks one of your opponents or a planeswalker an opponent controls" (Gahiji, Frontier Warmonger): an attack on an opponent, or on a
  planeswalker an opponent controls (its controller is the defending player); not on you, nor on a planeswalker you control.
* 509.3a, 509.3b, 603.2c: "blocks one or more black creatures" (Rashka the Slayer), "blocks or becomes blocked by one or more Orcs" (Dwarven Soldier):
  once however many creatures of that kind it blocks or is blocked by; none of them, no trigger.
* 603.2c, 701.21a: "one or more players sacrifice one or more creatures" (Evin): every player's sacrifice of one batch is one event; "you sacrifice ~ or
  another creature" (Kingpin): either, each its own; 603.10a: ~ sacrificed itself is seen looking back in time.
* 701.9a: "When you discard this card" (Titanbones): it was discarded (put into the graveyard from a hand); the ability triggers from the graveyard.
* 603.2: "Whenever Bebop & Rocksteady attack or block": a plural name takes plural verbs, the same events; 201.5: the name is one object's.
* 507.1, 603.2: "At the beginning of combat on each player's turn" (Kitt Kanto): every player's turn, not only yours or an opponent's.
* 608.2c, 603.4: "Then if Cloud has power 7 or greater" is checked as that instruction is carried out (its power then); "may have it connive" (Baron Strucker):
  "it" is the creature that entered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, events
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, settle, until
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand
from tests.wave36a_kit import (
    attack,
    attack_as,
    block,
    offered,
    pick,
    ready,
    resolve_stack,
    to_gy,
    to_turn_of,
    zone,
)

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Gahiji, Honored One", "Frontier Warmonger", "Evin, Waterdeep Opportunist", "Hostile Investigator", "Kingpin, Wilson Fisk",
        "Titanbones, Towering Heart", "Bebop & Rocksteady", "Kitt Kanto, Mayhem Diva", "Rashka the Slayer", "Dwarven Soldier", "Amphibious Kavu",
        "Baron Strucker, HYDRA Overlord", "Silas Renn, Seeker Adept", "Cloud, Ex-SOLDIER", "Rielle, the Everwise", "Veronica, Dissident Scribe",
        "Magmakin Artillerist"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_trigger_wording_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "a creature attacks one of your opponents or a planeswalker an opponent controls",
    "one or more creatures attack one of your opponents or a planeswalker they control",
    "~ blocks one or more black creatures",
    "~ blocks or becomes blocked by one or more Orcs",
    "~ attack or block",
    "~ enter or attack",
    "one or more players sacrifice one or more creatures",
    "you sacrifice ~ or another creature",
    "you discard this card",
    "you discard one or more cards for the first time each turn",
    "you discard one or more nonland cards for the first time each turn",
])
def test_the_new_trigger_conditions_are_read(text):
    assert events.parse_condition(text) is not None


@pytest.mark.parametrize("text", [
    "an opponent attacks one of your opponents or a planeswalker they control",  # (a player's attack: the wording of a creature's)
    "~ blocks one or more",  # (nothing named)
    "one or more players cycle one or more cards",  # (only sacrifice and discard are batches of every player)
    "you discard ~ or another card",
    "you discard one or more cards with mana value 3 for the first time each turn",  # (a discard's mana value isn't kept in the turn's log: not asked of it)
    "an opponent discards one or more cards for the first time each turn",
])
def test_nearby_trigger_conditions_stay_unread(text):
    assert events.parse_condition(text) is None


def hp(s, name, pid="p1"):
    return pt(s, name, pid)


def loyal(s, name, pid="p1", loyalty=6):
    """A planeswalker on the battlefield with its loyalty (a bare move gives it none: 704.5i would put it into the graveyard)."""
    c = put(s, name, pid)
    act(s, pid, type="counter", card_ids=[c.id], kind="loyalty", delta=loyalty)
    return c


# -- Gahiji, Honored One -------------------------------------------------------------------------------------------------------------
def gahiji_table(cards):
    s = build(cards, ["Gahiji, Honored One", "Grizzly Bears", "Gideon Jura"], theirs=["Grizzly Bears", "Gideon Jura"], forests=20)
    put(s, "Gahiji, Honored One")
    put(s, "Grizzly Bears")
    ready(s, "Gahiji, Honored One", "Grizzly Bears")
    return s


def test_gahiji_gives_an_attacker_plus_two_power_when_it_attacks_an_opponent(cards):
    s = gahiji_table(cards)
    bears = card_named(s, "Grizzly Bears")
    attack(s, bears)
    settle(s)
    assert hp(s, "Grizzly Bears") == (4, 2)  # (+2/+0 until end of turn)
    check(s)


def test_gahiji_gives_it_to_an_attacker_of_a_planeswalker_an_opponent_controls(cards):
    s = gahiji_table(cards)
    gideon = loyal(s, "Gideon Jura", "p2")
    bears = card_named(s, "Grizzly Bears")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": gideon.id}])
    settle(s)
    assert hp(s, "Grizzly Bears") == (4, 2)
    check(s)


def test_gahiji_is_silent_when_a_creature_attacks_you_or_a_planeswalker_you_control(cards):
    """508.3a: an opponent's creature attacking you (or your planeswalker) isn't an attack on "one of your opponents"."""
    s = gahiji_table(cards)
    gideon = loyal(s, "Gideon Jura")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    bob_bears = card_named(s, "Grizzly Bears", "p2")
    attack_as(s, "p2", [bob_bears], gideon.id)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert hp(s, "Grizzly Bears", "p2") == (2, 2)
    check(s)


# -- Frontier Warmonger: "those creatures gain menace until end of turn" ----------------------------------------------------------------
def menace(s, name, pid="p1"):
    from app.rules.plan import Plan

    c = s.state.cards[card_named(s, name, pid).id]
    return "menace" in {k.lower() for k in Plan(s.state, "p1", s.cards, None).ch(c).granted}


def test_frontier_warmonger_gives_the_attackers_menace(cards):
    s = build(cards, ["Frontier Warmonger", "Grizzly Bears"], forests=20)
    put(s, "Frontier Warmonger")
    put(s, "Grizzly Bears")
    ready(s, "Frontier Warmonger", "Grizzly Bears")
    attack(s, card_named(s, "Grizzly Bears"))
    settle(s)
    assert menace(s, "Grizzly Bears") and not menace(s, "Frontier Warmonger")  # (those creatures: the ones that attacked)
    check(s)


def test_frontier_warmonger_is_silent_when_the_attack_is_on_you(cards):
    s = build(cards, ["Frontier Warmonger"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Frontier Warmonger")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], "p1")
    until(s, lambda s: s.state.turn.phase == "main2")
    assert not menace(s, "Grizzly Bears", "p2")
    check(s)


# -- Rashka the Slayer / Dwarven Soldier: "blocks one or more …" ---------------------------------------------------------------------------
def test_rashka_gets_the_bonus_when_it_blocks_a_black_creature(cards):
    s = build(cards, ["Rashka the Slayer"], theirs=["Dregscape Zombie"], forests=20)
    put(s, "Rashka the Slayer")
    put(s, "Dregscape Zombie", "p2")
    ready(s, "Dregscape Zombie", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Dregscape Zombie", "p2")], "p1")
    block(s, "p1", (card_named(s, "Rashka the Slayer"), card_named(s, "Dregscape Zombie", "p2")))
    settle(s)
    assert hp(s, "Rashka the Slayer") == (4, 5)  # (+1/+2 until end of turn)
    check(s)


def test_rashka_ignores_a_creature_that_is_not_black(cards):
    s = build(cards, ["Rashka the Slayer"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Rashka the Slayer")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], "p1")
    block(s, "p1", (card_named(s, "Rashka the Slayer"), card_named(s, "Grizzly Bears", "p2")))
    settle(s)
    assert hp(s, "Rashka the Slayer") == (3, 3)
    check(s)


def test_blocking_two_black_creatures_triggers_once(cards):
    """603.2c: "one or more" is one trigger however many of them it blocks (a creature that can block an additional creature)."""
    s = build(cards, [], theirs=["Dregscape Zombie", "Twisted Abomination"], forests=20)
    creature(s, "p1", "Double Rashka", "3/3", "Token Creature — Human Archer",
             "This creature can block an additional creature each combat.\nWhenever this creature blocks one or more black creatures, this creature gets +1/+2 until end of turn.")
    put(s, "Dregscape Zombie", "p2")
    put(s, "Twisted Abomination", "p2")
    ready(s, "Dregscape Zombie", "Twisted Abomination", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Dregscape Zombie", "p2"), card_named(s, "Twisted Abomination", "p2")], "p1")
    block(s, "p1", (card_named(s, "Double Rashka"), card_named(s, "Dregscape Zombie", "p2")),
          (card_named(s, "Double Rashka"), card_named(s, "Twisted Abomination", "p2")))
    puts = [e for e in s.state.log if any("put an ability on the stack" in (p.t or "") for p in e.parts)]
    assert len(puts) == 1  # (one trigger for the two black creatures it blocks)
    assert hp(s, "Double Rashka") == (4, 5)  # (once: +1/+2, not +2/+4)
    check(s)


def test_dwarven_soldier_gets_the_toughness_when_it_is_blocked_by_an_orc(cards):
    s = build(cards, ["Dwarven Soldier"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Dwarven Soldier")
    ready(s, "Dwarven Soldier")
    orc = creature(s, "p2", "Orc", "2/2", "Token Creature — Orc")
    attack(s, card_named(s, "Dwarven Soldier"))
    block(s, "p2", (orc, card_named(s, "Dwarven Soldier")))
    settle(s)
    assert hp(s, "Dwarven Soldier") == (2, 3)  # (blocked by an Orc: +0/+2)
    check(s)


def test_dwarven_soldier_is_unmoved_by_a_blocker_that_is_not_an_orc(cards):
    s = build(cards, ["Dwarven Soldier"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Dwarven Soldier")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Dwarven Soldier")
    attack(s, card_named(s, "Dwarven Soldier"))
    block(s, "p2", (card_named(s, "Grizzly Bears", "p2"), card_named(s, "Dwarven Soldier")))
    settle(s)
    assert hp(s, "Dwarven Soldier") == (2, 1)
    check(s)


# -- Evin, Waterdeep Opportunist / Kingpin, Wilson Fisk: sacrifices --------------------------------------------------------------------------
def treasures(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == f"{pid}:battlefield"]


def cast_choosing(s, name, pid="p1", **answers):
    """Cast the spell and answer what it asks: ``answers`` maps a decision's prompt fragment to the labels to choose."""
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        labels = next((v for k, v in answers.items() if k.replace("_", " ") in d.prompt.lower()), None)
        ids = [o.id for o in d.options if labels is not None and o.label in labels] if labels is not None else [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    raise AssertionError("never settled")


def evin_table(cards):
    s = build(cards, ["Evin, Waterdeep Opportunist", "Barter in Blood", "Village Rites", "Grizzly Bears", "Llanowar Elves"],
              theirs=["Grizzly Bears", "Young Wolf", "Village Rites"], forests=20)
    for name in ("Evin, Waterdeep Opportunist", "Grizzly Bears", "Llanowar Elves"):
        put(s, name)
    put(s, "Grizzly Bears", "p2")
    return s


def test_evin_makes_one_tapped_treasure_when_every_player_sacrifices_creatures_at_once(cards):
    """Barter in Blood: both players sacrifice two creatures in the same event batch: one trigger (603.2c), not one per player."""
    s = evin_table(cards)
    put(s, "Young Wolf", "p2")
    to_hand(s, "Barter in Blood")
    mana(s, B=2, G=2)
    cast_choosing(s, "Barter in Blood", sacrifice_2=["Grizzly Bears", "Llanowar Elves"])
    assert zone(s, "Grizzly Bears") == "p1:graveyard" and zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Evin, Waterdeep Opportunist") == "p1:battlefield"
    assert len(treasures(s)) == 1 and treasures(s)[0].tapped
    check(s)


def test_evin_sees_itself_sacrificed(cards):
    """603.10a: sacrificed with the others, it leaves the battlefield as the event happens and still saw it."""
    s = evin_table(cards)
    to_hand(s, "Barter in Blood")
    mana(s, B=2, G=2)
    cast_choosing(s, "Barter in Blood", sacrifice_2=["Evin, Waterdeep Opportunist", "Llanowar Elves"])
    assert zone(s, "Evin, Waterdeep Opportunist") == "p1:graveyard" and len(treasures(s)) == 1
    check(s)


def test_evin_triggers_when_only_an_opponent_sacrifices(cards):
    s = evin_table(cards)
    to_turn_of(s, "p2")
    to_hand(s, "Village Rites", "p2")
    mana(s, "p2", B=1)
    cast_choosing(s, "Village Rites", "p2")
    assert zone(s, "Grizzly Bears", "p2") == "p2:graveyard" and len(treasures(s)) == 1
    check(s)


def test_evin_triggers_only_once_each_turn(cards):
    s = evin_table(cards)
    to_hand(s, "Village Rites")
    to_hand(s, "Barter in Blood")
    mana(s, B=3, G=2)
    cast_choosing(s, "Village Rites", sacrifice_a_creature=["Llanowar Elves"])
    assert len(treasures(s)) == 1
    cast_choosing(s, "Barter in Blood", sacrifice_2=["Grizzly Bears", "Evin, Waterdeep Opportunist"])
    assert len(treasures(s)) == 1  # (a second batch the same turn: "triggers only once each turn")
    check(s)


def test_evin_is_silent_when_a_creature_merely_dies(cards):
    s = evin_table(cards)
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "Llanowar Elves").id], value=9)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and treasures(s) == []
    check(s)


def kingpin_table(cards):
    s = build(cards, ["Kingpin, Wilson Fisk", "Village Rites", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears", "Village Rites"], forests=20)
    for name in ("Kingpin, Wilson Fisk", "Grizzly Bears", "Llanowar Elves"):
        put(s, name)
    put(s, "Grizzly Bears", "p2")
    return s


def test_kingpin_makes_two_treasures_when_you_sacrifice_another_creature(cards):
    s = kingpin_table(cards)
    to_hand(s, "Village Rites")
    mana(s, B=1)
    cast_choosing(s, "Village Rites", sacrifice_a_creature=["Grizzly Bears"])
    assert zone(s, "Grizzly Bears") == "p1:graveyard" and len(treasures(s)) == 2
    check(s)


def test_kingpin_makes_two_treasures_when_you_sacrifice_it(cards):
    """603.10a: Kingpin sacrificed itself: the trigger looks back at it."""
    s = kingpin_table(cards)
    to_hand(s, "Village Rites")
    mana(s, B=1)
    cast_choosing(s, "Village Rites", sacrifice_a_creature=["Kingpin, Wilson Fisk"])
    assert zone(s, "Kingpin, Wilson Fisk") == "p1:graveyard" and len(treasures(s)) == 2
    check(s)


def test_kingpin_ignores_what_an_opponent_sacrifices(cards):
    s = kingpin_table(cards)
    to_turn_of(s, "p2")
    to_hand(s, "Village Rites", "p2")
    mana(s, "p2", B=1)
    cast_choosing(s, "Village Rites", "p2")
    assert zone(s, "Grizzly Bears", "p2") == "p2:graveyard" and treasures(s) == []
    check(s)


# -- Hostile Investigator: "Whenever one or more players discard one or more cards, investigate" ----------------------------------------------
def clues(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Clue" and c.zone == f"{pid}:battlefield"]


def test_hostile_investigator_investigates_once_when_every_player_discards_at_once(cards):
    """Wheel of Fortune: both players discard their hands in one batch: one event (603.2c), one Clue."""
    s = build(cards, ["Hostile Investigator", "Wheel of Fortune"], theirs=["Grizzly Bears", "Young Wolf"], forests=20)
    put(s, "Hostile Investigator")
    to_hand(s, "Wheel of Fortune")
    to_hand(s, "Grizzly Bears", "p2")
    to_hand(s, "Young Wolf", "p2")
    mana(s, R=1, G=2)
    cast(s, "Wheel of Fortune")
    assert len(clues(s)) == 1
    check(s)


def test_hostile_investigator_is_silent_when_nobody_discards(cards):
    s = build(cards, ["Hostile Investigator", "Opt"], forests=20)
    put(s, "Hostile Investigator")
    to_hand(s, "Opt")
    mana(s, U=1)
    cast(s, "Opt")
    assert clues(s) == []
    check(s)


# -- Magmakin Artillerist: "When you cycle this card, it deals 1 damage to each opponent" ------------------------------------------------------
def test_cycling_magmakin_artillerist_deals_one_damage_to_each_opponent(cards):
    """702.29c: "it" is the cycled card, the source of the damage (a card in the graveyard); the damage is dealt to the opponent."""
    s = build(cards, ["Magmakin Artillerist"], forests=20)
    magmakin = to_hand(s, "Magmakin Artillerist")
    mana(s, R=1, G=1)
    act(s, "p1", type="activate_ability", card_id=magmakin.id, ability=1)
    settle(s)
    assert zone(s, "Magmakin Artillerist") == "p1:graveyard" and s.state.players["p2"].life == 39 and s.state.players["p1"].life == 40
    check(s)


def test_discarding_magmakin_artillerist_without_cycling_it_deals_no_damage(cards):
    s = build(cards, ["Magmakin Artillerist", "Faithless Looting"], forests=20)
    to_hand(s, "Magmakin Artillerist")
    to_hand(s, "Faithless Looting")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Faithless Looting").id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("Magmakin")), next(o.id for o in d.options if o.label == "Forest")])
    settle(s)
    assert zone(s, "Magmakin Artillerist") == "p1:graveyard" and s.state.players["p2"].life == 40
    check(s)


# -- Rielle, the Everwise / Veronica, Dissident Scribe: "for the first time each turn" ----------------------------------------------------------
def looting(s, discard_labels):
    """Cast Faithless Looting (hand or graveyard) and discard the cards with these labels, one card for each label (a repeated label: another card)."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Faithless Looting").id)
    d = s.state.rules.decision
    assert d is not None and d.prompt == "Discard 2 cards"
    ids, left = [], list(d.options)
    for label in discard_labels:
        o = next(o for o in left if o.label == label)
        left.remove(o)
        ids.append(o.id)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
    settle(s)


def rielle_table(cards):
    s = build(cards, ["Rielle, the Everwise", "Faithless Looting", "Llanowar Elves"], forests=20)
    put(s, "Rielle, the Everwise")
    to_hand(s, "Faithless Looting")
    to_hand(s, "Llanowar Elves")  # (so that there is a choice to make)
    mana(s, R=4, G=2)
    return s


def test_rielle_draws_as_many_cards_as_you_discarded_the_first_time_each_turn(cards):
    """Faithless Looting draws two and discards two in one batch: one trigger, drawing that many (2)."""
    s = rielle_table(cards)
    hand = len(s.state.zones["p1:hand"])
    looting(s, ["Forest", "Forest"])
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2 - 2 + 2  # (cast, draw two, discard two, Rielle draws two)
    check(s)


def test_rielle_does_not_draw_for_a_second_discard_the_same_turn(cards):
    s = rielle_table(cards)
    looting(s, ["Forest", "Forest"])
    hand = len(s.state.zones["p1:hand"])
    looting(s, ["Forest", "Forest"])  # (flashback {2}{R}: the second discard of the turn)
    assert len(s.state.zones["p1:hand"]) == hand + 2 - 2  # (draw two, discard two; nothing more)
    check(s)


def test_rielle_draws_again_on_the_next_turn(cards):
    s = rielle_table(cards)
    looting(s, ["Forest", "Forest"])
    to_turn_of(s, "p2")
    to_turn_of(s, "p1")
    mana(s, R=3)
    hand = len(s.state.zones["p1:hand"])
    looting(s, ["Forest", "Forest"])
    assert len(s.state.zones["p1:hand"]) == hand + 2 - 2 + 2
    check(s)


def veronica_table(cards):
    s = build(cards, ["Veronica, Dissident Scribe", "Faithless Looting", "Grizzly Bears", "Llanowar Elves"], forests=20)
    put(s, "Veronica, Dissident Scribe")
    to_hand(s, "Faithless Looting")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Llanowar Elves")
    mana(s, R=4, G=2)
    return s


def junk(s):
    return [c for c in s.state.cards.values() if c.name == "Junk" and c.zone == "p1:battlefield"]


def test_veronica_makes_a_junk_token_for_the_first_nonland_discard_of_the_turn(cards):
    s = veronica_table(cards)
    looting(s, ["Forest", "Forest"])
    assert junk(s) == []  # (two lands: not nonland cards)
    looting(s, ["Grizzly Bears", "Forest"])  # (the first nonland card discarded this turn, though the second discard of the turn)
    assert len(junk(s)) == 1
    check(s)


def test_veronica_makes_a_junk_token_only_the_first_time(cards):
    s = veronica_table(cards)
    looting(s, ["Grizzly Bears", "Forest"])
    assert len(junk(s)) == 1
    looting(s, ["Llanowar Elves", "Forest"])  # (a second nonland discard this turn)
    assert len(junk(s)) == 1
    check(s)


# -- Titanbones, Towering Heart: "When you discard this card" --------------------------------------------------------------------------
def loot(cards, discard):
    s = build(cards, ["Titanbones, Towering Heart", "Faithless Looting"], forests=20)
    to_hand(s, "Titanbones, Towering Heart")
    to_hand(s, "Faithless Looting")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Faithless Looting").id)
    d = s.state.rules.decision
    assert d is not None and d.prompt == "Discard 2 cards"
    titan = next(o.id for o in d.options if o.label.startswith("Titanbones"))
    forests = [o.id for o in d.options if o.label == "Forest"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[titan, forests[0]] if discard else forests[:2])
    settle(s)
    return s


def test_titanbones_gains_three_life_when_it_is_discarded(cards):
    s = loot(cards, discard=True)
    assert zone(s, "Titanbones, Towering Heart") == "p1:graveyard" and s.state.players["p1"].life == 43
    check(s)


def test_titanbones_does_nothing_when_another_card_is_discarded(cards):
    s = loot(cards, discard=False)
    assert zone(s, "Titanbones, Towering Heart") == "p1:hand" and s.state.players["p1"].life == 40
    check(s)


def test_titanbones_does_nothing_when_it_dies_on_the_battlefield(cards):
    s = build(cards, ["Titanbones, Towering Heart"], forests=20)
    put(s, "Titanbones, Towering Heart")
    act(s, "p1", type="move", card_ids=[card_named(s, "Titanbones, Towering Heart").id], to={"zone": "graveyard"})
    settle(s)
    assert s.state.players["p1"].life == 40
    check(s)


# -- Bebop & Rocksteady: "Whenever Bebop & Rocksteady attack or block, sacrifice a permanent unless you discard a card" ----------------------
def bebop_table(cards):
    s = build(cards, ["Bebop & Rocksteady", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Bebop & Rocksteady")
    ready(s, "Bebop & Rocksteady")
    to_hand(s, "Grizzly Bears")
    return s


def test_bebop_and_rocksteady_attacking_asks_to_discard_or_sacrifice(cards):
    s = bebop_table(cards)
    attack(s, card_named(s, "Bebop & Rocksteady"))
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Discard a card", "Don't pay"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:graveyard" and zone(s, "Bebop & Rocksteady") == "p1:battlefield"
    check(s)


def test_bebop_and_rocksteady_declining_sacrifices_a_permanent(cards):
    s = bebop_table(cards)
    put(s, "Llanowar Elves")
    attack(s, card_named(s, "Bebop & Rocksteady"))
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    assert offered(s) == ["Bebop & Rocksteady", "Llanowar Elves"]  # (a permanent of yours: any)
    pick(s, "Llanowar Elves")
    settle(s)
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Bebop & Rocksteady") == "p1:battlefield" and zone(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_bebop_and_rocksteady_blocking_asks_too(cards):
    s = bebop_table(cards)
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], "p1")
    block(s, "p1", (card_named(s, "Bebop & Rocksteady"), card_named(s, "Grizzly Bears", "p2")))
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == ["Discard a card", "Don't pay"]
    check(s)


def test_bebop_and_rocksteady_is_silent_when_it_neither_attacks_nor_blocks(cards):
    s = bebop_table(cards)
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], "p1")
    block(s, "p1")
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_one"
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Bebop & Rocksteady") == "p1:battlefield"
    check(s)


# -- Kitt Kanto, Mayhem Diva: "At the beginning of combat on each player's turn" --------------------------------------------------------
def kitt_table(cards):
    s = build(cards, ["Kitt Kanto, Mayhem Diva", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears"], forests=20)
    for name in ("Kitt Kanto, Mayhem Diva", "Grizzly Bears", "Llanowar Elves"):
        put(s, name)
    put(s, "Grizzly Bears", "p2")
    ready(s, "Kitt Kanto, Mayhem Diva", "Grizzly Bears", "Llanowar Elves")
    ready(s, "Grizzly Bears", pid="p2")
    return s


def goaded(s, name, pid):
    from app.rules.keyword_actions import goaded_by
    from app.rules.plan import Plan

    return goaded_by(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]))


def test_kitt_kanto_triggers_at_the_beginning_of_combat_on_your_own_turn(cards):
    s = kitt_table(cards)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and "pay" in [o.id for o in d.options] and s.state.turn.phase == "begin_combat" and s.state.turn.active_player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    pick(s, "Grizzly Bears", "Llanowar Elves")  # (tapped to pay)
    assert offered(s) == ["Grizzly Bears", "Kitt Kanto, Mayhem Diva", "Llanowar Elves"]  # ("target creature that player controls": that player is you)
    pick(s, "Kitt Kanto, Mayhem Diva")
    resolve_stack(s)
    assert hp(s, "Kitt Kanto, Mayhem Diva") == (5, 5) and goaded(s, "Kitt Kanto, Mayhem Diva", "p1") == {"p1"}
    check(s)


def test_kitt_kanto_triggers_on_an_opponents_turn_too_for_that_players_creature(cards):
    s = kitt_table(cards)
    until(s, lambda s: s.state.rules.decision is not None)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["decline"])  # (your own turn: not now)
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind != "declare_attackers")
    d = s.state.rules.decision
    assert d.player == "p1" and s.state.turn.phase == "begin_combat" and s.state.turn.active_player == "p2"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    pick(s, "Grizzly Bears", "Llanowar Elves")
    assert offered(s) == ["Grizzly Bears"]  # (that player = Bob: his Bears, not yours)
    pick(s, "Grizzly Bears")
    resolve_stack(s)
    assert hp(s, "Grizzly Bears", "p2") == (4, 4) and goaded(s, "Grizzly Bears", "p2") == {"p1"}
    assert hp(s, "Grizzly Bears", "p1") == (2, 2)
    check(s)


def test_kitt_kanto_cannot_pay_without_two_untapped_creatures(cards):
    s = build(cards, ["Kitt Kanto, Mayhem Diva"], forests=20)
    put(s, "Kitt Kanto, Mayhem Diva")
    ready(s, "Kitt Kanto, Mayhem Diva")
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.rules.decision is None  # (one untapped creature, Kitt Kanto itself: the cost of tapping two can't be paid, so nothing is asked)
    check(s)


# -- Baron Strucker, HYDRA Overlord: "Whenever another Villain you control enters, you may have it connive" --------------------------------
def baron_table(cards):
    s = build(cards, ["Baron Strucker, HYDRA Overlord", "Undead Hand Ninja", "Bushmaster, Coiled Henchman", "Grizzly Bears"], forests=20)
    put(s, "Baron Strucker, HYDRA Overlord")
    to_hand(s, "Grizzly Bears")
    mana(s, B=2, G=2)
    return s


def test_baron_strucker_lets_you_have_the_villain_that_entered_connive(cards):
    """701.50a: it draws a card, then discards a card; with a nonland card discarded, a +1/+1 counter goes on that creature."""
    s = baron_table(cards)
    to_hand(s, "Undead Hand Ninja")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Undead Hand Ninja").id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.kind == "confirm" and "connive" in d.prompt.lower()
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    assert d is not None  # (the discard, after the draw)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Grizzly Bears")])
    settle(s)
    ninja = card_named(s, "Undead Hand Ninja")
    assert zone(s, "Grizzly Bears") == "p1:graveyard" and s.state.cards[ninja.id].counters.get("+1/+1", 0) == 1  # (a nonland card was discarded)
    check(s)


def test_baron_strucker_may_decline(cards):
    s = baron_table(cards)
    to_hand(s, "Undead Hand Ninja")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Undead Hand Ninja").id)
    until(s, lambda s: s.state.rules.decision is not None)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["no"])
    settle(s)
    ninja = card_named(s, "Undead Hand Ninja")
    assert len(s.state.zones["p1:hand"]) == hand - 1 and s.state.cards[ninja.id].counters.get("+1/+1", 0) == 0
    check(s)


def test_baron_strucker_ignores_a_creature_that_is_not_a_villain_and_acts_once_each_turn(cards):
    s = baron_table(cards)
    to_hand(s, "Bushmaster, Coiled Henchman")
    to_hand(s, "Undead Hand Ninja")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)  # (not a Villain)
    settle(s)
    assert s.state.rules.decision is None
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Undead Hand Ninja").id)
    until(s, lambda s: s.state.rules.decision is not None)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["no"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bushmaster, Coiled Henchman").id)
    settle(s)
    assert s.state.rules.decision is None and zone(s, "Bushmaster, Coiled Henchman") == "p1:battlefield"  # "Do this only once each turn"
    check(s)


# -- Silas Renn, Seeker Adept: "choose target artifact card in your graveyard. You may cast that card this turn" ------------------------------
def silas_table(cards):
    s = build(cards, ["Silas Renn, Seeker Adept", "Sol Ring", "Arcane Signet", "Grizzly Bears"], forests=20)
    put(s, "Silas Renn, Seeker Adept")
    ready(s, "Silas Renn, Seeker Adept")
    to_gy(s, "Sol Ring")
    to_gy(s, "Grizzly Bears")
    return s


def test_silas_renn_lets_you_cast_the_chosen_artifact_from_the_graveyard_this_turn(cards):
    s = silas_table(cards)
    attack(s, card_named(s, "Silas Renn, Seeker Adept"))
    assert offered(s) == ["Sol Ring"]  # (an artifact card in your graveyard: not the Bears)
    pick(s, "Sol Ring")
    until(s, lambda s: s.state.turn.phase == "main2")
    assert zone(s, "Sol Ring") == "p1:graveyard"  # (chosen, not moved)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sol Ring").id)
    settle(s)
    assert zone(s, "Sol Ring") == "p1:battlefield"
    check(s)


def test_silas_renn_gives_no_permission_to_another_card(cards):
    s = silas_table(cards)
    attack(s, card_named(s, "Silas Renn, Seeker Adept"))
    pick(s, "Sol Ring")
    until(s, lambda s: s.state.turn.phase == "main2")
    mana(s, G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)  # (a creature card in the graveyard: no permission)
    check(s)


# -- Cloud, Ex-SOLDIER: "Then if Cloud has power 7 or greater, create two Treasure tokens" -----------------------------------------------
def cloud_attacks(cards, counters):
    s = build(cards, ["Cloud, Ex-SOLDIER"], forests=20)
    put(s, "Cloud, Ex-SOLDIER")
    if counters:
        act(s, "p1", type="counter", card_ids=[card_named(s, "Cloud, Ex-SOLDIER").id], kind="+1/+1", delta=counters)
    attack(s, card_named(s, "Cloud, Ex-SOLDIER"))
    settle(s)
    return s


def test_cloud_creates_two_treasures_with_power_seven_or_more(cards):
    s = cloud_attacks(cards, 3)  # (4 + 3 = 7)
    assert hp(s, "Cloud, Ex-SOLDIER") == (7, 7) and len(treasures(s)) == 2
    check(s)


def test_cloud_creates_none_with_less_power(cards):
    s = cloud_attacks(cards, 2)  # (6)
    assert hp(s, "Cloud, Ex-SOLDIER") == (6, 6) and treasures(s) == []
    check(s)


def test_kingpin_triggers_only_once_each_turn(cards):
    s = kingpin_table(cards)
    to_hand(s, "Village Rites")
    mana(s, B=1)
    cast_choosing(s, "Village Rites", sacrifice_a_creature=["Grizzly Bears"])
    assert len(treasures(s)) == 2
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"zone": "graveyard"})  # (dies: not a sacrifice)
    c = card_named(s, "Llanowar Elves")
    assert s.state.cards[c.id].zone == "p1:graveyard" and len(treasures(s)) == 2
    check(s)
