"""Wave 110C: "If you would lose the game, instead ..." (614.1a, 104.3, 704.5a): Exquisite Archangel, The Golden Throne, Lich's Mirror."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, life, make_db, put, real

EXTRA = [
    real("Exquisite Archangel", "{4}{W}{W}", 6, "Creature — Angel", "Flying\nIf you would lose the game, instead exile this creature and your life total becomes equal to your starting life total.",
         ("4", "5"), "W"),
    real("The Golden Throne", "{2}{W}{W}", 4, "Legendary Artifact",
         "Arcane Life-support — If you would lose the game, instead exile The Golden Throne and your life total becomes 1.\nA Thousand Souls Die Every Day — {T}, Sacrifice a creature: Add three mana in any combination of colors.",
         None, ""),
    real("Lich's Mirror", "{5}", 5, "Artifact",
         "If you would lose the game, instead shuffle your hand, your graveyard, and all permanents you own into your library, then draw seven cards and your life total becomes 20.",
         None, ""),
]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _lose(s):
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")  # (the next state-based check: a table edit is not an intent)
    answer(s)


def test_archangel_exiles_itself_and_resets_life(cards):
    s = build(cards, ["Exquisite Archangel"])
    angel = put(s, "Exquisite Archangel")
    _lose(s)
    assert life(s) == 40 and s.state.cards[angel.id].zone == "p1:exile" and s.state.rules.winner is None
    _lose(s)  # the replacement is used up: the next loss happens
    assert s.state.rules.winner == "p2"
    check(s)


def test_golden_throne_sets_life_to_one(cards):
    s = build(cards, ["The Golden Throne"])
    throne = put(s, "The Golden Throne")
    _lose(s)
    assert life(s) == 1 and s.state.cards[throne.id].zone == "p1:exile" and s.state.rules.winner is None
    check(s)


def test_lich_mirror_shuffles_everything_in_and_draws_seven(cards):
    s = build(cards, ["Lich's Mirror", "Grizzly Bears"])
    mirror, bears = put(s, "Lich's Mirror"), put(s, "Grizzly Bears")
    _lose(s)
    assert life(s) == 20 and s.state.rules.winner is None
    assert s.state.cards[mirror.id].zone != "p1:battlefield" and s.state.cards[bears.id].zone != "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == 7 and not s.state.zones.get("p1:graveyard")
    check(s)


def test_loss_happens_without_a_replacement(cards):
    s = build(cards, ["Grizzly Bears"])
    _lose(s)
    assert s.state.rules.winner == "p2"


def test_two_replacements_player_chooses_order(cards):
    """616.1: Golden Throne and Lich's Mirror both apply; the player picks, and the other stays for the next loss."""
    for pick, expect_life in (("The Golden Throne", 1), ("Lich's Mirror", 20)):
        s = build(cards, ["The Golden Throne", "Lich's Mirror"])
        throne, mirror = put(s, "The Golden Throne"), put(s, "Lich's Mirror")
        act(s, "p1", type="set_life", player="p1", value=0)
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
        assert d is not None and d.player == "p1" and {o.label for o in d.options} == {"The Golden Throne", "Lich's Mirror"}
        chosen = throne if pick == "The Golden Throne" else mirror
        other = mirror if chosen is throne else throne
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[chosen.id])
        answer(s)
        assert life(s) == expect_life and s.state.rules.winner is None
        assert s.state.cards[chosen.id].zone != "p1:battlefield"
        if chosen is throne:
            assert s.state.cards[other.id].zone == "p1:battlefield"
        check(s)


TRIS = real("Triskaidekaphobia", "{3}", 3, "Enchantment",
            "At the beginning of your upkeep, choose one —\n• Each player with exactly 13 life loses the game, then each player gains 1 life.\n"
            "• Each player with exactly 13 life loses the game, then each player loses 1 life.", None, "")
EXTRA.append(TRIS)


def test_two_player_loss_each_replaced_then_rest_of_effect_runs(cards):
    """104.3e + 616.1: both players lose at once; p1's choice among two replacements pauses the effect, p2's own applies, then 'each player gains 1 life' still runs."""
    s = build(cards, ["Triskaidekaphobia", "The Golden Throne", "Lich's Mirror"], ["Exquisite Archangel"])
    put(s, "Triskaidekaphobia")
    throne, mirror = put(s, "The Golden Throne"), put(s, "Lich's Mirror")
    angel = put(s, "Exquisite Archangel", "p2")
    for p in ("p1", "p2"):
        act(s, p, type="set_life", player=p, value=13)
    for _ in range(60):  # (to p1's next upkeep trigger: choose the first mode)
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one" and d.player == "p1" and any(o.id == throne.id for o in d.options):
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.id for o in d.options} == {throne.id, mirror.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[throne.id])
    answer(s)
    assert life(s, "p1") == 2 and life(s, "p2") == 41  # replaced to 1 / 40, then each player gains 1
    assert s.state.cards[throne.id].zone == "p1:exile" and s.state.cards[angel.id].zone == "p2:exile"
    assert s.state.cards[mirror.id].zone == "p1:battlefield" and s.state.rules.winner is None
    check(s)
