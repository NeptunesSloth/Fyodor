"""Wave 30H: linked exiled sets and what is done with them (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30h_linked_exile_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 607.2a: "cards exiled with ~" are only the cards the object's linked exiling ability put in exile, each while it is still that object
  there (400.7); a new object (the permanent left and came back) has none of them.
* 607.2b: a replacement effect that exiles is the exiling half too (Valgavoth).
* 608.2g: "you may cast a spell from among cards exiled with ~ without paying its mana cost" is done as the ability resolves; one not cast
  then is not cast later. 601.3, 305.1: a static "you may play / cast … cards exiled with ~" is a permission with the normal timing.
* 118.9, 119.4: Valgavoth's alternative cost (life equal to the mana value) replaces the mana cost of a spell cast with that permission.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from app.rules.casting import castable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30h_linked_exile_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30h", number=f"H{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone(s, pid, z):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{z}", []))


def put_in(s, name, where, pid="p1", position=None):
    c = card_named(s, name, pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": where}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    for name in reversed(names):
        put_in(s, name, "library", pid, "top")


def settle(s, prefer=(), limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (option ids or card names, in that order) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for n in prefer for o in d.options if n in (o.id, o.label, o.card_id)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want[:1] if want else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_turn(s, number):
    """Pass priority (no attackers, no blockers) until the main phase of that turn."""
    for _ in range(80):
        if s.state.turn.number == number and s.state.turn.phase == "main1" and not s.state.rules.decision:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def attack(s, name):
    """Alice attacks Bob with that creature (her first main phase of the turn)."""
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers", d
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, name).id, "target": "p2"}])


JELEVA = "Jeleva, Nephalia's Scourge"
ALICE_TOP = ["Lightning Bolt", "Grizzly Bears", "Pyroclasm", "Giant Growth"]
BOB_TOP = ["Counterspell", "Murder", "Firebolt", "Rampant Growth"]


def jeleva_game(cards):
    """Alice casts Jeleva for four mana: each player exiles the top four cards of their library (both sets are linked to her)."""
    s = build(cards, [JELEVA, "Mulldrifter", *ALICE_TOP], BOB_TOP)
    stack_top(s, ALICE_TOP)
    stack_top(s, BOB_TOP, "p2")
    to_hand(s, JELEVA)
    mana(s, U=1, B=1, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, JELEVA).id)
    settle(s)
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP) and zone(s, "p2", "exile") == sorted(BOB_TOP)
    return s


def pick(s, *names):
    """Answer the open choice with these cards (none: no card)."""
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, n, pid).id for n, pid in names])
    return d


def offered(s):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", d
    return sorted(o.label for o in d.options)


def test_jeleva_casts_one_instant_or_sorcery_of_either_players_exiled_cards_as_the_trigger_resolves(cards):
    """608.2g + 607.2a: "Whenever Jeleva attacks, you may cast an instant or sorcery spell from among cards exiled with Jeleva without paying its
    mana cost." Cards of both libraries are offered (not the creature), one is cast, and a card not cast then is not cast later."""
    s = jeleva_game(cards)
    to_turn(s, 3)
    attack(s, JELEVA)
    # (Counterspell has no spell to target, 601.2c: it can't be cast, so it isn't offered)
    assert offered(s) == sorted(["Lightning Bolt", "Pyroclasm", "Giant Growth", "Murder", "Firebolt", "Rampant Growth"])
    pick(s)  # (none: she passes on the cast)
    settle(s)
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP) and zone(s, "p2", "exile") == sorted(BOB_TOP)
    assert not castable(s.state, "p1", card_named(s, "Lightning Bolt"), cards)  # (nothing keeps a permission to cast it later)
    check(s)
    to_turn(s, 5)
    attack(s, JELEVA)
    assert "Firebolt" in offered(s)
    pick(s, ("Firebolt", "p2"))  # Bob's own card, cast by Alice
    d = s.state.rules.decision
    assert d.kind == "choose_one" and "Firebolt" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert zone(s, "p2", "graveyard") == ["Firebolt"] and s.state.players["p2"].life == 36  # (40 - 1 and 1 from Jeleva in two combats, 2 from Firebolt; a card goes to its owner's graveyard)
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP) and zone(s, "p2", "exile") == sorted(set(BOB_TOP) - {"Firebolt"})
    check(s)


def test_a_jeleva_that_came_back_is_a_new_object_without_the_old_cards(cards):
    """607.2a + 400.7: the Jeleva that left the battlefield and returned has exiled nothing; the cards the old one exiled are still in exile,
    but nothing is offered for them (the Rulings: "it won't be associated with the cards the other Jeleva exiled")."""
    s = jeleva_game(cards)
    to_turn(s, 3)
    put_in(s, JELEVA, "hand")
    put_in(s, JELEVA, "battlefield")  # (not cast: X is 0, nothing is exiled)
    settle(s)
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP)
    to_turn(s, 5)
    attack(s, JELEVA)
    assert s.state.rules.decision is None  # (no choice at all: the new Jeleva has no cards)
    settle(s)
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP) and zone(s, "p2", "exile") == sorted(BOB_TOP)
    check(s)


