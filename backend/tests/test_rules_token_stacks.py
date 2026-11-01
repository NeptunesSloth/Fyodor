"""-- token stacks (gap 2) -- A logical token stack ("Goblin ×10": ``CardInstance.quantity``) is one card on the table standing for N
identical tokens, a sandbox convenience. The rules engine works with objects: a token is an object (109.1), each token on the battlefield is
a permanent (110.1) subject to everything that affects permanents (111.6). So with automation on the engine never sees a stack:

* tokens made by hand are made as separate objects (the client's ``stacked`` is ignored) and identical tokens aren't merged;
* a stack that exists anyway (made while automation was off, an older save, ``stack_adjust``) is spread out before the engine reads the
  table: the tokens were already there, so spreading is no event (no "enters" trigger, no token "created"), and each token has been under
  its controller's control as long as the stack has (302.6).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_combat import automate, table
from tests.test_rules_conditionals import build, life, settle
from tests.test_rules_effects import mana, replay_matches

MIRKWOOD_BATS = card('Mirkwood Bats', set_code='tst', number='GX2T1', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Bat',
                     oracle_text='Flying\nWhenever you create or sacrifice a token, each opponent loses 1 life.', power='2', toughness='3',
                     colors=['B'], color_identity=['B'], keywords=['Flying'])
GOBLIN = {"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "colors": ["R"]}
TREASURE = {"name": "Treasure", "type_line": "Token Artifact — Treasure", "text": "{T}, Sacrifice this token: Add one mana of any color."}
KRENKO_TEXT = "{1}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control."


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), MIRKWOOD_BATS], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def saved(s):
    """The table saved and loaded again: play goes on from the loaded one."""
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded


def on_field(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def boss(s):
    """A Krenko-like counter of Goblins ("for each" / "the number of"), as a token with the activated ability."""
    act(s, "p1", type="create_token", player="p1", token={"name": "Boss", "type_line": "Token Creature — Test", "power": "1",
                                                          "toughness": "1", "text": KRENKO_TEXT})
    return on_field(s, "Boss")[0]


def activate(s, source):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    settle(s)


def test_tokens_made_by_hand_are_separate_objects_with_automation_on(cards):
    s = build(cards)
    made = act(s, "p1", type="create_token", player="p1", token=GOBLIN, count=10, stacked=True)
    assert made.stacked is False  # recorded as made: the replay makes ten too
    goblins = on_field(s, "Goblin")
    assert len(goblins) == 10 and all(g.quantity == 1 for g in goblins)
    s = saved(s)
    activate(s, boss(s))  # X is the number of Goblins you control: ten objects, ten Goblins
    assert len(on_field(s, "Goblin")) == 20
    replay_matches(s)


def test_the_sandbox_still_stacks(cards):
    s = table(cards)  # automation off
    act(s, "p1", type="create_token", player="p1", token=GOBLIN, count=10, stacked=True)
    (stack,) = on_field(s, "Goblin")
    assert stack.quantity == 10


def test_identical_tokens_are_not_merged_with_automation_on(cards):
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token=GOBLIN, count=2)
    a, b = on_field(s, "Goblin")
    with pytest.raises(ActionError, match="its own object"):
        act(s, "p1", type="merge_tokens", card_ids=[a.id, b.id])
    assert len(on_field(s, "Goblin")) == 2


def test_a_stack_is_spread_out_before_the_engine_sacrifices_one_treasure(cards):
    """Mirkwood Bats sees one token sacrificed (one life), and no token created by the spreading."""
    s = build(cards, "Mirkwood Bats")
    bats = next(c for c in s.state.cards.values() if c.name == "Mirkwood Bats")
    act(s, "p1", type="move", card_ids=[bats.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="create_token", player="p1", token=TREASURE)
    (stack,) = on_field(s, "Treasure")
    act(s, "p1", type="stack_adjust", card_id=stack.id, delta=2)  # "Treasure ×3" (as an older save may hold it)
    assert s.state.cards[stack.id].quantity == 3
    s = saved(s)
    before = life(s, "p2")
    act(s, "p1", type="activate_ability", card_id=stack.id, ability=0, mana_choice="B")
    settle(s)
    treasures = on_field(s, "Treasure")
    assert len(treasures) == 2 and all(t.quantity == 1 and not t.tapped for t in treasures)
    assert mana_pool(s) == {"B": 1}
    assert life(s, "p2") == before - 1
    replay_matches(s)
    saved(s)


def test_spread_tokens_are_counted_one_each(cards):
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token=GOBLIN)
    (stack,) = on_field(s, "Goblin")
    act(s, "p1", type="stack_adjust", card_id=stack.id, delta=2)
    source = boss(s)
    activate(s, source)  # the stack was spread first: X is 3
    goblins = on_field(s, "Goblin")
    assert len(goblins) == 6 and all(g.quantity == 1 for g in goblins)
    rules = s.state.rules
    spread = [g for g in goblins if g.id != stack.id][:2]
    for g in spread:
        assert rules.controlled_since[g.id] == rules.controlled_since[stack.id]
    replay_matches(s)
    saved(s)


def test_a_stack_from_the_sandbox_attacks_as_separate_creatures(cards):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token={**GOBLIN, "power": "2", "toughness": "2"}, count=3, stacked=True)
    (stack,) = on_field(s, "Goblin")
    assert stack.quantity == 3
    automate(s)  # automation on (the reconciliation spreads the stack): Alice declares attackers
    goblins = on_field(s, "Goblin")
    assert len(goblins) == 3 and all(g.quantity == 1 for g in goblins)
    d = s.state.rules.decision
    assert d.kind == "declare_attackers" and {f"a:{g.id}" for g in goblins} <= {o.id for o in d.options}
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": g.id, "target": "p2"} for g in goblins])
    settle(s)
    assert life(s, "p2") == 40 - 6
    replay_matches(s)
    saved(s)


def test_splitting_a_stack_by_hand_with_automation_on_is_no_new_token(cards):
    """Split one off, then spread the rest, by hand: the new objects are the tokens that were there (no event, same control age)."""
    s = build(cards, "Mirkwood Bats")
    bats = next(c for c in s.state.cards.values() if c.name == "Mirkwood Bats")
    act(s, "p1", type="move", card_ids=[bats.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="create_token", player="p1", token=GOBLIN)
    (stack,) = on_field(s, "Goblin")
    act(s, "p1", type="stack_adjust", card_id=stack.id, delta=3)
    act(s, "p1", type="split_stack", card_id=stack.id, count=1)
    act(s, "p1", type="expand_stack", card_id=stack.id)
    goblins = on_field(s, "Goblin")
    assert len(goblins) == 4 and all(g.quantity == 1 for g in goblins)
    rules = s.state.rules
    new = {g.id for g in goblins} - {stack.id}
    assert not [e for e in rules.events if e.card in new]
    assert all(rules.controlled_since[g] == rules.controlled_since[stack.id] for g in new)
    before = life(s, "p2")
    act(s, "p1", type="pass_priority")  # the engine acts: nothing was created, nothing triggers
    settle(s)
    assert life(s, "p2") == before
    replay_matches(s)
    saved(s)


def test_tokens_spread_on_a_later_turn_keep_the_stacks_control_age(cards):
    """302.6: a stack made on turn 1 (automation paused) is spread when automation resumes on turn 3; every token has been under
    Alice's control since turn 1, so each can attack."""
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token={**GOBLIN, "power": "2", "toughness": "2"})
    (stack,) = on_field(s, "Goblin")
    act(s, "p1", type="configure", automation_paused=True)
    act(s, "p1", type="stack_adjust", card_id=stack.id, delta=2)
    act(s, "p1", type="next_turn")
    act(s, "p2", type="next_turn")
    assert (s.state.turn.number, s.state.turn.active_player) == (3, "p1")
    s = saved(s)
    act(s, "p1", type="configure", automation_paused=False)  # resuming reconciles: the stack is spread
    goblins = on_field(s, "Goblin")
    assert len(goblins) == 3 and {s.state.rules.controlled_since[g.id].turn for g in goblins} == {1}
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert {f"a:{g.id}" for g in goblins} <= {o.id for o in s.state.rules.decision.options}
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": g.id, "target": "p2"} for g in goblins])
    settle(s)
    assert life(s, "p2") == 40 - 6
    replay_matches(s)
    saved(s)
