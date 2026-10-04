"""Wave 5A: mana-ability riders and untap riders, researched against CR 2026-09-25.

* 605.1a / 605.3b: an activated mana ability resolves as it is activated: its amounts ("for each Elf on the
  battlefield", "where X is …") and its colors ("any color among legendary creatures and planeswalkers you control",
  "for each color among permanents you control") are read then, and its other effects ("You gain 2 life.", "Each
  opponent gains 1 life.") happen in the same resolution. A cost that moves a card to or from a library ("{T}, Mill a
  card: Add {C}.") makes it an ordinary activated ability that uses the stack.

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.casting import mana_abilities
from app.rules.mana import parse_mana_ability
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, find, put

EXTRA = [
    card('The Great Henge', set_code="tst", number="A01", mana_cost='{7}{G}{G}', cmc=9.0, type_line='Legendary Artifact', oracle_text='This spell costs {X} less to cast, where X is the greatest power among creatures you control.\n{T}: Add {G}{G}. You gain 2 life.\nWhenever a nontoken creature you control enters, put a +1/+1 counter on it and draw a card.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Pristine Talisman', set_code="tst", number="A02", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='{T}: Add {C}. You gain 1 life.', colors=[], color_identity=[]),  # noqa: E501
    card('Grove of the Burnwillows', set_code="tst", number="A03", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add {R} or {G}. Each opponent gains 1 life.', colors=[], color_identity=['G', 'R']),  # noqa: E501
    card('Mox Amber', set_code="tst", number="A04", mana_cost='{0}', cmc=0.0, type_line='Legendary Artifact', oracle_text='{T}: Add one mana of any color among legendary creatures and planeswalkers you control.', colors=[], color_identity=[]),  # noqa: E501
    card('Plaza of Heroes', set_code="tst", number="A05", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a legendary spell.\n{T}: Add one mana of any color among legendary permanents you control.\n{3}, {T}, Exile this land: Target legendary creature gains hexproof and indestructible until end of turn.', colors=[], color_identity=[]),  # noqa: E501
    card('The Grey Havens', set_code="tst", number="A06", mana_cost='', cmc=0.0, type_line='Legendary Land', oracle_text='When The Grey Havens enters, scry 1.\n{T}: Add {C}.\n{T}: Add one mana of any color among legendary creature cards in your graveyard.', colors=[], color_identity=[], keywords=['Scry']),  # noqa: E501
    card('Bloom Tender', set_code="tst", number="A07", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='Vivid — {T}: For each color among permanents you control, add one mana of that color.', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Vivid']),  # noqa: E501
    card('Faeburrow Elder', set_code="tst", number="A08", mana_cost='{1}{G}{W}', cmc=3.0, type_line='Creature — Treefolk Druid', oracle_text='Vigilance\nThis creature gets +1/+1 for each color among permanents you control.\n{T}: For each color among permanents you control, add one mana of that color.', power='0', toughness='0', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Vigilance']),  # noqa: E501
    card('Priest of Titania', set_code="tst", number="A09", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='{T}: Add {G} for each Elf on the battlefield.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Cabal Stronghold', set_code="tst", number="A10", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{3}, {T}: Add {B} for each basic Swamp you control.', colors=[], color_identity=['B']),  # noqa: E501
    card('Crypt of Agadeem', set_code="tst", number="A11", mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\n{T}: Add {B}.\n{2}, {T}: Add {B} for each black creature card in your graveyard.', colors=[], color_identity=['B']),  # noqa: E501
    card('Overgrown Battlement', set_code="tst", number="A12", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Wall', oracle_text='Defender\n{T}: Add {G} for each creature you control with defender.', power='0', toughness='4', colors=['G'], color_identity=['G'], keywords=['Defender']),  # noqa: E501
    card('Kydele, Chosen of Kruphix', set_code="tst", number="A13", mana_cost='{2}{G}{U}', cmc=4.0, type_line='Legendary Creature — Human Wizard', oracle_text="{T}: Add {C} for each card you've drawn this turn.\nPartner (You can have two commanders if both have partner.)", power='2', toughness='3', colors=['G', 'U'], color_identity=['G', 'U'], keywords=['Partner']),  # noqa: E501
    card('Relic of Sauron', set_code="tst", number="A14", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='{T}: Add two mana in any combination of {U}, {B}, and/or {R}.\n{3}, {T}: Draw two cards, then discard a card.', colors=[], color_identity=['B', 'R', 'U']),  # noqa: E501
    card('Firemind Vessel', set_code="tst", number="A15", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='This artifact enters tapped.\n{T}: Add two mana of different colors.', colors=[], color_identity=[]),  # noqa: E501
    card('Wirewood Channeler', set_code="tst", number="A16", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Druid', oracle_text='{T}: Add X mana of any one color, where X is the number of Elves on the battlefield.', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Baldur's Gate", set_code="tst", number="A17", mana_cost='', cmc=0.0, type_line='Legendary Land — Gate', oracle_text='{T}: Add {C}.\n{2}, {T}: Add X mana of any one color, where X is the number of other Gates you control.', colors=[], color_identity=[]),  # noqa: E501
    card('Millikin', set_code="tst", number="A18", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Construct', oracle_text='{T}, Mill a card: Add {C}. (Activate only as an instant. To mill a card, put the top card of your library into your graveyard.)', power='0', toughness='1', colors=[], color_identity=[], keywords=['Mill']),  # noqa: E501
    card("Karametra's Acolyte", set_code="tst", number="A19", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Druid', oracle_text='{T}: Add an amount of {G} equal to your devotion to green. (Each {G} in the mana costs of permanents you control counts toward your devotion to green.)', power='1', toughness='4', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Mirari's Wake", set_code="tst", number="B01", mana_cost='{3}{G}{W}', cmc=5.0, type_line='Enchantment', oracle_text='Creatures you control get +1/+1.\nWhenever you tap a land for mana, add one mana of any type that land produced.', colors=['G', 'W'], color_identity=['G', 'W']),  # noqa: E501
    card('Kinnan, Bonder Prodigy', set_code="tst", number="B02", mana_cost='{G}{U}', cmc=2.0, type_line='Legendary Creature — Human Druid', oracle_text='Whenever you tap a nonland permanent for mana, add one mana of any type that permanent produced.\n{5}{G}{U}: Look at the top five cards of your library. You may put a non-Human creature card from among them onto the battlefield. Put the rest on the bottom of your library in a random order.', power='2', toughness='2', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Badgermole Cub', set_code="tst", number="B03", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Badger Mole', oracle_text="When this creature enters, earthbend 1. (Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it. When it dies or is exiled, return it to the battlefield tapped.)\nWhenever you tap a creature for mana, add an additional {G}.", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Earthbend']),  # noqa: E501
    card('Regal Behemoth', set_code="tst", number="B04", mana_cost='{4}{G}{G}', cmc=6.0, type_line='Creature — Dinosaur', oracle_text="Trample\nWhen this creature enters, you become the monarch.\nWhenever you tap a land for mana while you're the monarch, add an additional one mana of any color.", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('High Tide', set_code="tst", number="B05", mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Until end of turn, whenever a player taps an Island for mana, that player adds an additional {U}.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Mana Flare', set_code="tst", number="B06", mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment', oracle_text='Whenever a player taps a land for mana, that player adds one mana of any type that land produced.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Nirkana Revenant', set_code="tst", number="B07", mana_cost='{4}{B}{B}', cmc=6.0, type_line='Creature — Vampire Shade', oracle_text='Whenever you tap a Swamp for mana, add an additional {B}.\n{B}: This creature gets +1/+1 until end of turn.', power='4', toughness='4', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Groundchuck & Dirtbag', set_code="tst", number="B08", mana_cost='{4}{G}{G}', cmc=6.0, type_line='Legendary Creature — Ox Mole Mutant', oracle_text='Trample\nWhenever you tap a land for mana, add {G}.', power='8', toughness='8', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('Eldrazi Temple', set_code="tst", number="B09", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi.', colors=[], color_identity=[]),  # noqa: E501
    card('Snap', set_code="tst", number="C01", mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Return target creature to its owner's hand. Untap up to two lands.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Peregrine Drake', set_code="tst", number="C02", mana_cost='{4}{U}', cmc=5.0, type_line='Creature — Drake', oracle_text='Flying\nWhen this creature enters, untap up to five lands.', power='2', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flying']),  # noqa: E501
    card('Seedborn Muse', set_code="tst", number="C03", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Spirit', oracle_text="Untap all permanents you control during each other player's untap step.", power='2', toughness='4', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Unwinding Clock', set_code="tst", number="C04", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text="Untap all artifacts you control during each other player's untap step.", colors=[], color_identity=[]),  # noqa: E501
    card("Bender's Waterskin", set_code="tst", number="C05", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="Untap this artifact during each other player's untap step.\n{T}: Add one mana of any color.", colors=[], color_identity=[]),  # noqa: E501
    card('Colossus of Sardia', set_code="tst", number="C06", mana_cost='{9}', cmc=9.0, type_line='Artifact Creature — Golem', oracle_text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nThis creature doesn't untap during your untap step.\n{9}: Untap this creature. Activate only during your upkeep.", power='9', toughness='9', colors=[], color_identity=[], keywords=['Trample']),  # noqa: E501
    card('Frantic Search', set_code="tst", number="C07", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text='Draw two cards, then discard two cards. Untap up to three lands.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Murkfiend Liege', set_code="tst", number="C08", mana_cost='{2}{G/U}{G/U}{G/U}', cmc=5.0, type_line='Creature — Horror', oracle_text="Other green creatures you control get +1/+1.\nOther blue creatures you control get +1/+1.\nUntap all green and/or blue creatures you control during each other player's untap step.", power='4', toughness='4', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Simian Spirit Guide', set_code="tst", number="D01", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Ape Spirit', oracle_text='Exile this card from your hand: Add {R}.', power='2', toughness='2', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Rite of Flame', set_code="tst", number="D02", mana_cost='{R}', cmc=1.0, type_line='Sorcery', oracle_text='Add {R}{R}, then add {R} for each card named Rite of Flame in each graveyard.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Accumulated Knowledge', set_code="tst", number="D03", mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text='Draw a card, then draw cards equal to the number of cards named Accumulated Knowledge in all graveyards.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Forbidden Orchard', set_code="tst", number="F01", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add one mana of any color.\nWhenever you tap this land for mana, target opponent creates a 1/1 colorless Spirit creature token.', colors=[], color_identity=[]),  # noqa: E501
    card('Manabarbs', set_code="tst", number="F02", mana_cost='{3}{R}', cmc=4.0, type_line='Enchantment', oracle_text='Whenever a player taps a land for mana, this enchantment deals 1 damage to that player.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Zhur-Taa Druid', set_code="tst", number="F03", mana_cost='{R}{G}', cmc=2.0, type_line='Creature — Human Druid', oracle_text='{T}: Add {G}.\nWhenever you tap this creature for mana, it deals 1 damage to each opponent.', power='1', toughness='1', colors=['G', 'R'], color_identity=['G', 'R']),  # noqa: E501
    card('Twitching Doll', set_code="tst", number="G01", mana_cost='{1}{G}', cmc=2.0, type_line='Artifact Creature — Spider Toy', oracle_text='{T}: Add one mana of any color. Put a nest counter on this creature.\n{T}, Sacrifice this creature: Create a 2/2 green Spider creature token with reach for each counter on this creature. Activate only as a sorcery.', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Gemstone Mine', set_code="tst", number="G02", mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters with three mining counters on it.\n{T}, Remove a mining counter from this land: Add one mana of any color. If there are no mining counters on this land, sacrifice it.', colors=[], color_identity=[]),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] != "Accumulated Knowledge"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    """Replay rebuilds the same table, a save/load round trip keeps it, and a session rebuilt from the history too."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def next_main(s):
    """Play on to Alice's next first main phase (her permanents are no longer summoning sick); nobody attacks."""
    act(s, "p1", type="pass_priority")
    for _ in range(80):
        if s.state.turn.active_player == "p1" and s.state.turn.phase == "main1" and s.state.turn.number > 1:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blockers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    raise AssertionError("never reached Alice's next main phase")


