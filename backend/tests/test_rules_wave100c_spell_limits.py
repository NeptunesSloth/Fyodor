"""Wave 100C: loyalty-ability counters, convoke kin and a one-more-spell limit (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 606.3: a loyalty ability is an activated ability with a loyalty cost; only such an ability of a planeswalker is a legal target.
* 702.51a: the creatures that convoked the spell; "share a creature type" (205.3m).
* 101.2: "You can cast only one more spell this turn".
* 701.67a: "unless you waterbend {2}": each artifact or creature tapped pays {1}. 608.2d: "your choice of" as it resolves.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
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
    settle,
    start_cast,
    to_phase,
    walker,
    zone,
)

PROMOTED = ["Verdant Command", "Everything Comes to Dust", "Irencrag Feat", "Waterbending Lesson", "Mercurial Transformation", "Burning of Xinye",
            "Split the Party", "Dreams of Steel and Oil", "Treacherous Urge", "Pox",
            "Omen of Fire", "Sway of the Stars", "Energybending", "Embiggen",
            "Eliminate the Impossible", "Aura Barbs", "Baki's Curse", "Pollen Lullaby",
            "Metamorphose", "Rite of Ruin"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_verdant_command_counters_a_loyalty_ability_but_not_another_activated_one(cards):
    """Verdant Command (modes 2 and 4): Liliana's +1 is countered (nobody discards), Bob gains 3. Merfolk Looter's ability can't be targeted."""
    s = build(cards, ["Verdant Command", "Liliana of the Veil", "Merfolk Looter"], [])
    lili, looter = walker(s, "Liliana of the Veil"), put_on(s, "Merfolk Looter")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    looting = s.state.zones["stack"][-1]
    with pytest.raises(ActionError):
        start_cast(s, "Verdant Command", targets=[looting, "p2"], modes=[1, 3], G=1, C=1)
    settle(s)
    move(s, one(s, "Verdant Command"), "hand")  # (the looting may have discarded it)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    act(s, "p1", type="activate_ability", card_id=lili.id, ability=0)
    plus = s.state.zones["stack"][-1]
    cast(s, "Verdant Command", targets=[plus, "p2"], modes=[1, 3], G=1, C=1)
    assert len(s.state.zones["p2:hand"]) == hands["p2"] and len(s.state.zones["p1:hand"]) == hands["p1"] - 1  # (only Verdant Command left it)
    assert life(s, "p2") == 43
    check(s)


