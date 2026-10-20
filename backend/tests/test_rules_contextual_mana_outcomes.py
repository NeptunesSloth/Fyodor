"""Canonical contextual mana output, retention, restrictions and delayed instructions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / "fixtures/contextual_mana_outcomes_cards.json"
NAMES = [c["name"] for c in json.loads(DATA.read_text())][:15]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"], set_code="imr37", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    r = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield r
    r.close()


def game(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())]
    s = table(cards, names, names, names)
    for p in ["p1", "p2", "p3"]:
        act(s, p, type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    return s


def pool(s, color, pid="p1"):
    p = s.state.players[pid]
    return p.mana.get(color, 0) + sum(u.sym == color for u in p.mana_units)


def activate(s, c, index=0, **kw):
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=index, **kw)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_altar_actual_mana_gain_and_both_devotions(cards):
    from app.rules import values

    s = game(cards)
    c = put(s, "Altar of the Pantheon", "battlefield")
    put(s, "Thassa, God of the Sea", "battlefield")
    before = s.state.players["p1"].life
    activate(s, c, index=1, mana_choice="G")
    assert pool(s, "G") == 1 and s.state.players["p1"].life == before + 1
    plan = Plan(s.state, "p1", cards, None)
    assert values._devotion(plan, "p1", ["U"]) == 2
    assert values._devotion(plan, "p1", ["U", "R"]) == 2
    roundtrip(s)


def test_trenzalore_true_mana_counter_then_actual_reset(cards):
    s = game(cards)
    c = put(s, "Trenzalore Clocktower", "battlefield")
    put(s, "The First Doctor", "battlefield")
    activate(s, c, index=0)
    assert pool(s, "U") == 1 and s.state.cards[c.id].counters["time"] == 1 and not s.state.zones.get("stack")
    act(s, "p1", type="counter", card_ids=[c.id], kind="time", delta=11)
    act(s, "p1", type="tap", card_ids=[c.id], tapped=False)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    activate(s, c, index=1, sources=[])
    assert s.state.cards[c.id].zone == "p1:exile"
    answer(s)
    assert len(s.state.zones["p1:hand"]) == 7 and s.state.cards[c.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("colors", [0, 1, 2])
def test_tarnation_current_monocolored_once_each(cards, colors):
    s = game(cards)
    c = put(s, "Tarnation Vista", "battlefield")
    if colors:
        put(s, "Llanowar Elves", "battlefield")
        put(s, "Trained Armodon", "battlefield")
    if colors == 2:
        put(s, "Fervor", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    activate(s, c, index=2)
    answer(s)
    assert s.state.cards[c.id].tapped and pool(s, "C") == 0
    assert pool(s, "G") == (colors > 0) and pool(s, "R") == (colors == 2)
    roundtrip(s)


def test_titans_exile_cost_and_colored_spell_actual_payment(cards):
    s = game(cards)
    c = put(s, "Titans' Nest", "battlefield")
    a = put(s, "Forest", "graveyard")
    activate(s, c, index=1)
    if s.state.rules.decision:
        choose(s, [a.id])
    answer(s)
    assert s.state.cards[a.id].zone == "p1:exile" and pool(s, "C") == 1
    spell = cast(s, "Trained Armodon", {"G": 2})
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield" and pool(s, "C") == 0
    roundtrip(s)


def test_mana_short_only_target_player_lands_and_pool(cards):
    s = game(cards)
    mine = put(s, "Forest", "battlefield")
    theirs = put(s, "Mountain", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p2", mana={"R": 3})
    cast(s, "Mana Short", {"C": 2, "U": 1}, ["p2"])
    answer(s)
    assert s.state.cards[theirs.id].tapped and not s.state.cards[mine.id].tapped
    assert pool(s, "R", "p2") == 0
    roundtrip(s)


def test_energy_tap_actual_mana_value_and_tap(cards):
    s = game(cards)
    c = put(s, "Trained Armodon", "battlefield")
    cast(s, "Energy Tap", {"U": 1}, [c.id])
    answer(s)
    assert s.state.cards[c.id].tapped and pool(s, "C") == 3
    roundtrip(s)


def test_omenpaths_two_distinct_choices_and_restrictions(cards):
    s = game(cards)
    cast(s, "Open the Omenpaths", {"C": 2, "R": 1}, modes=[0])
    settle(s)
    choose(s, ["G"])
    assert "G" not in {o.id for o in s.state.rules.decision.options}
    choose(s, ["R"])
    answer(s)
    assert pool(s, "G") == 2 and pool(s, "R") == 2
    assert all(u.only for u in s.state.players["p1"].mana_units)
    roundtrip(s)


def test_upwelling_keeps_every_players_actual_units(cards):
    s = game(cards)
    put(s, "Upwelling", "battlefield")
    land = put(s, "Forest", "battlefield")
    activate(s, land)
    act(s, "p1", type="add_mana", player="p2", mana={"R": 3})
    to_phase(s, "main2", 4)
    assert pool(s, "G") == 1 and pool(s, "R", "p2") == 3
    assert s.state.players["p1"].mana_units
    roundtrip(s)


def test_paradise_returns_only_original_activators_next_untap(cards):
    s = game(cards)
    c = put(s, "Undiscovered Paradise", "battlefield")
    activate(s, c, mana_choice="G")
    act(s, "p1", type="set_controller", card_ids=[c.id], player="p2")
    to_phase(s, "upkeep", 5)
    assert s.state.cards[c.id].zone == "p2:battlefield" and s.state.cards[c.id].controller == "p2"
    to_phase(s, "upkeep", 7)
    assert s.state.cards[c.id].zone == "p1:hand"
    roundtrip(s)


def test_niko_three_chapters_actual_foretold_mana_and_return(cards):
    s = game(cards)
    put(s, "Behold the Multiverse", "foretell")
    returned = put(s, "Saw It Coming", "graveyard")
    before = s.state.players["p1"].life
    saga = cast(s, "Niko Defies Destiny", {"C": 1, "W": 1, "U": 1})
    answer(s)
    assert s.state.players["p1"].life == before + 2
    to_phase(s, "main1", 7)
    answer(s)
    assert pool(s, "W") == 1 and pool(s, "U") == 1
    assert all(u.only for u in s.state.players["p1"].mana_units)
    to_phase(s, "main1", 10)
    answer(s)
    assert s.state.cards[returned.id].zone == "p1:hand"
    assert s.state.cards[saga.id].zone == "p1:graveyard"
    roundtrip(s)


def test_smoky_front_restricted_mana_pays_back_unlock_token(cards):
    s = game(cards)
    c = cast(s, "Smoky Lounge // Misty Salon", {"C": 2, "R": 1}, face=0)
    answer(s)
    to_phase(s, "main1", 7)
    answer(s)
    assert pool(s, "R") == 2
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 1})
    act(s, "p1", type="unlock_door", card_id=c.id, door=2)
    answer(s)
    tokens = [
        x for x in s.state.cards.values() if x.token and x.name == "Spirit" and x.zone == "p1:battlefield"
    ]
    assert len(tokens) == 1
    assert Plan(s.state, "p1", cards, None).ch(tokens[0]).pt == (2, 2)
    roundtrip(s)


def test_power_sink_unpaid_taps_mana_lands_and_empties_pool(cards):
    s = game(cards)
    land = put(s, "Mountain", "battlefield", "p2")
    target = cast(s, "Lightning Bolt", {"R": 1, "C": 2}, ["p1"], pid="p2")
    cast(s, "Power Sink", {"U": 1, "C": 3}, [target.id], x_value=3)
    answer(s)
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.cards[land.id].tapped and pool(s, "C", "p2") == 0
    roundtrip(s)


def test_plasm_capture_delays_until_next_first_main_not_main2(cards):
    s = game(cards)
    target = cast(s, "Lightning Bolt", {"R": 1}, ["p1"], pid="p2")
    cast(s, "Plasm Capture", {"G": 2, "U": 2}, [target.id])
    answer(s)
    assert s.state.cards[target.id].zone == "p2:graveyard" and s.state.rules.delayed
    to_phase(s, "main2", 4)
    answer(s)
    assert not any(pool(s, c) for c in "WUBRG")
    to_phase(s, "main1", 7)
    settle(s)
    choose(s, ["G"])
    answer(s)
    assert pool(s, "G") == 1
    roundtrip(s)


@pytest.mark.parametrize("back", [False, True])
def test_conduit_both_faces_attack_delayed_mana(cards, back):
    s = game(cards)
    c = put(s, "Conduit of Storms // Conduit of Emrakul", "battlefield")
    to_phase(s, "main1", 7)
    if back:
        act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "R": 2})
        activate(s, c, index=1, sources=[])
        answer(s)
        assert s.state.cards[c.id].face == 1
    to_phase(s, "declare_attackers", 7)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])
    answer(s)
    assert not pool(s, "C") and not pool(s, "R")
    to_phase(s, "main2", 7)
    answer(s)
    assert pool(s, "C" if back else "R") == (2 if back else 1)
    roundtrip(s)


def test_blood_snow_chooses_creature_destroyed_by_same_spell(cards):
    s = game(cards)
    bear = put(s, "Trained Armodon", "battlefield")
    one = put(s, "Llanowar Elves", "battlefield")
    land = put(s, "Snow-Covered Forest", "battlefield")
    land2 = put(s, "Snow-Covered Swamp", "battlefield")
    put(s, "Secret Door", "graveyard")
    spell = put(s, "Blood on the Snow", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "B": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=[land.id, land2.id], modes=[0])
    settle(s)
    choose(s, [one.id])
    answer(s)
    assert s.state.cards[one.id].zone == "p1:battlefield" and s.state.cards[bear.id].zone == "p1:graveyard"
    roundtrip(s)


def test_altar_bonus_applies_to_actual_nykthos_and_before_ability_loss(cards):
    from app.rules import values

    s = game(cards)
    put(s, "Altar of the Pantheon", "battlefield")
    n = put(s, "Nykthos, Shrine to Nyx", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    activate(s, n, index=1, mana_choice="B")
    answer(s)
    assert pool(s, "B") == 1 and pool(s, "C") == 0
    put(s, "March of the Machines", "battlefield")
    put(s, "Humility", "battlefield")
    plan = Plan(s.state, "p1", cards, None)
    assert values._devotion(plan, "p1", ["B"]) == 1
    roundtrip(s)


def test_paradise_skipped_untap_waits_for_next_actual_untap_cold(cards, tmp_path):
    s = game(cards)
    c = put(s, "Undiscovered Paradise", "battlefield")
    activate(s, c, mana_choice="G")
    cast(s, "Savor the Moment", {"C": 1, "U": 2})
    answer(s)
    to_phase(s, "upkeep", 5)
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].tapped
    cold_run(
        s,
        cards,
        tmp_path,
        """
