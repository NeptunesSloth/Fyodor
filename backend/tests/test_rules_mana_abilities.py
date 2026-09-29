"""Mana abilities beyond plain {T}: pain lands, filters, spending restrictions, counters as a cost,
the chosen color, life as a cost, "Activate only if you control …", and Reflecting Pool."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.casting import castable
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import run_until

SPELLS = [(1, "Shivan Reef"), (1, "Sungrass Prairie"), (1, "Ancient Ziggurat"), (1, "Vivid Marsh"), (1, "Sol Grail"),
          (1, "Blightsoil Druid"), (1, "Tainted Isle"), (1, "Reflecting Pool"), (1, "Grizzly Bears"), (1, "Swamp"),
          (1, "Forest"), (1, "Mountain"), (1, "Lightning Bolt"), (1, "Sol Ring")]
LIBRARY = [(8, "Island")]  # stays in the library (draws later in the game)


def table(cards, *on_battlefield):
    alice = deck(cards, "Krenko, Mob Boss", SPELLS + LIBRARY)
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    act(s, "p1", type="draw", count=len(SPELLS))
    for name in on_battlefield:
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "battlefield"})
    return s


def named(s, name):
    return next(s.state.cards[c] for c in s.state.cards if s.state.cards[c].name == name and s.state.cards[c].owner == "p1")


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=named(s, name).id, **kw)


def test_pain_land_hurts_only_for_colored_mana(cards):
    s = table(cards, "Shivan Reef")
    cast(s, "Sol Ring")  # {1}: the painless {C}
    assert s.state.players["p1"].life == 40 and named(s, "Shivan Reef").tapped
    act(s, "p1", type="tap", card_ids=[named(s, "Shivan Reef").id], tapped=False)
    cast(s, "Lightning Bolt", targets=["p2"])  # {R}: "deals 1 damage to you"
    assert s.state.players["p1"].life == 39


def test_a_plain_land_is_used_before_a_painful_one(cards):
    s = table(cards, "Shivan Reef", "Mountain")
    cast(s, "Lightning Bolt", targets=["p2"])
    assert named(s, "Mountain").tapped and not named(s, "Shivan Reef").tapped
    assert s.state.players["p1"].life == 40


def test_filter_land_needs_other_mana_for_its_activation(cards):
    s = table(cards, "Sungrass Prairie")
    assert not castable(s.state, "p1", named(s, "Grizzly Bears"), cards)  # it can't pay for itself
    act(s, "p1", type="move", card_ids=[named(s, "Forest").id], to={"zone": "battlefield"})
    cast(s, "Grizzly Bears")  # Forest pays {1} → Prairie adds {G}{W}, which pays {1}{G}
    assert named(s, "Grizzly Bears").zone in ("stack", "p1:battlefield")
    assert named(s, "Forest").tapped and named(s, "Sungrass Prairie").tapped
    assert s.state.players["p1"].mana == {}


def test_spending_restrictions(cards):
    s = table(cards, "Ancient Ziggurat", "Forest")
    assert not castable(s.state, "p1", named(s, "Lightning Bolt"), cards)  # creature spells only
    cast(s, "Grizzly Bears")
    assert named(s, "Ancient Ziggurat").tapped
    with pytest.raises(ActionError, match="only pay for certain things"):
        act(s, "p1", type="tap", card_ids=[named(s, "Ancient Ziggurat").id], tapped=False)
        act(s, "p1", type="activate_ability", card_id=named(s, "Ancient Ziggurat").id, ability=0)


def test_charge_counters_as_a_cost(cards):
    s = table(cards, "Vivid Marsh")
    marsh = named(s, "Vivid Marsh")
    act(s, "p1", type="counter", card_ids=[marsh.id], kind="charge", delta=2)
    cast(s, "Lightning Bolt", targets=["p2"])  # {R}: remove a charge counter for "any color"
    assert s.state.cards[marsh.id].counters.get("charge") == 1 and s.state.cards[marsh.id].tapped


def test_chosen_color(cards):
    s = table(cards, "Sol Grail")
    grail = named(s, "Sol Grail")
    assert not castable(s.state, "p1", named(s, "Lightning Bolt"), cards)  # no color chosen yet
    act(s, "p1", type="set_choice", card_id=grail.id, key="Chosen color", value="Red")
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.cards[grail.id].tapped


def test_life_as_a_cost(cards):
    s = table(cards, "Blightsoil Druid", "Mountain")
    druid = named(s, "Blightsoil Druid")
    extra = [c for c in zone(s.state, "p1", "hand") if s.state.cards[c].name != "Grizzly Bears"]
    act(s, "p1", type="move", card_ids=extra, to={"zone": "graveyard"})  # (no discarding at end of turn)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # no summoning sickness now
    cast(s, "Grizzly Bears")  # {1}{G}: Mountain + Druid (pay 1 life)
    assert s.state.cards[druid.id].tapped and s.state.players["p1"].life == 39


def test_activate_only_if_you_control_a_swamp(cards):
    s = table(cards, "Tainted Isle")
    assert not castable(s.state, "p1", named(s, "Lightning Bolt"), cards)
    ability = 1  # "{T}: Add {U} or {B}. Activate only if you control a Swamp."
    act(s, "p1", type="move", card_ids=[named(s, "Swamp").id], to={"zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=named(s, "Tainted Isle").id, ability=ability, mana_choice="B")
    assert s.state.players["p1"].mana == {"B": 1}


def test_reflecting_pool_copies_your_lands(cards):
    s = table(cards, "Reflecting Pool", "Forest")
    act(s, "p1", type="activate_ability", card_id=named(s, "Reflecting Pool").id, ability=0)
    assert s.state.players["p1"].mana == {"G": 1}
