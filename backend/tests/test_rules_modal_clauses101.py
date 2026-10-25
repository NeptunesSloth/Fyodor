"""Native modal choices, source damage, designation removal and spell-only protection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build as _build
from tests.wave9c_kit import check
from tests.wave100c_kit import (
    cast,
    chars,
    move,
    one,
    pt_of,
    put_on,
    settle,
    start_cast,
    to_phase,
    walker,
    zone,
)

NAMES = ["Gix's Command", "Deadly Complication", "Compel Brutality", "Display of Dominance"]
DATA = json.loads((Path(__file__).parent / "fixtures/modal_clauses101_cards.json").read_text())


@pytest.fixture
def cards(settings):
    existing = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        fields = {k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")}
        existing[c["name"]] = card(c["name"], set_code="m101", number=str(i), **fields)
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, mine=(), theirs=()):
    s = _build(cards, mine, theirs, forests=20, islands=20)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    return s


def pick(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def advance_question(s):
    for _ in range(30):
        if s.state.rules.decision:
            return s.state.rules.decision
        if not s.state.zones.get("stack"):
            raise AssertionError("No resolution question")
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("No question")


@pytest.mark.parametrize("name", NAMES)
def test_whole_canonical_card101(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_gix_untargeted_choice_can_choose_shroud_then_later_destroy_uses_new_power101(cards):
    s = build(cards, ["Gix's Command", "Grizzly Bears"], ["Deadly Insect", "Llanowar Elves"])
    bear, insect, elf = (
        put_on(s, "Grizzly Bears"),
        put_on(s, "Deadly Insect", "p2"),
        put_on(s, "Llanowar Elves", "p2"),
    )
    start_cast(s, "Gix's Command", modes=[0, 1], B=2, C=3)
    d = advance_question(s)
    assert d.min_choices == 0 and d.max_choices == 1 and insect.id in [o.id for o in d.options]
    assert not s.state.rules.stack[next(iter(s.state.rules.stack))].targets
    pick(s, [insect.id])
    settle(s)
    assert s.state.cards[insect.id].counters["+1/+1"] == 2
    assert "lifelink" in chars(s, insect).keywords and pt_of(s, insect) == (8, 3)
    assert zone(s, bear) == "p1:graveyard" and zone(s, elf) == "p2:graveyard"
    check(s)


def test_gix_first_mode_selects_at_resolution_counter_before_destroy_and_grant_expires101(cards):
    s = build(cards, ["Gix's Command", "Grizzly Bears"], ["Hill Giant"])
    bear, giant = put_on(s, "Grizzly Bears"), put_on(s, "Hill Giant", "p2")
    start_cast(s, "Gix's Command", modes=[0, 1], B=2, C=3)
    advance_question(s)
    pick(s, [bear.id])
    settle(s)
    assert pt_of(s, bear) == (4, 4) and zone(s, giant) == "p2:battlefield"
    assert "lifelink" in chars(s, bear).keywords
    to_phase(s, "main1", turn=2)
    assert "lifelink" not in chars(s, bear).keywords and bear.counters["+1/+1"] == 2
    check(s)


def test_gix_optional_zero_and_counter_prohibition_still_grants_lifelink101(cards):
    for none in (False, True):
        s = build(cards, ["Gix's Command", "Grizzly Bears", "Solemnity"], [])
        bear = put_on(s, "Grizzly Bears")
        put_on(s, "Solemnity")
        start_cast(s, "Gix's Command", modes=[0, 2], target_counts=[0], B=2, C=3)
        advance_question(s)
        pick(s, [] if none else [bear.id])
        settle(s)
        assert bear.counters.get("+1/+1", 0) == 0
        assert ("lifelink" in chars(s, bear).keywords) == (not none)
        check(s)


def suspected_bear(cards):
    s = build(cards, ["Deadly Complication", "Reasonable Doubt", "Opt", "Grizzly Bears"], ["Hill Giant"])
    bear, giant = put_on(s, "Grizzly Bears"), put_on(s, "Hill Giant", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    opt = start_cast(s, "Opt", U=1)
    cast(s, "Reasonable Doubt", targets=[opt.id, bear.id], target_counts=[1, 1], prefer=["decline"], U=1, C=1)
    assert "menace" in chars(s, bear).keywords
    return s, bear, giant


@pytest.mark.parametrize("decline", [False, True])
def test_deadly_both_modes_native_suspected_target_and_optional_removal101(cards, decline):
    s, bear, giant = suspected_bear(cards)
    cast(
        s,
        "Deadly Complication",
        modes=[0, 1],
        targets=[giant.id, bear.id],
        target_counts=[1, 1],
        prefer=["decline" if decline else "pay"],
        B=1,
        R=1,
        C=1,
    )
    assert zone(s, giant) == "p2:graveyard" and bear.counters["+1/+1"] == 1
    assert ("menace" in chars(s, bear).keywords) == decline
    check(s)


def test_deadly_second_mode_rejects_unsuspected_or_foreign_creature_atomically101(cards):
    s = build(cards, ["Deadly Complication", "Grizzly Bears"], ["Hill Giant"])
    bear, giant = put_on(s, "Grizzly Bears"), put_on(s, "Hill Giant", "p2")
    for target in (bear.id, giant.id):
        source = move(s, one(s, "Deadly Complication"), "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "R": 1, "C": 1})
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=source.id, modes=[1], targets=[target])
        assert s.state.model_dump(mode="json") == before


def test_compel_planeswalker_damage_uses_loyalty_and_actual_source101(cards):
    s = build(cards, ["Compel Brutality", "Jace Beleren"], ["Colossal Dreadmaw"])
    jace, victim = walker(s, "Jace Beleren", loyalty=5), put_on(s, "Colossal Dreadmaw", "p2")
    cast(s, "Compel Brutality", modes=[1], targets=[jace.id, victim.id], target_counts=[1, 1], G=1, C=1)
    assert s.state.cards[victim.id].damage == 5 and jace.counters["loyalty"] == 5
    check(s)


def test_compel_first_mode_creature_deals_damage_to_planeswalker101(cards):
    s = build(cards, ["Compel Brutality", "Grizzly Bears"], ["Jace Beleren"])
    bear, jace = put_on(s, "Grizzly Bears"), walker(s, "Jace Beleren", "p2", loyalty=5)
    cast(s, "Compel Brutality", modes=[0], targets=[bear.id, jace.id], target_counts=[1, 1], G=1, C=1)
    assert jace.counters["loyalty"] == 3
    check(s)


def test_compel_blue_planeswalker_source_protection_prevents_damage101(cards):
    s = build(cards, ["Compel Brutality", "Jace Beleren"], ["Scryb Ranger"])
    jace, ranger = walker(s, "Jace Beleren", loyalty=5), put_on(s, "Scryb Ranger", "p2")
    cast(s, "Compel Brutality", modes=[1], targets=[jace.id, ranger.id], target_counts=[1, 1], G=1, C=1)
    assert zone(s, ranger) == "p2:battlefield" and ranger.damage == 0
    check(s)


def test_display_first_mode_destroys_blue_noncreature_but_not_creature101(cards):
    s = build(cards, ["Display of Dominance"], ["Jace Beleren", "Prodigal Sorcerer"])
    jace, sorcerer = walker(s, "Jace Beleren", "p2", loyalty=5), put_on(s, "Prodigal Sorcerer", "p2")
    cast(s, "Display of Dominance", modes=[0], targets=[jace.id], G=1, C=1)
    assert zone(s, jace) == "p2:graveyard" and zone(s, sorcerer) == "p2:battlefield"
    check(s)


def test_display_second_mode_blocks_opponent_blue_spell_allows_own_and_late_permanent101(cards):
    s = build(
        cards,
        ["Display of Dominance", "Grizzly Bears", "Unsummon", "Llanowar Elves"],
        ["Unsummon", "Hill Giant"],
    )
    bear = put_on(s, "Grizzly Bears")
    cast(s, "Display of Dominance", modes=[1], G=1, C=1)
    elf = put_on(s, "Llanowar Elves")
    assert "untargetable_opp_spells:UB" in chars(s, bear).imposed, (
        s.state.rules.effects,
        chars(s, bear).imposed,
    )
    assert "untargetable_opp_spells:UB" in chars(s, elf).imposed, (
        s.state.rules.effects,
        chars(s, elf).imposed,
    )
    enemy = move(s, one(s, "Unsummon", "p2"), "hand")
    opponent = put_on(s, "Hill Giant", "p2")
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    for target in (bear.id, elf.id):
        with pytest.raises(ActionError):
            act(s, "p2", type="cast_spell", card_id=enemy.id, targets=[target])
    act(s, "p2", type="cast_spell", card_id=enemy.id, targets=[opponent.id])
    settle(s)
    assert zone(s, opponent) == "p2:hand"
    cast(s, "Unsummon", targets=[bear.id], U=1)
    assert zone(s, bear) == "p1:hand"
    check(s)


def test_compel_lost_planeswalker_target_does_not_deal_lki_damage101(cards):
    s = build(cards, ["Compel Brutality", "Jace Beleren", "Boomerang"], ["Colossal Dreadmaw"])
    jace, victim = walker(s, "Jace Beleren", loyalty=5), put_on(s, "Colossal Dreadmaw", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    start_cast(s, "Compel Brutality", modes=[1], targets=[jace.id, victim.id], target_counts=[1, 1], G=1, C=1)
    cast(s, "Boomerang", targets=[jace.id], U=2)
    assert zone(s, jace) == "p1:hand" and victim.damage == 0
    check(s)


def cold(s, tmp_path, code, ids):
    import subprocess
    import sys

    import app

    saved = tmp_path / "modal101.json"
    saved.write_text(s.state.model_dump_json())
    source = (
        """import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave100c_kit import settle,to_phase,move
