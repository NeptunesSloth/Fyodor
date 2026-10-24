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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads(
    (Path(__file__).parent / "fixtures/fight_receipts90_cards.json").read_text()
)
NAMES = [c["name"] for c in DATA[:3]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="f90",
            number=str(i),
            **{k: v for k, v in c.items() if k != "name"},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup90(cards, observer="Neyith of the Dire Hunt"):
    names = [c["name"] for c in DATA] + ["Slip Out the Back"]
    s = table(cards, names, names, names)
    source = put(s, observer, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    wall = put(s, "Wall of Roots", "battlefield", pid="p2")
    orn = put(s, "Ornithopter", "battlefield")
    other_orn = put(s, "Ornithopter", "battlefield", pid="p2")
    start(s)
    return s, source, bear, elf, wall, orn, other_orn


def fight90(s, a, b):
    spell = put(s, "Pit Fight" if a.controller == "p1" else "Blood Feud", "hand")
    mana(s, **({"C": 1, "G": 1} if a.controller == "p1" else {"C": 4, "R": 2}))
    wait_priority(s, "p1")
    before = len(s.state.zones["p1:hand"])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[a.id, b.id],
        target_counts=[1, 1],
    )
    settle(s)
    return before


def pick90(s, ids):
    for _ in range(60):
        if s.state.rules.decision is not None:
            pick(s, ids)
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no target decision")


@pytest.mark.parametrize("name", NAMES)
def test_whole90(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_real_fight_spell_draw_and_both_original_participants90(cards):
    s, _, bear, _, wall, _, _ = setup90(cards)
    before = fight90(s, bear, wall)
    assert len(s.state.zones["p1:hand"]) == before
    assert set(s.state.rules.turn_log.fought90) == {
        Plan(s.state, "p1", s.cards, None).oid(bear),
        Plan(s.state, "p1", s.cards, None).oid(wall),
    }
    assert bear.damage == 0 and wall.damage == 2


def test_zero_power_fight_is_genuine_and_draws90(cards):
    s, _, _, _, _, orn, other = setup90(cards)
    before = fight90(s, orn, other)
    assert len(s.state.zones["p1:hand"]) == before
    assert len(s.state.rules.turn_log.fought90) == 2 and orn.damage == other.damage == 0
    from tests.test_rules_designations import roundtrip

    roundtrip(s)


def test_prevented_both_friendly_fighters_count_once90(cards):
    s, _, bear, elf, _, _, _ = setup90(cards)
    safe = put(s, "Safe Passage", "hand")
    mana(s, C=2, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=safe.id)
    settle(s)
    before = fight90(s, bear, elf)
    assert len(s.state.zones["p1:hand"]) == before
    assert bear.damage == elf.damage == 0 and bear.zone == elf.zone == "p1:battlefield"
    assert len(s.state.rules.turn_log.fought90) == 2
    from tests.test_rules_designations import roundtrip

    roundtrip(s)


def test_actual_regent_cast_optional_etb_fight_delayed_counters90(cards):
    s, source, _, _, wall, _, _ = setup90(cards, NAMES[1])
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    mana(s, C=5, G=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    pick90(s, [wall.id])
    settle(s)
    payment90(s, "yes")
    assert source.zone == "p1:battlefield" and wall.damage == 4
    assert len(s.state.rules.delayed) == 1 and not source.counters
    to_phase(s, "end", turn=4)
    settle(s)
    assert source.counters.get("+1/+1") == 2


def test_actual_ring_cast_entry_same_mana_value_fight_treasure90(cards):
    s, source, bear, _, wall, _, _ = setup90(cards, NAMES[2])
    act(
        s,
        "p1",
        type="move",
        card_ids=[source.id, bear.id],
        to={"player": "p1", "zone": "hand"},
    )
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=bear.id)
    pick90(s, [wall.id])
    settle(s)
    assert wall.damage == 2 and bear.damage == 0
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    settle(s)
    assert source.tapped and any(
        c.name == "Treasure" and c.zone == "p1:battlefield"
        for c in s.state.cards.values()
    )


def payment90(s, answer):
    for _ in range(40):
        d = s.state.rules.decision
        if d:
            assert answer in {o.id for o in d.options}
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer])
            settle(s)
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


