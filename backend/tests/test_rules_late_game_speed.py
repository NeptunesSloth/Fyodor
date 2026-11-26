"""-- late-game speed -- A late Commander board (a full hand, a wide battlefield) made every view slow: each card in a hand derived the
whole battlefield again to find the table's static abilities (Dream Devourer's foretell, zone grants), each permanent's mana abilities
were read again for every castable check, every derivation in a view read every card in the game for what is attached to it, and each
red or black source of combat damage derived the battlefield again for Ghostly Flame. The answers are the same as before; counts, not
timings, guard the speed."""

from __future__ import annotations

import pytest

from app.rules import characteristics as chars
from app.rules import layers, permissions, read_pass
from app.rules.view import rules_view
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import build

HAND = ["Lightning Bolt", "Counterspell", "Opt", "Murder", "Giant Growth", "Swords to Plowshares", "Grizzly Bears", "Mulldrifter",
        "Day of Judgment", "Rampant Growth", "Treasure Cruise", "Staggershock", "Firebolt", "Kitchen Finks", "Mana Leak", "Capsize"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def late_board(cards):
    """Alice: the spells above in hand, ten Forests, ten Mountains, Elves, Bears, Master of Etherium, Sol Rings and a pile of tokens."""
    s = build(cards, [*[(1, n) for n in HAND], (10, "Forest"), (10, "Mountain"), (2, "Llanowar Elves"), (1, "Master of Etherium"),
                      (2, "Sol Ring"), (1, "Monastery Swiftspear")])
    mine = lambda name: [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == name]  # noqa: E731
    act(s, "p1", type="move", card_ids=[cid for n in HAND for cid in mine(n)][:len(HAND)], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[*mine("Forest"), *mine("Mountain"), *mine("Llanowar Elves"), *mine("Master of Etherium"),
                                        *mine("Sol Ring"), *mine("Monastery Swiftspear")], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="create_token", player="p1", count=12, stacked=False,
        token={"name": "Elemental", "type_line": "Token Creature — Elemental", "power": "5", "toughness": "5", "colors": ["R", "G"]})
    return s


def counted(monkeypatch, module, name):
    calls = [0]
    real = getattr(module, name)

    def wrapper(*a, **kw):  # type: ignore[no-untyped-def]
        calls[0] += 1
        return real(*a, **kw)

    monkeypatch.setattr(module, name, wrapper)
    return calls


# -- the table's statics, read once per view ----------------------------------------------------------------------------------
def test_a_view_reads_the_tables_statics_once_however_many_cards_are_in_hand(cards, monkeypatch):
    s = late_board(cards)
    hand = [c for c in s.state.zones["p1:hand"] if "Land" not in chars.of(s.state.cards[c], cards).types]
    assert len(hand) >= 12
    calls = counted(monkeypatch, permissions, "_all_table_statics")
    view = rules_view(s.state, "p1", cards)
    assert view is not None and view["hints"]["castable"]
    # (each nonland card in hand derived it again: once per card, ~15 times a view)
    assert calls[0] <= 2, calls[0]


def test_the_views_are_the_same_as_when_nothing_was_kept_part_way(cards, monkeypatch):
    s = late_board(cards)
    act(s, "p1", type="pass_priority")  # (Bob's views too, and a view after a change)
    now = {pid: rules_view(s.state, pid, cards) for pid in ("p1", "p2")}
    monkeypatch.setattr(layers, "quiet", lambda state, info: False)  # (the old reading: nothing kept while a derivation is part-way)
    monkeypatch.setattr(read_pass, "once_viewing", lambda state, info, key, compute: compute())  # (nor a view's mana abilities)
    monkeypatch.setattr(read_pass, "card_fact", lambda state, key, compute: None)  # (nor its card facts)
    before = {pid: rules_view(s.state, pid, cards) for pid in ("p1", "p2")}
    assert now == before


@pytest.mark.parametrize(("name", "value"), [("depth", 1), ("solving", [[]]), ("l4", {"x"}), ("cda", {"x"}), ("pt", {"x": None}),
                                             ("rules_off", 1), ("judging", [((), (0, 0, 0))]), ("probe", object()),
                                             ("grant_capture45", object()), ("borrow_capture", {})])
def test_only_the_top_level_of_a_whole_derivation_of_this_table_is_quiet(cards, monkeypatch, name, value):
    s = late_board(cards)
    with read_pass.scope(s.state, cards) as sc:
        monkeypatch.setattr(layers._T, "memo", [s.state, cards, None])
        assert not layers.settled() and layers.quiet(s.state, cards)
        assert read_pass.once(s.state, cards, "k", lambda: 1) == 1
        assert read_pass.once(s.state, cards, "k", lambda: 2) == 1 and sc.once["k"] == 1  # (quiet: kept and served)
        assert not layers.quiet(s.state, object()) and not layers.quiet(s.state.model_copy(), cards)  # (another table or card info)
        monkeypatch.setattr(layers._T, name, value)  # something else part-way: asked afresh, not kept
        assert not layers.quiet(s.state, cards)
        assert read_pass.once(s.state, cards, "k", lambda: 3) == 3
        assert read_pass.once(s.state, cards, "j", lambda: 4) == 4 and "j" not in sc.once
        monkeypatch.undo()
    assert layers.settled()


# -- card facts and mana abilities in a view's pass ---------------------------------------------------------------------------
def test_a_views_pass_keeps_card_facts_and_mana_abilities_but_a_plans_pass_reads_mana_abilities_again(cards):
    from app.rules.casting import mana_abilities
    from app.rules.plan import Plan

    s = late_board(cards)
    state = s.state
    elf = next(c for c in state.cards.values() if c.name == "Llanowar Elves" and c.zone == "p1:battlefield")
    asked = []
    assert read_pass.card_fact(state, "f", lambda: asked.append(1) or 1) is None  # (no pass: the caller reads the cards itself)
    with read_pass.scope(state, cards):
        assert read_pass.card_fact(state, "f", lambda: asked.append(1) or 1) == 1
        assert read_pass.card_fact(state, "f", lambda: asked.append(2) or 2) == 1
        first = mana_abilities(state, elf, cards)
        assert first and mana_abilities(state, elf, cards) is first  # (kept: the same list)
        probe = elf.model_copy(update={"tapped": True})  # (a probe's copy of the card: read afresh)
        assert mana_abilities(state, probe, cards) is not first
    assert asked == [1]
    assert mana_abilities(state, elf, cards) == first and mana_abilities(state, elf, cards) is not first  # (outside the pass)
    plan = Plan(state, "p1", cards, None)
    mine = plan.state.cards[elf.id]
    with plan.reading():
        assert mana_abilities(plan.state, mine, cards) is not mana_abilities(plan.state, mine, cards)  # (a Plan's pass: read again)


# -- Ghostly Flame's look at the battlefield ----------------------------------------------------------------------------------
def test_each_damage_source_does_not_derive_the_battlefield_again(cards, monkeypatch):
    from app.rules import wave110f_cards
    from app.rules.plan import Plan

    s = late_board(cards)
    plan = Plan(s.state, "p1", cards, None)
    red = [plan.ch(c) for c in plan.state.cards.values() if c.name == "Elemental"]
    board = len(plan.state.zones["p1:battlefield"]) + len(plan.state.zones["p2:battlefield"])
    calls = counted(monkeypatch, layers, "_derive")
    assert wave110f_cards.damage_colors(plan, red[0]) is red[0]  # (no Ghostly Flame: as it is)
    first = calls[0]
    assert board <= first <= 4 * board
    assert all(wave110f_cards.damage_colors(plan, ch) is ch for ch in red[1:])
    assert calls[0] == first  # (each of the other 11 sources derived the whole battlefield again: 12 × as many)
