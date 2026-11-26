"""-- playtest (nov 18) -- "Risen Reef's ability resolves weird": the trigger asked "You may choose the card you looked at (only a card
that qualifies can be chosen)" with only "Done (none)" and no card — the top card wasn't a land, so it wasn't an option, and the chooser
couldn't see what they had looked at. A look-and-choose with a filter now shows every card the chooser looked at (``display["cards"]``,
in library order) with why the others don't qualify; the options stay the cards that do (the server refuses any other), all of it in the
chooser's view alone; the one-card gate (top_library.private_gate) is worded from the card, and is still asked whatever the card is (701.20e).

Real Oracle text: Risen Reef, Augur of Bolas, Commune with Nature, Lead the Stampede, Oath of Nissa, Coiling Oracle, and Domri Rade's +1
line on a test sorcery.
"""

from __future__ import annotations

import json

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import top_library
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card("Risen Reef", set_code="tst", number="LK1", mana_cost="{1}{G}{U}", cmc=3.0, type_line="Creature — Elemental",
         oracle_text="Whenever this creature or another Elemental you control enters, look at the top card of your library. If it's a "
                     "land card, you may put it onto the battlefield tapped. If you don't put the card onto the battlefield, put it into "
                     "your hand.", power="1", toughness="1", colors=["G", "U"], color_identity=["G", "U"]),
    card("Augur of Bolas", set_code="tst", number="LK2", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Merfolk Wizard",
         oracle_text="When this creature enters, look at the top three cards of your library. You may reveal an instant or sorcery card "
                     "from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
         power="1", toughness="3", colors=["U"], color_identity=["U"]),
    card("Commune with Nature", set_code="tst", number="LK3", mana_cost="{G}", cmc=1.0, type_line="Sorcery",
         oracle_text="Look at the top five cards of your library. You may reveal a creature card from among them and put it into your "
                     "hand. Put the rest on the bottom of your library in any order.", colors=["G"], color_identity=["G"]),
    card("Lead the Stampede", set_code="tst", number="LK4", mana_cost="{2}{G}", cmc=3.0, type_line="Sorcery",
         oracle_text="Look at the top five cards of your library. You may reveal any number of creature cards from among them and put "
                     "the revealed cards into your hand. Put the rest on the bottom of your library in any order.",
         colors=["G"], color_identity=["G"]),
    card("Oath of Nissa", set_code="tst", number="LK5", mana_cost="{G}", cmc=1.0, type_line="Legendary Enchantment",
         oracle_text="When Oath of Nissa enters, look at the top three cards of your library. You may reveal a creature, land, or "
                     "planeswalker card from among them and put it into your hand. Put the rest on the bottom of your library in any "
                     "order.\nYou may spend mana as though it were mana of any color to cast planeswalker spells.",
         colors=["G"], color_identity=["G"]),
    card("Coiling Oracle", set_code="tst", number="LK6", mana_cost="{G}{U}", cmc=2.0, type_line="Creature — Snake Elf Druid",
         oracle_text="When this creature enters, reveal the top card of your library. If it's a land card, put it onto the battlefield. "
                     "Otherwise, put that card into your hand.", power="1", toughness="1", colors=["G", "U"], color_identity=["G", "U"]),
    card("Test Glimpse", set_code="tst", number="LK7", mana_cost="{G}", cmc=1.0, type_line="Sorcery",
         oracle_text="Look at the top card of your library. If it's a creature card, you may reveal it and put it into your hand.",
         colors=["G"], color_identity=["G"]),
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    base.update({c["name"]: c for c in EXTRA})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to(s, name, zone, position=None):
    c = named(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": zone}, **({"position": position} if position else {}))
    return s.state.cards[c.id]


def cast(s, name, **pay):
    c = to(s, name, "hand")
    mana(s, **pay)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def until_pick(s, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "pick_looked":
            return d
        assert d is None, f"unexpected decision: {d.prompt}"
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def settle(s, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        if d is not None:  # (the rest to the bottom: any order)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(d.min_choices, 0)]
                if d.kind != "order" else [o.id for o in d.options])
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def theirs(s, viewer):
    """What ``viewer``'s view says about the pending decision (and that it names no hidden card)."""
    return json.dumps(s.view(viewer).get("rules", {}).get("decision"))


# -- Risen Reef ---------------------------------------------------------------------------------------------------
def test_risen_reef_nonland_top_is_shown_and_goes_to_hand(cards):
    s = build(cards, "Risen Reef", "Grizzly Bears")
    bears = to(s, "Grizzly Bears", "library", "top")
    cast(s, "Risen Reef", G=1, U=1, C=1)
    d = until_pick(s)
    assert d.player == "p1" and d.kind == "choose_cards" and d.min_choices == 0 and d.max_choices == 0
    assert d.options == [] and d.display["cards"] == [bears.id]  # shown, not an answer
    assert d.prompt == "Risen Reef: you looked at Grizzly Bears (not a land card) — it goes into your hand."
    assert d.display == {"kind": "looked", "cards": [bears.id], "ineligible": "not a land card", "otherwise": "It goes into your hand"}
    mine = s.view("p1")["rules"]["decision"]
    assert mine["display"]["cards"] == [bears.id] and mine["display"]["kind"] == "looked"
    assert s.view("p1")["cards"][bears.id].get("name") == "Grizzly Bears"  # the chooser sees what they looked at
    for other in ("p2", "__spectator__"):
        seen = theirs(s, other)
        assert "Grizzly Bears" not in seen and bears.id not in seen and "looked" not in seen
        assert s.view(other)["cards"].get(bears.id, {}).get("name") in (None, "")
    with pytest.raises(ActionError):
        choose(s, [bears.id])  # the server refuses a card that doesn't qualify
    choose(s, [])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:hand"
    replay_matches(s)


@pytest.mark.parametrize("take", [True, False])
def test_risen_reef_land_top_asks_battlefield_tapped(cards, take):
    s = build(cards, "Risen Reef", "Island")
    island = to(s, "Island", "library", "top")
    cast(s, "Risen Reef", G=1, U=1, C=1)
    d = until_pick(s)
    assert d.min_choices == 0 and d.max_choices == 1
    assert [o.id for o in d.options] == [island.id]
    assert d.prompt == "Risen Reef: you looked at Island. It's a land card — put it onto the battlefield tapped?"
    assert d.display == {"kind": "looked", "cards": [island.id], "ineligible": "not a land card", "take": "Put it onto the battlefield tapped",
                         "otherwise": "It goes into your hand"}
    assert "Island" not in theirs(s, "p2")
    choose(s, [island.id] if take else [])
    settle(s)
    c = s.state.cards[island.id]
    assert (c.zone, c.tapped) == (("p1:battlefield", True) if take else ("p1:hand", False))
    replay_matches(s)


@pytest.mark.parametrize("top, takes", [("Llanowar Elves", True), ("Forest", False)])
def test_domri_line_asks_either_way(cards, top, takes):
    s = build(cards, "Test Glimpse", "Llanowar Elves")
    c = to(s, top, "library", "top")
    cast(s, "Test Glimpse", G=1)
    d = until_pick(s)
    assert [o.id for o in d.options] == ([c.id] if takes else []) and d.display["cards"] == [c.id]
    if takes:
        assert d.prompt == "Test Glimpse: you looked at Llanowar Elves. It's a creature card — reveal it and put it into your hand?"
        assert d.display["take"] == "Reveal it and put it into your hand"
    else:
        assert d.prompt == "Test Glimpse: you looked at Forest (not a creature card) — it stays on top of your library."
        assert "take" not in d.display
    p2_before = theirs(s, "p2")
    assert "Forest" not in p2_before and "Llanowar" not in p2_before
    choose(s, [c.id] if takes else [])
    settle(s)
    assert s.state.cards[c.id].zone == ("p1:hand" if takes else "p1:library")
    log = json.dumps(s.view("p2")["log"])
    assert ("Llanowar Elves" in log) == takes and "Forest" not in log


# -- top N with a filter: every card looked at, in library order ------------------------------------------------------
@pytest.mark.parametrize("spell, pay, n, good, bad, why", [
    ("Augur of Bolas", {"U": 1, "C": 1}, 3, "Lightning Bolt", "Grizzly Bears", "not an instant or sorcery card"),
    ("Commune with Nature", {"G": 1}, 5, "Grizzly Bears", "Lightning Bolt", "not a creature card"),
    ("Lead the Stampede", {"G": 1, "C": 2}, 5, "Grizzly Bears", "Lightning Bolt", "not a creature card"),
    ("Oath of Nissa", {"G": 1}, 3, "Grizzly Bears", "Lightning Bolt", "not a creature, land, or planeswalker card"),
])
def test_top_n_shows_every_card_looked_at(cards, spell, pay, n, good, bad, why):
    s = build(cards, spell, "Lightning Bolt", "Grizzly Bears")
    bad_card = to(s, bad, "library", "top")
    good_card = to(s, good, "library", "top")
    cast(s, spell, **pay)
    d = until_pick(s)
    top = s.state.zones["p1:library"][:n]
    assert d.display["cards"] == top  # every card looked at, in library order
    eligible = [o.id for o in d.options]
    assert good_card.id in eligible and bad_card.id not in eligible
    assert d.display["kind"] == "looked" and d.display["ineligible"] in (why, "doesn't qualify")
    with pytest.raises(ActionError):
        choose(s, [bad_card.id])
    seen = theirs(s, "p2")
    assert good not in seen and bad not in seen
    choose(s, [good_card.id])
    settle(s)
    assert s.state.cards[good_card.id].zone == "p1:hand" and s.state.cards[bad_card.id].zone == "p1:library"


def test_coiling_oracle_reveal_needs_no_choice(cards):
    s = build(cards, "Coiling Oracle", "Grizzly Bears")
    bears = to(s, "Grizzly Bears", "library", "top")
    cast(s, "Coiling Oracle", G=1, U=1)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:hand"


def test_wording_helpers():
    from app.rules import selectors

    land = selectors.Selector(card=True, types=("Land",), zones=()).key()
    assert top_library.describe(land) == "a land card"
    assert top_library.describe(selectors.Selector(card=True, types=("Sorcery", "Instant"), zones=()).key()) == "an instant or sorcery card"
    assert top_library.describe(selectors.Selector(card=True, types=("Creature",), extras=("chosen_type",), zones=()).key()) \
        == "a creature card of the chosen type"
    assert top_library.describe(selectors.Selector(card=True, types=("Creature",), compare=(("mv", "<=", 3),), zones=()).key()) is None
