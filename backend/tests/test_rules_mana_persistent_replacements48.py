from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.rules import casting, mana_replace
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards():
    if not (Path(__file__).resolve().parents[2] / "data/cards.sqlite").is_file():
        pytest.skip("the real card database is needed (data/cards.sqlite)")
    r = CardRepository(
        Path(__file__).resolve().parents[2] / "data/cards.sqlite",
        ImageStore(Path(__file__).resolve().parents[2] / "data/images"),
    )
    yield r
    r.close()


def setup(cards, names=()):
    s = table(cards, ["Quarum Trench Gnomes", "Plains", *names], ["Plains"], [])
    source = put(s, "Quarum Trench Gnomes", "battlefield")
    land = put(s, "Plains", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    return s, source, land


def apply(s, source, land):
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=[land.id])
    answer(s)
    wait_priority(s, "p1")
    assert s.state.rules.resolved_mana_replacements


def activate(s, land, player="p1", multi=False, color=None):
    opts = casting.mana_abilities(s.state, land, s.cards)
    index = next(i for i, ab in opts if not multi or any(len(o) > 1 for o in ab.options))
    act(
        s,
        player,
        type="activate_ability",
        card_id=land.id,
        ability=index,
        **({"mana_choice": color} if color else {}),
    )
    answer(s)


def test_native_real_targeted_effect_changes_white_and_keeps_producer(cards):
    s, gnome, land = setup(cards)
    apply(s, gnome, land)
    receipt = s.state.rules.resolved_mana_replacements[0]
    assert receipt.source_object == Plan(s.state, "p1", cards, None).oid(gnome)
    assert receipt.target.object_id == Plan(s.state, "p1", cards, None).oid(land)
    activate(s, land)
    assert s.state.players["p1"].mana_units[0].sym == "C"
    assert s.state.players["p1"].mana_units[0].src == receipt.target.object_id
    assert "Basic" in s.state.players["p1"].mana_units[0].tags
    roundtrip(s)


@pytest.mark.parametrize(
    "option,expected",
    [(("W", "W", "G"), ("C", "C", "G")), (("C", "U", "B", "R", "G"), ("C", "U", "B", "R", "G")), ((), ())],
)
def test_exact_componentwise_mapping(option, expected):
    assert mana_replace._apply({"do": "white_to_colorless"}, option) == [expected]


@pytest.mark.parametrize(
    "change", ["source_departure", "source_control", "land_control", "land_blink", "phase_cycle"]
)
def test_native_effect_lifetime_uses_exact_target_not_source_presence(cards, change):
    s, gnome, land = setup(cards)
    apply(s, gnome, land)
    original = Plan(s.state, "p1", cards, None).oid(land)
    player = "p1"
    if change == "source_departure":
        act(s, "p1", type="move", card_ids=[gnome.id], to={"player": "p1", "zone": "graveyard"})
    elif change == "source_control":
        act(s, "p1", type="set_controller", card_ids=[gnome.id], player="p2")
    elif change == "land_control":
        act(s, "p1", type="set_controller", card_ids=[land.id], player="p2")
        player = "p2"
        wait_priority(s, player)
    elif change == "land_blink":
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "exile"})
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
        assert Plan(s.state, "p1", cards, None).oid(land) != original
    else:
        act(s, "p1", type="phase_shift", card_ids=[land.id], out=True)
        assert not mana_replace.in_play(s.state, cards)
        act(s, "p1", type="phase_shift", card_ids=[land.id], out=False)
        assert Plan(s.state, "p1", cards, None).oid(land) == original
    activate(s, land, player)
    assert s.state.players[player].mana_units[0].sym == ("W" if change == "land_blink" else "C")
    roundtrip(s)


def test_unrelated_plains_and_nongenuine_target_are_not_affected(cards):
    s, g, l = setup(cards)  # noqa: E741
    other = put(s, "Plains", "battlefield", "p2")
    apply(s, g, l)
    wait_priority(s, "p2")
    activate(s, other, "p2")
    assert s.state.players["p2"].mana_units[0].sym == "W"