def options(s, c):
    return dict(mana_abilities(s.state, s.state.cards[c.id], s.cards))


def choose(s, label):
    d = s.state.rules.decision
    assert d is not None, "expected a choice"
    pick = next(o for o in d.options if o.label == label)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])


# -- coverage ------------------------------------------------------------------------------------------------------
def test_the_cards_are_full():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            level = coverage.of_characteristics(characteristics(c["name"], c["type_line"], c["oracle_text"]))
            assert level.level == "FULL", (c["name"], level.manual_parts)


@pytest.mark.parametrize("text", [
    "{T}: Add X mana in any combination of colors, where X is the number of creatures you control with defender.",
    "{T}: Add {G} for each creature that entered this turn under target player's control.",
    "{T}: Add X mana of any one color, where X is the number of cards in target opponent's hand.",
    "{T}: Add {R}. You gain 1 life for each creature you control.",
    "{T}: Add one mana of any color among cards in target opponent's graveyard.",
    "{T}: Add one mana of any color among permanents your opponents control or cards in exile.",
])
def test_refused_wordings(text):
    assert parse_mana_ability(text) is None


# -- riders: life gain -----------------------------------------------------------------------------------------------
def test_great_henge_adds_two_green_and_gains_two_life(cards):
    s = build(cards, [(1, "The Great Henge"), (1, "Pristine Talisman"), (8, "Forest")])
    henge = put(s, "The Great Henge", "battlefield")
    talisman = put(s, "Pristine Talisman", "battlefield")
    life = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=henge.id, ability=1)
    assert s.state.players["p1"].mana == {"G": 2} and s.state.players["p1"].life == life + 2
    assert not s.state.zones.get("stack")  # 605.3b: no stack
    act(s, "p1", type="activate_ability", card_id=talisman.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 2, "C": 1} and s.state.players["p1"].life == life + 3
    roundtrip(s)


