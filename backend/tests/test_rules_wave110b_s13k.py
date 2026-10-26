"""Wave 110B session 13 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Kaito, Dancing Shadow: 603.2c one trigger per batch of combat damage, 606.3 loyalty abilities twice this turn only if a creature was returned (608.2c).
"""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import attack, build, check, drive, put, repository


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kaito, Dancing Shadow")).level == "FULL"


def run(cards, answer):
    s = build(cards, ["Kaito, Dancing Shadow", "Grizzly Bears", "Serra Angel"], [])
    kaito = put(s, "Kaito, Dancing Shadow")
    act(s, "p1", type="counter", card_ids=[kaito.id], kind="loyalty", delta=3 - s.state.cards[kaito.id].counters.get("loyalty", 0))
    bears = put(s, "Grizzly Bears")
    angel = put(s, "Serra Angel")
    attack(s, bears, angel)
    drive_to = lambda d: [bears.id] if answer and bears.id in [o.id for o in d.options] else []  # noqa: E731
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=drive_to(d))
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, kaito, bears, angel


@pytest.mark.parametrize("answer", [True, False])
def test_return_one_then_twice(cards, answer):
    s, kaito, bears, angel = run(cards, answer)
    assert s.state.cards[bears.id].zone == ("p1:hand" if answer else "p1:battlefield")
    assert s.state.cards[angel.id].zone == "p1:battlefield"
    act(s, "p1", type="activate_ability", card_id=kaito.id, ability=2)  # 0: Draw a card.
    drive(s)
    if answer:
        act(s, "p1", type="activate_ability", card_id=kaito.id, ability=2)
        drive(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=kaito.id, ability=2)
    check(s)


def test_overencumbered_full(cards):
    assert coverage.of_card_data(cards.resolve("Overencumbered")).level == "FULL"


def over(cards, pay, extra_artifacts=0):
    """Alice enchants Bob with Overencumbered (he gets Clue, Food, Junk); in his turn's beginning of combat he may pay {1} per artifact."""
    from tests.test_rules_wave30m_durations import to_phase
    from tests.wave110b_kit import cast, mana

    s = build(cards, ["Overencumbered", *["Forest"] * 12], ["Grizzly Bears", *["Forest"] * 12])
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    mana(s, "p1", W=1, U=1, B=1, R=1, G=1, C=5)
    cast(s, "Overencumbered", ["p2"])
    arts = [c for c in s.state.cards.values() if c.controller == "p2" and c.zone == "p2:battlefield" and c.name in ("Clue", "Food", "Junk")]
    assert sorted(c.name for c in arts) == ["Clue", "Food", "Junk"]
    to_phase(s, "main1", turn=2)
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:3]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="set_stops", own=["declare_attackers"], others=[], smart_pass=False)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
        elif d is not None and d.kind == "declare_attackers":
            return s, bears, d
        elif s.state.turn.phase in ("end", "main2"):
            return s, bears, None
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no combat")  # pragma: no cover


@pytest.mark.parametrize("pay", [True, False])
def test_overencumbered_pay_per_artifact_or_no_attack(cards, pay):
    s, bears, d = over(cards, pay)
    if pay:
        assert d is not None
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
        assert s.state.cards[bears.id].tapped
    else:
        if d is not None:
            with pytest.raises(ActionError):
                act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)


def test_heroic_sacrifice_full(cards):
    assert coverage.of_card_data(cards.resolve("Heroic Sacrifice")).level == "FULL"


def heroic(cards, bolts):
    """Alice chooses Bears (one +1/+1 counter: 3/3); Bob's Lightning Bolts at Alice and at Angel are dealt to Bears instead (614.9)."""
    from tests.wave110b_kit import cast, mana

    s = build(cards, ["Heroic Sacrifice", "Serra Angel", "Grizzly Bears", "Elvish Mystic", "Lightning Bolt", "Lightning Bolt"], [])
    bears = put(s, "Grizzly Bears")
    angel = put(s, "Serra Angel")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    mana(s, "p1", W=1, C=1)
    cast(s, "Heroic Sacrifice", [bears.id])
    return s, bears, angel


