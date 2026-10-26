"""Wave 110D: opponent's-choice targets at a three-player table (real Oracle text, tests/fixtures/wave110d_cards.json).

* 115.1, 601.2c: "target creature of an opponent's choice" - the caster picks which opponent chooses, that opponent picks among ITS OWN creatures (Evangelize).
* 603.3d: a trigger's controller picks the opponent (Mausoleum Turnkey, Cuombajj Witches) when there are several.
"""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import put, to_hand
from tests.wave110d_kit import ability, card_db, check, cost, mana, now, put_new, settle, to_phase  # noqa: F401


def three(cards, mine=(), p2=(), p3=()):
    def d(cmdr, names, basic):
        return deck(cards, cmdr, [*((1, n) for n in names), (10, basic)])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=d("Krenko, Mob Boss", mine, "Forest")),
                                     PlayerSetup("Bob", cards=d("Atraxa, Praetors' Voice", p2, "Island")),
                                     PlayerSetup("Carol", cards=d("Atraxa, Praetors' Voice", p3, "Island"))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_evangelize_picks_opponent_then_their_own_creature(cards):
    s = three(cards, ["Evangelize"], ["Grizzly Bears"], ["Llanowar Elves"])
    b, e = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p3")
    ev = to_hand(s, "Evangelize")
    mana(s, "p1", **cost("Evangelize"))
    act(s, "p1", type="cast_spell", card_id=ev.id, sources=[])
    d = s.state.rules.decision
    assert d.player == "p1" and {"p2", "p3"} <= {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d.player == "p3" and {o.id for o in d.options} == {e.id}  # p3 sees only its own creature
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[e.id])
    settle(s)
    assert now(s, e).controller == "p1" and now(s, b).controller == "p2"
    check(s)


def test_turnkey_trigger_opponent_choice_with_two_opponents(cards):
    s = three(cards, ["Mausoleum Turnkey", "Grizzly Bears", "Llanowar Elves"])
    a, c = to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[a.id, c.id], to={"player": "p1", "zone": "graveyard"})
    tk = to_hand(s, "Mausoleum Turnkey")
    mana(s, "p1", **cost("Mausoleum Turnkey"))
    act(s, "p1", type="cast_spell", card_id=tk.id, sources=[])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.player != "p1":
            break
        if d is not None and "p3" in {o.id for o in d.options}:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
        elif d is not None:
            raise AssertionError(d.prompt)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and {o.id for o in d.options} == {a.id, c.id}
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[c.id])
    settle(s)
    assert now(s, c).zone == "p1:hand"
    check(s)


def test_witches_second_damage_chosen_by_picked_opponent(cards):
    s = three(cards, ["Cuombajj Witches", "Grizzly Bears"], ["Grizzly Bears"])
    w = put(s, "Cuombajj Witches")  # (in the opening hand)
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=ability(s, w, "{T}"), sources=[])
    log = []
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        log.append((d.player, d.kind, sorted(o.id for o in d.options)[:4]))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if d.player == "p1" and "p2" in {o.id for o in d.options} else ["p1"] if "p1" in {o.id for o in d.options} else [d.options[0].id])
    assert [x[0] for x in log] == ["p1", "p1", "p2"] and log[1][2] == ["p2", "p3"]  # my target, then which opponent picks, then that opponent's pick
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [39, 39, 40]
    settle(s)
    check(s)