def test_pristine_talisman_used_by_the_payer_gains_life(cards):
    """The auto-payer taps it for {C} — the life gain rides along (one resolution)."""
    s = build(cards, [(1, "Pristine Talisman"), (1, "Millikin"), (8, "Forest")])
    talisman = put(s, "Pristine Talisman", "battlefield")
    life = s.state.players["p1"].life
    millikin = find(s, "Millikin")
    act(s, "p1", type="move", card_ids=[millikin.id], to={"player": "p1", "zone": "hand"})
    forest = put(s, "Forest", "battlefield")
    act(s, "p1", type="cast_spell", card_id=millikin.id)  # {2}: the Forest and the Talisman
    assert s.state.cards[talisman.id].tapped and s.state.cards[forest.id].tapped
    assert s.state.players["p1"].life == life + 1
    roundtrip(s)


def test_grove_of_the_burnwillows_each_opponent_gains_one(cards):
    s = build(cards, [(1, "Grove of the Burnwillows"), (9, "Forest")])
    grove = put(s, "Grove of the Burnwillows", "battlefield")
    mine, theirs = s.state.players["p1"].life, s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=grove.id, ability=1, mana_choice="R")
    assert s.state.players["p1"].mana == {"R": 1}
    assert s.state.players["p2"].life == theirs + 1 and s.state.players["p1"].life == mine
    roundtrip(s)


