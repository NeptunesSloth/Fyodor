"""Wave 15A: small static wordings (real Oracle text, replay and save/load for each).

* 305.2: "Each player may play an additional land on each of their turns" (Rites of Flourishing).
* 604.3 / 613.4: Multani's "for each land you control and each land card in your graveyard", Nighthawk Scavenger's "1 plus the
  number of card types among cards in your opponents' graveyards".
* 611.3a: "~ has first strike during your turn" (Razorkin Needlehead).
* 107.1a: "mills half their library, rounded down" (Traumatize); 701.9a: "discard all the cards in your hand, then draw that many".
* 100.2a / 903.5b: "A deck can have any number of / up to seven cards named ~" (deck building only).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip
from tests.wave9c_kit import pt

EXTRA = [
    card("Rites of Flourishing", set_code="tst", number="B01", mana_cost="{2}{G}", cmc=3.0, type_line="Enchantment",
         oracle_text="At the beginning of each player's draw step, that player draws an additional card.\n"
                     "Each player may play an additional land on each of their turns.", colors=["G"], color_identity=["G"]),
    card("Multani, Yavimaya's Avatar", set_code="tst", number="B02", mana_cost="{4}{G}{G}", cmc=6.0,
         type_line="Legendary Creature — Elemental Avatar", power="0", toughness="0", colors=["G"], color_identity=["G"],
         oracle_text="Reach, trample\nMultani gets +1/+1 for each land you control and each land card in your graveyard."),
    card("Nighthawk Scavenger", set_code="tst", number="B03", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Creature — Vampire Rogue",
         power="1+*", toughness="3", colors=["B"], color_identity=["B"],
         oracle_text="Flying, deathtouch, lifelink\nNighthawk Scavenger's power is equal to 1 plus the number of card types among "
                     "cards in your opponents' graveyards."),
    card("Razorkin Needlehead", set_code="tst", number="B04", mana_cost="{2}{R}{R}", cmc=4.0, type_line="Creature — Human Assassin",
         power="2", toughness="2", colors=["R"], color_identity=["R"],
         oracle_text="This creature has first strike during your turn.\nWhenever an opponent draws a card, this creature deals 1 "
                     "damage to them."),
    card("Traumatize", set_code="tst", number="B05", mana_cost="{3}{U}{U}", cmc=5.0, type_line="Sorcery",
         oracle_text="Target player mills half their library, rounded down.", colors=["U"], color_identity=["U"]),
    card("Tolarian Winds", set_code="tst", number="B06", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Discard all the cards in your hand, then draw that many cards.", colors=["U"], color_identity=["U"]),
    card("Relentless Rats", set_code="tst", number="B07", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Rat", power="2",
         toughness="2", colors=["B"], color_identity=["B"],
         oracle_text="This creature gets +1/+1 for each other creature on the battlefield named Relentless Rats.\n"
                     "A deck can have any number of cards named Relentless Rats."),
    card("Test Big", set_code="tst", number="B08", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Knight", power="5",
         toughness="5", colors=["W"], color_identity=["W"], oracle_text=""),
    card("Test Relic", set_code="tst", number="B09", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA if c["oracle_text"]])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def play_land(s, pid, name="Forest"):
    c = next(c for c in s.state.zones[f"{pid}:library"] if s.state.cards[c].name == name)
    act(s, pid, type="move", card_ids=[c], to={"zone": "hand"})
    act(s, pid, type="play_land", card_id=c)


def test_rites_of_flourishing_gives_every_player_a_second_land(cards):
    s = build(cards, p1=("Rites of Flourishing",))
    put(s, "Rites of Flourishing", "battlefield")
    play_land(s, "p1")
    play_land(s, "p1")
    with pytest.raises(ActionError, match="already played"):
        play_land(s, "p1")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    play_land(s, "p2", "Island")  # Alice's permanent, Bob's own turn
    play_land(s, "p2", "Island")
    with pytest.raises(ActionError, match="already played"):
        play_land(s, "p2", "Island")
    roundtrip(s)


def test_multani_counts_lands_you_control_and_land_cards_in_your_graveyard(cards):
    s = build(cards, p1=("Multani, Yavimaya's Avatar",))
    put(s, "Multani, Yavimaya's Avatar", "battlefield")
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:3]
    act(s, "p1", type="move", card_ids=forests[:2], to={"player": "p1", "zone": "battlefield"})
    assert pt(s, "Multani, Yavimaya's Avatar") == (2, 2)
    act(s, "p1", type="move", card_ids=forests[2:], to={"zone": "graveyard"})
    assert pt(s, "Multani, Yavimaya's Avatar") == (3, 3)
    roundtrip(s)


def test_nighthawk_scavenger_counts_card_types_in_the_opponents_graveyards(cards):
    s = build(cards, p1=("Nighthawk Scavenger", "Test Relic"), p2=("Test Big", "Test Relic"))
    put(s, "Nighthawk Scavenger", "battlefield")
    assert pt(s, "Nighthawk Scavenger")[0] == 1
    put(s, "Test Big", "graveyard", "p2")
    put(s, "Test Relic", "graveyard", "p2")
    put(s, "Island", "graveyard", "p2")
    put(s, "Test Relic", "graveyard", "p1")  # your own graveyard does not count
    assert pt(s, "Nighthawk Scavenger")[0] == 4  # 1 + creature, artifact, land
    roundtrip(s)


def test_razorkin_has_first_strike_only_during_its_controllers_turn(cards):
    from app.rules.plan import Plan

    s = build(cards, p1=("Razorkin Needlehead",))
    put(s, "Razorkin Needlehead", "battlefield")

    def first_strike():
        c = next(c for c in s.state.cards.values() if c.name == "Razorkin Needlehead")
        return "first strike" in Plan(s.state, "p1", s.cards, None).ch(c).keywords

    assert first_strike()
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert not first_strike()
    roundtrip(s)


def test_traumatize_mills_half_the_targets_library_rounded_down(cards):
    s = build(cards, p1=("Traumatize",))
    n = len(s.state.zones["p2:library"])
    c = put(s, "Traumatize", "hand")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p2:library"]) == n - n // 2
    assert len(s.state.zones["p2:graveyard"]) == n // 2
    roundtrip(s)


def test_tolarian_winds_draws_as_many_cards_as_it_discarded(cards):
    s = build(cards, p1=("Tolarian Winds",))
    c = put(s, "Tolarian Winds", "hand")
    for _ in range(3):
        play = next(x for x in s.state.zones["p1:library"] if s.state.cards[x].name == "Forest")
        act(s, "p1", type="move", card_ids=[play], to={"zone": "hand"})
    before = list(s.state.zones["p1:hand"])
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    now = s.state.zones["p1:hand"]
    assert len(now) == len(before) - 1  # the spell left the hand; the rest were discarded and as many drawn
    assert not set(now) & set(before)
    assert len(s.state.zones["p1:graveyard"]) == len(before) - 1 + 1
    roundtrip(s)


def test_relentless_rats_count_each_other_rat(cards):
    s = build(cards, p1=("Relentless Rats",))
    put(s, "Relentless Rats", "battlefield")
    assert pt(s, "Relentless Rats") == (2, 2)
    act(s, "p1", type="create_token", player="p1", token={"name": "Relentless Rats", "type_line": "Token Creature — Rat",
                                                          "power": "1", "toughness": "1", "text": ""})
    assert pt(s, "Relentless Rats") == (3, 3)
    roundtrip(s)


def test_deck_building_limits_follow_the_card():
    from app.decks.service import over_limit

    rats = {"type_line": "Creature — Rat", "oracle_text": "A deck can have any number of cards named Rat Colony."}
    dwarves = {"type_line": "Creature — Dwarf", "oracle_text": "A deck can have up to seven cards named Seven Dwarves."}
    plain = {"type_line": "Creature — Elf", "oracle_text": ""}
    assert not over_limit(rats, 30, 1)
    assert not over_limit(dwarves, 7, 1)
    assert over_limit(dwarves, 8, 1)
    assert over_limit(plain, 2, 1)
    assert not over_limit(plain, 1, 1)
    assert not over_limit(plain, 4, 4)
