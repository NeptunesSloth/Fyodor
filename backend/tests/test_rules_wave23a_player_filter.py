"""Wave 23A: per-player filters (CR 608.2c, 101.4, 800.4a).

"Each opponent who [predicate] …", "For each opponent who [predicate], …" and "Each opponent who can't …" after an instruction that
acted on several players (Refurbished Familiar, Plaguecrafter, Kroxa, Thornbow Archer, Depopulate), and the counts "for each opponent
who controls fewer creatures than you / has more cards in hand than you / has less life than you" (Voice of Many, Wojek Investigator,
Great Unclean One). Real Oracle text; every scenario replays and survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, settle, to_hand, until
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=(), keywords=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"23A-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=list(keywords), **extra)


EXTRA = [
    real("Refurbished Familiar", "{3}{B}", 4, "Artifact Creature — Zombie Rat",
         "Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nFlying\nWhen this creature enters, each opponent discards a card. For each opponent who can't, you draw a card.",
         ("2", "1"), "B", ("Flying", "Affinity")),
    real("Plaguecrafter", "{2}{B}", 3, "Creature — Human Shaman",
         "When this creature enters, each player sacrifices a creature or planeswalker of their choice. Each player who can't discards a card.", ("3", "2"), "B"),
    real("Kroxa, Titan of Death's Hunger", "{B}{R}", 2, "Legendary Creature — Elder Giant",
         "When Kroxa enters, sacrifice it unless it escaped.\nWhenever Kroxa enters or attacks, each opponent discards a card, then each opponent who didn't discard a nonland card this way loses 3 life.\nEscape—{B}{B}{R}{R}, Exile five other cards from your graveyard. (You may cast this card from your graveyard for its escape cost.)",
         ("6", "6"), "BR", ("Escape",)),
    real("Thornbow Archer", "{B}", 1, "Creature — Elf Archer", "Whenever this creature attacks, each opponent who doesn't control an Elf loses 1 life.", ("1", "2"), "B"),
    real("Voice of Many", "{2}{G}{G}", 4, "Creature — Elf Druid", "When this creature enters, draw a card for each opponent who controls fewer creatures than you.", ("3", "3"), "G"),
    real("Wojek Investigator", "{2}{W}", 3, "Creature — Angel Detective",
         'Flying, vigilance\nAt the beginning of your upkeep, investigate once for each opponent who has more cards in hand than you. (To investigate, create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")',
         ("2", "4"), "W", ("Flying", "Investigate", "Vigilance")),
    real("Great Unclean One", "{4}{B}", 5, "Creature — Demon",
         "Reverberating Summons — At the beginning of your end step, each opponent loses 2 life. Then for each opponent who has less life than you, create a 1/3 black Demon creature token named Plaguebearer of Nurgle.",
         ("4", "5"), "B", ("Reverberating Summons",)),
    real("Depopulate", "{2}{W}{W}", 4, "Sorcery", "Each player who controls a multicolored creature draws a card. Then destroy all creatures.", colors="W"),
    real("Garruk, Veiled Butcher", "{3}{B}{B}", 5, "Legendary Planeswalker — Garruk",
         "If a creature an opponent controls would die, exile it instead.\n+2: Up to one target creature gets -4/-1 until your next turn.\n−2: Each player sacrifices a creature of their choice. If you sacrificed a creature this way, create a 4/4 green Beast creature token with trample.\n−3: Each opponent discards two cards. For each opponent who didn't discard two nonland cards this way, you draw a card.",
         colors="B"),
]
FULL = ["Refurbished Familiar", "Plaguecrafter", "Kroxa, Titan of Death's Hunger", "Thornbow Archer", "Voice of Many",
        "Wojek Investigator", "Great Unclean One", "Depopulate"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build3(cards, mine=(), bob=(), carol=()):
    """Alice (p1, in her main phase), Bob (p2) and Carol (p3)."""
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (12, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (12, "Island")])
    c = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (12, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b), PlayerSetup("Carol", cards=c)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def stops(s):
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_stops", own=["upkeep", "end"], others=["upkeep", "end"])


def hand(s, pid):
    return zone(s.state, pid, "hand")


def deal(s, pid, name, n=1):
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def empty_hand(s, pid):
    for c in list(hand(s, pid)):
        act(s, pid, type="move", card_ids=[c], to={"zone": "library"})


def cast(s, name, pid="p1", **pool):
    """Cast the card from hand (its mana added first); it resolves with whatever it triggers."""
    c = to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id)
    return c


def names(s, pid, key):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, key))


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_wordings_are_read_for_the_group_and_refuse_what_they_do_not_know():
    found = scripts.parse_effects("Each opponent discards a card. For each opponent who can't, you draw a card.")
    assert found is not None and [e["do"] for e in found[0]] == ["discard", "players_where", "draw"]
    assert found[0][1]["repeat"] == 1 and found[0][1]["pred"]["has"] is False
    assert scripts.parse_effects("Each opponent who has a bad day loses 1 life.") is None
    # "who can't" needs an earlier instruction that acted on the players (nothing to be "this way" about)
    assert scripts.parse_effects("Each opponent who can't loses 3 life.") is None
    # a clause that still addresses everyone isn't aimed at the group
    assert scripts.parse_effects("Each opponent who controls an Elf loses 1 life and each player draws a card.") is None


def test_refurbished_familiar_draws_once_for_each_opponent_who_cant(cards):
    s = build3(cards, mine=["Refurbished Familiar"])
    empty_hand(s, "p2")
    empty_hand(s, "p3")
    deal(s, "p3", "Mountain")  # Carol has a card to discard, Bob has none
    others = len(hand(s, "p1")) - 1  # (the Familiar itself leaves the hand; the draw happens as it resolves)
    cast(s, "Refurbished Familiar", B=1, C=3)
    settle(s)
    assert len(hand(s, "p1")) == others + 1  # only Bob couldn't
    assert names(s, "p3", "graveyard") == ["Mountain"] and hand(s, "p3") == []
    roundtrip(s)


def test_refurbished_familiar_nobody_draws_when_everyone_discards(cards):
    s = build3(cards, mine=["Refurbished Familiar"])
    empty_hand(s, "p2")
    empty_hand(s, "p3")
    deal(s, "p2", "Island")
    deal(s, "p3", "Mountain")
    others = len(hand(s, "p1")) - 1  # (the Familiar itself leaves the hand; the draw happens as it resolves)
    cast(s, "Refurbished Familiar", B=1, C=3)
    settle(s)
    assert len(hand(s, "p1")) == others
    assert names(s, "p2", "graveyard") == ["Island"] and names(s, "p3", "graveyard") == ["Mountain"]
    roundtrip(s)


def test_refurbished_familiar_every_opponent_cant_draws_twice(cards):
    s = build3(cards, mine=["Refurbished Familiar"])
    empty_hand(s, "p2")
    empty_hand(s, "p3")
    others = len(hand(s, "p1")) - 1  # (the Familiar itself leaves the hand; the draw happens as it resolves)
    cast(s, "Refurbished Familiar", B=1, C=3)
    settle(s)
    assert len(hand(s, "p1")) == others + 2
    roundtrip(s)


def test_plaguecrafter_each_player_who_cant_discards(cards):
    s = build3(cards, mine=["Plaguecrafter"])
    empty_hand(s, "p2")
    deal(s, "p2", "Island", 2)
    empty_hand(s, "p3")
    deal(s, "p3", "Mountain", 1)
    creature(s, "p2", "Bear")  # Bob has a creature to sacrifice; Alice has Plaguecrafter; Carol has nothing
    cast(s, "Plaguecrafter", B=1, C=2)
    settle(s)
    assert names(s, "p1", "graveyard") == ["Plaguecrafter"]  # (she sacrificed it: she could, so no discard)
    assert len(hand(s, "p2")) == 2 and names(s, "p2", "battlefield") == []  # (the Bear token ceased to exist)
    assert hand(s, "p3") == [] and names(s, "p3", "graveyard") == ["Mountain"]  # Carol couldn't sacrifice: she discards
    roundtrip(s)


def test_kroxa_opponents_who_did_not_discard_a_nonland_card_lose_life(cards):
    s = build3(cards, mine=["Kroxa, Titan of Death's Hunger"], bob=["Thornbow Archer"])
    empty_hand(s, "p2")
    deal(s, "p2", "Thornbow Archer")  # a nonland card: Bob keeps his life
    empty_hand(s, "p3")
    deal(s, "p3", "Mountain")  # a land: Carol loses 3
    cast(s, "Kroxa, Titan of Death's Hunger", B=1, R=1)
    settle(s)
    assert life(s, "p2") == 40 and life(s, "p3") == 37
    roundtrip(s)


def test_kroxa_an_opponent_with_no_cards_loses_life_too(cards):
    s = build3(cards, mine=["Kroxa, Titan of Death's Hunger"])
    empty_hand(s, "p2")
    empty_hand(s, "p3")
    cast(s, "Kroxa, Titan of Death's Hunger", B=1, R=1)
    settle(s)
    assert life(s, "p2") == 37 and life(s, "p3") == 37
    roundtrip(s)


def test_thornbow_archer_only_hurts_opponents_without_an_elf(cards):
    s = build3(cards, mine=["Thornbow Archer"], carol=["Voice of Many"])
    archer = on_field(s, "Thornbow Archer")
    on_field(s, "Voice of Many", "p3")  # Carol controls an Elf Druid
    s.state.rules.controlled_since[archer.id].turn = 0  # (no summoning sickness)
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": archer.id, "target": "p2"}])
    settle(s)
    assert life(s, "p3") == 40  # an Elf: not hurt
    assert life(s, "p2") == 38  # the trigger's 1 life and the unblocked Archer's 1 damage
    roundtrip(s)


def test_voice_of_many_draws_for_each_opponent_with_fewer_creatures(cards):
    s = build3(cards, mine=["Voice of Many"])
    creature(s, "p3", "Bear")
    creature(s, "p3", "Wolf")  # Carol controls two creatures to Alice's one (Voice itself): not fewer
    others = len(hand(s, "p1")) - 1
    cast(s, "Voice of Many", G=2, C=2)
    settle(s)
    assert len(hand(s, "p1")) == others + 1  # only Bob (no creatures) controls fewer
    roundtrip(s)


def test_wojek_investigator_counts_opponents_with_more_cards_in_hand(cards):
    s = build3(cards, mine=["Wojek Investigator"])
    on_field(s, "Wojek Investigator")
    for pid, n in (("p1", 2), ("p2", 2), ("p3", 1)):  # (Bob and Carol each draw once before Alice's next upkeep: 3 and 2)
        empty_hand(s, pid)
        deal(s, pid, "Forest" if pid == "p1" else "Island" if pid == "p2" else "Mountain", n)
    stops(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "upkeep")  # (Alice's upkeep: the trigger resolved)
    assert [len(hand(s, p)) for p in ("p1", "p2", "p3")] == [2, 3, 2]
    clues = [c for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield"]
    assert len(clues) == 1  # Bob has more cards in hand than Alice; Carol has as many
    roundtrip(s)


def test_great_unclean_one_makes_a_demon_for_each_opponent_with_less_life(cards):
    s = build3(cards, mine=["Great Unclean One"])
    on_field(s, "Great Unclean One")
    act(s, "p1", type="set_life", player="p2", value=20)
    act(s, "p1", type="set_life", player="p3", value=50)
    stops(s)
    until(s, lambda s: s.state.turn.number == 1 and s.state.turn.phase == "end")
    settle(s)
    assert life(s, "p2") == 18 and life(s, "p3") == 48
    assert names(s, "p1", "battlefield").count("Plaguebearer of Nurgle") == 1  # (Carol: 48 is not less than 40)
    roundtrip(s)


def test_depopulate_each_player_who_controls_a_multicolored_creature_draws(cards):
    s = build3(cards, mine=["Depopulate"])
    act(s, "p2", type="create_token", player="p2", token={"name": "Gold", "type_line": "Token Creature — Test", "power": "2", "toughness": "2",
                                                       "colors": ["W", "U"]})
    creature(s, "p3", "Plain")
    before = {p: len(hand(s, p)) for p in ("p1", "p2", "p3")}
    cast(s, "Depopulate", W=2, C=2)
    settle(s)
    assert len(hand(s, "p2")) == before["p2"] + 1  # a multicolored creature: draws, then it is destroyed
    assert len(hand(s, "p3")) == before["p3"] and len(hand(s, "p1")) == before["p1"] - 1
    roundtrip(s)
