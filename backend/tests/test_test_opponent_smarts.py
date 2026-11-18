"""-- bot smarts -- what the opponent the server plays for (app/game/bot.py) does beyond lands, creatures and simple attacks, level by level:

* it answers another player's spell or ability on the stack that would take its creature (Intermediate on): a protection or
  indestructible instant, a regeneration ability, a blink, a sacrifice for value; Advanced also counters the removal of a key creature;
  each spell is answered once;
* combat maths (Intermediate on): first strike, menace (two blockers), double blocks (Advanced), tramplers' and divided damage — and every
  level answers a division of any size (a power of a billion, past the old 10000 bound) instead of stalling;
* X spells and X abilities (X from its mana), modal spells (the best mode), several targets and divided damage (Intermediate on).

Everything through recorded intents: each game replays the same."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game import bot
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, turn_on
from tests.test_test_opponent import attack_with, human_move, play, put, replay_matches, until_it_decides
from tests.test_test_opponent_abilities import EXTRA as ABILITY_CARDS


def creature(name: str, number: str, pt: str, text: str = "", keywords: tuple[str, ...] = (), cost: str = "{2}{G}", cmc: float = 3.0):
    p, t = pt.split("/")
    return card(name, set_code="tbs", number=number, mana_cost=cost, cmc=cmc, type_line="Creature — Beast", oracle_text=text,
                power=p, toughness=t, keywords=list(keywords), colors=["G"], color_identity=["G"])


SMARTS = [
    card("Plains", set_code="tbs", number="0", type_line="Basic Land — Plains", oracle_text="({T}: Add {W}.)"),
    creature("Test First Striker", "1", "2/2", "First strike", ("First strike",), cost="{1}{G}", cmc=2.0),
    creature("Test Menace Brute", "2", "3/3", "Menace", ("Menace",)),
    creature("Test Big Brute", "3", "4/4", cost="{3}{G}", cmc=4.0),
    creature("Test Colossus", "4", "1000000000/1000000000", "Trample", ("Trample",), cost="{G}", cmc=1.0),
    creature("Test Spore Pod", "5", "1/1", "Sacrifice this creature: Draw a card.", cost="{G}", cmc=1.0),
    card("Test Safekeeping", set_code="tbs", number="6", mana_cost="{G}", cmc=1.0, type_line="Instant",
         oracle_text="Target permanent you control gains hexproof and indestructible until end of turn.", colors=["G"], color_identity=["G"]),
    card("Test Intervention", set_code="tbs", number="7", mana_cost="{1}{G}", cmc=2.0, type_line="Instant",
         oracle_text="Permanents you control gain hexproof and indestructible until end of turn.", colors=["G"], color_identity=["G"]),
    card("Test Fireball", set_code="tbs", number="8", mana_cost="{X}{R}", cmc=1.0, type_line="Sorcery",
         oracle_text="Test Fireball deals X damage to any target.", colors=["R"], color_identity=["R"]),
    card("Test X Rod", set_code="tbs", number="9", mana_cost="{2}", cmc=2.0, type_line="Artifact",
         oracle_text="{X}, {T}: This artifact deals X damage to target creature."),
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()} | {c["name"]: c for c in ABILITY_CARDS} | {c["name"]: c for c in SMARTS}
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def board(cards, *, level: str = "intermediate", life: int = 20, mine: tuple[str, ...] = (), hand: tuple[str, ...] = (),
          theirs: tuple[str, ...] = (), top: list[tuple[int, str]] | None = None) -> tuple[GameSession, dict[str, str]]:
    """Alice's permanents ``mine`` and the opponent's ``theirs`` on the table when the rules start, Alice holding ``hand``, the
    opponent holding ``top`` (both decks in order: no shuffle)."""
    human = [(1, n) for n in mine] + [(1, n) for n in hand] + [(30, "Mountain")]
    opponent = [(1, n) for n in theirs] + (top or [(1, "Monastery Swiftspear")]) + [(30, "Forest")]
    state = new_game([PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", human)),
                      PlayerSetup("Opponent", cards=deck(cards, "Krenko, Mob Boss", opponent))], name="Deck test", format="sandbox",
                     settings=GameSettings(starting_life=life, allow_test_objects=True), shuffle=False, first_player=0)
    state.players["p2"].bot = "simple"
    state.players["p2"].bot_level = level
    from app.game.handlers.zones import draw_cards

    for pid in ("p1", "p2"):
        draw_cards(state, pid, 7)
    s = GameSession(state, cards=cards)
    ids = {f"p1:{n}": put(s, "p1", n) for n in mine} | {f"p2:{n}": put(s, "p2", n) for n in theirs}
    turn_on(s)
    return s, ids


def alices_main(s: GameSession) -> None:
    for _ in range(100):
        r = s.state.rules
        if s.state.turn.phase == "main1" and r.priority == "p1" and r.decision is None and s.state.turn.active_player == "p1":
            return
        if bot.step(s) is None:
            human_move(s)
    raise AssertionError("never got to Alice's main phase")


def in_hand(s: GameSession, pid: str, name: str) -> str:
    return next(c for c in s.state.zones[f"{pid}:hand"] if s.state.cards[c].name == name)


def alice_casts(s: GameSession, name: str, targets: list[str]) -> None:
    alices_main(s)
    act(s, "p1", type="cast_spell", card_id=in_hand(s, "p1", name), targets=targets)


def bot_casts(s: GameSession) -> list[str]:
    return [s.state.cards[a.card_id].name for a in s.history.actions if a.type == "cast_spell" and a.actor == "p2"]


def bot_acts(s: GameSession, kind: str) -> list:
    return [a for a in s.history.actions if a.type == kind and a.actor == "p2"]


def zone(s: GameSession, cid: str) -> str:
    return s.state.cards[cid].zone


# ---------------------------------------------------------------------------- answering the stack


@pytest.mark.parametrize(("level", "saved"), [("simple", False), ("intermediate", True)])
def test_it_saves_its_creature_from_a_bolt_with_a_protection_instant(cards, level, saved):
    s, ids = board(cards, level=level, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Grizzly Bears", "Forest"),
                   top=[(1, "Test Safekeeping")])
    bears = ids["p2:Grizzly Bears"]
    alice_casts(s, "Lightning Bolt", [bears])
    play(s, until_turn=1)
    assert ("Test Safekeeping" in bot_casts(s)) == saved
    assert (zone(s, bears) == "p2:battlefield") == saved
    replay_matches(s)


def test_it_answers_a_board_wipe_with_indestructible_for_everything(cards):
    s, ids = board(cards, mine=("Mountain", "Mountain"), hand=("Pyroclasm",), theirs=("Grizzly Bears", "Llanowar Elves", "Forest", "Forest"),
                   top=[(1, "Test Intervention")])
    alice_casts(s, "Pyroclasm", [])
    play(s, until_turn=1)
    assert bot_casts(s) == ["Test Intervention"]
    assert zone(s, ids["p2:Grizzly Bears"]) == "p2:battlefield" and zone(s, ids["p2:Llanowar Elves"]) == "p2:battlefield"
    replay_matches(s)


def test_it_regenerates_its_troll_in_response(cards):
    s, ids = board(cards, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Albino Troll", "Forest", "Forest"))
    troll = ids["p2:Albino Troll"]
    alice_casts(s, "Lightning Bolt", [troll])
    play(s, until_turn=1)
    assert [s.state.cards[a.card_id].name for a in bot_acts(s, "activate_ability")] == ["Albino Troll"]  # (once: never a loop)
    assert zone(s, troll) == "p2:battlefield"
    replay_matches(s)


def test_it_blinks_the_target_away(cards):
    s, ids = board(cards, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Test Big Brute", "Plains"), top=[(1, "Cloudshift")])
    alice_casts(s, "Lightning Bolt", [ids["p2:Test Big Brute"]])
    play(s, until_turn=1)
    assert bot_casts(s) == []  # (a 4/4 survives a Bolt: nothing to answer)
    s, ids = board(cards, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Grizzly Bears", "Plains"), top=[(1, "Cloudshift")])
    alice_casts(s, "Lightning Bolt", [ids["p2:Grizzly Bears"]])
    play(s, until_turn=1)
    assert bot_casts(s) == ["Cloudshift"]
    assert any(s.state.cards[c].name == "Grizzly Bears" for c in s.state.zones["p2:battlefield"])
    assert s.state.zones["p2:graveyard"] == [c for c in s.state.zones["p2:graveyard"] if s.state.cards[c].name == "Cloudshift"]
    replay_matches(s)


def test_it_sacrifices_a_doomed_creature_for_value(cards):
    s, ids = board(cards, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Test Spore Pod",))
    before = len(s.state.zones["p2:hand"])
    alice_casts(s, "Lightning Bolt", [ids["p2:Test Spore Pod"]])
    while s.state.zones.get("stack") or s.state.turn.phase == "main1" and not bot_acts(s, "activate_ability"):
        if bot.step(s) is None:
            human_move(s)
    assert [s.state.cards[a.card_id].name for a in bot_acts(s, "activate_ability")] == ["Test Spore Pod"]
    assert zone(s, ids["p2:Test Spore Pod"]) == "p2:graveyard"
    assert len(s.state.zones["p2:hand"]) == before + 1  # (the card it drew: before its own draw step)
    play(s, until_turn=1)
    replay_matches(s)


@pytest.mark.parametrize(("level", "countered"), [("intermediate", False), ("advanced", True)])
def test_advanced_counters_the_removal_of_a_key_creature(cards, level, countered):
    s, ids = board(cards, level=level, mine=("Mountain",), hand=("Lightning Bolt",), theirs=("Test Ogre", "Island", "Island"),
                   top=[(1, "Counterspell")])
    ogre = ids["p2:Test Ogre"]
    alice_casts(s, "Lightning Bolt", [ogre])
    play(s, until_turn=1)
    assert ("Counterspell" in bot_casts(s)) == countered
    assert (zone(s, ogre) == "p2:battlefield") == countered
    replay_matches(s)


# ---------------------------------------------------------------------------- combat maths


def their_attack(s: GameSession) -> list[str]:
    until_it_decides(s, "declare_attackers")
    assert bot.step(s) == "declare_attackers"
    declared = next(a for a in reversed(s.history.actions) if a.type == "declare_attackers" and a.actor == "p2")
    return sorted(s.state.cards[x.card_id].name for x in declared.attackers)


@pytest.mark.parametrize(("level", "attacks"), [("simple", []), ("intermediate", ["Test First Striker"])])
def test_a_first_striker_attacks_into_a_blocker_it_kills_first(cards, level, attacks):
    s, _ = board(cards, level=level, mine=("Grizzly Bears",), theirs=("Test First Striker",))
    assert their_attack(s) == attacks


def blocks_declared(s: GameSession) -> list[tuple[str, str]]:
    a = next(a for a in reversed(s.history.actions) if a.type == "declare_blockers" and a.actor == "p2")
    return sorted((s.state.cards[b.blocker_id].name, s.state.cards[b.attacker_id].name) for b in a.blocks)


@pytest.mark.parametrize(("level", "blocks"), [("simple", []), ("intermediate", [("Grizzly Bears", "Test Menace Brute")] * 2)])
def test_two_blockers_kill_a_menace_attacker(cards, level, blocks):
    s, ids = board(cards, level=level, mine=("Test Menace Brute",), theirs=("Grizzly Bears", "Grizzly Bears"))
    attack_with(s, ids["p1:Test Menace Brute"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert blocks_declared(s) == blocks
    play(s, until_turn=1)
    assert (zone(s, ids["p1:Test Menace Brute"]) == "p1:graveyard") == bool(blocks)
    replay_matches(s)


@pytest.mark.parametrize(("level", "double"), [("intermediate", False), ("advanced", True)])
def test_advanced_double_blocks_a_big_attacker(cards, level, double):
    s, ids = board(cards, level=level, mine=("Test Ogre",), theirs=("Grizzly Bears", "Grizzly Bears"))
    attack_with(s, ids["p1:Test Ogre"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert len(blocks_declared(s)) == (2 if double else 0)
    play(s, until_turn=1)
    assert (zone(s, ids["p1:Test Ogre"]) == "p1:graveyard") == double
    replay_matches(s)


@pytest.mark.parametrize("level", ["simple", "intermediate", "advanced"])
def test_a_billion_power_trampler_assigns_lethal_to_each_blocker_and_the_rest_to_the_player(cards, level):
    """Every level answers the division (no stall), whatever its size: lethal damage to each blocker in turn, the rest trampling over."""
    s, ids = board(cards, level=level, life=40, mine=("Grizzly Bears", "Llanowar Elves"), theirs=("Test Colossus",))
    until_it_decides(s, "declare_attackers")
    colossus = ids["p2:Test Colossus"]
    assert bot.step(s) == "declare_attackers"
    for _ in range(40):  # (Alice blocks with both)
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            human_move(s, blocks=[{"blocker_id": ids["p1:Grizzly Bears"], "attacker_id": colossus},
                                  {"blocker_id": ids["p1:Llanowar Elves"], "attacker_id": colossus}])
            break
        if bot.step(s) is None:
            human_move(s)
    play(s, until_turn=2)
    divided = [a for a in bot_acts(s, "choose") if a.amounts]
    assert divided and sum(divided[-1].amounts) == 1_000_000_000
    assert sorted(divided[-1].amounts)[:2] == [1, 2]
    assert zone(s, ids["p1:Grizzly Bears"]) == "p1:graveyard" and zone(s, ids["p1:Llanowar Elves"]) == "p1:graveyard"
    assert s.state.rules.winner == "p2"
    replay_matches(s)


# ---------------------------------------------------------------------------- X, modes, several targets


@pytest.mark.parametrize(("level", "x"), [("simple", None), ("intermediate", 2)])
def test_x_burn_is_sized_to_kill_the_creature_it_aims_at(cards, level, x):
    s, ids = board(cards, level=level, mine=("Grizzly Bears",), theirs=("Mountain",) * 6,
                   top=[(1, "Test Fireball")])
    play(s, until_turn=2)
    cast = [a for a in bot_acts(s, "cast_spell") if s.state.cards[a.card_id].name == "Test Fireball"]
    assert [a.x_value for a in cast] == ([x] if x else [])
    assert (zone(s, ids["p1:Grizzly Bears"]) == "p1:graveyard") == bool(x)
    replay_matches(s)


def test_x_burn_goes_at_the_player_when_it_is_lethal(cards):
    s, _ = board(cards, life=4, theirs=("Mountain", "Mountain", "Mountain", "Mountain", "Mountain"), top=[(1, "Test Fireball")])
    play(s, until_turn=2)
    cast = next(a for a in bot_acts(s, "cast_spell") if s.state.cards[a.card_id].name == "Test Fireball")
    assert cast.x_value >= 4 and cast.targets == ["p1"]
    assert s.state.rules.winner == "p2"
    replay_matches(s)


def test_an_x_ability_kills_a_creature(cards):
    s, ids = board(cards, mine=("Grizzly Bears",), theirs=("Test X Rod", "Forest", "Forest", "Forest"))
    play(s, until_turn=2)
    rods = [a for a in bot_acts(s, "activate_ability") if s.state.cards[a.card_id].name == "Test X Rod"]
    assert rods and rods[0].x_value >= 2
    assert zone(s, ids["p1:Grizzly Bears"]) == "p1:graveyard"
    replay_matches(s)


def test_a_modal_spell_picks_the_mode_that_helps(cards):
    """Test Shatter Charm: "destroy target artifact" or "draw a card". Its only artifact target is its own Sol Ring: it draws."""
    s, ids = board(cards, theirs=("Sol Ring", "Mountain"), top=[(1, "Test Shatter Charm")])
    play(s, until_turn=2)
    assert "Test Shatter Charm" in bot_casts(s)
    assert zone(s, ids["p2:Sol Ring"]) == "p2:battlefield"
    picked = [a.option_ids for a in bot_acts(s, "choose") if a.option_ids and all(":" in o for o in a.option_ids)]
    assert picked == [["1:0"]]
    replay_matches(s)


def test_divided_damage_kills_what_it_can_and_the_rest_goes_at_the_player(cards):
    """Test Barrage (4 damage divided among up to three targets) with Alice's 2/2 and 1/1: both die, 1 at Alice."""
    s, ids = board(cards, mine=("Grizzly Bears", "Llanowar Elves"), theirs=("Mountain",), top=[(1, "Test Barrage")])
    play(s, until_turn=2)
    assert "Test Barrage" in bot_casts(s)
    assert zone(s, ids["p1:Grizzly Bears"]) == "p1:graveyard" and zone(s, ids["p1:Llanowar Elves"]) == "p1:graveyard"
    assert s.state.players["p1"].life == 19
    replay_matches(s)