def test_everything_comes_to_dust_spares_creatures_sharing_a_type_with_a_convoker(cards):
    """Alice's Grizzly Bears convokes: Bob's Grizzly Bears (a Bear) stays with it; Bob's Llanowar Elves, Alice's Sol Ring and Holy Strength go."""
    s = build(cards, ["Everything Comes to Dust", "Grizzly Bears", "Sol Ring", "Holy Strength"], ["Grizzly Bears", "Llanowar Elves"])
    bear, theirs, elves = put_on(s, "Grizzly Bears"), put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
    ring, strength = put_on(s, "Sol Ring"), put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[strength.id], to=bear.id)
    spell = move(s, one(s, "Everything Comes to Dust"), "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 3, "C": 6})
    act(s, "p1", type="cast_spell", card_id=spell.id, contributions=[{"kind": "convoke", "card": bear.id}])
    settle(s)
    assert zone(s, bear) == "p1:battlefield" and zone(s, theirs) == "p2:battlefield" and zone(s, elves) == "p2:exile"
    assert zone(s, ring) == "p1:exile" and zone(s, strength) == "p1:exile"
    check(s)


def test_irencrag_feat_adds_seven_red_then_allows_one_more_spell(cards):
    s = build(cards, ["Irencrag Feat", "Lightning Bolt", "Opt"], [])
    cast(s, "Irencrag Feat", R=3, C=1)
    me = s.state.players["p1"]
    assert me.mana.get("R", 0) + sum(1 for u in me.mana_units if u.sym == "R") == 7
    cast(s, "Lightning Bolt", targets=["p2"])
    with pytest.raises(ActionError):
        start_cast(s, "Opt", U=1)
    check(s)


@pytest.mark.parametrize("bend", [True, False])
def test_waterbending_lesson_discards_unless_you_waterbend(cards, bend):
    """Waterbending Lesson: Alice draws three; she waterbends {2} by tapping Grizzly Bears and Sol Ring (no discard), or declines (discards one)."""
    s = build(cards, ["Waterbending Lesson", "Grizzly Bears", "Sol Ring"], [])
    bear, ring = put_on(s, "Grizzly Bears"), put_on(s, "Sol Ring")
    move(s, one(s, "Waterbending Lesson"), "hand")
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Waterbending Lesson", prefer=["pay", bear.id, ring.id] if bend else ["decline"], U=1, C=3)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 3 - (0 if bend else 1)
    assert s.state.cards[bear.id].tapped is bend and s.state.cards[ring.id].tapped is bend
    check(s)


@pytest.mark.parametrize(("form", "pt"), [("Frog 1/1", (1, 1)), ("Octopus 4/4", (4, 4))])
def test_mercurial_transformation_becomes_the_chosen_creature_without_abilities(cards, form, pt):
    s = build(cards, ["Mercurial Transformation"], ["Sol Ring"])
    ring = put_on(s, "Sol Ring", "p2")
    cast(s, "Mercurial Transformation", targets=[ring.id], prefer=[form], U=1, C=1)
    ch = chars(s, ring)
    assert pt_of(s, ring) == pt and ch.is_creature and form.split()[0] in ch.subtypes and ch.colors == {"U"} and not ch.abilities
    check(s)


def test_burning_of_xinye_you_then_the_opponent_destroy_four_lands_then_four_damage(cards):
    """Alice destroys four of her five lands (her choice), Bob his only two; then 4 damage to each creature."""
    s = build(cards, ["Burning of Xinye", "Hulking Cyclops"], [])
    mine = [move(s, c, "battlefield") for c in named(s, "Forest")[:5]]
    theirs = [move(s, c, "battlefield") for c in named(s, "Island", "p2")[:2]]
    cyclops = put_on(s, "Hulking Cyclops")
    cast(s, "Burning of Xinye", targets=["p2"], prefer=[c.id for c in mine[1:]], R=2, C=4)
    assert [zone(s, c) for c in mine] == ["p1:battlefield"] + ["p1:graveyard"] * 4
    assert all(zone(s, c) == "p2:graveyard" for c in theirs) and s.state.cards[cyclops.id].damage == 4
    check(s)


def test_split_the_party_alice_returns_half_of_bobs_creatures_rounded_up(cards):
    """Bob controls three creatures: Alice chooses two (Grizzly Bears, Llanowar Elves) to return; Benalish Hero stays."""
    s = build(cards, ["Split the Party"], ["Grizzly Bears", "Llanowar Elves", "Benalish Hero"])
    bear, elves, hero = (put_on(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Benalish Hero"))
    cast(s, "Split the Party", targets=["p2"], prefer=[bear.id, elves.id], U=2, C=3)
    assert zone(s, bear) == "p2:hand" and zone(s, elves) == "p2:hand" and zone(s, hero) == "p2:battlefield"
    check(s)


def test_dreams_of_steel_and_oil_exiles_one_card_from_the_hand_and_one_from_the_graveyard(cards):
    s = build(cards, ["Dreams of Steel and Oil"], ["Sol Ring", "Grizzly Bears", "Opt"])
    ring, bear = move(s, one(s, "Sol Ring", "p2"), "hand"), move(s, one(s, "Grizzly Bears", "p2"), "graveyard")
    opt = move(s, one(s, "Opt", "p2"), "hand")
    cast(s, "Dreams of Steel and Oil", targets=["p2"], prefer=[ring.id, bear.id], B=1)
    assert zone(s, ring) == "p2:exile" and zone(s, bear) == "p2:exile" and zone(s, opt) == "p2:hand"
    check(s)


def test_treacherous_urge_steals_a_creature_from_the_hand_with_haste_until_the_end_step(cards):
    s = build(cards, ["Treacherous Urge"], ["Grizzly Bears"])
    bear = move(s, one(s, "Grizzly Bears", "p2"), "hand")
    cast(s, "Treacherous Urge", targets=["p2"], prefer=[bear.id], B=1, C=4)
    assert zone(s, bear) == "p1:battlefield" and "haste" in chars(s, bear).keywords
    act(s, "p1", type="set_stops", own=["end"], others=[], smart_pass=False)
    to_phase(s, "end", turn=1)
    settle(s)
    assert zone(s, bear) == "p2:graveyard"
    check(s)



def hand_of(s, pid, names=(), basics=0):
    """Empty ``pid``'s hand into the library, then put those cards (and some basic lands) in it."""
    for c in list(s.state.zones[f"{pid}:hand"]):
        move(s, s.state.cards[c], "library")
    basic = "Forest" if pid == "p1" else "Island"
    for c in [one(s, n, pid) for n in names] + [c for c in named(s, basic, pid) if c.zone.endswith(":library")][:basics]:
        move(s, c, "hand")


def test_pox_each_player_loses_a_third_of_everything_rounded_up(cards):
    """Alice: 40 life, four cards, two creatures, four lands. Bob: 10 life, two cards, no creature, three lands. Thirds rounded up: Alice loses 14,
    discards 2, sacrifices 1 creature and 2 lands; Bob loses 4, discards 1, sacrifices 1 land."""
    s = build(cards, ["Pox", "Grizzly Bears", "Llanowar Elves"], [])
    bear, elves = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves")
    forests = [move(s, c, "battlefield") for c in named(s, "Forest")[:4]]
    islands = [move(s, c, "battlefield") for c in named(s, "Island", "p2")[:3]]
    act(s, "p2", type="set_life", player="p2", value=10)
    hand_of(s, "p1", ["Pox"], 4)
    hand_of(s, "p2", (), 2)
    cast(s, "Pox", B=3)
    assert life(s) == 26 and life(s, "p2") == 6
    assert len(s.state.zones["p1:hand"]) == 2 and len(s.state.zones["p2:hand"]) == 1
    assert sorted(zone(s, c) for c in (bear, elves)) == ["p1:battlefield", "p1:graveyard"]
    assert [zone(s, c) for c in forests].count("p1:graveyard") == 2 and [zone(s, c) for c in islands].count("p2:graveyard") == 1
    check(s)


def test_omen_of_fire_bounces_islands_then_each_player_sacrifices_per_white_permanent(cards):
    """Alice controls one white permanent (Holy Strength on her creature) and a Plains: she sacrifices the Plains (her choice); Bob's only
    white permanent is Benalish Hero, which he sacrifices. Bob's Island returns to his hand."""
    s = build(cards, ["Omen of Fire", "Plains", "Holy Strength", "Grizzly Bears"], ["Benalish Hero"])
    bear, strength, plains = put_on(s, "Grizzly Bears"), put_on(s, "Holy Strength"), put_on(s, "Plains")
    act(s, "p1", type="attach", card_ids=[strength.id], to=bear.id)
    island, hero = move(s, named(s, "Island", "p2")[0], "battlefield"), put_on(s, "Benalish Hero", "p2")
    cast(s, "Omen of Fire", prefer=[plains.id], R=2, C=3)
    assert zone(s, island) == "p2:hand" and zone(s, plains) == "p1:graveyard" and zone(s, strength) == "p1:battlefield"
    assert zone(s, hero) == "p2:graveyard"
    check(s)


def test_sway_of_the_stars_resets_both_players(cards):
    """Everything each player owns on the battlefield (Bob's Sol Ring under Alice's control goes to Bob's library), their hands and graveyards
    are shuffled in; each draws seven; both life totals become 7."""
    s = build(cards, ["Sway of the Stars", "Grizzly Bears", "Opt"], ["Sol Ring"])
    bear, opt = put_on(s, "Grizzly Bears"), move(s, one(s, "Opt"), "graveyard")
    ring = one(s, "Sol Ring", "p2")
    act(s, "p2", type="move", card_ids=[ring.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Sway of the Stars", U=2, C=8)
    assert not s.state.zones.get("p1:battlefield") and not s.state.zones.get("p2:battlefield")
    assert zone(s, bear) in ("p1:library", "p1:hand") and zone(s, opt) in ("p1:library", "p1:hand") and zone(s, ring) in ("p2:library", "p2:hand")
    assert len(s.state.zones["p1:hand"]) == 7 and len(s.state.zones["p2:hand"]) == 7 and life(s) == 7 and life(s, "p2") == 7
    check(s)


def test_energybending_gives_your_lands_every_basic_land_type_this_turn(cards):
    """Alice's Forest is also a Plains, Island, Swamp and Mountain (with their mana abilities, 305.6) this turn; Bob's Island is not; then a draw."""
    s = build(cards, ["Energybending"], [])
    forest, island = move(s, named(s, "Forest")[0], "battlefield"), move(s, named(s, "Island", "p2")[0], "battlefield")
    library = len(s.state.zones["p1:library"])
    cast(s, "Energybending", G=1, C=1)
    basics = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    assert basics <= chars(s, forest).subtypes and chars(s, island).subtypes == {"Island"}
    assert len([a for a in chars(s, forest).abilities if a.kind == "mana"]) == 5 and len(s.state.zones["p1:library"]) == library - 2
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    to_phase(s, "main1", turn=2)
    assert chars(s, forest).subtypes == {"Forest"}
    check(s)


def test_embiggen_counts_supertypes_card_types_and_subtypes(cards):
    """Sliver Queen (Legendary Creature — Sliver: three) becomes 10/10 this turn."""
    s = build(cards, ["Embiggen", "Sliver Queen"], [])
    queen = put_on(s, "Sliver Queen")
    cast(s, "Embiggen", targets=[queen.id], G=1)
    assert pt_of(s, queen) == (10, 10)
    check(s)


def test_eliminate_the_impossible_investigates_shrinks_and_unsuspects_opponents_creatures(cards):
    """Bob's Grizzly Bears is suspected first (Reasonable Doubt on Alice's own Opt): Eliminate the Impossible gives Alice a Clue, the bear
    -2/-0 and it is no longer suspected (it may block again, 701.60c)."""
    s = build(cards, ["Eliminate the Impossible", "Reasonable Doubt", "Opt"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    opt = start_cast(s, "Opt", U=1)
    cast(s, "Reasonable Doubt", targets=[opt.id, bear.id], target_counts=[1, 1], prefer=["decline"], U=1, C=1)
    assert "menace" in chars(s, bear).keywords
    cast(s, "Eliminate the Impossible", U=1, C=1)
    assert pt_of(s, bear) == (0, 2) and "menace" not in chars(s, bear).keywords
    assert [c.controller for c in s.state.cards.values() if c.name == "Clue" and c.zone.endswith(":battlefield")] == ["p1"]
    check(s)


def test_aura_barbs_enchantments_hit_their_controllers_then_auras_their_creatures(cards):
    """Holy Strength (on Alice's Grizzly Bears, now 3/4) and Bob's Propaganda each deal 2 to their controller; then Holy Strength deals 2 to the bear."""
    s = build(cards, ["Aura Barbs", "Holy Strength", "Grizzly Bears"], ["Propaganda"])
    bear, strength = put_on(s, "Grizzly Bears"), put_on(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[strength.id], to=bear.id)
    put_on(s, "Propaganda", "p2")
    cast(s, "Aura Barbs", R=1, C=2)
    assert life(s) == 38 and life(s, "p2") == 38 and s.state.cards[bear.id].damage == 2
    check(s)


def test_bakis_curse_two_damage_per_aura_on_each_creature(cards):
    """Grizzly Bears with Holy Strength and Pacifism (3/4): 4 damage, it dies; Llanowar Elves, no Aura: none."""
    s = build(cards, ["Baki's Curse", "Holy Strength", "Pacifism", "Grizzly Bears", "Llanowar Elves"], [])
    bear, elves = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves")
    for name in ("Holy Strength", "Pacifism"):
        act(s, "p1", type="attach", card_ids=[put_on(s, name).id], to=bear.id)
    cast(s, "Baki's Curse", U=2, C=2)
    assert zone(s, bear) == "p1:graveyard" and zone(s, elves) == "p1:battlefield" and s.state.cards[elves.id].damage == 0
    check(s)


def test_pollen_lullaby_a_won_clash_keeps_that_players_creatures_tapped(cards):
    """Alice's top card is Sliver Queen (5), Bob's an Island (0): Alice wins the clash; Bob's tapped Grizzly Bears stays tapped in his next untap step."""
    s = build(cards, ["Pollen Lullaby", "Sliver Queen"], ["Grizzly Bears"])
    bear = put_on(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
    move(s, one(s, "Sliver Queen"), "library", position="top")
    move(s, one(s, "Pollen Lullaby"), "hand")
    cast(s, "Pollen Lullaby", prefer=["top"], W=1, C=1)
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    to_phase(s, "main1", turn=2)
    assert s.state.cards[bear.id].tapped
    check(s)


def test_metamorphose_tucks_the_permanent_and_its_controller_may_put_a_card_in(cards):
    s = build(cards, ["Metamorphose"], ["Sol Ring", "Grizzly Bears"])
    ring, bear = put_on(s, "Sol Ring", "p2"), move(s, one(s, "Grizzly Bears", "p2"), "hand")
    cast(s, "Metamorphose", targets=[ring.id], prefer=[bear.id], U=1, C=1)
    assert s.state.zones["p2:library"][0] == ring.id and zone(s, bear) == "p2:battlefield"
    check(s)


def test_rite_of_ruin_one_two_three_in_the_chosen_order(cards):
    """Order lands, creatures, artifacts: Bob (three Islands, two creatures, two artifacts) sacrifices one land, both creatures and both artifacts."""
    s = build(cards, ["Rite of Ruin"], ["Grizzly Bears", "Llanowar Elves", "Sol Ring", "Arcane Signet"])
    islands = [move(s, c, "battlefield") for c in named(s, "Island", "p2")[:3]]
    rest = [put_on(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Sol Ring", "Arcane Signet")]
    cast(s, "Rite of Ruin", prefer=["Lands, creatures, artifacts"], R=2, C=5)
    assert [zone(s, c) for c in islands].count("p2:graveyard") == 1 and all(zone(s, c) == "p2:graveyard" for c in rest)
    check(s)