from tests.test_rules_bandmate_references import wait_priority
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
"""
        + code
        + "\nrepo.close()\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", source, str(saved), str(s.cards.db_path), json.dumps(ids)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_genuine_cold_gix_original_nontarget_choice101(cards, tmp_path):
    s = build(cards, ["Gix's Command", "Grizzly Bears"], ["Deadly Insect"])
    bear, insect = put_on(s, "Grizzly Bears"), put_on(s, "Deadly Insect", "p2")
    start_cast(s, "Gix's Command", modes=[0, 1], B=2, C=3)
    advance_question(s)
    cold(
        s,
        tmp_path,
        """d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[m['insect']]);settle(s)
c=s.state.cards[m['insect']]
assert c.counters['+1/+1']==2 and 'lifelink' in Plan.view(s.state,'p1',repo).ch(c).keywords
assert s.state.cards[m['bear']].zone=='p1:graveyard'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"bear": bear.id, "insect": insect.id},
    )


def test_genuine_cold_display_dynamic_rule_then_expires101(cards, tmp_path):
    from tests.test_rules_bandmate_references import wait_priority

    s = build(cards, ["Display of Dominance", "Grizzly Bears"], ["Unsummon", "Hill Giant"])
    bear, giant = put_on(s, "Grizzly Bears"), put_on(s, "Hill Giant", "p2")
    enemy = move(s, one(s, "Unsummon", "p2"), "hand")
    cast(s, "Display of Dominance", modes=[1], G=1, C=1)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    cold(
        s,
        tmp_path,
        """try:act(s,'p2',type='cast_spell',card_id=m['spell'],targets=[m['bear']])
except ActionError:pass
else:raise AssertionError('blue spell targeted protected creature')
act(s,'p2',type='cast_spell',card_id=m['spell'],targets=[m['giant']]);settle(s)
assert s.state.cards[m['giant']].zone=='p2:hand'
to_phase(s,'main1',turn=2)
move(s,s.state.cards[m['spell']],'hand');wait_priority(s,'p2')
act(s,'p2',type='add_mana',player='p2',mana={'U':1})
act(s,'p2',type='cast_spell',card_id=m['spell'],targets=[m['bear']]);settle(s)
assert s.state.cards[m['bear']].zone=='p1:hand'
""",
        {"spell": enemy.id, "giant": giant.id, "bear": bear.id},
    )


