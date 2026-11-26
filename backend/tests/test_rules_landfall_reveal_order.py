"""A landfall deck at full automation (Nissa, Resurgent Animist; Scute Swarm; Avenger of Zendikar), real Oracle text (Scryfall).

701.20a: "reveal cards from the top of your library until you reveal an Elf or Elemental card" turns them face up for every player — the
log line names them (and the card found) to the opponent, the table's reveal notice reads it (``reveal`` on the entry) — and then the rest go
to the bottom in a random order nobody can read. "If this is the second time this ability has resolved this turn": only the second.
603.3b: the trigger order prompt words each ability (its printed text, not the engine's primitives), groups identical ones, never asks
when all of them are identical, and remembers an order ("always use this order for these cards") for the rest of the game.
Each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.views import build_view
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put

NISSA = ("Landfall — Whenever a land you control enters, add one mana of any color. Then if this is the second time this ability has "
         "resolved this turn, reveal cards from the top of your library until you reveal an Elf or Elemental card. Put that card into your "
         "hand and the rest on the bottom of your library in a random order.")
SCUTE = ("Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, "
         "create a token that's a copy of this creature instead.")
EXTRA = [
    real("Nissa, Resurgent Animist", "{2}{G}", 3, "Legendary Creature — Elf Scout", NISSA, ("3", "3"), "G"),
    real("Scute Swarm", "{2}{G}", 3, "Creature — Insect", SCUTE, ("1", "1"), "G"),
    real("Avenger of Zendikar", "{5}{G}{G}", 7, "Creature — Elemental", "When this creature enters, create a 0/1 green Plant creature token "
         "for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.",
         ("5", "5"), "G"),
    real("Explore", "{1}{G}", 2, "Sorcery", "You may play an additional land this turn.\nDraw a card.", None, "G"),
    real("Llanowar Elves", "{G}", 1, "Creature — Elf Druid", "{T}: Add {G}.", ("1", "1"), "G"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
    real("Sylvan Messenger", "{3}{G}", 4, "Creature — Elf", "Trample (This creature can deal excess combat damage to the player or "
         "planeswalker it's attacking.)\nWhen this creature enters, reveal the top four cards of your library. Put all Elf cards revealed this "
         "way into your hand and the rest on the bottom of your library in any order.", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def library(s, pid="p1"):
    return s.state.zones[f"{pid}:library"]


def play_land(s):
    """Alice plays a Forest from deep in her library (the top stays as it was)."""
    forest = next(c for c in reversed(library(s)) if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest)


def another_land_drop(s):
    """Explore: one more land this turn (it draws the top card)."""
    act(s, "p1", type="move", card_ids=[card_named(s, "Explore").id], to={"zone": "hand"})
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Explore").id)
    settle(s)


def p2_log(s, since):
    return build_view(s.state, "p2")["log"][since:]


def names(part):
    return [g["card"]["name"] for g in part.get("group") or [] if "card" in g]


def test_nissa_reveals_publicly_only_on_the_second_resolution(cards):
    # library, top first: Explore draws Sol Ring; the reveal turns over Lightning Bolt, Island and finds Llanowar Elves
    s = build(cards, ["Nissa, Resurgent Animist", "Explore", "Sol Ring", "Lightning Bolt", "Island", "Llanowar Elves"])
    put(s, "Nissa, Resurgent Animist")
    seen = len(s.state.log)
    play_land(s)
    settle(s)
    first = p2_log(s, seen)
    assert not any(e.get("reveal") for e in first), "the first resolution reveals nothing"
    assert card_named(s, "Llanowar Elves").zone == "p1:library"

    another_land_drop(s)
    assert card_named(s, "Sol Ring").zone == "p1:hand"
    seen = len(s.state.log)
    play_land(s)
    settle(s)
    entries = p2_log(s, seen)
    shown = [e for e in entries if e.get("reveal")]
    assert len(shown) == 1, entries
    e = shown[0]
    assert e["reveal"] == {"player": "p1", "source": "Nissa, Resurgent Animist", "until": True, "found": True}
    groups = [p for p in e["parts"] if "group" in p]
    assert names(groups[0]) == ["Lightning Bolt", "Island", "Llanowar Elves"]  # the opponent sees every revealed card, in the order turned over
    assert groups[0].get("hidden", 0) == 0
    assert any(p.get("card", {}).get("name") == "Llanowar Elves" for p in e["parts"]), "the card found is announced"
    assert card_named(s, "Llanowar Elves").zone == "p1:hand"
    lib = library(s)
    assert set(lib[-2:]) == {card_named(s, "Lightning Bolt").id, card_named(s, "Island").id}  # the rest: the bottom
    # nothing about the library leaks afterwards: no card stays revealed, the opponent knows no library card nor its place
    assert not any(s.state.cards[c].revealed_to for c in lib)
    view = build_view(s.state, "p2")
    assert view["zones"]["p1:library"]["known"] == []
    assert not any(c in view["cards"] for c in lib)
    moved = [p for e in entries for p in e["parts"] if "group" in p and "Island" in names(p) and e is not shown[0]]
    for p in moved:  # the move to the bottom lists them by name, not in the random order they went in (401.4)
        assert names(p) == sorted(names(p))
    check(s)


def test_reveal_the_top_four_is_public_too(cards):
    """The same path for "reveal the top N cards" (Sylvan Messenger, Goblin Ringleader): the opponent sees them, then the Elves go to hand."""
    s = build(cards, ["Sylvan Messenger", "Llanowar Elves", "Island", "Lightning Bolt", "Explore"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Sylvan Messenger").id], to={"zone": "hand"})
    mana(s, G=4)
    seen = len(s.state.log)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sylvan Messenger").id)
    settle(s)
    shown = [e for e in p2_log(s, seen) if e.get("reveal")]
    assert len(shown) == 1 and shown[0]["reveal"] == {"player": "p1", "source": "Sylvan Messenger", "until": False, "found": False}
    assert names(next(p for p in shown[0]["parts"] if "group" in p)) == ["Llanowar Elves", "Island", "Lightning Bolt", "Explore"]
    assert card_named(s, "Llanowar Elves").zone == "p1:hand"
    assert not any(s.state.cards[c].revealed_to for c in library(s))
    check(s)


def test_identical_triggers_go_on_the_stack_without_asking(cards):
    s = build(cards, ["Scute Swarm"])
    put(s, "Scute Swarm")
    act(s, "p1", type="create_token", player="p1",
        token={"name": "Scute Swarm", "type_line": "Token Creature — Insect", "power": "1", "toughness": "1", "text": SCUTE, "colors": ["G"]})
    play_land(s)
    d = s.state.rules.decision
    assert d is None or d.kind != "order"
    settle(s)
    insects = [c for c in s.state.cards.values() if c.name == "Insect" and c.zone == "p1:battlefield"]
    assert len(insects) == 2
    check(s)


def _landfall_table(cards):
    s = build(cards, ["Nissa, Resurgent Animist", "Scute Swarm", "Avenger of Zendikar", "Explore", "Llanowar Elves"])
    for name in ("Nissa, Resurgent Animist", "Scute Swarm", "Avenger of Zendikar"):
        put(s, name)
    act(s, "p1", type="create_token", player="p1",
        token={"name": "Scute Swarm", "type_line": "Token Creature — Insect", "power": "1", "toughness": "1", "text": SCUTE, "colors": ["G"]})
    return s


def test_mixed_triggers_ask_with_grouped_readable_options(cards):
    s = _landfall_table(cards)
    play_land(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == "order"
    assert len(d.options) == 4 and d.min_choices == d.max_choices == 4  # one option per trigger: the answer lists them all
    rows = d.display["triggers"]
    assert [(r["name"], r["count"]) for r in rows] == [("Nissa, Resurgent Animist", 1), ("Scute Swarm", 2), ("Avenger of Zendikar", 1)]
    by_name = {r["name"]: r for r in rows}
    assert by_name["Scute Swarm"]["short"].startswith("Landfall: create a 1/1 green Insect creature token")
    assert by_name["Nissa, Resurgent Animist"]["text"] == NISSA
    assert by_name["Nissa, Resurgent Animist"]["source"] == card_named(s, "Nissa, Resurgent Animist").id
    assert d.display["rememberable"] is True
    for o in d.options:  # the printed words, never the engine's primitives
        assert " — Landfall: " in o.label
        assert not any(w in o.label for w in ("token_copy", "Add_mana", "look_top", "pick_looked", "rest_looked", "token(s)", "counter(s)"))
    # the opponent sees only that Alice is choosing
    from app.rules.view import decision_view

    other = decision_view(s.state, d, "p2")
    assert "options" not in other and "display" not in other
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])  # "Auto order": as they triggered
    settle(s)
    check(s)


def test_a_remembered_order_is_used_the_next_time(cards):
    s = _landfall_table(cards)
    play_land(s)
    d = s.state.rules.decision
    rows = {r["name"]: r["ids"] for r in d.display["triggers"]}
    # Avenger first (resolves last), then both Scute Swarms, Nissa last (resolves first)
    order = [*rows["Avenger of Zendikar"], *rows["Scute Swarm"], *rows["Nissa, Resurgent Animist"]]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=order, remember="always_order")
    saved = s.state.rules.prefs_for("p1").trigger_orders
    assert saved == [["Avenger of Zendikar:1", "Scute Swarm:0", "Nissa, Resurgent Animist:0"]]
    settle(s)

    another_land_drop(s)
    seen = len(s.state.log)
    play_land(s)
    d = s.state.rules.decision
    assert d is None or d.kind != "order", "the saved order is used without asking"
    stack = [s.state.cards[c] for c in s.state.zones.get("stack", [])]
    names_on_stack = [c.name for c in stack]
    assert names_on_stack[0].startswith("Avenger") and names_on_stack[-1].startswith("Nissa"), names_on_stack
    assert any("saved order" in "".join(p.get("t") or "" for p in e["parts"]) for e in p2_log(s, seen))  # a public notice of it
    settle(s)
    check(s)

    act(s, "p1", type="set_prefs", forget_trigger_orders=True)
    assert s.state.rules.prefs_for("p1").trigger_orders == []
    check(s)


def test_remembering_needs_a_trigger_order(cards):
    from app.game.errors import ActionError

    s = _landfall_table(cards)
    play_land(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    while (d := s.state.rules.decision) is not None and d.kind == "order":
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    if d is not None:  # (a mana color, a "you may"): not an order, so it can't be remembered as one
        with pytest.raises(ActionError):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id], remember="always_order")
