"""Wave 24A: "becomes a copy of …, except …" (CR 707.4, 707.9, 613.2): another / up to one target, the object a trigger names ("it", "that
creature"), pronouns of a character card ("his name is", "he's 4/4"), "has this ability" (707.9a), last known information for a creature
that died (608.2h).

Real Oracle text (tests/fixtures/wave24a_become_cards.json, from data/cards.sqlite); each scenario replays and round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_effects import replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24a_become_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24d", number=f"B{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA)]
FODDER = [
    card("Probe Beast", set_code="t24d", number="B90", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Beast", oracle_text="", power="3",
         toughness="3", colors=["G"], color_identity=["G"]),
    card("Probe Dragon", set_code="t24d", number="B91", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Dragon", oracle_text="Flying",
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


def settle(s, yes=True, limit=30):
    """Resolve everything; a yes/no question is answered ``yes``, any other choice the first option."""
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            labels = {o.label: o.id for o in d.options}
            choose(s, labels.get("Yes" if yes else "No") or d.options[0].id)
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


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [], "legalities": {"commander": "legal"}}).level == "FULL"


def test_impossible_man_takes_the_name_back_and_lasts_until_end_of_turn(cards):
    s = build(cards, "Impossible Man", "Probe Beast")
    man = on_battlefield(s, "Impossible Man")
    beast = on_battlefield(s, "Probe Beast")
    pay(s, U=1, C=2)
    index = next(a.index for a in ch(s, man).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=man.id, ability=index, targets=[beast.id])
    settle(s)
    c = ch(s, s.state.cards[man.id])
    assert c.name == "Impossible Man" and c.subtypes == {"Beast"} and c.pt == (3, 3)  # 707.9b: it keeps its name, copies the rest
    roundtrip(s)


def test_sarkhan_becomes_a_copy_of_the_dragon_that_entered(cards):
    s = build(cards, "Sarkhan, Soul Aflame", "Probe Dragon")
    sarkhan = on_battlefield(s, "Sarkhan, Soul Aflame")
    cast(s, "Probe Dragon", R=1, C=3)
    settle(s)
    c = ch(s, s.state.cards[sarkhan.id])
    assert c.name == "Sarkhan, Soul Aflame" and "Legendary" in c.supertypes and "Dragon" in c.subtypes and c.pt == (4, 4)
    assert "flying" in c.keywords
    roundtrip(s)


def test_sarkhan_may_decline(cards):
    s = build(cards, "Sarkhan, Soul Aflame", "Probe Dragon")
    sarkhan = on_battlefield(s, "Sarkhan, Soul Aflame")
    cast(s, "Probe Dragon", R=1, C=3)
    settle(s, yes=False)
    assert ch(s, s.state.cards[sarkhan.id]).pt == (2, 4)
    roundtrip(s)


def test_cemetery_puca_copies_the_creature_that_died_as_it_last_existed(cards):
    s = build(cards, "Cemetery Puca", "Probe Beast", "Doom Blade")
    puca = on_battlefield(s, "Cemetery Puca")
    beast = on_battlefield(s, "Probe Beast")
    cast(s, "Doom Blade", targets=[beast.id], B=1, C=2)  # (the second C is the {1} the Puca asks for)
    settle(s)
    c = ch(s, s.state.cards[puca.id])
    assert c.name == "Probe Beast" and c.pt == (3, 3)
    assert any("becomes a copy of that creature" in a.text for a in c.abilities)  # 707.9a: "except it has this ability"
    roundtrip(s)


def test_unstable_shapeshifter_copies_each_creature_that_enters(cards):
    s = build(cards, "Unstable Shapeshifter", "Probe Dragon", "Probe Beast")
    shifter = on_battlefield(s, "Unstable Shapeshifter")
    cast(s, "Probe Dragon", R=1, C=3)
    settle(s)
    assert ch(s, s.state.cards[shifter.id]).name == "Probe Dragon"
    cast(s, "Probe Beast", G=1, C=2)
    settle(s)  # (it kept the ability, 707.9a: it copies the next one too)
    assert ch(s, s.state.cards[shifter.id]).name == "Probe Beast"
    roundtrip(s)
