"""Wave 27B: trigger wordings. Real Oracle text; scenarios check the replay and a save and a load.

* 508.3d: "a player attacks one or more of your opponents" (once per attack) / "another one of your opponents"; "that attacking player".
* 601.2i / 107.1: "a creature spell with mana value 4, 5, or 6" (a list of values in a selector).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave5j_token_copies import drive
from tests.wave9c_kit import card_named, check, life, mana

CARDS = [
    ("Probe Jolene", "{2}", "Enchantment", None, None,
     "Whenever a player attacks one or more of your opponents, that attacking player creates a Treasure token."),
    ("Probe Karazikar", "{2}", "Enchantment", None, None,
     "Whenever an opponent attacks another one of your opponents, you and the attacking player each draw a card and lose 1 life."),
    ("Probe Unsealing", "{2}", "Enchantment", None, None,
     "Whenever you cast a creature spell with mana value 4, 5, or 6, create two 0/1 colorless Eldrazi Spawn creature tokens with "
     "\"Sacrifice this token: Add {C}.\""),
    ("Probe Imp", "{1}", "Creature — Imp", "1", "1", ""),
    ("Probe Brute", "{3}", "Creature — Ogre", "4", "4", ""),
    ("Probe Giant", "{4}", "Creature — Giant", "4", "4", ""),
]
EXTRA = [card(n, set_code="t27b", number=f"T{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1) if "{4}" not in mc else 4.0,
              type_line=tl, colors=["R"], color_identity=["R"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c[0] for c in CARDS if c[5]])
def test_wave27b_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def table(cards, mine, players=2):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (2, "Probe Imp"), (8, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in mine), (2, "Probe Imp"), (10, "Island")]),
             deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (2, "Probe Imp"), (10, "Mountain")])][:players]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put(s, card_obj, pid):
    act(s, pid, type="move", card_ids=[card_obj.id], to={"player": pid, "zone": "battlefield"})
    return card_obj


def imp(s, pid):
    c = next(c for c in s.state.cards.values() if c.name == "Probe Imp" and c.owner == pid and c.zone.endswith(":library"))
    put(s, c, pid)
    s.state.rules.controlled_since[c.id].turn = 0
    return c


def treasures(s, pid):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.controller == pid and c.zone.endswith(":battlefield")]


def to_attack(s, *attackers):
    act(s, "p1", type="pass_priority")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in attackers])
    drive(s)


def test_attacking_one_or_more_of_your_opponents_triggers_once_for_the_attacker(cards):
    s = table(cards, ["Probe Jolene"], players=3)
    put(s, card_named(s, "Probe Jolene", "p1"), "p1")
    a, b = imp(s, "p1"), imp(s, "p1")
    to_attack(s, (a, "p2"), (b, "p3"))  # two opponents attacked in one declaration: still one trigger (508.3d)
    assert len(treasures(s, "p1")) == 1 and not treasures(s, "p2")
    check(s)


def test_another_players_attack_on_an_opponent_of_the_watcher_gives_that_attacker_the_token(cards):
    s = table(cards, ["Probe Jolene"], players=3)
    # Carol's Jolene sees Alice attack Bob (one of Carol's opponents): Alice, the attacking player, creates the Treasure
    put(s, card_named(s, "Probe Jolene", "p3"), "p3")
    a = imp(s, "p1")
    to_attack(s, (a, "p2"))
    assert len(treasures(s, "p1")) == 1 and not treasures(s, "p3")
    check(s)


def test_attacking_the_watcher_does_not_trigger(cards):
    s = table(cards, ["Probe Jolene"], players=2)
    put(s, card_named(s, "Probe Jolene", "p2"), "p2")  # Bob controls it and Alice attacks Bob: Bob is the one attacked, not one of Bob's opponents
    a = imp(s, "p1")
    to_attack(s, (a, "p2"))
    assert not treasures(s, "p1")  # (Bob is the attacked player, not an opponent of Bob)
    check(s)


def test_cast_trigger_reads_a_list_of_mana_values(cards):
    s = table(cards, ["Probe Unsealing", "Probe Giant", "Probe Brute"])
    put(s, card_named(s, "Probe Unsealing"), "p1")
    for name, spawns in (("Probe Brute", 0), ("Probe Giant", 2)):  # mana value 3 no, 4 yes
        c = card_named(s, name)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, C=4)
        act(s, "p1", type="cast_spell", card_id=c.id)
        drive(s)
        have = len([x for x in s.state.cards.values() if x.is_token and x.name == "Eldrazi Spawn" and x.controller == "p1"])
        assert have == (2 if name == "Probe Giant" else 0), (name, have)
    check(s)


def test_karazikar_both_players_draw_and_lose(cards):
    s = table(cards, ["Probe Karazikar"], players=3)
    put(s, card_named(s, "Probe Karazikar", "p3"), "p3")
    a = imp(s, "p1")  # Alice (an opponent of Carol) attacks Bob (another one of Carol's opponents)
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p3")}
    to_attack(s, (a, "p2"))
    assert life(s, "p3") == 39 and life(s, "p1") == 39
    assert len(s.state.zones["p1:hand"]) == hand["p1"] + 1 and len(s.state.zones["p3:hand"]) == hand["p3"] + 1
    check(s)