def test_display_actual_opponent_blue_ability_is_not_prohibited101(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = build(cards, ["Display of Dominance", "Grizzly Bears"], ["Prodigal Sorcerer"])
    bear, wizard = put_on(s, "Grizzly Bears"), put_on(s, "Prodigal Sorcerer", "p2")
    to_phase(s, "main1", turn=2)
    wait_priority(s, "p1")
    cast(s, "Display of Dominance", modes=[1], G=1, C=1)
    wait_priority(s, "p2")
    act(s, "p2", type="activate_ability", card_id=wizard.id, ability=0, targets=[bear.id], sources=[])
    settle(s)
    assert bear.damage == 1 and zone(s, bear) == "p1:battlefield"
    check(s)


def test_display_existing_blue_spell_loses_its_only_target_on_resolution101(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = build(cards, ["Display of Dominance", "Grizzly Bears"], ["Unsummon"])
    bear = put_on(s, "Grizzly Bears")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    enemy = start_cast(s, "Unsummon", pid="p2", targets=[bear.id], U=1)
    wait_priority(s, "p1")
    cast(s, "Display of Dominance", modes=[1], G=1, C=1)
    assert zone(s, bear) == "p1:battlefield" and zone(s, enemy) == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("cold_restore", [False, True])
def test_actual_concession_restores_controller_without_changing_gix_chosen_object101(
    cards, tmp_path, cold_restore
):
    from tests.wave100c_kit import three

    s = three(cards, ["Gix's Command"], ["Control Magic"], ["Grizzly Bears"])
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    bear = put_on(s, "Grizzly Bears", "p3")
    to_phase(s, "main1", turn=2)
    start_cast(s, "Control Magic", pid="p2", targets=[bear.id], U=2, C=2)
    settle(s)
    assert s.state.cards[bear.id].controller == "p2"
    to_phase(s, "main1", turn=4)
    start_cast(s, "Gix's Command", modes=[0, 1], B=2, C=3)
    advance_question(s)
    original = s.state.rules.object_id(bear.id)
    act(s, "p2", type="concede")
    assert s.state.rules.object_id(bear.id) == original and s.state.cards[bear.id].controller == "p3"
    assert s.state.rules.decision and bear.id in [o.id for o in s.state.rules.decision.options]
    if cold_restore:
        cold(
            s,
            tmp_path,
            """d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[m['bear']]);settle(s)
c=s.state.cards[m['bear']]
assert c.zone=='p3:battlefield' and c.counters['+1/+1']==2
assert 'lifelink' in Plan.view(s.state,'p1',repo).ch(c).keywords
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
            {"bear": bear.id},
        )
    else:
        pick(s, [bear.id])
        settle(s)
        assert s.state.cards[bear.id].zone == "p3:battlefield"
        assert s.state.cards[bear.id].counters["+1/+1"] == 2 and "lifelink" in chars(s, bear).keywords
        check(s)


def test_concession_stale_gix_artifact_option_no_longer_creature_is_not_modified101(cards):
    from tests.wave100c_kit import three

    s = three(cards, ["Gix's Command"], ["March of the Machines"], ["Sol Ring"])
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    artifact = put_on(s, "Sol Ring", "p3")
    to_phase(s, "main1", turn=2)
    start_cast(s, "March of the Machines", pid="p2", U=1, C=3)
    settle(s)
    assert chars(s, artifact).is_creature
    to_phase(s, "main1", turn=4)
    start_cast(s, "Gix's Command", modes=[0, 1], B=2, C=3)
    advance_question(s)
    original = s.state.rules.object_id(artifact.id)
    act(s, "p2", type="concede")
    assert s.state.rules.object_id(artifact.id) == original and not chars(s, artifact).is_creature
    pick(s, [artifact.id])
    settle(s)
    assert not artifact.counters and "lifelink" not in chars(s, artifact).keywords
    assert zone(s, artifact) == "p3:battlefield"
    check(s)
