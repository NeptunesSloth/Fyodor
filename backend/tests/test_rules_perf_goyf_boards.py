"""Big boards (gaps5): Disa the Restless with a board of Lhurgoyfs. A Lhurgoyf's power and toughness count cards in graveyards
(613.4a: a characteristic-defining ability, layer 7a), and every Lhurgoyf on the board counts the same cards: the count is read once
per table state for all of them (``layers._cda``), and a card in a graveyard no longer derives the whole battlefield to learn it gets
no foretell (``dynamic_zone_keyword_costs56``). The answers stay exactly as before: the counts follow every card that enters or
leaves a graveyard in a kept read pass, a count of "your graveyard" stays each player's own, and different wordings never share one.
The guards count calls, so they are not timing-flaky."""

from __future__ import annotations

import pytest

from app.rules import characteristics as chars
from app.rules import layers, scripts, values
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_pod_disa import EXTRA as DISA
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, put

GOYFS = [
    real("Tarmogoyf", "{1}{G}", 2, "Creature — Lhurgoyf",
         "Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number "
         "plus 1.", ("*", "1+*"), "G"),
    real("Lhurgoyf", "{2}{G}{G}", 4, "Creature — Lhurgoyf",
         "Lhurgoyf's power is equal to the number of creature cards in all graveyards and its toughness is equal to that number plus 1.",
         ("*", "1+*"), "G"),
    real("Nethergoyf", "{B}", 1, "Creature — Lhurgoyf",
         "Nethergoyf's power is equal to the number of card types among cards in your graveyard and its toughness is equal to that "
         "number plus 1.\nEscape—{2}{B}, Exile any number of other cards from your graveyard with four or more card types among them.",
         ("*", "1+*"), "B"),
]
MINE = ["Disa the Restless", "Maskwood Nexus", "Tarmogoyf", "Lhurgoyf", "Nethergoyf", "Sol Ring", "Lightning Bolt", "Rampant Growth",
        "Llanowar Elves", "Wrath of God", "Conspiracy", "Grizzly Bears"]
THEIRS = ["Nethergoyf", "Counterspell", "Day of Judgment"]
TOKENS = 12


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *DISA, *GOYFS], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def board(cards):
    """Disa, Maskwood Nexus, a Tarmogoyf, a Lhurgoyf, each player's Nethergoyf and twelve Tarmogoyf tokens; in the graveyards an
    artifact, an instant and a sorcery (Alice's) and an instant (Bob's)."""
    s = build(cards, MINE, THEIRS)
    for name in ("Disa the Restless", "Maskwood Nexus", "Tarmogoyf", "Lhurgoyf", "Nethergoyf"):
        put(s, name)
    put(s, "Nethergoyf", "p2")
    cost, colors, p, t, type_line, text = scripts.NAMED_TOKENS["Tarmogoyf"]
    act(s, "p1", type="create_token", player="p1", count=TOKENS, stacked=False,
        token={"name": "Tarmogoyf", "power": p, "toughness": t, "colors": colors, "type_line": type_line, "text": text, "mana_cost": cost})
    for name in ("Sol Ring", "Lightning Bolt", "Rampant Growth"):
        to_graveyard(s, name)
    to_graveyard(s, "Counterspell", "p2")
    return s


def goyfs(plan):
    return [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and "goyf" in c.name]


def pts(plan):
    """Every Lhurgoyf's power and toughness, by name and controller (one read pass), checked against a derivation outside any pass."""
    with plan.reading():
        kept = {c.id: (c.name, c.controller, *plan.ch(c).pt) for c in goyfs(plan)}
    layers._CDA_CACHE.clear()
    assert {c.id: (c.name, c.controller, *plan.ch(c).pt) for c in goyfs(plan)} == kept  # (no pass, nothing kept: read afresh)
    return sorted(set(kept.values()))


