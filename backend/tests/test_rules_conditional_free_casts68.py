"""Native conditional zero-mana permissions and complete printed cards."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    "Omnipresence",
    "Aluren",
    "Fires of Invention",
    "Vision, Spectral Synthezoid",
    "Weftwalking",
    "Once Upon a Time",
    "World War Hulk",
]
SUPPORT = [
    "Lightning Bolt",
    "Shock",
    "Blaze",
    "Fling",
    "K-9, Mark I",
    "Forest",
    "Island",
    "Sol Ring",
    "Llanowar Elves",
    "Divination",
    "Giant Growth",
    "Centaur Courser",
    "Disperse",
    "Murder",
    "Darksteel Myr",
    "Doubling Season",
    "Skaab Ruinator",
    "Vedalken Orrery",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for filename in [
        "exile_outcomes42_cards.json",
        "exile_cast_outcomes45_cards.json",
        "fight_exile_receipts65_cards.json",
        "immediate_cast_pools67_cards.json",
        "conditional_free_casts68_cards.json",
    ]:
        for i, c in enumerate(
            json.loads((Path(__file__).parent / "fixtures" / filename).read_text())
        ):
            base[c["name"]] = card(
                c["name"],
                set_code="cf68",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = gameplay.setup(cards, *NAMES, *SUPPORT)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    return s


def clear(s):
    act(s, "p1", type="clear_mana")


def free(s, name, pid="p1", **kw):
    source = put(s, name, "hand", pid)
    act(s, pid, type="cast_spell", card_id=source.id, free=True, **kw)
    settle(s)
    return source


@pytest.mark.parametrize("name", NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_omnipresence_actual_creature_count_limits_free_hand_spells(cards):
    s = setup(cards)
    cast(s, "Omnipresence")
    put(s, "Grizzly Bears", "battlefield")
    clear(s)
    free(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p2"].life == 37
    too_large = put(s, "Centaur Courser", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=too_large.id, free=True)
    assert s.state.cards[too_large.id].zone == "p1:hand"
    roundtrip(s)


def test_aluren_opponent_casts_small_creature_during_source_controllers_turn(cards):
    s = setup(cards)
    cast(s, "Aluren")
    clear(s)
    wait_priority(s, "p2")
    bear = free(s, "Grizzly Bears", "p2")
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    assert s.state.turn.active_player == "p1"
    assert not s.state.players["p2"].mana
    roundtrip(s)


def test_aluren_flash_permission_cannot_be_used_for_paid_cast(cards):
    s = setup(cards)
    cast(s, "Aluren")
    clear(s)
    wait_priority(s, "p2")
    bear = put(s, "Grizzly Bears", "hand", "p2")
    mana(s, "p2", C=1, G=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bear.id)
    assert s.state.cards[bear.id].zone == "p2:hand"
    roundtrip(s)


def test_fires_counts_itself_and_all_earlier_casts_for_two_limit(cards):
    s = setup(cards)
    cast(s, "Fires of Invention")
    put(s, "Forest", "battlefield")
    put(s, "Island", "battlefield")
    clear(s)
    free(s, "Grizzly Bears")
    bolt = put(s, "Lightning Bolt", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])
    assert s.state.cards[bolt.id].zone == "p1:hand"
    roundtrip(s)


def test_vision_robot_branch_once_during_own_turn(cards):
    s = setup(cards)
    cast(s, "Vision, Spectral Synthezoid")
    clear(s)
    robot = free(s, "K-9, Mark I")
    assert s.state.cards[robot.id].zone == "p1:battlefield"
    bolt = put(s, "Lightning Bolt", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_weftwalking_paid_entry_shuffles_hand_and_graveyard_draws_seven(cards):
    s = setup(cards)
    hand = put(s, "Shock", "hand")
    grave = put(s, "Lightning Bolt", "graveyard")
    before = len(s.state.zones["p1:library"])
    old_hand_and_graveyard = len(s.state.zones["p1:hand"]) + len(
        s.state.zones["p1:graveyard"]
    )

    source = cast(s, "Weftwalking")
    assert len(s.state.zones["p1:hand"]) == 7
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert s.state.cards[hand.id].zone in ["p1:library", "p1:hand"]
    assert s.state.cards[grave.id].zone in ["p1:library", "p1:hand"]
    assert len(s.state.zones["p1:library"]) == before + old_hand_and_graveyard - 1 - 7
    roundtrip(s)


def test_once_first_game_cast_reveals_creature_and_randomly_bottoms_rest(cards):
    s = setup(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest", "Shock", "Blaze", "Sol Ring"])
    source = free(s, "Once Upon a Time")
    d = s.state.rules.decision
    assert d and d.resume["step"] == "pick_looked"
    answer(s, [top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:hand"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert set(s.state.zones["p1:library"][-4:]) == set(top[1:])
    roundtrip(s)


def test_world_chapter_one_next_matching_spell_consumed_after_nonmatching_cast(cards):
    s = setup(cards)
    source = cast(s, "World War Hulk")
    clear(s)
    cast(s, "Lightning Bolt", targets=["p2"])
    clear(s)
    creature = free(s, "Llanowar Elves")
    assert s.state.cards[creature.id].zone == "p1:battlefield"
    bear = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    assert s.state.cards[source.id].counters["lore"] == 1
    roundtrip(s)


@pytest.mark.parametrize("seq,turn", [(2, 1), (0, 2)])
def test_raw_table_start_cannot_claim_complete_game_history_outside_fresh_boundary(
    cards, seq, turn
):
    from app.game.factory import PlayerSetup, new_game
    from app.game.rules_state import start_rules
    from tests.game_helpers import deck

    state = new_game(
        [
            PlayerSetup(
                name="Alice",
                cards=deck(
                    cards, "Krenko, Mob Boss", [(1, "Once Upon a Time"), (10, "Forest")]
                ),
            )
        ],
        shuffle=False,
    )
    state.seq = seq
    state.turn.number = turn
    rules = start_rules(state)
    assert rules.cast_history_complete is None
    roundtrip_state = type(state).model_validate_json(state.model_dump_json())
    assert roundtrip_state.rules.cast_history_complete is None


def test_legacy_marker_missing_and_empty_history_cannot_claim_first_spell(cards):
    from app.game.state import GameState

    s = setup(cards)
    saved = s.state.model_dump(mode="json")
    saved["rules"].pop("cast_history_complete")
    assert (
        saved["rules"]["named_casts_game"] == {}
        and saved["rules"]["turn_log"]["casts"] == []
    )
    s.state = GameState.model_validate(saved)
    assert s.state.rules.cast_history_complete is None
    source = put(s, "Once Upon a Time", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    to_phase(s, "main1", turn=4)
    assert s.state.rules.cast_history_complete is None
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    roundtrip(s)


def test_once_prior_paid_spell_persists_game_history_after_next_turn(cards):
    s = setup(cards)
    assert s.state.rules.cast_history_complete is True
    cast(s, "Lightning Bolt", targets=["p2"])
    clear(s)
    source = put(s, "Once Upon a Time", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    to_phase(s, "main1", turn=4)
    assert s.state.rules.turn_log.casts == []
    assert s.state.rules.named_casts_game["p1"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    roundtrip(s)


def test_vision_nonrobot_creature_cannot_use_free_permission(cards):
    s = setup(cards)
    cast(s, "Vision, Spectral Synthezoid")
    clear(s)
    bear = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    free(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_weftwalking_each_own_turn_first_spell_and_earlier_paid_casts_count(cards):
    s = setup(cards)
    cast(s, "Weftwalking")
    clear(s)
    own = put(s, "Lightning Bolt", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=own.id, free=True, targets=["p2"])
    to_phase(s, "main1", turn=2)
    wait_priority(s, "p2")
    foreign = free(s, "Llanowar Elves", "p2")
    assert s.state.cards[foreign.id].zone == "p2:battlefield"
    another = put(s, "Grizzly Bears", "hand", "p2")
    wait_priority(s, "p2")
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=another.id, free=True)
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=own.id, free=True, targets=["p2"])
    roundtrip(s)


def test_world_all_three_native_chapters_and_eventual_saga_departure(cards):
    s = setup(cards)
    source = cast(s, "World War Hulk")
    clear(s)
    creature = free(s, "Llanowar Elves")
    to_phase(s, "main1", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and creature.id in [o.id for o in d.options]
    answer(s, [creature.id])
    settle(s)
    assert s.state.cards[creature.id].counters["+1/+1"] == 3
    to_phase(s, "main1", turn=7)
    settle(s)
    d = s.state.rules.decision
    assert d and creature.id in [o.id for o in d.options]
    answer(s, [creature.id])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    from app.rules import characteristics, layers

    ch = layers.derive(
        s.state,
        s.state.cards[creature.id],
        characteristics.of(s.state.cards[creature.id], s.cards),
        s.cards,
    )
    assert ch.pt == (8, 8) and "trample" in ch.keywords
    roundtrip(s)


def test_omnipresence_counts_current_controlled_creatures_and_loses_authority(
    cards,
):
    s = setup(cards)
    source = cast(s, "Omnipresence")
    first = put(s, "Grizzly Bears", "battlefield")
    second = put(s, "Llanowar Elves", "battlefield")
    clear(s)
    spell = put(s, "Centaur Courser", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, free=True)
    cast(s, "Disperse", targets=[first.id])
    clear(s)
    too_big = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=too_big.id, free=True)
    cast(s, "Disperse", targets=[source.id])
    clear(s)
    bolt = put(s, "Lightning Bolt", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])
    assert s.state.cards[second.id].zone == "p1:battlefield"
    roundtrip(s)


def test_aluren_free_response_is_not_auto_passed_over(cards):
    from app.rules import casting

    s = setup(cards)
    cast(s, "Aluren")
    clear(s)
    bear = put(s, "Grizzly Bears", "hand", "p2")
    act(s, "p2", type="set_prefs", response="auto", hold_priority=False)
    mana(s, R=1)
    spell = put(s, "Shock", "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p3"])
    assert casting.has_responses(s.state, "p2", s.cards)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    assert casting.free_castable(s.state, "p2", s.state.cards[bear.id], s.cards)
    assert not casting.castable(s.state, "p2", s.state.cards[bear.id], s.cards)
    act(s, "p2", type="cast_spell", card_id=bear.id, free=True)
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    assert s.state.players["p3"].life == 38
    roundtrip(s)


def test_aluren_independent_flash_source_still_allows_paid_creature(cards):
    s = setup(cards)
    cast(s, "Aluren")
    cast(s, "Vedalken Orrery")
    clear(s)
    to_phase(s, "main1", turn=2)
    wait_priority(s, "p1")
    bear = put(s, "Grizzly Bears", "hand")
    mana(s, C=1, G=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.turn.active_player == "p2"
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_aluren_free_creature_still_requires_three_graveyard_exiles(cards):
    s = setup(cards)
    cast(s, "Aluren")
    clear(s)
    source = put(s, "Skaab Ruinator", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    paid = [
        put(s, n, "graveyard").id
        for n in ["Grizzly Bears", "Llanowar Elves", "Centaur Courser"]
    ]
    act(s, "p1", type="cast_spell", card_id=source.id, free=True)
    settle(s)
    d = s.state.rules.decision
    if d:
        answer(s, paid)
        settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert all(s.state.cards[c].zone == "p1:exile" for c in paid)
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_world_next_matching_permission_survives_source_departure(
    cards,
):
    s = setup(cards)
    source = cast(s, "World War Hulk")
    cast(s, "Disperse", targets=[source.id])
    clear(s)
    assert s.state.cards[source.id].zone == "p1:hand"
    free(s, "Llanowar Elves")
    bear = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    roundtrip(s)


def test_world_next_matching_spell_cannot_be_saved_by_paying_normally(cards):
    s = setup(cards)
    cast(s, "World War Hulk")
    cast(s, "Llanowar Elves")
    clear(s)
    bear = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    roundtrip(s)


def test_fires_arriving_as_third_spell_counts_all_prior_casts(cards):
    s = setup(cards)
    cast(s, "Lightning Bolt", targets=["p2"])
    cast(s, "Shock", targets=["p2"])
    source = cast(s, "Fires of Invention")
    clear(s)
    put(s, "Forest", "battlefield")
    put(s, "Island", "battlefield")
    bear = put(s, "Grizzly Bears", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id, free=True)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_fires_offturn_forbids_paid_spell_but_does_not_limit_opponents(cards):
    s = setup(cards)
    cast(s, "Fires of Invention")
    clear(s)
    to_phase(s, "main1", turn=2)
    wait_priority(s, "p1")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    wait_priority(s, "p2")
    foreign = put(s, "Shock", "hand", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=foreign.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 38
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_genuine_cold_static_or_stored_free_cast_authority(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    s = setup(cards)
    pid = "p1"
    victim = "p2"
    creature = False
    if name == "Once Upon a Time":
        stack_library(s, ["Grizzly Bears", "Forest", "Shock", "Blaze", "Sol Ring"])
        candidate = put(s, name, "hand")
    elif name == "Omnipresence":
        cast(s, name)
        put(s, "Grizzly Bears", "battlefield")
        candidate = put(s, "Lightning Bolt", "hand")
    elif name == "Aluren":
        cast(s, name)
        pid = "p2"
        victim = "p3"
        creature = True
        candidate = put(s, "Grizzly Bears", "hand", pid)
        wait_priority(s, pid)
    elif name == "Fires of Invention":
        cast(s, name)
        put(s, "Forest", "battlefield")
        put(s, "Island", "battlefield")
        candidate = put(s, "Grizzly Bears", "hand")
        creature = True
    elif name == "Vision, Spectral Synthezoid":
        cast(s, name)
        candidate = put(s, "Lightning Bolt", "hand")
    elif name == "Weftwalking":
        cast(s, name)
        to_phase(s, "main1", turn=2)
        pid = "p2"
        victim = "p3"
        candidate = put(s, "Lightning Bolt", "hand", pid)
        wait_priority(s, pid)
    else:
        source = cast(s, name)
        cast(s, "Disperse", targets=[source.id])
        candidate = put(s, "Llanowar Elves", "hand")
        creature = True
    clear(s)
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
cid,pid,victim,name=sys.argv[3:7];creature=sys.argv[7]=='True'
assert s.state.cards[cid].zone==pid+':hand'
kw={} if creature or name=='Once Upon a Time' else {'targets':[victim]}
act(s,pid,type='cast_spell',card_id=cid,free=True,**kw);settle(s)
if name=='Once Upon a Time':
 d=s.state.rules.decision
 assert d and d.resume['step']=='pick_looked'
 picked=next(o.id for o in d.options if s.state.cards[o.id].name=='Grizzly Bears')
 answer(s,[picked]);settle(s)
 assert s.state.cards[picked].zone==pid+':hand'
elif creature:
 assert s.state.cards[cid].zone==pid+':battlefield'
else:
 assert s.state.players[victim].life==37
assert not s.state.players[pid].mana
roundtrip(s)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            candidate.id,
            pid,
            victim,
            name,
            str(creature),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
