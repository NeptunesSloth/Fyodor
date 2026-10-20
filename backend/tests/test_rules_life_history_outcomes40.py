"""Actual printed damage/history sequences, original identities and instruction order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/life_history40_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="lh40", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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


def test_final_punishment_damage_not_life_loss(cards):
    s = game(cards)
    cast(s, "Lightning Bolt", ["p2"])
    cast(s, "Final Punishment", ["p2"])
    assert s.state.players["p2"].life == 34
    roundtrip(s)


def test_haunt_counts_actual_artifacts_after_native_tokens(cards):
    s = game(cards)
    put(s, "Sol Ring", "battlefield")
    cast(s, "Haunt the Network", ["p2"])
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (43, 37)
    ts = [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name == "Thopter"]
    assert len(ts) == 2 and all("flying" in Plan(s.state, "p1", cards, None).ch(c).keywords for c in ts)
    roundtrip(s)


def test_first_family_includes_countered_or_resolved_cast_colors(cards):
    s = game(cards)
    cast(s, "Lightning Bolt", ["p2"])
    before = len(s.state.zones["p1:hand"])
    cast(s, "First Family")
    assert s.state.players["p1"].life == 43
    assert len(s.state.zones["p1:hand"]) == before + 3
    roundtrip(s)


def test_tempest_counts_only_actual_destroyed_controller_receipts(cards):
    s = game(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Ancient Brontodon", "battlefield", "p2")
    cast(s, "Deadly Tempest")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (39, 39)
    roundtrip(s)


def test_seeds_controller_gets_mv_for_each_original_artifact(cards):
    s = game(cards)
    put(s, "Sol Ring", "battlefield")
    put(s, "Unerring Sling", "battlefield", "p2")
    cast(s, "Seeds of Innocence")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (41, 43)
    roundtrip(s)


def test_reverse_polarity_counts_original_artifact_source_damage(cards):
    from tests.test_rules_conditional_prevention import activate

    s = game(cards)
    source = cast(s, "Triskelion")
    source = s.state.cards[source.id]
    activate(s, source, "damage to any target", ["p1"])
    activate(s, source, "damage to any target", ["p1"])
    cast(s, "Lightning Bolt", ["p1"])
    assert s.state.players["p1"].life == 35
    cast(s, "Reverse Polarity")
    assert s.state.players["p1"].life == 39
    roundtrip(s)


def test_foul_tongue_actual_attackers_and_actual_replaced_loss(cards):
    from tests.test_rules_conditional_prevention import attack

    s = game(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    put(s, "Bloodletter of Aclazotz", "battlefield")
    attack(s, [bear], turn=4)
    cast(s, "Foul-Tongue Shriek", ["p2"])
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (42, 38)
    roundtrip(s)


def test_tempest_indestructible_excluded_but_seeds_indestructible_gets_life(cards):
    s = game(cards)
    myr = put(s, "Darksteel Myr", "battlefield", "p2")
    ingot = put(s, "Darksteel Ingot", "battlefield", "p2")
    cast(s, "Deadly Tempest")
    assert s.state.players["p2"].life == 40 and s.state.cards[myr.id].zone.endswith(":battlefield")
    cast(s, "Seeds of Innocence")
    assert s.state.players["p2"].life == 46 and s.state.cards[ingot.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_cradle_actual_gain_event_target_then_optional_payment(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    put(s, "Cradle of Vitality", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Healing Salve", ["p1"], modes=[0])
    d = s.state.rules.decision
    assert d and any(o.card_id == bear.id for o in d.options)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.id == "pay" for o in d.options)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_belbe_actual_postcombat_active_player_not_ability_controller(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    put(s, "Belbe, Corrupted Observer", "battlefield")
    cast(s, "Lightning Bolt", ["p2"])
    to_phase(s, "main2", turn=4)
    from tests.test_rules_designations import settle

    settle(s)
    assert mana_pool(s).get("C", 0) == 2
    roundtrip(s)


def test_study_owned_commander_choice_is_not_greatest_mana_value(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    low = put(s, "Yoshimaru, Ever Faithful", "command")
    high = put(s, "Ravos, Soultender", "battlefield")
    for c in list(s.state.cards.values()):
        if c.owner == "p1" and c.commander_key:
            act(s, "p1", type="set_commander", card_id=c.id, value=False)
    for source in [low, high]:
        act(s, "p1", type="set_commander", card_id=source.id, value=True)
    before = len(s.state.zones["p1:hand"])
    cast(s, "Stinging Study")
    d = s.state.rules.decision
    assert d and {low.id, high.id} <= {o.card_id for o in d.options}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[low.id])
    settle(s)
    assert s.state.players["p1"].life == 39 and len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


def test_warlock_native_etb_lost_life_reveal_and_original_controller_selects(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    land = put(s, "Island", "hand", "p2")
    spell = put(s, "Deadly Tempest", "hand", "p2")
    cast(s, "Lightning Bolt", ["p2"])
    cast(s, "Thought-Stalker Warlock")
    d = s.state.rules.decision
    assert d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    d = s.state.rules.decision
    assert (
        d
        and d.player == "p1"
        and spell.id in {o.card_id for o in d.options}
        and land.id not in {o.card_id for o in d.options}
    )
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == "p2:graveyard"
    roundtrip(s)


def install_cold_foundation():
    from app.rules import effects
    from app.rules import life_history_outcomes as leaf

    assert all(effects.PRIMITIVES.get(k) is fn for k, fn in leaf.PRIMITIVES.items())


@pytest.mark.parametrize("stage", ["study", "cradle", "warlock", "racket", "confidant", "scythe"])
def test_life_native_pending_choices_resume_in_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards)
    ids = {}
    if stage == "study":
        low = put(s, "Yoshimaru, Ever Faithful", "command")
        high = put(s, "Ravos, Soultender", "battlefield")
        for old in list(s.state.cards.values()):
            if old.owner == "p1" and old.commander_key:
                act(s, "p1", type="set_commander", card_id=old.id, value=False)
        for c in [low, high]:
            act(s, "p1", type="set_commander", card_id=c.id, value=True)
        cast(s, "Stinging Study")
        ids = {"low": low.id}
    elif stage == "cradle":
        put(s, "Cradle of Vitality", "battlefield")
        bear = put(s, "Grizzly Bears", "battlefield")
        cast(s, "Healing Salve", ["p1"], modes=[0])
        d = s.state.rules.decision
        assert d
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
        settle(s)
        ids = {"bear": bear.id}
    elif stage == "racket":
        from tests.test_rules_wave30m_durations import stops, to_phase

        put(s, "Protection Racket", "battlefield")
        for name in ["Ancient Brontodon", "Sol Ring"]:
            c = put(s, name, "hand")
            act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
        stops(s, "upkeep")
        to_phase(s, "upkeep", turn=7)
        settle(s)
    elif stage == "confidant":
        from tests.test_rules_wave30m_durations import stops, to_phase

        put(s, "Enlightened Confidant", "battlefield")
        cast(s, "Healing Salve", ["p1"], modes=[0])
        top = put(s, "Sol Ring", "hand")
        act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
        stops(s, "end")
        to_phase(s, "end", turn=4)
        settle(s)
        ids = {"top": top.id}
    elif stage == "scythe":
        from tests.test_rules_conditional_prevention import attack
        from tests.test_rules_designations import pick
        from tests.test_rules_wave30m_durations import stops, to_phase

        source = put(s, "Scythe Specter", "battlefield")
        first = put(s, "Deadly Tempest", "hand", "p2")
        second = put(s, "Deadly Tempest", "hand", "p3")
        put(s, "Island", "hand", "p2")
        put(s, "Island", "hand", "p3")
        stops(s, "combat_damage")
        attack(s, [source], turn=4)
        to_phase(s, "combat_damage", turn=4)
        settle(s)
        pick(s, [first.id])
        settle(s)
        ids = {"first": first.id, "second": second.id}
    else:
        spell = put(s, "Deadly Tempest", "hand", "p2")
        cast(s, "Lightning Bolt", ["p2"])
        cast(s, "Thought-Stalker Warlock")
        d = s.state.rules.decision
        assert d
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
        settle(s)
        ids = {"spell": spell.id}
    assert s.state.rules.decision
    path = tmp_path / "state.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_life_history_outcomes40 import install_cold_foundation
from tests.test_rules_designations import pick,settle,roundtrip
install_cold_foundation()
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
stage=sys.argv[3];ids=json.loads(sys.argv[4])
assert s.state.rules.decision
if stage=='study':
 pick(s,[ids['low']]);settle(s);assert s.state.players['p1'].life==39
elif stage=='cradle':
 pick(s,['pay']);settle(s);assert s.state.cards[ids['bear']].counters.get('+1/+1')==3
elif stage=='racket':
 assert s.state.rules.decision.player=='p2'
 pick(s,['pay']);settle(s);assert s.state.rules.decision.player=='p3'
 pick(s,['decline']);settle(s);assert s.state.players['p2'].life==39
elif stage=='confidant':
 pick(s,[ids['top']]);settle(s);assert s.state.cards[ids['top']].zone=='p1:hand'
elif stage=='scythe':
 assert s.state.rules.decision.player=='p3' and s.state.cards[ids['first']].zone=='p2:hand'
 pick(s,[ids['second']]);settle(s)
 assert (s.state.players['p2'].life,s.state.players['p3'].life)==(30,34)
else:
 assert s.state.rules.decision.player=='p1'
 pick(s,[ids['spell']]);settle(s);assert s.state.cards[ids['spell']].zone=='p2:graveyard'
assert s.state.rules.decision is None
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(s.cards.db_path), stage, json.dumps(ids)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_racket_reveals_and_finishes_one_opponent_before_next_top(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    put(s, "Protection Racket", "battlefield")
    for name in ["Ancient Brontodon", "Sol Ring"]:
        c = put(s, name, "hand")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=7)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    pick(s, ["pay"])
    settle(s)
    assert s.state.players["p2"].life == 39
    d = s.state.rules.decision
    assert d and d.player == "p3"
    pick(s, ["decline"])
    settle(s)
    assert any(c.name == "Sol Ring" and c.zone == "p1:exile" for c in s.state.cards.values())
    assert any(c.name == "Ancient Brontodon" and c.zone == "p1:hand" for c in s.state.cards.values())
    roundtrip(s)


def test_confidant_actual_private_surveil_then_return_exact_affordable_card(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    put(s, "Enlightened Confidant", "battlefield")
    cast(s, "Healing Salve", ["p1"], modes=[0])
    top = put(s, "Sol Ring", "hand")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    stops(s, "end")
    to_phase(s, "end", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p1" and top.id in {o.id for o in d.options}
    pick(s, [top.id])
    settle(s)
    assert s.state.cards[top.id].zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("has_other", [True, False])
def test_xathrid_mandatory_original_source_exclusion_and_failed_branch(cards, has_other):
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    demon = put(s, "Xathrid Demon", "battlefield")
    if has_other:
        put(s, "Ancient Brontodon", "battlefield")
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=7)
    settle(s)
    assert s.state.rules.decision is None
    if has_other:
        assert (s.state.players["p1"].life, s.state.players["p2"].life, s.state.players["p3"].life) == (
            40,
            31,
            31,
        )
        assert not s.state.cards[demon.id].tapped
    else:
        assert s.state.players["p1"].life == 33 and s.state.cards[demon.id].tapped
    roundtrip(s)


def test_spinal_combat_cast_actual_control_haste_then_delayed_sacrifice_gain(cards):
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    victim = put(s, "Ancient Brontodon", "battlefield", "p2")
    stops(s, "begin_combat", "end")
    to_phase(s, "begin_combat", turn=4)
    cast(s, "Spinal Embrace", [victim.id])
    assert s.state.cards[victim.id].controller == "p1"
    assert "haste" in Plan(s.state, "p1", cards, None).ch(s.state.cards[victim.id]).keywords
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard" and s.state.players["p1"].life == 49
    roundtrip(s)


def test_scythe_real_combat_secret_simultaneous_discards_greatest_tie(cards):
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    source = put(s, "Scythe Specter", "battlefield")
    first = put(s, "Deadly Tempest", "hand", "p2")
    second = put(s, "Deadly Tempest", "hand", "p3")
    put(s, "Island", "hand", "p2")
    put(s, "Island", "hand", "p3")
    stops(s, "combat_damage")
    attack(s, [source], turn=4)
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    pick(s, [first.id])
    settle(s)
    assert s.state.cards[first.id].zone == "p2:hand"
    d = s.state.rules.decision
    assert d and d.player == "p3"
    pick(s, [second.id])
    settle(s)
    assert s.state.cards[first.id].zone == "p2:graveyard" and s.state.cards[second.id].zone == "p3:graveyard"
    assert (s.state.players["p2"].life, s.state.players["p3"].life) == (30, 34)
    roundtrip(s)


def test_soulgorger_records_actual_entry_loss_and_exact_source_return(cards):
    s = game(cards)
    source = cast(s, "Soulgorger Orgg")
    assert s.state.players["p1"].life == 1
    cast(s, "Healing Salve", ["p1"], modes=[0])
    cast(s, "Deadly Tempest")
    assert s.state.cards[source.id].zone == "p1:graveyard"
    # Tempest loses another1 life before the leaving ability gains the original39.
    assert s.state.players["p1"].life == 42
    roundtrip(s)


def test_blitzwing_endstep_uses_gross_target_loss_and_stays_front(cards):
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    name = next(c["name"] for c in DATA if c["name"].startswith("Blitzwing,"))
    s = game(cards)
    source = put(s, name, "battlefield")
    cast(s, "Lightning Bolt", ["p2"])
    stops(s, "end")
    to_phase(s, "end", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d
    pick(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 34 and s.state.cards[source.id].face == 0
    roundtrip(s)


def test_blitzwing_actual_converted_cost_random_back_combat_then_zero_loss_convert(cards):
    from app.rules import alt_costs
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    name = next(c["name"] for c in DATA if c["name"].startswith("Blitzwing,"))
    s = game(cards)
    source = put(s, name, "hand")
    offers = alt_costs.converted_offers(s.state, "p1", source, cards)
    assert len(offers) == 1
    cast(s, name, alt_cost=offers[0].key)
    assert s.state.cards[source.id].face == 1
    stops(s, "begin_combat", "combat_damage", "end")
    to_phase(s, "begin_combat", turn=4)
    settle(s)
    ch = Plan(s.state, "p1", cards, None).ch(s.state.cards[source.id])
    assert "Creature" in ch.types and ("flying" in ch.keywords or "indestructible" in ch.keywords)
    attack(s, [s.state.cards[source.id]], turn=4)
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    assert s.state.cards[source.id].face == 0
    to_phase(s, "end", turn=4)
    settle(s)
    pick(s, ["p3"])
    settle(s)
    assert s.state.players["p3"].life == 40 and s.state.cards[source.id].face == 1
    roundtrip(s)


def test_soulgorger_prohibited_loss_returns_zero_after_prohibition_leaves(cards):
    s = game(cards)
    emperor = cast(s, "Platinum Emperion")
    source = cast(s, "Soulgorger Orgg")
    assert s.state.players["p1"].life == 40
    cast(s, "Disenchant", [emperor.id])
    cast(s, "Murder", [source.id])
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_soulgorger_independent_copied_source_keeps_separate_actual_loss(cards):
    from tests.test_rules_designations import pick, settle

    s = game(cards)
    original = cast(s, "Soulgorger Orgg")
    cast(s, "Healing Salve", ["p1"], modes=[0])
    copy = cast(s, "Clone")
    d = s.state.rules.decision
    assert d and original.id in {o.id for o in d.options}
    pick(s, [original.id])
    settle(s)
    assert s.state.players["p1"].life == 1
    cast(s, "Murder", [copy.id])
    assert s.state.players["p1"].life == 4
    cast(s, "Murder", [original.id])
    assert s.state.players["p1"].life == 43
    roundtrip(s)


def test_belbe_opponent_active_gets_mana_for_departed_opponents_loss(cards):
    from tests.game_helpers import act, mana_pool
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    put(s, "Belbe, Corrupted Observer", "battlefield")
    stops(s, "main1", "main2")
    to_phase(s, "main1", turn=5)
    act(s, "p3", type="set_life", player="p3", value=3)
    cast(s, "Lightning Bolt", ["p3"])
    assert "p3" in s.state.rules.lost
    to_phase(s, "main2", turn=5)
    settle(s)
    assert mana_pool(s, "p2").get("C", 0) == 2 and not mana_pool(s, "p1")
    roundtrip(s)


@pytest.mark.parametrize("decline", [True, False])
def test_confidant_decline_or_expensive_card_never_puts_it_in_hand(cards, decline):
    from tests.game_helpers import act
    from tests.test_rules_designations import pick, settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    put(s, "Enlightened Confidant", "battlefield")
    cast(s, "Healing Salve", ["p1"], modes=[0])
    top = put(s, "Ancient Brontodon", "hand")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    stops(s, "end")
    to_phase(s, "end", turn=4)
    settle(s)
    pick(s, [] if decline else [top.id])
    settle(s)
    assert s.state.cards[top.id].zone == ("p1:library" if decline else "p1:graveyard")
    roundtrip(s)


def test_spinal_blinked_new_incarnation_is_not_sacrificed_or_counted(cards):
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    victim = put(s, "Ancient Brontodon", "battlefield", "p2")
    stops(s, "begin_combat", "end")
    to_phase(s, "begin_combat", turn=4)
    cast(s, "Spinal Embrace", [victim.id])
    cast(s, "Cloudshift", [victim.id])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p1:battlefield" and s.state.players["p1"].life == 40
    roundtrip(s)


def test_xathrid_blinked_new_source_can_pay_old_others_requirement(cards):
    from tests.test_rules_wave30m_durations import stops, to_phase

    s = game(cards)
    source = put(s, "Xathrid Demon", "battlefield")
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=7)
    assert s.state.rules.stack
    cast(s, "Cloudshift", [source.id])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert (s.state.players["p1"].life, s.state.players["p2"].life, s.state.players["p3"].life) == (
        40,
        33,
        33,
    )
    roundtrip(s)


def test_soulgorger_suppressed_enter_trigger_is_known_zero(cards):
    s = game(cards)
    cast(s, "Torpor Orb")
    source = cast(s, "Soulgorger Orgg")
    original = Plan(s.state, "p1", cards, None).oid(source.id)
    assert original in s.state.rules.entry_life_origins
    assert s.state.players["p1"].life == 40
    cast(s, "Murder", [source.id])
    assert s.state.players["p1"].life == 40
    assert not s.state.rules.entry_life_notices
    roundtrip(s)


def test_soulgorger_countered_enter_trigger_is_known_zero(cards):
    from tests.game_helpers import act

    s = game(cards)
    source = cast(s, "Soulgorger Orgg", resolve=False)
    for _ in range(12):
        if s.state.cards[source.id].zone.endswith(":battlefield"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[source.id].zone.endswith(":battlefield")
    trigger = next(cid for cid, entry in s.state.rules.stack.items() if entry.source_card == source.id)
    cast(s, "Stifle", [trigger])
    assert s.state.players["p1"].life == 40
    cast(s, "Murder", [source.id])
    assert s.state.players["p1"].life == 40 and not s.state.rules.entry_life_notices
    roundtrip(s)


def test_soulgorger_legacy_missing_entry_receipt_is_explicitly_unknown(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = game(cards)
    source = cast(s, "Soulgorger Orgg")
    assert s.state.players["p1"].life == 1
    saved = s.state.model_dump(mode="json")
    for key in ["entry_life_losses", "entry_life_origins", "entry_life_notices"]:
        saved["rules"].pop(key, None)
    s = GameSession(GameState.model_validate(saved), cards=cards)
    cast(s, "Murder", [source.id])
    assert s.state.players["p1"].life == 1
    assert len(s.state.rules.entry_life_notices) == 1
    assert "Earlier entry life loss is unavailable" in json.dumps(s.view("p1")["log"])
    roundtrip(s)
