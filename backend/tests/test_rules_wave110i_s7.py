"""Wave 110I (session 7): real Oracle text; scenarios check replay and save/load.

* Fasting: the draw step is skipped only when its controller says so (614.10a, 614.1); skipping gains 2 life; drawing destroys it (121.1).
* Smelting Vat: the up-to-two noncreature artifacts put onto the battlefield have total mana value at most the sacrificed artifact's (608.2d).
* Hipparion: blocking a creature with power 3 or greater costs {1} (509.1d); power 2 costs nothing.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import build, card_named, life, mana, put
from tests.wave110a_kit import answer
from tests.wave110c_kit import check, make_db

HIPPARION = "This creature can't block creatures with power 3 or greater unless you pay {1}."
FASTING = ("At the beginning of your upkeep, put a hunger counter on this enchantment. Then destroy this enchantment if it has five or more hunger counters on it.\n"
           "If you would begin your draw step, you may skip that step instead. If you do, you gain 2 life.\nWhen you draw a card, destroy this enchantment.")
VAT = ("{1}, {T}, Sacrifice another artifact: Reveal the top eight cards of your library. Put up to two noncreature artifact cards with total mana value "
       "less than or equal to the sacrificed artifact's mana value from among them onto the battlefield and the rest on the bottom of your library in a random order.")
EXTRA = [real("Smelting Vat", "{2}", 2, "Artifact", VAT, None, ""),
         real("Probe Gem1", "{1}", 1, "Artifact", "", None, ""), real("Probe Gem2", "{2}", 2, "Artifact", "", None, ""),
         real("Probe Gem3", "{3}", 3, "Artifact", "", None, ""), real("Probe Golem", "{1}", 1, "Artifact Creature — Golem", "", ("1", "1"), ""),
         real("Fasting", "{W}", 1, "Enchantment", FASTING, None, "W"),
         real("Hipparion", "{1}{G}", 2, "Creature — Horse", HIPPARION, ("1", "3"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("power", "paid"), [("3", True), ("4", True), ("2", False)])
def test_hipparion_block_tax(cards, power, paid):
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import combat_step, pool

    s = sandbox(cards)
    a = creature(s, "p1", "Atk", f"{power}/4")
    h = creature(s, "p2", "Hip", "1/3", text=HIPPARION)
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if paid:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": h.id, "attacker_id": a.id}])
        pool(s, "p2", G=1)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": h.id, "attacker_id": a.id}])
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[h.id].is_blocking
    assert not s.state.players["p2"].mana.get("G")
    check(s)


@pytest.mark.parametrize("skip", [True, False])
def test_fasting_optional_skip(cards, skip):
    s = build(cards, ["Fasting"])
    put(s, "Fasting")
    hand = len(s.state.zones["p1:hand"])
    asked = 0
    for _ in range(200):
        d = s.state.rules.decision
        if s.state.turn.number >= 3 and s.state.turn.phase == "main1":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif (d.resume or {}).get("step") == "skip_may110i":
            asked += 1
            assert d.player == "p1"
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes" if skip else "no"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert asked == 1
    fasting = card_named(s, "Fasting")
    assert (life(s) == 42 and len(s.state.zones["p1:hand"]) == hand and fasting.zone == "p1:battlefield") if skip \
        else (life(s) == 40 and len(s.state.zones["p1:hand"]) == hand + 1 and s.state.cards[fasting.id].zone == "p1:graveyard")
    check(s)


def _vat(cards, sac):
    s = build(cards, ["Smelting Vat", "Probe Gem1", "Probe Gem2", "Probe Gem3", "Probe Golem"])
    vat = put(s, "Smelting Vat")
    rock = put(s, sac)  # the only other artifact: sacrificed as the cost
    for n in ("Probe Golem", "Probe Gem3", "Probe Gem2", "Probe Gem1"):
        if n != sac:
            act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "library"}, position="top")
    mana(s, C=1)
    activate(s, "p1", vat)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            return s, d, rock
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no pick")


def test_smelting_vat_total_mana_value(cards):
    s, d, rock = _vat(cards, "Probe Gem3")
    g1, g2, golem = (card_named(s, n) for n in ("Probe Gem1", "Probe Gem2", "Probe Golem"))
    assert golem.id not in [o.id for o in d.options] and g1.id in [o.id for o in d.options]  # noncreature only
    answer(s, [g1.id, g2.id])  # 1 + 2 <= 3
    assert {s.state.cards[g1.id].zone, s.state.cards[g2.id].zone} == {"p1:battlefield"}
    assert s.state.cards[golem.id].zone == "p1:library" and s.state.cards[rock.id].zone == "p1:graveyard"
    check(s)


def test_smelting_vat_refuses_too_much_mana_value(cards):
    s, d, rock = _vat(cards, "Probe Gem1")  # mana value 1
    g2, g3 = card_named(s, "Probe Gem2"), card_named(s, "Probe Gem3")
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[g2.id])  # 2 > 1
    answer(s, [])
    assert s.state.cards[g2.id].zone == "p1:library" and s.state.cards[g3.id].zone == "p1:library"
    check(s)