# -- counted mana -----------------------------------------------------------------------------------------------------
def test_priest_of_titania_counts_every_elf_on_the_battlefield(cards):
    s = build(cards, [(1, "Priest of Titania"), (1, "Llanowar Elves"), (8, "Forest")], bob=[(1, "Wirewood Channeler"), (9, "Island")])
    priest = put(s, "Priest of Titania", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    put(s, "Wirewood Channeler", "battlefield", pid="p2")
    next_main(s)
    assert options(s, priest)[0].options == (("G", "G", "G"),)  # its own, Alice's other Elf and Bob's (Priest ruling)
    act(s, "p1", type="activate_ability", card_id=priest.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 3}
    roundtrip(s)


def test_cabal_stronghold_counts_basic_swamps_and_pays_its_activation(cards):
    s = build(cards, [(1, "Cabal Stronghold"), (2, "Swamp"), (3, "Forest")])
    stronghold = put(s, "Cabal Stronghold", "battlefield")
    for c in [c for c in s.state.cards.values() if c.name == "Swamp" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    assert options(s, stronghold)[1].options == (("B", "B"),)
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=stronghold.id, ability=1)
    assert s.state.players["p1"].mana == {"B": 2}
    roundtrip(s)


def test_crypt_of_agadeem_counts_black_creature_cards_in_your_graveyard(cards):
    s = build(cards, [(1, "Crypt of Agadeem"), (2, "Twisted Abomination"), (7, "Forest")], bob=[(9, "Island")])
    crypt = put(s, "Crypt of Agadeem", "battlefield")
    assert 2 not in options(s, crypt)  # none: it would add no mana (605.2)
    act(s, "p1", type="create_token", player="p1", token={"name": "Shade", "type_line": "Token Creature — Shade",
                                                         "power": "1", "toughness": "1", "colors": ["B"], "text": ""})
    assert 2 not in options(s, crypt)  # a token on the battlefield isn't a card in your graveyard
    for c in [c for c in s.state.cards.values() if c.name == "Twisted Abomination"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    assert options(s, crypt)[2].options == (("B", "B"),)
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=crypt.id, ability=2)
    assert s.state.players["p1"].mana == {"B": 2}
    roundtrip(s)


def test_kydele_counts_the_cards_you_drew_this_turn(cards):
    s = build(cards, [(1, "Kydele, Chosen of Kruphix"), (9, "Forest")])
    kydele = put(s, "Kydele, Chosen of Kruphix", "battlefield")
    next_main(s)  # Alice drew one card in her draw step
    assert options(s, kydele)[0].options == (("C",),)
    roundtrip(s)


def test_wirewood_channeler_x_of_one_color(cards):
    s = build(cards, [(1, "Wirewood Channeler"), (1, "Llanowar Elves"), (8, "Forest")])
    channeler = put(s, "Wirewood Channeler", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    next_main(s)
    act(s, "p1", type="activate_ability", card_id=channeler.id, ability=0, mana_choice=None)
    choose(s, "{U}{U}")
    assert s.state.players["p1"].mana == {"U": 2}
    roundtrip(s)


def test_baldurs_gate_counts_other_gates(cards):
    s = build(cards, [(1, "Baldur's Gate"), (9, "Forest")])
    gate = put(s, "Baldur's Gate", "battlefield")
    assert 1 not in options(s, gate)  # no other Gates: it would add no mana
    roundtrip(s)


def test_karametras_acolyte_devotion(cards):
    s = build(cards, [(1, "Karametra's Acolyte"), (1, "Priest of Titania"), (8, "Forest")])
    acolyte = put(s, "Karametra's Acolyte", "battlefield")
    put(s, "Priest of Titania", "battlefield")
    assert options(s, acolyte)[0].options == (("G", "G"),)  # {3}{G} and {1}{G}: devotion 2 (700.5)
    roundtrip(s)


# -- colors among -----------------------------------------------------------------------------------------------------
def test_mox_amber_and_plaza_of_heroes_read_legendary_permanents(cards):
    s = build(cards, [(1, "Mox Amber"), (1, "Plaza of Heroes"), (1, "Kydele, Chosen of Kruphix"), (7, "Forest")])
    mox = put(s, "Mox Amber", "battlefield")
    plaza = put(s, "Plaza of Heroes", "battlefield")
    assert not options(s, mox)  # only itself: a colorless legendary artifact (ruling 2018-04-27)
    assert 2 not in options(s, plaza)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=mox.id, ability=0)
    put(s, "Kydele, Chosen of Kruphix", "battlefield")
    assert options(s, mox)[0].options == (("U",), ("G",))
    assert options(s, plaza)[2].options == (("U",), ("G",))
    act(s, "p1", type="activate_ability", card_id=mox.id, ability=0, mana_choice="U")
    assert s.state.players["p1"].mana == {"U": 1}
    roundtrip(s)


def test_the_grey_havens_reads_legendary_creature_cards_in_your_graveyard(cards):
    s = build(cards, [(1, "The Grey Havens"), (1, "Kydele, Chosen of Kruphix"), (8, "Forest")])
    havens = put(s, "The Grey Havens", "battlefield")
    pass_until_stack_empty(s)  # (its scry 1)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert 2 not in options(s, havens)
    put(s, "Kydele, Chosen of Kruphix", "graveyard")
    assert options(s, havens)[2].options == (("U",), ("G",))
    roundtrip(s)


def test_bloom_tender_adds_one_of_each_color_among_your_permanents(cards):
    s = build(cards, [(1, "Bloom Tender"), (1, "Faeburrow Elder"), (1, "Kydele, Chosen of Kruphix"), (7, "Forest")])
    tender = put(s, "Bloom Tender", "battlefield")
    put(s, "Forest", "battlefield")  # (a land is colorless: no {C}, ruling 2025-11-17)
    next_main(s)
    assert options(s, tender)[0].options == (("G",),)
    put(s, "Kydele, Chosen of Kruphix", "battlefield")
    put(s, "Faeburrow Elder", "battlefield")
    act(s, "p1", type="activate_ability", card_id=tender.id, ability=0)
    assert s.state.players["p1"].mana == {"W": 1, "U": 1, "G": 1}
    roundtrip(s)


# -- fixed combinations ---------------------------------------------------------------------------------------------------
def test_relic_of_sauron_and_firemind_vessel(cards):
    s = build(cards, [(1, "Relic of Sauron"), (1, "Firemind Vessel"), (8, "Forest")])
    relic = put(s, "Relic of Sauron", "battlefield")
    vessel = put(s, "Firemind Vessel", "battlefield")
    assert set(options(s, relic)[0].options) == {("U", "U"), ("U", "B"), ("U", "R"), ("B", "B"), ("B", "R"), ("R", "R")}
    found = options(s, vessel)[1].options
    assert len(found) == 10 and all(a != b for a, b in found)  # two different colors
    act(s, "p1", type="activate_ability", card_id=relic.id, ability=0)
    choose(s, "{B}{R}")
    assert s.state.players["p1"].mana == {"B": 1, "R": 1}
    roundtrip(s)


# -- 605.1a: a library-moving cost is not a mana ability --------------------------------------------------------------------
def test_millikin_uses_the_stack(cards):
    s = build(cards, [(1, "Millikin"), (9, "Forest")])
    millikin = put(s, "Millikin", "battlefield")
    next_main(s)
    library = len(s.state.zones["p1:library"])
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="activate_ability", card_id=millikin.id, ability=0)
    assert len(s.state.zones["p1:library"]) == library - 1  # milled as a cost
    assert s.state.zones.get("stack")  # 605.1a: not a mana ability, so it waits on the stack
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana.get("C") == 1
    roundtrip(s)


