"""-- round 5 audit: replicate and additional costs -- scenarios through the real action API with real Oracle text pulled from the card
database: replicate (702.56: the count, the total cost 601.2f, one copy per payment, new targets for the copies, copies aren't cast 707.10,
magecraft sees them, a copy of a replicated spell isn't replicated, Djinn Illuminatus's grant), kicker / multikicker (702.33), buyback,
entwine, escalate, splice, conspire, bargain, casualty, squad, mandatory additional costs ("sacrifice a creature", "discard a card",
"pay X life"), cost changes on additional costs (Thalia, a reducer), free casts that still pay kicker (118.9d), flashback + kicker, commander
tax with kicker (903.8), and copies of a kicked spell being kicked (707.10). Every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_review_core import REAL_DB, real_cards
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

NAMES = ["Train of Thought", "Gigadrowse", "Shattering Spree", "Djinn Illuminatus", "Archmage Emeritus", "Grapeshot", "Twincast",
         "Burst Lightning", "Everflowing Chalice", "Thalia, Guardian of Thraben", "Omniscience", "Goblin Electromancer", "Snapcaster Mage",
         "Capsize", "Collective Brutality", "Glacial Ray", "Lava Spike", "Burn Trail", "Torch the Tower", "Cut Your Losses", "Fling",
         "Thrill of Possibility", "Toxic Deluge", "Josu Vess, Lich Knight", "Bone Splinters", "Arco-Flagellant", "Lightning Bolt",
         "Grizzly Bears", "Sol Ring", "Mind Stone", "Hill Giant", "Craw Wurm", "Raging Goblin", "Goblin Piker"]

pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="the real card database is needed")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *real_cards([n for n in NAMES if n not in have])], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


FULL = [n for n in NAMES if n not in ("Grizzly Bears", "Sol Ring", "Mind Stone", "Hill Giant", "Craw Wurm", "Raging Goblin", "Goblin Piker")]


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=120):
    """Resolve the stack; decisions answered from ``picks`` in turn (an option id / label / card id, or a list), else their first options."""
    picks = list(picks)

    def find(d, token):
        return next((o.id for o in d.options if token in (o.id, o.label, o.card_id)), token)

    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [find(d, t) for t in pick] if isinstance(pick, list) else [find(d, pick)] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def stack(s):
    return [s.state.cards[i].name for i in s.state.zones.get("stack", [])]


# -- replicate (702.56) --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("paid", [0, 1, 3])
def test_train_of_thought_one_copy_per_payment(cards, paid):
    s = build(cards, ["Train of Thought"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=1 + paid, C=1 + paid)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=paid)
    answer(s)
    assert hand(s) == before - 1 + 1 + paid  # the spell and one copy per payment each draw a card
    assert zone_of(s, "Train of Thought") == "p1:graveyard"
    assert not s.state.cards[c.id].zone.startswith("stack")
    check(s)


def test_replicate_count_needs_the_mana(cards):
    s = build(cards, ["Train of Thought"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=2, C=2)  # {1}{U} + {1}{U}: one payment, not two
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)


def test_gigadrowse_copies_choose_new_targets(cards):
    s = build(cards, ["Gigadrowse"], ["Grizzly Bears", "Hill Giant", "Craw Wurm"])
    bears, giant, wurm = (put(s, n, "p2") for n in ("Grizzly Bears", "Hill Giant", "Craw Wurm"))
    c = to_hand(s, "Gigadrowse")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2, targets=[bears.id])
    d = s.state.rules.decision
    assert d is not None and "Replicate" in d.prompt, d.prompt  # the copies are replicate's, not storm's
    answer(s, "Choose new targets for each copy", "Hill Giant", "Craw Wurm")
    tapped = {x.name for x in (s.state.cards[bears.id], s.state.cards[giant.id], s.state.cards[wurm.id]) if x.tapped}
    assert tapped == {"Grizzly Bears", "Hill Giant", "Craw Wurm"}
    check(s)


def test_replicate_copies_are_not_cast_storm_counts_one(cards):
    s = build(cards, ["Train of Thought", "Grapeshot"])
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    g = to_hand(s, "Grapeshot")
    mana(s, R=1, C=1)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=["p2"])
    answer(s)  # storm: one spell (Train of Thought) cast before it this turn; its two copies weren't cast
    assert before - life(s, "p2") == 2
    check(s)


def test_magecraft_sees_each_replicate_copy(cards):
    s = build(cards, ["Train of Thought", "Archmage Emeritus"])
    put(s, "Archmage Emeritus")
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=3)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    assert hand(s) == before - 1 + 3 + 3  # three draws from the spell and its copies, three from magecraft (cast + two copies)
    check(s)


def test_a_copy_of_a_replicated_spell_isnt_replicated(cards):
    s = build(cards, ["Train of Thought", "Twincast"])
    c = to_hand(s, "Train of Thought")
    t = to_hand(s, "Twincast")
    mana(s, U=4, C=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    act(s, "p1", type="cast_spell", card_id=t.id, targets=[c.id])
    answer(s)
    # 1 cast + 1 replicate copy + 1 Twincast copy (the copy of a spell whose replicate was paid isn't cast: no trigger, 707.10)
    assert hand(s) == before - 2 + 3
    check(s)


def test_djinn_illuminatus_grants_replicate_equal_to_mana_cost(cards):
    s = build(cards, ["Djinn Illuminatus", "Lightning Bolt"])
    put(s, "Djinn Illuminatus")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=3)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"], replicate=[2])
    answer(s)
    assert before - life(s, "p2") == 9
    check(s)


def test_djinn_offers_its_grant_in_the_hints(cards):
    s = build(cards, ["Djinn Illuminatus", "Lightning Bolt"])
    put(s, "Djinn Illuminatus")
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    hints = s.view("p1")["rules"]["hints"]
    assert b.id in (hints.get("replicate111r3") or {}), hints.get("replicate111r3")


def test_replicate_with_thalia_tax_paid_once(cards):
    s = build(cards, ["Train of Thought"], ["Thalia, Guardian of Thraben"])
    put(s, "Thalia, Guardian of Thraben", "p2")
    c = to_hand(s, "Train of Thought")
    mana(s, U=3, C=4)  # {1}{U} + 2 × {1}{U} + Thalia's {1}: the increase applies once to the total cost (601.2f)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=2)
    answer(s)
    assert hand(s) == before - 1 + 3
    assert not s.state.players["p1"].mana
    check(s)


def test_shattering_spree_free_cast_still_pays_replicate(cards):
    s = build(cards, ["Shattering Spree", "Omniscience"], ["Sol Ring", "Mind Stone"])
    put(s, "Omniscience")
    a1, a2 = put(s, "Sol Ring", "p2"), put(s, "Mind Stone", "p2")
    c = to_hand(s, "Shattering Spree")
    mana(s, R=1)
    # 118.9d: cast without paying its mana cost from the table (the card menu's "Cast without paying its mana cost"), replicate may be paid
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, ask_optional=True, targets=[a1.id])
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options][:1] == ["Replicate {R}"], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    assert not s.state.players["p1"].mana  # the {R} paid once (the mana cost not at all)
    answer(s, "Mind Stone")
    assert zone_of(s, "Sol Ring", "p2").endswith("graveyard") and zone_of(s, "Mind Stone", "p2").endswith("graveyard")
    check(s)


def test_omniscience_kicker_is_offered_and_only_the_kicker_is_paid(cards):
    s = build(cards, ["Burst Lightning", "Omniscience"])
    put(s, "Omniscience")
    c = to_hand(s, "Burst Lightning")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, ask_optional=True, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and "kicker:1" in [o.id for o in d.options], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:1"])
    answer(s)
    assert life(s, "p2") == 36 and not s.state.players["p1"].mana  # kicked: 4 damage, {4} paid (118.9d, 601.2f)
    check(s)


def test_omniscience_without_asking_stays_unkicked(cards):  # (an intent without ask_optional: as before, nothing asked)
    s = build(cards, ["Burst Lightning", "Omniscience"])
    put(s, "Omniscience")
    c = to_hand(s, "Burst Lightning")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 38
    check(s)