def test_mana_of_other_colors_from_target_and_two_white_preserve_quantity(cards):
    s, g, l = setup(cards, ["Gift of Paradise"])  # noqa: E741
    aura = put(s, "Gift of Paradise", "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=l.id)
    apply(s, g, l)
    activate(s, l, multi=True, color="G")
    assert [u.sym for u in s.state.players["p1"].mana_units] == ["G", "G"]
    act(s, "p1", type="tap", card_ids=[l.id], tapped=False)
    activate(s, l, multi=True, color="C")
    assert [u.sym for u in s.state.players["p1"].mana_units] == ["G", "G", "C", "C"]


def test_losing_plains_after_resolution_does_not_remove_exact_object_effect(cards):
    s, g, l = setup(cards, ["Gift of Paradise", "Spreading Seas"])  # noqa: E741
    gift = put(s, "Gift of Paradise", "battlefield")
    act(s, "p1", type="attach", card_ids=[gift.id], to=l.id)
    apply(s, g, l)
    seas = put(s, "Spreading Seas", "battlefield")
    act(s, "p1", type="attach", card_ids=[seas.id], to=l.id)
    assert "Plains" not in Plan(s.state, "p1", cards, None).ch(l).subtypes
    activate(s, l, multi=True, color="C")
    assert [u.sym for u in s.state.players["p1"].mana_units] == ["C", "C"]


def test_independent_aura_bonus_is_not_recolored_by_target_effect(cards):
    s, g, l = setup(cards, ["Wild Growth"])  # noqa: E741
    aura = put(s, "Wild Growth", "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=l.id)
    apply(s, g, l)
    activate(s, l)
    units = s.state.players["p1"].mana_units
    assert [u.sym for u in units] == ["C", "G"]
    assert units[0].src == Plan(s.state, "p1", cards, None).oid(l)
    assert units[1].src == Plan(s.state, "p1", cards, None).oid(aura)


def test_target_losing_plains_before_resolution_fizzles(cards):
    s, g, l = setup(cards, ["Spreading Seas"])  # noqa: E741
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=g.id, ability=0, targets=[l.id])
    seas = put(s, "Spreading Seas", "battlefield")
    act(s, "p1", type="attach", card_ids=[seas.id], to=l.id)
    answer(s)
    assert not s.state.rules.resolved_mana_replacements


def test_distinct_resolutions_retain_unique_effect_identity_and_native_overlap_guard(cards):
    s, g, l = setup(cards)  # noqa: E741
    apply(s, g, l)
    act(s, "p1", type="tap", card_ids=[g.id], tapped=False)
    apply(s, g, l)
    rows = s.state.rules.resolved_mana_replacements
    assert len(rows) == 2 and rows[0].id != rows[1].id
    assert rows[0].target == rows[1].target
    assert casting.mana_abilities(s.state, l, cards) == []
    roundtrip(s)


def test_canonical_full_definition(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Quarum Trench Gnomes")).level == "FULL"


def test_nonbasic_plains_is_legal_and_other_intrinsic_color_survives(cards):
    s = table(cards, ["Quarum Trench Gnomes", "Savannah"], [], [])
    g = put(s, "Quarum Trench Gnomes", "battlefield")
    land = put(s, "Savannah", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    apply(s, g, land)
    opts = casting.mana_abilities(s.state, land, cards)
    assert any(("C",) in ab.options for _, ab in opts)
    assert any(("G",) in ab.options for _, ab in opts)
    assert all(("W",) not in ab.options for _, ab in opts)
    index = next(i for i, ab in opts if ("C",) in ab.options)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=index)
    assert s.state.players["p1"].mana_units[0].sym == "C"


@pytest.mark.parametrize("when", ["stack", "resolved"])
def test_true_cold_exact_persistent_receipt_source_already_left(cards, tmp_path, when):
    import subprocess
    import sys

    s, g, l = setup(cards)  # noqa: E741
    source_oid = Plan(s.state, "p1", cards, None).oid(g)
    if when == "stack":
        act(s, "p1", type="set_prefs", hold_priority=True)
        act(s, "p1", type="activate_ability", card_id=g.id, ability=0, targets=[l.id])
        assert s.state.zones.get("stack")
    else:
        apply(s, g, l)
    act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "graveyard"})
    path = tmp_path / "quarum.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import casting
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
repo=CardRepository(Path.cwd().parent / 'data/cards.sqlite',ImageStore(Path.cwd().parent / 'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p2')
answer(s);wait_priority(s,'p1')
rows=s.state.rules.resolved_mana_replacements
assert len(rows)==1 and rows[0].source_object==sys.argv[3]
land=s.state.cards[sys.argv[2]]
index=next(i for i,ab in casting.mana_abilities(s.state,land,repo))
s.perform('p1',{'type':'activate_ability','card_id':land.id,'ability':index})
assert [(u.sym,u.src) for u in s.state.players['p1'].mana_units]==[('C',rows[0].target.object_id)]
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), l.id, source_oid],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr


def test_target_blink_while_ability_on_stack_never_retargets_successor(cards):
    s, g, l = setup(cards)  # noqa: E741
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=g.id, ability=0, targets=[l.id])
    old = Plan(s.state, "p1", cards, None).oid(l)
    act(s, "p1", type="move", card_ids=[l.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="move", card_ids=[l.id], to={"player": "p1", "zone": "battlefield"})
    assert Plan(s.state, "p1", cards, None).oid(l) != old
    answer(s)
    assert not s.state.rules.resolved_mana_replacements
    wait_priority(s, "p1")
    activate(s, l)
    assert s.state.players["p1"].mana_units[0].sym == "W"


def test_mana_ability_without_tap_cost_is_not_replaced(cards):
    from app.rules import mana as M

    s, g, l = setup(cards)  # noqa: E741
    apply(s, g, l)
    ability = M.parse_mana_ability("{0}: Add {W}.", ("W",), card_name="Native no-tap boundary")
    assert ability is not None and not ability.tap
    assert mana_replace.extend(s.state, l, cards, [(99, ability)]) == [(99, ability)]
