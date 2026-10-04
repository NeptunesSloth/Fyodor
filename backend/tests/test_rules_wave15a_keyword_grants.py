"""Wave 15A: a static ability granting a triggered keyword through its Comprehensive Rules meaning (613.1f): "Other creatures you
control have extort." (Pontiff of Blight; 702.101a) and "Sliver creatures you control have afflict 2." (Lazotep Sliver; 702.130a).
Each instance triggers separately (702.101b, 702.130b). Replay and save/load checked."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, mana, put, reloaded, to_hand
from tests.test_rules_wave6e_statics import attack_with

EXTRA = [
    card("Pontiff of Blight", set_code="tst", number="K01", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Phyrexian Cleric",
         oracle_text="Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain "
                     "that much life.)\nOther creatures you control have extort.", power="3", toughness="3", colors=["B"],
         color_identity=["B"], keywords=["Extort"]),
    card("Lazotep Sliver", set_code="tst", number="K02", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Zombie Sliver",
         oracle_text="Sliver creatures you control have afflict 2. (Whenever this creature becomes blocked, defending player "
                     "loses 2 life.)", power="1", toughness="1", colors=["B"], color_identity=["B"]),
    card("Opt", set_code="tst", number="K03", mana_cost="{U}", cmc=1.0, type_line="Instant", colors=["U"], color_identity=["U"],
         oracle_text="Scry 1.\nDraw a card."),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Pontiff of Blight", "Lazotep Sliver"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_granted_extort_triggers_for_each_instance(cards):
    s = build(cards, "Pontiff of Blight", "Opt")
    put(s, "Pontiff of Blight")
    token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")  # "other creatures you control" have extort too
    opt = to_hand(s, "Opt")
    mana(s, U=1, W=2)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    for _ in range(2):  # two instances: the Pontiff's own and the Bear's granted one
        until(s, lambda s: s.state.rules.decision is not None and any(o.id == "pay" for o in s.state.rules.decision.options))
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 42
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_granted_afflict_makes_the_blocked_players_defender_lose_life(cards):
    s = build(cards, "Lazotep Sliver")
    sliver = put(s, "Lazotep Sliver")
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")
    attack_with(s, sliver)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    life = s.state.players["p2"].life
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": sliver.id}])
    settle(s)
    assert s.state.players["p2"].life == life - 2  # the Sliver is blocked by the Wall (0 damage back): afflict 2 only
    replay_matches(s)
    replay_matches(reloaded(s))