# -- triggered mana abilities on tapping for mana (106.12a, 605.1b, 605.4a) ------------------------------------------------
def lands(s, name, pid="p1", n=1):
    out = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith("battlefield")][:n]
    for c in out:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return out


def test_mirraris_wake_adds_a_type_the_land_produced(cards):
    s = build(cards, [(1, "Mirari's Wake"), (1, "Grove of the Burnwillows"), (1, "Eldrazi Temple"), (1, "Grizzly Bears"),
                      (6, "Forest")])
    put(s, "Mirari's Wake", "battlefield")
    forest, = lands(s, "Forest")
    grove = put(s, "Grove of the Burnwillows", "battlefield")
    temple = put(s, "Eldrazi Temple", "battlefield")
    island, = lands(s, "Island", "p2")
    assert options(s, forest)[0].options == (("G", "G"),)
    assert options(s, grove)[0].options == (("C", "C"),)
    assert options(s, grove)[1].options == (("R", "R"), ("G", "G"))  # one of the types that land produced
    assert list(options(s, temple)) == [0]  # its restricted {C}{C}: left to the player while the Wake applies
    assert options(s, island)[0].options == (("U",),)  # "you": only Alice's lands
    bears = find(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="tap", card_ids=[grove.id, temple.id], tapped=True)
    act(s, "p1", type="cast_spell", card_id=bears.id)  # {1}{G}: the one Forest pays it all (605.4a)
    assert s.state.cards[forest.id].tapped and s.state.cards[bears.id].zone != "p1:hand"
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


