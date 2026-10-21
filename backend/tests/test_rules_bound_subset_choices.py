"""Canonical exact-pool choices preserve actor, target relation and original complements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/bound_subset_choices_cards.json").read_text())
NAMES = [c["name"] for c in DATA[:13]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="bsc", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c["name"] for c in DATA]
    return table(cards, names, names, names)


def cast(s, name, targets=(), pid="p1", **kwargs):
    source = put(s, name, "hand", pid)
    mana(s, pid=pid, C=30, W=8, U=8, B=8, R=8, G=8)
    wait_priority(s, pid)
    if name in ("Barrin's Spite", "Retribution", "Incriminate", "Trial of Agony", "Wake to Slaughter"):
        kwargs.setdefault("target_counts", [len(targets)])
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


def choose(s, values):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=values)
    settle(s)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result.manual_parts


@pytest.mark.parametrize("name", ["Barrin's Spite", "Retribution", "Incriminate", "Trial of Agony"])
def test_pair_choice_actual_effects(cards, name):
    s = game(cards)
    a = put(s, "Siege Mastodon", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    unrelated = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, name, [a.id, b.id])
    d = s.state.rules.decision
    assert d and d.player == "p2" and {o.card_id for o in d.options} == {a.id, b.id}
    roundtrip(s)
    choose(s, [a.id])
    if name == "Trial of Agony":
        assert s.state.cards[a.id].zone == "p2:graveyard"
        assert "cant_block" in chars(s, b).imposed
    else:
        assert s.state.cards[a.id].zone == "p2:graveyard"
        if name == "Barrin's Spite":
            assert s.state.cards[b.id].zone == "p2:hand"
        elif name == "Retribution":
            assert s.state.cards[b.id].counters.get("-1/-1") == 1
        else:
            assert s.state.cards[b.id].zone == "p2:battlefield"
    assert s.state.cards[unrelated.id].zone == "p2:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Goblin War Cry", "Eunuchs' Intrigues"])
def test_choose_one_creature_restricts_only_other_original_objects(cards, name):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    cast(s, name, ["p2"])
    assert s.state.rules.decision.player == "p2"
    choose(s, [a.id])
    assert "cant_block" not in chars(s, a).imposed
    assert "cant_block" in chars(s, b).imposed
    later = put(s, "Llanowar Elves", "battlefield", "p2")
    assert "cant_block" not in chars(s, later).imposed
    roundtrip(s)


def test_monomania_target_chooses_private_keep_and_discards_rest(cards):
    s = game(cards)
    # Clear only this player's random opening cards so the exact pool is meaningful.
    for cid in list(s.state.zones["p2:hand"]):
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "library"})
    kept = put(s, "Sol Ring", "hand", "p2")
    discarded = put(s, "Forest", "hand", "p2")
    cast(s, "Monomania", ["p2"])
    assert s.state.rules.decision.player == "p2"
    choose(s, [kept.id])
    assert s.state.cards[kept.id].zone == "p2:hand"
    assert s.state.cards[discarded.id].zone == "p2:graveyard"
    roundtrip(s)


def test_wake_opponent_keeps_one_in_hand_other_has_haste_and_exiles_at_end(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Centaur Courser", "graveyard")
    cast(s, "Wake to Slaughter", [a.id, b.id], target_counts=[2])
    choose(s, ["p2"])
    assert s.state.rules.decision.player == "p2"
    choose(s, [a.id])
    assert s.state.cards[a.id].zone == "p1:hand"
    assert s.state.cards[b.id].zone == "p1:battlefield"
    assert "haste" in chars(s, b).keywords
    roundtrip(s)
    to_phase(s, "end")
    settle(s)
    assert s.state.cards[b.id].zone == "p1:exile"


def test_fortunate_uses_each_choosers_control_and_preserves_global_chosen_set(cards):
    s = game(cards)
    own = put(s, "Grizzly Bears", "battlefield")
    own_loser = put(s, "Sol Ring", "battlefield")
    two = put(s, "Centaur Courser", "battlefield", "p2")
    two_loser = put(s, "Sol Ring", "battlefield", "p2")
    three = put(s, "Darksteel Myr", "battlefield", "p3")
    land = put(s, "Forest", "battlefield")
    cast(s, "Fortunate Few")
    d = s.state.rules.decision
    assert d.player == "p1" and own.id not in {o.id for o in d.options}
    choose(s, [two.id])
    d = s.state.rules.decision
    assert d.player == "p2" and two_loser.id not in {o.id for o in d.options}
    choose(s, [three.id])
    d = s.state.rules.decision
    assert d.player == "p3" and two.id not in {o.id for o in d.options}
    choose(s, [own.id])
    assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in (own, two, three, land))
    assert s.state.cards[own_loser.id].zone == "p1:graveyard"
    assert s.state.cards[two_loser.id].zone == "p2:graveyard"
    roundtrip(s)


def test_coin_real_two_exile_cost_then_opponent_choice_bottom_and_tapped_entry(cards):
    s = game(cards)
    source = put(s, "Coin of Fate", "battlefield")
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Centaur Courser", "graveyard")
    mana(s, C=3, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, sources=[])
    if s.state.rules.decision is not None:
        choose(s, [a.id, b.id])
    else:
        settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert s.state.cards[a.id].zone == "p1:exile" and s.state.cards[b.id].zone == "p1:exile"
    choose(s, ["p2"])
    assert s.state.rules.decision.player == "p2"
    choose(s, [a.id])
    assert s.state.cards[a.id].zone == "p1:library"
    assert s.state.zones["p1:library"][-1] == a.id
    assert s.state.cards[b.id].zone == "p1:battlefield" and s.state.cards[b.id].tapped
    assert s.state.table.monarch == "p1"
    roundtrip(s)


def test_teferi_real_ultimate_source_dies_chosen_land_bounces_and_owners_shuffle(cards):
    s = game(cards)
    source = put(s, "Teferi, Temporal Pilgrim", "battlefield")
    act(s, "p1", type="set_counter", card_id=source.id, kind="loyalty", value=12)
    chosen = put(s, "Forest", "battlefield", "p2")
    land = put(s, "Island", "battlefield", "p2")
    stolen = put(s, "Grizzly Bears", "battlefield", "p3")
    act(s, "p1", type="set_controller", card_ids=[stolen.id], player="p2")
    own = put(s, "Sol Ring", "battlefield", "p2")
    wait_priority(s, "p1")
    ability = next(a.index for a in chars(s, source).abilities if a.cost and "12" in a.cost)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability, targets=["p2"], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert s.state.rules.decision.player == "p2"
    choose(s, [chosen.id])
    assert s.state.cards[chosen.id].zone == "p2:hand"
    assert s.state.cards[land.id].zone == "p2:battlefield"
    assert s.state.cards[own.id].zone == "p2:library"
    assert s.state.cards[stolen.id].zone == "p3:library"
    roundtrip(s)


def test_kami_real_chapter_three_transforms_then_defender_chooses_graveyard_value(cards):
    s = game(cards)
    # Actual Saga chapter III leaves and returns the card as its back face.
    source = put(s, "The Kami War // O-Kagachi Made Manifest", "battlefield")
    act(s, "p1", type="set_counter", card_id=source.id, kind="lore", value=2)
    to_phase(s, "main1", turn=4)
    settle(s)
    assert s.state.cards[source.id].face == 1
    chosen = put(s, "Siege Mastodon", "graveyard")
    another = put(s, "Sol Ring", "graveyard")
    to_phase(s, "declare_attackers", turn=7)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    assert s.state.rules.decision.player == "p2"
    assert {o.id for o in s.state.rules.decision.options} == {chosen.id, another.id}
    choose(s, [chosen.id])
    assert s.state.cards[chosen.id].zone == "p1:hand"
    assert chars(s, source).pt == (11, 6)
    roundtrip(s)


def test_neyam_real_combat_targets_damaged_players_graveyard_then_opponent_selects_own_pool(cards):
    s = game(cards)
    source = put(s, "Neyam Shai Murad", "battlefield")
    first = put(s, "Forest", "graveyard", "p2")
    own = put(s, "Centaur Courser", "graveyard")
    decoy = put(s, "Sol Ring", "graveyard", "p2")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert first.id in {o.id for o in d.options} and own.id not in {o.id for o in d.options}
    choose(s, [first.id])
    d = s.state.rules.decision
    assert d.player == "p1"
    choose(s, ["yes"])
    # One permanent in our graveyard makes the opponent's choice compulsory.
    assert s.state.cards[first.id].zone == "p2:hand"
    assert s.state.cards[own.id].zone == "p1:battlefield"
    assert s.state.cards[decoy.id].zone == "p2:graveyard"
    roundtrip(s)


def pending_cast(s, name, targets=(), pid="p1", **kwargs):
    source = put(s, name, "hand", pid)
    mana(s, pid=pid, C=30, W=8, U=8, B=8, R=8, G=8)
    wait_priority(s, pid)
    if name in ("Barrin's Spite", "Retribution", "Incriminate", "Trial of Agony", "Wake to Slaughter"):
        kwargs.setdefault("target_counts", [len(targets)])
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), sources=[], **kwargs)
    return source


@pytest.mark.parametrize("name", ["Barrin's Spite", "Retribution", "Incriminate", "Trial of Agony"])
def test_one_illegal_target_forces_surviving_target_not_unrelated_creature(cards, name):
    s = game(cards)
    a = put(s, "Siege Mastodon", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    unrelated = put(s, "Grizzly Bears", "battlefield", "p2")
    pending_cast(s, name, [a.id, b.id])
    act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "hand"})
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == "p2:graveyard"
    assert s.state.cards[b.id].zone == "p2:hand"
    assert not s.state.cards[unrelated.id].counters and "cant_block" not in chars(s, unrelated).imposed
    roundtrip(s)


@pytest.mark.parametrize("name", ["Barrin's Spite", "Retribution", "Incriminate"])
@pytest.mark.parametrize("barred", [1, 2])
def test_sacrifice_choice_excludes_impossible_options_and_both_barred_has_no_other(cards, name, barred):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    suit = put(s, "Assault Suit", "battlefield", "p2")
    act(s, "p2", type="attach", card_ids=[suit.id], to=a.id)
    if barred == 2:
        suit2 = put(s, "Assault Suit", "battlefield", "p3")
        act(s, "p3", type="attach", card_ids=[suit2.id], to=b.id)
    cast(s, name, [a.id, b.id])
    assert s.state.rules.decision is None
    if barred == 2:
        assert s.state.cards[a.id].zone == "p2:battlefield" and s.state.cards[b.id].zone == "p2:battlefield"
        assert not s.state.cards[a.id].counters and not s.state.cards[b.id].counters
    else:
        assert s.state.cards[b.id].zone == "p2:graveyard"
        assert s.state.cards[a.id].zone == ("p2:hand" if name == "Barrin's Spite" else "p2:battlefield")
        if name == "Retribution":
            assert s.state.cards[a.id].counters.get("-1/-1") == 1
    roundtrip(s)


def test_sacrifice_replacement_still_freezes_other_before_selected_leaves(cards):
    s = game(cards)
    put(s, "Rest in Peace", "battlefield")
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    cast(s, "Barrin's Spite", [a.id, b.id])
    choose(s, [a.id])
    assert s.state.cards[a.id].zone == "p2:exile"
    assert s.state.cards[b.id].zone == "p2:hand"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Barrin's Spite", "Trial of Agony"])
def test_same_controller_target_relation_rejects_mixed_controller_pair(cards, name):
    from app.game.errors import ActionError

    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p3")
    with pytest.raises(ActionError):
        pending_cast(s, name, [a.id, b.id])


def test_wake_single_legal_target_is_hand_return_not_battlefield(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Centaur Courser", "graveyard")
    pending_cast(s, "Wake to Slaughter", [a.id, b.id])
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "hand"})
    settle(s)
    choose(s, ["p2"])
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == "p1:hand" and s.state.cards[b.id].zone == "p1:hand"
    roundtrip(s)


def test_wake_zero_targets_does_not_return_other_graveyard_card(cards):
    s = game(cards)
    untouched = put(s, "Grizzly Bears", "graveyard")
    cast(s, "Wake to Slaughter", [], target_counts=[0])
    if s.state.rules.decision:
        choose(s, ["p2"])
    assert s.state.cards[untouched.id].zone == "p1:graveyard"
    roundtrip(s)


def test_pair_controller_change_before_resolution_invalidates_relation(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    spell = pending_cast(s, "Barrin's Spite", [a.id, b.id])
    act(s, "p2", type="set_controller", card_ids=[a.id], player="p3")
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == "p3:battlefield" and s.state.cards[b.id].zone == "p2:battlefield"
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("stage", ["spite", "monomania", "wake", "retribution"])
def test_exact_pool_choices_resume_in_a_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(cards)
    picks = []
    expected = {}
    if stage == "spite":
        a = put(s, "Grizzly Bears", "battlefield", "p2")
        b = put(s, "Centaur Courser", "battlefield", "p2")
        cast(s, "Barrin's Spite", [a.id, b.id])
        picks = [a.id]
        expected = {a.id: "p2:graveyard", b.id: "p2:hand"}
    elif stage == "monomania":
        for cid in list(s.state.zones["p2:hand"]):
            act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "library"})
        a = put(s, "Sol Ring", "hand", "p2")
        b = put(s, "Forest", "hand", "p2")
        cast(s, "Monomania", ["p2"])
        picks = [a.id]
        expected = {a.id: "p2:hand", b.id: "p2:graveyard"}
    elif stage == "wake":
        a = put(s, "Grizzly Bears", "graveyard")
        b = put(s, "Centaur Courser", "graveyard")
        cast(s, "Wake to Slaughter", [a.id, b.id])
        choose(s, ["p2"])
        picks = [a.id]
        expected = {a.id: "p1:hand", b.id: "p1:battlefield"}
    else:
        put(s, "Doubling Season", "battlefield", "p2")
        a = put(s, "Grizzly Bears", "battlefield", "p2")
        b = put(s, "Siege Mastodon", "battlefield", "p2")
        cast(s, "Retribution", [a.id, b.id])
        picks = [a.id]
        expected = {a.id: "p2:graveyard", b.id: "p2:battlefield"}
    assert s.state.rules.decision
    saved = tmp_path / f"{stage}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_bound_subset_choices import choose
from tests.test_rules_designations import roundtrip
save,db,picks,expected,stage=sys.argv[1:]
picks,expected=json.loads(picks),json.loads(expected)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
choose(s,picks)
assert all(s.state.cards[cid].zone==zone for cid,zone in expected.items())
if stage=='wake':
 from tests.test_rules_wave30m_durations import to_phase
 from tests.test_rules_designations import settle
 from tests.test_rules_wave6c_tokens_pumps import chars
 cid=next(cid for cid,zone in expected.items() if zone.endswith(':battlefield'))
 assert 'haste' in chars(s,s.state.cards[cid]).keywords
 to_phase(s,'end');settle(s)
 assert s.state.cards[cid].zone=='p1:exile'
if stage=='retribution':
 cid=next(cid for cid,zone in expected.items() if zone.endswith(':battlefield'))
 assert s.state.cards[cid].counters['-1/-1']==2
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            json.dumps(picks),
            json.dumps(expected),
            stage,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_actual_spell_copy_keeps_pair_relation_and_original_becomes_illegal(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    original = pending_cast(s, "Barrin's Spite", [a.id, b.id])
    cast(s, "Reverberate", [original.id], pid="p2")
    # Native copying asks whether to change the copy's targets.
    d = s.state.rules.decision
    if d and {o.id for o in d.options} & {"keep", "no", "same"}:
        choose(s, [next(o.id for o in d.options if o.id in ("keep", "no", "same"))])
    d = s.state.rules.decision
    assert d and d.player == "p2" and {o.id for o in d.options} == {a.id, b.id}
    choose(s, [a.id])
    assert s.state.cards[a.id].zone == "p2:graveyard"
    assert s.state.cards[b.id].zone == "p2:hand"
    assert s.state.cards[original.id].zone == "p1:graveyard"
    roundtrip(s)


def test_wake_actual_printed_flashback_retains_other_new_object_until_end(cards):
    s = game(cards)
    source = put(s, "Wake to Slaughter", "graveyard")
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Centaur Courser", "graveyard")
    mana(s, C=4, B=1, R=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[a.id, b.id], target_counts=[2], sources=[])
    settle(s)
    choose(s, ["p2"])
    choose(s, [a.id])
    assert s.state.cards[source.id].zone == "p1:exile"
    old = s.state.rules.object_id(b.id)
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.rules.object_id(b.id) != old
    to_phase(s, "end")
    settle(s)
    assert s.state.cards[b.id].zone == "p1:battlefield"
    assert "haste" not in chars(s, s.state.cards[b.id]).keywords
    roundtrip(s)


def test_warcry_restrictions_expire_and_do_not_follow_new_incarnations(cards):
    s = game(cards)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Centaur Courser", "battlefield", "p2")
    cast(s, "Goblin War Cry", ["p2"])
    choose(s, [a.id])
    assert "cant_block" in chars(s, b).imposed
    act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "battlefield"})
    assert "cant_block" not in chars(s, s.state.cards[b.id]).imposed
    to_phase(s, "upkeep", turn=2)
    assert "cant_block" not in chars(s, s.state.cards[b.id]).imposed
    roundtrip(s)


def test_retribution_native_counter_replacement_order_survives_a_cold_save(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    put(s, "Doubling Season", "battlefield", "p2")
    put(s, "Winding Constrictor", "battlefield", "p2")
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Siege Mastodon", "battlefield", "p2")
    cast(s, "Retribution", [a.id, b.id])
    choose(s, [a.id])
    d = s.state.rules.decision
    assert d and d.player == "p2" and "616.1" in d.prompt
    saved = tmp_path / "replacement-order.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_bound_subset_choices import choose
from tests.test_rules_designations import roundtrip
save,db,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
choose(s,[d.options[0].id])
assert s.state.cards[cid].counters['-1/-1'] in (3,4)
assert s.state.cards[cid].zone=='p2:battlefield'
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), b.id],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_monomania_kept_choice_is_private_to_target(cards):
    s = game(cards)
    a = put(s, "Sol Ring", "hand", "p2")
    put(s, "Forest", "hand", "p2")
    cast(s, "Monomania", ["p2"])
    own = s.view("p2")["rules"]["decision"]
    assert a.id in {o["id"] for o in own["options"]}
    for pid in ("p1", "p3"):
        waiting = s.view(pid)["rules"]["decision"]
        assert not waiting.get("options") and "resume" not in waiting
    choose(s, [a.id])
    roundtrip(s)


def test_coin_new_exile_incarnation_is_not_the_paid_exiled_object(cards):
    s = game(cards)
    source = put(s, "Coin of Fate", "battlefield")
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Centaur Courser", "graveyard")
    mana(s, C=3, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, sources=[])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    old = s.state.rules.object_id(b.id)
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "exile"})
    assert s.state.rules.object_id(b.id) != old
    settle(s)
    choose(s, ["p2"])
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == "p1:library"
    assert s.state.cards[b.id].zone == "p1:exile"
    assert s.state.table.monarch == "p1"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Goblin War Cry", "Eunuchs' Intrigues"])
def test_no_creatures_does_not_ask_for_an_impossible_selection(cards, name):
    s = game(cards)
    cast(s, name, ["p2"])
    assert s.state.rules.decision is None
    roundtrip(s)
