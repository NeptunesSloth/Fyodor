"""-- planechase automation -- the face-up plane or phenomenon as a rules object (CR 311, 312, 901; app/rules/planar.py,
app/game/handlers/planechase.py ``sync``), proven end to end on real Oracle text:

* the object: in the planar controller's command zone, controlled by the active player (311.5), in no view (the client shows
  ``planechase_view``); none at a table without automation;
* statics: Krosa ("All creatures get +2/+2.", layers.statics), Feeding Grounds (spells cost {1} less: permissions._table_statics);
* chaos (311.7, 901.9b): Panopticon's "Whenever chaos ensues, draw a card.";
* the planeswalker symbol (901.8): the planeswalking ability goes on the stack, then "When you planeswalk to Panopticon" (701.31d);
* planeswalking away (701.31d): Sanctum of Serra's "destroy all nonland permanents";
* a phenomenon (312.5, 312.7 / 704.6f): Mutual Epiphany's encounter resolves, then the table planeswalks on by itself;
* an upkeep trigger under the next player (311.5) and "When you planeswalk to ~ and at the beginning of your upkeep" (Spectrox
  Mines, 603.2), which doesn't trigger for the starting plane (901.5).

Each with automation off too: nothing happens by itself (the players apply the planes by hand, as before)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import settle, to_turn
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, life, mana, pt, put

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    "Krosa": ("Plane — Dominaria", "All creatures get +2/+2.\nWhenever chaos ensues, you may add {W}{U}{B}{R}{G}."),
    "Feeding Grounds": ("Plane — Muraganda", "Red spells cost {1} less to cast.\nGreen spells cost {1} less to cast.\nWhenever chaos ensues, put "
                        "X +1/+1 counters on target creature, where X is that creature's mana value."),
    "Panopticon": ("Plane — Mirrodin", "When you planeswalk to Panopticon, draw a card.\nAt the beginning of your draw step, draw an additional "
                   "card.\nWhenever chaos ensues, draw a card."),
    "Lethe Lake": ("Plane — Arkhos", "At the beginning of your upkeep, mill ten cards.\nWhenever chaos ensues, target player mills ten cards."),
    "Sanctum of Serra": ("Plane — Serra's Realm", "When you planeswalk away from Sanctum of Serra, destroy all nonland permanents.\nWhenever "
                         "chaos ensues, you may have your life total become 20."),
    "Mutual Epiphany": ("Phenomenon", "When you encounter Mutual Epiphany, each player draws four cards. (Then planeswalk away from this "
                        "phenomenon.)"),
    "Spectrox Mines": ("Plane — Androzani Minor", "When you planeswalk to Spectrox Mines and at the beginning of your upkeep, you lose 3 life "
                       "and create a Treasure token.\nWhenever chaos ensues, create a Food token and a 2/2 black Human Rogue creature token."),
}
EXTRA = [card(n, set_code="opca", number=f"PL-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA.append(real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"))


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    """The planar deck dealt in the order given (no shuffle)."""

    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str], *, on: bool = True) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    settings = GameSettings(planechase=True, planar_deck_size=len(pool))
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0,
                     settings=settings, planar_pool=lambda: pool, rng=_InOrder())
    assert [c.name for c in state.planechase.deck] == planes
    if on:
        enable(state)
    s = GameSession(state, cards=cards)
    if on:
        act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def face(s):
    pc = s.state.planechase
    return s.state.cards.get(pc.face_id) if pc.face_id else None


def log_lines(s, back=30):
    return ["".join(p.get("t") or p.get("card", {}).get("name", "") for p in e["parts"]) for e in s.view("p1")["log"][-back:]]


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def roll(s, on: bool, value: int) -> None:
    """The active player rolls the planar die (the server's d6: 1 planeswalker, 2 chaos, 3-6 blank) and everything resolves."""
    act(s, "p1", type="roll_planar_die" if on else "planar_roll")
    if on:
        settle(s)


@pytest.mark.parametrize("name", list(PLANES))
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_plane_is_no_spell_and_its_unread_lines_stay_manual(cards):
    cov = coverage.of_card_data(cards.resolve("Krosa"))
    assert {f.id for f in cov.features} == {"planar", "text:0", "text:1"}  # (never "cast it")


@pytest.mark.parametrize("on", [True, False])
def test_the_face_up_plane_is_an_object_of_the_planar_controller_in_no_view(cards, on):
    s = table(cards, ["Krosa", "Lethe Lake"], on=on)
    if not on:  # a table without automation: no rules object, the table exactly as before
        assert face(s) is None and not any(cid.startswith("planar-") for cid in s.state.cards)
        return
    plane = face(s)
    assert plane.card_id == s.state.planechase.deck[0].printing_id and plane.zone == "p1:command" and plane.controller == plane.owner == "p1"
    for viewer in ("p1", "p2"):
        view = s.view(viewer)
        assert plane.id not in json.dumps(view) and view["planechase"]["current"]["name"] == "Krosa"
    assert plane.id not in s.state.zones.get("p1:command", [])
    to_turn(s, 2)  # Bob's turn: Bob is the planar controller (311.5), the same object
    again = face(s)
    assert again.id == plane.id and again.controller == "p2" and again.zone == "p2:command"
    check(s)


@pytest.mark.parametrize("on", [True, False])
def test_krosa_all_creatures_get_plus_two(cards, monkeypatch, on):
    s = table(cards, ["Krosa", "Lethe Lake"], on=on)
    put(s, "Runeclaw Bear")
    if not on:
        assert face(s) is None
        return
    assert pt(s, "Runeclaw Bear") == (4, 4)
    act(s, "p1", type="planeswalk")  # (the table's planeswalk: to Lethe Lake)
    assert pt(s, "Runeclaw Bear") == (2, 2) and face(s).name == "Lethe Lake"
    check(s)


def test_feeding_grounds_green_spells_cost_one_less(cards):
    from tests.test_rules_wave100n_multi import cast

    s = table(cards, ["Feeding Grounds", "Krosa"])
    mana(s, G=1)
    bear = cast(s, "Runeclaw Bear")  # {1}{G} for {G}
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("on", [True, False])
def test_chaos_ensues_panopticon_draws(cards, monkeypatch, on):
    s = table(cards, ["Panopticon", "Krosa"], on=on)
    before = hand(s)
    script(monkeypatch, [2])
    roll(s, on, 2)
    assert s.state.planechase.last_roll.face == "chaos"
    assert hand(s) == before + (1 if on else 0)
    if on:
        check(s)


@pytest.mark.parametrize("on", [True, False])
def test_the_planeswalker_symbol_planeswalks_to_panopticon(cards, monkeypatch, on):
    s = table(cards, ["Krosa", "Panopticon"], on=on)
    before = hand(s)
    script(monkeypatch, [1])
    act(s, "p1", type="roll_planar_die" if on else "planar_roll")
    if on:  # 901.8, 901.9c: the planeswalking ability went on the stack (it could be responded to), then resolved
        settle(s)
        assert any("Planeswalking ability" in line for line in log_lines(s)), log_lines(s)
    assert s.state.planechase.deck[0].name == "Panopticon"
    assert hand(s) == before + (1 if on else 0)  # "When you planeswalk to Panopticon, draw a card."
    if on:
        assert face(s).name == "Panopticon"
        check(s)


@pytest.mark.parametrize("on", [True, False])
def test_planeswalking_away_from_sanctum_of_serra_destroys_nonland_permanents(cards, monkeypatch, on):
    s = table(cards, ["Sanctum of Serra", "Lethe Lake"], on=on)
    bear = put(s, "Runeclaw Bear")
    script(monkeypatch, [1])
    roll(s, on, 1)
    assert s.state.planechase.deck[0].name == "Lethe Lake"
    assert s.state.cards[bear.id].zone == ("p1:graveyard" if on else "p1:battlefield")
    if on:
        check(s)


@pytest.mark.parametrize("on", [True, False])
def test_a_phenomenon_resolves_then_the_table_planeswalks_on(cards, monkeypatch, on):
    s = table(cards, ["Krosa", "Mutual Epiphany", "Panopticon"], on=on)
    mine, theirs = hand(s), hand(s, "p2")
    script(monkeypatch, [1])
    roll(s, on, 1)
    if not on:  # by hand: the phenomenon waits face up for "Done — planeswalk"
        assert s.state.planechase.deck[0].name == "Mutual Epiphany" and (hand(s), hand(s, "p2")) == (mine, theirs)
        return
    # 312.5: each player drew four; 704.6f: then the table planeswalked on, to Panopticon (701.31d: its trigger, one more for Alice)
    assert s.state.planechase.deck[0].name == "Panopticon" and face(s).name == "Panopticon"
    assert (hand(s), hand(s, "p2")) == (mine + 5, theirs + 4)
    assert [c.name for c in s.state.planechase.visited] == ["Krosa", "Mutual Epiphany"]
    check(s)


def test_spectrox_mines_starting_plane_doesnt_trigger_but_each_upkeep_does(cards):
    s = table(cards, ["Spectrox Mines", "Krosa"])
    # 901.5: turning the starting plane face up triggers nothing; Alice's first upkeep does (3 life, a Treasure)
    assert life(s, "p1") == 37 and life(s, "p2") == 40
    to_turn(s, 2)  # Bob's upkeep: "you" is Bob, the planar controller
    assert life(s, "p2") == 37 and life(s, "p1") == 37
    assert any(c.name == "Treasure" and c.controller == "p2" and c.zone == "p2:battlefield" for c in s.state.cards.values())
    check(s)