def test_mana_flare_gives_each_player_more_and_stacks(cards):
    s = build(cards, [(1, "Mana Flare"), (1, "Mirari's Wake"), (8, "Forest")])
    put(s, "Mana Flare", "battlefield")
    forest, = lands(s, "Forest")
    island, = lands(s, "Island", "p2")
    assert options(s, island)[0].options == (("U", "U"),)  # "that player adds"
    assert options(s, forest)[0].options == (("G", "G"),)
    put(s, "Mirari's Wake", "battlefield")
    assert options(s, forest)[0].options == (("G", "G", "G"),)  # two triggers, each adds one
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 3}
    roundtrip(s)


def test_kinnan_and_badgermole_cub_on_a_mana_creature(cards):
    s = build(cards, [(1, "Kinnan, Bonder Prodigy"), (1, "Badgermole Cub"), (1, "Llanowar Elves"), (7, "Forest")])
    put(s, "Kinnan, Bonder Prodigy", "battlefield")
    elves = put(s, "Llanowar Elves", "battlefield")
    forest, = lands(s, "Forest")
    assert options(s, elves)[0].options == (("G", "G"),)  # a nonland permanent: one more of a type it produced
    assert options(s, forest)[0].options == (("G",),)  # a land: not Kinnan's
    cub = find(s, "Badgermole Cub")
    act(s, "p1", type="move", card_ids=[cub.id], to={"player": "p1", "zone": "battlefield"})
    pass_until_stack_empty(s)
    if s.state.rules.decision is not None:  # (its earthbend target)
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        pass_until_stack_empty(s)
    next_main(s)
    assert options(s, elves)[0].options == (("G", "G", "G"),)
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 3}
    roundtrip(s)


def test_regal_behemoth_only_while_you_are_the_monarch(cards):
    s = build(cards, [(1, "Regal Behemoth"), (9, "Forest")])
    behemoth = find(s, "Regal Behemoth")
    act(s, "p1", type="move", card_ids=[behemoth.id], to={"player": "p1", "zone": "battlefield"})
    forest, = lands(s, "Forest")
    act(s, "p1", type="set_monarch", player="p2")
    assert options(s, forest)[0].options == (("G",),)
    act(s, "p1", type="set_monarch", player="p1")
    assert set(options(s, forest)[0].options) == {("G", c) for c in "WUBRG"}
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    choose(s, "{R}{G}")
    assert s.state.players["p1"].mana == {"R": 1, "G": 1}
    roundtrip(s)


def test_nirkana_revenant_and_groundchuck_read_the_land(cards):
    s = build(cards, [(1, "Nirkana Revenant"), (1, "Groundchuck & Dirtbag"), (2, "Swamp"), (6, "Forest")])
    put(s, "Nirkana Revenant", "battlefield")
    swamp, = lands(s, "Swamp")
    forest, = lands(s, "Forest")
    assert options(s, swamp)[0].options == (("B", "B"),) and options(s, forest)[0].options == (("G",),)
    put(s, "Groundchuck & Dirtbag", "battlefield")
    assert options(s, swamp)[0].options == (("B", "B", "G"),) and options(s, forest)[0].options == (("G", "G"),)
    roundtrip(s)


def test_high_tide_lasts_until_end_of_turn_for_every_player(cards):
    s = build(cards, [(1, "High Tide"), (5, "Island"), (4, "Forest")])
    tide = find(s, "High Tide")
    act(s, "p1", type="move", card_ids=[tide.id], to={"player": "p1", "zone": "hand"})
    mine, = lands(s, "Island")
    theirs, = lands(s, "Island", "p2")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=tide.id)
    pass_until_stack_empty(s)
    assert options(s, mine)[0].options == (("U", "U"),) and options(s, theirs)[0].options == (("U", "U"),)
    reloaded = GameSession(s.history.rebuild(), cards=s.cards)
    assert options(reloaded, mine)[0].options == (("U", "U"),)
    next_main(s)
    assert options(s, mine)[0].options == (("U",),)  # it ended with the turn (514.2)
    roundtrip(s)


# -- untap riders ----------------------------------------------------------------------------------------------------------
def to_bobs_main(s):
    """Play on to Bob's next first main phase; nobody attacks."""
    act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    for _ in range(80):
        if s.state.turn.active_player == "p2" and s.state.turn.phase == "main1":
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blockers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    raise AssertionError("never reached Bob's main phase")


