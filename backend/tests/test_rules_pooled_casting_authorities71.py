"""Actual linked and current-turn pools keep source, use and hidden information."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import can_see
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

JACOB = "Jacob Hauken, Inspector // Hauken's Insight"
NAMES = [JACOB, "Dawnhand Dissident", "Maralen, Fae Ascendant", "Coram, the Undertaker"]
SUPPORT = [
    "Grizzly Bears",
    "Llanowar Elves",
    "Forest",
    "Lightning Bolt",
    "Sol Ring",
    "Demon of Catastrophes",
    "Falco Spara, Pactweaver",
    "Disperse",
    "Vitalize",
    "Faerie Mastermind",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for filename in [
        "exile_outcomes42_cards.json",
        "exile_cast_outcomes45_cards.json",
        "fight_exile_receipts65_cards.json",
        "top_library_authorities69_cards.json",
        "pooled_casting_authorities71_cards.json",
    ]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="pc71",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, *SUPPORT)


@pytest.mark.parametrize("name", [n for n in NAMES if n != "Dawnhand Dissident"])
def test_canonical_full_scout(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def test_jacob_actual_front_exile_transform_and_free_back_cast_share_source_scope(cards):
    s = setup(cards)
    source = cast(s, JACOB)
    to_phase(s, "main1", turn=4)
    settle(s)
    target = put(s, "Grizzly Bears", "hand")
    mana(s, C=4, U=2)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{T}:"))
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "exile_hand_down", d
    answer(s, [target.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "pay_or_sacrifice", d
    answer(s, ["pay"])
    settle(s)
    assert s.state.cards[source.id].face == 1
    linked = s.state.rules.exiled_with[s.state.rules.object_id(source.id)]
    target = next(
        c for c in s.state.cards.values() if c.zone == "p1:exile" and s.state.rules.object_id(c.id) in linked
    )
    assert target.name == "Grizzly Bears"
    assert s.state.cards[target.id].zone == "p1:exile"
    assert can_see(s.state, s.state.cards[target.id], "p1")
    assert not can_see(s.state, s.state.cards[target.id], "p2")
    act(s, "p1", type="clear_mana")
    act(s, "p1", type="cast_spell", card_id=target.id, free=True)
    settle(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_maralen_actual_two_exiles_stamp_exact_turn_and_union_count_not_two_for_itself(cards):
    s = setup(cards)
    put(s, "Llanowar Elves", "battlefield", pid="p2")
    top = stack_library(s, ["Sol Ring", "Grizzly Bears", "Forest"], pid="p2")
    source = cast(s, "Maralen, Fae Ascendant")
    d = s.state.rules.decision
    assert d and d.resume["step"] == "trigger_target", d
    answer(s, ["p2"])
    settle(s)
    oid = s.state.rules.object_id(source.id)
    assert all(s.state.cards[c].zone == "p2:exile" for c in top[:2])
    assert len(s.state.rules.exiled_with[oid]) == 2
    assert len(s.state.rules.linked_exile_turns71[oid]) == 2
    act(s, "p1", type="clear_mana")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[1], free=True)
    assert s.state.model_dump(mode="json") == before
    from app.rules.casting import has_responses
    from app.rules.view import hints

    assert top[1] not in hints(s.state, "p1", cards)["free_castable"]
    assert not has_responses(s.state, "p1", cards)
    act(s, "p1", type="cast_spell", card_id=top[0], free=True)
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:battlefield"
    assert s.state.cards[top[0]].owner == "p2"
    roundtrip(s)


def test_coram_actual_attack_mills_each_library_then_land_and_foreign_spell_have_separate_uses(cards):
    s = setup(cards)
    source = cast(s, "Coram, the Undertaker")
    to_phase(s, "declare_attackers", turn=4)
    top1 = stack_library(s, ["Forest", "Sol Ring"])
    top2 = stack_library(s, ["Lightning Bolt", "Forest"], pid="p2")
    top3 = stack_library(s, ["Grizzly Bears", "Forest"], pid="p3")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    assert all(s.state.cards[c].zone.endswith(":graveyard") for c in [top1[0], top2[0], top3[0]])
    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[source.id]).pt[0] == 2
    to_phase(s, "main2", turn=4)
    settle(s)
    act(s, "p1", type="play_land", card_id=top1[0])
    settle(s)
    mana(s, R=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=top2[0], targets=["p3"])
    settle(s)
    assert s.state.players["p3"].life == 37
    assert s.state.cards[top1[0]].zone == "p1:battlefield"
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top3[0])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def jacob_two(s):
    source = cast(s, JACOB)
    to_phase(s, "main1", turn=4)
    settle(s)
    bear = put(s, "Grizzly Bears", "hand")
    land = put(s, "Forest", "hand")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{T}:"))
    settle(s)
    answer(s, [bear.id])
    settle(s)
    mana(s, C=4, U=2)
    d = s.state.rules.decision
    # The optional payment was offered only if mana was already available.
    if d is not None:
        answer(s, ["decline"])
    cast(s, "Vitalize")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{T}:"))
    settle(s)
    answer(s, [land.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "pay_or_sacrifice"
    answer(s, ["pay"])
    settle(s)
    assert s.state.cards[source.id].face == 1
    linked = s.state.rules.exiled_with[s.state.rules.object_id(source.id)]
    pool = {
        c.name: c.id
        for c in s.state.cards.values()
        if c.zone == "p1:exile" and s.state.rules.object_id(c.id) in linked
    }
    assert set(pool) == {"Grizzly Bears", "Forest"}
    return source, pool


@pytest.mark.parametrize("first", ["land", "spell"])
def test_jacob_two_real_front_exiles_remain_linked_through_transform_and_share_one_land_or_spell_use(
    cards, first
):
    s = setup(cards)
    source, pool = jacob_two(s)
    act(s, "p1", type="clear_mana")
    if first == "land":
        act(s, "p1", type="play_land", card_id=pool["Forest"])
    else:
        act(s, "p1", type="cast_spell", card_id=pool["Grizzly Bears"], free=True)
    settle(s)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        if first == "land":
            act(s, "p1", type="cast_spell", card_id=pool["Grizzly Bears"], free=True)
        else:
            act(s, "p1", type="play_land", card_id=pool["Forest"])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_maralen_current_turn_only_and_no_history_invention_for_old_saved_pool(cards):
    from app.game.state import GameState

    s = setup(cards)
    top = stack_library(s, ["Sol Ring", "Grizzly Bears"], pid="p2")
    cast(s, "Maralen, Fae Ascendant")
    answer(s, ["p2"])
    settle(s)
    old = s.state.model_dump(mode="json")
    old["rules"].pop("linked_exile_turns71")
    s.state = GameState.model_validate(old)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[0], free=True)
    assert s.state.model_dump(mode="json") == before
    # A new turn cannot turn unknown or old exile provenance into a fresh receipt.
    to_phase(s, "main1", turn=2)
    settle(s)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[0], free=True)
    assert s.state.model_dump(mode="json") == before


def test_maralen_bounce_recast_creates_new_scope_and_fresh_once_use_without_old_cards(cards):
    s = setup(cards)
    old_top = stack_library(s, ["Sol Ring", "Grizzly Bears"], pid="p2")
    source = cast(s, "Maralen, Fae Ascendant")
    answer(s, ["p2"])
    settle(s)
    old_oid = s.state.rules.object_id(source.id)
    act(s, "p1", type="cast_spell", card_id=old_top[0], free=True)
    settle(s)
    cast(s, "Disperse", targets=[source.id])
    put(s, "Llanowar Elves", "battlefield")
    new_top = stack_library(s, ["Sol Ring", "Forest"], pid="p3")
    source = cast(s, "Maralen, Fae Ascendant")
    answer(s, ["p3"])
    settle(s)
    assert s.state.rules.object_id(source.id) != old_oid
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=old_top[1], free=True)
    assert s.state.model_dump(mode="json") == before
    act(s, "p1", type="cast_spell", card_id=new_top[0], free=True)
    settle(s)
    assert s.state.cards[new_top[0]].zone == "p1:battlefield"
    roundtrip(s)


def test_maralen_native_old_turn_instant_is_not_fresh_but_opponent_turn_flash_trigger_creates_new_authority(
    cards,
):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    old_top = stack_library(s, ["Lightning Bolt", "Grizzly Bears"], pid="p2")
    cast(s, "Maralen, Fae Ascendant")
    answer(s, ["p2"])
    settle(s)
    to_phase(s, "main1", turn=2)
    settle(s)
    wait_priority(s, "p1")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=old_top[0], targets=["p3"], free=True)
    assert s.state.model_dump(mode="json") == before
    from app.rules.casting import has_responses
    from app.rules.view import hints

    assert old_top[0] not in hints(s.state, "p1", cards)["free_castable"]
    assert not has_responses(s.state, "p1", cards)
    new_top = stack_library(s, ["Lightning Bolt", "Sol Ring"], pid="p3")
    mana(s, C=1, U=1)
    fairy = put(s, "Faerie Mastermind", "hand")
    act(s, "p1", type="cast_spell", card_id=fairy.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "trigger_target"
    answer(s, ["p3"])
    settle(s)
    act(s, "p1", type="clear_mana")
    wait_priority(s, "p1")
    from app.rules.casting import free_castable, has_responses

    assert free_castable(s.state, "p1", s.state.cards[new_top[0]], s.cards, check_priority=False)
    assert has_responses(s.state, "p1", s.cards)
    assert new_top[1] not in hints(s.state, "p1", cards)["free_castable"]
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=new_top[1], free=True)
    assert s.state.model_dump(mode="json") == before
    act(s, "p1", type="cast_spell", card_id=new_top[0], targets=["p2"], free=True)
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[new_top[0]].zone == "p3:graveyard"
    wait_priority(s, "p1")
    assert new_top[1] not in hints(s.state, "p1", cards)["free_castable"]
    assert not has_responses(s.state, "p1", cards)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=new_top[1], free=True)
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_coram_rejects_cards_put_in_graveyard_from_hand_without_invented_library_arrival(cards):
    s = setup(cards)
    cast(s, "Coram, the Undertaker")
    bolt = put(s, "Lightning Bolt", "hand", pid="p2")
    act(s, "p2", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, R=1)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p3"])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def coram_ready(s):
    source = cast(s, "Coram, the Undertaker")
    to_phase(s, "declare_attackers", turn=4)
    own = stack_library(s, ["Forest", "Sol Ring"])
    other = stack_library(s, ["Lightning Bolt", "Forest"], pid="p2")
    third = stack_library(s, ["Grizzly Bears", "Forest"], pid="p3")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    to_phase(s, "main2", turn=4)
    settle(s)
    return source, own[0], other[0], third[0]


def test_coram_native_bounce_recast_has_new_independent_spell_use(cards):
    s = setup(cards)
    source, land, bolt, bear = coram_ready(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt, targets=["p3"])
    settle(s)
    old_oid = s.state.rules.object_id(source.id)
    cast(s, "Disperse", targets=[source.id])
    cast(s, "Coram, the Undertaker")
    assert s.state.rules.object_id(source.id) != old_oid
    mana(s, C=1, G=1)
    act(s, "p1", type="cast_spell", card_id=bear)
    settle(s)
    assert s.state.cards[bear].zone == "p1:battlefield"
    assert s.state.cards[bear].owner == "p3"
    act(s, "p1", type="play_land", card_id=land)
    settle(s)
    assert s.state.cards[land].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("mode", ["jacob", "coram", "maralen", "maralen_spent"])
def test_actual_cold_linked_or_graveyard_authority_and_saved_use(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    if mode == "jacob":
        source, pool = jacob_two(s)
        first, second = pool["Forest"], pool["Grizzly Bears"]
        act(s, "p1", type="clear_mana")
    elif mode == "coram":
        source, land, first, second = coram_ready(s)
        act(s, "p1", type="play_land", card_id=land)
        settle(s)
        mana(s, R=1, G=1, C=1)
    else:
        top = stack_library(s, ["Sol Ring", "Lightning Bolt"], pid="p2")
        cast(s, "Maralen, Fae Ascendant")
        answer(s, ["p2"])
        settle(s)
        first, second = top
        act(s, "p1", type="clear_mana")
        if mode == "maralen_spent":
            act(s, "p1", type="cast_spell", card_id=first, free=True)
            settle(s)
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from app.game.visibility import can_see
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
mode,first,second=sys.argv[3:6]
if mode=='jacob':
 assert can_see(s.state,s.state.cards[first],'p1') and not can_see(s.state,s.state.cards[first],'p2')
 act(s,'p1',type='play_land',card_id=first);settle(s)
 assert s.state.cards[first].zone=='p1:battlefield'
 payload={'type':'cast_spell','card_id':second,'free':True}
elif mode=='coram':
 act(s,'p1',type='cast_spell',card_id=first,targets=['p3']);settle(s)
 assert s.state.players['p3'].life==37
 payload={'type':'cast_spell','card_id':second}
else:
 if mode=='maralen':
  act(s,'p1',type='cast_spell',card_id=first,free=True);settle(s)
 assert s.state.cards[first].zone=='p1:battlefield' and s.state.cards[first].owner=='p2'
 payload={'type':'cast_spell','card_id':second,'free':True,'targets':['p3']}
before=s.state.model_dump(mode='json')
try:act(s,'p1',**payload)
except ActionError:pass
else:raise AssertionError('The same native permission was spent twice')
assert s.state.model_dump(mode='json')==before
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode, first, second],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_coram_foreign_graveyard_is_offered_only_with_native_current_arrival_authority(cards):
    from app.rules.casting import has_responses
    from app.rules.view import hints

    s = setup(cards)
    source, land, bolt, bear = coram_ready(s)
    mana(s, R=1)
    offered = hints(s.state, "p1", cards)
    assert bolt in offered["castable"]
    assert land in offered["playable_lands"]
    assert has_responses(s.state, "p1", cards)
    invalid = put(s, "Sol Ring", "hand", pid="p2")
    act(s, "p2", type="move", card_ids=[invalid.id], to={"player": "p2", "zone": "graveyard"})
    assert invalid.id not in hints(s.state, "p1", cards)["castable"]
    act(s, "p1", type="cast_spell", card_id=bolt, targets=["p3"])
    settle(s)
    assert bear not in hints(s.state, "p1", cards)["castable"]
    roundtrip(s)


def test_foreign_face_down_linked_pool_never_becomes_external_hint_or_response(cards):
    from app.rules.casting import has_responses
    from app.rules.pooled_casting_authorities71 import external_candidates

    s = setup(cards)
    source, pool = jacob_two(s)
    assert not can_see(s.state, s.state.cards[pool["Grizzly Bears"]], "p2")
    assert pool["Grizzly Bears"] not in external_candidates(s.state, "p2", cards)
    assert pool["Forest"] not in external_candidates(s.state, "p2", cards)
    assert not has_responses(s.state, "p2", cards)
    roundtrip(s)


def test_coram_arrival_oid_does_not_follow_a_card_through_hand_back_to_graveyard(cards):
    from app.rules.view import hints

    s = setup(cards)
    source, land, bolt, bear = coram_ready(s)
    original = s.state.rules.object_id(bolt)
    act(s, "p2", type="move", card_ids=[bolt], to={"player": "p2", "zone": "hand"})
    act(s, "p2", type="move", card_ids=[bolt], to={"player": "p2", "zone": "graveyard"})
    assert s.state.rules.object_id(bolt) != original
    mana(s, R=1)
    assert bolt not in hints(s.state, "p1", cards)["castable"]
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt, targets=["p3"])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_coram_spell_use_survives_control_change_but_land_use_remains_independent(cards):
    from app.rules.view import hints
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    source, land, bolt, bear = coram_ready(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt, targets=["p3"])
    settle(s)
    oid = s.state.rules.object_id(source.id)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    act(s, "p2", type="set_controller", card_ids=[source.id], player="p1")
    assert s.state.rules.object_id(source.id) == oid
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    assert bear not in hints(s.state, "p1", cards)["castable"]
    assert land in hints(s.state, "p1", cards)["playable_lands"]
    act(s, "p1", type="play_land", card_id=land)
    settle(s)
    roundtrip(s)
