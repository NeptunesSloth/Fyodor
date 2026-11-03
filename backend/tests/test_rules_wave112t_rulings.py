"""Wave 112T: the Star Trek cards wave 111 refused for want of a ruling, now settled by the Star Trek release notes
(https://magic.wizards.com/en/news/feature/star-trek-release-notes). CR 2026-09-25. Real Oracle text (Scryfall, 2026-10-30); every scenario
checks the replay and a save and a load.

* All Good Things...: "check whatever cards are exiled with this Saga …, even if that's fewer than three cards … You'll gain 10 life if there's
  only one exiled card, as it will share a card type with itself. If there are no exiled cards, you will also gain 10 life."
* Commander Spock: "If the revealed card has {X} in its mana cost, X is 0 for the purpose of determining its mana value." / "You cast the card
  while Commander Spock's ability is resolving … Timing restrictions based on its types are ignored." "Still on top of your library": the
  revealed card, unmoved (400.7).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put

EXTRA = [
    real('All Good Things...', '{3}{G}{U}', 5, 'Enchantment — Saga',
         '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Draw two cards, then exile a card from your hand.\nIV — If all cards exiled with this Saga share a card type, you gain 10 life.', None, 'UG'),
    real('Commander Spock', '{2}{G}{W}{U}', 5, 'Legendary Creature — Vulcan Human Scientist',
         "Strange new worlds — Whenever Commander Spock enters or attacks, reveal the top card of your library. You may cast that card without paying its mana cost if that spell's mana value is equal to or less than the number of differently named lands you control. If it's a land card, you may put it onto the battlefield tapped. If that card is still on top of your library, draw a card.", ("3", "5"), 'WUG'),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Test Proliferate 111E", "{U}", 1, "Instant", "Proliferate.", None, "U"),
    real("Test X Spell 112T", "{X}{R}", 1, "Sorcery", "Test X Spell 112T deals X damage to any target.", None, "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            if any(i not in {o.id for o in d.options} for i in ids):
                raise AssertionError(f"{d.prompt}: {[(o.id, o.label) for o in d.options]}")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def zone(s, c):
    return s.state.cards[c.id].zone


def to(s, c, z, pid=None, **kw):
    act(s, pid or c.owner, type="move", card_ids=[c.id], to={"player": pid or c.owner, "zone": z}, **kw)


def chapter(s, saga, n, *picks):
    """Chapter ``n`` of ``saga``: n - 1 lore counters by hand, then a real proliferate adds the n-th (714.2b)."""
    have = s.state.cards[saga.id].counters.get("lore", 0)
    if n - 1 > have:
        act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=n - 1 - have)
    mana(s, U=1)
    c = card_named(s, "Test Proliferate 111E")
    to(s, c, "hand")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, [saga.id], *picks)
    if zone(s, c) != "p1:library":
        to(s, c, "library", position="top")  # (the same proliferate again next time)


# -- All Good Things... ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("exiled, gain", [((), True), (("Forest",), True), (("Forest", "Forest", "Forest"), True),
                                          (("Forest", "Lightning Bolt", "Forest"), False), (("Lightning Bolt", "Opt"), True)])
def test_all_good_things_gains_10_if_all_exiled_cards_share_a_card_type(cards, exiled, gain):
    s = build(cards, ["All Good Things...", "Test Proliferate 111E", "Lightning Bolt", "Opt"])
    saga = card_named(s, "All Good Things...")
    if not exiled:
        to(s, saga, "battlefield")  # (no chapter has resolved: nothing is exiled with it)
    for i, name in enumerate(exiled, start=1):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone in ("p1:library", "p1:hand"))
        to(s, c, "hand")
        drawn = s.state.rules.turn_log.drew.get("p1", 0)
        if i == 1:  # chapter I as it enters (714.3a): cast it
            to(s, saga, "hand")
            mana(s, G=1, U=1, C=3)
            act(s, "p1", type="cast_spell", card_id=saga.id)
            answer(s, c.id)
        else:
            chapter(s, saga, i, c.id)  # draw two, then exile this card from the hand
        assert zone(s, c) == "p1:exile" and s.state.rules.turn_log.drew.get("p1", 0) == drawn + 2  # drew two, then exiled the chosen card
    before = life(s)
    chapter(s, saga, 4)
    assert life(s) == before + (10 if gain else 0)
    check(s)


# -- Commander Spock ----------------------------------------------------------------------------------------------------------------------
def spock(s, top):
    """Commander Spock enters with ``top`` on top of Alice's library (one land, a Forest, on the battlefield: one land name)."""
    put(s, "Forest")
    to(s, card_named(s, top), "library", position="top")
    sp = card_named(s, "Commander Spock")
    to(s, sp, "hand")
    mana(s, G=1, W=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sp.id)
    return card_named(s, top)


@pytest.mark.parametrize("cast", [True, False])
def test_spock_casts_the_revealed_card_or_draws_it(cards, cast):
    s = build(cards, ["Commander Spock", "Lightning Bolt"])
    bolt = spock(s, "Lightning Bolt")  # mana value 1 <= one differently named land
    answer(s, bolt.id if cast else [], "p2")
    if cast:
        assert life(s, "p2") == 37 and zone(s, bolt) == "p1:graveyard"  # cast: no longer on top, no draw
        assert s.state.zones["p1:library"][0] != bolt.id
    else:
        assert zone(s, bolt) == "p1:hand" and life(s, "p2") == 40  # still on top: drawn
    check(s)


def test_spock_too_expensive_is_drawn_and_x_counts_as_zero(cards):
    s = build(cards, ["Commander Spock", "Grizzly Bears", "Test X Spell 112T"])
    bears = spock(s, "Grizzly Bears")  # mana value 2 > 1: can't be cast this way
    answer(s)
    assert zone(s, bears) == "p1:hand"
    x = card_named(s, "Test X Spell 112T")
    to(s, x, "library", position="top")
    turn = s.state.turn.number
    s2 = s
    act(s2, "p1", type="move", card_ids=[card_named(s, "Commander Spock").id], to={"player": "p1", "zone": "hand"})
    mana(s, G=1, W=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Commander Spock").id)
    answer(s, x.id, "p2")  # {X}{R}: mana value 1 with X = 0 (the ruling); cast for X = 0
    assert zone(s, x) == "p1:graveyard" and life(s, "p2") == 40 and s.state.turn.number == turn
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_spock_puts_a_revealed_land_onto_the_battlefield_tapped(cards, take):
    s = build(cards, ["Commander Spock", "Island"] if False else ["Commander Spock"])
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    put(s, "Forest")
    to(s, land, "library", position="top")
    sp = card_named(s, "Commander Spock")
    to(s, sp, "hand")
    mana(s, G=1, W=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sp.id)
    answer(s, [], land.id if take else [])  # (nothing to cast: a land isn't cast); "you may put it onto the battlefield tapped"
    if take:
        assert zone(s, land) == "p1:battlefield" and s.state.cards[land.id].tapped
    else:
        assert zone(s, land) == "p1:hand"  # still on top: drawn
    check(s)
