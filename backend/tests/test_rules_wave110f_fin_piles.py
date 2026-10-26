"""Wave 110F final pass, on real Oracle text (3-player table). Every scenario checks the replay and a save and a load.

* 802.2, 700.3: Stand or Fall: every opponent is a defending player at the beginning of combat; the caster separates each one's creatures into two piles, that
  player chooses one, and only creatures in the chosen piles can block this turn.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, until
from tests.wave9c_kit import put
from tests.wave36a_kit import ready
from tests.wave53d_kit import EXTRA, check, open_repo, table

STAND = "Stand or Fall"
EXTRA.append(card(STAND, set_code="w110f", number="S1", mana_cost="{3}{R}", cmc=4.0, type_line="Enchantment", colors=["R"], color_identity=["R"],
                  oracle_text="At the beginning of combat on your turn, for each defending player, separate all creatures that player controls into two piles and that player chooses one. "
                              "Only creatures in the chosen piles can block this turn."))


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def test_stand_or_fall_is_full(cards):
    assert coverage.of_card_data(cards.resolve(STAND)).level == "FULL"


def _decision(s, pid, kind):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.kind == kind, (d and (d.player, d.kind), pid, kind)
    return d


def _split(s, pid, first):
    d = _decision(s, pid, "choose_cards")
    act(s, pid, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if any(o.label.startswith(f) for f in first)])


def _pile(s, pid, number):
    d = _decision(s, pid, "choose_one")
    act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(f"Pile {number}"))])


def _setup(cards):
    s = table(cards, [STAND], players=3)
    put(s, STAND)
    hit = creature(s, "p1", "Alice Hit")
    ready(s, "Alice Hit")
    bob = [creature(s, "p2", n) for n in ("Bob One", "Bob Two")]
    carol = [creature(s, "p3", n) for n in ("Carol One", "Carol Two")]
    until(s, lambda s: s.state.rules.decision is not None, limit=300)
    return s, hit, bob, carol


def test_stand_or_fall_each_defending_player_chooses_a_pile_and_only_its_creatures_block(cards):
    s, hit, bob, carol = _setup(cards)
    _split(s, "p1", ["Bob One"])
    _split(s, "p1", ["Carol One"])
    _pile(s, "p2", 1)  # Bob keeps Bob One
    _pile(s, "p3", 2)  # Carol keeps Carol Two
    late = creature(s, "p2", "Bob Late")  # (entered after the ability resolved: in no pile, so it can't block either)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hit.id, "target": "p2"}])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p2"
    for c in (bob[1], late):
        with pytest.raises(Exception, match="not in the pile chosen"):
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": c.id, "attacker_id": hit.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bob[0].id, "attacker_id": hit.id}])
    check(s)


def test_stand_or_fall_records_each_players_chosen_pile_for_this_turn(cards):
    """The restriction lasts this turn only: the record names the turn it was made."""
    s, hit, bob, carol = _setup(cards)
    _split(s, "p1", ["Bob One"])
    _split(s, "p1", ["Carol One"])
    _pile(s, "p2", 1)
    _pile(s, "p3", 1)
    assert {e[1] for e in s.state.rules.block_piles110f} == {"p2", "p3"} and {e[0] for e in s.state.rules.block_piles110f} == {s.state.turn.number}
    check(s)


# -- Arcum's Sleigh: "defending player" outside an attack trigger (802.2, 508.5a, 602.5b) ---------------------------------------------------
SLEIGH = "Arcum's Sleigh"
EXTRA.append(card(SLEIGH, set_code="w110f", number="S2", mana_cost="{2}", cmc=2.0, type_line="Artifact", colors=[], color_identity=[],
                  oracle_text="{2}, {T}: Target creature gains vigilance until end of turn. Activate only during combat and only if defending player controls a snow land."))
EXTRA.append(card("Test Snow 110F", set_code="w110f", number="S3", type_line="Basic Snow Land — Island", colors=[], color_identity=["U"], oracle_text="({T}: Add {U}.)"))


def test_sleigh_is_full(cards):
    assert coverage.of_card_data(cards.resolve(SLEIGH)).level == "FULL"


def _sleigh(cards, snow_owner, to_combat=True):
    from tests.wave53d_kit import answer  # noqa: F401

    s = table(cards, [SLEIGH], bobs=["Test Snow 110F"] if snow_owner == "p2" else [], carols=["Test Snow 110F"] if snow_owner == "p3" else [], players=3)
    sleigh = put(s, SLEIGH)
    if snow_owner:
        put(s, "Test Snow 110F", snow_owner)
    hit = creature(s, "p1", "Alice Hit")
    ready(s, "Alice Hit")
    if to_combat:
        for pid in s.state.players:
            act(s, pid, type="set_prefs", full_control=True, hold_priority=True)
        for _ in range(6):
            act(s, s.state.rules.priority, type="pass_priority")
            if s.state.rules.decision is not None:
                break
        assert s.state.rules.decision.kind == "declare_attackers"
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": hit.id, "target": "p2"}])
        assert s.state.turn.phase == "declare_attackers"
    return s, sleigh, hit


@pytest.mark.parametrize("snow_owner,ok", [("p2", True), ("p3", True), (None, False)])
def test_sleigh_needs_a_defending_player_with_a_snow_land(cards, snow_owner, ok):
    """802.2: every opponent is a defending player during the combat phase; the Sleigh's controller picks one (508.5a), so any of them controlling a snow land will do."""
    from tests.wave9c_kit import mana

    s, sleigh, hit = _sleigh(cards, snow_owner)
    mana(s, "p1", C=2)
    if ok:
        act(s, "p1", type="activate_ability", card_id=sleigh.id, ability=0, targets=[hit.id])
        assert s.state.cards[sleigh.id].tapped
        check(s)
    else:
        with pytest.raises(Exception, match="snow land"):
            act(s, "p1", type="activate_ability", card_id=sleigh.id, ability=0, targets=[hit.id])


