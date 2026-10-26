"""Wave 110C: Breath of Fury: 701.21a sacrifice the enchanted creature, 303.4 attach the Aura to another creature you control, and only if you did, 500.8 untap all
your creatures and an additional combat phase after this one."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import build, check, make_db, mana, put, real, to_hand

BREATH = ("Enchant creature you control\nWhen enchanted creature deals combat damage to a player, sacrifice it and attach this Aura to a creature you control. If you do, "
          "untap all creatures you control and after this phase, there is an additional combat phase.")
EXTRA = [real("Breath of Fury", "{2}{R}{R}", 4, "Enchantment — Aura", BREATH, None, "R"),
         real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"), real("Test Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Breath of Fury")).level == "FULL"


def _setup(cards, others):
    s = build(cards, ["Breath of Fury", "Test Bear", "Test Giant"][: 2 + others])
    bear = put(s, "Test Bear")
    giant = put(s, "Test Giant") if others else None
    for c in (bear, giant):
        if c is not None:
            s.state.rules.controlled_since[c.id].turn = 0
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Breath of Fury").id, targets=[bear.id])
    for _ in range(4):
        if not s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    to_phase(s, "declare_attackers", 1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    return s, bear, giant


@pytest.mark.parametrize("others", [1, 0])
def test_sacrifice_move_untap_and_extra_combat(cards, others):
    s, bear, giant = _setup(cards, others)
    aura = next(c for c in s.state.cards.values() if c.name == "Breath of Fury")
    combats = 0
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            combats += 1
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[giant.id] if giant and giant.id in [o.id for o in d.options] else [d.options[0].id])
        elif s.state.turn.phase in ("main2", "end") or s.state.turn.number > 1:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    if others:
        assert s.state.cards[aura.id].attached_to == giant.id and not s.state.cards[giant.id].tapped
        assert combats == 1  # the additional combat phase's declare-attackers
    else:
        assert s.state.cards[aura.id].zone == "p1:graveyard" and combats == 0
    check(s)
