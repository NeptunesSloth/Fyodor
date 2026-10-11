"""Wave 36A: mana added by the amount of a trigger event ("add that much mana …", "add twice that much {G}"), researched against CR
2026-09-25, real Oracle text (tests/fixtures/wave36a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.2c, 608.2k: "that much" is the amount of the event that triggered the ability: for "one or more creatures you control attack" the
  number of those creatures (a batch of attackers is one event with that many parts), for combat damage the damage dealt.
* 605.1b: a triggered ability that isn't a mana ability (it doesn't trigger from a mana ability's activation) uses the stack, so the mana is
  added as it resolves; 106.4: mana empties from the pool as each step and phase ends unless something says otherwise
  ("you don't lose this mana", Radha / Photon: until end of turn; Fangorn's static: unspent green mana).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, settle, until
from tests.wave9c_kit import build, card_named, check, put
from tests.wave36a_kit import attack, next_own_turn, offered, pick, pool

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Grand Warlord Radha", "Fangorn, Tree Shepherd", "Photon, Mighty Marvel"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_event_mana_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "When this creature enters, add that much mana of any one color.",  # (nothing to be "that much": an enters trigger has no amount, 608.2k)
    "{T}: Add that much mana of any one color.",  # (an activated mana ability has no event either)
    "Add that much mana in any combination of {R} and/or {G}.",  # (a spell: no event)
])
def test_that_much_mana_needs_an_event_with_an_amount(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Permanent", "Creature — Elf" if text.startswith("When") else "Artifact" if text.startswith("{T}") else "Instant", text)
    assert coverage.of_characteristics(chs).level != "FULL"


def table(cards, name, *, others=(), theirs=()):
    s = build(cards, [name, *others], theirs=theirs, forests=20)
    put(s, name)
    return s


# -- Grand Warlord Radha: "add that much mana in any combination of {R} and/or {G}" ---------------------------------------------------
def test_radha_adds_a_mana_for_each_attacking_creature_and_keeps_it_until_the_end_of_the_turn(cards):
    s = table(cards, "Grand Warlord Radha", others=["Grizzly Bears", "Llanowar Elves"])
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    next_own_turn(s)
    attack(s, card_named(s, "Grand Warlord Radha"), card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves"))
    assert offered(s) == ["{G}", "{R}"]  # (each of the three is chosen on its own: {R} or {G}, 106.1)
    pick(s, "{R}")
    assert offered(s) == ["{G}", "{R}"]
    pick(s, "{G}")
    pick(s, "{R}")
    settle(s)
    assert pool(s) == {"R": 2, "G": 1}  # (three attackers: three mana)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert sum(pool(s).values()) == 3  # (106.4: "you don't lose this mana as steps and phases end")
    check(s)


def test_radha_counts_only_the_creatures_that_attacked(cards):
    s = table(cards, "Grand Warlord Radha", others=["Grizzly Bears"])
    put(s, "Grizzly Bears")
    next_own_turn(s)
    attack(s, card_named(s, "Grand Warlord Radha"))
    assert offered(s) == ["{G}", "{R}"]
    pick(s, "{G}")
    settle(s)
    assert pool(s) == {"G": 1}
    check(s)


def test_radha_adds_nothing_when_nobody_attacks(cards):
    s = table(cards, "Grand Warlord Radha")
    next_own_turn(s)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert pool(s) == {}
    check(s)


# -- Fangorn, Tree Shepherd: "add twice that much {G}" ------------------------------------------------------------------------------
def test_fangorn_adds_twice_as_much_green_as_the_treefolk_that_attacked(cards):
    """Two Treefolk attack (Fangorn and a token) with a Bears: "that much" is the Treefolk among them (2), so {G} four times; and the
    green mana stays through the steps (Fangorn's static ability)."""
    s = table(cards, "Fangorn, Tree Shepherd", others=["Grizzly Bears"])
    put(s, "Grizzly Bears")
    ent = creature(s, "p1", "Ent", "2/2", "Token Creature — Treefolk")
    next_own_turn(s)
    attack(s, card_named(s, "Fangorn, Tree Shepherd"), card_named(s, "Ent"), card_named(s, "Grizzly Bears"))
    settle(s)
    assert pool(s) == {"G": 4}
    until(s, lambda s: s.state.turn.phase == "main2")
    assert pool(s) == {"G": 4} and ent.zone == "p1:battlefield"
    check(s)


def test_fangorn_alone_adds_two(cards):
    s = table(cards, "Fangorn, Tree Shepherd", others=["Grizzly Bears"])
    put(s, "Grizzly Bears")
    next_own_turn(s)
    attack(s, card_named(s, "Fangorn, Tree Shepherd"), card_named(s, "Grizzly Bears"))
    settle(s)
    assert pool(s) == {"G": 2}  # (the Bears is no Treefolk)
    check(s)


# -- Photon, Mighty Marvel: "add that much mana of any one color" ----------------------------------------------------------------------
def test_photon_adds_the_combat_damage_it_dealt_in_one_color(cards):
    s = table(cards, "Photon, Mighty Marvel")
    next_own_turn(s)
    attack(s, card_named(s, "Photon, Mighty Marvel"))
    assert offered(s) == ["{B}", "{G}", "{R}", "{U}", "{W}"]
    pick(s, "{U}")
    settle(s)
    assert pool(s) == {"U": 2}  # (2 damage: two mana of the one color chosen)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert pool(s) == {"U": 2}
    check(s)


def test_photon_blocked_by_a_wall_adds_nothing(cards):
    """It dealt its damage to a creature, not a player: no trigger."""
    s = table(cards, "Photon, Mighty Marvel")
    creature(s, "p2", "Wall", "0/4", "Token Creature — Wall", "Defender\nReach")
    next_own_turn(s)
    attack(s, card_named(s, "Photon, Mighty Marvel"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": card_named(s, "Wall", "p2").id, "attacker_id": card_named(s, "Photon, Mighty Marvel").id}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert pool(s) == {}
    check(s)