def test_the_counts_follow_the_graveyards_in_a_kept_pass(cards):
    s = board(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    # all graveyards: artifact, instant, sorcery (3 types; no creature card); Alice's: 3 types, Bob's: 1
    assert pts(plan) == [("Lhurgoyf", "p1", 0, 1), ("Nethergoyf", "p1", 3, 4), ("Nethergoyf", "p2", 1, 2), ("Tarmogoyf", "p1", 3, 4)]
    elves = card_named(s, "Llanowar Elves")
    plan.do({"type": "move", "card_ids": [elves.id], "to": {"player": "p1", "zone": "graveyard"}})  # a creature card enters Alice's graveyard
    assert pts(plan) == [("Lhurgoyf", "p1", 1, 2), ("Nethergoyf", "p1", 4, 5), ("Nethergoyf", "p2", 1, 2), ("Tarmogoyf", "p1", 4, 5)]
    judgment = card_named(s, "Day of Judgment", "p2")
    plan.do({"type": "move", "card_ids": [judgment.id], "to": {"player": "p2", "zone": "graveyard"}})  # a sorcery: no new type for all
    assert pts(plan) == [("Lhurgoyf", "p1", 1, 2), ("Nethergoyf", "p1", 4, 5), ("Nethergoyf", "p2", 2, 3), ("Tarmogoyf", "p1", 4, 5)]
    ring = card_named(s, "Sol Ring")
    plan.do({"type": "move", "card_ids": [ring.id], "to": {"player": "p1", "zone": "hand"}})  # the only artifact card leaves
    assert pts(plan) == [("Lhurgoyf", "p1", 1, 2), ("Nethergoyf", "p1", 3, 4), ("Nethergoyf", "p2", 2, 3), ("Tarmogoyf", "p1", 3, 4)]
    plan.do({"type": "set_controller", "card_ids": [card_named(s, "Nethergoyf").id], "player": "p2"})  # "your graveyard": Bob's now
    assert pts(plan) == [("Lhurgoyf", "p1", 1, 2), ("Nethergoyf", "p2", 2, 3), ("Tarmogoyf", "p1", 3, 4)]


def test_a_graveyard_change_between_two_goyfs_is_counted(cards):
    """Mid-action: the count the goyfs share is kept with what the table holds, so the next goyf read after a card enters (or leaves)
    a graveyard counts it, outside a read pass and inside one that a table action ran in (as ``read_pass.card_fact`` is guarded)."""
    s = board(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    a, b, c, d = [x for x in goyfs(plan) if x.is_token][:4]
    elves, ring = card_named(s, "Llanowar Elves"), card_named(s, "Sol Ring")
    assert plan.ch(a).pt == (3, 4)
    plan.do({"type": "move", "card_ids": [elves.id], "to": {"player": "p1", "zone": "graveyard"}})
    assert plan.ch(b).pt == (4, 5) and plan.ch(a).pt == (4, 5)

    def cda(card):  # type: ignore[no-untyped-def]
        return layers._cda(plan.state, card, chars.of(card, plan.info), plan.info)  # (layer 7a itself: a pass keeps derived goyfs whole)

    with plan.reading():
        assert cda(c) == (4, 5)
        plan.do({"type": "move", "card_ids": [ring.id], "to": {"player": "p1", "zone": "hand"}})
        assert cda(d) == (3, 4) and cda(c) == (3, 4)
        plan.do({"type": "move", "card_ids": [ring.id], "to": {"player": "p2", "zone": "graveyard"}})  # (into another graveyard)
        assert cda(d) == (4, 5)


def test_one_read_pass_counts_the_graveyards_once_for_every_goyf(cards, monkeypatch):
    s = board(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    calls: list[str] = []
    real_distinct = values._distinct

    def distinct(*args, **kw):  # type: ignore[no-untyped-def]
        calls.append("distinct")
        return real_distinct(*args, **kw)

    monkeypatch.setattr(values, "_distinct", distinct)
    layers._CDA_CACHE.clear()
    with plan.reading():
        assert {plan.ch(c).pt for c in goyfs(plan) if c.name != "Lhurgoyf"} == {(3, 4), (1, 2)}  # (Bob's Nethergoyf: 1 type)
    # 13 Tarmogoyfs (two counts each: power, then toughness = that count plus 1) and two Nethergoyfs read 30 counts before: now one
    # for "all graveyards" and one for each player's own graveyard (the Lhurgoyf's "creature cards" is a count, not this one)
    assert len(calls) == 3, calls


def test_a_land_drop_on_a_goyf_board_derives_graveyard_cards_a_bounded_number_of_times(cards, monkeypatch):
    s = board(cards)
    for name in ("Wrath of God", "Conspiracy", "Grizzly Bears"):  # (seven cards in graveyards)
        to_graveyard(s, name)
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    graveyard = {cid for z in ("p1:graveyard", "p2:graveyard") for cid in s.state.zones[z]}
    calls = [0]
    real = layers._derive

    def counted(state, card, *args, **kw):  # type: ignore[no-untyped-def]
        calls[0] += card.id in graveyard
        return real(state, card, *args, **kw)

    monkeypatch.setattr(layers, "_derive", counted)
    layers._CDA_CACHE.clear()
    act(s, "p1", type="play_land", card_id=forest.id)
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    # each wording's count derives the graveyard cards once per table state: 57 derivations of each graveyard card here (1025 before,
    # when every goyf derived them twice, power then toughness, and each graveyard card derived the whole battlefield again, every
    # goyf's count among it); a regression to that shows here
    assert calls[0] / len(graveyard) < 100, calls[0]
    check(s)


def test_the_goyf_board_plays_out_and_replays(cards):
    s = board(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    tarmo = card_named(s, "Tarmogoyf")
    assert plan.ch(tarmo).pt == (3, 4)
    check(s)
