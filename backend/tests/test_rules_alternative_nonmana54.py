"""Native selected-spell alternative payments and announced X."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game

NAMES = ["Disrupting Shoal", "Blazing Shoal", "Sickening Shoal", "Nourishing Shoal", "Foil", "Dream Halls"]


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/alternative_nonmana54_cards.json").read_text())
    ):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def offer(s, c, pid="p1"):
    plan = Plan(s.state, pid, s.cards, None)
    offers = alt_costs.offers(s.state, pid, c, plan.ch(c), s.cards)
    assert len(offers) == 1
    return offers[0].key


@pytest.mark.parametrize(
    "name,payment,mv",
    [
        ("Blazing Shoal", "Lightning Bolt", 1),
        ("Sickening Shoal", "Dark Ritual", 1),
        ("Nourishing Shoal", "Grizzly Bears", 2),
    ],
)
def test_real_shoal_announced_x_and_colored_hand_payment(cards, name, payment, mv):
    s = game(cards, [name, payment], ["Grizzly Bears"])
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    c = put(s, name, "hand")
    paid = put(s, payment, "hand")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        alt_cost=offer(s, c),
        x_value=mv,
        targets=[] if name == "Nourishing Shoal" else [victim.id],
        sources=[],
    )
    assert paid.zone == "p1:exile" and s.state.rules.stack[c.id].x == mv
    answer(s)
    if name == "Nourishing Shoal":
        assert s.state.players["p1"].life == 42
    else:
        assert Plan(s.state, "p1", cards, None).ch(victim).pt == (
            (3, 2) if name == "Blazing Shoal" else (1, 1)
        )
    roundtrip(s)


@pytest.mark.parametrize("matches", [True, False])
def test_disrupting_targets_any_spell_but_checks_mv_on_resolution(cards, matches):
    s = game(cards, ["Grizzly Bears"], ["Disrupting Shoal", "Counterspell", "Ponder"])
    target = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=target.id, sources=[])
    c = put(s, "Disrupting Shoal", "hand", "p2")
    paid = put(s, "Counterspell" if matches else "Ponder", "hand", "p2")
    wait_priority(s, "p2")
    act(
        s,
        "p2",
        type="cast_spell",
        card_id=c.id,
        alt_cost=offer(s, c, "p2"),
        x_value=2 if matches else 1,
        targets=[target.id],
        sources=[],
    )
    assert paid.zone == "p2:exile"
    answer(s)
    assert target.zone == ("p1:graveyard" if matches else "p1:battlefield")
    roundtrip(s)


def test_foil_distinct_island_and_other_card_payment(cards):
    s = game(cards, ["Grizzly Bears"], ["Foil", "Ponder"])
    target = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=target.id, sources=[])
    c = put(s, "Foil", "hand", "p2")
    island = put(s, "Island", "hand", "p2")
    other = put(s, "Ponder", "hand", "p2")
    wait_priority(s, "p2")
    act(
        s,
        "p2",
        type="cast_spell",
        card_id=c.id,
        alt_cost=offer(s, c, "p2"),
        targets=[target.id],
        sources=[],
        cost_choices=[{"component": 0, "cards": [island.id]}, {"component": 1, "cards": [other.id]}],
    )
    assert island.zone == other.zone == "p2:graveyard"
    answer(s)
    assert target.zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("payer", ["p1", "p2"])
def test_dream_halls_actual_spell_color_and_any_controller(cards, payer):
    s = game(cards, ["Dream Halls", "Ponder", "Counterspell"], ["Ponder", "Counterspell"])
    put(s, "Dream Halls", "battlefield")
    target = put(s, "Ponder", "hand", payer)
    payment = put(s, "Counterspell", "hand", payer)
    if payer == "p2":
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, "main1", 5)
        assert s.state.turn.active_player == "p2"
    wait_priority(s, payer)
    act(
        s,
        payer,
        type="cast_spell",
        card_id=target.id,
        alt_cost=offer(s, target, payer),
        sources=[],
        cost_choices=[{"component": 0, "cards": [payment.id]}],
    )
    assert payment.zone == payer + ":graveyard" and target.zone == "stack"
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize("payment,x", [("Lightning Bolt", 2), ("Grizzly Bears", 1)])
def test_shoal_wrong_mana_value_or_color_is_atomic(cards, payment, x):
    s = game(cards, ["Blazing Shoal", payment], ["Grizzly Bears"])
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    c = put(s, "Blazing Shoal", "hand")
    wrong = put(s, payment, "hand")
    key = offer(s, c)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=c.id,
            alt_cost=key,
            x_value=x,
            targets=[victim.id],
            sources=[],
            cost_choices=[{"component": 0, "cards": [wrong.id]}],
        )
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("spell,payment", [("Sol Ring", "Counterspell"), ("Ponder", "Lightning Bolt")])
def test_dream_halls_colorless_or_wrong_color_cannot_be_paid(cards, spell, payment):
    s = game(cards, ["Dream Halls", spell, payment])
    put(s, "Dream Halls", "battlefield")
    c = put(s, spell, "hand")
    wrong = put(s, payment, "hand")
    key = offer(s, c)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=c.id,
            alt_cost=key,
            sources=[],
            cost_choices=[{"component": 0, "cards": [wrong.id]}],
        )
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("name", NAMES)
def test_true_cold_selected_spell_native_payment(cards, tmp_path, name):
    import subprocess
    import sys

    from app.rules import alt_costs as source_module

    if name in ("Foil", "Disrupting Shoal"):
        s = game(cards, ["Grizzly Bears"], [name, "Counterspell", "Ponder"])
        target = put(s, "Grizzly Bears", "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
        act(s, "p1", type="cast_spell", card_id=target.id, sources=[])
        pid = "p2"
        c = put(s, name, "hand", pid)
        payment = put(s, "Counterspell", "hand", pid)
        wait_priority(s, pid)
        action = dict(
            type="cast_spell", card_id=c.id, targets=[target.id], sources=[], alt_cost=offer(s, c, pid)
        )
        if name == "Disrupting Shoal":
            action["x_value"] = 2
            action["cost_choices"] = [{"component": 0, "cards": [payment.id]}]
            expected = {payment.id: "p2:exile", target.id: "p1:graveyard"}
        else:
            island = put(s, "Island", "hand", pid)
            action["cost_choices"] = [
                {"component": 0, "cards": [island.id]},
                {"component": 1, "cards": [payment.id]},
            ]
            expected = {payment.id: "p2:graveyard", island.id: "p2:graveyard", target.id: "p1:graveyard"}
    else:
        payment_name = {
            "Blazing Shoal": "Lightning Bolt",
            "Sickening Shoal": "Dark Ritual",
            "Nourishing Shoal": "Grizzly Bears",
            "Dream Halls": "Counterspell",
        }[name]
        s = game(cards, [name, payment_name, "Ponder"], ["Grizzly Bears"])
        pid = "p1"
        if name == "Dream Halls":
            put(s, name, "battlefield")
            c = put(s, "Ponder", "hand")
        else:
            c = put(s, name, "hand")
        payment = put(s, payment_name, "hand")
        targets = []
        if name in ("Blazing Shoal", "Sickening Shoal"):
            targets = [put(s, "Grizzly Bears", "battlefield", "p2").id]
        action = dict(
            type="cast_spell",
            card_id=c.id,
            targets=targets,
            sources=[],
            alt_cost=offer(s, c),
            cost_choices=[{"component": 0, "cards": [payment.id]}],
        )
        if name != "Dream Halls":
            action["x_value"] = 2 if name == "Nourishing Shoal" else 1
        expected = {payment.id: "p1:graveyard" if name == "Dream Halls" else "p1:exile", c.id: "p1:graveyard"}
    saved = tmp_path / "game.json"
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(dict(actor=pid, action=action, expected=expected)))
    code = r"""
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
act(s,spec['actor'],**spec['action']);answer(s)
for cid,zone in spec['expected'].items():assert s.state.cards[cid].zone==zone
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), str(spec)],
        cwd=Path(source_module.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_foil_cannot_discard_the_same_island_twice(cards):
    s = game(cards, ["Grizzly Bears"], ["Foil", "Ponder"])
    target = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=target.id, sources=[])
    c = put(s, "Foil", "hand", "p2")
    island = put(s, "Island", "hand", "p2")
    wait_priority(s, "p2")
    key = offer(s, c, "p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p2",
            type="cast_spell",
            card_id=c.id,
            alt_cost=key,
            targets=[target.id],
            sources=[],
            cost_choices=[{"component": 0, "cards": [island.id]}, {"component": 1, "cards": [island.id]}],
        )
    assert s.state.model_dump_json() == before


