"""-- token stack folds review (wave TS2R) -- the independent review of docs/TOKEN_STACKS.md section 9 (folded token-making triggers).

A fold makes the tokens of N identical triggered abilities in ONE creation event. That is exact only when nothing can tell one event of
N·k tokens from N events of k. A one-shot replacement effect of a resolved spell waiting for "the next time one or more creatures …
enter this turn" (Mystic Reflection, 614.5 / 614.12; Storyweave) is used up by the first of the N events: only the first resolution's
tokens are changed. Folding would change all of them, so the fold is refused (the triggers stay separate) or, when the effect arrives in
response, resolving the folded ability is refused. Real Oracle text; replay and save/load round trips.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.pod_c_kit import card, mana, put, settle, to_hand
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_waveTS2_folds import EXTRA as TS2_EXTRA
from tests.test_rules_waveTS2_folds import board, count, ramp, triggers
from tests.wave9c_kit import check

EXTRA = [
    *TS2_EXTRA,
    real("Mystic Reflection", "{1}{U}", 2, "Instant",
         "Choose target nonlegendary creature. The next time one or more creatures or planeswalkers enter this turn, they enter as copies "
         "of the chosen creature.\nForetell {U} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on "
         "a later turn for its foretell cost.)", None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _reflect(s, bears) -> None:
    """Bob casts Mystic Reflection on his Grizzly Bears now and everyone passes until it has resolved."""
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Mystic Reflection", "p2").id, targets=[bears.id])
    while any(s.state.cards[i].name == "Mystic Reflection" for i in s.state.zones.get("stack") or []):
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.turn_log.mirror110b


def test_mystic_reflection_waiting_keeps_the_triggers_separate(cards):
    """Three Scute Swarms and four lands; Bob's Mystic Reflection resolves in response to Rampant Growth. The fifth land triggers each
    Swarm (fewer than six lands: a 1/1 Insect each). Three separate resolutions make three creation events; only the first is "the next
    time one or more creatures enter" (614.5, 614.12), so one Insect is a Grizzly Bears and two are Insects. One folded event of three
    would make all three Bears, so the triggers aren't folded."""
    s = board(cards, 3, lands=4, theirs=["Mystic Reflection", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rampant Growth").id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    _reflect(s, bears)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            forests = [o.id for o in d.options if (o.label or "").startswith("Forest")][:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=forests or [o.id for o in d.options][: max(1, d.min_choices)])
            continue
        if triggers(s):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert triggers(s) == ["Scute Swarm"] * 3
    settle(s)
    assert count(s) == 3 and count(s, "Insect") == 2 and count(s, "Grizzly Bears") == 1
    check(s)


def test_mystic_reflection_in_response_refuses_resolving_the_fold(cards):
    """"Scute Swarm (×3)" is on the stack when Bob's Mystic Reflection resolves: resolving the fold would turn all three Insects into
    Bears, but only the first of three resolutions would. The folded ability can't be taken apart, so resolving it is refused (pause
    automation and resolve them by hand) instead of resolved wrong."""
    s = board(cards, 3, lands=4, theirs=["Mystic Reflection", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×3)"]
    act(s, "p1", type="pass_priority")
    _reflect(s, bears)
    with pytest.raises(ActionError, match="Mystic Reflection"):
        for _ in range(4):
            act(s, s.state.rules.priority, type="pass_priority")
    assert count(s, "Insect") == 0 and count(s, "Grizzly Bears") == 0
    check(s)


def test_fold_survives_save_load_at_the_order_decision(cards):
    """Two folded groups (Scute Swarm ×3, Rampaging Baloths ×2): the order decision (603.3b) and the folded pending triggers round-trip
    through replay and save/load before and after the order is chosen."""
    s = board(cards, 3, mine=["Rampaging Baloths"])
    act(s, "p1", type="create_token", player="p1", token={"card_id": card(s, "Rampaging Baloths").card_id}, count=1, stacked=False)
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rampant Growth").id)
    ordered = False
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "order":
            assert sorted(o.label for o in d.options) == ["Rampaging Baloths (×2)", "Scute Swarm (×3)"]
            check(s)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
            ordered = True
            continue
        if d is not None:
            forests = [o.id for o in d.options if (o.label or "").startswith("Forest")][:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=forests or [o.id for o in d.options][: max(1, d.min_choices)])
            continue
        if triggers(s):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert ordered and sorted(triggers(s)) == ["Rampaging Baloths (×2)", "Scute Swarm (×3)"]
    check(s)
    settle(s)
    assert count(s) == 6 and count(s, "Beast") == 2
    check(s)