# ---------------------------------------------------------------------------- never stuck


@pytest.mark.parametrize("level", ["simple", "intermediate", "advanced"])
def test_a_game_of_everything_always_moves_on(cards, level):
    """Both decks full of the new cards: the game reaches turn 8 at every level (each window ends in a pass), and replays."""
    mix = ["Test Fireball", "Test Safekeeping", "Test Intervention", "Test Menace Brute", "Test First Striker", "Test Barrage",
           "Test Shatter Charm", "Albino Troll", "Test Spore Pod", "Test X Rod", "Counterspell", "Lightning Bolt", "Pyroclasm"]
    opponent = [(1, n) for pair in zip(["Forest", "Mountain", "Island"] * 5, mix, strict=False) for n in pair] + [(20, "Forest")]
    human = [(1, n) for pair in zip(["Mountain"] * 13, mix, strict=False) for n in pair] + [(20, "Mountain")]
    state = new_game([PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", human)),
                      PlayerSetup("Opponent", cards=deck(cards, "Krenko, Mob Boss", opponent))], name="Deck test", format="sandbox",
                     settings=GameSettings(starting_life=20, allow_test_objects=True), shuffle=False, first_player=0)
    state.players["p2"].bot = "simple"
    state.players["p2"].bot_level = level
    from app.game.handlers.zones import draw_cards

    for pid in ("p1", "p2"):
        draw_cards(state, pid, 7)
    s = GameSession(state, cards=cards)
    turn_on(s)
    play(s, until_turn=8)
    assert s.state.turn.number > 8 or s.state.rules.winner is not None
    replay_matches(s)