def test_disrupting_reads_target_announced_x_on_stack(cards):
    s = game(cards, ["Fireball"], ["Disrupting Shoal", "Counterspell"])
    target = put(s, "Fireball", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "R": 1})
    act(s, "p1", type="cast_spell", card_id=target.id, x_value=1, targets=["p2"], sources=[])
    c = put(s, "Disrupting Shoal", "hand", "p2")
    payment = put(s, "Counterspell", "hand", "p2")
    wait_priority(s, "p2")
    act(
        s,
        "p2",
        type="cast_spell",
        card_id=c.id,
        x_value=2,
        alt_cost=offer(s, c, "p2"),
        targets=[target.id],
        sources=[],
        cost_choices=[{"component": 0, "cards": [payment.id]}],
    )
    answer(s)
    assert target.zone == "p1:graveyard" and s.state.players["p2"].life == 40
    roundtrip(s)


def test_dream_halls_preserves_native_additional_spell_tax(cards):
    s = game(cards, ["Dream Halls", "Ponder", "Counterspell"], ["Thalia, Guardian of Thraben"])
    put(s, "Dream Halls", "battlefield")
    put(s, "Thalia, Guardian of Thraben", "battlefield", "p2")
    c = put(s, "Ponder", "hand")
    payment = put(s, "Counterspell", "hand")
    key = offer(s, c)
    before = s.state.model_dump_json()
    action = dict(
        type="cast_spell",
        card_id=c.id,
        alt_cost=key,
        sources=[],
        cost_choices=[{"component": 0, "cards": [payment.id]}],
    )
    with pytest.raises(ActionError):
        act(s, "p1", **action)
    assert s.state.model_dump_json() == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", **action)
    answer(s)
    assert payment.zone == "p1:graveyard"
    roundtrip(s)


