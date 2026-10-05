"""Wave 24B: speed (CR 702.178 max speed, 702.179 start your engines!, 704.5aa), real Oracle text; every scenario checks the replay and a
save and a load.

* 702.179a / 704.5aa: a player who controls a permanent with start your engines! and has no speed gets speed 1.
* 702.179d: whenever one or more opponents lose life during your turn, if your speed is less than 4, it increases by 1; once each turn.
* 702.178a: "Max speed — [Ability]" is "As long as your speed is 4, this object has '[Ability]'"; 702.179e: max speed is speed 4.
* 702.179f: "your speed" is 0 for a player with none.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

ENGINES = ("Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses "
           "life. Max speed is 4.)")
CARDS = [
    ("Nesting Bot", "{W}", "Artifact Creature — Robot", "1", "1",
     f"{ENGINES}\nWhen this creature dies, create a 1/1 colorless Servo artifact creature token.\nMax speed — This creature gets +1/+0."),
    ("Gastal Raider", "{1}{R}", "Creature — Goblin Rogue", "2", "2",
     f"{ENGINES}\nMax speed — This creature gets +1/+1 and has menace."),
    ("Embalmed Ascendant", "{1}{W}{B}", "Creature — Zombie", "1", "2",
     f"{ENGINES}\nWhen this creature enters, create a 2/2 black Zombie creature token.\n"
     "Max speed — Whenever a creature you control dies, each opponent loses 1 life and you gain 1 life."),
    ("Muraganda Raceway", "", "Land", None, None, f"{ENGINES}\n{{T}}: Add {{C}}.\nMax speed — {{T}}: Add {{C}}{{C}}."),
    ("Hazoret, Godseeker", "{1}{R}", "Legendary Creature — God", "5", "3",
     f"Indestructible, haste\n{ENGINES}\n{{1}}, {{T}}: Target creature with power 2 or less can't be blocked this turn.\n"
     "Hazoret can't attack or block unless you have max speed."),
    ("Racers' Scoreboard", "{1}{W}", "Artifact", None, None, f"{ENGINES}\nMax speed — Spells you cast cost {{1}} less to cast."),
    ("The Speed Demon", "{3}{B}{B}", "Legendary Creature — Demon", "5", "5",
     f"Flying, trample\n{ENGINES}\nAt the beginning of your end step, you draw X cards and lose X life, where X is your speed."),
    ("Samut, the Driving Force", "{3}{R}{G}{W}", "Legendary Creature — Human Warrior Cleric", "4", "5",
     f"First strike, vigilance, haste\n{ENGINES}\nOther creatures you control get +X/+0, where X is your speed.\n"
     "Noncreature spells you cast cost {X} less to cast, where X is your speed."),
    ("Momentum Breaker", "{1}{B}", "Enchantment", None, None,
     f"{ENGINES}\nWhen this enchantment enters, each opponent sacrifices a creature or Vehicle of their choice. Each opponent who can't "
     "discards a card.\n{2}, Sacrifice this enchantment: You gain life equal to your speed."),
    ("Leonin Surveyor", "{1}{W}", "Creature — Cat Scout", "2", "2",
     f"{ENGINES}\nDuring your turn, this creature has first strike.\nMax speed — {{3}}, Exile this card from your graveyard: Draw a card."),
    ("Probe Soldier", "{1}{W}", "Creature — Human Soldier", "1", "1", ""),
    ("Probe Relic", "{1}", "Artifact", None, None, "{T}: Add {C}."),
    ("Probe Spell", "{2}", "Sorcery", None, None, "Draw a card."),
    ("Act of Treason", "{2}{R}", "Sorcery", None, None,
     "Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. (It can attack and {T} this turn.)"),
]
EXTRA = [card(n, set_code="t24s", number=f"S{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=[], color_identity=[], oracle_text=text, **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [c[0] for c in CARDS[:9]] + ["Leonin Surveyor"])
def test_the_speed_cards_are_full(name):
    assert level(name) == "FULL", name


def speed(s, pid="p1"):
    return s.state.players[pid].resources.get("speed")


def set_speed(s, n, pid="p1"):
    act(s, pid, type="set_resource", player=pid, key="speed", value=n)


def bolt(s, target, pid="p1"):
    c = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    answer(s)


def test_start_your_engines_gives_speed_1_and_it_rises_once_each_turn(cards):
    s = build(cards, ["Nesting Bot", "Lightning Bolt"], [])
    assert speed(s) is None  # 702.179b: no speed until something sets it
    to_hand(s, "Nesting Bot")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Nesting Bot").id)
    answer(s)
    assert speed(s) == 1 and speed(s, "p2") is None  # 704.5aa
    bolt(s, "p2")
    assert life(s, "p2") == 37 and speed(s) == 2  # 702.179d: an opponent lost life during Alice's turn
    bolt(s, "p2")
    assert speed(s) == 2  # "triggers only once each turn"
    check(s)


def test_a_player_losing_life_on_their_own_turn_does_not_raise_speed(cards):
    s = build(cards, ["Nesting Bot", "Lightning Bolt"], [])
    put(s, "Nesting Bot")
    answer(s)
    bolt(s, "p1")  # (Alice hurts herself: no opponent lost life)
    assert speed(s) == 1
    check(s)


def test_speed_stops_at_max_speed(cards):
    s = build(cards, ["Nesting Bot", "Lightning Bolt"], [])
    put(s, "Nesting Bot")
    set_speed(s, 3)
    bolt(s, "p2")
    assert speed(s) == 4
    check(s)
    s2 = build(cards, ["Nesting Bot", "Lightning Bolt"], [])
    put(s2, "Nesting Bot")
    set_speed(s2, 4)
    bolt(s2, "p2")
    assert speed(s2) == 4


def test_max_speed_static_pump_and_keyword_only_at_speed_4(cards):
    s = build(cards, ["Nesting Bot", "Gastal Raider"], [])
    put(s, "Nesting Bot")
    put(s, "Gastal Raider")
    assert pt(s, "Nesting Bot") == (1, 1) and pt(s, "Gastal Raider") == (2, 2)
    set_speed(s, 3)
    assert pt(s, "Gastal Raider") == (2, 2)
    set_speed(s, 4)
    assert pt(s, "Nesting Bot") == (2, 1) and pt(s, "Gastal Raider") == (3, 3)
    set_speed(s, 2)  # (it lasts only as long as the speed does: 611.3a)
    assert pt(s, "Gastal Raider") == (2, 2)
    check(s)


def test_max_speed_triggered_ability_only_at_speed_4(cards):
    s = build(cards, ["Embalmed Ascendant", "Lightning Bolt"], [])
    to_hand(s, "Embalmed Ascendant")
    mana(s, W=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Embalmed Ascendant").id)
    answer(s)
    zombie = next(c for c in s.state.cards.values() if c.is_token and c.name == "Zombie")
    bolt(s, zombie.id)  # speed 1: nothing happens when the token dies
    assert life(s, "p2") == 40
    set_speed(s, 4)
    z2 = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    asc = card_named(s, "Embalmed Ascendant")
    act(s, "p1", type="cast_spell", card_id=z2.id, targets=[asc.id])
    answer(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 41  # (702.178a: the granted trigger; the Ascendant's own death counts)
    check(s)


def mana_abilities(s, cid):
    from app.rules.plan import Plan

    return [ab.index for ab in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid]).abilities if ab.kind == "mana"]


def test_max_speed_mana_ability(cards):
    s = build(cards, ["Muraganda Raceway"], [])
    land = put(s, "Muraganda Raceway")
    assert len(mana_abilities(s, land.id)) == 1  # (below max speed only the printed {T}: Add {C})
    set_speed(s, 4)
    assert len(mana_abilities(s, land.id)) == 2  # 702.178a: the granted one
    act(s, "p1", type="activate_ability", card_id=land.id, ability=max(mana_abilities(s, land.id)))
    assert s.state.players["p1"].mana.get("C", 0) == 2
    check(s)


def test_cant_attack_or_block_unless_you_have_max_speed(cards):
    s = build(cards, ["Hazoret, Godseeker"], [])
    h = put(s, "Hazoret, Godseeker")
    from app.rules.plan import Plan

    def rules():
        return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[h.id]).imposed

    assert any("cant_attack" in str(r) for r in rules())
    set_speed(s, 4)
    assert not any("cant_attack" in str(r) for r in rules())
    check(s)


def test_cost_reduction_only_at_max_speed(cards):
    s = build(cards, ["Racers' Scoreboard", "Probe Spell"], [])
    put(s, "Racers' Scoreboard")
    c = to_hand(s, "Probe Spell")
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id)  # costs {2}: one mana isn't enough below max speed
    set_speed(s, 4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert zone_of(s, "Probe Spell") == "p1:graveyard"
    check(s)


def test_your_speed_as_a_value(cards):
    s = build(cards, ["Momentum Breaker"], ["Probe Soldier"])
    put(s, "Probe Soldier", "p2")
    mb = to_hand(s, "Momentum Breaker")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=mb.id)
    answer(s)
    assert zone_of(s, "Probe Soldier", "p2") == "p2:graveyard" and speed(s) == 1
    set_speed(s, 3)
    mana(s, G=2)
    act(s, "p1", type="activate_ability", card_id=mb.id, ability=2)
    answer(s)
    assert life(s) == 43 and zone_of(s, "Momentum Breaker") == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("n,works", [(3, False), (4, True)])
def test_max_speed_ability_that_works_from_the_graveyard(cards, n, works):
    """702.178b: the granted ability works from the zone it states: {3}, Exile this card from your graveyard: Draw a card, only at max speed."""
    s = build(cards, ["Leonin Surveyor"], [])
    c = card_named(s, "Leonin Surveyor")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    set_speed(s, n)
    mana(s, G=3)
    hand = len(s.state.zones["p1:hand"])
    ab = next(a.index for a in __import__("app.rules.plan", fromlist=["Plan"]).Plan(s.state, "p1", s.cards, None).ch(
        s.state.cards[c.id]).abilities if a.kind == "activated")
    if works:
        act(s, "p1", type="activate_ability", card_id=c.id, ability=ab)
        answer(s)
        assert len(s.state.zones["p1:hand"]) == hand + 1 and zone_of(s, "Leonin Surveyor") == "p1:exile"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=c.id, ability=ab)
    check(s)


def test_a_player_who_gains_control_of_a_start_your_engines_permanent_gets_speed_1_of_their_own(cards):
    """704.5aa: the controller of the permanent with start your engines! who has no speed gets speed 1 (control, not ownership); Alice's stays."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Nesting Bot"], ["Act of Treason"])
    to_hand(s, "Nesting Bot")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Nesting Bot").id)
    answer(s)
    set_speed(s, 3)
    to_turn(s, 2)
    c = to_hand(s, "Act of Treason", "p2")
    mana(s, "p2", R=1, U=2)
    act(s, "p2", type="cast_spell", card_id=c.id, targets=[card_named(s, "Nesting Bot").id])
    answer(s)
    assert s.state.cards[card_named(s, "Nesting Bot").id].controller == "p2"
    assert speed(s, "p2") == 1 and speed(s) == 3  # (Bob has no max speed with it: Nesting Bot is 1/1 again for him)
    assert pt(s, "Nesting Bot") == (1, 1)
    check(s)


def test_the_speed_trigger_belongs_to_the_active_player_only(cards):
    s = build(cards, ["Nesting Bot", "Lightning Bolt"], ["Nesting Bot"])
    to_hand(s, "Nesting Bot")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Nesting Bot").id)
    answer(s)
    put(s, "Nesting Bot", "p2")
    set_speed(s, 1, "p2")  # (Bob has speed 1 too: an opponent losing life on Alice's turn raises Alice's speed, never Bob's)
    bolt(s, "p2")
    assert speed(s) == 2 and speed(s, "p2") == 1
    check(s)
