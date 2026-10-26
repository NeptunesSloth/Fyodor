"""Wave 110G session 13: Roar of Jukai (702.47a splice; 118.1 "An opponent gains 5 life" is a cost paid as an additional cost)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave110b_kit import ch

SPLICE = " (As you cast an Arcane spell, you may reveal this card from your hand and pay its splice cost. If you do, add this card's effects to that spell.)"
EXTRA = [
    real("Roar of Jukai", "{1}{G}", 2, "Instant", "If you control a Forest, each blocked creature gets +2/+2 until end of turn.\nSplice onto Arcane—An opponent gains 5 life." + SPLICE, None, "G"),
    real("Kodama's Might", "{G}", 1, "Instant — Arcane", "Target creature gets +2/+2 until end of turn.\nSplice onto Arcane {G}" + SPLICE, None, "G"),
    real("Raging River", "{R}{G}", 2, "Enchantment", "Whenever one or more creatures you control attack, each defending player divides all creatures without flying they control into a \"left\" pile and a \"right\" pile. Then, for each attacking creature you control, choose \"left\" or \"right.\" That creature can't be blocked this combat except by creatures with flying and creatures in a pile with the chosen label.", None, "GR"),
    real("Sky Hawk", "{2}{U}", 3, "Creature \u2014 Bird", "Flying", ("1", "1"), "U"),
    real("Bear Cub", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Roar of Jukai", "Raging River"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("forest", [True, False])
def test_roar_spliced_onto_arcane_gives_opponent_life_and_pumps_blocked(cards, forest):
    s = build(cards, ["Bear Cub", "Kodama's Might", "Roar of Jukai", "Forest"], ["Bear Cub"])
    atk, blk = put(s, "Bear Cub"), put(s, "Bear Cub", "p2")
    if forest:
        put(s, "Forest")
    might, roar = to_hand(s, "Kodama's Might"), to_hand(s, "Roar of Jukai")
    s.state.rules.controlled_since[atk.id].turn = 0
    act(s, "p1", type="pass_priority")
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atk.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blk.id, "attacker_id": atk.id}])
    mana(s, G=2)
    life = s.state.players["p2"].life
    act(s, "p1", type="cast_spell", card_id=might.id, splice=[roar.id], targets=[atk.id], target_counts=[1])
    assert s.state.cards[roar.id].zone == "p1:hand" and s.state.players["p2"].life == life + 5  # 702.47a: cost paid at cast, card stays in hand
    for _ in range(10):
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # Might +2/+2 on the attacker; Roar +2/+2 on each blocked creature (the attacker is blocked) if a Forest is controlled
    assert ch(s, atk).pt == ((6, 6) if forest else (4, 4))
    check(s)


def _decide(s, player, ids):
    d = s.state.rules.decision
    assert d is not None and d.player == player, d
    act(s, player, type="choose", decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize("label, flier", [("left", False), ("right", False), ("left", True)])
def test_raging_river_piles_limit_blockers(cards, label, flier):
    """508.5 / 509.1b: Bob's left pile is B1; the chosen label decides which ground blocker may block; a flier always may."""
    s = build(cards, ["Raging River", "Bear Cub"], ["Bear Cub", "Grizzly Bears", "Sky Hawk"])
    put(s, "Raging River")
    atk, b1, b2 = put(s, "Bear Cub"), put(s, "Bear Cub", "p2"), put(s, "Grizzly Bears", "p2")
    hawk = put(s, "Sky Hawk", "p2")
    s.state.rules.controlled_since[atk.id].turn = 0
    act(s, "p1", type="pass_priority")
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atk.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")  # the trigger resolves
    act(s, "p2", type="pass_priority")
    _decide(s, "p2", [b1.id])  # left pile: B1 (the flier isn't divided)
    _decide(s, "p1", [label])
    ok, bad = (b1, b2) if label == "left" else (b2, b1)
    for p in ("p1", "p2"):
        if s.state.rules.priority == p:
            act(s, p, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bad.id, "attacker_id": atk.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": (hawk if flier else ok).id, "attacker_id": atk.id}])
    check(s)
