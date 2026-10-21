"""Actual printed damage/history sequences, original identities and instruction order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from app.rules.sba import power
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/damage_history39_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="dh39", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c["name"] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    put(s, "Fervor", "battlefield")
    return s


def test_whipkeeper_counts_actual_damage_twice_not_just_its_own_source(cards):
    s = game(cards)
    source = put(s, "Whipkeeper", "battlefield")
    target = put(s, "Ancient Brontodon", "battlefield", "p2")
    cast(s, "Lightning Bolt", [target.id])
    activate(s, source, "damage to target", [target.id])
    assert s.state.cards[target.id].damage == 6
    roundtrip(s)


def test_eternal_flame_mountains_freezes_two_simultaneous_player_amounts(cards):
    s = game(cards)
    for n in ["Mountain", "Snow-Covered Mountain", "Stomping Ground"]:
        put(s, n, "battlefield")
    cast(s, "Eternal Flame", ["p2"])
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (38, 37)
    roundtrip(s)


def test_catapult_divides_x_by_current_opponent_creature_count(cards):
    s = game(cards)
    targets = [
        put(s, n, "battlefield", "p2") for n in ["Grizzly Bears", "Runeclaw Bear", "Colossal Dreadmaw"]
    ]
    cast(s, "Dwarven Catapult", ["p2"], x_value=5)
    assert [s.state.cards[c.id].damage for c in targets] == [1, 1, 1]
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_superior_numbers_opponent_target_is_not_forced_to_creature_controller(cards):
    s = game(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Runeclaw Bear", "battlefield")
    put(s, "Memnite", "battlefield", "p2")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p3")
    cast(s, "Superior Numbers", [target.id, "p2"], target_counts=[1, 1])
    assert s.state.cards[target.id].damage == 1
    roundtrip(s)


def test_friendly_fire_random_single_hand_card_hits_creature_and_controller(cards):
    s = game(cards)
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    for cid in list(s.state.zones.get("p2:hand", [])):
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "library"})
    revealed = put(s, "Divination", "hand", "p2")
    cast(s, "Friendly Fire", [target.id])
    assert s.state.cards[target.id].damage == 3 and s.state.players["p2"].life == 37
    assert s.state.cards[revealed.id].zone == "p2:hand"
    roundtrip(s)


def test_builder_counts_actual_deaths_for_each_original_controller(cards):
    s = game(cards)
    targets = [put(s, "Sol Ring", "battlefield", p) for p in ["p1", "p2", "p3"]]
    cast(s, "Builder's Bane", [c.id for c in targets], x_value=3, target_counts=[3])
    assert [s.state.players[p].life for p in ["p1", "p2", "p3"]] == [39, 39, 39]
    assert all(s.state.cards[c.id].zone.endswith(":graveyard") for c in targets)
    roundtrip(s)


def test_dead_reckoning_captures_graveyard_cda_before_card_leaves(cards):
    s = game(cards)
    old = put(s, "Lhurgoyf", "graveyard")
    put(s, "Grizzly Bears", "graveyard", "p2")
    victim = put(s, "Colossal Dreadmaw", "battlefield", "p3")
    plan = Plan(s.state, "p1", cards, None)
    assert power(old, plan.ch(old)) == 2
    cast(s, "Dead Reckoning", [old.id, victim.id], target_counts=[1, 1])
    pick(s, ["yes"])
    settle(s)
    assert s.state.cards[old.id].zone == "p1:library"
    assert s.state.cards[victim.id].damage == 2
    roundtrip(s)


def test_heretic_mills_before_using_highest_actual_mana_value(cards):
    s = game(cards)
    source = put(s, "Heretic's Punishment", "battlefield")
    # Observe the actual packet rather than inventing a nominal mill result.
    from app.rules.effects import _library

    packet = _library(Plan(s.state, "p1", cards, None), "p1")[:3]
    expected = max((cards.resolve(s.state.cards[c].name).get("cmc", 0) for c in packet), default=0)
    activate(s, source, "Choose any target", ["p2"])
    assert s.state.players["p2"].life == 40 - int(expected)
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in packet)
    roundtrip(s)


def test_spirit_flare_real_combat_taps_own_source_before_damage(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    own = put(s, "Grizzly Bears", "battlefield")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    to_phase(s, "declare_attackers", turn=5)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": target.id, "target": "p1"}])
    cast(s, "Spirit Flare", [own.id, target.id], target_counts=[1, 1])
    assert s.state.cards[own.id].tapped and s.state.cards[target.id].damage == 2
    roundtrip(s)


def test_sling_actual_creature_tap_cost_supplies_power_not_artifact(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    own = put(s, "Colossal Dreadmaw", "battlefield")
    source = put(s, "Unerring Sling", "battlefield")
    target = put(s, "Air Elemental", "battlefield", "p2")
    to_phase(s, "declare_attackers", turn=5)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": target.id, "target": "p1"}])
    activate(s, source, "deals damage", [target.id])
    if s.state.rules.decision:
        pick(s, [own.id])
        settle(s)
    assert s.state.cards[own.id].tapped and s.state.cards[source.id].tapped
    assert s.state.cards[target.id].zone == "p2:graveyard"
    roundtrip(s)


def test_sentinel_counts_spells_before_triggering_spell_even_if_still_stacked(cards):
    s = game(cards)
    source = cast(s, "Sentinel Tower")
    # Tower itself is not instant/sorcery. Both real casts trigger target selection.
    cast(s, "Lightning Bolt", ["p2"], resolve=False)
    pick(s, ["p3"])
    settle(s)
    assert s.state.players["p3"].life == 39
    cast(s, "Shock", ["p2"], resolve=False)
    pick(s, ["p3"])
    settle(s)
    assert s.state.players["p3"].life == 37 and s.state.players["p2"].life == 35
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_curse_counts_all_current_attachments_on_enchanted_players_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    cast(s, "Curse of Thirst", ["p2"])
    cast(s, "Curse of Vitality", ["p2"])
    to_phase(s, "upkeep", turn=5)
    settle(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


@pytest.mark.parametrize("pay", [False, True])
def test_hunger_other_creature_payment_cannot_sacrifice_enchanted_creature(cards, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    host = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    other = put(s, "Grizzly Bears", "battlefield", "p2") if pay else None
    cast(s, "Unnatural Hunger", [host.id])
    to_phase(s, "upkeep", turn=5)
    settle(s)
    if pay:
        assert s.state.rules.decision.player == "p2"
        pick(s, ["pay"])
        settle(s)
        if s.state.rules.decision:
            assert host.id not in [o.id for o in s.state.rules.decision.options]
            pick(s, [other.id])
            settle(s)
        assert s.state.cards[other.id].zone == "p2:graveyard"
        assert s.state.players["p2"].life == 40
    else:
        assert s.state.rules.decision is None
        assert s.state.players["p2"].life == 34
    assert s.state.cards[host.id].zone == "p2:battlefield"
    roundtrip(s)


def test_tuktuk_real_enter_optional_destroy_then_current_ally_count(cards):
    s = game(cards)
    put(s, "Stonework Puma", "battlefield")
    target = put(s, "Sol Ring", "battlefield", "p2")
    cast(s, "Tuktuk Scrapper")
    pick(s, [target.id])
    settle(s)
    pick(s, ["yes"])
    settle(s)
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_flesh_reaver_combat_damage_triggers_actual_damage_to_its_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source = cast(s, "Flesh Reaver")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    to_phase(s, "end_combat", turn=4)
    settle(s)
    assert s.state.players["p1"].life == 36 and s.state.players["p2"].life == 36
    roundtrip(s)


def test_justice_sums_red_spell_damage_to_multiple_players_one_source_batch(cards):
    s = game(cards)
    source = cast(s, "Justice")
    for n in ["Mountain", "Snow-Covered Mountain", "Stomping Ground"]:
        put(s, n, "battlefield")
    cast(s, "Eternal Flame", ["p2"])
    # Spell deals3+2 simultaneously; Justice then deals5 to its original controller.
    assert s.state.players["p1"].life == 33 and s.state.players["p2"].life == 37
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_electryte_damages_current_blockers_after_defending_player_combat_damage(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source = cast(s, "Electryte")
    bear = put(s, "Grizzly Bears", "battlefield")
    blocker = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    to_phase(s, "declare_attackers", turn=4)
    act(
        s,
        "p1",
        type="declare_attackers",
        attackers=[{"card_id": source.id, "target": "p2"}, {"card_id": bear.id, "target": "p2"}],
    )
    to_phase(s, "declare_blockers", turn=4)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bear.id}])
    to_phase(s, "end_combat", turn=4)
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[blocker.id].damage == 5
    roundtrip(s)


def test_monsoon_counts_only_newly_tapped_islands_at_end_step(cards):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    cast(s, "Monsoon")
    lands = [put(s, n, "battlefield") for n in ["Island", "Snow-Covered Island", "Steam Vents"]]
    act(s, "p1", type="tap", card_ids=[lands[0].id], tapped=True)
    stops(s, "end", "upkeep", "main1")
    to_phase(s, "end", turn=4)
    settle(s)
    assert all(s.state.cards[c.id].tapped for c in lands)
    assert s.state.players["p1"].life == 38
    roundtrip(s)


def test_trumpet_vigilant_attacker_untapped_nonattacker_tapped_and_counted(cards):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    cast(s, "Angel's Trumpet")
    attacker = put(s, "Grizzly Bears", "battlefield")
    idle = put(s, "Runeclaw Bear", "battlefield")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    to_phase(s, "end_combat", turn=4)
    settle(s)
    stops(s, "end", "upkeep", "main1")
    to_phase(s, "end", turn=4)
    settle(s)
    assert not s.state.cards[attacker.id].tapped and s.state.cards[idle.id].tapped
    assert s.state.players["p1"].life == 39
    roundtrip(s)


def test_growth_additional_draw_count_excludes_normal_draw_step_card(cards):
    from app.rules import history
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    source = cast(s, "Malignant Growth")
    act(s, "p1", type="counter", card_ids=[source.id], kind="growth", delta=2)
    stops(s, "draw", "upkeep", "main1")
    to_phase(s, "draw", turn=5)
    settle(s)
    assert s.state.players["p2"].life == 38
    assert history.log_for(Plan(s.state, "p1", cards, None)).drew.get("p2") == 3
    roundtrip(s)
