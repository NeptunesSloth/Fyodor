"""Wave 110D: Mishra, Claimed by Gix, real Oracle text.

* 701.42a: the pair attacking melds into Mishra, Lost to Phyrexia, which 508.4 enters tapped and attacking; the drain counts the attackers first.
* 603.4 / 608.2c: the "if" is checked on resolution: without the Engine attacking nothing melds.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave18d_merged import meld_set
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build, check, life, put
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401
from tests.wave110d_kit import next_turn, now, to_phase

MISHRA = ("Mishra, Claimed by Gix", "{2}{B}{R}", 4, "Legendary Creature — Phyrexian Human Artificer",
          "Whenever you attack, each opponent loses X life and you gain X life, where X is the number of attacking creatures. If Mishra, Claimed by Gix and a creature named "
          "Phyrexian Dragon Engine are attacking, and you both own and control them, exile them, then meld them into Mishra, Lost to Phyrexia. It enters tapped and attacking.",
          ("3", "5"), "BR")
ENGINE = ("Phyrexian Dragon Engine", "{3}", 3, "Artifact Creature — Phyrexian Dragon",
          "Double strike\nWhen this creature enters from your graveyard, you may discard your hand. If you do, draw three cards.\nUnearth {3}{R}{R}\n(Melds with Mishra, Claimed by Gix.)",
          ("2", "2"), "")
WATCH = ("Tap Watcher", "{1}", 1, "Enchantment", "Whenever a creature becomes tapped, you gain 1 life.", None, "")
LOST = ("Mishra, Lost to Phyrexia", "", 0, "Legendary Artifact Creature — Phyrexian Artificer", "Menace", ("9", "9"), "BR")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *meld_set(MISHRA, ENGINE, LOST), real(*WATCH)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Mishra, Claimed by Gix")).level == "FULL"


def attack(cards, names, watch=False):
    s = build(cards, [MISHRA[0], ENGINE[0], *([WATCH[0]] if watch else [])], ["Grizzly Bears"])
    if watch:
        put(s, WATCH[0])
    mine = {n: put(s, n) for n in (MISHRA[0], ENGINE[0])}
    next_turn(s)
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine[n].id, "target": "p2"} for n in names])
    for _ in range(20):  # resolve the trigger, staying in the declare attackers step (the melded permanent is still attacking there)
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.rules.pending_triggers:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, mine


def test_both_attacking_meld_tapped_and_attacking(cards):
    s, mine = attack(cards, [MISHRA[0], ENGINE[0]])
    host = now(s, mine[MISHRA[0]])
    assert host.melded and host.name == LOST[0] and host.tapped and host.is_attacking
    assert [p.name for p in host.merged] == [MISHRA[0], ENGINE[0]]  # the Engine is part of the one permanent (712.4a)
    assert life(s, "p2") == 38 and life(s, "p1") == 42  # X = 2 attackers, drained before the meld
    check(s)


def test_the_engine_not_attacking_means_no_meld(cards):
    s, mine = attack(cards, [MISHRA[0]])
    host = now(s, mine[MISHRA[0]])
    assert not host.melded and host.name == MISHRA[0] and now(s, mine[ENGINE[0]]).zone == "p1:battlefield"
    assert life(s, "p2") == 39 and life(s, "p1") == 41  # X = 1
    check(s)


def test_melded_permanent_enters_tapped_without_becoming_tapped(cards):
    """508.4 / 712.4a: it ENTERS tapped and attacking; no "becomes tapped" event, so the watcher counts only the two declared attackers."""
    s, mine = attack(cards, [MISHRA[0], ENGINE[0]], watch=True)
    assert now(s, mine[MISHRA[0]]).tapped and life(s, "p1") == 44  # 42 + 2 (declaration taps), not 45
    check(s)
