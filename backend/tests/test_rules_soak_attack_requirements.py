"""What the declare-attackers decision tells the table (found by tools/soak.py). Each creature's own legal attack targets (508.1c: Alexios,
Deimos of Kosmos "can't attack its owner", soak seed 7001: the table offered the owner and the server refused it) and the creatures a
requirement says attack, with the places that obey it best (508.1d: Khârn the Betrayer "attacks or blocks each combat if able", soak
seed 5103: the bot attacked with nothing and the server refused). The decision's ``display`` carries both (``targets``, ``must_attack``);
the client offers only those targets and pre-selects those attacks, and the soak bot answers the same way. Real Oracle text."""

from __future__ import annotations

import random

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import check
from tools import soak

EXTRA = [
    card("Alexios, Deimos of Kosmos", set_code="tst", number="SK-Alex", mana_cost="{3}{R}", cmc=4.0,
         type_line="Legendary Creature — Human Berserker", power="4", toughness="4", colors=["R"], color_identity=["R"], keywords=["Trample"],
         oracle_text="Trample\nAlexios attacks each combat if able, can't be sacrificed, and can't attack its owner.\nAt the beginning of each "
                     "player's upkeep, that player gains control of Alexios, untaps it, and puts a +1/+1 counter on it. It gains haste until end "
                     "of turn."),
    card("Khârn the Betrayer", set_code="tst", number="SK-Kharn", mana_cost="{3}{R}", cmc=4.0,
         type_line="Legendary Creature — Astartes Berserker", power="5", toughness="1", colors=["R"], color_identity=["R"],
         keywords=["Berzerker", "Sigil of Corruption", "The Betrayer"],
         oracle_text="Berzerker — Khârn the Betrayer attacks or blocks each combat if able.\nSigil of Corruption — When you lose control of Khârn "
                     "the Betrayer, draw two cards.\nThe Betrayer — If damage would be dealt to Khârn the Betrayer, prevent that damage and an "
                     "opponent of your choice gains control of it."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, mine, theirs):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def put(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_attackers(s, pid, limit=200):
    """Play on (no attacks, no blocks) until ``pid`` declares attackers: the decision as ``pid``'s client sees it."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == pid:
            return s.view(pid)["rules"]["decision"]
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            raise AssertionError(d.prompt)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} never declared attackers")


def bot_answers(s, pid, view, n=40):
    return [soak.Bot(s, soak.CachedCards(s.cards), random.Random(seed)).answer(pid, view)["attackers"] for seed in range(n)]


def test_each_attacker_is_offered_only_the_targets_it_may_attack(cards):
    """Alexios ("… attacks each combat if able, … and can't attack its owner"), Bob's card: on Bob's turn it attacks Alice if able (Alice is
    its one place, a requirement: pre-selected), and attacking with nothing is refused. At Alice's upkeep she gains control of it (haste):
    her only opponent is its owner, so the decision offers it no target (508.1c) and no requirement (508.1d: none can be obeyed), while her
    Grizzly Bears may attack Bob; the server refuses Alexios attacking Bob, and the soak bot never tries it."""
    s = table(cards, ["Grizzly Bears"], ["Alexios, Deimos of Kosmos"])
    bears, alexios = put(s, "Grizzly Bears", "p1"), put(s, "Alexios, Deimos of Kosmos", "p2")
    d = to_attackers(s, "p2")
    assert s.state.cards[alexios.id].controller == "p2"
    assert d["display"]["targets"][alexios.id] == ["p1"] and d["display"]["must_attack"] == {alexios.id: ["p1"]}
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    assert all(any(a["card_id"] == alexios.id and a["target"] == "p1" for a in move) for move in bot_answers(s, "p2", d))
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": alexios.id, "target": "p1"}])
    d = to_attackers(s, "p1")
    assert s.state.cards[alexios.id].controller == "p1" and s.state.cards[alexios.id].owner == "p2"
    assert {o["id"] for o in d["options"]} >= {f"a:{alexios.id}", f"a:{bears.id}", "t:p2"}
    assert d["display"]["targets"] == {alexios.id: [], bears.id: ["p2"]}
    assert d["display"]["must_attack"] == {}
    with pytest.raises(ActionError, match="can't attack Bob"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": alexios.id, "target": "p2"}])
    moves = bot_answers(s, "p1", d)
    assert not any(a["card_id"] == alexios.id for move in moves for a in move) and any(moves)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers"
    check(s)


def test_a_creature_that_must_attack_is_named_and_the_bot_attacks_with_it(cards):
    """Khârn the Betrayer ("Berzerker — Khârn the Betrayer attacks or blocks each combat if able."), able to attack on Alice's turn: her
    declare-attackers decision names it as a creature that must attack, with Bob as its place (508.1d); attacking with nothing
    is refused, and the soak bot always attacks with it (with the Bears or not, at random)."""
    s = table(cards, ["Khârn the Betrayer", "Grizzly Bears"], [])
    kharn, bears = put(s, "Khârn the Betrayer", "p1"), put(s, "Grizzly Bears", "p1")
    d = to_attackers(s, "p1")
    assert d["display"]["targets"] == {kharn.id: ["p2"], bears.id: ["p2"]}
    assert d["display"]["must_attack"] == {kharn.id: ["p2"]}
    with pytest.raises(ActionError, match="Khârn the Betrayer attacks each combat if able"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    moves = bot_answers(s, "p1", d)
    assert all({"card_id": kharn.id, "target": "p2"} in move for move in moves)
    assert {len(move) for move in moves} == {1, 2}  # (the Bears too, sometimes)
    act(s, "p1", type="declare_attackers", attackers=next(m for m in moves if len(m) == 1))
    check(s)
