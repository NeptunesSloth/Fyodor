"""Wave 24B: soulbond (CR 702.95), real Oracle text; every scenario checks the replay and a save and a load.

* 702.95a: two triggered abilities, "may pair" when it enters / when another creature you control enters, if both are unpaired.
* 702.95b/d: paired creatures; a creature is in one pair only. 702.95c: both must still be creatures you control as it resolves.
* 702.95e: a pair ends when a creature leaves the battlefield or another player gains control of one.
* "As long as this creature is paired with another creature, each of those creatures gets +4/+4": a static of the pair.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

SB = "Soulbond (You may pair this creature with another unpaired creature when either enters. They remain paired for as long as you control both of them.)"
CARDS = [
    ("Wolfir Silverheart", "{3}{G}{G}", "Creature — Wolf Warrior", "4", "4",
     f"{SB}\nAs long as this creature is paired with another creature, each of those creatures gets +4/+4."),
    ("Nightshade Peddler", "{1}{G}", "Creature — Human Druid", "1", "1",
     f"{SB}\nAs long as this creature is paired with another creature, both creatures have deathtouch."),
    ("Doom Weaver", "{4}{B}{B}", "Creature — Spider Horror", "1", "8",
     f"Reach\n{SB}\nAs long as Doom Weaver is paired with another creature, each of those creatures has "
     "\"When this creature dies, draw cards equal to its power.\""),
    ("Probe Soldier", "{1}{W}", "Creature — Human Soldier", "1", "1", ""),
    ("Probe Knight", "{1}{W}", "Creature — Human Knight", "2", "2", ""),
    ("Act of Treason", "{2}{R}", "Sorcery", None, None,
     "Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. (It can attack and "
     "{T} this turn.)"),
]
EXTRA = [card(n, set_code="t24p", number=f"P{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
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


@pytest.mark.parametrize("name", [c[0] for c in CARDS[:3]])
def test_the_soulbond_cards_are_full(name):
    assert level(name) == "FULL", name


def cast(s, name, **m):
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def pairs(s):
    return dict(s.state.rules.pairs)


def test_it_pairs_when_it_enters_and_the_pair_gets_the_bonus(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier"], [])
    put(s, "Probe Soldier")
    cast(s, "Wolfir Silverheart", G=5)
    answer(s, "yes")  # 702.95a: "you may pair"
    assert len(pairs(s)) == 2
    assert pt(s, "Wolfir Silverheart") == (8, 8) and pt(s, "Probe Soldier") == (5, 5)
    check(s)


def test_declining_leaves_both_unpaired(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier"], [])
    put(s, "Probe Soldier")
    cast(s, "Wolfir Silverheart", G=5)
    answer(s, "no")
    assert not pairs(s) and pt(s, "Wolfir Silverheart") == (4, 4)
    check(s)


def test_a_creature_entering_later_pairs_with_the_unpaired_soulbond_creature(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier"], [])
    cast(s, "Wolfir Silverheart", G=5)
    answer(s)  # (alone: nothing to pair with, no trigger)
    assert not pairs(s)
    cast(s, "Probe Soldier", W=1, G=1)
    answer(s, "yes")  # 702.95a: "whenever another creature you control enters"
    assert pt(s, "Probe Soldier") == (5, 5) and len(pairs(s)) == 2
    check(s)


def test_an_already_paired_creature_isnt_paired_again(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier", "Probe Knight"], [])
    put(s, "Probe Soldier")
    cast(s, "Wolfir Silverheart", G=5)
    answer(s, "yes")
    cast(s, "Probe Knight", W=1, G=1)
    answer(s)  # 702.95d: both of the pair are paired already: no trigger, no question
    assert len(pairs(s)) == 2 and pt(s, "Probe Knight") == (2, 2)
    check(s)


def test_the_choice_when_several_creatures_could_be_paired(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier", "Probe Knight"], [])
    put(s, "Probe Soldier")
    knight = put(s, "Probe Knight")
    cast(s, "Wolfir Silverheart", G=5)
    answer(s, "yes", knight.id)
    assert pt(s, "Probe Knight") == (6, 6) and pt(s, "Probe Soldier") == (1, 1)
    check(s)


def test_the_pair_ends_when_a_creature_leaves_and_the_bonus_ends(cards):
    s = build(cards, ["Wolfir Silverheart", "Probe Soldier", "Probe Knight", "Lightning Bolt"], [])
    put(s, "Probe Soldier")
    wolfir = cast(s, "Wolfir Silverheart", G=5)
    answer(s, "yes")
    soldier = card_named(s, "Probe Soldier")
    act(s, "p1", type="move", card_ids=[soldier.id], to={"zone": "graveyard"})
    cast(s, "Probe Knight", W=1, G=1)  # (the engine acts: the pair is looked at before triggers)
    answer(s, "no")
    assert zone_of(s, "Probe Soldier") == "p1:graveyard" and not pairs(s)  # 702.95e: it left the battlefield
    assert pt(s, "Wolfir Silverheart") == (4, 4)
    assert pt(s, "Wolfir Silverheart") == (4, 4) and wolfir.id in s.state.cards
    check(s)


def test_the_pair_ends_when_another_player_gains_control(cards):
    from tests.test_rules_conditionals import to_turn

    s = build(cards, ["Wolfir Silverheart", "Probe Soldier"], ["Act of Treason"])
    put(s, "Probe Soldier")
    cast(s, "Wolfir Silverheart", G=5)
    answer(s, "yes")
    to_turn(s, 2)
    c = to_hand(s, "Act of Treason", "p2")
    mana(s, "p2", R=1, U=2)
    act(s, "p2", type="cast_spell", card_id=c.id, targets=[card_named(s, "Probe Soldier").id])
    answer(s)
    assert s.state.cards[card_named(s, "Probe Soldier").id].controller == "p2"
    assert not pairs(s)  # 702.95e: another player gained control of one of them
    assert pt(s, "Wolfir Silverheart") == (4, 4)
    check(s)


def test_a_paired_creature_gets_the_other_ones_granted_keyword(cards):
    s = build(cards, ["Nightshade Peddler", "Probe Soldier"], [])
    put(s, "Probe Soldier")
    cast(s, "Nightshade Peddler", G=1, W=1)
    answer(s, "yes")
    from app.rules.plan import Plan

    def kws(name):
        return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name)).keywords

    assert "deathtouch" in kws("Probe Soldier") and "deathtouch" in kws("Nightshade Peddler")
    check(s)


def test_a_quoted_ability_granted_to_the_pair_triggers_for_the_partner_dying(cards):
    s = build(cards, ["Doom Weaver", "Probe Knight", "Lightning Bolt"], [])
    put(s, "Probe Knight")
    cast(s, "Doom Weaver", B=2, G=4)
    answer(s, "yes")
    hand = len(s.state.zones["p1:hand"])
    c = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[card_named(s, "Probe Knight").id])
    answer(s)
    assert zone_of(s, "Probe Knight") == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + 2  # the Bolt left the hand again; two cards drawn: "draw cards equal to its power" (2)
    check(s)
