"""Wave 28D: "where X is" values that depend on an event or a result (CR 2026-09-25). Real Oracle text; every scenario checks the replay and
a save and a load.

* 603.3d / 601.2c: a triggered ability's targets are chosen as it is put on the stack, so "up to X target …, where X is the number of
  cards looked at while scrying this way" (Elrond, Elvish Mariner) and "… the number of nonland cards milled this way" (The Wise Mothman)
  are read from the trigger event then (701.22d, 603.2c); "this way" in a "one or more" batch trigger is that batch.
* 107.3c: the text defines X; 601.2c: the number of targets doesn't change after.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

REAL = [
    ("Elrond, Master of Healing", "{2}{W}{U}", "Legendary Creature — Elf Noble", "3", "4",
     "Whenever you scry, put a +1/+1 counter on each of up to X target creatures, where X is the number of cards looked at while scrying this way.\n"
     "Whenever a creature you control with a +1/+1 counter on it becomes the target of a spell or ability an opponent controls, you may draw a card."),
    ("Elvish Mariner", "{2}{U}", "Creature — Elf Warrior", "2", "3",
     "Whenever this creature attacks, scry 1.\nWhenever you scry, tap up to X target nonland permanents, where X is the number of cards looked at while scrying this way."),
    ("The Wise Mothman", "{2}{G}{G}", "Legendary Creature — Mutant Insect", "3", "3",
     "Flying\nWhenever The Wise Mothman enters or attacks, each player gets a rad counter.\nWhenever one or more nonland cards are milled, put a +1/+1 "
     "counter on each of up to X target creatures, where X is the number of nonland cards milled this way."),
    ("Preordain", "{U}", "Sorcery", None, None, "Scry 2, then draw a card."),
    ("Thought Scour", "{U}", "Instant", None, None, "Target player mills two cards. Draw a card."),
    ("Opt", "{U}", "Instant", None, None, "Scry 1.\nDraw a card."),
]
EXTRA = [card(n, set_code="t28w", number=f"W{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["U"], color_identity=["U"], oracle_text=text, **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Elrond, Master of Healing", "Elvish Mariner", "The Wise Mothman"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name):
    spell = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": ["p1"]} if name == "Thought Scour" else {}))
    return spell


def finish_scry(s):
    """Answer the scry's own prompts (nothing to the bottom, the order as offered); the decision that follows is returned."""
    d = until_asked(s)
    for _ in range(6):
        if d is None or d.resume.get("step") == "trigger_group":
            return d
        if d.kind == "order":
            pick(s, *[o.id for o in d.options])
        else:
            pick(s)
        d = until_asked(s)
    raise AssertionError(d)


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


@pytest.mark.parametrize("scry", [2, 1])
def test_elrond_counts_the_cards_looked_at(cards, scry):
    s = build(cards, ["Elrond, Master of Healing", "Preordain", "Opt"])
    put(s, "Elrond, Master of Healing")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub", "Elf")]
    mana(s, U=1)
    cast(s, "Preordain" if scry == 2 else "Opt")
    d = finish_scry(s)
    assert d is not None and d.kind == "choose_cards"  # (Elrond's targets: up to X)
    assert d.max_choices == scry  # 603.3d / 601.2c: X = the cards looked at while scrying
    check(s)
    pick(s, mine[0].id)
    until_asked(s)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert counters(s, mine[0]) == 1 and counters(s, mine[1]) == 0
    check(s)


def test_elrond_scrying_with_a_short_library_looks_at_fewer(cards):
    s = build(cards, ["Elrond, Master of Healing", "Preordain"])
    put(s, "Elrond, Master of Healing")
    creature(s, "p1", "Bear")
    spell = to_hand(s, "Preordain")
    for c in list(s.state.zones["p1:library"][1:]):
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})  # (one card left)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = finish_scry(s)
    assert d is not None and d.max_choices == 1  # 701.22d: one card was looked at
    check(s)


def test_elvish_mariner_taps_up_to_that_many(cards):
    s = build(cards, ["Elvish Mariner", "Preordain"], ["Llanowar Elves"])
    put(s, "Elvish Mariner")
    theirs = [creature(s, "p2", n) for n in ("Wolf", "Boar", "Ox")]
    mana(s, U=1)
    cast(s, "Preordain")
    d = finish_scry(s)
    assert d is not None and d.max_choices == 2
    with pytest.raises(ActionError):
        pick(s, *[t.id for t in theirs])
    pick(s, theirs[0].id, theirs[1].id)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert [s.state.cards[t.id].tapped for t in theirs] == [True, True, False]
    check(s)


def test_the_wise_mothman_counts_the_nonland_cards_milled(cards):
    s = build(cards, ["The Wise Mothman", "Thought Scour", "Preordain", "Opt"])
    put(s, "The Wise Mothman")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub", "Elf")]
    top = [card_named(s, n) for n in ("Preordain", "Opt")]
    for c in top:  # (the top two cards of the library: both nonland)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    mana(s, U=1)
    cast(s, "Thought Scour")
    d = until_asked(s)
    assert d is not None and d.kind == "choose_cards" and d.max_choices == 2  # (X = 2 nonland cards milled this way)
    check(s)
    pick(s, mine[0].id, mine[2].id)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert [counters(s, m) for m in mine] == [1, 0, 1]
    check(s)


def test_the_wise_mothman_lands_are_not_counted(cards):
    s = build(cards, ["The Wise Mothman", "Thought Scour", "Preordain"])
    put(s, "The Wise Mothman")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub")]
    act(s, "p1", type="move", card_ids=[card_named(s, "Preordain").id], to={"zone": "library"}, position="top")
    mana(s, U=1)
    cast(s, "Thought Scour")  # (one nonland and one Forest milled)
    d = until_asked(s)
    assert d is not None and d.max_choices == 1
    check(s)