def test_snap_untaps_up_to_two_lands_of_the_players_choice(cards):
    s = build(cards, [(1, "Snap"), (4, "Island"), (5, "Forest")])
    islands = lands(s, "Island", n=3)
    theirs, = lands(s, "Island", "p2")
    act(s, "p1", type="tap", card_ids=[c.id for c in islands], tapped=True)
    act(s, "p2", type="tap", card_ids=[theirs.id], tapped=True)
    act(s, "p1", type="create_token", player="p2", token={"name": "Wolf", "type_line": "Token Creature — Wolf",
                                                         "power": "2", "toughness": "2", "text": ""})
    wolf = next(c for c in s.state.cards.values() if c.name == "Wolf")
    snap = find(s, "Snap")
    act(s, "p1", type="move", card_ids=[snap.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=snap.id, targets=[wolf.id])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.max_choices == 2 and d.min_choices == 0
    assert {o.card_id for o in d.options} == {c.id for c in islands} | {theirs.id}  # any tapped land (no "you control")
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[islands[0].id, islands[1].id, islands[2].id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[islands[0].id, islands[1].id])
    assert not s.state.cards[islands[0].id].tapped and not s.state.cards[islands[1].id].tapped
    assert s.state.cards[islands[2].id].tapped and s.state.cards[theirs.id].tapped
    assert wolf.id not in s.state.cards or s.state.cards[wolf.id].zone != "p2:battlefield"
    roundtrip(s)


def test_peregrine_drake_enters_and_untaps_up_to_five(cards):
    s = build(cards, [(1, "Peregrine Drake"), (9, "Forest")])
    forest, other = lands(s, "Forest", n=2)
    act(s, "p1", type="tap", card_ids=[forest.id, other.id], tapped=True)
    drake = find(s, "Peregrine Drake")
    act(s, "p1", type="move", card_ids=[drake.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=drake.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {forest.id, other.id} and d.max_choices == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest.id])
    assert not s.state.cards[forest.id].tapped and s.state.cards[other.id].tapped
    roundtrip(s)


def test_seedborn_muse_untaps_during_each_other_players_untap_step(cards):
    s = build(cards, [(1, "Seedborn Muse"), (1, "Colossus of Sardia"), (8, "Forest")])
    muse = put(s, "Seedborn Muse", "battlefield")
    colossus = put(s, "Colossus of Sardia", "battlefield")
    a, b = lands(s, "Forest", n=2)
    theirs, = lands(s, "Island", "p2")
    act(s, "p1", type="tap", card_ids=[muse.id, colossus.id, a.id, b.id], tapped=True)
    act(s, "p2", type="tap", card_ids=[theirs.id], tapped=True)
    act(s, "p1", type="counter", card_ids=[b.id], kind="stun", delta=1)
    to_bobs_main(s)
    assert not s.state.cards[theirs.id].tapped  # Bob's own untap step
    assert not s.state.cards[muse.id].tapped and not s.state.cards[a.id].tapped
    # "doesn't untap during your untap step": this isn't Alice's untap step (Seedborn ruling 2004-10-04)
    assert not s.state.cards[colossus.id].tapped
    assert s.state.cards[b.id].tapped and "stun" not in s.state.cards[b.id].counters  # 122.1d
    roundtrip(s)


def test_unwinding_clock_and_benders_waterskin_untap_only_what_they_name(cards):
    s = build(cards, [(1, "Unwinding Clock"), (1, "Bender's Waterskin"), (8, "Forest")])
    clock = put(s, "Unwinding Clock", "battlefield")
    skin = put(s, "Bender's Waterskin", "battlefield")
    forest, = lands(s, "Forest")
    act(s, "p1", type="tap", card_ids=[clock.id, skin.id, forest.id], tapped=True)
    act(s, "p1", type="move", card_ids=[clock.id], to={"player": "p1", "zone": "hand"})  # only the Waterskin now
    to_bobs_main(s)
    assert not s.state.cards[skin.id].tapped and s.state.cards[forest.id].tapped
    roundtrip(s)


def test_unwinding_clock_untaps_artifacts_not_lands(cards):
    s = build(cards, [(1, "Unwinding Clock"), (1, "Pristine Talisman"), (8, "Forest")])
    clock = put(s, "Unwinding Clock", "battlefield")
    talisman = put(s, "Pristine Talisman", "battlefield")
    forest, = lands(s, "Forest")
    act(s, "p1", type="tap", card_ids=[clock.id, talisman.id, forest.id], tapped=True)
    to_bobs_main(s)
    assert not s.state.cards[clock.id].tapped and not s.state.cards[talisman.id].tapped
    assert s.state.cards[forest.id].tapped
    roundtrip(s)


# -- a mana ability activated from the hand (113.6m, 605.3a) ------------------------------------------------------------------
def test_simian_spirit_guide_from_the_hand_only(cards):
    s = build(cards, [(2, "Simian Spirit Guide"), (8, "Forest")])
    guide, other = [c for c in s.state.cards.values() if c.name == "Simian Spirit Guide"]
    act(s, "p1", type="move", card_ids=[guide.id, other.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:exile" and s.state.players["p1"].mana == {"R": 1}
    assert not s.state.zones.get("stack")  # 605.3b
    # on the battlefield it has no mana ability to use (its cost exiles it from the hand)
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})
    assert not options(s, other)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=other.id, ability=0)
    roundtrip(s)