def test_dream_halls_discard_matches_red_spell_not_blue_enchantment(cards):
    s = game(cards, ["Dream Halls", "Lightning Bolt", "Fireball", "Counterspell"])
    put(s, "Dream Halls", "battlefield")
    c = put(s, "Lightning Bolt", "hand")
    red = put(s, "Fireball", "hand")
    blue = put(s, "Counterspell", "hand")
    key = offer(s, c)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=c.id,
            targets=["p2"],
            alt_cost=key,
            sources=[],
            cost_choices=[{"component": 0, "cards": [blue.id]}],
        )
    assert s.state.model_dump_json() == before
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        targets=["p2"],
        alt_cost=key,
        sources=[],
        cost_choices=[{"component": 0, "cards": [red.id]}],
    )
    answer(s)
    assert red.zone == "p1:graveyard" and blue.zone == "p1:hand" and s.state.players["p2"].life == 37
    roundtrip(s)


def test_shoal_hand_x_counts_zero_not_the_announced_spell_x(cards):
    s = game(cards, ["Blazing Shoal", "Fireball"], ["Grizzly Bears"])
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    c = put(s, "Blazing Shoal", "hand")
    red = put(s, "Fireball", "hand")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        targets=[victim.id],
        alt_cost=offer(s, c),
        x_value=1,
        sources=[],
        cost_choices=[{"component": 0, "cards": [red.id]}],
    )
    answer(s)
    assert red.zone == "p1:exile" and Plan(s.state, "p1", cards, None).ch(victim).pt == (3, 2)
    roundtrip(s)
