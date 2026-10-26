"""Wave 110B session 20: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* The Raven's Warning: 903.11 no card from outside the game comes into a Commander game, so chapter III offers nothing and the Saga is sacrificed (714.4).
* Summon: Brynhildr: 122.1, 611.2a the exiled card stays playable in every turn its controller puts a lore counter on the Saga (it enters with one, 714.3a), not in others.
* Temporal Extortion ruling check: tests/test_rules_wave110b_s19.py.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, check, drive, life, mana, repository, to_hand, zone_of


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["The Raven's Warning", "Summon: Brynhildr"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_ravens_warning_chapter_three_offers_nothing_from_outside_the_game(cards):
    """903.11: the optional import is impossible, so nothing is asked (608.2d); the Saga is sacrificed after III (714.4)."""
    s = build(cards, ["The Raven's Warning"], [], forests=30, islands=40)
    mana(s, W=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "The Raven's Warning").id)
    drive(s)
    assert life(s, "p1") == 42  # chapter I: the Bird and 2 life
    saga = card_named(s, "The Raven's Warning")
    library = len(s.state.zones["p1:library"])
    to_phase(s, "main1", turn=5)
    drive(s)  # chapters II and III: no decision is left open
    assert s.state.rules.decision is None and zone_of(s, "The Raven's Warning") == "p1:graveyard"
    assert saga.id in s.state.zones["p1:graveyard"] and len(s.state.zones["p1:library"]) <= library
    check(s)


@pytest.mark.parametrize(("turn", "playable"), [(1, True), (3, True), (7, False)])
def test_brynhildr_card_is_playable_in_turns_a_lore_counter_is_put(cards, turn, playable):
    """122.1, 611.2a: playable on the turn the Saga enters (its lore counter) and on later turns with a lore counter put; not once the Saga is gone (turn 7, III was turn 5)."""
    s = build(cards, ["Summon: Brynhildr"], [], forests=30, islands=40)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Summon: Brynhildr").id)
    drive(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile" and c.name == "Forest"]
    assert len(exiled) == 1
    if turn > 1:
        to_phase(s, "main1", turn=turn)
        drive(s)
    if playable:
        act(s, "p1", type="play_land", card_id=exiled[0].id)
        assert s.state.cards[exiled[0].id].zone == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="play_land", card_id=exiled[0].id)
    check(s)


SLICER = "Slicer, Hired Muscle // Slicer, High-Speed Antagonist"


@pytest.mark.parametrize("give", [True, False])
def test_slicer_opponent_upkeep_give_control_or_convert(cards, give):
    """613.1b, 701.39a, 701.21, 701.28: you may have the upkeep's player gain control of Slicer until end of turn; if you do it is untapped, goaded and can't be
    sacrificed this turn; if you don't it converts. Control returns at cleanup (514.2) and the goad lasts until your next turn."""
    from app.rules import keyword_actions, prohibitions
    from app.rules.plan import Plan

    s = build(cards, [SLICER], [], forests=30, islands=40)
    slicer = card_named(s, SLICER)
    act(s, "p1", type="move", card_ids=[slicer.id], to={"player": "p1", "zone": "battlefield"})
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm":
            break
        if d is not None:
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and d.kind == "confirm" and s.state.turn.number == 2 and s.state.turn.phase == "upkeep"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes" if give else "no"])
    drive(s)
    c = s.state.cards[slicer.id]
    plan = Plan(s.state, "p2", s.cards, None)
    if give:
        assert c.controller == "p2" and not c.tapped and c.face == 0
        assert "p1" in keyword_actions.goaded_by(plan.ch(c)) and prohibitions.sacrifice_forbidden(plan, c)
        while not (d := s.state.rules.decision) or d.kind != "declare_attackers":
            act(s, s.state.rules.priority, type="pass_priority")
        with pytest.raises(ActionError, match="goaded"):  # 701.15b: it attacks each combat if able
            act(s, "p2", type="declare_attackers", attackers=[])
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": slicer.id, "target": "p1"}])
        to_phase(s, "main1", turn=3)
        assert s.state.cards[slicer.id].controller == "p1" and not prohibitions.sacrifice_forbidden(Plan(s.state, "p1", s.cards, None), s.state.cards[slicer.id])
    else:
        assert c.controller == "p1" and c.face == 1  # (701.28: converted = transformed)
    check(s)


def test_niv_mizzet_reborn_one_card_of_exactly_each_color_pair(cards):
    """105.2, 608.2d: of the ten revealed cards one card of exactly each color pair is chosen (a pair with several candidates is the player's choice, none no pick; a mono-colored or
    three-color card is never chosen); the chosen cards go to hand, the rest to the bottom of the library."""
    from tests.wave110b_kit import top

    s = build(cards, ["Niv-Mizzet Reborn", "Supreme Verdict", "Genku, Future Shaper", "Fire // Ice", "Bloodbraid Elf", "Kess, Dissident Mage", "Lightning Bolt"], [], forests=30, islands=40)
    ten = ["Supreme Verdict", "Genku, Future Shaper", "Fire // Ice", "Bloodbraid Elf", "Kess, Dissident Mage", "Lightning Bolt"]
    for n in ten:
        top(s, n)
    mana(s, U=3, R=3, G=3, W=3, B=3, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Niv-Mizzet Reborn").id)
    drive(s, lambda d: [o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Supreme Verdict"] or None)
    hand = sorted(s.state.cards[c].name for c in s.state.zones["p1:hand"])
    assert hand == ["Bloodbraid Elf", "Fire // Ice", "Supreme Verdict"]
    check(s)
