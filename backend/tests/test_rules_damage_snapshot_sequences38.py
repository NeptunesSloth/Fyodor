"""Independent canonical gameplay proofs for printed damage sequences."""

from __future__ import annotations

import pytest

from app.rules import sba
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, cast
from tests.test_rules_damage_snapshots38 import cards as cards
from tests.test_rules_damage_snapshots38 import setup
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


def test_command_real_cross_graveyard_cards_damage_then_return_under_caster(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    beast = put(s, "Colossal Dreadmaw", "graveyard", "p2")
    cast(s, "Command the Dreadhorde", [bear.id, beast.id], target_counts=[2])
    assert s.state.players["p1"].life == 32
    assert all(
        s.state.cards[c.id].zone.endswith(":battlefield") and s.state.cards[c.id].controller == "p1"
        for c in (bear, beast)
    )
    roundtrip(s)


def test_command_illegal_target_excluded_from_damage_and_return(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    beast = put(s, "Colossal Dreadmaw", "graveyard", "p2")
    cast(s, "Command the Dreadhorde", [bear.id, beast.id], target_counts=[2], resolve=False)
    act(s, "p2", type="move", card_ids=[beast.id], to={"player": "p2", "zone": "hand"})
    settle(s)
    assert s.state.players["p1"].life == 38
    assert s.state.cards[beast.id].zone.endswith(":hand")
    assert s.state.cards[bear.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_exorcist_real_exiled_card_is_damage_source(cards):
    s = setup(cards)
    source = put(s, "Selfless Exorcist", "battlefield")
    victim = put(s, "Grizzly Bears", "graveyard", "p2")
    to_phase(s, "main1", turn=4)
    activate(s, source, "Exile target creature", [victim.id])
    assert s.state.cards[victim.id].zone.endswith(":exile")
    assert s.state.cards[source.id].damage == 2
    roundtrip(s)


def test_creature_bond_reads_departed_creature_toughness_not_base(cards):
    s = setup(cards)
    creature = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, "Creature Bond", [creature.id])
    cast(s, "Giant Growth", [creature.id], pid="p2")
    cast(s, "Murder", [creature.id])
    assert s.state.players["p2"].life == 35
    assert s.state.cards[creature.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_leeches_removes_actual_poison_then_deals_that_amount(cards):
    s = setup(cards)
    act(s, "p1", type="set_resource", player="p2", key="poison", value=5)
    cast(s, "Leeches", ["p2"])
    assert s.state.players["p2"].resources.get("poison", 0) == 0
    assert s.state.players["p2"].life == 35
    roundtrip(s)


@pytest.mark.parametrize("cleaved", [False, True])
def test_lantern_flare_printed_normal_count_and_cleave_x(cards, cleaved):
    s = setup(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Runeclaw Bear", "battlefield")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    flare = put(s, "Lantern Flare", "hand")
    cast(s, "Lantern Flare", [target.id], **({"alt_cost": f"{flare.id}:0", "x_value": 4} if cleaved else {}))
    n = 4 if cleaved else 2
    assert s.state.cards[target.id].damage == n
    assert s.state.players["p1"].life == 40 + n
    roundtrip(s)


def test_chainer_all_three_chapters_damage_gain_then_real_token_source(cards):
    s = setup(cards)
    saga = cast(s, "Chainer's Torment")
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [42, 38, 38]
    to_phase(s, "main1", turn=4)
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [44, 36, 36]
    to_phase(s, "main1", turn=7)
    settle(s)
    nightmares = [
        c
        for c in s.state.cards.values()
        if c.token and c.name == "Nightmare Horror" and c.zone.endswith(":battlefield")
    ]
    assert len(nightmares) == 1
    assert chars(s, nightmares[0]).power == chars(s, nightmares[0]).toughness == "22"
    assert s.state.players["p1"].life == 22
    assert s.state.cards[saga.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_chainer_doubled_tokens_each_deal_frozen_x_with_native_prevention(cards):
    s = setup(cards)
    cast(s, "Chainer's Torment")
    to_phase(s, "main1", turn=4)
    settle(s)
    cast(s, "Doubling Season")
    to_phase(s, "upkeep", turn=7)
    cast(s, "Safe Passage")
    to_phase(s, "main1", turn=7)
    settle(s)
    nightmares = [
        c
        for c in s.state.cards.values()
        if c.token and c.name == "Nightmare Horror" and c.zone.endswith(":battlefield")
    ]
    assert len(nightmares) == 2
    assert all(chars(s, c).power == chars(s, c).toughness == "22" for c in nightmares)
    assert s.state.players["p1"].life == 44
    roundtrip(s)


def test_frantic_counts_instants_sorceries_and_adventure_once(cards):
    s = setup(cards)
    for name in ["Shock", "Safe Passage", "Bonecrusher Giant // Stomp"]:
        put(s, name, "graveyard")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    cast(s, "Frantic Firebolt", [target.id])
    assert s.state.cards[target.id].damage == 5
    roundtrip(s)


def test_structural_assault_includes_prior_artifact_death_not_indestructible(cards):
    s = setup(cards)
    earlier = put(s, "Memnite", "battlefield", "p2")
    cast(s, "Shock", [earlier.id])
    ring = put(s, "Sol Ring", "battlefield")
    ingot = put(s, "Darksteel Ingot", "battlefield")
    survivor = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    bear = put(s, "Runeclaw Bear", "battlefield")
    cast(s, "Structural Assault")
    assert s.state.cards[ring.id].zone.endswith(":graveyard")
    assert s.state.cards[ingot.id].zone.endswith(":battlefield")
    assert s.state.cards[survivor.id].damage == 2
    assert s.state.cards[bear.id].zone.endswith(":graveyard")
    roundtrip(s)


@pytest.mark.parametrize("mount", [False, True])
def test_saddle_pumps_or_adds_counter_before_creature_damage(cards, mount):
    s = setup(cards)
    own = put(s, "Bridled Bighorn" if mount else "Grizzly Bears", "battlefield")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    before = int(chars(s, own).power)
    cast(s, "Throw from the Saddle", [own.id, target.id], target_counts=[1, 1])
    assert s.state.cards[target.id].damage == before + 1
    assert s.state.cards[own.id].counters.get("+1/+1", 0) == int(mount)
    roundtrip(s)


def test_showstopping_surprise_target_creature_deals_to_each_other_creature(cards):
    s = setup(cards)
    own = put(s, "Grizzly Bears", "battlefield")
    friend = put(s, "Runeclaw Bear", "battlefield")
    target = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    cast(s, "Showstopping Surprise", [own.id])
    assert s.state.cards[own.id].damage == 0
    assert s.state.cards[friend.id].zone.endswith(":graveyard")
    assert s.state.cards[target.id].damage == 2
    roundtrip(s)


def test_refuse_deals_spell_mana_value_without_countering_spell(cards):
    s = setup(cards)
    source = cast(
        s, "Giant Growth", [put(s, "Grizzly Bears", "battlefield", "p2").id], pid="p2", resolve=False
    )
    cast(s, "Refuse // Cooperate", [source.id], face=0)
    assert s.state.players["p2"].life == 39
    assert s.state.cards[source.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_cooperate_actual_aftermath_copies_spell_then_exiles_self(cards):
    s = setup(cards)
    copy = put(s, "Refuse // Cooperate", "graveyard")
    source = cast(s, "Lightning Bolt", ["p3"], pid="p2", resolve=False)
    from tests.test_rules_bandmate_references import mana, wait_priority

    mana(s, U=3, C=4)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=copy.id, face=1, targets=[source.id], sources=[])
    settle(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        keep = next((o.id for o in d.options if "keep" in o.label.lower()), None)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[keep] if keep else [])
        settle(s)
    assert s.state.players["p3"].life == 34
    assert s.state.cards[copy.id].zone.endswith(":exile")
    roundtrip(s)


@pytest.mark.parametrize("stage", ["command", "bond", "chainer", "structural"])
def test_printed_damage_sequences_resume_saved_game_in_fresh_process(cards, tmp_path, stage):
    import json
    import subprocess
    import sys
    from pathlib import Path

    s = setup(cards)
    ids = {}
    if stage == "command":
        bear = put(s, "Grizzly Bears", "graveyard", "p2")
        cast(s, "Command the Dreadhorde", [bear.id], target_counts=[1], resolve=False)
        ids = {"bear": bear.id}
    elif stage == "bond":
        bear = put(s, "Grizzly Bears", "battlefield", "p2")
        cast(s, "Creature Bond", [bear.id])
        cast(s, "Giant Growth", [bear.id], pid="p2")
        cast(s, "Murder", [bear.id], resolve=False)
    elif stage == "chainer":
        cast(s, "Chainer's Torment")
        to_phase(s, "main1", turn=4)
        settle(s)
        assert s.state.players["p1"].life == 44
        to_phase(s, "upkeep", turn=7)
    else:
        earlier = put(s, "Memnite", "battlefield", "p2")
        cast(s, "Shock", [earlier.id])
        put(s, "Sol Ring", "battlefield")
        creature = put(s, "Colossal Dreadmaw", "battlefield", "p2")
        cast(s, "Structural Assault", resolve=False)
        ids = {"creature": creature.id}
    saved = tmp_path / f"{stage}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
from tests.test_rules_wave30m_durations import to_phase
save,db,stage,raw=sys.argv[1:]
ids=json.loads(raw)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if stage=='chainer':to_phase(s,'main1',turn=7)
settle(s)
if stage=='command':
 assert s.state.players['p1'].life==38
 assert s.state.cards[ids['bear']].controller=='p1' and s.state.cards[ids['bear']].zone.endswith(':battlefield')
elif stage=='bond':assert s.state.players['p2'].life==35
elif stage=='chainer':
 assert s.state.players['p1'].life==22
 assert sum(c.name=='Nightmare Horror' and c.token and c.zone.endswith(':battlefield') for c in s.state.cards.values())==1
else:assert s.state.cards[ids['creature']].damage==2
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, json.dumps(ids)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_command_lethal_damage_then_platinum_angel_enters_before_sba(cards):
    s = setup(cards)
    angel = put(s, "Platinum Angel", "graveyard", "p2")
    beast = put(s, "Colossal Dreadmaw", "graveyard")
    act(s, "p1", type="set_life", player="p1", value=2)
    cast(s, "Command the Dreadhorde", [angel.id, beast.id], target_counts=[2])
    assert s.state.players["p1"].life == -11
    assert "p1" not in s.state.rules.lost
    assert s.state.cards[angel.id].zone.endswith(":battlefield")
    assert s.state.cards[angel.id].controller == "p1"
    assert s.state.cards[beast.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_chainer_doubled_modified_power_tokens_each_deal_original_x(cards):
    s = setup(cards)
    cast(s, "Chainer's Torment")
    to_phase(s, "main1", turn=4)
    settle(s)
    cast(s, "Doubling Season")
    cast(s, "Glorious Anthem")
    cast(s, "Platinum Angel")
    to_phase(s, "main1", turn=7)
    settle(s)
    nightmares = [
        c
        for c in s.state.cards.values()
        if c.token and c.name == "Nightmare Horror" and c.zone.endswith(":battlefield")
    ]
    assert len(nightmares) == 2
    assert all(
        sba.power(s.state.cards[c.id], chars(s, c)) == sba.toughness(s.state.cards[c.id], chars(s, c)) == 23
        for c in nightmares
    )
    assert s.state.players["p1"].life == 0  # 44-22-22, not44-23-23
    assert "p1" not in s.state.rules.lost
    roundtrip(s)


def test_exorcist_reads_creature_card_current_exile_cda_power(cards):
    s = setup(cards)
    source = put(s, "Selfless Exorcist", "battlefield")
    victim = put(s, "Lhurgoyf", "graveyard", "p2")
    put(s, "Grizzly Bears", "graveyard")
    to_phase(s, "main1", turn=4)
    assert sba.power(s.state.cards[victim.id], chars(s, victim)) == 2
    activate(s, source, "Exile target creature", [victim.id])
    assert s.state.cards[victim.id].zone.endswith(":exile")
    assert sba.power(s.state.cards[victim.id], chars(s, victim)) == 1
    assert s.state.cards[source.id].damage == 1
    roundtrip(s)


def test_exorcist_departed_source_is_not_replaced_by_new_recipient(cards):
    s = setup(cards)
    source = put(s, "Selfless Exorcist", "battlefield")
    victim = put(s, "Grizzly Bears", "graveyard", "p2")
    to_phase(s, "main1", turn=4)
    activate(s, source, "Exile target creature", [victim.id], resolve=False)
    cast(s, "Murder", [source.id], pid="p2")
    assert s.state.cards[source.id].zone.endswith(":graveyard")
    assert s.state.cards[victim.id].zone.endswith(":exile")
    assert s.state.cards[source.id].damage == 0
    roundtrip(s)
