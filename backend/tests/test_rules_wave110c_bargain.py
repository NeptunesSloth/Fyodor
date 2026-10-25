"""Wave 110C: Back for Seconds (702.166b bargain read as kicked; 608.2d the controller picks the one target put onto the battlefield instead),
Blitzball Stadium (701.41a support X; 122.1 kinds of counters; 509.1b unblockable),
Nahiri's Lithoforming (305.2 X extra land plays; 614.1d lands enter tapped this turn)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real, to_hand

EXTRA = [real("Back for Seconds", "{2}{B}", 3, "Sorcery",
              "Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\n"
              "Return up to two target creature cards from your graveyard to your hand. If this spell was bargained, you may put one of those cards with "
              "mana value 4 or less onto the battlefield instead of putting it into your hand.", None, "B"),
         real("Nahiri's Lithoforming", "{X}{R}{R}", 2, "Sorcery",
              "Sacrifice X lands. For each land sacrificed this way, draw a card. You may play X additional lands this turn. Lands you control enter tapped this turn.", None, "R"),
         real("Blitzball Stadium", "{X}{U}", 1, "Artifact",
              "When this artifact enters, support X. (Put a +1/+1 counter on each of up to X target creatures.)\n"
              "Go for the Goal! — {3}, {T}: Until end of turn, target creature gains \"Whenever this creature deals combat damage to a player, draw a card for each kind of counter on it\" "
              "and it can't be blocked this turn.", None, "U"),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Huge Bear", "{5}{G}", 6, "Creature — Bear", "", ("6", "6"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Back for Seconds", "Nahiri's Lithoforming", "Blitzball Stadium"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def grave(s, *names):
    out = [put(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in out], to={"player": "p1", "zone": "graveyard"})
    return out


@pytest.mark.parametrize("bargain,where", [(False, ("p1:hand", "p1:hand")), (True, ("p1:battlefield", "p1:hand"))])
def test_bargained_puts_a_cheap_target_onto_the_battlefield(cards, bargain, where):
    """702.166b + 608.2d: bargained, the controller picks a target with mana value 4 or less; the other still goes to hand."""
    s = build(cards, ["Back for Seconds", "Small Bear", "Huge Bear", "Sol Ring"])
    small, huge = grave(s, "Small Bear", "Huge Bear")
    ring = put(s, "Sol Ring")
    src = to_hand(s, "Back for Seconds")
    mana(s, B=1, C=2)
    from app.rules.view import hints

    kw = {"optional_costs": [hints(s.state, "p1", s.cards)["optional_costs"][src.id][0]["id"]]} if bargain else {}
    act(s, "p1", type="cast_spell", card_id=src.id, targets=[small.id, huge.id], target_counts=[2], **kw)
    if bargain:
        d = s.state.rules.decision
        while d is not None and d.resume.get("step") != "choose_branch110c":
            answer(s, [ring.id]) if "sacrifice" in d.prompt.lower() else act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
            d = s.state.rules.decision
        assert [o.label for o in d.options] == ["Return them to your hand", "Battlefield: Small Bear"]
        answer(s, [d.options[1].id])
    else:
        answer(s)
    assert (s.state.cards[small.id].zone, s.state.cards[huge.id].zone) == where
    check(s)


@pytest.mark.parametrize("x", [0, 1, 2])
def test_lithoforming_draws_per_land_sacrificed_then_extra_tapped_land_plays(cards, x):
    """608.2c/305.2/614.1d: X lands sacrificed and cards drawn; X more land plays this turn; the lands played enter tapped."""
    s = build(cards, ["Nahiri's Lithoforming"])
    lands = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"]
    act(s, "p1", type="move", card_ids=lands[:2], to={"player": "p1", "zone": "battlefield"})
    in_hand = lands[2:5]
    act(s, "p1", type="move", card_ids=in_hand, to={"zone": "hand"})
    mana(s, R=2, C=x)
    hand = len(s.state.zones["p1:hand"])
    src = to_hand(s, "Nahiri's Lithoforming")
    act(s, "p1", type="cast_spell", card_id=src.id, targets=[], x_value=x, sources=[])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + x  # the spell left the hand, X cards were drawn
    played = 0
    for cid in in_hand:
        try:
            act(s, "p1", type="play_land", card_id=cid)
        except Exception:
            break
        assert s.state.cards[cid].tapped
        played += 1
    assert played == 1 + x
    check(s)


def test_blitzball_support_x_then_unblockable_draws_per_kind_of_counter(cards):
    """701.41a: X counters' worth of targets; 122.1: one card per kind of counter on the creature; 509.1b: it can't be blocked."""
    s = build(cards, ["Blitzball Stadium", "Small Bear"], ["Huge Bear"])
    bear, wall = put(s, "Small Bear"), put(s, "Huge Bear", pid="p2")
    stadium = to_hand(s, "Blitzball Stadium")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=stadium.id, targets=[bear.id], target_counts=[1], x_value=1, sources=[])
    answer(s)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1
    act(s, "p1", type="counter", card_ids=[bear.id], kind="flying", delta=1)
    to_phase(s, "main1", 3)
    mana(s, C=3)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=stadium.id, ability=1, targets=[bear.id])
    answer(s)
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bear.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == before + 2
    check(s)
