"""Wave 110I session 15.

* The Dominion Bracelet: the granted "{15}, Exile <the Bracelet>: You control target opponent during their next turn" (723.1) pays the Bracelet itself as the exile cost
  (granter cost, 607.1a) and costs {X} less, X = the equipped creature's power including the Bracelet's +1/+1 (ruling 2025-07-25: locked in before costs are paid; 601.2f).
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_s11 import _three
from tests.test_rules_wave110i_s14 import BEAR, GIANT  # noqa: F401  (registers the helper creatures)
from tests.wave9c_kit import build, check, life, mana, put
from tests.wave110j_kit import now

BRACELET = real("The Dominion Bracelet", "{2}", 2, "Legendary Artifact — Equipment",
                "Equipped creature gets +1/+1 and has \"{15}, Exile The Dominion Bracelet: You control target opponent during their next turn. This ability costs {X} less to activate, where X is "
                "this creature's power. Activate only as a sorcery.\" (You see all cards that player could see and make all decisions for them.)\nEquip {1}", None, "")
base.EXTRA.append(BRACELET)


def test_bracelet_full(cards):
    assert coverage.of_card_data(cards.resolve("The Dominion Bracelet")).level == "FULL"


def _granted(s, host):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = s.state.cards[host.id]
    return next(x.index for x in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if x.index >= 100 and x.kind == "activated")


def _equipped(cards, creature):
    s = _three(cards, ["The Dominion Bracelet", creature])
    bracelet, host = put(s, "The Dominion Bracelet"), put(s, creature)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bracelet.id, ability=1, targets=[host.id])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bracelet.id].attached_to == host.id
    return s, bracelet, host


@pytest.mark.parametrize(("creature", "cost"), [("Bear110I", 12), ("Giant110I", 14)])
def test_bracelet_cost_drops_by_the_equipped_power_and_exiles_it(cards, creature, cost):
    """2/2 Bear + 1 = power 3: {12}; 0/9 Giant + 1 = power 1: {14}. One mana short is refused; paying exiles the Bracelet and Alice controls Bob next turn."""
    s, bracelet, host = _equipped(cards, creature)
    mana(s, C=cost - 1)
    with pytest.raises(ActionError, match="pay|afford|mana"):
        act(s, "p1", type="activate_ability", card_id=host.id, ability=_granted(s, host), targets=["p2"])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=host.id, ability=_granted(s, host), targets=["p2"])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bracelet.id].zone.endswith(":exile")
    assert [(c.controlled, c.controller) for c in s.state.rules.player_control] == [("p2", "p1")]
    check(s)


# -- Megatron, Tyrant // Megatron, Destructive Force --------------------------------------------------------------------------------------------------------------------------------------
_MFRONT = ("More Than Meets the Eye {1}{R}{W}{B} (You may cast this card converted for {1}{R}{W}{B}.)\nYour opponents can't cast spells during combat.\n"
           "At the beginning of each of your postcombat main phases, you may convert Megatron. If you do, add {C} for each 1 life your opponents have lost this turn.")
_MBACK = ("Living metal (During your turn, this Vehicle is also a creature.)\nWhenever Megatron attacks, you may sacrifice another artifact. When you do, Megatron deals damage equal to the "
          "sacrificed artifact's mana value to target creature. If excess damage would be dealt to that creature this way, instead that damage is dealt to that creature's controller "
          "and you convert Megatron.")
MEGATRON = card("Megatron, Tyrant // Megatron, Destructive Force", set_code="tst", number="110I-mt", layout="transform", mana_cost="{3}{R}{W}{B} // ", cmc=6.0,
                type_line="Legendary Artifact Creature — Robot // Legendary Artifact — Vehicle", power="7", toughness="5", colors=["B", "R", "W"], color_identity=["B", "R", "W"],
                keywords=["Living metal", "Convert", "More Than Meets the Eye"], oracle_text=_MFRONT + "\n//\n" + _MBACK,
                card_faces=[{"name": "Megatron, Tyrant", "mana_cost": "{3}{R}{W}{B}", "type_line": "Legendary Artifact Creature — Robot", "oracle_text": _MFRONT, "power": "7", "toughness": "5",
                             "colors": ["B", "R", "W"]},
                            {"name": "Megatron, Destructive Force", "mana_cost": "", "type_line": "Legendary Artifact — Vehicle", "oracle_text": _MBACK, "power": "4", "toughness": "5",
                             "colors": ["B", "R", "W"]}])
MNAME = MEGATRON["name"]
base.EXTRA.extend([MEGATRON, real("Gizmo110I", "{2}", 2, "Artifact", "", None, ""), real("Anvil110I", "{3}", 3, "Artifact", "", None, ""),
                   real("Wolf110I", "{1}{G}", 2, "Creature — Wolf", "", ("2", "2"), "G")])


def test_megatron_full():
    assert coverage.of_card_data({**MEGATRON, "faces": MEGATRON["card_faces"]}).level == "FULL"


def _swing(s, megatron, pick):
    """Attack with the Vehicle; the may-sacrifice and the target answer as ``pick`` says (an artifact name, or None to decline)."""
    from tests.wave110b_kit import attack

    attack(s, megatron)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            labels = {o.id: o.label for o in d.options}
            ids = [i for i, label in labels.items() if pick is not None and pick in label] or [i for i, label in labels.items() if "Wolf110I" in label or label in ("No", "Don't pay") and (pick is None or "Transform" in d.prompt)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(ids or [o.id for o in d.options])[: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


@pytest.mark.parametrize(("artifact", "excess", "converts"), [("Anvil110I", 1, True), ("Gizmo110I", 0, False), (None, 0, False)])
def test_megatron_redirects_the_excess_and_converts_only_then(cards, artifact, excess, converts):
    """MV 3 into a 2/2: lethal is 2, so 1 excess goes to Bob and Megatron converts (120.4a). MV 2: exactly lethal, no excess, no convert. Declining the sacrifice: nothing."""
    s = build(cards, [MNAME, "Anvil110I", "Gizmo110I"], ["Wolf110I"])
    megatron = put(s, MNAME)
    act(s, "p1", type="set_face", card_id=megatron.id, face=1)
    put(s, "Anvil110I")
    put(s, "Gizmo110I")
    wolf = put(s, "Wolf110I", "p2")
    _swing(s, megatron, artifact)
    assert (s.state.cards[wolf.id].zone.endswith(":graveyard")) == (artifact is not None)
    assert life(s, "p2") == 40 - excess - (7 if converts else 4)  # (then unblocked combat damage: the 7/5 front face after converting, else the 4/5 Vehicle)
    assert (now(s, megatron).face == 0) == converts
    check(s)