def test_the_payer_never_exiles_a_spirit_guide_by_itself(cards):
    s = build(cards, [(1, "Simian Spirit Guide"), (1, "Rite of Flame"), (8, "Forest")])
    guide = find(s, "Simian Spirit Guide")
    rite = find(s, "Rite of Flame")
    act(s, "p1", type="move", card_ids=[guide.id, rite.id], to={"player": "p1", "zone": "hand"})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rite.id)  # {R}: no red source on the battlefield
    assert s.state.cards[guide.id].zone == "p1:hand"
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    act(s, "p1", type="cast_spell", card_id=rite.id)  # paid with the Guide's {R}
    pass_until_stack_empty(s)
    assert s.state.cards[rite.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {"R": 2}
    roundtrip(s)


# -- "for each card named ~ in each graveyard" --------------------------------------------------------------------------------
def test_rite_of_flame_counts_the_others_in_every_graveyard(cards):
    s = build(cards, [(2, "Rite of Flame"), (8, "Forest")], bob=[(1, "Rite of Flame"), (9, "Island")])
    rite, other = [c for c in s.state.cards.values() if c.name == "Rite of Flame" and c.owner == "p1"]
    bobs = next(c for c in s.state.cards.values() if c.name == "Rite of Flame" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[bobs.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[rite.id], to={"player": "p1", "zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=rite.id)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana == {"R": 4}  # {R}{R}, then one for each of the two in graveyards (not itself)
    roundtrip(s)


def test_named_counts_elsewhere_read_the_source_name():
    """-- amounts (wave 12C) -- "cards named ~" (selectors) counts the source's own name; the spell on the stack isn't one of them
    (tests/test_rules_wave12c_amounts.py plays Kindle)."""
    from tests.test_rules_scripts import ch as characteristics

    ak = next(c for c in EXTRA if c["name"] == "Accumulated Knowledge")
    level = coverage.of_characteristics(characteristics(ak["name"], ak["type_line"], ak["oracle_text"]))
    assert level.level == "FULL"


def test_spirit_guide_while_paying_for_a_spell(cards):
    """605.3a: a mana ability can be activated while paying — here from the hand, during the "tap your mana" prompt."""
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Simian Spirit Guide"), (1, "Rite of Flame"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # the table default: players tap their own mana
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")
    guide = find(s, "Simian Spirit Guide")
    rite = find(s, "Rite of Flame")
    act(s, "p1", type="move", card_ids=[guide.id, rite.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=rite.id)
    d = s.state.rules.decision
    assert d is not None and (d.resume or {}).get("step") == "pay_mana"
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:exile"
    assert s.state.cards[rite.id].zone != "p1:hand"  # paid: cast
    roundtrip(s)


# -- triggers on tapping for mana that use the stack (605.5a, 106.12a, 603.3) -------------------------------------------------------
def test_forbidden_orchard_gives_the_target_opponent_a_spirit(cards):
    s = build(cards, [(1, "Forbidden Orchard"), (9, "Forest")])
    orchard = put(s, "Forbidden Orchard", "battlefield")
    act(s, "p1", type="activate_ability", card_id=orchard.id, ability=0, mana_choice="W")
    assert s.state.players["p1"].mana == {"W": 1}  # the mana first (605.3b); the trigger waits for priority (603.3)
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == ["p2"]  # "target opponent" (115.1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    spirits = [c for c in s.state.cards.values() if c.name.startswith("Spirit") and c.controller == "p2"]
    assert len(spirits) == 1 and s.state.cards[spirits[0].id].zone == "p2:battlefield"
    roundtrip(s)


def test_manabarbs_when_the_payer_taps_lands(cards):
    s = build(cards, [(1, "Manabarbs"), (1, "Grizzly Bears"), (8, "Forest")])
    put(s, "Manabarbs", "battlefield")
    lands(s, "Forest", n=2)
    life = s.state.players["p1"].life
    bears = find(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=bears.id)  # the auto-payer taps two Forests: two triggers
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life - 2
    roundtrip(s)


def test_zhur_taa_druid_hurts_each_opponent(cards):
    s = build(cards, [(1, "Zhur-Taa Druid"), (9, "Forest")])
    druid = put(s, "Zhur-Taa Druid", "battlefield")
    next_main(s)
    life = s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana == {"G": 1} and s.state.players["p2"].life == life - 1
    roundtrip(s)


# -- counter riders ----------------------------------------------------------------------------------------------------------------
def test_twitching_doll_puts_a_nest_counter_on_itself(cards):
    s = build(cards, [(1, "Twitching Doll"), (9, "Forest")])
    doll = put(s, "Twitching Doll", "battlefield")
    next_main(s)
    act(s, "p1", type="activate_ability", card_id=doll.id, ability=0, mana_choice="B")
    assert s.state.players["p1"].mana == {"B": 1} and s.state.cards[doll.id].counters.get("nest") == 1
    roundtrip(s)


def test_gemstone_mine_is_sacrificed_with_its_last_counter(cards):
    s = build(cards, [(1, "Gemstone Mine"), (9, "Forest")])
    mine = put(s, "Gemstone Mine", "battlefield")
    act(s, "p1", type="counter", card_ids=[mine.id], kind="mining", delta=2)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=1, mana_choice="U")
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[mine.id].counters.get("mining") == 1
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=False)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=1, mana_choice="R")
    assert s.state.players["p1"].mana == {"U": 1, "R": 1}
    assert s.state.cards[mine.id].zone == "p1:graveyard"  # no mining counters left: sacrificed (701.21a)
    roundtrip(s)
