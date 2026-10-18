"""Review 52 (head review of waves 52A-D, CR 2026-09-25): pins for behaviors the wave changed that its own tests didn't play, with real Oracle text
(tests/fixtures/review52_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review52_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r52", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer=None, limit=60):
    """Pass priority until the stack is empty; a decision is answered by ``answer(d)`` (option ids), else with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            picked = answer(d) if answer is not None else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=picked or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- 400.7, 603.6c: a card put into a graveyard that has since left it still triggers "is put into a graveyard"; "put it onto the battlefield" then finds no card
def test_lorcan_a_commander_moved_to_the_command_zone_is_not_stolen(cards):
    s = build(cards, ["Lorcan, Warlock Collector", "Murder"])
    put(s, "Lorcan, Warlock Collector")
    atraxa = card_named(s, "Atraxa, Praetors' Voice", "p2")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Murder")
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[atraxa.id])
    settle(s, lambda d: ["yes"] if any(o.id == "yes" for o in d.options) else None)

    assert zone_of(s, "Atraxa, Praetors' Voice", "p2") == "p2:command"
    check(s)


# -- 709.4b: Embodiment of Agonies: a split card's mana cost is its two halves combined (its ruling of 2019-07-12: Fire // Ice is {2}{U}{R}, Ral's Outburst's cost)
def test_embodiment_a_split_card_has_its_halves_combined_cost(cards):
    s = build(cards, ["Embodiment of Agonies", "Fire // Ice", "Ral's Outburst", "Lightning Bolt"])
    for name in ("Fire // Ice", "Ral's Outburst", "Lightning Bolt"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Embodiment of Agonies").id)
    settle(s)
    assert s.state.cards[card_named(s, "Embodiment of Agonies").id].counters.get("+1/+1") == 2  # {2}{U}{R} once, {R}
    check(s)


# -- 701.48a: "Learn." is the rummage, else a Lesson card from outside the game (the sideboard, as for the Wishes: 400.11a); Overgrown Arch
def learned(cards, discard):
    s = build(cards, ["Overgrown Arch", "Environmental Sciences", "Grizzly Bears"])
    arch = put(s, "Overgrown Arch")
    lesson = card_named(s, "Environmental Sciences")
    act(s, "p1", type="move", card_ids=[lesson.id], to={"zone": "sideboard"})
    to_hand(s, "Grizzly Bears")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=arch.id, ability=2)
    asked = []

    def answer(d):
        asked.append(d.prompt)
        ids = [o.id for o in d.options]
        return [x for x in ids if x in ("yes", "pay")][:1] or ids[:1] if discard else [x for x in ids if x in ("no", "decline")][:1] or [lesson.id]
    settle(s, answer)
    return s, lesson, asked


def test_overgrown_arch_learn_declined_rummage_fetches_a_lesson_from_the_sideboard(cards):
    s, lesson, asked = learned(cards, discard=False)
    assert s.state.cards[lesson.id].zone == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_overgrown_arch_learn_rummage_taken_asks_for_no_lesson(cards):
    s, lesson, asked = learned(cards, discard=True)
    assert s.state.cards[lesson.id].zone == "p1:sideboard" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    assert not any("outside the game" in p for p in asked)
    check(s)