from tests.test_rules_wave30m_durations import to_phase
to_phase(s,'upkeep',8)
assert s.state.cards[args[0]].zone=='p1:hand'
assert not s.state.rules.untap_operations
""",
        c.id,
    )


def test_paradise_extra_beginning_untap_returns_same_turn(cards):
    s = game(cards)
    c = put(s, "Undiscovered Paradise", "battlefield")
    cast(s, "Shadow of the Second Sun", {"C": 4, "U": 2}, ["p1"])
    answer(s)
    activate(s, c, mana_choice="R")
    to_phase(s, "main2", 4)
    answer(s)
    to_phase(s, "upkeep", 4)
    assert s.state.cards[c.id].zone == "p1:hand"
    roundtrip(s)


def test_mana_short_large_plain_pool_and_actual_source_unit(cards):
    s = game(cards)
    land = put(s, "Forest", "battlefield", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="activate_ability", card_id=land.id, ability=0)
    for _ in range(11):
        act(s, "p2", type="add_mana", player="p2", mana={"C": 100})
    assert pool(s, "C", "p2") == 1100 and pool(s, "G", "p2") == 1
    cast(s, "Mana Short", {"C": 2, "U": 1}, ["p2"])
    answer(s)
    assert not s.state.players["p2"].mana and not s.state.players["p2"].mana_units
    roundtrip(s)


def test_mana_short_conversion_replacement_and_upwelling_distinction(cards):
    s = game(cards)
    put(s, "Upwelling", "battlefield")
    put(s, "Kruphix, God of Horizons", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p2", mana={"R": 3})
    act(s, "p1", type="add_mana", player="p3", mana={"G": 2})
    cast(s, "Mana Short", {"C": 2, "U": 1}, ["p2"])
    answer(s)
    assert pool(s, "C", "p2") == 3 and pool(s, "R", "p2") == 0
    # Upwelling protects boundary emptying, not an explicit loss instruction.
    spell = put(s, "Mana Short", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "U": 1})
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p3"], sources=[])
    answer(s)
    assert pool(s, "G", "p3") == 0
    roundtrip(s)


def test_omenpaths_second_color_cold(cards, tmp_path):
    s = game(cards)
    cast(s, "Open the Omenpaths", {"C": 2, "R": 1}, modes=[0])
    settle(s)
    choose(s, ["G"])
    cold_run(
        s,
        cards,
        tmp_path,
        """
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_contextual_mana_outcomes import pool
choose(s,['U'])
assert pool(s,'G')==2 and pool(s,'U')==2
assert all(u.only for u in s.state.players['p1'].mana_units)
""",
    )


def test_plasm_delayed_original_spell_value_cold(cards, tmp_path):
    s = game(cards)
    target = cast(s, "Lightning Bolt", {"R": 1}, ["p1"], pid="p2")
    cast(s, "Plasm Capture", {"G": 2, "U": 2}, [target.id])
    answer(s)
    cold_run(
        s,
        cards,
        tmp_path,
        """
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import settle
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer
from tests.test_rules_contextual_mana_outcomes import pool
to_phase(s,'main2',4)
answer(s)
assert not any(pool(s,c) for c in 'WUBRG')
to_phase(s,'main1',7)
settle(s)
choose(s,['R'])
answer(s)
assert pool(s,'R')==1
""",
    )


def test_blood_snow_return_choice_cold(cards, tmp_path):
    s = game(cards)
    one = put(s, "Llanowar Elves", "battlefield")
    put(s, "Secret Door", "graveyard")
    land = put(s, "Snow-Covered Forest", "battlefield")
    spell = put(s, "Blood on the Snow", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "B": 2})
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=[land.id], modes=[0])
    settle(s)
    cold_run(
        s,
        cards,
        tmp_path,
        """
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[0]].zone=='p1:battlefield'
""",
        one.id,
    )


def test_mana_short_large_color_conversion_preserves_actual_unit_source(cards):
    s = game(cards)
    put(s, "Kruphix, God of Horizons", "battlefield", "p2")
    land = put(s, "Forest", "battlefield", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="activate_ability", card_id=land.id, ability=0)
    original_source = s.state.players["p2"].mana_units[0].src
    for _ in range(11):
        act(s, "p2", type="add_mana", player="p2", mana={"R": 100})
    cast(s, "Mana Short", {"C": 2, "U": 1}, ["p2"])
    answer(s)
    assert pool(s, "C", "p2") == 1101 and pool(s, "R", "p2") == 0 and pool(s, "G", "p2") == 0
    assert s.state.players["p2"].mana_units[0].src == original_source
    roundtrip(s)


def test_titans_private_exile_activation_cost_cold(cards, tmp_path):
    s = game(cards)
    c = put(s, "Titans' Nest", "battlefield")
    a = put(s, "Forest", "graveyard")
    put(s, "Mountain", "graveyard")
    activate(s, c, index=1)
    assert s.state.rules.decision is not None
    cold_run(
        s,
        cards,
        tmp_path,
        """
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_contextual_mana_outcomes import pool
choose(s,[args[0]])
assert s.state.cards[args[0]].zone=='p1:exile'
assert pool(s,'C')==1
assert all(u.only for u in s.state.players['p1'].mana_units)
""",
        a.id,
    )


def test_niko_mana_pays_real_foretell_special_action_but_not_artifact(cards):
    from app.game.errors import ActionError

    s = game(cards)
    cast(s, "Niko Defies Destiny", {"C": 1, "W": 1, "U": 1})
    answer(s)
    to_phase(s, "main1", 7)
    answer(s)
    ring = put(s, "Sol Ring", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ring.id, sources=[])
    assert pool(s, "W") == 1 and pool(s, "U") == 1
    doom = put(s, "Doomskar", "hand")
    act(s, "p1", type="activate_ability", card_id=doom.id, ability=1)
    assert s.state.cards[doom.id].zone == "p1:foretell"
    assert pool(s, "W") == 0 and pool(s, "U") == 0
    roundtrip(s)


def test_titans_mana_rejects_colorless_and_printed_x_even_zero(cards):
    from app.game.errors import ActionError

    s = game(cards)
    c = put(s, "Titans' Nest", "battlefield")
    put(s, "Forest", "graveyard")
    activate(s, c, index=1)
    answer(s)
    ring = put(s, "Sol Ring", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ring.id, sources=[])
    xspell = put(s, "Green Sun's Zenith", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=xspell.id, sources=[], x_value=1)
    assert pool(s, "C") == 1 and pool(s, "G") == 1
    roundtrip(s)


def test_omenpaths_second_mode_is_team_pump_without_mana(cards):
    s = game(cards)
    own = put(s, "Trained Armodon", "battlefield")
    opponent = put(s, "Llanowar Elves", "battlefield", "p2")
    cast(s, "Open the Omenpaths", {"C": 2, "R": 1}, modes=[1])
    answer(s)
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[own.id]).pt == (4, 3)
    assert plan.ch(s.state.cards[opponent.id]).pt == (1, 1)
    assert not any(pool(s, c) for c in "WUBRGC")
    roundtrip(s)


def test_paradise_does_not_follow_returned_new_incarnation(cards):
    s = game(cards)
    c = put(s, "Undiscovered Paradise", "battlefield")
    activate(s, c, mana_choice="G")
    original = Plan(s.state, "p1", cards, None).oid(s.state.cards[c.id])
    put(s, "Undiscovered Paradise", "hand")
    put(s, "Undiscovered Paradise", "battlefield")
    assert Plan(s.state, "p1", cards, None).oid(s.state.cards[c.id]) != original
    to_phase(s, "upkeep", 7)
    assert s.state.cards[c.id].zone == "p1:battlefield"
    roundtrip(s)
