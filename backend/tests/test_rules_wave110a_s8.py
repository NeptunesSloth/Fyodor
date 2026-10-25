"""Wave 110A session 8: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Nacatl War-Pride - "must be blocked by exactly one creature if able": 509.1c requirement (blocked at least once) and 509.1b restriction (not by two).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

NACATL, HARSH, ELMINSTER = "Nacatl War-Pride", "Harsh Justice", "Elminster"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([NACATL, HARSH, ELMINSTER])


def _attack(cards):
    s = build(cards, [NACATL], ["Grizzly Bears", "Hill Giant"])
    nacatl = put(s, NACATL)
    a, b = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": nacatl.id, "target": "p2"}])
    answer(s)
    to_phase(s, "declare_blockers")
    return s, nacatl, a, b


def _tokens(s, nacatl):
    return [c for c in s.state.cards.values() if c.name == NACATL and c.id != nacatl.id and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("plan,legal", [("none", False), ("one", False), ("both_on_nacatl", False), ("one_each", True)])
def test_nacatl_and_its_copies_must_each_be_blocked_by_exactly_one_creature(cards, plan, legal):
    """509.1c: two blockers for three attackers that must each be blocked: both must block, on different attackers; 509.1b: not two on one."""
    s, nacatl, a, b = _attack(cards)
    t1 = _tokens(s, nacatl)[0]
    blocks = {"none": [], "one": [(a, nacatl)], "both_on_nacatl": [(a, nacatl), (b, nacatl)], "one_each": [(a, nacatl), (b, t1)]}[plan]
    blocks = [{"blocker_id": x.id, "attacker_id": y.id} for x, y in blocks]
    if legal:
        act(s, "p2", type="declare_blockers", blocks=blocks)
        assert s.state.cards[a.id].is_blocking and s.state.cards[b.id].is_blocking
        check(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=blocks)


def test_nacatl_attack_trigger_makes_a_token_copy_per_defending_creature_exiled_at_end(cards):
    """111.1 / 508.4 (tapped and attacking), 608.2h (X as it resolves); the tokens are exiled at the beginning of the next end step."""
    s, nacatl, a, b = _attack(cards)
    toks = _tokens(s, nacatl)
    assert len(toks) == 2 and all(t.attacking is not None and t.tapped for t in toks)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": a.id, "attacker_id": nacatl.id}, {"blocker_id": b.id, "attacker_id": toks[0].id}])
    to_phase(s, "end")
    answer(s)
    assert not _tokens(s, nacatl)
    check(s)


def _harsh(cards, hit=True):
    s = build(cards, ["Grizzly Bears"], [HARSH])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    return s, bears


def test_harsh_justice_reflects_combat_damage_to_the_attackers_controller(cards):
    """The damage the attacker dealt to Bob is dealt to Alice by that creature as well (the same amount, 120.3)."""
    s, bears = _harsh(cards)
    cast(s, HARSH, pid="p2")
    answer(s)
    to_phase(s, "end_combat")
    assert life(s, "p2") == 38 and life(s, "p1") == 38
    check(s)


def test_harsh_justice_needs_an_attack_on_you_in_the_declare_attackers_step(cards):
    s = build(cards, ["Grizzly Bears"], [HARSH])
    next_turn(s)
    stops(s)
    to_phase(s, "main1")
    with pytest.raises(ActionError):
        cast(s, HARSH, pid="p2")


@pytest.mark.parametrize("scry", [True, False])
def test_elminster_scry_makes_the_next_instant_or_sorcery_cheaper_by_the_cards_looked_at(cards, scry):
    """701.22d / 601.2f: scry 2 looks at two cards, so the next instant or sorcery costs {2} less this turn (Divination {2}{U} for {U})."""
    s = build(cards, [ELMINSTER, "Divination"])
    elm = put(s, ELMINSTER)
    act(s, "p1", type="counter", card_ids=[elm.id], kind="loyalty", delta=5)
    next_turn(s)
    stops(s)
    if scry:
        act(s, "p1", type="activate_ability", card_id=elm.id, ability=1)
        answer(s)
    fund(s, "{U}")
    if scry:
        cast(s, "Divination", pay=False)
        answer(s)
        assert zone_of(s, "Divination") == "p1:graveyard"
        check(s)
    else:
        with pytest.raises(ActionError):
            cast(s, "Divination", pay=False)