def test_a_card_cast_from_the_set_that_returns_to_exile_is_a_new_object(cards):
    """400.7: Lightning Bolt cast this way is put into the graveyard; put into exile again it is a new object, no longer exiled with Jeleva."""
    s = jeleva_game(cards)
    to_turn(s, 3)
    attack(s, JELEVA)
    pick(s, ("Lightning Bolt", "p1"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Lightning Bolt"] and s.state.players["p2"].life == 36  # (Bolt, then the 1 combat damage)
    put_in(s, "Lightning Bolt", "exile")
    assert "Lightning Bolt" in zone(s, "p1", "exile")
    to_turn(s, 5)
    attack(s, JELEVA)
    assert offered(s) == sorted(["Pyroclasm", "Giant Growth", "Murder", "Firebolt", "Rampant Growth"])  # (no Lightning Bolt)
    check(s)


def kaho_game(cards):
    s = build(cards, ["Kaho, Minamo Historian", "Lightning Bolt", "Giant Growth", "Murder", "Counterspell"], ["Grizzly Bears"])
    to_hand(s, "Kaho, Minamo Historian")
    mana(s, U=2, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kaho, Minamo Historian").id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, n).id for n in ("Lightning Bolt", "Giant Growth", "Murder")])
    settle(s)
    assert zone(s, "p1", "exile") == ["Giant Growth", "Lightning Bolt", "Murder"]
    return s


def test_kaho_casts_a_spell_with_mana_value_exactly_x_from_the_cards_it_exiled(cards):
    """608.2g + 607.2a: "{X}, {T}: You may cast a spell with mana value X from among cards exiled with Kaho without paying its mana cost." X is
    the mana value itself, not "or less"; nothing is offered when no card has it."""
    s = kaho_game(cards)
    put(s, "Grizzly Bears", "p2")
    to_turn(s, 3)
    kaho = card_named(s, "Kaho, Minamo Historian")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=kaho.id, ability=1, x_value=1)
    assert offered(s) == ["Giant Growth", "Lightning Bolt"]  # (Murder is mana value 3)
    pick(s)
    settle(s)
    to_turn(s, 5)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=kaho.id, ability=1, x_value=3)
    assert offered(s) == ["Murder"]  # (exactly 3: neither of the cheaper ones)
    pick(s, ("Murder", "p1"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[card_named(s, "Grizzly Bears", "p2").id])
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Murder"] and zone(s, "p2", "graveyard") == ["Grizzly Bears"]
    check(s)
    to_turn(s, 7)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=kaho.id, ability=1, x_value=2)
    assert s.state.rules.decision is None  # (nothing has mana value 2)
    settle(s)
    check(s)


def test_a_kaho_that_came_back_is_a_new_object_without_the_old_cards(cards):
    """607.2a + 400.7: Kaho's ruling - "Kaho's activated ability refers only to cards exiled by its triggered ability"; a new Kaho has none."""
    s = kaho_game(cards)
    to_turn(s, 3)
    put_in(s, "Kaho, Minamo Historian", "hand")
    put_in(s, "Kaho, Minamo Historian", "battlefield")
    to_turn(s, 5)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Kaho, Minamo Historian").id, ability=1, x_value=1)
    assert s.state.rules.decision is None  # (Lightning Bolt and Giant Growth are still in exile, exiled with the old Kaho)
    settle(s)
    assert zone(s, "p1", "exile") == ["Giant Growth", "Lightning Bolt", "Murder"]
    check(s)


def test_izzet_chemister_casts_any_number_of_its_exiled_cards_when_it_is_sacrificed(cards):
    """"{1}{R}, {T}, Sacrifice this creature: Cast any number of cards exiled with this creature without paying their mana costs." The creature
    is gone when the ability resolves (its last known information, 608.2h, still owns the set); the cards are cast one at a time."""
    s = build(cards, ["Izzet Chemister", "Lightning Bolt", "Giant Growth", "Pyroclasm"], ["Grizzly Bears"])
    chemister = put(s, "Izzet Chemister")
    for name in ("Lightning Bolt", "Pyroclasm"):
        put_in(s, name, "graveyard")
    for turn, name in ((1, "Lightning Bolt"), (3, "Pyroclasm")):
        if turn > 1:
            to_turn(s, turn)
        mana(s, R=1)
        act(s, "p1", type="activate_ability", card_id=chemister.id, ability=1, targets=[card_named(s, name).id])
        settle(s)
        assert card_named(s, name).zone == "p1:exile"
    put_in(s, "Giant Growth", "exile")  # (exiled some other way: not one of them)
    to_turn(s, 5)
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=chemister.id, ability=2)
    assert offered(s) == ["Lightning Bolt", "Pyroclasm"]
    pick(s, ("Pyroclasm", "p1"))
    assert offered(s) == ["Lightning Bolt"]  # (one at a time; "any number")
    pick(s, ("Lightning Bolt", "p1"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Izzet Chemister", "Lightning Bolt", "Pyroclasm"] and zone(s, "p1", "exile") == ["Giant Growth"]
    assert s.state.players["p2"].life == 37
    check(s)


def test_cards_exiled_with_a_creature_are_not_encoded_on_it(cards):
    """702.99: only a cipher spell encoded on a creature gives it "copy the encoded card" when it deals combat damage to a player. The cards a creature's
    linked ability exiled (607.2a) once did: Jeleva, connecting, asked to copy and cast each of the eight cards (they shared the record)."""
    s = jeleva_game(cards)
    to_turn(s, 3)
    attack(s, JELEVA)
    pick(s)
    asked = []
    for _ in range(40):
        if s.state.turn.phase == "main2" and not s.state.rules.decision:
            break
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.kind)
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "main2" and s.state.players["p2"].life == 39 and "order" not in asked and not s.state.zones.get("stack")
    assert zone(s, "p1", "exile") == sorted(ALICE_TOP) and zone(s, "p2", "exile") == sorted(BOB_TOP)
    check(s)
