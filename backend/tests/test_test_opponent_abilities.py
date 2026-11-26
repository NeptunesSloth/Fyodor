"""-- test opponent: abilities and tricks -- the opponent the server plays for (app/game/bot.py) activates its permanents' abilities
(a damage ability at an opposing creature or player, equip onto its creature, a planeswalker's), casts a pump spell after blockers when
it wins the fight, and never repeats a free ability endlessly. Everything through recorded intents: the games replay the same."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game import bot
from tests.fixtures.cards import card, fixture_cards
from tests.test_test_opponent import attack_with, board, human_move, play, replay_matches, until_it_decides

EXTRA = [
    card("Test Pinger", set_code="tbt", number="1", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Wizard",
         oracle_text="{T}: This creature deals 1 damage to any target.", power="1", toughness="1", colors=["R"], color_identity=["R"]),
    card("Test Free Pinger", set_code="tbt", number="2", mana_cost="{2}", cmc=2.0, type_line="Artifact",
         oracle_text="{0}: This artifact deals 1 damage to any target."),
    card("Test Ogre", set_code="tbt", number="3", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Ogre", oracle_text="",
         power="3", toughness="3", colors=["R"], color_identity=["R"]),
    card("Test Twin Mage", set_code="tbt", number="4", mana_cost="{3}{G}", cmc=4.0, type_line="Creature — Human Wizard",
         oracle_text="Whenever you cast an instant or sorcery spell, copy that spell. You may choose new targets for the copy.",
         power="4", toughness="2", colors=["G"], color_identity=["G"]),
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()} | {c["name"]: c for c in EXTRA}
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def activations(s, name: str | None = None) -> list:
    return [a for a in s.history.actions if a.type == "activate_ability" and a.actor == "p2"
            and (name is None or s.state.cards[a.card_id].name == name)]


def test_it_pings_an_opposing_creature_it_kills(cards):
    s, ids = board(cards, mine=("Llanowar Elves",), theirs=("Test Pinger",))
    play(s, until_turn=2)  # (after its combat: a creature taps for its ability once it no longer attacks)
    assert s.state.cards[ids["p1:Llanowar Elves"]].zone == "p1:graveyard"
    assert s.state.players["p1"].life == 20
    assert [a.targets for a in activations(s, "Test Pinger")] == [[ids["p1:Llanowar Elves"]]]
    replay_matches(s)


def test_with_nothing_to_kill_it_pings_the_player(cards):
    """Alice's 2/2 keeps the 1/1 home (it would die attacking) and 1 damage doesn't kill it: the ping goes at Alice."""
    s, ids = board(cards, mine=("Grizzly Bears",), theirs=("Test Pinger",))
    play(s, until_turn=2)
    assert s.state.players["p1"].life == 19
    assert s.state.cards[ids["p1:Grizzly Bears"]].zone == "p1:battlefield"
    assert [a.targets for a in activations(s, "Test Pinger")] == [["p1"]]
    replay_matches(s)


def test_it_equips_its_creature(cards):
    s, ids = board(cards, theirs=("Grizzly Bears", "Bonesplitter", "Forest"))
    play(s, until_turn=2)
    eq = s.state.cards[ids["p2:Bonesplitter"]]
    assert eq.attached_to == ids["p2:Grizzly Bears"]
    assert len(activations(s, "Bonesplitter")) == 1  # (once: it doesn't move it back and forth)
    assert s.state.players["p1"].life <= 16  # (the 4/2 Bears attacked into an empty board)
    replay_matches(s)


def test_it_casts_a_pump_spell_after_blocking_to_win_the_fight(cards):
    """At 2 life it chump-blocks Alice's 3/3 with its Bears, then Giant Growth makes them a 5/5: the Ogre dies, the Bears live."""
    s, ids = board(cards, life=2, mine=("Test Ogre",), theirs=("Grizzly Bears", "Forest"), top=[(1, "Giant Growth")])
    attack_with(s, ids["p1:Test Ogre"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    play(s, until_turn=1)
    cast = [a for a in s.history.actions if a.type == "cast_spell" and a.actor == "p2"]
    assert [s.state.cards[a.card_id].name for a in cast] == ["Giant Growth"]
    assert cast[0].targets == [ids["p2:Grizzly Bears"]]
    assert s.state.cards[ids["p1:Test Ogre"]].zone == "p1:graveyard"
    assert s.state.cards[ids["p2:Grizzly Bears"]].zone == "p2:battlefield"
    assert s.state.players["p2"].life == 2
    replay_matches(s)


def test_it_keeps_a_pump_spell_when_the_fight_is_already_won(cards):
    s, ids = board(cards, mine=("Llanowar Elves",), theirs=("Grizzly Bears", "Forest"), top=[(1, "Giant Growth")])
    attack_with(s, ids["p1:Llanowar Elves"])
    play(s, until_turn=1)
    assert not [a for a in s.history.actions if a.type == "cast_spell" and a.actor == "p2"]
    assert s.state.cards[ids["p1:Llanowar Elves"]].zone == "p1:graveyard"


def test_a_free_repeatable_ability_is_used_a_few_times_a_turn_never_endlessly(cards):
    s, _ = board(cards, life=40, theirs=("Test Free Pinger",))
    per_turn: dict[int, int] = {}
    for _ in range(3000):
        if s.state.turn.number > 4:
            break
        turn = s.state.turn.number
        played = bot.step(s)
        if played == "activate_ability":
            per_turn[turn] = per_turn.get(turn, 0) + 1
        elif played is None:
            assert human_move(s)
    assert s.state.turn.number == 5  # (the game goes on: it always passes in the end)
    assert per_turn and all(n <= bot.ABILITY_CAP for n in per_turn.values()), per_turn
    assert s.state.players["p1"].life == 40 - sum(per_turn.values())
    replay_matches(s)


def test_the_ledger_stops_an_ability_once_it_hits_the_cap(cards):
    s, _ = board(cards, theirs=("Test Free Pinger",))
    play(s, until_turn=1)
    while bot.pending(s.state) != "p2":
        human_move(s)
    view = bot.observe(s.state, "p2", cards)
    free = next(h for h in view["rules"]["hints"].get("activatable", []) if view["cards"][h["card_id"]]["name"] == "Test Free Pinger")
    key = f"{free['card_id']}:{free['ability']}"
    turn = [view["turn"]["number"], view["turn"]["active_player"]]
    memory = {"acts": {"turn": turn, "n": {key: bot.ABILITY_CAP}, "total": bot.ABILITY_CAP}}
    assert not [t for t in bot.decide(view, cards, memory) if t.get("type") == "activate_ability"]


def test_a_copy_of_its_pump_keeps_the_target_in_the_fight(cards):
    """-- playtest (nov 17) -- its copier copies its Giant Growth: the copy stays on the blocker in the fight, not on the bigger copier
    out of combat (it put Riku's copy on Riku)."""
    s, ids = board(cards, life=2, mine=("Test Ogre",), theirs=("Grizzly Bears", "Test Twin Mage", "Forest"), top=[(1, "Giant Growth")])
    attack_with(s, ids["p1:Test Ogre"])
    until_it_decides(s, "declare_blockers")
    play(s, until_turn=1)
    asked = [a for a in s.history.actions if a.type == "choose" and a.actor == "p2" and a.option_ids == ["keep"]]
    moved = [a for a in s.history.actions if a.type == "choose" and a.actor == "p2" and ids["p2:Test Twin Mage"] in (a.option_ids or [])]
    assert asked and not moved
    assert s.state.cards[ids["p1:Test Ogre"]].zone == "p1:graveyard"