@pytest.mark.parametrize("paid", [False, True])
def test_actual_neyith_cast_and_combat_optional_double_native_duration90(cards, paid):
    s, source, bear, _, _, _, _ = setup90(cards)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    mana(s, C=2, G=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    to_phase(s, "begin_combat", turn=4)
    mana(s, C=2, G=1)
    pick90(s, [bear.id])
    payment90(s, "pay" if paid else "decline")
    ch = Plan(s.state, "p1", s.cards, None).ch(bear)
    assert ch.pt == ((4, 2) if paid else (2, 2))
    assert "must_be_blocked" in ch.imposed
    to_phase(s, "main2", turn=4)
    assert "must_be_blocked" not in Plan(s.state, "p1", s.cards, None).ch(bear).imposed
    to_phase(s, "main1", turn=5)
    assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == (2, 2)


def test_neyith_two_blocked_creatures_once_not_fights90(cards):
    from tests.test_rules_wave30p_combat import attack, block

    s, _, bear, elf, wall, _, other = setup90(cards)
    to_phase(s, "begin_combat", turn=4)
    mana(s, C=2, G=1)
    pick90(s, [bear.id])
    payment90(s, "decline")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (bear, "p2"), (elf, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    before = len(s.state.zones["p1:hand"])
    block(s, "p2", (wall, bear), (other, elf))
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 1
    assert not s.state.rules.turn_log.fought90


def test_opponents_fighting_does_not_draw_for_neyith90(cards):
    s, _, _, _, wall, _, other = setup90(cards)
    before = fight90(s, wall, other)
    assert len(s.state.zones["p1:hand"]) == before - 1
    assert len(s.state.rules.turn_log.fought90) == 2


@pytest.mark.parametrize(
    "response", ["Counterspell", "Swords to Plowshares", "Swords source"]
)
def test_real_fight_spell_counter_or_missing_target_is_not_fight90(cards, response):
    s, _, bear, _, wall, _, _ = setup90(cards)
    act(s, "p1", type="set_prefs", hold_priority=True)
    spell = put(s, "Pit Fight", "hand")
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[bear.id, wall.id],
        target_counts=[1, 1],
    )
    answer = put(
        s, "Swords to Plowshares" if response == "Swords source" else response, "hand"
    )
    mana(s, **({"U": 2} if response == "Counterspell" else {"W": 1}))
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=answer.id,
        targets=[
            spell.id
            if response == "Counterspell"
            else bear.id
            if response == "Swords source"
            else wall.id
        ],
    )
    settle(s)
    assert not s.state.rules.turn_log.fought90 and not any(
        e.kind == "fought" for e in s.state.rules.events
    )
    assert bear.damage == 0


def test_regent_delayed_counter_and_ring_exclude_blinked_new_fighter90(cards):
    from app.game.errors import ActionError

    s, _, bear, _, wall, _, _ = setup90(cards, NAMES[1])
    fight90(s, bear, wall)
    assert len(s.state.rules.delayed) == 1
    spell = put(s, "Cloudshift", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    settle(s)
    ring = put(s, NAMES[2], "battlefield")
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(ring).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    assert not ring.tapped
    to_phase(s, "end", turn=4)
    settle(s)
    assert not bear.counters


def test_ring_actual_entry_target_live_mana_value_after_cytoshape90(cards):
    from app.game.errors import ActionError

    s, ring, bear, _, wall, orn, other = setup90(cards, NAMES[2])
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=bear.id)
    for _ in range(60):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d and other.id not in {o.card_id for o in d.options}
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[other.id])
    pick(s, [wall.id])
    copy = put(s, "Cytoshape", "hand")
    mana(s, C=1, G=1, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=copy.id, targets=[bear.id])
    pick90(s, [orn.id])
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(bear).name == "Ornithopter"
    assert not s.state.rules.turn_log.fought90 and wall.damage == 0


