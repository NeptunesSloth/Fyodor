"""Wave 110B session 14 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Tranquil Frillback: 107.1b pay {G} up to three times, 603.12 the reflexive ability, 700.2b "choose up to that many" modes = the times paid.
"""
from __future__ import annotations

import pytest

from app.rules import coverage, sba
from tests.game_helpers import act
from tests.wave110b_kit import build, card_named, ch, check, drive, life, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tranquil Frillback")).level == "FULL"


def frillback(cards, G, times, modes):
    """Cast it with {2}{G} + ``G`` more green; pay ``times``; choose the mode indexes ``modes`` (artifact and enchantment targets exist)."""
    s = build(cards, ["Tranquil Frillback", "Sol Ring"], ["Grizzly Bears"], forests=30)
    ring = put(s, "Sol Ring")
    to_hand(s, "Tranquil Frillback")
    mana(s, G=3 + G)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tranquil Frillback").id)
    seen = []

    def answer(d):
        seen.append(d.prompt)
        if "how many times" in d.prompt:
            return [f"x:{times}"] if times else ["decline"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return [f"{i}:0" for i in modes]
        return None
    drive(s, answer)
    return s, ring, seen


def test_pay_twice_two_modes(cards):
    s, ring, seen = frillback(cards, 2, 2, [0, 2])
    assert s.state.cards[ring.id].zone.endswith("graveyard") and life(s, "p1") == 44  # destroy artifact, gain 4 (40 + 4)
    assert any("up to two" in p for p in seen)
    check(s)


def test_pay_once_limits_to_one_mode(cards):
    s, ring, seen = frillback(cards, 3, 1, [2])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 44
    assert any("up to one" in p for p in seen)
    check(s)


def test_pay_nothing_no_modes(cards):
    s, ring, _ = frillback(cards, 3, 0, [])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 40
    check(s)


def test_hawkeye_attack_pays_once_for_one_mode(cards):
    """Hawkeye (same "pay {1} up to three times ... choose up to that many" with ability word and mode labels): attacking taps it (603.2)."""
    assert coverage.of_card_data(cards.resolve("Hawkeye, Master Marksman")).level == "FULL"
    from tests.wave110b_kit import attack

    s = build(cards, ["Hawkeye, Master Marksman"], ["Grizzly Bears"], forests=30)
    hawk = put(s, "Hawkeye, Master Marksman")
    mana(s, G=3)

    def answer(d):
        if "how many times" in d.prompt:
            return ["x:1"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return ["1:0"]
        return None
    attack(s, hawk)
    drive(s, answer)
    assert life(s, "p2") == 38  # Explosive: 2 damage to target player (before combat damage)
    check(s)


@pytest.mark.parametrize("sacrifice", [True, False])
def test_dragon_broodmother_token_devours(cards, sacrifice):
    """702.82a: the Dragon token created at each upkeep has devour 2: sacrificing one creature gives it two +1/+1 counters (a 3/3 flier)."""
    assert coverage.of_card_data(cards.resolve("Dragon Broodmother")).level == "FULL"
    s = build(cards, ["Dragon Broodmother", *["Grizzly Bears"] * 20], ["Grizzly Bears"] * 20, forests=30)
    put(s, "Dragon Broodmother")
    bears = put(s, "Grizzly Bears")
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "choose_cards" and "Discard" in d.prompt:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif d is not None:
            assert "devour 2" in d.prompt and bears.id in [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id] if sacrifice else ["done"])
            d = s.state.rules.decision  # asked again until "done" (702.82a: any number)
            if sacrifice:
                assert d is not None and "devour 2" in d.prompt and bears.id not in [o.id for o in d.options]
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["done"])
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("no devour prompt")
    drive(s)
    dragons = [c for c in s.state.cards.values() if c.token and c.token.name == "Dragon"]
    assert len(dragons) == 1
    t = dragons[0]
    assert (sba.power(t, ch(s, t)), sba.toughness(t, ch(s, t))) == ((3, 3) if sacrifice else (1, 1))
    assert s.state.cards[bears.id].zone.endswith("graveyard") == sacrifice
    check(s)


def senu_game(cards, zone, legend="Krenko, Mob Boss", blocker=False):
    from tests.wave110b_kit import attack, through_combat

    s = build(cards, ["Senu, Keen-Eyed Protector", legend, "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    senu = card_named(s, "Senu, Keen-Eyed Protector")
    act(s, "p1", type="move", card_ids=[senu.id], to={"player": "p1", "zone": zone})
    lord = put(s, legend)
    bears = put(s, "Grizzly Bears", "p2") if blocker else None
    attack(s, lord)
    through_combat(s, blocks=[(bears, lord)] if blocker else None)
    return s, senu


def test_senu_enters_attacking_from_exile_when_unblocked(cards):
    """603.2 / 509.3g / 508.4: Krenko attacks unblocked; Senu (exiled) joins the attack, so both connect: 3 + 2 damage."""
    assert coverage.of_card_data(cards.resolve("Senu, Keen-Eyed Protector")).level == "FULL"
    s, senu = senu_game(cards, "exile")
    assert s.state.cards[senu.id].zone.endswith("battlefield") and life(s, "p2") == 35
    check(s)


@pytest.mark.parametrize("zone,blocker", [("hand", False), ("graveyard", False), ("exile", True)])
def test_senu_stays_put_elsewhere_or_when_blocked(cards, zone, blocker):
    """113.6k: the ability works only from exile; a blocked legendary creature doesn't trigger it (509.3g)."""
    s, senu = senu_game(cards, zone, blocker=blocker)
    assert not s.state.cards[senu.id].zone.endswith("battlefield")
    check(s)
