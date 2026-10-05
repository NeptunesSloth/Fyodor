"""Wave 24A: group copies and copies of cards in graveyards (CR 707.2, 707.4, 707.9, 611.2c).

* "Each other creature becomes a copy of that creature until end of turn, except it isn't legendary" (Nanogene Conversion, Mirrorweave,
  Loki, Lord of Misrule): one layer-1 effect on the group as it is as the effect begins (611.2c); "other" is other than the copied object.
* "~ becomes a copy of target creature card in your graveyard with mana value X, except …" (Lazav, the Multifarious), "Exile target
  creature card from a graveyard. This creature becomes a copy of that card" (Dimir Doppelganger): a card's copiable values are its printed
  ones (707.2).
* "You may have this creature enter as a copy of any creature card in a graveyard" (Body Double, Echoing Deeps' land card).

Real Oracle text (tests/fixtures/wave24a_group_cards.json, from data/cards.sqlite); each scenario replays and round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand, token
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24a_group_cards.json").read_text("utf-8"))
SKIP = {"Forest"}
EXTRA = [card(c["name"], set_code="t24e", number=f"G{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA) if c["name"] not in SKIP]
FODDER = [
    card("Probe Beast", set_code="t24e", number="G90", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Beast", oracle_text="", power="3",
         toughness="3", colors=["G"], color_identity=["G"]),
    card("Probe Legend", set_code="t24e", number="G91", mana_cost="{1}{R}", cmc=2.0, type_line="Legendary Creature — Human Wizard",
         oracle_text="Haste", power="2", toughness="2", colors=["R"], color_identity=["R"], keywords=["Haste"]),
    card("Probe Dragon", set_code="t24e", number="G92", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Dragon", oracle_text="Flying",
         power="4", toughness="4", colors=["R"], color_identity=["R"], keywords=["Flying"]),
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def settle(s, pick=None, limit=30):
    """Resolve everything; ``pick`` (an object id) is chosen wherever it is offered, else the first option."""
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            ids = [o.id for o in d.options]
            choose(s, pick if pick in ids else ids[0])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=None, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def ability(s, c, **kw):
    index = next(a.index for a in ch(s, c).abilities if a.kind == "activated" and "copy" in a.text)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=index, **kw)


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] != "Forest"])
def test_the_promoted_cards_are_full(name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [], "legalities": {"commander": "legal"}}).level == "FULL"


def test_nanogene_conversion_makes_every_other_creature_a_nonlegendary_copy_until_end_of_turn(cards):
    s = build(cards, "Nanogene Conversion", "Probe Legend", "Probe Beast")
    legend = on_battlefield(s, "Probe Legend")
    beast = on_battlefield(s, "Probe Beast")
    theirs = token(s, "p2", "Opposing Bear", "2/2")
    cast(s, "Nanogene Conversion", targets=[legend.id], U=1, C=3)
    settle(s, pick=legend.id)
    for c in (beast, theirs):
        got = ch(s, s.state.cards[c.id])
        assert got.name == "Probe Legend" and "Legendary" not in got.supertypes and got.pt == (2, 2) and "haste" in got.keywords
    assert "Legendary" in ch(s, legend).supertypes  # (the chosen creature itself is no "other" creature)
    roundtrip(s)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 2)  # the end of turn: they are what they were
    assert ch(s, s.state.cards[beast.id]).name == "Probe Beast"


def test_loki_changes_only_the_creatures_you_control_other_than_the_chosen_one(cards):
    s = build(cards, "Loki, Lord of Misrule", "Probe Legend", "Probe Beast")
    loki = on_battlefield(s, "Loki, Lord of Misrule")
    legend = on_battlefield(s, "Probe Legend")
    beast = on_battlefield(s, "Probe Beast")
    theirs = token(s, "p2", "Opposing Bear", "2/2")
    for cid in (loki.id, legend.id, beast.id):  # (no summoning sickness for the {T} cost)
        s.state.rules.controlled_since[cid].turn = 0
    pay(s, U=1)
    index = next(a.index for a in ch(s, loki).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=loki.id, ability=index, targets=[legend.id])
    settle(s, pick=legend.id)
    assert ch(s, s.state.cards[beast.id]).name == "Probe Legend" and ch(s, s.state.cards[loki.id]).name == "Probe Legend"
    assert ch(s, s.state.cards[theirs.id]).name == "Opposing Bear"
    assert "Legendary" not in ch(s, s.state.cards[beast.id]).supertypes
    roundtrip(s)


def test_lazav_copies_a_creature_card_in_the_graveyard_with_mana_value_x(cards):
    s = build(cards, "Lazav, the Multifarious", "Probe Beast")
    lazav = on_battlefield(s, "Lazav, the Multifarious")
    beast = to_hand(s, "Probe Beast")
    act(s, "p1", type="move", card_ids=[beast.id], to={"player": "p1", "zone": "graveyard"})
    pay(s, U=3)
    ability(s, lazav, targets=[beast.id], x_value=3)
    settle(s, pick=beast.id)
    c = ch(s, s.state.cards[lazav.id])
    assert c.name == "Lazav, the Multifarious" and "Legendary" in c.supertypes and "Beast" in c.subtypes and c.pt == (3, 3)
    assert any("becomes a copy" in a.text for a in c.abilities)  # 707.9a: it has this ability
    roundtrip(s)


def test_dimir_doppelganger_exiles_the_card_and_becomes_a_copy_of_it(cards):
    s = build(cards, "Dimir Doppelganger", "Probe Beast")
    dop = on_battlefield(s, "Dimir Doppelganger")
    beast = to_hand(s, "Probe Beast")
    act(s, "p1", type="move", card_ids=[beast.id], to={"player": "p1", "zone": "graveyard"})
    pay(s, U=1, B=1, C=1)
    ability(s, dop, targets=[beast.id])
    settle(s, pick=beast.id)
    assert s.state.cards[beast.id].zone == "p1:exile"
    c = ch(s, s.state.cards[dop.id])
    assert c.name == "Probe Beast" and c.pt == (3, 3) and any("becomes a copy of that card" in a.text for a in c.abilities)
    roundtrip(s)


def test_body_double_enters_as_a_copy_of_a_creature_card_in_a_graveyard(cards):
    s = build(cards, "Body Double", "Probe Dragon")
    dragon = to_hand(s, "Probe Dragon")
    act(s, "p1", type="move", card_ids=[dragon.id], to={"player": "p1", "zone": "graveyard"})
    double = cast(s, "Body Double", U=1, C=4)
    for _ in range(8):
        d = decision(s)
        if d is not None and d.prompt.endswith("to copy"):
            choose(s, dragon.id)
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    c = ch(s, s.state.cards[double.id])
    assert c.name == "Probe Dragon" and c.pt == (4, 4) and "flying" in c.keywords
    assert s.state.cards[dragon.id].zone == "p1:graveyard"  # (a copy of the card: it stays there)
    roundtrip(s)


def test_the_graveyard_candidates_are_public_cards_only(cards):
    from app.rules import copying
    from app.rules.plan import Plan

    s = build(cards, "Body Double", "Probe Dragon", "Probe Beast")
    dragon = to_hand(s, "Probe Dragon")
    act(s, "p1", type="move", card_ids=[dragon.id], to={"player": "p1", "zone": "graveyard"})
    in_hand = to_hand(s, "Probe Beast")
    plan = Plan(s.state, "p1", s.cards, None)
    ids = copying.entry_candidates(plan, "p1", "creature card in a graveyard" + copying.TO_COPY)
    assert ids == [dragon.id] and in_hand.id not in ids