def test_sleigh_not_outside_combat(cards):
    from tests.wave9c_kit import mana

    s, sleigh, hit = _sleigh(cards, "p2", to_combat=False)
    mana(s, "p1", C=2)
    with pytest.raises(Exception, match="combat"):
        act(s, "p1", type="activate_ability", card_id=sleigh.id, ability=0, targets=[hit.id])


# -- Tahngarth, First Mate (rulings 2019-08-23) ------------------------------------------------------------------------------------------
TAHNGARTH = "Tahngarth, First Mate"
EXTRA.append(card(TAHNGARTH, set_code="w110f", number="S4", mana_cost="{2}{R}{G}", cmc=4.0, type_line="Legendary Creature — Minotaur Warrior", power="5", toughness="5",
                  colors=["R", "G"], color_identity=["R", "G"],
                  oracle_text="Tahngarth can't be blocked by more than one creature.\nWhenever an opponent attacks with one or more creatures, if Tahngarth is tapped, you may have that opponent "
                              "gain control of Tahngarth until end of combat. If you do, choose a player or planeswalker that opponent is attacking. Tahngarth is attacking that player or planeswalker."))


def test_tahngarth_is_full(cards):
    assert coverage.of_card_data(cards.resolve(TAHNGARTH)).level == "FULL"


def _tahngarth(cards, tapped=True):
    s = table(cards, [TAHNGARTH], players=3)
    t = put(s, TAHNGARTH)
    if tapped:
        act(s, "p1", type="tap", card_ids=[t.id], tapped=True)
    one, two = creature(s, "p2", "Bob One"), creature(s, "p2", "Bob Two")
    ready(s, "Bob One", "Bob Two", pid="p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers" and s.state.turn.active_player == "p2", limit=400)
    return s, t, one, two


def _answer(s, pid, label=None):
    for _ in range(6):  # (the trigger is on the stack: pass until its question comes up)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d and (d.player, d.kind), pid)
    pick = next(o for o in d.options if label is None or o.label.startswith(label))
    act(s, pid, type="choose", decision_id=d.id, option_ids=[pick.id])


def test_tahngarth_attacks_the_player_the_opponent_chose_to_attack(cards):
    """Bob attacks Alice and Carol: Alice gives him Tahngarth until end of combat and picks Carol: it attacks her (not declared: no attack trigger), then combat damage."""
    s, t, one, two = _tahngarth(cards)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}, {"card_id": two.id, "target": "p3"}])
    _answer(s, "p1", "Yes")
    _answer(s, "p1", "Carol")
    until(s, lambda s: s.state.turn.phase == "main2", limit=60)
    assert s.state.players["p3"].life == 40 - 2 - 5 and s.state.players["p1"].life == 40 - 2  # (Tahngarth hit Carol for 5)
    assert s.state.cards[t.id].controller == "p1" and s.state.cards[t.id].attacking is None  # (back at the end of combat)
    check(s)


def test_tahngarth_untapped_or_declined_does_nothing(cards):
    s, t, one, two = _tahngarth(cards, tapped=False)  # (intervening "if": 603.4)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}])
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "confirm"
    assert s.state.cards[t.id].controller == "p1"
    check(s)
    s, t, one, two = _tahngarth(cards)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}])
    _answer(s, "p1", "No")
    assert s.state.cards[t.id].controller == "p1" and s.state.cards[t.id].attacking is None
    check(s)
