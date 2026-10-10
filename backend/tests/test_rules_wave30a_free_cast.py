"""Wave 30A: free-cast cleanup of the granted casts (CR 2026-09-25). Real Oracle text (tests/fixtures/wave29b_cards.json); each scenario checks the
replay and a save and a load.

* 702.60a ripple: "Put all revealed cards not cast this way on the bottom of your library in any order." A revealed card with the spell's name that
  is declined (or can't be cast, or whose cast is cancelled: 601.2) is one of those cards, so its owner orders it with the others in one move
  (401.4), not after them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_review29b_granted_faces import asked, cascade_into, options
from tests.wave9c_kit import build, mana, put, reloaded

HERE = Path(__file__).parent / "fixtures"
DATA = [*json.loads((HERE / "wave29b_cards.json").read_text("utf-8")), *json.loads((HERE / "review29b_cards.json").read_text("utf-8"))]
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def choose(s, *options):
    d = decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(options))


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def ripple_question(cards):
    """Thrumming Stone gives Hit // Run ripple 4: p1 casts one copy (target p2), the other is on top of the library, and the "cast it?" is pending."""
    s = build(cards, ["Thrumming Stone", "Hit // Run", "Hit // Run"])
    put(s, "Thrumming Stone")
    first, second = [c for c in s.state.cards.values() if c.name == "Hit // Run" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "library"}, position="top")
    top4 = list(s.state.zones["p1:library"][:4])
    mana(s, B=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "suspend_cast":
            return s, second, top4
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:  # (reveal the top four: yes)
            choose(s, *[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never asked")


# -- ripple: the declined card joins the others (702.60a) ------------------------------------------------------------------------------
def test_a_declined_ripple_card_is_ordered_with_the_others(cards):
    """Declining the revealed Hit // Run: all four revealed cards go on the bottom in the order p1 gives, the declined one among them (before the
    fix it was put last, below the three others, whatever p1 chose)."""
    s, second, top4 = ripple_question(cards)
    s = reloaded(s)
    choose(s, "no")
    d = decision(s)
    assert d.kind == "order" and {o.card_id for o in d.options} == set(top4)
    order = [*[c for c in top4 if c != second.id], second.id]  # (first chosen ends at the very bottom: the declined card is the fourth from it)
    choose(s, *order)
    assert s.state.zones["p1:library"][-4:] == list(reversed(order)) and s.state.zones["p1:library"][-4] == second.id
    assert s.state.rules.decision is None and not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    check(s)


def test_a_ripple_cast_cancelled_at_its_target_is_a_card_not_cast(cards):
    """601.2: Hit // Run chosen to be cast and then cancelled at its target joins the cards not cast: the ability goes on, and p1 orders all four."""
    s, second, top4 = ripple_question(cards)
    choose(s, "yes")
    d = decision(s)
    assert d.resume["step"] == "cast_target" and s.view("p1")["rules"]["decision"]["cancelable"]
    s = reloaded(s)
    choose(s, "cancel")
    d = decision(s)
    assert d.kind == "order" and {o.card_id for o in d.options} == set(top4)
    choose(s, *[o.card_id for o in d.options])
    assert set(s.state.zones["p1:library"][-4:]) == set(top4) and s.state.cards[second.id].zone == "p1:library"
    assert s.state.rules.decision is None and not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    check(s)


def test_a_cast_ripple_card_is_left_out_of_the_order(cards):
    """702.60a: only the revealed cards not cast go on the bottom: p1 orders the other three after Hit is cast."""
    s, second, top4 = ripple_question(cards)
    choose(s, "yes")
    choose(s, "p2")
    d = decision(s)
    assert d.kind == "order" and {o.card_id for o in d.options} == set(top4) - {second.id}
    s = reloaded(s)
    choose(s, *[o.card_id for o in d.options])
    assert s.state.cards[second.id].zone == "stack" and s.state.rules.free_cast_then is None
    check(s)


# -- an unpayable free cast is never a dead end (601.2h, 118.9d) -----------------------------------------------------------------------
def test_a_cast_whose_cost_cant_be_paid_leaves_the_question_open(cards):
    """Sol Ring cascaded under Thalia ("Noncreature spells cost {1} more") costs {1}, and p1 (auto payment) has no mana. Mana is not checked before
    the question (a payment by hand, "self" or manual mode, can use mana abilities that auto payment doesn't count, so skipping it would refuse a
    cast that could be made), so "yes" is offered; it is refused with a message, the question stays, and "no" is the way out (cancelling is the
    way out of a cast refused at its target: tests/test_rules_review29b_granted_faces.py)."""
    s, ring, went_past = cascade_into(cards, "Sol Ring", theirs=["Thalia, Guardian of Thraben"], passed=["Craterhoof Behemoth"],
                                      setup=lambda s: put(s, "Thalia, Guardian of Thraben", "p2"))
    assert options(s) == [("yes", "Cast it"), ("no", "Put it on the bottom")]
    with pytest.raises(ActionError):
        choose(s, "yes")
    assert asked(s) and ring.id in s.state.rules.free_casts
    s = reloaded(s)
    choose(s, "no")
    assert set(s.state.zones["p1:library"][-2:]) == {ring.id, *went_past} and not s.state.rules.free_casts
    check(s)