def test_ring_no_chosen_target_is_not_fight90(cards):
    from app.game.errors import ActionError

    s, ring, bear, _, wall, _, _ = setup90(cards, NAMES[2])
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
    mana(s, C=1, G=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=bear.id)
    pick90(s, [])
    settle(s)
    assert not s.state.rules.turn_log.fought90 and wall.damage == 0
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(ring).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)


@pytest.mark.parametrize("mode", ["neyith", "regent", "ring", "regent_blink"])
def test_genuine_cold_native_fight_receipt90(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    observer = (
        NAMES[0] if mode == "neyith" else NAMES[2] if mode == "ring" else NAMES[1]
    )
    s, source, bear, _, wall, _, _ = setup90(cards, observer)
    if mode == "neyith":
        act(s, "p1", type="set_prefs", hold_priority=True)
        spell = put(s, "Pit Fight", "hand")
        mana(s, C=1, G=1)
        wait_priority(s, "p1")
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=spell.id,
            targets=[bear.id, wall.id],
            target_counts=[1, 1],
        )
    else:
        fight90(s, bear, wall)
    blink = put(s, "Cloudshift", "hand")
    mana(s, W=1)
    saved = tmp_path / "fight90.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode,source,bear,blink=sys.argv[3:]
if mode=='neyith':
 before=len(s.state.zones['p1:hand']);settle(s)
 assert len(s.state.zones['p1:hand'])==before+1
 assert len(s.state.rules.turn_log.fought90)==2
elif mode=='ring':
 assert len(s.state.rules.turn_log.fought90)==2
 index=next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source]).abilities if a.kind=='activated')
 wait_priority(s,'p1');act(s,'p1',type='activate_ability',card_id=source,ability=index);settle(s)
 assert any(c.name=='Treasure' and c.zone=='p1:battlefield' for c in s.state.cards.values())
else:
 if mode=='regent_blink':
  wait_priority(s,'p1');act(s,'p1',type='cast_spell',card_id=blink,targets=[bear]);settle(s)
 to_phase(s,'end',turn=4);settle(s)
 assert s.state.cards[bear].counters.get('+1/+1',0)==(0 if mode=='regent_blink' else 2)
repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            mode,
            source.id,
            bear.id,
            blink.id,
        ],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("observer", NAMES[:2])
def test_watcher_itself_fights_and_dies_still_triggers90(cards, observer):
    s, source, _, _, _, _, _ = setup90(cards, observer)
    enemy = put(s, "Colossal Dreadmaw", "battlefield", pid="p2")
    before = fight90(s, source, enemy)
    assert source.zone == "p1:graveyard"
    if observer == NAMES[0]:
        assert len(s.state.zones["p1:hand"]) == before
    else:
        assert len(s.state.rules.delayed) == 1
        to_phase(s, "end", turn=4)
        settle(s)
        assert not source.counters


def test_ring_no_surviving_friendly_fighter_cannot_tap90(cards):
    from app.game.errors import ActionError

    s, ring, bear, _, _, _, _ = setup90(cards, NAMES[2])
    enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
    fight90(s, bear, enemy)
    assert bear.zone == "p1:graveyard" and enemy.zone == "p2:graveyard"
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(ring).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    assert not ring.tapped


def test_regent_fight_during_end_step_waits_for_next_turn_end90(cards):
    s, _, bear, _, wall, _, _ = setup90(cards, NAMES[1])
    to_phase(s, "end", turn=4)
    fight90(s, bear, wall)
    assert not bear.counters and len(s.state.rules.delayed) == 1
    to_phase(s, "end", turn=5)
    settle(s)
    assert bear.counters.get("+1/+1") == 2


def test_ring_fought_history_expires_on_next_turn90(cards):
    from app.game.errors import ActionError

    s, ring, bear, _, wall, _, _ = setup90(cards, NAMES[2])
    fight90(s, bear, wall)
    assert s.state.rules.turn_log.fought90
    to_phase(s, "main1", turn=7)
    assert (
        s.state.turn.active_player == "p1"
        and not ring.tapped
        and not s.state.rules.turn_log.fought90
    )
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(ring).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)


