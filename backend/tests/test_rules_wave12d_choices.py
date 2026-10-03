"""Wave 12D: other players' choices, mana for another player, giving control, land types set (CR 2026-09-25).

* "Target opponent gains control of this creature / all other permanents you control", "An opponent gains control of
  it" (not a target: its controller chooses the opponent, 608.2d), "Each player gains control of all creatures they own",
  "You gain control of all enchantments": layer 2 control-changing effects (613.1b, 613.7), 108.4a / 110.2.
Every scenario also checks that replaying the recorded history reproduces the table and that a reload does.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_control import answer, cast, check, put
from tests.test_rules_delayed import next_end_step
from tests.test_rules_effects import mana, pass_until_stack_empty

REAL = [
    card("Akroan Horse", set_code="tst", number="D1", mana_cost="{4}", cmc=4.0, type_line="Artifact Creature — Horse",
         oracle_text="Defender\nWhen this creature enters, an opponent gains control of it.\nAt the beginning of your upkeep, each "
                     "opponent creates a 1/1 white Soldier creature token.", power="0", toughness="4", keywords=["Defender"]),
    card("Humble Defector", set_code="tst", number="D2", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Rogue",
         oracle_text="{T}: Draw two cards. Target opponent gains control of this creature. Activate only during your turn.",
         power="2", toughness="1", colors=["R"], color_identity=["R"]),
    card("Sky Swallower", set_code="tst", number="D3", mana_cost="{3}{U}{U}", cmc=5.0, type_line="Creature — Leviathan",
         oracle_text="Flying\nWhen this creature enters, target opponent gains control of all other permanents you control.",
         power="8", toughness="8", colors=["U"], color_identity=["U"], keywords=["Flying"]),
    card("Trostani Discordant", set_code="tst", number="D4", mana_cost="{3}{G}{W}", cmc=5.0, type_line="Legendary Creature — Dryad",
         oracle_text="Other creatures you control get +1/+1.\nWhen Trostani enters, create two 1/1 white Soldier creature tokens with "
                     "lifelink.\nAt the beginning of your end step, each player gains control of all creatures they own.",
         power="1", toughness="4", colors=["G", "W"], color_identity=["G", "W"]),
    card("Eladamri's Vineyard", set_code="tst", number="D6", mana_cost="{G}", cmc=1.0, type_line="Enchantment",
         oracle_text="At the beginning of each player's first main phase, that player adds {G}{G}.", colors=["G"], color_identity=["G"]),
    card("Tangleroot", set_code="tst", number="D7", mana_cost="{3}", cmc=3.0, type_line="Artifact",
         oracle_text="Whenever a player casts a creature spell, that player adds {G}.", color_identity=["G"]),
    card("The Warring Triad", set_code="tst", number="D8", mana_cost="{3}", cmc=3.0, type_line="Legendary Artifact Creature — God",
         oracle_text="Flying, trample, haste\nAs long as there are fewer than eight cards in your graveyard, The Warring Triad isn't a "
                     "creature.\n{T}, Mill a card: Target player adds one mana of any color. (Activate only as an instant.)",
         power="5", toughness="5", keywords=["Flying", "Haste", "Trample", "Mill"]),
    card("Wrong Turn Test", set_code="tst", number="D5", mana_cost="{2}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Target opponent gains control of target creature.", colors=["U"], color_identity=["U"]),
]
NAMES = ["Akroan Horse", "Humble Defector", "Sky Swallower", "Trostani Discordant", "Wrong Turn Test", "Eladamri's Vineyard", "Tangleroot",
         "The Warring Triad"]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, three=False):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in NAMES), (4, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(4, "Grizzly Bears"), (1, "Llanowar Elves"), (20, "Island")])
    players = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)]
    if three:
        players.append(PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(4, "Grizzly Bears"), (20, "Mountain")])))
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


# -- giving control (613.1b) -------------------------------------------------------------------------------------
def test_humble_defector_draws_then_gives_itself_away(cards):
    s = build(cards)
    h = put(s, "Humble Defector")
    s.state.rules.controlled_since[h.id].turn = 0  # (it has been here since before this turn: no summoning sickness)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=h.id, ability=0, targets=["p2"])
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    assert s.state.cards[h.id].controller == "p2" and s.state.cards[h.id].owner == "p1"
    next_end_step(s)
    assert s.state.cards[h.id].controller == "p2"  # no duration: for the game
    check(s)


def test_akroan_horse_goes_to_the_only_opponent(cards):
    s = build(cards)
    horse = cast(s, "Akroan Horse", None, C=4)
    assert s.state.cards[horse.id].controller == "p2" and s.state.cards[horse.id].zone == "p2:battlefield"
    check(s)


def test_akroan_horse_asks_its_controller_which_opponent(cards):
    s = build(cards, three=True)
    horse = cast(s, "Akroan Horse", None, C=4)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # 608.2d: not a target
    assert s.state.cards[horse.id].controller == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    pass_until_stack_empty(s)
    assert s.state.cards[horse.id].controller == "p3"
    check(s)


def test_sky_swallower_gives_everything_else_away(cards):
    s = build(cards)
    land = put(s, "Forest")
    bear = put(s, "Grizzly Bears")
    swallower = cast(s, "Sky Swallower", None, U=2, C=3)
    if s.state.rules.decision is not None:
        answer(s, "p2")
    assert s.state.cards[land.id].controller == "p2" and s.state.cards[bear.id].controller == "p2"
    assert s.state.cards[swallower.id].controller == "p1"  # "all other permanents"
    check(s)


def test_trostani_gives_every_creature_back_to_its_owner(cards):
    s = build(cards)
    cast(s, "Wrong Turn Test", ["p2", put(s, "Grizzly Bears").id], counts=[1, 1], U=1, C=2)  # Alice's own Bear goes to Bob
    stolen = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.controller == "p2"]
    assert len(stolen) == 1
    trostani = put(s, "Trostani Discordant")
    next_end_step(s)  # Alice's end step: each player gains control of all creatures they own
    assert s.state.cards[stolen[0].id].controller == "p1" and s.state.cards[trostani.id].controller == "p1"
    check(s)


# -- mana for another player (106.3, 106.4) ----------------------------------------------------------------------
def to_turn(s, number, phase="main1"):
    from tests.test_rules_conditionals import to_turn as go

    go(s, number, phase)


def test_eladamris_vineyard_adds_mana_for_whoever_s_main_phase_it_is(cards):
    s = build(cards)
    put(s, "Eladamri's Vineyard")
    next_end_step(s)
    to_turn(s, 2)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].mana == {"G": 2} and s.state.players["p1"].mana == {}  # Bob's pool, not Alice's
    check(s)


def test_tangleroot_adds_mana_for_the_player_who_cast(cards):
    s = build(cards)
    put(s, "Tangleroot")
    next_end_step(s)
    to_turn(s, 2)
    bear = put(s, "Grizzly Bears", "hand", "p2")
    mana(s, "p2", G=1, U=1)
    act(s, "p2", type="cast_spell", card_id=bear.id)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].mana == {"G": 1} and s.state.players["p1"].mana == {}
    check(s)


def test_the_warring_triad_lets_a_target_player_choose_the_color(cards):
    s = build(cards)
    triad = put(s, "The Warring Triad")
    s.state.rules.controlled_since[triad.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=triad.id, ability=2, targets=["p2"])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # 106.4: it is Bob who adds the mana, so Bob chooses
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["R"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].mana == {"R": 1} and s.state.players["p1"].mana == {}
    check(s)
