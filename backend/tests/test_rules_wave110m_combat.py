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
