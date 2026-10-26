"""Wave 110M: costs and restrictions on combat. Every scenario checks the replay and a save and a load.

* 509.1c-d, 509.1f: "Enchanted creature can't be blocked unless defending player pays {3} for each creature they control that's blocking it." (Awesome Presence):
  a cost for each creature blocking that attacker; blocking any other attacker is free, and a requirement never forces the payment.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build as designations_build
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase
from tests.wave110m_kit import full_test, open_repo

PRESENCE = "Awesome Presence"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([PRESENCE])


def table(cards):
    """Alice attacks with the enchanted Grizzly Bears and with Elite Vanguard; Bob has Llanowar Elves, Mother of Runes and Grizzly Bears."""
    s = designations_build(cards, [PRESENCE, "Grizzly Bears", "Elite Vanguard"],
                           bob=[(1, "Llanowar Elves"), (1, "Mother of Runes"), (10, "Island")])
    bear = put(s, "Grizzly Bears", "battlefield")
    vanguard = put(s, "Elite Vanguard", "battlefield")
    aura = put(s, PRESENCE, "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    blockers = [put(s, n, "battlefield", "p2") for n in ("Llanowar Elves", "Mother of Runes")]
    stops(s)
    next_turn(s)
    attack(s, bear, vanguard)
    to_phase(s, "declare_blockers")
    assert s.state.rules.decision.kind == "declare_blockers"
    return s, bear, vanguard, blockers


def declare(s, pairs):
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def test_blocking_the_enchanted_creature_costs_three_for_each_blocker(cards):
    s, bear, _, (elves, mother) = table(cards)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 3})
    with pytest.raises(ActionError, match="Blocking costs"):
        declare(s, [(elves, bear), (mother, bear)])  # {6}: three in the pool, and the Elves' one mana
    declare(s, [(mother, bear)])
    assert s.state.cards[mother.id].blocking == bear.id and mana_pool(s, "p2") == {}
    roundtrip(s)


def test_two_blockers_of_the_enchanted_creature_pay_six(cards):
    s, bear, _, (elves, mother) = table(cards)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 6})
    declare(s, [(elves, bear), (mother, bear)])
    assert s.state.cards[elves.id].blocking == bear.id and s.state.cards[mother.id].blocking == bear.id and mana_pool(s, "p2") == {}
    roundtrip(s)


def test_blocking_another_attacker_is_free(cards):
    s, _, vanguard, (elves, _) = table(cards)
    declare(s, [(elves, vanguard)])
    assert s.state.cards[elves.id].blocking == vanguard.id and mana_pool(s, "p2") == {}
    roundtrip(s)


def test_unpayable_cost_leaves_the_declaration_untouched(cards):
    s, bear, _, (elves, _) = table(cards)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="Blocking costs"):
        declare(s, [(elves, bear)])
    assert s.state.model_dump(mode="json") == before
    declare(s, [])
    assert s.state.cards[elves.id].blocking is None
    roundtrip(s)


# -- Johan -----------------------------------------------------------------------------------------------------------------------------------
JOHAN = "Johan"
test_johan_full = full_test([JOHAN])


def johan_table(cards, tap_johan=False):
    from tests.wave110m_kit import build, put

    s = build(cards, [JOHAN, "Grizzly Bears", "Llanowar Elves"], forests=20)
    johan, bears = put(s, JOHAN), put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    return s, johan, bears, elves


@pytest.mark.parametrize("use,johan_tapped,bears_tapped", [(True, False, False), (False, False, True), (True, True, True)])
def test_johan_attacks_without_tapping_only_while_he_is_untapped_and_stays_home(cards, use, johan_tapped, bears_tapped):
    """If you do: Johan can't attack until end of combat, and attacking doesn't cause creatures you control to tap this combat if Johan is untapped (508.1f)."""
    from tests.test_rules_wave34b_activated import next_turn, stops, to_phase
    from tests.wave110m_kit import act, answer

    s, johan, bears, elves = johan_table(cards)
    stops(s)
    next_turn(s)
    if johan_tapped:
        act(s, "p1", type="tap", card_ids=[johan.id], tapped=True)
    to_phase(s, "begin_combat")
    answer(s, "yes" if use else "no")
    to_phase(s, "declare_attackers")
    if use:
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": johan.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": elves.id, "target": "p2"}])
    assert s.state.cards[bears.id].tapped is bears_tapped and s.state.cards[elves.id].tapped is bears_tapped
    roundtrip(s)


# -- Gurzigost -------------------------------------------------------------------------------------------------------------------------------
GURZIGOST = "Gurzigost"
test_gurzigost_full = full_test([GURZIGOST])


def gurzigost_upkeep(cards, graveyard):
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave34b_activated import to_phase
    from tests.wave110m_kit import act, build, card_named, put

    s = build(cards, [GURZIGOST, "Grizzly Bears", "Llanowar Elves", "Elite Vanguard"], forests=20)
    g = put(s, GURZIGOST)
    for n in graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    stops(s)
    to_phase(s, "upkeep", turn=3)
    until(s, lambda s: s.state.rules.decision is not None or g.id not in s.state.zones["p1:battlefield"] or s.state.turn.phase != "upkeep")
    return s, g


def test_gurzigost_upkeep_put_two_cards_on_the_bottom_or_sacrifice_it(cards):
    from tests.wave110m_kit import answer, card_named, check

    s, g = gurzigost_upkeep(cards, ["Grizzly Bears", "Llanowar Elves", "Elite Vanguard"])
    bears, elves = card_named(s, "Grizzly Bears").id, card_named(s, "Llanowar Elves").id
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and (d.min_choices, d.max_choices) == (0, 2)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears])  # one is not two
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears, elves])
    answer(s, elves)  # (the Elves go on the very bottom)
    assert s.state.cards[g.id].zone == "p1:battlefield" and s.state.zones["p1:library"][-2:] == [bears, elves]
    check(s)


def test_gurzigost_is_sacrificed_when_nothing_is_put_back(cards):
    from tests.wave110m_kit import answer, check

    s, g = gurzigost_upkeep(cards, ["Grizzly Bears", "Llanowar Elves"])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[])
    answer(s)
    assert s.state.cards[g.id].zone == "p1:graveyard"
    check(s)


def test_gurzigost_with_fewer_than_two_graveyard_cards_cannot_pay(cards):
    from tests.wave110m_kit import answer, check

    s, g = gurzigost_upkeep(cards, ["Grizzly Bears"])
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_cards"
    answer(s)
    assert s.state.cards[g.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("yes", [True, False])
def test_gurzigost_may_assign_its_combat_damage_as_though_it_weren_t_blocked(cards, yes):
    """510.1c: the activated ability lasts this turn; the controller still chooses when damage is assigned."""
    from tests.test_rules_wave34b_activated import attack, next_turn
    from tests.test_rules_wave36a_trigger_words import loyal  # noqa: F401
    from tests.wave110m_kit import answer, build, check, fund, life, put, to_hand, to_phase

    s = build(cards, [GURZIGOST, "Grizzly Bears"], ["Wall of Fire"], forests=20)
    wall = put(s, "Wall of Fire", "p2")
    stops(s)
    next_turn(s)
    g = put(s, GURZIGOST)  # (after the upkeep, where it would have to pay)
    from tests.wave36a_kit import ready

    ready(s, GURZIGOST)
    to_hand(s, "Grizzly Bears")
    fund(s, "{G}{G}")
    act(s, "p1", type="activate_ability", card_id=g.id, ability=1)
    answer(s)
    attack(s, g)
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": g.id}])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm":
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes" if yes else "no"])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase in ("combat_damage", "declare_blockers") or s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == (34 if yes else 40)
    check(s)
