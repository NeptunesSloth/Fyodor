"""Regression tests for rules simplifications replaced by the real rule (batch 3).

- 800.4j: a turn whose active player left goes on to its end without an active player.
- 800.4a: objects the leaver still controls are exiled; a control-changing effect just ends.
- 104.3a: a player can concede at any time (another player's priority or decision, their own
  decision, mid-combat); the others go on.
- 610.3d: "until ~ leaves" returns after simultaneous departures happen at once.
- 701.21a: "sacrifice ~ unless you pay" doesn't sacrifice what its controller no longer controls.
- 701.23 (Path to Exile ruling): a player who declines to search doesn't shuffle.
- 903.9b: a commander's owner is asked before it would go to a hand or library.
- "may" memory: remembered answers belong to one card's ability, not a name.
- 120 / 608.2: "each creature and each player" is one simultaneous damage event.
"""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import ch, named, token
from tests.test_rules_delayed import activate, on_battlefield, reloaded, rules
from tests.test_rules_effects import replay_matches
from tests.test_rules_suspend import until


def build3(cards, *names):
    """Alice (p1, active, in her main phase), Bob (p2) and Carol (p3)."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (9, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob),
                                     PlayerSetup("Carol", cards=carol)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def life(s, pid):
    return s.state.players[pid].life


def log_text(s, pid="p1"):
    import json

    return json.dumps(s.view(pid)["log"])


def settle(s, limit=30):
    """Answer every decision with its first options and pass until the stack is empty."""
    for _ in range(limit):
        d = rules(s).decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:max(d.min_choices, 1)]
                if d.kind != "order" else [o.id for o in d.options])
        elif s.state.zones.get("stack"):
            act(s, rules(s).priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- 800.4j: the turn goes on without its active player ------------------------------------------------
END_STEP_GAIN = "At the beginning of each end step, you gain 1 life."


def test_the_turn_continues_to_its_end_step_after_the_active_player_concedes(cards):
    s = build3(cards)
    token(s, "p3", "Carol's Keeper", "1/1", text=END_STEP_GAIN)
    before = life(s, "p3")
    turn = s.state.turn.number
    act(s, "p1", type="concede")  # in Alice's own main phase
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    # the end step of Alice's turn still happened (800.4j): its "at the beginning of" trigger did
    assert life(s, "p3") >= before + 1
    assert s.state.turn.active_player == "p2"  # 800.4k: then the next player's turn
    replay_matches(s)


def test_a_departed_active_player_neither_draws_nor_attacks(cards):
    s = build3(cards)
    act(s, "p2", type="set_prefs", stops_my_turn=["upkeep"], response="on")
    act(s, "p3", type="set_prefs", stops_their_turn=["draw", "main1", "end"], response="on")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "upkeep"
          and rules(s).priority == "p2", limit=120)
    hand = list(s.state.zones["p2:hand"])
    library = list(s.state.zones["p2:library"])
    turn = s.state.turn.number
    act(s, "p2", type="concede")  # during Bob's own upkeep
    assert s.state.turn.active_player == "p2" and s.state.turn.number == turn  # the turn isn't over …
    assert rules(s).priority == "p3"  # (800.4j: the next player instead of the active player)
    seen = set()

    def watch(s):
        seen.add(s.state.turn.phase)
        assert rules(s).decision is None or rules(s).decision.player != "p2"
        return s.state.turn.number > turn

    until(s, watch, limit=80)
    assert {"draw", "main1", "end"} <= seen  # … it went on step by step (800.4j)
    assert s.state.zones["p2:hand"] == hand and s.state.zones["p2:library"] == library  # no draw (504.1)
    assert s.state.turn.active_player == "p3"
    replay_matches(s)


# -- 800.4a: what the leaver still controls is exiled ---------------------------------------------------
def test_a_reanimated_card_of_another_player_is_exiled_when_its_controller_leaves(cards):
    # "Return target creature card from a graveyard to the battlefield under your control": no
    # control-changing effect to end — the card is exiled (800.4a), not returned to its owner.
    s = build3(cards)
    bears = named(s, "Grizzly Bears")  # Bob's
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[bears.id].owner == "p2"
    act(s, "p1", type="concede")
    assert s.state.cards[bears.id].zone == "p2:exile"
    replay_matches(s)


def test_a_stolen_permanent_returns_to_its_owner_when_the_thief_leaves(cards):
    # Threaten-style (done by hand: set_controller): the control-changing effect ends (800.4a).
    s = build3(cards)
    bears = named(s, "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    act(s, "p1", type="concede")
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[bears.id].controller == "p2"
    replay_matches(s)


# -- 104.3a: concede at any time -------------------------------------------------------------------------
def test_concede_while_another_player_has_priority(cards):
    s = build3(cards)
    assert rules(s).priority == "p1"
    act(s, "p3", type="concede")
    assert "p3" in rules(s).conceded
    assert rules(s).priority == "p1" and rules(s).decision is None
    replay_matches(s)


def test_concede_with_priority_passes_it_on(cards):
    s = build3(cards)
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p2", type="set_prefs", response="on", full_control=True)
    act(s, "p3", type="set_prefs", response="on", full_control=True)
    src = token(s, "p1", "Pinger", "1/1", text="{1}: You gain 1 life.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    if rules(s).priority == "p1":
        act(s, "p1", type="pass_priority")
    assert rules(s).priority == "p2"
    act(s, "p2", type="concede")  # 800.4a: priority passes to the next player still in the game
    assert rules(s).priority == "p3" and s.state.zones.get("stack")
    replay_matches(s)


def test_concede_during_another_players_decision_keeps_it(cards):
    s = build3(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    src = token(s, "p1", "Looter", "1/1", text="{1}: Scry 2.")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    until(s, lambda s: rules(s).decision is not None, limit=10)
    d = rules(s).decision
    assert d.player == "p1"
    act(s, "p3", type="concede")
    assert rules(s).decision is not None and rules(s).decision.id == d.id  # Alice still decides
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    replay_matches(s)


def test_concede_during_own_decision_mid_resolution_lets_the_resolution_go_on(cards):
    # Alice's ability: each opponent discards a card (Bob, then Carol: APNAP), then Alice gains 2
    # life. Bob concedes while choosing: his choice isn't made (800.4f-h), Carol still discards and
    # the rest of Alice's ability still resolves.
    s = build3(cards)
    for pid, name in (("p2", "Island"), ("p3", "Mountain")):
        ids = [c.id for c in s.state.cards.values() if c.owner == pid and c.name == name][:2]
        act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "hand"})
    src = token(s, "p1", "Mindripper", "1/1", text="{1}: Each opponent discards a card. You gain 2 life.")
    before, carol_hand = life(s, "p1"), len(s.state.zones["p3:hand"])
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    until(s, lambda s: rules(s).decision is not None, limit=20)
    assert rules(s).decision.player == "p2"
    act(s, "p2", type="concede")
    d = rules(s).decision
    assert d is not None and d.player == "p3"  # Carol's choice is still asked
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert len(s.state.zones["p3:hand"]) == carol_hand - 1
    assert life(s, "p1") == before + 2
    replay_matches(s)


def test_the_active_player_concedes_while_declaring_attackers(cards):
    s = build3(cards)
    token(s, "p1", "Alice's Bear", "2/2")
    until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_attackers", limit=40)
    turn = s.state.turn.number
    act(s, "p1", type="concede")  # mid-combat, with her own decision pending
    assert rules(s).decision is None or rules(s).decision.player != "p1"
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    assert s.state.turn.active_player == "p2"
    replay_matches(s)


def test_a_defender_concedes_while_declaring_blockers(cards):
    s = build3(cards)
    bear = token(s, "p1", "Alice's Bear", "2/2")
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p1")  # (no-op: still Alice's)
    token(s, "p2", "Bob's Wall", "0/4")
    token(s, "p3", "Carol's Wall", "0/4")
    # (not summoning sick: it has been under Alice's control since her turn began)
    rules(s).controlled_since[bear.id].turn = 0
    until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_attackers", limit=40)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_blockers", limit=10)
    assert rules(s).decision.player == "p2"
    act(s, "p2", type="concede")
    # the creature attacking Bob is removed from combat (506.4, 800.4a); nobody is left blocking
    assert rules(s).decision is None or rules(s).decision.player != "p2"
    assert s.state.cards[bear.id].attacking is None
    until(s, lambda s: s.state.turn.phase == "main2", limit=30)
    replay_matches(s)


def test_concede_while_paused(cards):
    s = build3(cards)
    act(s, "p1", type="configure", automation_paused=True)
    step = (s.state.turn.number, s.state.turn.phase)
    act(s, "p2", type="concede")
    assert "p2" in rules(s).conceded and rules(s).paused
    assert (s.state.turn.number, s.state.turn.phase) == step  # nothing else ran while paused
    replay_matches(s)


def test_cannot_concede_twice(cards):
    import pytest

    from app.game.errors import ActionError

    s = build3(cards)
    act(s, "p2", type="concede")
    with pytest.raises(ActionError):
        act(s, "p2", type="concede")


def test_concede_survives_reload(cards):
    s = build3(cards)
    act(s, "p1", type="concede")
    s2 = reloaded(s)
    assert s2.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    assert ch(s2, on_battlefield(s2, "Grizzly Bears", "p2")).pt == (2, 2)


# -- 610.3d: simultaneous returns ------------------------------------------------------------------------
JAILER = "{1}: Exile target artifact or creature an opponent controls until ~ leaves the battlefield."


def two_player(cards, alice_cards=(), bob_cards=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice_cards), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob_cards), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def test_returns_after_a_board_wipe_are_one_simultaneous_entry(cards, monkeypatch):
    from app.rules import attachments

    s = two_player(cards, bob_cards=("Grizzly Bears", "Llanowar Elves"))
    victims = [named(s, "Grizzly Bears"), named(s, "Llanowar Elves")]
    for i, victim in enumerate(victims):
        act(s, "p2", type="move", card_ids=[victim.id], to={"player": "p2", "zone": "battlefield"})
        jailer = token(s, "p1", f"Jailer {i}", "1/1", text=JAILER)
        activate(s, jailer, targets=[victim.id])
        assert s.state.cards[victim.id].zone == "p2:exile"
    calls = []
    real = attachments.enter

    def spy(plan, entries, ctx, **kw):
        calls.append(len(entries))
        return real(plan, entries, ctx, **kw)

    monkeypatch.setattr(attachments, "enter", spy)
    wipe = token(s, "p1", "Wiper", "1/1", text="{1}: Destroy all creatures.")
    activate(s, wipe)
    settle(s)
    assert all(s.state.cards[v.id].zone == "p2:battlefield" for v in victims)
    assert 2 in calls and 1 not in calls  # both in one entry (610.3d), not one source at a time
    replay_matches(s)


# -- 701.21a: "sacrifice ~ unless you pay" checks who controls it ------------------------------------------
def test_sacrifice_unless_you_pay_does_nothing_after_a_control_change(cards):
    # Phantasmal Forces: "At the beginning of your upkeep, sacrifice this creature unless you pay
    # {U}." Bob steals it in response: Alice can't sacrifice what she doesn't control (701.21a); she may still pay (118.12).
    s = two_player(cards, alice_cards=("Phantasmal Forces",))
    forces = on_battlefield(s, "Phantasmal Forces")
    act(s, "p1", type="set_prefs", full_control=True)
    for _ in range(200):
        if s.state.turn.phase == "upkeep" and s.state.turn.active_player == "p1" and s.state.zones.get("stack"):
            break
        d = rules(s).decision
        if d is not None:
            assert (d.resume or {}).get("step") != "pay_or_sacrifice"
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:d.min_choices])
        else:
            act(s, rules(s).priority, type="pass_priority")
    act(s, "p2", type="set_controller", card_ids=[forces.id], player="p2")  # (Threaten-style, by hand)
    for _ in range(10):
        if not s.state.zones.get("stack"):
            break
        d = rules(s).decision
        if d is not None and (d.resume or {}).get("step") == "pay_or_sacrifice":  # 118.12: Alice may still pay; nothing is sacrificed either way
            assert d.player == "p1" and [o.label for o in d.options][1] == "Don't pay"
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
            continue
        act(s, rules(s).priority, type="pass_priority")
    assert s.state.cards[forces.id].zone == "p2:battlefield"
    replay_matches(s)


# -- Path to Exile: no search, no shuffle -----------------------------------------------------------------
PATH = ("{1}: Exile target creature. Its controller may search their library for a basic land card, put that card "
        "onto the battlefield tapped, then shuffle.")


def test_declining_a_may_search_does_not_shuffle(cards):
    # Path to Exile ruling: "If that player doesn't [search], the player won't shuffle their library."
    s = two_player(cards)
    bears = token(s, "p2", "Bob's Brute", "3/3")
    library = list(s.state.zones["p2:library"])
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=token(s, "p1", "Pather", "1/1", text=PATH).id, ability=0,
        targets=[bears.id])
    until(s, lambda s: rules(s).decision is not None, limit=10)
    d = rules(s).decision
    assert d.player == "p2" and d.kind == "confirm" and [o.id for o in d.options] == ["yes", "no"]
    assert "options" not in s.view("p1")["rules"]["decision"]  # (Bob's choice, private)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert s.state.zones["p2:library"] == library  # same cards, same ids, same order: never shuffled
    replay_matches(s)


def test_searching_and_finding_nothing_still_shuffles(cards):
    s = two_player(cards)
    brute = token(s, "p2", "Bob's Brute", "3/3")
    library = list(s.state.zones["p2:library"])
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=token(s, "p1", "Pather", "1/1", text=PATH).id, ability=0,
        targets=[brute.id])
    until(s, lambda s: rules(s).decision is not None, limit=10)
    act(s, "p2", type="choose", decision_id=rules(s).decision.id, option_ids=["yes"])
    d = rules(s).decision
    assert d.kind == "choose_cards" and d.min_choices == 0
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[])  # 701.23b: finds nothing
    settle(s)
    assert s.state.zones["p2:library"] != library  # shuffled (new hidden ids)
    replay_matches(s)


# -- "may" memory: one card's ability, not a name ---------------------------------------------------------
WARDEN = "Whenever another creature enters, you may gain 1 life."


def test_a_remembered_may_answer_belongs_to_one_card_not_its_name(cards):
    s = two_player(cards)
    act(s, "p1", type="set_prefs", auto_order_identical_triggers=True)
    first, second = token(s, "p1", "Warden", "1/1", text=WARDEN), None
    act(s, "p1", type="create_token", player="p1", token={"name": "Warden", "type_line": "Token Creature — Test",
                                                         "power": "1", "toughness": "1", "text": WARDEN})
    second = next(c for c in s.state.cards.values() if c.name == "Warden" and c.id != first.id)
    settle(s)
    # a third creature enters: both Wardens trigger; "yes this turn" for one doesn't answer the other
    asked = []
    maker = token(s, "p1", "Maker", "0/1", text="{1}: Create a 1/1 white Soldier creature token.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=maker.id, ability=0)
    for _ in range(30):
        d = rules(s).decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, rules(s).priority, type="pass_priority")
        elif d.kind == "confirm" and d.memory_key and d.memory_key.startswith("may:"):
            asked.append(d.memory_key)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
        else:
            act(s, d.player, type="choose", decision_id=d.id,
                option_ids=[o.id for o in d.options][:max(d.min_choices, 1)] if d.kind != "order" else [o.id for o in d.options])
    assert len(asked) == 2 and len(set(asked)) == 2
    assert {first.id, second.id} == {k.split(":")[1] for k in asked}
    replay_matches(s)


def test_a_remembered_may_answer_still_answers_the_same_cards_ability(cards):
    s = two_player(cards)
    token(s, "p1", "Warden", "1/1", text=WARDEN)
    maker = token(s, "p1", "Maker", "0/1", text="{1}: Create a 1/1 white Soldier creature token.")
    before = life(s, "p1")
    asked = 0
    for _ in range(2):
        act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
        act(s, "p1", type="activate_ability", card_id=maker.id, ability=0)
        for _ in range(10):
            d = rules(s).decision
            if d is None and not s.state.zones.get("stack"):
                break
            if d is None:
                act(s, rules(s).priority, type="pass_priority")
            else:
                asked += 1
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
    assert asked == 1 and life(s, "p1") == before + 2  # the second time: remembered, no prompt
    replay_matches(s)


# -- 120 / 608.2: "each creature and each player" is one damage event ----------------------------------------
PESTILENCE = "{1}: Pestilence deals 1 damage to each creature and each player."


def test_damage_to_each_creature_and_each_player_is_one_simultaneous_event(cards, monkeypatch):
    from app.rules import effects

    s = two_player(cards)
    bear = token(s, "p2", "Bob's Bear", "2/2")
    pest = token(s, "p1", "Pestilence", "0/3", text=PESTILENCE)
    batches = []
    real = effects._deal

    def spy(plan, ctx, hits, e=None, **kw):
        batches.append(sorted(key for _, key, _ in hits))
        return real(plan, ctx, hits, e, **kw)

    monkeypatch.setattr(effects, "_deal", spy)
    life1, life2 = life(s, "p1"), life(s, "p2")
    activate(s, pest)
    settle(s)
    assert batches == [sorted([bear.id, pest.id, "p1", "p2"])]  # one batch: creatures and players together
    assert life(s, "p1") == life1 - 1 and life(s, "p2") == life2 - 1
    assert s.state.cards[bear.id].damage == 1 and s.state.cards[pest.id].damage == 1
    replay_matches(s)


def test_commander_owner_is_asked_before_it_would_go_to_a_hand(cards):
    # 903.9b: "… its owner may put it into the command zone instead" — a replacement effect: the
    # commander never touches the hand (no "put into a hand" event, nothing revealed by a hand).
    s = two_player(cards)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    bear = token(s, "p1", "Alice's Bear", "2/2")
    src = token(s, "p1", "Evacuator", "0/1", text="{1}: Return all creatures to their owners' hands.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    until(s, lambda s: rules(s).decision is not None, limit=10)
    d = rules(s).decision
    assert d.player == "p1" and d.resume["step"] == "commander_first"
    assert s.state.cards[krenko.id].zone == "p1:battlefield"  # still there while its owner decides
    assert "options" not in s.view("p2")["rules"]["decision"]  # (Alice's decision)
    s2 = reloaded(s)  # the question survives a reload
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s2)
    assert s2.state.cards[krenko.id].zone == "p1:command"
    assert bear.id not in s2.state.cards  # (the token went to a hand and ceased to exist)
    assert not [e for e in rules(s2).events if e.card == krenko.id and (e.to_zone or "").endswith(":hand")]
    replay_matches(s2)


def test_two_damage_sentences_stay_two_events(cards, monkeypatch):
    from app.rules import effects

    s = two_player(cards)
    token(s, "p2", "Bob's Bear", "2/2")
    pest = token(s, "p1", "Pinger", "0/3", text="{1}: Pinger deals 1 damage to each creature. Pinger deals 1 damage to each player.")
    batches = []
    real = effects._deal
    monkeypatch.setattr(effects, "_deal", lambda plan, ctx, hits, e=None, **kw: (batches.append(len(hits)),
                                                                                 real(plan, ctx, hits, e, **kw))[1])
    activate(s, pest)
    settle(s)
    assert batches == [2, 2]
