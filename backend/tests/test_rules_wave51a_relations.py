"""Wave 51A: target groups with a relation between the targets (CR 2026-09-25), real Oracle text
(tests/fixtures/wave51a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 601.2c / 115.1: "two target creature cards that share a creature type" (Unbury), "two target creatures you control that share a creature type"
  (Secret Tunnel), "two target permanents that share a permanent type" (Role Reversal), "two target creatures controlled by different players"
  (Run Away Together): the relation is a rule of the choice, checked as the targets are chosen and again for a new set of targets (115.7e).
* 608.2b / 608.2h: it is judged again as the spell resolves: targets that no longer share a type are both illegal (Shifting Loyalties ruling), and a
  target that left counts as it last existed (Return from Extinction / Run Away Together rulings: the other one is still returned).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave50i_modal_modes import until_decision
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51a", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def grave(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


# --- Unbury: two creature cards that share a creature type ------------------------------------------------------------------------------


def unbury_table(cards):
    s = build(cards, ["Unbury", "Llanowar Elves", "Elvish Visionary", "Grizzly Bears"], [])
    return s, grave(s, "Llanowar Elves"), grave(s, "Elvish Visionary"), grave(s, "Grizzly Bears")


def test_unbury_returns_two_cards_that_share_a_creature_type(cards):
    s, elves, seer, bears = unbury_table(cards)
    to_hand(s, "Unbury")
    mana(s, B=1, G=1)
    with pytest.raises(ActionError, match="share a creature type"):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Unbury").id, modes=[1], targets=[elves.id, bears.id], target_counts=[2])  # Elf and Bear: no
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Unbury").id, modes=[1], targets=[elves.id, seer.id], target_counts=[2])
    settle(s)
    assert zone_of(s, "Llanowar Elves") == zone_of(s, "Elvish Visionary") == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_unbury_one_card_left_the_graveyard_the_other_still_returns(cards):
    s, elves, seer, _ = unbury_table(cards)
    to_hand(s, "Unbury")
    mana(s, B=1, G=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Unbury").id, modes=[1], targets=[elves.id, seer.id], target_counts=[2])
    assert s.state.rules.stack
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "exile"})  # in response: it left, as an Elf (ruling 2019-06-14)
    settle(s)
    assert zone_of(s, "Elvish Visionary") == "p1:hand" and zone_of(s, "Llanowar Elves") == "p1:exile"
    check(s)


def test_unbury_first_mode_has_no_relation(cards):
    s, elves, _, bears = unbury_table(cards)
    to_hand(s, "Unbury")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Unbury").id, modes=[0], targets=[bears.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:hand" and zone_of(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


# --- Secret Tunnel: no longer sharing a type on resolution -------------------------------------------------------------------------------


def test_secret_tunnel_needs_two_creatures_sharing_a_type(cards):
    s = build(cards, ["Secret Tunnel", "Llanowar Elves", "Elvish Visionary", "Grizzly Bears"], [])
    tunnel = put(s, "Secret Tunnel")
    elves, seer, bears = put(s, "Llanowar Elves"), put(s, "Elvish Visionary"), put(s, "Grizzly Bears")
    mana(s, C=4)
    with pytest.raises(ActionError, match="share a creature type"):
        act(s, "p1", type="activate_ability", card_id=tunnel.id, ability=2, targets=[elves.id, bears.id], target_counts=[2])
    act(s, "p1", type="activate_ability", card_id=tunnel.id, ability=2, targets=[elves.id, seer.id], target_counts=[2])
    settle(s)
    assert "cant_be_blocked" in imposed(s, elves) and "cant_be_blocked" in imposed(s, seer) and "cant_be_blocked" not in imposed(s, bears)
    check(s)


def imposed(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).imposed


def test_secret_tunnel_ability_does_nothing_when_they_stopped_sharing_a_type(cards):
    s = build(cards, ["Secret Tunnel", "Llanowar Elves", "Elvish Visionary", "Turn to Frog"], [])
    tunnel = put(s, "Secret Tunnel")
    elves, seer = put(s, "Llanowar Elves"), put(s, "Elvish Visionary")
    to_hand(s, "Turn to Frog")
    mana(s, C=4, U=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=tunnel.id, ability=2, targets=[elves.id, seer.id], target_counts=[2])
    assert s.state.rules.stack  # (Alice can respond, so it waits)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Turn to Frog").id, targets=[seer.id])  # an Elf Shaman is now a Frog
    settle(s)
    assert "cant_be_blocked" not in imposed(s, elves) and "cant_be_blocked" not in imposed(s, seer)  # both targets were illegal: nothing happened
    check(s)


# --- Run Away Together / Role Reversal: controllers and permanent types -----------------------------------------------------------------


def test_run_away_together_needs_two_players_creatures(cards):
    s = build(cards, ["Run Away Together", "Llanowar Elves", "Elvish Visionary"], ["Grizzly Bears"])
    mine, mine2, theirs = put(s, "Llanowar Elves"), put(s, "Elvish Visionary"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Run Away Together")
    mana(s, U=1, G=1)
    spell = card_named(s, "Run Away Together")
    with pytest.raises(ActionError, match="different players"):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, mine2.id], target_counts=[2])  # the same player controls both
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[2])
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:hand" and zone_of(s, "Grizzly Bears", "p2") == "p2:hand"
    assert zone_of(s, "Elvish Visionary") == "p1:battlefield"
    check(s)


def test_run_away_together_is_not_castable_without_a_pair_of_controllers(cards):
    s = build(cards, ["Run Away Together", "Llanowar Elves", "Elvish Visionary"], [])
    put(s, "Llanowar Elves"), put(s, "Elvish Visionary")
    to_hand(s, "Run Away Together")
    mana(s, U=1, G=1)
    with pytest.raises(ActionError, match="enough legal targets"):  # both creatures are Alice's: no two are controlled by different players
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Run Away Together").id)
    assert zone_of(s, "Run Away Together") == "p1:hand"
    check(s)


def test_role_reversal_exchanges_permanents_sharing_a_permanent_type(cards):
    s = build(cards, ["Role Reversal", "Llanowar Elves", "Sol Grail"], ["Grizzly Bears", "Pacifism"])
    mine, rock = put(s, "Llanowar Elves"), put(s, "Sol Grail")
    theirs = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Role Reversal")
    mana(s, U=2, R=1)
    spell = card_named(s, "Role Reversal")
    with pytest.raises(ActionError, match="share a permanent type"):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[rock.id, theirs.id], target_counts=[2])  # an artifact and a creature
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[2])
    settle(s)
    assert s.state.cards[mine.id].controller == "p2" and s.state.cards[theirs.id].controller == "p1"
    check(s)


def test_role_reversal_nothing_happens_when_one_player_controls_both(cards):
    s = build(cards, ["Role Reversal", "Llanowar Elves", "Elvish Visionary"], [])
    a, b = put(s, "Llanowar Elves"), put(s, "Elvish Visionary")
    to_hand(s, "Role Reversal")
    mana(s, U=2, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Role Reversal").id, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert s.state.cards[a.id].controller == s.state.cards[b.id].controller == "p1"
    check(s)


# --- triggers: Kitsune (exchange, other creatures of different players) -----------------------------------------------------------------


def cast_kitsune(s):
    to_hand(s, "Kitsune, Dragon's Daughter")
    mana(s, U=2, G=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kitsune, Dragon's Daughter").id)


def test_kitsune_exchanges_two_other_creatures_controlled_by_different_players(cards):
    s = build(cards, ["Kitsune, Dragon's Daughter", "Llanowar Elves", "Elvish Visionary"], ["Grizzly Bears"])
    mine, mine2, theirs = put(s, "Llanowar Elves"), put(s, "Elvish Visionary"), put(s, "Grizzly Bears", "p2")
    cast_kitsune(s)
    d = until_decision(s)
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {mine.id, mine2.id, theirs.id}  # (not Kitsune: "other")
    with pytest.raises(ActionError, match="different players"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id, mine2.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id, theirs.id])
    settle(s)
    assert s.state.cards[mine.id].controller == "p2" and s.state.cards[theirs.id].controller == "p1"
    assert s.state.cards[mine2.id].controller == "p1"
    check(s)


def test_kitsune_with_creatures_of_one_player_only_is_removed(cards):
    s = build(cards, ["Kitsune, Dragon's Daughter", "Llanowar Elves", "Elvish Visionary"], [])
    put(s, "Llanowar Elves"), put(s, "Elvish Visionary")
    cast_kitsune(s)
    settle(s)
    assert s.state.rules.decision is None and not s.state.rules.stack  # 603.3d: not enough legal targets
    check(s)


# --- total mana value of cards chosen on resolution (no targets: 608.2d) ----------------------------------------------------------------


def test_technomancer_returns_artifact_creatures_up_to_a_total_mana_value_of_six(cards):
    s = build(cards, ["Technomancer", "Perilous Myr", "Foundry Inspector", "Frogmite"], [])
    myr, inspector, frog = grave(s, "Perilous Myr"), grave(s, "Foundry Inspector"), grave(s, "Frogmite")
    to_hand(s, "Technomancer")
    mana(s, B=2, G=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Technomancer").id)
    d = until_decision(s)
    assert d is not None and {o.id for o in d.options} == {myr.id, inspector.id, frog.id} and "total mana value 6 or less" in d.prompt
    with pytest.raises(ActionError, match="total mana value 6 or less"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[inspector.id, frog.id])  # 3 + 4
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[myr.id, frog.id])  # 2 + 4
    settle(s)
    assert zone_of(s, "Perilous Myr") == zone_of(s, "Frogmite") == "p1:battlefield" and zone_of(s, "Foundry Inspector") == "p1:graveyard"
    check(s)


def test_technomancer_may_return_none(cards):
    s = build(cards, ["Technomancer", "Perilous Myr"], [])
    grave(s, "Perilous Myr")
    to_hand(s, "Technomancer")
    mana(s, B=2, G=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Technomancer").id)
    d = until_decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert zone_of(s, "Perilous Myr") == "p1:graveyard"
    check(s)


def test_michelangelo_s_technique_puts_up_to_two_creatures_with_total_mana_value_six_from_the_top_eight(cards):
    s = build(cards, ["Michelangelo's Technique", "Frogmite", "Foundry Inspector", "Grizzly Bears"], [])
    to_hand(s, "Michelangelo's Technique")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Michelangelo's Technique").id)
    d = until_decision(s)
    frog, inspector, bears = (card_named(s, n) for n in ("Frogmite", "Foundry Inspector", "Grizzly Bears"))
    assert d is not None and {frog.id, inspector.id, bears.id} <= {o.id for o in d.options}
    with pytest.raises(ActionError, match="total mana value 6 or less"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[frog.id, inspector.id])  # 4 + 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[frog.id, bears.id])  # 4 + 2
    settle(s)
    assert zone_of(s, "Frogmite") == zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Foundry Inspector") == "p1:library"
    assert inspector.id not in str(s.view("p2")["rules"].get("decision"))  # (the cards looked at stay private)
    check(s)


def ao_dies(s):
    put(s, "Ao, the Dawn Sky")
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, "Ao, the Dawn Sky").id])
    return until_decision(s)


def test_ao_counters_on_each_creature_or_vehicle_you_control(cards):
    s = build(cards, ["Ao, the Dawn Sky", "Murder", "Grizzly Bears", "Sky-Skiff", "Sol Grail"], [])
    for n in ("Grizzly Bears", "Sky-Skiff", "Sol Grail"):
        put(s, n)
    d = ao_dies(s)
    assert d is not None and "choose one mode" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "counters" in o.label)])
    settle(s)
    counters = lambda n: s.state.cards[card_named(s, n).id].counters.get("+1/+1", 0)  # noqa: E731
    assert counters("Grizzly Bears") == counters("Sky-Skiff") == 2 and counters("Sol Grail") == 0  # (a Vehicle that isn't crewed is no creature)
    check(s)


def test_ao_puts_nonland_permanents_with_total_mana_value_four_from_the_top_seven(cards):
    s = build(cards, ["Ao, the Dawn Sky", "Murder", "Frogmite", "Perilous Myr", "Foundry Inspector"], [])
    d = ao_dies(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Look at the top seven" in o.label)])
    d = until_decision(s)
    frog, myr, inspector = (card_named(s, n) for n in ("Frogmite", "Perilous Myr", "Foundry Inspector"))
    with pytest.raises(ActionError, match="total mana value 4 or less"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[myr.id, inspector.id])  # 2 + 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[frog.id])
    settle(s)
    assert zone_of(s, "Frogmite") == "p1:battlefield" and zone_of(s, "Perilous Myr") == zone_of(s, "Foundry Inspector") == "p1:library"
    check(s)
