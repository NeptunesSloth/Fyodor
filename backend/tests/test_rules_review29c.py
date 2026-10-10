"""Review 29C (head review of wave 29C): regressions of the fixes.

* 118.12 / 118.11: "You may draw a card. If you do, …" checks that the player chose to draw, "regardless of what events actually occurred":
  a draw another player's replacement effect took (Notion Thief: the ruling of 2018-03-16, "that opponent still discards a card") is done.
* Target arrows only show a spell's targets: the table takes at most 200 arrows, so the engine's chunks of 20 stop short of that instead of
  refusing the cast or the resolution that makes them.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

from app.game.state import Arrow
from app.rules.plan import ENGINE_ARROWS, Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import RIDDLESMITH, creature
from tests.test_rules_effects import mana
from tests.test_rules_replacements2 import NOTION_THIEF, permanent
from tests.test_rules_wave9b_exile_permission import build, put, roundtrip


def test_if_you_do_holds_when_an_opponents_notion_thief_took_the_draw(cards):
    s = build(cards, p1=("Sol Ring",))
    permanent(s, "p2", "Notion Thief", "Creature", NOTION_THIEF)
    creature(s, "p1", "Riddlesmith", "2/1", "Token Creature — Human Artificer", text=RIDDLESMITH)
    forest = put(s, "Forest", "hand")
    ring = put(s, "Sol Ring", "hand")
    mana(s, C=1)
    bob_hand = len(s.state.zones["p2:hand"])
    act(s, "p1", type="cast_spell", card_id=ring.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(s.state.zones["p2:hand"]) == bob_hand + 1  # (Notion Thief: Alice skips the draw, Bob draws instead)
    assert s.state.cards[forest.id].zone == "p1:graveyard"  # 118.12: she chose to draw, so she discards
    roundtrip(s)


def test_target_arrows_stop_short_of_the_tables_arrow_limit(cards):
    s = build(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    plan.state.arrows = [Arrow(id=f"a{i}", owner="p1", source="p1", targets=["p2"], kind="custom") for i in range(200)]
    plan.target_arrows("p1", ["p2"])  # (the table refuses arrow 201: the cast or resolution making it was refused with it)
    assert len(plan.state.arrows) == 200
    plan.state.arrows = plan.state.arrows[:ENGINE_ARROWS - 2]
    plan.target_arrows("p1", ["p2"])
    assert len(plan.state.arrows) == ENGINE_ARROWS - 1
