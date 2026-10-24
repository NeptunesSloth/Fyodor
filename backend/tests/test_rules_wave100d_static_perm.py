"""Wave 100D: rule-modifying statics and loyalty abilities of permanents (app/rules/static_perm100d.py), real Oracle text,
CR 2026-09-25. Every scenario checks the replay and a save/load round trip.

* Attachment legality: "can be attached only to a creature with power / toughness N or greater" and "can't be equipped" (301.5c,
  701.3b, 704.5n); "You control enchanted artifact creature." (613.1b); "Enchanted Mountain is a 7/7 … It's still a land." (205.1b).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

EXTRA = [
    real('O-Naginata', '{1}', 1, 'Artifact — Equipment', 'This Equipment can be attached only to a creature with power 3 or greater.\nEquipped creature gets +3/+0 and has trample.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)', None, ''),
    real('Gate Smasher', '{3}', 3, 'Artifact — Equipment', 'This Equipment can be attached only to a creature with toughness 4 or greater.\nEquipped creature gets +3/+0 and has trample.\nEquip {3}', None, ''),
    real('Goblin Brawler', '{2}{R}', 3, 'Creature — Goblin Warrior', "First strike\nThis creature can't be equipped.", ("2", "2"), 'R'),
    real('Bonesplitter', '{1}', 1, 'Artifact — Equipment', 'Equipped creature gets +2/+0.\nEquip {1}', None, ''),
    real('Domineer', '{1}{U}{U}', 3, 'Enchantment — Aura', 'Enchant artifact creature\nYou control enchanted artifact creature.', None, 'U'),
    real('Awaken the Ancient', '{1}{R}{R}{R}', 4, 'Enchantment — Aura', "Enchant Mountain\nEnchanted Mountain is a 7/7 red Giant creature with haste. It's still a land.", None, 'R'),
]


def pw(name, cost, cmc, types, text, colors, loyalty):
    return {**real(name, cost, cmc, types, text, None, colors), "loyalty": loyalty}


EXTRA += [
    pw('Gideon, the Oathsworn', '{4}{W}{W}', 6, 'Legendary Planeswalker — Gideon', "Whenever you attack with two or more non-Gideon creatures, put a +1/+1 counter on each of those creatures.\n+2: Until end of turn, Gideon becomes a 5/5 white Soldier creature that's still a planeswalker. Prevent all damage that would be dealt to him this turn. (He can't attack if he was cast this turn.)\n−9: Exile Gideon and each creature your opponents control.", 'W', "4"),
    pw('Dovin, Architect of Law', '{4}{W}{U}', 6, 'Legendary Planeswalker — Dovin', "+1: You gain 2 life and draw a card.\n−1: Tap target creature. It doesn't untap during its controller's next untap step.\n−9: Tap all permanents target opponent controls. That player skips their next untap step.", 'UW', "5"),
    pw('Ajani Unrelenting', '{4}{R}{R}', 6, 'Legendary Planeswalker — Ajani', 'Whenever you activate a loyalty ability, create a 2/2 colorless Wizard Soldier creature token named Cadet.\n+1: Creatures you control get +1/+0 and gain haste until end of turn.\n−2: Discard your hand, then draw a card for each creature you control.\n−3: Ajani deals 4 damage to each creature except for tokens you control.', 'R', "5"),
    pw('Nicol Bolas, Planeswalker', '{4}{U}{B}{B}{R}', 8, 'Legendary Planeswalker — Bolas', "+3: Destroy target noncreature permanent.\n−2: Gain control of target creature.\n−9: Nicol Bolas deals 7 damage to target player or planeswalker. That player or that planeswalker's controller discards seven cards, then sacrifices seven permanents of their choice.", 'BRU', "5"),
    pw('Liliana, the Necromancer', '{3}{B}{B}', 5, 'Legendary Planeswalker — Liliana', '+1: Target player loses 2 life.\n−1: Return target creature card from your graveyard to your hand.\n−7: Destroy up to two target creatures. Put up to two creature cards from graveyards onto the battlefield under your control.', 'B', "4"),
]
EXTRA += [
    real('Replenish', '{3}{W}', 4, 'Sorcery', 'Return all enchantment cards from your graveyard to the battlefield. (Auras with nothing to enchant remain in your graveyard.)', None, 'W'),
    real('Heightened Awareness', '{3}{U}{U}', 5, 'Enchantment', 'As this enchantment enters, discard your hand.\nAt the beginning of your draw step, draw an additional card.', None, 'U'),
    real('Overlaid Terrain', '{2}{G}{G}', 4, 'Enchantment', 'As this enchantment enters, sacrifice all lands you control.\nLands you control have "{T}: Add two mana of any one color."', None, 'G'),
    real("Full Moon's Rise", '{1}{G}', 2, 'Enchantment', 'Werewolf creatures you control get +1/+0 and have trample.\nSacrifice this enchantment: Regenerate all Werewolf creatures you control.', None, 'G'),
]
FULL = ["Heightened Awareness", "Overlaid Terrain", "Full Moon's Rise", "O-Naginata", "Gate Smasher", "Goblin Brawler", "Domineer", "Awaken the Ancient", "Gideon, the Oathsworn", "Dovin, Architect of Law",
        "Ajani Unrelenting", "Nicol Bolas, Planeswalker", "Liliana, the Necromancer"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def equip(s, gear, ability, host, **m):
    mana(s, **m)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=ability, targets=[host.id])
    settle(s)


def sba_check(s):
    """704.3: state-based actions are checked as a player would receive priority (Alice passes; Bob gets it)."""
    act(s, "p1", type="pass_priority")


def attached(s, gear):
    return s.state.cards[gear.id].attached_to


# -- attachment legality (301.5c, 701.3b, 704.5n) -------------------------------------------------------------------------
def test_o_naginata_moves_only_onto_power_three_and_falls_off_below(cards):
    s = build(cards, ["O-Naginata"])
    blade = put(s, "O-Naginata")
    small = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    big = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "3/5")
    equip(s, blade, 2, small, C=2)  # the equip ability may target it (ruling 2020-08-07), but nothing moves (701.3b)
    assert attached(s, blade) is None
    equip(s, blade, 2, big, C=2)
    assert attached(s, blade) == big.id and pt(s, "Ogre") == (6, 5)
    act(s, "p1", type="counter", card_ids=[big.id], kind="-1/-1", delta=3)
    sba_check(s)
    assert attached(s, blade) == big.id  # 3 power with its own +3/+0 (0 + 3): still legal
    act(s, "p1", type="counter", card_ids=[big.id], kind="-1/-1", delta=1)
    sba_check(s)
    assert attached(s, blade) is None  # 704.5n: 2 power, the +3/+0 included, makes it unattached
    assert s.state.cards[blade.id].zone == "p1:battlefield"
    check(s)


def test_gate_smasher_needs_toughness_four(cards):
    s = build(cards, ["Gate Smasher"])
    smasher = put(s, "Gate Smasher")
    low = token_of(s, "p1", "Bear", "Token Creature — Bear", "5/3")
    wall = token_of(s, "p1", "Wall", "Token Creature — Wall", "0/4")
    equip(s, smasher, 2, low, C=3)
    assert attached(s, smasher) is None
    equip(s, smasher, 2, wall, C=3)
    assert attached(s, smasher) == wall.id and pt(s, "Wall") == (3, 4)
    act(s, "p1", type="counter", card_ids=[wall.id], kind="-1/-1", delta=1)
    sba_check(s)
    assert attached(s, smasher) is None  # 704.5n (ruling 2015-02-25)
    check(s)


def test_goblin_brawler_cannot_be_equipped(cards):
    s = build(cards, ["Goblin Brawler", "Bonesplitter"])
    brawler = put(s, "Goblin Brawler")
    splitter = put(s, "Bonesplitter")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    equip(s, splitter, 1, brawler, C=1)  # ruling 2004-12-01: the ability can target it, the Equipment fails to move
    assert attached(s, splitter) is None and pt(s, "Goblin Brawler") == (2, 2)
    equip(s, splitter, 1, bear, C=1)
    assert attached(s, splitter) == bear.id
    check(s)


def test_domineer_steals_an_artifact_creature_only(cards):
    s = build(cards, ["Domineer"])
    golem = token_of(s, "p2", "Golem", "Token Artifact Creature — Golem", "3/3")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    aura = to_hand(s, "Domineer")
    mana(s, U=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])  # 303.4a: enchant artifact creature
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[golem.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == golem.id
    assert s.state.cards[golem.id].controller == "p1" and s.state.cards[bear.id].controller == "p2"  # 613.1b
    check(s)


def test_awaken_the_ancient_animates_a_mountain(cards):
    s = build(cards, ["Awaken the Ancient", "Mountain"])
    mountain = put(s, "Mountain")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    aura = to_hand(s, "Awaken the Ancient")
    mana(s, R=3, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[forest.id])  # Enchant Mountain
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[mountain.id])
    settle(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[mountain.id])
    assert ch.is_creature and ch.is_land and "Mountain" in ch.subtypes and "Giant" in ch.subtypes  # 205.1b: still a land
    assert "haste" in ch.keywords and set(ch.colors) == {"R"}
    assert pt(s, "Mountain") == (7, 7)
    check(s)


# -- loyalty abilities (606) ------------------------------------------------------------------------------------------------
def walker(s, name, loyalty):
    c = put(s, name)
    act(s, "p1", type="set_counter", card_id=c.id, kind="loyalty", value=loyalty)
    return c


def loyal(s, c, ability, targets=()):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability, targets=list(targets))
    settle(s)


def zone(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


@pytest.mark.parametrize("start", [10, 9])
def test_gideon_exiles_himself_and_each_opposing_creature(cards, start):
    s = build(cards, ["Gideon, the Oathsworn"], ["Grizzly Bears", "Sol Ring"])
    gideon = walker(s, "Gideon, the Oathsworn", start)
    mine = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    bears = put(s, "Grizzly Bears", "p2")
    ring = put(s, "Sol Ring", "p2")
    loyal(s, gideon, 2)
    assert zone(s, bears) == "p2:exile" and zone(s, ring) == "p2:battlefield" and zone(s, mine) == "p1:battlefield"
    # 9 loyalty: the cost leaves him with none, so he's put into the graveyard before the ability resolves (704.5i, ruling 2019-05-03)
    assert zone(s, gideon) == ("p1:exile" if start == 10 else "p1:graveyard")
    check(s)


def test_dovin_taps_everything_and_the_opponent_skips_the_untap_step(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Dovin, Architect of Law"], ["Grizzly Bears", "Sol Ring"])
    dovin = walker(s, "Dovin, Architect of Law", 9)
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    loyal(s, dovin, 2, ["p2"])
    assert s.state.cards[bears.id].tapped and s.state.cards[ring.id].tapped and not s.state.cards[forest.id].tapped
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.cards[bears.id].tapped and s.state.cards[ring.id].tapped  # 502.1 skipped (614.10)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.turn.number >= 4)
    assert not s.state.cards[bears.id].tapped  # only the next one
    check(s)


def test_ajani_unrelenting_spares_only_your_tokens(cards):
    s = build(cards, ["Ajani Unrelenting", "Grizzly Bears"])
    ajani = walker(s, "Ajani Unrelenting", 5)
    my_token = token_of(s, "p1", "Ox", "Token Creature — Ox", "5/5")
    my_card = put(s, "Grizzly Bears")
    their_token = token_of(s, "p2", "Elk", "Token Creature — Elk", "5/5")
    loyal(s, ajani, 3)
    cadet = next(c for c in s.state.cards.values() if c.name == "Cadet")  # the trigger resolved first (ruling 2026-08-21): a token of yours
    assert s.state.cards[my_token.id].damage == 0 and s.state.cards[cadet.id].damage == 0
    assert s.state.cards[their_token.id].damage == 4 and zone(s, my_card) == "p1:graveyard"
    check(s)


def test_nicol_bolas_ultimate_discards_then_sacrifices(cards):
    s = build(cards, ["Nicol Bolas, Planeswalker"], ["Grizzly Bears", "Sol Ring"])
    bolas = walker(s, "Nicol Bolas, Planeswalker", 9)
    for name in ("Grizzly Bears", "Sol Ring"):
        put(s, name, "p2")
    for i in range(7):
        token_of(s, "p2", f"Spirit {i}", "Token Creature — Spirit", "1/1")
    act(s, "p2", type="draw", count=9 - len(s.state.zones.get("p2:hand", [])))
    before = s.state.players["p2"].life
    loyal(s, bolas, 2, ["p2"])
    assert s.state.players["p2"].life == before - 7
    assert len(s.state.zones["p2:hand"]) == 2  # seven of the nine cards discarded
    assert len(s.state.zones["p2:battlefield"]) == 2  # seven of the nine permanents sacrificed
    assert zone(s, bolas) == "p1:graveyard"  # (0 loyalty)
    check(s)


def test_liliana_returns_cards_chosen_after_the_destruction(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Liliana, the Necromancer"], ["Grizzly Bears"])
    liliana = walker(s, "Liliana, the Necromancer", 8)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="activate_ability", card_id=liliana.id, ability=2, targets=[bears.id], target_counts=[1])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and bears.id in {o.id for o in d.options}  # the destroyed card is offered (ruling 2018-07-13)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.controller == "p1" and back.owner == "p2"
    check(s)


# -- "As ~ enters, …" (614.1c, 614.12) ----------------------------------------------------------------------------------------
def hand(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:hand", []))


def test_heightened_awareness_discards_the_hand_as_it_enters(cards):
    s = build(cards, ["Heightened Awareness", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears"])
    aura = to_hand(s, "Heightened Awareness")
    others = [to_hand(s, "Grizzly Bears"), to_hand(s, "Sol Ring")]
    theirs = to_hand(s, "Grizzly Bears", "p2")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=aura.id)
    settle(s)
    assert zone(s, aura) == "p1:battlefield"
    assert all(zone(s, c) == "p1:graveyard" for c in others) and not hand(s)
    assert zone(s, theirs) == "p2:hand"
    check(s)


def test_overlaid_terrain_sacrifices_the_lands_before_it_enters(cards):
    s = build(cards, ["Overlaid Terrain"], ["Grizzly Bears"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    terrain = to_hand(s, "Overlaid Terrain")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=terrain.id)
    settle(s)
    assert zone(s, terrain) == "p1:battlefield"
    assert all(zone(s, f) == "p1:graveyard" for f in forests) and zone(s, island) == "p2:battlefield"  # (only yours)
    check(s)


def test_entering_from_the_graveyard_does_it_too(cards):
    s = build(cards, ["Replenish", "Heightened Awareness", "Overlaid Terrain", "Sol Ring"])
    for name in ("Heightened Awareness", "Overlaid Terrain"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    ring = to_hand(s, "Sol Ring")
    spell = to_hand(s, "Replenish")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert zone(s, card_named(s, "Heightened Awareness")) == "p1:battlefield" and zone(s, card_named(s, "Overlaid Terrain")) == "p1:battlefield"
    assert zone(s, ring) == "p1:graveyard" and zone(s, forest) == "p1:graveyard"  # (Wood Elemental's ruling: however it enters)
    check(s)


def test_full_moons_rise_regenerates_every_werewolf(cards):
    s = build(cards, ["Full Moon's Rise", "Murder"])
    rise = put(s, "Full Moon's Rise")
    wolf = token_of(s, "p1", "Wolfman", "Token Creature — Human Werewolf", "2/2")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    assert pt(s, "Wolfman") == (3, 2) and pt(s, "Bear") == (2, 2)
    act(s, "p1", type="activate_ability", card_id=rise.id, ability=1)
    settle(s)
    assert zone(s, rise) == "p1:graveyard" and pt(s, "Wolfman") == (2, 2)  # (the bonus left with it: ruling 2011-09-22)
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[wolf.id])
    settle(s)
    assert zone(s, wolf) == "p1:battlefield" and s.state.cards[wolf.id].tapped  # 701.19a: regenerated
    act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bear.id])
    settle(s)
    assert bear.id not in s.state.cards or zone(s, bear) != "p1:battlefield"  # no shield on a non-Werewolf
    check(s)
