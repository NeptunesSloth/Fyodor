"""The soak bot (tools/soak.py) and attack taxes (508.1h): it declared attackers at random and the server refused the ones it couldn't pay for
("Attacking costs {6} (508.1h): Seat 2 can't pay it", Ghostly Prison / Propaganda style), reported as hint mismatches. It now declares only
what it can pay, read with the engine's own attack cost (combat_rules.attack_cost) and payment check (casting.can_pay)."""

from __future__ import annotations

import random

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check
from tools import soak

EXTRA = [
    real('Ghostly Prison', '{2}{W}', 3, 'Enchantment',
         "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", None, 'W'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def put(s, name: str, pid: str):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield"))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def test_the_soak_bot_attacks_only_with_what_it_can_pay_for(cards):
    """Alice has Ghostly Prison; Bob has a Mountain, Llanowar Elves and two Grizzly Bears. One Bear can attack (the Mountain and the Elves pay
    {2}); two attackers cost {4}, and an attacking Elves is tapped by the attack (508.1f), so it can't pay. Each seed's declaration is
    one the server accepts: none, or one Bear."""
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Ghostly Prison"), (10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Llanowar Elves"), (2, "Grizzly Bears"), (10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "Ghostly Prison", "p1")
    put(s, "Mountain", "p2")
    elves = put(s, "Llanowar Elves", "p2")
    bears = {put(s, "Grizzly Bears", "p2").id, put(s, "Grizzly Bears", "p2").id}
    for _ in range(100):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("Bob never declared attackers")
    view = s.view("p2")["rules"]["decision"]
    assert {o["id"] for o in view["options"]} >= {f"a:{elves.id}", *(f"a:{b}" for b in bears)}
    declared = []
    for seed in range(40):
        move = soak.Bot(s, soak.CachedCards(cards), random.Random(seed)).answer("p2", view)
        attackers = [a["card_id"] for a in move["attackers"]]
        assert attackers == [] or (len(attackers) == 1 and attackers[0] in bears), (seed, attackers)
        declared.append(attackers)
    assert any(declared)  # (the bot still attacks when it can pay)
    act(s, "p2", type="declare_attackers", attackers=next(soak.Bot(s, soak.CachedCards(cards), random.Random(seed)).answer("p2", view)["attackers"]
                                                          for seed, picked in enumerate(declared) if picked))
    assert s.state.rules.decision is None and s.state.players["p1"].life == 38  # (the {2} paid by the Mountain and the Elves; a Bear hit Alice)
    assert s.state.cards[elves.id].tapped
    check(s)
