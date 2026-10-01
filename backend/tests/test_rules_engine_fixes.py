"""Regression tests for engine simplifications replaced by the real rule (batch 3, engine items).

Every card is a real Commander-legal card; its Oracle text (the card database, 2026-09-30 snapshot)
is transcribed below and named in the comment above it. CR 2026-09-25.

- 616.1 / 614.16: token copies go through the pausable token choke point (the creator orders
  non-commuting replacements; the instruction's binding and later steps follow the answer).
- 707.5: a card entering as a copy keeps its copy effect whatever object number it gets.
- 603.6a / 614.12 / 613.7m: permanents put onto the battlefield together enter as one event, judged
  against the table before any of them enters, timestamped in APNAP order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_replacements2 import (
    DOUBLING_SEASON,
    XORN,
    answer,
    decision,
    named_all,
    permanent,
    reload,
)
from tests.test_rules_suspend import until

EXTRA = [
    # Glacial Fortress
    card("Glacial Fortress", set_code="tef", number="E1", type_line="Land",
         oracle_text="This land enters tapped unless you control a Plains or an Island.\n{T}: Add {W} or {U}.",
         color_identity=["W", "U"]),
    # Clone
    card("Clone", set_code="tef", number="E2", mana_cost="{3}{U}", cmc=4.0, type_line="Creature — Shapeshifter",
         oracle_text="You may have this creature enter as a copy of any creature on the battlefield.", colors=["U"],
         color_identity=["U"], power="0", toughness="0"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# The Mending of Dominaria, chapter III (its first sentence, as an activated ability)
RETURN_LANDS = "{1}: Return all land cards from your graveyard to the battlefield."
# the same instruction for creature cards
RETURN_CREATURES = "{1}: Return all creature cards from your graveyard to the battlefield."
# Molten Duplication (sorcery), as the activated ability of a custom permanent (the same effect text)
MOLTEN_DUPLICATION = ("{1}: Create a token that's a copy of target artifact or creature you control, except it's an "
                      "artifact in addition to its other types. It gains haste until end of turn. Sacrifice it at the "
                      "beginning of the next end step.")
TREASURE = "{T}, Sacrifice this token: Add one mana of any color."


def treasure(s, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": "Treasure", "type_line": "Token Artifact — Treasure",
                                                       "text": TREASURE})
    return named_all(s, "Treasure", pid)[-1]


def activate(s, card_, pid="p1", **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card_.id, ability=0, **kw)
    pass_until_stack_empty(s)


# -- token copies: 616.1 order through the token choke point ------------------------------------------
def test_a_token_copy_asks_the_creator_to_order_xorn_and_doubling_season(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    token(s, "p1", "Xorn", "3/2", XORN)
    gold = treasure(s)
    dup = permanent(s, "p1", "Molten Duplication", "Enchantment", MOLTEN_DUPLICATION)
    activate(s, dup, targets=[gold.id])
    d = decision(s)
    assert d is not None and d.player == "p1" and d.resume["step"] == "replace_order"  # 616.1: the creator's choice
    assert len(named_all(s, "Treasure")) == 1  # nothing is created before the choice (614.6)
    labels = {o.id: o.label for o in d.options}
    assert "3 Treasure" in labels["yes"] and "4 Treasure" in labels["no"]
    paused = reload(s, cards)  # saved and loaded while the choice is open: it goes on the same way
    for game in (paused, s):
        answer(game, "no")  # Xorn first: 1 + 1 = 2, then doubled: 4
        pass_until_stack_empty(game)
    assert len(named_all(paused, "Treasure")) == 5
    copies = [c for c in named_all(s, "Treasure") if c.id != gold.id]
    assert len(copies) == 4 and decision(s) is None
    # the instruction went on with the answer: "It gains haste" bound the four copies, and
    # "Sacrifice it at the beginning of the next end step" waits for them
    assert all("haste" in ch(s, c).keywords for c in copies)
    assert len(s.state.rules.delayed) == 1
    replay_matches(s)
    again = reload(s, cards)
    assert len(named_all(again, "Treasure")) == 5
    until(s, lambda s: not s.state.rules.delayed, limit=60)
    pass_until_stack_empty(s)
    assert [c.id for c in named_all(s, "Treasure")] == [gold.id]  # sacrificed (and gone: 704.5d)


# -- simultaneous entries (603.6a, 614.12, 613.7m) ----------------------------------------------------
def to_graveyard(s, *cards_, pid="p1"):
    for c in cards_:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})


def test_a_check_land_does_not_see_an_island_entering_with_it(cards):
    """614.12: "enters tapped unless you control a Plains or an Island" is judged before either
    enters — the Island returned with it isn't there yet."""
    s = build(cards, "Glacial Fortress", "Island")
    fortress, island = named(s, "Glacial Fortress"), named(s, "Island")
    to_graveyard(s, island, fortress)
    activate(s, permanent(s, "p1", "The Mending of Dominaria", "Enchantment", RETURN_LANDS))
    assert s.state.cards[fortress.id].zone == s.state.cards[island.id].zone == "p1:battlefield"
    assert s.state.cards[fortress.id].tapped and not s.state.cards[island.id].tapped
    # one event (603.6a): both zone changes are one batch
    batches = {e.batch for e in s.state.rules.events if e.kind == "zone_change" and e.to_zone == "p1:battlefield"
               and e.card in (fortress.id, island.id)}
    assert len(batches) == 1
    replay_matches(s)


