"""-- round 6 (cast choosers) -- the optional costs the table's cast chooser offers, with real Oracle text from the card database:
offspring given by a permanent (Zinnia, Valley's Voice: the ``offspring110a`` hint, paid as ``CastSpell.kicker``), a "Kicker {A} and/or {B}"
spell given replicate (Djinn Illuminatus: both kicker costs and the replicate count in one cast), and a spell cast from the top of the
library with Bolas's Citadel, which still pays kicker (118.9d: an alternative cost doesn't stop additional costs). Replay, save and load
are checked for each."""

from __future__ import annotations

import pytest

from app.rules import view
from tests.game_helpers import act
from tests.test_rules_review_core import REAL_DB, real_cards
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

NAMES = ["Zinnia, Valley's Voice", "Grizzly Bears", "Lightning Bolt", "Djinn Illuminatus", "Temporal Firestorm", "Burst Lightning", "Bolas's Citadel",
         "Kavu Titan"]

pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="the real card database is needed")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *real_cards([n for n in NAMES if n not in have])], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def answer(s, *picks, limit=120):
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [next((o.id for o in d.options if pick in (o.id, o.label, o.card_id)), pick)] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hints(s, pid="p1"):
    return view.hints(s.state, pid, s.cards)


def bf(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


# -- a) offspring a permanent gives (Zinnia, Valley's Voice) ------------------------------------------------------------------------------
def test_zinnia_offspring_is_hinted_for_creature_spells_only(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears", "Lightning Bolt", "Kavu Titan"], ["Grizzly Bears"])
    put(s, "Zinnia, Valley's Voice")
    bears, bolt, kavu = to_hand(s, "Grizzly Bears"), to_hand(s, "Lightning Bolt"), to_hand(s, "Kavu Titan")
    mana(s, G=2, R=2, C=4)
    granted = hints(s).get("offspring110a", {})
    assert granted.get(bears.id) == "Offspring {2} (Zinnia, Valley's Voice)", granted
    assert bolt.id not in granted  # not a creature spell
    assert kavu.id not in granted  # its own kicker shares the one paid-cost slot (CastSpell.kicker): not offered
    assert "offspring110a" not in hints(s, "p2")  # the opponent's view never carries it


def test_zinnia_offspring_paid_through_kicker_makes_the_token(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears"])
    put(s, "Zinnia, Valley's Voice")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=1, C=3)  # {1}{G} + offspring {2}
    act(s, "p1", type="cast_spell", card_id=bears.id, kicker=1)
    answer(s)
    assert not s.state.players["p1"].mana  # the offspring cost was paid (601.2f)
    assert len(bf(s, "Grizzly Bears")) == 2  # the card and its 1/1 token copy (702.175a)
    check(s)


def test_zinnia_offspring_not_paid_makes_no_token(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears"])
    put(s, "Zinnia, Valley's Voice")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=bears.id, ask_optional=True)
    answer(s)
    assert len(bf(s, "Grizzly Bears")) == 1 and sum(s.state.players["p1"].mana.values()) == 2
    check(s)


# -- b) "Kicker {A} and/or {B}" given replicate (Djinn Illuminatus) ----------------------------------------------------------------------
def test_djinn_gives_an_and_or_kicker_spell_replicate_and_both_are_paid(cards):
    s = build(cards, ["Djinn Illuminatus", "Temporal Firestorm", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Djinn Illuminatus")
    put(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Temporal Firestorm")
    mana(s, R=4, W=1, U=1, C=8)
    assert hints(s).get("replicate111r3", {}).get(c.id) == ["Replicate {3}{R}{R} (Djinn Illuminatus)"], hints(s).get("replicate111r3")
    # both kicker costs (mask 3: {1}{W} and {1}{U}) and replicate once ({3}{R}{R}), with {3}{R}{R}: 5 + 4 + 5 = 14 mana (601.2f)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=3, replicate=[1])
    assert not s.state.players["p1"].mana
    answer(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


# -- c) Bolas's Citadel: the top card cast for life still pays kicker (118.9d) ------------------------------------------------------------
def citadel(cards, top):
    s = build(cards, ["Bolas's Citadel", top])
    put(s, "Bolas's Citadel")
    c = card_named(s, top)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    return s, c


def test_citadel_cast_from_the_top_asks_for_kicker_and_pays_life_plus_kicker(cards):
    s, bolt = citadel(cards, "Burst Lightning")
    assert bolt.id in hints(s).get("free_castable", [])
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, ask_optional=True, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and "kicker:1" in [o.id for o in d.options], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    answer(s)
    assert life(s, "p2") == 36  # kicked: 4 damage
    assert life(s) == 39  # 119.4: life equal to its mana value (1), not its mana cost
    assert not s.state.players["p1"].mana  # the kicker {4} was paid (601.2f)
    check(s)


def test_citadel_kicker_declined_pays_life_only(cards):
    s, bolt = citadel(cards, "Burst Lightning")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, ask_optional=True, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert life(s, "p2") == 38 and life(s) == 39 and sum(s.state.players["p1"].mana.values()) == 4
    check(s)


def test_citadel_without_mana_for_kicker_casts_at_once(cards):  # nothing payable: nothing asked
    s, bolt = citadel(cards, "Burst Lightning")
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, ask_optional=True, targets=["p2"])
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_cards"
    answer(s)
    assert life(s, "p2") == 38 and life(s) == 39 and zone_of(s, "Burst Lightning") == "p1:graveyard"
    check(s)
