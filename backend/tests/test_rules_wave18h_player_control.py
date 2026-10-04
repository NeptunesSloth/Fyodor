"""Wave 18H: controlling another player (CR 723; app/game/control.py, app/rules/player_control.py).

"You control target player during that player's next turn." (Worst Fears, Mindslaver, Sorin Markov's -7) and Emrakul's
"you gain control of target opponent during that player's next turn. After that turn, that player takes an extra turn."
The controller makes the controlled player's choices (723.5), sees what that player sees only while controlling (723.4),
the player still concedes for themselves (723.6), the last effect wins (723.1a), objects keep their controllers (723.3).
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.control import controller_of
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.game.views import build_view
from app.game.visibility import SPECTATOR
from app.rules import coverage, scripts
from app.rules.view import rules_view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import creature, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card("Worst Fears", set_code="tst", number="C00", mana_cost="{7}{B}{B}", cmc=9.0, type_line="Sorcery", oracle_text="You control target player during that player's next turn. Exile Worst Fears. (You see all cards that player could see and make all decisions for them.)", colors=["B"], color_identity=["B"]),  # noqa: E501
    card("Mindslaver", set_code="tst", number="C01", mana_cost="{6}", cmc=6.0, type_line="Legendary Artifact", oracle_text="{4}, {T}, Sacrifice Mindslaver: You control target player during that player's next turn. (You see all cards that player could see and make all decisions for them.)"),  # noqa: E501
    card("Emrakul, the Promised End", set_code="tst", number="C02", mana_cost="{13}", cmc=13.0, type_line="Legendary Creature — Eldrazi", power="13", toughness="13", oracle_text="This spell costs {1} less to cast for each card type among cards in your graveyard.\nWhen you cast this spell, you gain control of target opponent during that player's next turn. After that turn, that player takes an extra turn.\nFlying, trample, protection from instants", keywords=["Flying", "Trample"]),  # noqa: E501
    card("Hidden Gem", set_code="tst", number="C03", mana_cost="{1}", cmc=1.0, type_line="Artifact", oracle_text="{T}: Add {C}."),
]
FULL = ["Worst Fears", "Mindslaver", "Emrakul, the Promised End"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wordings():
    assert scripts.parse_effects("You control target player during that player's next turn.") == (
        [{"do": "control_player", "who": "target"}], "player", False)
    assert scripts.parse_effects("You control target opponent during their next turn.")[1] == "opponent"
    for text in ("You control target player during that player's next combat phase.",
                 "You control each opponent during their next turn."):
        assert scripts.parse_effects(text) is None, text


def table(cards, players=3):
    fears = [(2, "Worst Fears")]
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*fears, (1, "Mindslaver"), (1, "Emrakul, the Promised End"), (9, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Hidden Gem"), (10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(1, "Worst Fears"), (1, "Mindslaver"), (10, "Island")]))][:players]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def cast_on(s, name, target, pid="p1"):
    c = to_hand(s, name, pid)
    mana(s, pid, B=2, C=10)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    drive(s, until=lambda s: not s.state.zones.get("stack"))
    return c


def drive(s, until, limit=300):
    """Play on the way the table would: whoever makes the choice (the decider, 723.5) answers it plainly."""
    for _ in range(limit):
        if until(s):
            return
        r = s.state.rules
        d = r.decision
        if d is None:
            who = controller_of(s.state, r.priority)
            act(s, who, type="pass_priority")
        else:
            who = d.decider or d.player
            if d.kind == "declare_attackers":
                act(s, who, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, who, type="declare_blockers", blocks=[])
            else:
                act(s, who, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never got there")


def seen_by(s, viewer):
    v = build_view(s.state, viewer)
    return {c["id"]: c for c in v["cards"].values() if not c.get("hidden")}


def bobs_turn(s):
    drive(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")


def test_worst_fears_pending_then_active_only_for_that_players_turn(cards):
    s = table(cards)
    gem = to_hand(s, "Hidden Gem", "p2")
    fears = cast_on(s, "Worst Fears", "p2")
    assert [(c.controlled, c.controller, c.status) for c in s.state.rules.player_control] == [("p2", "p1", "pending")]
    assert [s.state.cards[c].name for c in s.state.zones["p1:exile"]] == ["Worst Fears"] and fears.id in s.state.cards
    # Before Bob's turn nothing is shared: Alice doesn't see Bob's hand
    assert gem.id not in seen_by(s, "p1")
    bobs_turn(s)
    assert [(c.status) for c in s.state.rules.player_control] == ["active"]
    assert s.state.turn.active_player == "p2"  # 723.3: still the active player
    assert gem.id in seen_by(s, "p1") and gem.id in seen_by(s, "p2")  # 723.4
    assert gem.id not in seen_by(s, "p3") and gem.id not in seen_by(s, SPECTATOR)
    assert rules_view(s.state, "p1", s.cards)["control"] == [{"controlled": "p2", "controller": "p1", "status": "active"}]
    # ... the turn after it, the information stops flowing and Bob decides again
    drive(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.rules.player_control == []
    assert gem.id in seen_by(s, "p2") and gem.id not in seen_by(s, "p1")
    roundtrip(s)


def test_the_controller_acts_for_the_controlled_player_and_nobody_else_can(cards):
    s = table(cards)
    gem = to_hand(s, "Hidden Gem", "p2")
    island = to_hand(s, "Island", "p2")
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    assert s.state.rules.priority == "p2"
    with pytest.raises(ActionError, match="controlling you"):
        act(s, "p2", type="play_land", card_id=island.id)  # Bob can't play his own land: Alice makes his choices
    with pytest.raises(ActionError):
        act(s, "p3", type="play_land", card_id=island.id)  # nor can a third player
    act(s, "p1", type="play_land", card_id=island.id)  # Alice plays Bob's land for him (723.5, 723.5a: from his hand)
    assert s.state.cards[island.id].zone == "p2:battlefield" and s.state.cards[island.id].controller == "p2"
    # her own cards stay hers (723.3) and Bob's resources pay for what he casts (723.5a)
    mana(s, "p2", C=1)
    act(s, "p1", type="cast_spell", card_id=gem.id)
    drive(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[gem.id].zone == "p2:battlefield"
    own = to_hand(s, "Worst Fears", "p1")
    with pytest.raises(ActionError):  # 723.5a: Alice acts as Bob now and can't cast her own cards for him
        act(s, "p1", type="cast_spell", card_id=own.id, targets=["p3"])
    roundtrip(s)


def test_the_combat_decisions_are_the_controllers_and_stay_private_from_everyone_else(cards):
    s = table(cards)
    creature(s, "p2", "Ox")
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    drive(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    d = s.state.rules.decision
    assert d.player == "p2" and d.decider == "p1"
    assert rules_view(s.state, "p1", s.cards)["decision"]["kind"] == "declare_attackers"
    assert rules_view(s.state, "p1", s.cards)["decision"]["for_player"] == "p2"
    for who in ("p2", "p3", SPECTATOR):
        v = rules_view(s.state, who, s.cards)["decision"]
        assert v["kind"] == "declare_attackers" and "options" not in v and "for_player" not in v  # public: combat is declared
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[])
    roundtrip(s)


def test_a_private_choice_goes_only_to_the_controller(cards):
    s = table(cards)
    for c in [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island"][:9]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})  # more than seven cards: Bob discards at cleanup
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    drive(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind not in ("declare_attackers", "declare_blockers"))
    d = s.state.rules.decision
    assert d.player == "p2" and d.decider == "p1"
    mine = rules_view(s.state, "p1", s.cards)["decision"]
    assert mine["options"] and mine["for_player"] == "p2"
    for who in ("p2", "p3", SPECTATOR):
        v = rules_view(s.state, who, s.cards)["decision"]
        assert v["kind"] == "waiting" and not v.get("options") and v["source_id"] is None
        assert v["prompt"] == "Bob is making a choice"
    with pytest.raises(ActionError, match="making this choice for you"):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id], remember="yes_this_turn")
    roundtrip(s)


def test_the_last_effect_wins(cards):
    s = table(cards)
    slaver = to_hand(s, "Mindslaver", "p3")
    act(s, "p3", type="move", card_ids=[slaver.id], to={"player": "p3", "zone": "battlefield"})
    fears = to_hand(s, "Worst Fears", "p1")
    mana(s, "p1", B=2, C=10)
    mana(s, "p3", C=4)
    act(s, "p1", type="cast_spell", card_id=fears.id, targets=["p2"])
    for _ in range(5):
        if s.state.rules.priority == "p3":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p3", type="activate_ability", card_id=slaver.id, ability=0, targets=["p2"])  # in response: resolves first
    drive(s, lambda s: not s.state.zones.get("stack"))
    # Carol's resolved first, Alice's was created last: 723.1a, hers is the one that works
    assert [(c.controlled, c.controller, c.status) for c in s.state.rules.player_control] == [("p2", "p1", "pending")]
    assert s.state.cards[slaver.id].zone == "p3:graveyard"
    bobs_turn(s)
    assert controller_of(s.state, "p2") == "p1"
    roundtrip(s)


def test_a_player_always_concedes_for_themselves(cards):
    s = table(cards)
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    act(s, "p2", type="concede")  # 723.6
    assert "p2" in s.state.rules.conceded
    assert s.state.rules.player_control == [] or all(c.controlled != "p2" for c in s.state.rules.player_control if c.status == "pending")
    roundtrip(s)


def test_emrakul_gives_control_then_an_extra_turn(cards):
    s = table(cards, players=2)
    emrakul = to_hand(s, "Emrakul, the Promised End", "p1")
    mana(s, "p1", C=13)
    act(s, "p1", type="cast_spell", card_id=emrakul.id, targets=["p2"])
    drive(s, lambda s: not s.state.zones.get("stack"))
    assert [(c.controlled, c.controller, c.extra_after) for c in s.state.rules.player_control] == [("p2", "p1", 1)]
    gem = to_hand(s, "Hidden Gem", "p2")
    bobs_turn(s)
    assert gem.id in seen_by(s, "p1")
    assert s.state.rules.extra_turns == [{"player": "p2", "label": "Emrakul, the Promised End"}]
    drive(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.turn.active_player == "p2"  # the extra turn, not controlled
    assert s.state.rules.player_control == [] and gem.id not in seen_by(s, "p1")
    drive(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert s.state.turn.active_player == "p1"
    roundtrip(s)


def test_mindslaver_is_sacrificed_to_control_a_player(cards):
    s = table(cards, players=2)
    slaver = to_hand(s, "Mindslaver", "p1")
    act(s, "p1", type="move", card_ids=[slaver.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=slaver.id, ability=0, targets=["p2"])
    drive(s, lambda s: not s.state.zones.get("stack"))
    assert [(c.controlled, c.controller) for c in s.state.rules.player_control] == [("p2", "p1")]
    assert s.state.cards[slaver.id].zone == "p1:graveyard"
    roundtrip(s)


def test_cards_outside_the_game_stay_the_controlled_players_alone(cards):
    s = table(cards, players=2)
    side = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island")
    act(s, "p2", type="move", card_ids=[side.id], to={"player": "p2", "zone": "sideboard"})
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    assert s.state.cards[side.id].zone == "p2:sideboard"
    assert side.id in seen_by(s, "p2") and side.id not in seen_by(s, "p1")  # 723.4: only cards in the game are shared