@pytest.mark.parametrize("clone_first", [True, False])
def test_clone_entering_with_another_creature_keeps_its_copy(cards, clone_first):
    """707.5: the copy effect follows Clone onto the battlefield whatever object number it gets
    (two creatures entering together: never a predicted id)."""
    s = build(cards, "Clone", "Grizzly Bears")
    clone, bears = named(s, "Clone"), named(s, "Grizzly Bears")
    to_graveyard(s, *((clone, bears) if clone_first else (bears, clone)))
    chieftain = token(s, "p1", "Goblin Chieftain", "3/3")
    activate(s, permanent(s, "p1", "Raiser", "Enchantment", RETURN_CREATURES))
    d = decision(s)
    assert d is not None and chieftain.id in {o.id for o in d.options}
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # nothing entered before the choice (614.12a)
    answer(s, chieftain.id)
    pass_until_stack_empty(s)
    copy = ch(s, s.state.cards[clone.id])
    assert copy.name == "Goblin Chieftain" and copy.pt == (3, 3)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)


# -- 603.10a / 700.4: a crewed Vehicle dies as the creature it was ------------------------------------
# Zulaport Cutthroat (creature 1/1)
ZULAPORT = "Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life."


@pytest.mark.parametrize("crewed", [True, False])
def test_a_crewed_vehicle_dies_as_a_creature(cards, crewed):
    """603.10a: "another creature you control dies" looks back in time — the Vehicle was an
    artifact creature while crewed (a layer-4 effect gone once it's in the graveyard, 400.7)."""
    s = build(cards, "Sky-Skiff", "Murder")
    skiff = named(s, "Sky-Skiff")
    act(s, "p1", type="move", card_ids=[skiff.id], to={"player": "p1", "zone": "battlefield"})
    token(s, "p1", "Zulaport Cutthroat", "1/1", ZULAPORT)
    pilot = token(s, "p1", "Pilot", "1/1")
    if crewed:
        act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1)  # "Crew 1"
        answer(s, pilot.id)
        pass_until_stack_empty(s)
        assert ch(s, s.state.cards[skiff.id]).is_creature
    murder = named(s, "Murder")
    act(s, "p1", type="move", card_ids=[murder.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"B": 3})
    if not crewed:  # (Murder needs a creature: an uncrewed Vehicle is destroyed by hand)
        act(s, "p1", type="move", card_ids=[skiff.id], to={"player": "p1", "zone": "graveyard"})
    else:
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[skiff.id])
    pass_until_stack_empty(s)
    assert s.state.cards[skiff.id].zone == "p1:graveyard"
    assert not ch(s, s.state.cards[skiff.id]).is_creature  # (in the graveyard: just an artifact card)
    assert s.state.players["p1"].life == (41 if crewed else 40)
    assert s.state.players["p2"].life == (39 if crewed else 40)
    replay_matches(s)


# -- 615: "prevent all damage … this turn" records know their source --------------------------------------
# Trained Pronghorn (creature 1/1)
TRAINED_PRONGHORN = "Discard a card: Prevent all damage that would be dealt to this creature this turn."


def bolt(s, target, pid="p1"):
    spell = named(s, "Lightning Bolt")
    act(s, pid, type="move", card_ids=[spell.id], to={"player": pid, "zone": "hand"})
    act(s, pid, type="add_mana", player=pid, mana={"R": 1})
    act(s, pid, type="cast_spell", card_id=spell.id, targets=[target])
    pass_until_stack_empty(s)


def test_trained_pronghorn_prevents_damage_to_itself_only_as_that_object(cards):
    """615.1 / 400.7: "this creature" is the ability's source as the object it is now (the record
    is locked to that object and names its card) — the damage to it is prevented."""
    s = build(cards, "Lightning Bolt", "Grizzly Bears")
    pronghorn = token(s, "p1", "Trained Pronghorn", "1/1", TRAINED_PRONGHORN)
    bears = named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="activate_ability", card_id=pronghorn.id, ability=0)
    while decision(s) is not None:  # (the card to discard)
        answer(s, bears.id)
    pass_until_stack_empty(s)
    [rec] = [r for r in s.state.rules.replacements if r.get("kind") == "prevent"]
    assert rec["source_card"] == pronghorn.id and rec["scope"]["to_oids"] == [s.state.rules.object_id(pronghorn.id)]
    bolt(s, pronghorn.id)
    assert s.state.cards[pronghorn.id].zone == "p1:battlefield" and not s.state.cards[pronghorn.id].damage
    replay_matches(s)


def test_gideon_jura_prevention_names_its_source(cards):
    """Gideon Jura's 0: "Prevent all damage that would be dealt to him this turn" — the plain
    "prevent all" record, locked to Gideon (no special primitive any more)."""
    from app.rules import scripts

    effects, _, _ = scripts.parse_effects(
        "Until end of turn, ~ becomes a 6/6 Human Soldier creature that's still a planeswalker. Prevent all damage "
        "that would be dealt to him this turn.")
    assert effects[-1] == {"do": "prevent_all", "scope": {"combat": None, "to_objects": "self"}}


def test_simultaneous_entries_are_timestamped_in_apnap_order(cards):
    """613.7m: the active player's permanent gets the earlier timestamp, whatever order the effect
    lists them in; both enter in one step under their own controllers."""
    from app.rules import attachments
    from app.rules.plan import Plan

    s = build(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    plan = Plan(s.state, "p1", cards, None)
    assert attachments.enter(plan, [{"card": island.id, "player": "p2", "actor": "p2"},
                                    {"card": forest.id, "player": "p1", "actor": "p1"}], None)
    assert plan.state.cards[forest.id].zone == "p1:battlefield" and plan.state.cards[island.id].zone == "p2:battlefield"
    assert [st["type"] for st in plan.steps] == ["move"]  # one event (603.6a)
    objects = plan.state.rules.objects
    assert objects[forest.id] < objects[island.id]