@pytest.mark.parametrize(("level", "answered"), [("intermediate", False), ("advanced", True)])
def test_advanced_kills_a_creature_pumped_in_a_fight_in_response(cards, level, answered):
    """Its Ogre blocks Alice's Bears; Alice's Giant Growth on the Bears would win the fight: Advanced Bolts the Bears in response."""
    s, ids = board(cards, level=level, mine=("Grizzly Bears", "Forest"), hand=("Giant Growth",), theirs=("Test Ogre", "Mountain"),
                   top=[(1, "Lightning Bolt")])
    bears, ogre = ids["p1:Grizzly Bears"], ids["p2:Test Ogre"]
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "main2", "declare_blockers"])  # (Alice stops once blocks are known)
    attack_with(s, bears)
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert blocks_declared(s) == [("Test Ogre", "Grizzly Bears")]
    for _ in range(10):
        if s.state.rules.priority == "p1" and s.state.rules.decision is None:
            break
        assert bot.step(s) is not None
    act(s, "p1", type="cast_spell", card_id=in_hand(s, "p1", "Giant Growth"), targets=[bears])
    play(s, until_turn=1)
    assert ("Lightning Bolt" in bot_casts(s)) == answered
    assert (zone(s, bears) == "p1:graveyard") == answered
    assert (zone(s, ogre) == "p2:battlefield") == answered
    replay_matches(s)