def legacy_history90(s):
    from app.game.state import GameState

    data = s.state.model_dump(mode="json")
    data["rules"]["turn_log"].pop("fight_history90_known", None)
    s.state = GameState.model_validate(data)
    assert s.state.rules.turn_log.fight_history90_known is None


def test_legacy_unknown_fights_explicit_manual_history_and_conservative_preview90(
    cards,
):
    from app.game.errors import ActionError
    from app.rules import casting

    s, ring, _, _, _, _, _ = setup90(cards, NAMES[2])
    legacy_history90(s)
    assert not any(
        h["card_id"] == ring.id for h in casting.activatable(s.state, "p1", cards)
    )
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ring.id]).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError, match="Fight history.*unavailable"):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    spell = put(s, "Safe Passage", "hand")
    mana(s, C=2, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == "p1:graveyard"


def test_legacy_unknown_positive_actual_fight_is_valid_without_marking_known90(cards):
    from app.rules import casting

    s, ring, bear, _, wall, _, _ = setup90(cards, NAMES[2])
    legacy_history90(s)
    bear = s.state.cards[bear.id]
    wall = s.state.cards[wall.id]
    fight90(s, bear, wall)
    assert s.state.rules.turn_log.fight_history90_known is None
    assert any(
        h["card_id"] == ring.id for h in casting.activatable(s.state, "p1", cards)
    )
    legacy_history90(s)
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ring.id]).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    settle(s)
    assert (
        s.state.cards[ring.id].tapped
        and s.state.rules.turn_log.fight_history90_known is None
    )
    assert any(
        c.name == "Treasure" and c.zone == "p1:battlefield"
        for c in s.state.cards.values()
    )


def test_legacy_unknown_next_native_turn_is_known_empty90(cards):
    from app.game.errors import ActionError

    s, ring, _, _, _, _, _ = setup90(cards, NAMES[2])
    legacy_history90(s)
    to_phase(s, "main1", turn=5)
    assert (
        s.state.rules.turn_log.fight_history90_known is True
        and not s.state.rules.turn_log.fought90
    )
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ring.id]).abilities
        if a.kind == "activated"
    )
    wait_priority(s, "p1")
    with pytest.raises(ActionError) as caught:
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
    assert "unavailable" not in str(caught.value)


@pytest.mark.parametrize("both", [False, True])
def test_ring_actual_fighters_phase_out_are_nonexistent90(cards, both):
    from app.game.errors import ActionError

    s, ring, bear, elf, _, _, _ = setup90(cards, NAMES[2])
    safe = put(s, "Safe Passage", "hand")
    mana(s, C=2, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=safe.id)
    settle(s)
    fight90(s, bear, elf)
    original = {c.id: Plan(s.state, "p1", s.cards, None).oid(c) for c in (bear, elf)}
    slips = [
        c
        for c in s.state.cards.values()
        if c.owner == "p1" and c.name == "Slip Out the Back"
    ]
    assert len(slips) == 2
    for spell, target in zip(slips, [bear, elf] if both else [bear], strict=False):
        act(
            s,
            "p1",
            type="move",
            card_ids=[spell.id],
            to={"player": "p1", "zone": "hand"},
        )
        mana(s, U=1)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
        settle(s)
        plan = Plan(s.state, "p1", s.cards, None)
        assert target.zone == "p1:phased" and plan.oid(target) == original[target.id]
        assert plan.ch(target).is_creature
    plan = Plan(s.state, "p1", s.cards, None)
    assert plan.in_game(ring)
    index = next(a.index for a in plan.ch(ring).abilities if a.kind == "activated")
    wait_priority(s, "p1")
    if both:
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
        assert s.state.model_dump(mode="json") == before
        assert not ring.tapped
    else:
        assert plan.in_game(elf)
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=index)
        settle(s)
        assert ring.tapped
        assert any(
            c.name == "Treasure" and c.zone == "p1:battlefield"
            for c in s.state.cards.values()
        )
