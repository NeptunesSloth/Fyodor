"""Wave 17D: the trigger long tail, third pass (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 702.149a: a token "with training" has the keyword's triggered ability.
* 700.4: "leave the battlefield without dying" - a leave that is not a put into a graveyard.
* 701.17a: a mill event ("a player mills a nonland card", "one or more nonland cards are milled"), one per library owner's card.
* 603.2c: "a black spell or a Swamp you control enters" - two whole conditions, each its own event.
* 603.2 / 500.1: "they lose 1 life for each spell they've cast this turn", "if it's not their turn" - the event's player.
* 701.44a: "it explores" for the creature that entered; 701.9a: "exile that card" for the discarded card.
* 508.4: tokens put onto the battlefield attacking (untapped unless the text says tapped); "that many" for "one or more attack".
* 106.12a: "Whenever you tap a permanent for {C}, add an additional {C}" - only when the ability produced {C}, once.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import through_combat, token_of
from tests.test_rules_effects import mana
from tests.test_rules_wave5c_combat import attacking, declare, to_attack, to_blocks
from tests.test_rules_wave5c_combat import build as combat_build
from tests.test_rules_wave5c_combat import put as combat_put
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.test_rules_wave15b_triggers import kill
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

EXTRA = [
    real('Torens, Fist of the Angels', '{1}{G}{W}', 3, 'Legendary Creature — Human Cleric',
         'Training (Whenever this creature attacks with another creature with greater power, put a +1/+1 counter on this creature.)\nWhenever you cast a creature spell, create a 1/1 green and white Human Soldier creature token with training.', ("2", "2"), 'GW'),
    real('Dour Port-Mage', '{1}{U}', 2, 'Creature — Frog Wizard',
         "Whenever one or more other creatures you control leave the battlefield without dying, draw a card.\n{1}{U}, {T}: Return another target creature you control to its owner's hand.", ("1", "3"), 'U'),
    real('Glowing One', '{2}{G}', 3, 'Creature — Zombie Mutant',
         'Deathtouch\nWhenever this creature deals combat damage to a player, they get four rad counters.\nWhenever a player mills a nonland card, you gain 1 life.', ("2", "2"), 'G'),
    real('Screeching Scorchbeast', '{4}{B}{B}', 6, 'Creature — Bat Mutant',
         'Flying, menace\nWhenever this creature attacks, each player gets two rad counters.\nWhenever one or more nonland cards are milled, you may create that many 2/2 black Zombie Mutant creature tokens. Do this only once each turn.', ("5", "5"), 'B'),
    real('Staff of the Death Magus', '{3}', 3, 'Artifact',
         'Whenever you cast a black spell or a Swamp you control enters, you gain 1 life.', None, ''),
    real('Rug of Smothering', '{3}', 3, 'Artifact Creature — Construct',
         "Flying\nWhenever a player casts a spell, they lose 1 life for each spell they've cast this turn.", ("1", "3"), ''),
    real('Path of Discovery', '{3}{G}', 4, 'Enchantment',
         "Whenever a creature you control enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on the creature, then put the card back or put it into your graveyard.)", None, 'G'),
    real('Necropotence', '{B}{B}{B}', 3, 'Enchantment',
         'Skip your draw step.\nWhenever you discard a card, exile that card from your graveyard.\nPay 1 life: Exile the top card of your library face down. Put that card into your hand at the beginning of your next end step.', None, 'B'),
    real('Prosperous Thief', '{2}{U}', 3, 'Creature — Human Ninja',
         'Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nWhenever one or more Ninja or Rogue creatures you control deal combat damage to a player, create a Treasure token. (It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")', ("3", "2"), 'U'),
    real('Forsaken Monument', '{5}', 5, 'Legendary Artifact',
         'Colorless creatures you control get +2/+2.\nWhenever you tap a permanent for {C}, add an additional {C}.\nWhenever you cast a colorless spell, you gain 2 life.', None, ''),
    real('Parhelion II', '{6}{W}{W}', 8, 'Legendary Artifact — Vehicle',
         'Flying, first strike, vigilance\nWhenever Parhelion II attacks, create two 4/4 white Angel creature tokens with flying and vigilance that are attacking.\nCrew 4 (Tap any number of creatures you control with total power 4 or more: This Vehicle becomes an artifact creature until end of turn.)', ("5", "5"), 'W'),
    real('Poetic Ingenuity', '{2}{R}', 3, 'Enchantment',
         'Whenever one or more Dinosaurs you control attack, create that many Treasure tokens.\nWhenever you cast an artifact spell, create a 3/1 red Dinosaur creature token. This ability triggers only once each turn.', None, 'R'),
    real('Scytheclaw Raptor', '{2}{R}', 3, 'Creature — Dinosaur',
         "Whenever a player casts a spell, if it's not their turn, this creature deals 4 damage to them.", ("4", "3"), 'R'),
    real('Price of Glory', '{2}{R}', 3, 'Enchantment',
         "Whenever a player taps a land for mana, if it's not that player's turn, destroy that land.", None, 'R'),
    real("Test Soldier", "{1}{W}", 2, "Creature — Human Soldier", "", ("1", "1"), "W"),
    real("Test Giant", "{5}", 5, "Creature — Giant", "", ("5", "5")),
    real("Test Dinosaur", "{R}", 1, "Creature — Dinosaur", "Haste", ("2", "2"), "R"),
    real("Test Rogue", "{B}", 1, "Creature — Human Rogue", "Haste", ("2", "2"), "B"),
    real("Test Swamp", "", 0, "Basic Land — Swamp", "({T}: Add {B}.)", None),
    real("Test Black Spell", "{B}", 1, "Instant", "You gain 1 life.", None, "B"),
    real("Test Mill", "{U}", 1, "Sorcery", "Target player mills three cards.", None, "U"),
    real("Test Discard", "{B}", 1, "Sorcery", "Target player discards a card.", None, "B"),
    real("Test Solring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", None),
    real('Brimaz, King of Oreskos', '{1}{W}{W}', 3, 'Legendary Creature — Cat Soldier',
         "Vigilance\nWhenever Brimaz attacks, create a 1/1 white Cat Soldier creature token with vigilance that's attacking.\nWhenever Brimaz blocks a creature, create a 1/1 white Cat Soldier creature token with vigilance that's blocking that creature.", ("3", "4"), 'W'),
    real('Hapatra, Vizier of Poisons', '{B}{G}', 2, 'Legendary Creature — Human Cleric',
         'Whenever Hapatra deals combat damage to a player, you may put a -1/-1 counter on target creature.\nWhenever you put one or more -1/-1 counters on a creature, create a 1/1 green Snake creature token with deathtouch.', ("2", "2"), 'BG'),
    real('Nest of Scarabs', '{2}{B}', 3, 'Enchantment',
         'Whenever you put one or more -1/-1 counters on a creature, create that many 1/1 black Insect creature tokens.', None, 'B'),
    real("Test Bounce", "{U}", 1, "Sorcery", "Return target creature to its owner's hand.", None, "U"),
    real("Test Burst", "{R}", 1, "Instant", "Test Burst deals 1 damage to any target.", None, "R"),
]

NAMES = ["Torens, Fist of the Angels", "Dour Port-Mage", "Glowing One", "Screeching Scorchbeast", "Staff of the Death Magus",
         "Rug of Smothering", "Hapatra, Vizier of Poisons", "Nest of Scarabs", "Path of Discovery", "Necropotence", "Prosperous Thief", "Forsaken Monument", "Parhelion II",
         "Poetic Ingenuity", "Scytheclaw Raptor", "Price of Glory"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, pid="p1", **m):
    spell = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=spell.id)


def ch(s, card):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def test_torens_token_has_training(cards):
    # 702.149a: the token is created with the keyword, so it has the triggered ability
    s = build(cards, ["Torens, Fist of the Angels", "Test Giant"], [])
    put(s, "Torens, Fist of the Angels")
    cast(s, "Test Giant", C=5)
    answer(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == "Human Soldier")
    assert "training" in [k for ab in ch(s, token).abilities for k in ab.keywords]
    check(s)


def test_leaving_without_dying_draws_but_dying_does_not(cards):
    s = build(cards, ["Dour Port-Mage", "Test Soldier", "Test Bounce"], [])
    put(s, "Dour Port-Mage")
    soldier = put(s, "Test Soldier")
    hand = len(zone(s.state, "p1", "hand"))
    cast(s, "Test Bounce", U=1)  # bounced: leaves without dying
    answer(s, soldier.id)
    assert len(zone(s.state, "p1", "hand")) == hand + 2  # the soldier and the drawn card
    check(s)
    s = build(cards, ["Dour Port-Mage", "Test Soldier"], [])
    put(s, "Dour Port-Mage")
    put(s, "Test Soldier")
    hand = len(zone(s.state, "p1", "hand"))
    kill(s, "Test Soldier")  # 700.4: it died
    assert len(zone(s.state, "p1", "hand")) == hand
    check(s)


def test_milled_nonland_cards_trigger_once_per_batch(cards):
    # 701.17a: Bob mills three; Glowing One gains 1 life for each nonland card, Scorchbeast makes that many Zombies (once a turn)
    s = build(cards, ["Glowing One", "Screeching Scorchbeast", "Test Mill"], ["Test Giant", "Test Soldier", "Test Swamp"])
    put(s, "Glowing One")
    put(s, "Screeching Scorchbeast")
    top = s.state.zones["p2:library"][:3]
    nonland = sum(1 for c in top if s.state.cards[c].name not in ("Island", "Test Swamp"))
    assert nonland >= 1
    cast(s, "Test Mill", U=1)
    answer(s, "p2")
    answer(s)
    assert life(s, "p1") == 40 + nonland
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie Mutant" and c.zone == "p1:battlefield"]
    assert len(zombies) in (0, nonland)  # "you may": declined by default or all of them
    check(s)


def test_cast_black_spell_or_swamp_enters_gains_life(cards):
    s = build(cards, ["Staff of the Death Magus", "Test Black Spell", "Test Swamp"], [])
    put(s, "Staff of the Death Magus")
    cast(s, "Test Black Spell", B=1)
    answer(s)
    assert life(s, "p1") == 42  # the spell's own 1 and the Staff's 1
    act(s, "p1", type="play_land", card_id=to_hand(s, "Test Swamp").id)
    answer(s)
    assert life(s, "p1") == 43
    check(s)


def test_they_lose_1_life_for_each_spell_they_have_cast_this_turn(cards):
    # Rug of Smothering: the casting player (event player) and the count of that player's spells this turn
    s = build(cards, ["Rug of Smothering", "Test Burst", "Test Burst"], [])
    put(s, "Rug of Smothering")
    for _ in (1, 2):
        cast(s, "Test Burst", R=1)
        answer(s, "p2")
        answer(s)
    assert life(s, "p1") == 40 - 1 - 2
    check(s)


@pytest.mark.parametrize("land_on_top", [True, False])
def test_path_of_discovery_explores(cards, land_on_top):
    # 701.44a: a land goes to the hand; otherwise the creature gets a +1/+1 counter (the nonland card stays or goes to the graveyard)
    s = build(cards, ["Path of Discovery", "Test Soldier", "Test Giant"], [])
    put(s, "Path of Discovery")
    pick = next(c for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:library"
                and c.name == ("Forest" if land_on_top else "Test Giant"))
    act(s, "p1", type="move", card_ids=[pick.id], to={"player": "p1", "zone": "library"}, position="top")
    top = s.state.cards[pick.id]
    cast(s, "Test Soldier", W=1, C=1)
    answer(s)
    answer(s, "keep")
    soldier = card_named(s, "Test Soldier")
    if land_on_top:
        assert s.state.cards[top.id].zone == "p1:hand" and not soldier.counters.get("+1/+1")
    else:
        assert soldier.counters.get("+1/+1") == 1 and s.state.cards[top.id].zone == "p1:library"
    check(s)


def test_necropotence_exiles_the_discarded_card(cards):
    s = build(cards, ["Necropotence", "Test Discard", "Test Soldier"], [])
    put(s, "Necropotence")
    soldier = to_hand(s, "Test Soldier")
    cast(s, "Test Discard", B=1)
    answer(s, "p1")
    answer(s)
    assert not any(c.name == "Test Soldier" and c.zone == "p1:graveyard" for c in s.state.cards.values())
    assert s.state.cards[soldier.id].zone == "p1:exile"
    check(s)


def test_one_or_more_dinosaurs_attack_makes_that_many_treasures(cards):
    # Poetic Ingenuity: one trigger for the batch, as many Treasures as Dinosaurs attacked (not the Wolf)
    s = combat_build(cards, "Poetic Ingenuity")
    combat_put(s, "Poetic Ingenuity")
    rex = token_of(s, "p1", "Rex", "Token Creature — Dinosaur", "2/2", "Haste")
    raptor = token_of(s, "p1", "Raptor", "Token Creature — Dinosaur", "2/2", "Haste")
    wolf = token_of(s, "p1", "Wolf", "Token Creature — Wolf", "2/2", "Haste")
    to_attack(s)
    declare(s, (rex, "p2"), (raptor, "p2"), (wolf, "p2"))
    to_blocks(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 2
    check(s)


def test_brimaz_token_enters_attacking_and_untapped(cards):
    # 508.4: "that's attacking" (not "tapped and attacking"): the token is attacking, and isn't tapped
    s = combat_build(cards, "Brimaz, King of Oreskos")
    brimaz = combat_put(s, "Brimaz, King of Oreskos")
    to_attack(s, 3)
    declare(s, (brimaz, "p2"))
    to_blocks(s)
    cats = [c for c in s.state.cards.values() if c.name == "Cat Soldier" and c.zone == "p1:battlefield"]
    assert len(cats) == 1 and attacking(s, cats[0]) == "p2" and not cats[0].tapped
    check(s)


def test_ninja_or_rogue_creatures_dealing_combat_damage_make_one_treasure(cards):
    s = combat_build(cards, "Prosperous Thief")
    combat_put(s, "Prosperous Thief")
    a = token_of(s, "p1", "Ninja", "Token Creature — Human Ninja", "2/2", "Flying\nHaste")
    b = token_of(s, "p1", "Rogue", "Token Creature — Human Rogue", "2/2", "Flying\nHaste")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p2"))
    through_combat(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 1
    check(s)


def test_tapping_for_colorless_adds_one_more_colorless(cards):
    from app.rules.casting import mana_abilities

    s = build(cards, ["Forsaken Monument", "Test Solring"], [])
    put(s, "Forsaken Monument")
    sol, forest = put(s, "Test Solring"), next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    sol_opts = dict(mana_abilities(s.state, s.state.cards[sol.id], s.cards))
    forest_opts = dict(mana_abilities(s.state, s.state.cards[forest.id], s.cards))
    assert sol_opts[0].options == (("C", "C", "C"),)  # {C}{C}: one trigger for the tapping, one additional {C}
    assert forest_opts[0].options == (("G",),)  # {G}: not colorless
    check(s)


def test_spell_cast_out_of_turn_deals_4_damage_to_that_player(cards):
    # Scytheclaw Raptor: "if it's not their turn" is the casting player's, checked as it triggers and resolves (603.4)
    s = build(cards, ["Scytheclaw Raptor", "Test Burst"], ["Test Black Spell"])
    put(s, "Scytheclaw Raptor")
    to_hand(s, "Test Black Spell", "p2")
    burst = to_hand(s, "Test Burst")
    mana(s, "p2", B=1)  # (so that Bob can respond)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])  # Alice's own spell on her own turn: nothing triggers
    assert life(s, "p1") == 40 and s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Test Black Spell", "p2").id)  # Bob responds during Alice's turn
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 40 - 4 + 1 - 1)
    check(s)


def test_land_tapped_out_of_turn_is_destroyed(cards):
    # Price of Glory: "that land" is the land tapped for mana; the other player's own turn spares it
    s = build(cards, ["Price of Glory", "Test Burst"], ["Test Black Spell"])
    put(s, "Price of Glory")
    mine = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    theirs = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=0)
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield"
    burst = to_hand(s, "Test Burst")
    to_hand(s, "Test Black Spell", "p2")
    mana(s, "p2", B=1)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])  # (Bob gets priority during Alice's turn)
    act(s, "p2", type="activate_ability", card_id=theirs.id, ability=0)
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    check(s)


def block(s, blocker, attacker, pid="p2"):
    act(s, pid, type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])


def test_wither_counters_are_put_by_the_sources_controller(cards):
    # 120.3d: Alice's wither creature deals damage to Bob's blocker, so Alice puts the -1/-1 counters (Nest: that many Insects, once
    # for the batch); Bob's wither blocker damaging Alice's attacker is Bob putting them, which Alice's Nest does not see
    s = combat_build(cards, "Nest of Scarabs")
    combat_put(s, "Nest of Scarabs")
    viper = token_of(s, "p1", "Viper", "Token Creature — Snake", "2/2", "Wither\nHaste")
    wall = next(c for c in s.state.cards.values() if c.name == "Wall p2")
    to_attack(s)
    declare(s, (viper, "p2"))
    to_blocks(s)
    block(s, wall, viper)
    through_combat(s)
    assert s.state.cards[wall.id].counters.get("-1/-1") == 2
    assert sum(1 for c in s.state.cards.values() if c.name == "Insect" and c.zone == "p1:battlefield") == 2
    check(s)
    s = combat_build(cards, "Nest of Scarabs")
    combat_put(s, "Nest of Scarabs")
    ogre = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "2/2", "Haste")
    sting = token_of(s, "p2", "Stinger", "Token Creature — Insect", "1/4", "Wither")
    to_attack(s)
    declare(s, (ogre, "p2"))
    to_blocks(s)
    block(s, sting, ogre)
    through_combat(s)
    assert s.state.cards[ogre.id].counters.get("-1/-1") == 1
    assert not any(c.name == "Insect" for c in s.state.cards.values()), [(c.name, c.zone) for c in s.state.cards.values() if c.name == "Insect"]
    check(s)
