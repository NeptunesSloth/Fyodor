"""Wave 17C (the static_other long tail, third pass). Real Oracle text, replay and save/load for each.

* 702.21a: ward costs that aren't mana alone, granted by a static ("Other creatures you control have "Ward—Pay 2 life."") or
  printed with two parts ("Ward—{2}, Pay 2 life.").
* 614.12 / 702.136a: riot granted to the permanents a static names ("Nontoken creatures you control have riot.").
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Test Small", set_code="tst", number="C01", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Rhythm of the Wild", set_code="tst", number="C02", mana_cost="{1}{R}{G}", cmc=3.0, type_line="Enchantment",
         colors=["G", "R"], color_identity=["G", "R"],
         oracle_text="Creature spells you control can't be countered.\nNontoken creatures you control have riot. (They enter with your "
         "choice of a +1/+1 counter or haste.)"),
    card("Flame Jab", set_code="tst", number="C07", mana_cost="{R}", cmc=1.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Flame Jab deals 1 damage to any target.\nRetrace (You may cast this card from your graveyard by discarding a "
         "land card in addition to paying its other costs.)"),
    card("Deeproot Historian", set_code="tst", number="C08", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Merfolk Druid",
         power="2", toughness="2", colors=["G"], color_identity=["G"],
         oracle_text="Merfolk and Druid cards in your graveyard have retrace. (You may cast cards with retrace from your graveyard "
         "by discarding a land card in addition to paying their other costs.)"),
    card("Six", set_code="tst", number="C09", mana_cost="{2}{G}", cmc=3.0, type_line="Legendary Creature — Elemental Spirit Tortoise",
         power="2", toughness="4", colors=["G"], color_identity=["G"],
         oracle_text="Reach\nWhenever Six attacks, mill three cards. You may put a land card from among them into your hand.\n"
         "During your turn, nonland permanent cards in your graveyard have retrace. (You may cast permanent cards from your "
         "graveyard by discarding a land card in addition to paying their other costs.)"),
    card("Sami, Wildcat Captain", set_code="tst", number="C10", mana_cost="{4}{R}{W}", cmc=6.0,
         type_line="Legendary Creature — Human Artificer Rogue", power="4", toughness="4", colors=["R", "W"], color_identity=["R", "W"],
         oracle_text="Double strike, vigilance\nSpells you cast have affinity for artifacts. (They cost {1} less to cast for each "
         "artifact you control.)"),
    card("Test Relic", set_code="tst", number="C11", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
    card("Test Bear", set_code="tst", number="C12", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Bear", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Hoarding Broodlord", set_code="tst", number="C13", mana_cost="{5}{B}{B}{B}", cmc=8.0, type_line="Creature — Dragon",
         power="7", toughness="6", colors=["B"], color_identity=["B"],
         oracle_text="Convoke\nFlying\nWhen this creature enters, search your library for a card, exile it face down, then "
         "shuffle. For as long as that card remains exiled, you may play it.\nSpells you cast from exile have convoke."),
    card("Light Up the Stage", set_code="tst", number="C14", mana_cost="{2}{R}", cmc=3.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], oracle_text="Spectacle {R} (You may cast this spell for its spectacle cost rather than its mana cost "
         "if an opponent lost life this turn.)\nExile the top two cards of your library. Until the end of your next turn, you may "
         "play those cards."),
    card("Prismari, the Inspiration", set_code="tst", number="C15", mana_cost="{5}{U}{R}", cmc=7.0,
         type_line="Legendary Creature — Elder Dragon", power="7", toughness="7", colors=["R", "U"], color_identity=["R", "U"],
         oracle_text="Flying\nWard—Pay 5 life.\nInstant and sorcery spells you cast have storm. (Whenever you cast an instant or "
         "sorcery spell, copy it for each spell cast before it this turn. You may choose new targets for the copies.)"),
    card("Ygra, Eater of All", set_code="tst", number="C16", mana_cost="{3}{B}{G}", cmc=5.0, type_line="Legendary Creature — Elemental Cat",
         power="6", toughness="6", colors=["B", "G"], color_identity=["B", "G"],
         oracle_text="Ward—Sacrifice a Food.\nOther creatures are Food artifacts in addition to their other types and have \"{2}, {T}, "
         "Sacrifice this permanent: You gain 3 life.\"\nWhenever a Food is put into a graveyard from the battlefield, put two +1/+1 "
         "counters on Ygra."),
    card("Goldspan Dragon", set_code="tst", number="C17", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Creature — Dragon", power="4",
         toughness="4", colors=["R"], color_identity=["R"],
         oracle_text="Flying, haste\nWhenever Goldspan Dragon attacks or becomes the target of a spell, create a Treasure token.\n"
         "Treasures you control have \"{T}, Sacrifice this artifact: Add two mana of any one color.\""),
    card("Gourmand's Talent", set_code="tst", number="C18", mana_cost="{G}", cmc=1.0, type_line="Enchantment — Class", colors=["G"],
         color_identity=["G"], oracle_text="(Gain the next level as a sorcery to add its ability.)\nDuring your turn, artifacts you control "
         "are Foods in addition to their other types and have \"{2}, {T}, Sacrifice this artifact: You gain 3 life.\"\n{2}{G}: Level 2\n"
         "Whenever you gain life for the first time each turn, create a 3/3 green Raccoon creature token.\n{3}{G}: Level 3\n"
         "Whenever you gain life for the first time each turn, put a +1/+1 counter on each creature you control."),
    card("Boomerang Basics", set_code="tst", number="C19", mana_cost="{U}", cmc=1.0, type_line="Sorcery — Lesson", colors=["U"],
         color_identity=["U"], oracle_text="Return target nonland permanent to its owner's hand. If you controlled that permanent, "
         "draw a card."),
    card("Gleeful Demolition", set_code="tst", number="C20", mana_cost="{R}", cmc=1.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], oracle_text="Destroy target artifact. If you controlled that artifact, create three 1/1 red Phyrexian "
         "Goblin creature tokens."),
    card("Fateful Absence", set_code="tst", number="C21", mana_cost="{1}{W}", cmc=2.0, type_line="Instant", colors=["W"],
         color_identity=["W"], oracle_text="Destroy target creature or planeswalker. Its controller investigates. (They create a Clue "
         "token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")"),
    card("Serum Snare", set_code="tst", number="C22", mana_cost="{1}{U}", cmc=2.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="Return target nonland permanent to its owner's hand. If that permanent had mana value 3 or "
         "less, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already "
         "there.)"),
    card("Flamekin Herald", set_code="tst", number="C23", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Elemental Wizard",
         power="3", toughness="2", colors=["R"], color_identity=["R"],
         oracle_text="Commander spells you cast have cascade. (Whenever you cast a commander, exile cards from the top of your library "
         "until you exile a nonland card with lesser mana value. You may cast it without paying its mana cost. Put the exiled cards "
         "on the bottom in a random order.)"),
    card("Kudo, King Among Bears", set_code="tst", number="C24", mana_cost="{G}{W}", cmc=2.0, type_line="Legendary Creature — Bear",
         power="2", toughness="2", colors=["G", "W"], color_identity=["G", "W"],
         oracle_text="Other creatures have base power and toughness 2/2 and are Bears in addition to their other types."),
    card("Roshan, Hidden Magister", set_code="tst", number="C25", mana_cost="{3}{B}", cmc=4.0,
         type_line="Legendary Creature — Human Assassin", power="4", toughness="4", colors=["B"], color_identity=["B"],
         oracle_text="Other creatures you control are Assassins in addition to their other types. The same is true for creature spells "
         "you control and creature cards you own that aren't on the battlefield.\nFace-down creatures you control have menace.\n"
         "Whenever a permanent you control is turned face up, you draw a card and you lose 1 life."),
    card("Test Brute", set_code="tst", number="C26", mana_cost="{4}{G}", cmc=5.0, type_line="Creature — Ogre", power="5", toughness="5",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Giant Ox", set_code="tst", number="C27", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Ox", power="0", toughness="6",
         colors=["W"], color_identity=["W"], oracle_text="This creature crews Vehicles using its toughness rather than its power."),
    card("Hotshot Mechanic", set_code="tst", number="C28", mana_cost="{W}", cmc=1.0, type_line="Artifact Creature — Fox Pilot",
         power="2", toughness="1", colors=["W"], color_identity=["W"],
         oracle_text="This creature crews Vehicles as though its power were 2 greater."),
    card("Test Wagon", set_code="tst", number="C29", mana_cost="{3}", cmc=3.0, type_line="Artifact — Vehicle", power="4", toughness="4",
         oracle_text="Crew 4 (Tap any number of untapped creatures you control with total power 4 or more: This Vehicle becomes an "
         "artifact creature until end of turn.)"),
    card("Astor, Bearer of Blades", set_code="tst", number="C30", mana_cost="{2}{R}{W}", cmc=4.0,
         type_line="Legendary Creature — Human Warrior", power="4", toughness="4", colors=["R", "W"], color_identity=["R", "W"],
         oracle_text="When Astor enters, look at the top seven cards of your library. You may reveal an Equipment or Vehicle card "
         "from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nEquipment you "
         "control have equip {1}.\nVehicles you control have crew 1."),
    card("Surging Flame", set_code="tst", number="C31", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Ripple 4 (When you cast this spell, you may reveal the top four cards of your library. You "
         "may cast spells with the same name as this spell from among those cards without paying their mana costs. Put the rest on "
         "the bottom of your library.)\nSurging Flame deals 2 damage to any target."),
    card("Thrumming Stone", set_code="tst", number="C32", mana_cost="{5}", cmc=5.0, type_line="Legendary Artifact",
         oracle_text="Spells you cast have ripple 4. (Whenever you cast a spell, you may reveal the top four cards of your library. You "
         "may cast spells with the same name as that spell from among the revealed cards without paying their mana costs. Put the "
         "rest on the bottom of your library.)"),
    card("Morsel Theft", set_code="tst", number="C33", mana_cost="{2}{B}{B}", cmc=4.0, type_line="Kindred Sorcery — Rogue", colors=["B"],
         color_identity=["B"], oracle_text="Prowl {1}{B} (You may cast this for its prowl cost if you dealt combat damage to a player "
         "this turn with a Rogue.)\nTarget player loses 3 life and you gain 3 life. If this spell's prowl cost was paid, draw a card."),
    card("Hunting Velociraptor", set_code="tst", number="C34", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Dinosaur", power="3",
         toughness="2", colors=["R"], color_identity=["R"],
         oracle_text="First strike\nDinosaur spells you cast have prowl {2}{R}. (You may cast a spell for its prowl cost if you dealt "
         "combat damage to a player this turn with a creature with any of its creature types.)"),
    card("Test Raptor", set_code="tst", number="C35", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Creature — Dinosaur", power="5",
         toughness="5", colors=["R"], color_identity=["R"], oracle_text=""),
    card("Mudbutton Cursetosser", set_code="tst", number="C36", mana_cost="{B}", cmc=1.0, type_line="Creature — Goblin Warlock", power="2",
         toughness="1", colors=["B"], color_identity=["B"],
         oracle_text="As an additional cost to cast this spell, behold a Goblin or pay {2}. (To behold a Goblin, choose a Goblin you "
         "control or reveal a Goblin card from your hand.)\nThis creature can't block.\nWhen this creature dies, destroy target "
         "creature an opponent controls with power 2 or less."),
    card("Living Destiny", set_code="tst", number="C37", mana_cost="{3}{G}", cmc=4.0, type_line="Instant", colors=["G"], color_identity=["G"],
         oracle_text="As an additional cost to cast this spell, reveal a creature card from your hand.\nYou gain life equal to the "
         "revealed card's mana value."),
    card("Titan's Presence", set_code="tst", number="C38", mana_cost="{3}", cmc=3.0, type_line="Instant",
         oracle_text="As an additional cost to cast this spell, reveal a colorless creature card from your hand.\nExile target creature "
         "if its power is less than or equal to the revealed card's power."),
    card("Calamity of the Titans", set_code="tst", number="C39", mana_cost="{4}{C}{C}", cmc=6.0, type_line="Sorcery",
         oracle_text="As an additional cost to cast this spell, reveal a colorless creature card from your hand.\nExile each creature "
         "and planeswalker with mana value less than the revealed card's mana value."),
    card("Warlord's Elite", set_code="tst", number="C40", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Human Soldier", power="4",
         toughness="4", colors=["W"], color_identity=["W"],
         oracle_text="As an additional cost to cast this spell, tap two untapped artifacts, creatures, and/or lands you control."),
    card("Test Drone", set_code="tst", number="C41", mana_cost="{2}", cmc=2.0, type_line="Artifact Creature — Eldrazi Drone", power="3",
         toughness="3", oracle_text=""),
    card("Hexing Squelcher", set_code="tst", number="C05", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Goblin Sorcerer",
         power="2", toughness="2", colors=["R"], color_identity=["R"],
         oracle_text="This spell can't be countered.\nWard—Pay 2 life.\nSpells you control can't be countered.\nOther creatures you control have \"Ward—Pay 2 life.\""),
    card("Gisa, the Hellraiser", set_code="tst", number="C06", mana_cost="{3}{B}{B}", cmc=5.0,
         type_line="Legendary Creature — Human Warlock", power="4", toughness="4", colors=["B"], color_identity=["B"],
         oracle_text="Ward—{2}, Pay 2 life.\nSkeletons and Zombies you control get +1/+1 and have menace.\nWhenever you commit a "
         "crime, create two tapped 2/2 blue and black Zombie Rogue creature tokens. This ability triggers only once each turn. "
         "(Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _bolt(cards, target, p2, extra_mana=None):
    s = build(cards, p1=("Lightning Bolt",), p2=p2)
    for n in p2:
        put(s, n, "battlefield", "p2")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1, **(extra_mana or {}))
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[find(s, target, "p2").id])
    d = s.state.rules.decision
    while d is not None and d.player != "p1":  # (the ward trigger goes on the stack first)
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
    return s, d


def test_granted_ward_pay_life_counters_unless_paid(cards):
    s, _ = _bolt(cards, "Test Small", ("Hexing Squelcher", "Test Small"))
    for _ in range(6):  # 702.21a: the granted ward triggers as the Bolt targets Test Small (not Squelcher: its own, printed)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "2 life" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    answer(s)
    assert find(s, "Test Small", "p2").zone == "p2:battlefield" and s.state.players["p1"].life == 40  # countered
    roundtrip(s)


def test_ward_mana_and_life_two_part_cost(cards):
    s, _ = _bolt(cards, "Gisa, the Hellraiser", ("Gisa, the Hellraiser",), {"C": 2})
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "2 life" in d.prompt and "{2}" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert s.state.players["p1"].life == 38  # 702.21a: both parts of the cost, {2} and 2 life
    assert find(s, "Gisa, the Hellraiser", "p2").damage == 3
    roundtrip(s)


def test_granted_riot_asks_on_entering(cards):
    s = build(cards, p1=("Rhythm of the Wild", "Test Small"))
    put(s, "Rhythm of the Wild", "battlefield")
    c = put(s, "Test Small", "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, limit=30)
    got = find(s, "Test Small")
    assert got.zone == "p1:battlefield" and got.counters.get("+1/+1") == 1  # 702.136a (the first option: the counter)
    roundtrip(s)


def test_retrace_cast_from_graveyard_discarding_a_land(cards):
    s = build(cards, p1=("Flame Jab",))
    jab = put(s, "Flame Jab", "graveyard")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=jab.id, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == 39  # 702.81a
    assert s.state.cards[forest.id].zone == "p1:graveyard" and s.state.cards[jab.id].zone == "p1:graveyard"
    with pytest.raises(ActionError):  # no land card left in hand to discard
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=jab.id, targets=["p2"])
    roundtrip(s)


def test_granted_retrace_for_the_named_cards_only(cards):
    s = build(cards, p1=("Deeproot Historian", "Deeproot Historian", "Test Small"))
    hs = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Deeproot Historian"]
    act(s, "p1", type="move", card_ids=[hs[0].id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[hs[1].id], to={"player": "p1", "zone": "graveyard"})
    elf = put(s, "Test Small", "graveyard")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=2, C=1)
    with pytest.raises(ActionError):  # an Elf is neither a Merfolk nor a Druid
        act(s, "p1", type="cast_spell", card_id=elf.id)
    act(s, "p1", type="cast_spell", card_id=hs[1].id)  # 702.81a: a Merfolk Druid has retrace from the other one
    answer(s)
    assert s.state.cards[hs[1].id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:graveyard"
    roundtrip(s)


def test_granted_affinity_reduces_the_spells_cost(cards):
    s = build(cards, p1=("Sami, Wildcat Captain", "Test Relic", "Test Relic", "Test Bear"))
    put(s, "Sami, Wildcat Captain", "battlefield")
    for r in [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Test Relic"]:
        act(s, "p1", type="move", card_ids=[r.id], to={"player": "p1", "zone": "battlefield"})
    bear = put(s, "Test Bear", "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)  # 702.41a: {2}{G} less two generic = {G}
    answer(s)
    assert find(s, "Test Bear").zone == "p1:battlefield"
    roundtrip(s)


def test_convoke_granted_to_spells_cast_from_exile(cards):
    s = build(cards, p1=("Hoarding Broodlord", "Light Up the Stage", "Test Small", "Test Bear"))
    lord = put(s, "Hoarding Broodlord", "battlefield")
    small = put(s, "Test Small", "battlefield")
    bear = put(s, "Test Bear", "library", position="top")
    act_ = put(s, "Light Up the Stage", "hand")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=act_.id)
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    mana(s, C=1)  # {2}{G}: the creatures pay for the rest (702.51a: Test Small is green), the Bear is cast from exile
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[lord.id].tapped and s.state.cards[small.id].tapped
    roundtrip(s)


def test_granted_storm_copies_for_each_earlier_spell(cards):
    s = build(cards, p1=("Prismari, the Inspiration", "Lightning Bolt", "Lightning Bolt"))
    put(s, "Prismari, the Inspiration", "battlefield")
    bolts = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Lightning Bolt"]
    for b in bolts:
        act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "hand"})
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=bolts[0].id, targets=["p2"])  # 702.40a: nothing was cast before it
    act(s, "p1", type="cast_spell", card_id=bolts[1].id, targets=["p2"])  # one spell before it: one copy
    answer(s)
    assert s.state.players["p2"].life == 40 - 9
    roundtrip(s)


def _derived(s, name, pid="p1"):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = find(s, name, pid)
    return c, derive(s.state, c, chars.of(c, s.cards), s.cards)


def test_ygra_makes_creatures_foods_with_a_granted_sacrifice_ability(cards):
    s = build(cards, p1=("Ygra, Eater of All", "Test Small"))
    put(s, "Ygra, Eater of All", "battlefield")
    small = put(s, "Test Small", "battlefield")
    _, ch = _derived(s, "Test Small")
    assert "Artifact" in ch.types and "Food" in ch.subtypes and "Elf" in ch.subtypes  # 613.1d, 205.1b: in addition to its other types
    ab = next(a for a in ch.abilities if a.index >= 100 and a.kind == "activated")
    assert "{2}, {T}, Sacrifice" in ab.text and "gain 3 life" in ab.text  # 613.1f
    assert "Artifact" not in _derived(s, "Ygra, Eater of All")[1].types  # ("Other creatures")
    roundtrip(s)


def test_during_your_turn_artifacts_are_foods(cards):
    s = build(cards, p1=("Gourmand's Talent", "Test Relic"))
    put(s, "Gourmand's Talent", "battlefield")
    put(s, "Test Relic", "battlefield")
    assert "Food" in _derived(s, "Test Relic")[1].subtypes
    act(s, "p1", type="next_turn")  # Bob's turn: "During your turn" is over
    assert s.state.turn.active_player == "p2" and "Food" not in _derived(s, "Test Relic")[1].subtypes
    roundtrip(s)


def test_goldspan_dragon_treasures_tap_for_two(cards):
    s = build(cards, p1=("Goldspan Dragon",))
    put(s, "Goldspan Dragon", "battlefield")
    act(s, "p1", type="create_token", player="p1", token={"name": "Treasure", "type_line": "Token Artifact — Treasure",
                                                          "text": "{T}, Sacrifice this artifact: Add one mana of any color."})
    _, ch = _derived(s, "Treasure")
    ab = next(a for a in ch.abilities if a.kind == "mana" and a.index >= 100)
    assert "two mana" in ab.text  # 613.1f: the Dragon's granted ability, next to the Treasure's own
    roundtrip(s)


def test_if_you_controlled_that_permanent(cards):
    s = build(cards, p1=("Boomerang Basics", "Boomerang Basics", "Test Small"), p2=("Test Small",))
    mine, theirs = put(s, "Test Small", "battlefield"), put(s, "Test Small", "battlefield", "p2")
    spells = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Boomerang Basics"]
    for c in spells:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    hand = len(s.state.zones["p1:hand"])
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=spells[0].id, targets=[theirs.id])
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:hand" and len(s.state.zones["p1:hand"]) == hand - 1  # 608.2h: not yours, no card
    act(s, "p1", type="cast_spell", card_id=spells[1].id, targets=[mine.id])
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:hand" and len(s.state.zones["p1:hand"]) == hand - 2 + 1 + 1  # yours: you draw
    roundtrip(s)


def test_its_controller_investigates(cards):
    s = build(cards, p1=("Fateful Absence",), p2=("Test Small",))
    victim = put(s, "Test Small", "battlefield", "p2")
    spell = put(s, "Fateful Absence", "hand")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    answer(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    assert any(c.name == "Clue" and c.controller == "p2" for c in s.state.cards.values())  # 701.16a: the creature's controller
    roundtrip(s)


def test_commander_spells_have_cascade(cards):
    s = build(cards, p1=("Flamekin Herald",))
    put(s, "Flamekin Herald", "battlefield")
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Krenko, Mob Boss")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    text = " ".join(part.t or "" for e in s.state.log for part in e.parts)
    assert "ascade" in text  # 702.85a: the cascade trigger went on the stack and resolved
    roundtrip(s)


def test_kudo_sets_base_power_and_toughness_and_adds_bear(cards):
    s = build(cards, p1=("Kudo, King Among Bears", "Test Brute"))
    put(s, "Kudo, King Among Bears", "battlefield")
    put(s, "Test Brute", "battlefield")
    _, ch = _derived(s, "Test Brute")
    assert ch.pt == (2, 2) and {"Bear", "Ogre"} <= ch.subtypes  # 613.4b, 205.1b: base 2/2, Bear in addition
    roundtrip(s)


def test_roshan_assassins_on_the_battlefield_and_in_hand(cards):
    s = build(cards, p1=("Roshan, Hidden Magister", "Test Brute", "Test Small"))
    put(s, "Roshan, Hidden Magister", "battlefield")
    put(s, "Test Brute", "battlefield")
    put(s, "Test Small", "hand")
    assert "Assassin" in _derived(s, "Test Brute")[1].subtypes and "Assassin" in _derived(s, "Test Small")[1].subtypes
    assert "Assassin" in _derived(s, "Roshan, Hidden Magister")[1].subtypes  # (a printed Assassin, whatever "other" says)
    roundtrip(s)


@pytest.mark.parametrize("crewer, can", [("Giant Ox", True), ("Hotshot Mechanic", True), ("Test Small", False)])
def test_crew_counts_toughness_or_extra_power(cards, crewer, can):
    from app.rules.casting import activatable

    s = build(cards, p1=(crewer, "Test Wagon"))
    wagon = put(s, "Test Wagon", "battlefield")
    put(s, crewer, "battlefield")
    # 702.122a: Crew 4 — a 0/6 counting its toughness (6) and a 2/1 counting 2 greater (4) can; a plain 2/2 can't
    assert any(a["card_id"] == wagon.id for a in activatable(s.state, "p1", cards)) == can
    roundtrip(s)


def test_granted_equip_and_crew(cards):
    s = build(cards, p1=("Astor, Bearer of Blades", "Behemoth Sledge", "Test Wagon", "Test Small"))
    put(s, "Astor, Bearer of Blades", "battlefield")
    sledge = put(s, "Behemoth Sledge", "battlefield")
    wagon = put(s, "Test Wagon", "battlefield")
    small = put(s, "Test Small", "battlefield")
    _, ch = _derived(s, "Behemoth Sledge")
    granted = next(a for a in ch.abilities if a.index >= 100 and "equip" in a.keywords)
    assert granted.text == "Equip {1}"  # 613.1f: a second equip ability next to its own {3}
    _, wch = _derived(s, "Test Wagon")
    assert any(a.index >= 100 and a.text == "Crew 1" for a in wch.abilities)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sledge.id, ability=granted.index, targets=[small.id])
    answer(s)
    assert s.state.cards[sledge.id].attached_to == small.id  # 702.6a: attached for the granted {1}
    roundtrip(s)
    assert wagon.id


def _flames(s):
    return [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Surging Flame"]


def test_ripple_casts_the_copy_it_reveals(cards):
    s = build(cards, p1=("Surging Flame", "Surging Flame"))
    first, second = _flames(s)
    act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    for _ in range(30):  # reveal (yes), order the rest, cast the copy (yes) at Bob (the copy has ripple too: its own reveal)
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[:max(1, d.min_choices)])
    assert s.state.players["p2"].life == 40 - 4  # 702.60a: the spell and the Flame it revealed, cast without paying
    assert s.state.cards[second.id].zone == "p1:graveyard" and s.state.cards[first.id].zone == "p1:graveyard"
    roundtrip(s)


def test_ripple_with_no_copy_puts_the_revealed_cards_on_the_bottom(cards):
    s = build(cards, p1=("Surging Flame",))
    (flame,) = _flames(s)
    act(s, "p1", type="move", card_ids=[flame.id], to={"player": "p1", "zone": "hand"})
    top4 = list(s.state.zones["p1:library"][:4])
    below = list(s.state.zones["p1:library"][4:6])
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=flame.id, targets=["p2"])
    answer(s, limit=40)
    library = s.state.zones["p1:library"]
    assert library[:2] == below and set(library[-4:]) == set(top4)  # 702.60a: the revealed cards now at the bottom
    roundtrip(s)


def test_thrumming_stone_gives_every_spell_ripple(cards):
    s = build(cards, p1=("Thrumming Stone", "Lightning Bolt"))
    put(s, "Thrumming Stone", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    top4 = list(s.state.zones["p1:library"][:4])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s, limit=40)
    assert set(s.state.zones["p1:library"][-4:]) == set(top4)
    roundtrip(s)


def _prowl_offers(s, name):
    from app.rules import alt_costs, characteristics as chars

    c = find(s, name)
    return c, [o for o in alt_costs.offers(s.state, "p1", c, chars.of(c, s.cards), s.cards) if o.tag == "prowl"]


def _attack_with(s, type_line):
    act(s, "p1", type="create_token", player="p1", token={"name": "Scout", "type_line": type_line, "power": "2", "toughness": "2",
                                                          "text": "Haste"})
    scout = next(c for c in s.state.cards.values() if c.name == "Scout")
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": scout.id, "target": "p2"}])
    for _ in range(12):
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 38 and s.state.turn.phase == "main2"


def test_prowl_cost_after_combat_damage_by_a_creature_of_its_type(cards):
    s = build(cards, p1=("Morsel Theft",))
    theft = put(s, "Morsel Theft", "hand")
    assert not _prowl_offers(s, "Morsel Theft")[1]  # (nobody was dealt combat damage yet)
    _attack_with(s, "Token Creature — Rogue")
    _, offers = _prowl_offers(s, "Morsel Theft")
    assert len(offers) == 1  # 702.76a: a Rogue dealt combat damage to a player this turn
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=theft.id, targets=["p2"], alt_cost=offers[0].key)
    answer(s)
    assert s.state.players["p2"].life == 38 - 3 and len(s.state.zones["p1:hand"]) == hand - 1 + 1  # lost 3, and the prowl draw
    roundtrip(s)


def test_prowl_needs_a_matching_creature_type(cards):
    s = build(cards, p1=("Morsel Theft",))
    put(s, "Morsel Theft", "hand")
    _attack_with(s, "Token Creature — Goblin")
    assert not _prowl_offers(s, "Morsel Theft")[1]  # (a Goblin is not a Rogue)
    roundtrip(s)


def test_velociraptor_grants_prowl_to_dinosaur_spells(cards):
    s = build(cards, p1=("Hunting Velociraptor", "Test Raptor", "Test Small"))
    put(s, "Hunting Velociraptor", "battlefield")
    put(s, "Test Raptor", "hand")
    put(s, "Test Small", "hand")
    _attack_with(s, "Token Creature — Dinosaur")
    assert len(_prowl_offers(s, "Test Raptor")[1]) == 1 and not _prowl_offers(s, "Test Small")[1]
    roundtrip(s)


def test_behold_a_goblin_or_pay_two(cards):
    s = build(cards, p1=("Mudbutton Cursetosser",))
    act(s, "p1", type="create_token", player="p1", token={"name": "Imp", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1"})
    c = put(s, "Mudbutton Cursetosser", "hand")
    mana(s, B=1)  # 701.4a: choosing the Goblin you control is the additional cost: no {2}
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert find(s, "Mudbutton Cursetosser").zone == "p1:battlefield"
    roundtrip(s)


def test_pay_two_when_nothing_can_be_beheld(cards):
    s = build(cards, p1=("Mudbutton Cursetosser",))
    c = put(s, "Mudbutton Cursetosser", "hand")
    mana(s, B=1)
    with pytest.raises(ActionError):  # (no Goblin to behold: the {2} side is the only one, and it isn't there)
        act(s, "p1", type="cast_spell", card_id=c.id)
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert find(s, "Mudbutton Cursetosser").zone == "p1:battlefield"
    roundtrip(s)


def test_reveal_a_creature_card_and_gain_its_mana_value(cards):
    s = build(cards, p1=("Living Destiny", "Test Brute"))
    c = put(s, "Living Destiny", "hand")
    brute = put(s, "Test Brute", "hand")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.players["p1"].life == 45  # 701.20a / 608.2h: the revealed Test Brute's mana value, 5
    assert s.state.cards[brute.id].zone == "p1:hand"
    roundtrip(s)


def test_titans_presence_compares_with_the_revealed_card(cards):
    s = build(cards, p1=("Titan's Presence", "Test Drone"), p2=("Test Small", "Test Brute"))
    small, brute = put(s, "Test Small", "battlefield", "p2"), put(s, "Test Brute", "battlefield", "p2")
    presence = put(s, "Titan's Presence", "hand")
    put(s, "Test Drone", "hand")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=presence.id, targets=[brute.id])
    answer(s)
    assert s.state.cards[brute.id].zone == "p2:battlefield"  # power 5 is more than the revealed Drone's 3
    put(s, "Titan's Presence", "hand")
    act(s, "p1", type="cast_spell", card_id=presence.id, targets=[small.id])
    answer(s)
    assert s.state.cards[small.id].zone == "p2:exile"  # power 2 is at most 3
    roundtrip(s)


def test_calamity_of_the_titans_exiles_what_costs_less(cards):
    s = build(cards, p1=("Calamity of the Titans", "Test Drone"), p2=("Test Small", "Test Brute"))
    small, brute = put(s, "Test Small", "battlefield", "p2"), put(s, "Test Brute", "battlefield", "p2")
    c = put(s, "Calamity of the Titans", "hand")
    put(s, "Test Drone", "hand")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[small.id].zone == "p2:exile" and s.state.cards[brute.id].zone == "p2:battlefield"  # mana value 1 < 2 < 5
    roundtrip(s)


def test_tap_two_untapped_artifacts_creatures_or_lands(cards):
    s = build(cards, p1=("Warlord's Elite", "Test Small"))
    elite = put(s, "Warlord's Elite", "hand")
    put(s, "Test Small", "battlefield")
    put(s, "Forest", "battlefield")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=elite.id)
    answer(s)
    assert find(s, "Warlord's Elite").zone == "p1:battlefield"
    assert sum(1 for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:battlefield" and c.tapped) >= 2
    roundtrip(s)
