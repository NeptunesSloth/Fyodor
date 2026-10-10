"""Wave 23D: Gift (CR 702.174), real Oracle text; every scenario checks the replay and a save and a load.

* 702.174a: "You may promise an opponent a gift as you cast this spell" is an optional additional cost announced with the cast
  (``optional_costs``); 702.174j: on an instant or sorcery the gift happens before the spell's other effects; 702.174k: a promised
  gift is what "If the gift was promised" reads; 702.174b: on a permanent the gift is an enters trigger.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

CARDS = [
    ("Into the Flood Maw", "{U}", "Instant", None, None,
     "Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature "
     "token before its other effects.)\nReturn target creature an opponent controls to its owner's hand. If the gift was promised, instead "
     "return target nonland permanent an opponent controls to its owner's hand."),
    ("Blooming Blast", "{1}{R}", "Instant", None, None,
     "Gift a Treasure (You may promise an opponent a gift as you cast this spell. If you do, they create a Treasure token before its other "
     "effects. It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nBlooming Blast deals 2 damage to target "
     "creature. If the gift was promised, Blooming Blast also deals 3 damage to that creature's controller."),
    ("Wear Down", "{1}{G}", "Sorcery", None, None,
     "Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\n"
     "Destroy target artifact or enchantment. If the gift was promised, instead destroy two target artifacts and/or enchantments."),
    ("Scrapshooter", "{1}{G}{G}", "Creature — Raccoon Archer", "4", "4",
     "Gift a card (You may promise an opponent a gift as you cast this spell. If you do, when it enters, they draw a card.)\nReach\n"
     "When this creature enters, if the gift was promised, destroy target artifact or enchantment an opponent controls."),
    ("Probe Counter", "{U}{U}", "Instant", None, None, "Counter target spell."),
    ("Starforged Sword", "{4}", "Artifact — Equipment", None, None,
     "Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, when it enters, they create a tapped 1/1 blue Fish creature token.)\n"
     "When this Equipment enters, if the gift was promised, attach this Equipment to target creature you control.\n"
     "Equipped creature gets +3/+3 and loses flying.\nEquip {3}"),
    ("Coiling Rebirth", "{3}{B}{B}", "Sorcery", None, None,
     "Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\n"
     "Return target creature card from your graveyard to the battlefield. Then if the gift was promised and that creature isn't legendary, "
     "create a token that's a copy of that creature, except it's 1/1."),
    ("Probe Relic", "{1}", "Artifact", None, None, "{T}: Add {C}."),
    ("Probe Totem", "{1}", "Artifact", None, None, "{T}: Add {C}."),
    ("Probe Soldier", "{1}{W}", "Creature — Human Soldier", "1", "1", ""),
]
EXTRA = [card(n, set_code="t23g", number=f"G{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
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


@pytest.mark.parametrize("name", [c[0] for c in CARDS[:4]] + ["Starforged Sword", "Coiling Rebirth"])
def test_the_gift_cards_are_full(name):
    assert level(name) == "FULL", name


def cast(s, name, *picks, gift=False, **kw):
    """Cast ``name`` (promising the gift when ``gift``), answering each decision from ``picks`` else with its first option."""
    c = card_named(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"] if gift else [], **kw)
    answer(s, *picks)


def fish(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Fish" and c.controller == "p2"]


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


@pytest.mark.parametrize("gift", [False, True])
def test_into_the_flood_maw_promised_gift_gives_a_fish_and_widens_the_target(cards, gift):
    s = build(cards, ["Into the Flood Maw"], ["Probe Soldier", "Probe Relic"])
    soldier = put(s, "Probe Soldier", "p2")
    relic = put(s, "Probe Relic", "p2")
    to_hand(s, "Into the Flood Maw")
    mana(s, U=1)
    if not gift:  # a creature only (the artifact is no creature)
        with pytest.raises(ActionError):
            cast(s, "Into the Flood Maw", targets=[relic.id], target_counts=[1, 0])
        cast(s, "Into the Flood Maw", targets=[soldier.id], target_counts=[1, 0])
        assert zone_of(s, "Probe Soldier", "p2") == "p2:hand" and not fish(s)
    else:
        cast(s, "Into the Flood Maw", gift=True, targets=[relic.id], target_counts=[0, 1])  # 702.174m: the promised spell takes the wider target
        assert zone_of(s, "Probe Relic", "p2") == "p2:hand" and len(fish(s)) == 1 and fish(s)[0].tapped  # (702.174f)
    check(s)


def test_gift_happens_before_the_spells_other_effects(cards):
    """Blooming Blast: Bob gets a Treasure, then 2 damage to the creature and 3 to its controller (702.174j)."""
    s = build(cards, ["Blooming Blast"], ["Probe Soldier"])
    soldier = put(s, "Probe Soldier", "p2")
    to_hand(s, "Blooming Blast")
    mana(s, R=2)
    cast(s, "Blooming Blast", gift=True, targets=[soldier.id])
    assert zone_of(s, "Probe Soldier", "p2") == "p2:graveyard" and life(s, "p2") == 37
    treasure = [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure"]
    assert len(treasure) == 1 and treasure[0].controller == "p2"
    check(s)


def test_an_unpromised_gift_gives_nothing(cards):
    s = build(cards, ["Blooming Blast"], ["Probe Soldier"])
    soldier = put(s, "Probe Soldier", "p2")
    to_hand(s, "Blooming Blast")
    mana(s, R=2)
    cast(s, "Blooming Blast", targets=[soldier.id])
    assert life(s, "p2") == 40 and not [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure"]
    check(s)


def test_a_countered_spell_gives_no_gift(cards):
    """702.174j: if the spell is countered before resolving, the gift effect doesn't happen (it is part of the spell's resolution)."""
    s = build(cards, ["Blooming Blast"], ["Probe Soldier", "Probe Counter"])
    soldier = put(s, "Probe Soldier", "p2")
    c = to_hand(s, "Blooming Blast")
    counter = to_hand(s, "Probe Counter", "p2")
    mana(s, R=2)
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"], targets=[soldier.id])
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[c.id])  # (Bob has priority once the spell is on the stack)
    answer(s)
    assert zone_of(s, "Blooming Blast") == "p1:graveyard" and life(s, "p2") == 40
    assert not [x for x in s.state.cards.values() if x.is_token and x.name == "Treasure"]
    check(s)


@pytest.mark.parametrize("gift,expected", [(False, 1), (True, 2)])
def test_wear_down_chooses_two_targets_only_when_the_gift_was_promised(cards, gift, expected):
    s = build(cards, ["Wear Down"], ["Probe Relic", "Probe Totem"])
    relic, totem = put(s, "Probe Relic", "p2"), put(s, "Probe Totem", "p2")
    to_hand(s, "Wear Down")
    mana(s, G=2)
    bob_hand = hand(s, "p2")
    cast(s, "Wear Down", gift=gift, targets=[relic.id, totem.id][:expected], target_counts=[1, 0] if not gift else [0, 2])
    gone = [n for n in ("Probe Relic", "Probe Totem") if zone_of(s, n, "p2") == "p2:graveyard"]
    assert len(gone) == expected and hand(s, "p2") == bob_hand + (1 if gift else 0)
    check(s)


def test_with_several_opponents_the_caster_names_who_gets_the_gift(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    def side(commander, names):
        return deck(cards, commander, [*((1, n) for n in names), (10, "Island")])

    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=side("Krenko, Mob Boss", ["Wear Down"])),
                                     PlayerSetup("Bob", cards=side("Atraxa, Praetors' Voice", ["Probe Relic", "Probe Totem"])),
                                     PlayerSetup("Cy", cards=side("Krenko, Mob Boss", [""][:0]))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    relic, totem = put(s, "Probe Relic", "p2"), put(s, "Probe Totem", "p2")
    c = to_hand(s, "Wear Down")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"], targets=[relic.id, totem.id], target_counts=[0, 2])
    d = s.state.rules.decision
    assert d.kind == "choose_one" and {o.id for o in d.options} == {"p2", "p3"} and "gift" in d.prompt.lower()
    p3_hand = hand(s, "p3")
    answer(s, "p3")
    assert hand(s, "p3") == p3_hand + 1  # (the gift went to Cy, not to Bob)
    check(s)


@pytest.mark.parametrize("gift", [True, False])
def test_a_permanent_with_gift_gives_it_when_it_enters(cards, gift):
    s = build(cards, ["Scrapshooter"], ["Probe Relic"])
    relic = put(s, "Probe Relic", "p2")
    to_hand(s, "Scrapshooter")
    mana(s, G=3)
    bob_hand = hand(s, "p2")
    cast(s, "Scrapshooter", gift=gift, targets=[])
    assert zone_of(s, "Scrapshooter") == "p1:battlefield"
    assert hand(s, "p2") == bob_hand + (1 if gift else 0)
    assert zone_of(s, "Probe Relic", "p2") == ("p2:graveyard" if gift else "p2:battlefield")
    assert relic.id in s.state.cards
    check(s)


def test_starforged_sword_attaches_when_it_enters_with_a_promised_gift(cards):
    s = build(cards, ["Starforged Sword", "Probe Soldier"], [])
    soldier = put(s, "Probe Soldier")
    to_hand(s, "Starforged Sword")
    mana(s, G=4)
    cast(s, "Starforged Sword", gift=True, targets=[soldier.id])
    assert s.state.cards[card_named(s, "Starforged Sword").id].attached_to == soldier.id and len(fish(s)) == 1
    check(s)


@pytest.mark.parametrize("gift,tokens", [(True, 1), (False, 0)])
def test_coiling_rebirth_copies_only_when_promised(cards, gift, tokens):
    s = build(cards, ["Coiling Rebirth", "Probe Soldier"], [])
    soldier = put(s, "Probe Soldier")
    act(s, "p1", type="move", card_ids=[soldier.id], to={"zone": "graveyard"})
    to_hand(s, "Coiling Rebirth")
    mana(s, B=5)
    cast(s, "Coiling Rebirth", gift=gift, targets=[soldier.id])
    assert zone_of(s, "Probe Soldier") == "p1:battlefield"
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Probe Soldier"]) == tokens
    check(s)