@pytest.mark.parametrize("target", ["player", "angel"])
def test_heroic_sacrifice_redirects_damage_and_bears_death_moves_counters(cards, target):
    from tests.wave110b_kit import cast, mana

    s, bears, angel = heroic(cards, 1)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    mana(s, "p1", R=1)
    aim = "p1" if target == "player" else angel.id
    cast(s, "Lightning Bolt", [aim])
    drive(s)
    assert s.state.players["p1"].life == 40
    assert s.state.cards[angel.id].damage == 0
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # 3 damage on a 3/3
    assert s.state.cards[angel.id].counters.get("+1/+1", 0) == 1  # its counters move to the up-to-one target
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1  # and you draw a card
    check(s)


def test_heroic_sacrifice_stops_when_chosen_creature_is_gone(cards):
    """(if it's still on the battlefield): after the Bears died, damage goes to its original recipient."""
    from tests.wave110b_kit import cast, mana

    s, bears, angel = heroic(cards, 2)
    for _ in range(2):
        mana(s, "p1", R=1)
        cast(s, "Lightning Bolt", ["p1"])
        drive(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.players["p1"].life == 37
    check(s)


def test_faramir_full(cards):
    assert coverage.of_card_data(cards.resolve("Faramir, Prince of Ithilien")).level == "FULL"


@pytest.mark.parametrize("attacks", [False, True])
def test_faramir_draw_or_soldiers_at_chosen_players_next_end_step(cards, attacks):
    """603.7: Bob's next end step; he did not attack Alice that turn: she draws; he did: three 1/1 Human Soldiers."""
    s = build(cards, ["Faramir, Prince of Ithilien", *["Forest"] * 12], ["Grizzly Bears", *["Forest"] * 12])
    bears = put(s, "Grizzly Bears", "p2")
    put(s, "Faramir, Prince of Ithilien")
    s.state.rules.controlled_since[bears.id].turn = 0
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    soldiers = lambda: [c for c in s.state.cards.values() if c.name == "Human Soldier" and c.zone == "p1:battlefield"]  # noqa: E731
    for _ in range(120):
        d = s.state.rules.decision
        if s.state.turn.number == 3:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}] if attacks and d.player == "p2" else [])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert len(soldiers()) == (3 if attacks else 0)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + (1 if attacks else 2)  # (+1: the draw step of turn 3)
    check(s)


def test_lathiel_full(cards):
    assert coverage.of_card_data(cards.resolve("Lathiel, the Bounteous Dawn")).level == "FULL"


@pytest.mark.parametrize("split", ["one", "none", "fewer"])
def test_lathiel_distributes_up_to_the_life_gained(cards, split):
    """601.2d, 115.6: Soul Warden gains 1 life (Elvish Mystic enters); at the end step up to 1 counter goes on any number of other target creatures (maybe none)."""
    from tests.wave110b_kit import cast, mana

    s = build(cards, ["Lathiel, the Bounteous Dawn", "Soul Warden", "Serra Angel", "Elvish Mystic", "Grizzly Bears", *["Forest"] * 12], [])
    put(s, "Lathiel, the Bounteous Dawn")
    put(s, "Soul Warden")
    angel = put(s, "Serra Angel")
    mana(s, "p1", G=1)
    cast(s, "Elvish Mystic")
    if split == "fewer":  # two life gained: 2 counters may be distributed, fewer is allowed ("up to")
        mana(s, "p1", G=1, C=1)
        cast(s, "Grizzly Bears")
    assert s.state.players["p1"].life == (42 if split == "fewer" else 41)

    def pick(d):
        ids = [o.id for o in d.options]
        if d.kind == "choose_cards" and split == "none":
            return []
        return [angel.id] if angel.id in ids else None

    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[], amounts=[1])  # (1 of the 2 allowed)
        elif d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d) if pick(d) is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.number == 2:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[angel.id].counters.get("+1/+1", 0) == (0 if split == "none" else 1)
    check(s)
