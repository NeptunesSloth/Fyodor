"""Casting without paying the mana cost (CR 118.9, 107.3b, 608.2g): "you may cast a spell with
mana value N or less from your hand without paying its mana cost" (Electrodominance, the
Expertise cycle), "until end of turn, you may play that card without paying its mana cost"
(Mind's Desire), the static permissions (Omniscience, Fierce Guardianship's own line). X is 0,
additional costs can still be paid, declining keeps the card, hidden cards become public as they
are cast."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import permissions as P
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, rules

REAL = [
    card("Electrodominance", set_code="tst", number="F1", mana_cost="{X}{R}{R}", cmc=2.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Electrodominance deals X damage to any target. You may cast a spell with mana value X or less "
         "from your hand without paying its mana cost."),
    card("Yahenni's Expertise", set_code="tst", number="F2", mana_cost="{2}{B}{B}", cmc=4.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="All creatures get -3/-3 until end of turn. You may cast a spell with mana value 3 or less "
         "from your hand without paying its mana cost."),
    card("Mind's Desire", set_code="tst", number="F4", mana_cost="{4}{U}{U}", cmc=6.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Shuffle your library. Then exile the top card of your library. Until end of turn, you may play "
         "that card without paying its mana cost.\nStorm (When you cast this spell, copy it for each spell cast before it this turn.)"),
    card("Omniscience", set_code="tst", number="F5", mana_cost="{7}{U}{U}{U}", cmc=10.0, type_line="Enchantment", colors=["U"],
         color_identity=["U"], oracle_text="You may cast spells from your hand without paying their mana costs."),
    card("Fierce Guardianship", set_code="tst", number="F6", mana_cost="{2}{U}", cmc=3.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="If you control a commander, you may cast this spell without paying its mana cost.\n"
         "Counter target noncreature spell."),
    card("Blaze", set_code="tst", number="F7", mana_cost="{X}{R}", cmc=1.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Blaze deals X damage to any target."),
    card("Dracogenesis", set_code="tst", number="F8", mana_cost="{4}{R}{R}{R}", cmc=7.0, type_line="Enchantment", colors=["R"],
         color_identity=["R"], oracle_text="You may cast Dragon spells without paying their mana costs."),
    card("Test Drake", set_code="tst", number="F9", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Creature — Dragon", colors=["R"],
         color_identity=["R"], power="4", toughness="4", oracle_text="Flying"),
]


@pytest.fixture()
def cards(settings, card_db):
    build_database(fixture_cards() + REAL, settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, names, pid_deck=()):
    a = deck(cards, "Krenko, Mob Boss", [(1, n) for n in names] + list(pid_deck))
    b = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, where, pid="p1"):
    c = find(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": where})
    return s.state.cards[c.id]


def hints(s, pid="p1"):
    return s.view(pid)["rules"]["hints"]


def pick(s, ids):
    d = rules(s).decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    replay_matches(s)  # (reload: the history rebuilds the same table)
    assert GameState.model_validate(s.state.model_dump(mode="json")).model_dump(mode="json") == s.state.model_dump(mode="json")


# -- the wording ------------------------------------------------------------------------------------
def test_wordings_are_read_and_the_rest_refused():
    ok = scripts.parse_effects("You may cast a spell with mana value 5 or less from your hand without paying its mana cost.")
    assert ok is not None and ok[0] == [{"do": "free_cast", "zone": "hand", "filter": None, "optional": True, "mv": 5}]
    x = scripts.parse_effects("You may cast an instant or sorcery spell from your hand with mana value X or less without paying its mana cost.")
    assert x is not None and x[0][0]["mv"] == "x" and x[0][0]["filter"]
    # more instructions after the cast would be lost: refused
    assert scripts.parse_effects("You may cast a spell with mana value 3 or less from your hand without paying its mana cost. "
                                 "Draw a card.") is None
    # several cards at once / no source of "that card" / a land played as this resolves: not modelled
    assert scripts.parse_effects("Exile the top card of your library. You may cast those cards without paying their mana costs.") is None
    assert scripts.parse_effects("Draw a card. You may cast that card without paying its mana cost.") is None
    assert scripts.parse_effects("You may cast any number of spells from among them without paying their mana costs.") is None
    assert P.define_static("You may cast spells from your hand without paying their mana costs.", "static")["free"]
    assert P.define_static("You may cast Dragon spells without paying their mana costs.", "static")["zone"] == "any"
    assert P.define_static("If you control a commander, you may cast this spell without paying its mana cost.", "static")["cond"] == "commander"
    assert P.define_static("Any player may cast creature spells with mana value 3 or less without paying their mana costs.", "static") is None


# -- resolution: "you may cast a spell ... from your hand without paying its mana cost" ---------------
def test_electrodominance_casts_a_cheap_spell_free_and_x_is_zero(cards):
    s = build(cards, ["Electrodominance", "Blaze", "Grizzly Bears", "Rift Bolt"])
    for n in ("Electrodominance", "Blaze", "Grizzly Bears", "Rift Bolt"):
        put(s, n, "hand")
    spell = find(s, "Electrodominance")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38
    d = rules(s).decision
    assert d is not None and d.kind == "choose_cards"
    offered = {o.id for o in d.options}  # mana value 2 or less: Blaze (X = 0 in hand: 1) and Bears (2), not Rift Bolt (3)
    assert offered == {find(s, "Blaze").id, find(s, "Grizzly Bears").id}
    pick(s, [find(s, "Blaze").id])
    d = rules(s).decision  # Blaze's target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"]) if d else None
    pass_until_stack_empty(s)
    blaze = find(s, "Blaze")
    assert blaze.zone == "p1:graveyard"
    assert s.state.players["p2"].life == 38  # X was 0: no damage
    assert s.state.players["p1"].mana.get("R", 0) == 1  # nothing was paid for it (5 - RR - 2 for X)... 5-4
    assert rules(s).free_casts == []
    roundtrip(s)


def test_declining_keeps_the_card_and_nothing_is_cast_later(cards):
    s = build(cards, ["Yahenni's Expertise", "Grizzly Bears"])
    put(s, "Yahenni's Expertise", "hand")
    bears = put(s, "Grizzly Bears", "hand")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=find(s, "Yahenni's Expertise").id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    if d is not None and d.kind == "choose_cards" and (d.resume or {}).get("step") != "free_cast_pick":
        pick(s, [])
        d = rules(s).decision
    assert d is not None and (d.resume or {}).get("step") == "free_cast_pick"
    pick(s, [])
    assert s.state.cards[bears.id].zone == "p1:hand" and rules(s).free_casts == []
    with pytest.raises(ActionError):  # it was a one-time chance
        act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    roundtrip(s)


def test_nothing_eligible_offers_nothing(cards):
    s = build(cards, ["Yahenni's Expertise", "Mind's Desire"])
    put(s, "Yahenni's Expertise", "hand")
    put(s, "Mind's Desire", "hand")  # mana value 6 > 3
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=find(s, "Yahenni's Expertise").id)
    pass_until_stack_empty(s)
    assert rules(s).decision is None
    assert find(s, "Mind's Desire").zone == "p1:hand" and not s.state.zones.get("stack")
    roundtrip(s)


# -- "play that card without paying" (Mind's Desire) -----------------------------------------------
def test_minds_desire_grants_a_free_play_of_the_exiled_card(cards):
    s = build(cards, ["Mind's Desire"], pid_deck=[(8, "Grizzly Bears")])
    desire = put(s, "Mind's Desire", "hand")
    mana(s, U=6)
    act(s, "p1", type="cast_spell", card_id=desire.id)
    pass_until_stack_empty(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert len(exiled) == 1
    card_in_exile = exiled[0]
    assert card_in_exile.id in hints(s)["free_castable"]
    assert card_in_exile.id not in hints(s)["castable"]  # (118.9b: opt-in, nothing to pay with anyway)
    act(s, "p1", type="cast_spell", card_id=card_in_exile.id, free=True)
    pass_until_stack_empty(s)
    assert s.state.cards[card_in_exile.id].zone in ("p1:battlefield", "p1:stack")
    assert s.state.players["p1"].mana == {}
    assert rules(s).permissions == []
    roundtrip(s)


# -- static permissions ------------------------------------------------------------------------------
def test_omniscience_free_cast_from_hand_sets_x_to_zero_and_may_be_declined(cards):
    s = build(cards, ["Omniscience", "Blaze", "Grizzly Bears"])
    put(s, "Omniscience", "battlefield")
    blaze, bears = put(s, "Blaze", "hand"), put(s, "Grizzly Bears", "hand")
    assert {blaze.id, bears.id} <= set(hints(s)["free_castable"])
    # a plain cast still pays the mana cost (the free way is opt-in) …
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    # … and the free one pays nothing, X = 0
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=blaze.id, free=True, targets=["p2"])
    record = rules(s).payments[rules(s).object_id(blaze.id)]
    assert record.alternative == "free" and record.total_cost == "{0}" and record.x == 0
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 40
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    roundtrip(s)


def test_free_cast_keeps_additional_costs(cards):
    """118.9d: kicker is an additional cost: it is still paid on a spell cast without paying its mana cost."""
    s = build(cards, ["Omniscience", "Test Kicked Bolt"])
    put(s, "Omniscience", "battlefield")
    bolt = put(s, "Test Kicked Bolt", "hand")
    act(s, "p1", type="set_prefs", hold_priority=True)
    with pytest.raises(ActionError):  # the kicker {1}{R} can't be paid
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, kicker=1, targets=["p2"])
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, kicker=1, targets=["p2"])
    record = rules(s).payments[rules(s).object_id(bolt.id)]
    assert record.alternative == "free" and record.total_cost == "{1}{R}" and record.kicked == 1
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


def test_dracogenesis_only_frees_matching_spells(cards):
    s = build(cards, ["Dracogenesis", "Test Drake", "Grizzly Bears"])
    put(s, "Dracogenesis", "battlefield")
    drake, bears = put(s, "Test Drake", "hand"), put(s, "Grizzly Bears", "hand")
    assert drake.id in hints(s)["free_castable"] and bears.id not in hints(s)["free_castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    act(s, "p1", type="cast_spell", card_id=drake.id, free=True)
    pass_until_stack_empty(s)
    assert s.state.cards[drake.id].zone == "p1:battlefield"
    roundtrip(s)


def test_fierce_guardianship_needs_a_commander_on_the_battlefield(cards):
    s = build(cards, ["Fierce Guardianship", "Lightning Bolt"])
    guard, bolt = put(s, "Fierce Guardianship", "hand"), put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert guard.id not in hints(s)["free_castable"]  # the commander is still in the command zone
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=guard.id, free=True, targets=[bolt.id])
    krenko = find(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    assert guard.id in hints(s)["free_castable"]
    act(s, "p1", type="cast_spell", card_id=guard.id, free=True, targets=[bolt.id])
    assert s.state.cards[guard.id].zone == "stack" and s.state.players["p1"].mana == {}
    act(s, "p1", type="set_prefs", hold_priority=False)
    for _ in range(12):
        if not s.state.zones.get("stack") or rules(s).decision is not None:
            break
        act(s, rules(s).priority, type="pass_priority")
    assert not s.state.zones.get("stack") and s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.players["p2"].life == 40
    roundtrip(s)
