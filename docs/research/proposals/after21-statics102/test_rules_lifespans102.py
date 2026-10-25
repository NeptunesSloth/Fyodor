"""Native exact-object condition lifetimes, not restarting once a condition fails."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_wave30m_durations import settle, to_phase


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/lifespans102_cards.json").read_text())
    ):
        c = {**c, "card_faces": c.get("faces", [])}
        rows[c["name"]] = card(
            c["name"],
            set_code="ls102",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code", "number")},
        )
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    r = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield r
    r.close()


def setup(cards):
    a = deck(
        cards,
        "Krenko, Mob Boss",
        [
            (20, "Forest"),
            (1, "Rootwater Matriarch"),
            (1, "Braided Net // Braided Quipu"),
            (1, "Rancor"),
            (1, "Disenchant"),
            (2, "Unbender Tine"),
            (1, "Zygon Infiltrator"),
            (1, "Old Man of the Sea"),
            (1, "Giant Growth"),
            (1, "Reality Ripple"),
            (1, "Song of the Dryads"),
            (1, "Blade of Shared Souls"),
            (1, "Assimilation Aegis"),
            (1, "Panharmonicon"),
        ],
    )
    b = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island"), (1, "Grizzly Bears"), (1, "Sol Ring")])
    s = GameSession(
        enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)),
        cards=cards,
    )
    act(s, "p1", type="pass_priority")
    return s


def cast(s, name, target=None, *, finish=True):
    c = put(s, name, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 20, "W": 20, "G": 20, "U": 20})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target] if target else [])
    if finish:
        settle(s)
    return c


def test_matriarch_control_ends_when_last_aura_leaves_and_never_restarts(cards):
    s = setup(cards)
    source = put(s, "Rootwater Matriarch", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "main1", turn=3)
    aura = cast(s, "Rancor", bear.id)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1"
    assert any(e.duration_bound102 for e in s.state.rules.effects)
    cast(s, "Disenchant", aura.id)
    assert s.state.cards[bear.id].controller == "p2"
    assert not any(e.duration_bound102 for e in s.state.rules.effects)
    cast(s, "Rancor", bear.id)
    assert s.state.cards[bear.id].controller == "p2"
    assert coverage.of_card_data(cards.resolve("Rootwater Matriarch")).level == "FULL"
    roundtrip(s)


def test_braided_net_native_counter_cost_and_untap_end_without_restarting(cards):
    s = setup(cards)
    to_phase(s, "main1")
    source = cast(s, "Braided Net // Braided Quipu")
    ring = put(s, "Sol Ring", "battlefield", "p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[ring.id])
    settle(s)
    assert s.state.cards[source.id].counters["net"] == 2
    assert s.state.cards[ring.id].tapped
    assert "cant_activate" in Plan.view(s.state, "p1", cards).ch(s.state.cards[ring.id]).imposed
    tine = put(s, "Unbender Tine", "battlefield")
    act(s, "p1", type="activate_ability", card_id=tine.id, ability=0, targets=[ring.id])
    settle(s)
    assert "cant_activate" not in Plan.view(s.state, "p1", cards).ch(s.state.cards[ring.id]).imposed
    act(s, "p2", type="tap", card_ids=[ring.id], tapped=True)
    assert "cant_activate" not in Plan.view(s.state, "p1", cards).ch(s.state.cards[ring.id]).imposed
    assert coverage.of_card_data(cards.resolve("Braided Net // Braided Quipu")).level == "FULL"
    roundtrip(s)


def test_actual_blade_for_mirrodin_excludes_original_recipient_then_native_equip_ends_copy(cards):
    s = setup(cards)
    original = put(s, "Rootwater Matriarch", "battlefield")
    to_phase(s, "main1")
    blade = cast(s, "Blade of Shared Souls", finish=False)
    for _ in range(30):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None
    host = s.state.cards[s.state.cards[blade.id].attached_to]
    assert host.name == "Rebel"
    assert host.id not in [o.id for o in d.options]
    assert any(o.id == original.id or o.card_id == original.id for o in d.options)
    pick = next(o.id for o in d.options if o.id == original.id or o.card_id == original.id)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[host.id]).name == "Rootwater Matriarch"
    act(s, "p1", type="add_mana", player="p1", mana={"C": 10})
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=2, targets=[original.id])
    settle(s)
    assert s.state.cards[blade.id].attached_to == original.id
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[host.id]).name == "Rebel"
    assert coverage.of_card_data(cards.resolve("Blade of Shared Souls")).level == "FULL"
    roundtrip(s)


def test_actual_aegis_linked_exile_copy_native_re_equip_and_source_destroy(cards):
    s = setup(cards)
    host = put(s, "Rootwater Matriarch", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    second = put(s, "Krenko, Mob Boss", "battlefield")
    to_phase(s, "main1")
    aegis = cast(s, "Assimilation Aegis", finish=False)
    settle(s, prefer=(bear.id,))
    assert s.state.cards[bear.id].zone == "p2:exile"
    act(s, "p1", type="add_mana", player="p1", mana={"C": 20})
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=2, targets=[host.id])
    settle(s)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[host.id]).name == "Grizzly Bears"
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=2, targets=[second.id])
    settle(s)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[host.id]).name == "Rootwater Matriarch"
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[second.id]).name == "Grizzly Bears"
    cast(s, "Disenchant", aegis.id)
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[second.id]).name == "Krenko, Mob Boss"
    assert coverage.of_card_data(cards.resolve("Assimilation Aegis")).level == "FULL"
    roundtrip(s)


@pytest.mark.parametrize("changed", ["none", "card", "host"])
def test_actual_panharmonicon_aegis_multiple_linked_cards_cold_chooser(cards, tmp_path, changed):
    import subprocess
    import sys

    s = setup(cards)
    host = put(s, "Krenko, Mob Boss", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    other = put(s, "Rootwater Matriarch", "battlefield")
    put(s, "Panharmonicon", "battlefield")
    to_phase(s, "main1")
    aegis = cast(s, "Assimilation Aegis", finish=False)
    picks = [bear.id, other.id]
    for _ in range(70):
        d = s.state.rules.decision
        if d:
            offered = {o.id for o in d.options}
            if picks and picks[0] in offered:
                selected = [picks.pop(0)]
            else:
                selected = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=selected)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert not picks
    assert s.state.cards[bear.id].zone == "p2:exile" and s.state.cards[other.id].zone == "p1:exile"
    act(s, "p1", type="add_mana", player="p1", mana={"C": 20})
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=2, targets=[host.id])
    for _ in range(30):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d and d.resume["step"] == "linked_copy102"
    assert {o.id for o in d.options} == {bear.id, other.id}
    saved = tmp_path / "linked-copy.json"
    saved.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
if sys.argv[5]!='none':
 cid=sys.argv[3] if sys.argv[5]=='card' else sys.argv[4]
 act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'hand'})
 act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'exile' if sys.argv[5]=='card' else 'battlefield'})
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
settle(s)
assert Plan.view(s.state,'p1',repo).ch(s.state.cards[sys.argv[4]]).name==('Rootwater Matriarch' if sys.argv[5]=='none' else 'Krenko, Mob Boss')
assert bool([e for e in s.state.rules.effects if e.duration_bound102])==(sys.argv[5]=='none')
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), other.id, host.id, changed],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[host.id]).name == "Grizzly Bears"
    roundtrip(s)


def test_zygon_target_stun_prevents_first_untap_then_copy_duration_ends_cold(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, "Zygon Infiltrator", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    tines = [c.id for c in s.state.cards.values() if c.name == "Unbender Tine"]
    for cid in tines:
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 10, "U": 10})
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=[bear.id])
    settle(s)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[source.id]).name == "Grizzly Bears"
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters["stun"] == 1
    saved = tmp_path / "zygon-copy.json"
    saved.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
for i,tine in enumerate(sys.argv[5:]):
 act(s,'p1',type='activate_ability',card_id=tine,ability=0,targets=[sys.argv[4]])
 settle(s)
 assert Plan.view(s.state,'p1',repo).ch(s.state.cards[sys.argv[3]]).name==('Grizzly Bears' if i==0 else 'Zygon Infiltrator')
assert not any(e.duration_bound102 for e in s.state.rules.effects)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, bear.id, *tines],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for i, tine in enumerate(tines):
        act(s, "p1", type="activate_ability", card_id=tine, ability=0, targets=[bear.id])
        settle(s)
        assert Plan.view(s.state, "p1", cards).ch(s.state.cards[source.id]).name == (
            "Grizzly Bears" if i == 0 else "Zygon Infiltrator"
        )
    assert coverage.of_card_data(cards.resolve("Zygon Infiltrator")).level == "FULL"
    roundtrip(s)


def test_old_man_current_power_threshold_ends_control_without_restarting(cards):
    s = setup(cards)
    source = put(s, "Old Man of the Sea", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1" and s.state.cards[source.id].tapped
    cast(s, "Giant Growth", bear.id)
    assert s.state.cards[bear.id].controller == "p2"
    assert not any(e.duration_bound102 for e in s.state.rules.effects)
    to_phase(s, "main1", turn=4)
    assert Plan.view(s.state, "p1", cards).ch(s.state.cards[bear.id]).pt == (2, 2)
    assert s.state.cards[source.id].tapped
    assert s.state.cards[bear.id].controller == "p2"
    assert coverage.of_card_data(cards.resolve("Old Man of the Sea")).level == "FULL"
    roundtrip(s)


def test_old_man_source_phasing_ends_tracked_duration_per_702_26f(cards):
    s = setup(cards)
    source = put(s, "Old Man of the Sea", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1"
    cast(s, "Reality Ripple", source.id)
    assert s.state.cards[source.id].zone.endswith(":phased")
    assert s.state.cards[bear.id].controller == "p2"
    assert not any(e.duration_bound102 for e in s.state.rules.effects)
    roundtrip(s)


@pytest.mark.parametrize("changed", ["source", "target"])
def test_old_man_uses_zero_for_power_of_noncreature_per_107_2(cards, changed):
    s = setup(cards)
    source = put(s, "Old Man of the Sea", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    tine = put(s, "Unbender Tine", "battlefield")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    cast(s, "Song of the Dryads", source.id if changed == "source" else bear.id)
    assert s.state.cards[bear.id].controller == ("p2" if changed == "source" else "p1")
    if changed == "target":
        assert Plan.view(s.state, "p1", cards).ch(s.state.cards[bear.id]).pt is None
        act(s, "p1", type="activate_ability", card_id=tine.id, ability=0, targets=[source.id])
        settle(s)
        assert s.state.cards[bear.id].controller == "p2"
    assert not any(e.duration_bound102 for e in s.state.rules.effects)
    roundtrip(s)
