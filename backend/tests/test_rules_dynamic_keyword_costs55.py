"""Dynamic grants bind actual selected spell costs and announced X."""

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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/dynamic_keyword_costs55_cards.json").read_text())
    ):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ['Henzie "Toolbox" Torre', "Herigast, Erupting Nullkite"])
def test_complete_canonical_initial_two(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def offer(s, c):
    plan = Plan(s.state, "p1", s.cards, None)
    offers = alt_costs.offers(s.state, "p1", c, plan.ch(c), s.cards)
    assert len(offers) == 1
    return offers[0]


def test_henzie_grants_real_blitz_body(cards):
    s = game(cards, ['Henzie "Toolbox" Torre', "Shivan Dragon"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "R": 2})
    o = offer(s, c)
    assert o.tag == "blitz" and o.alt.mana_cost.text() == "{4}{R}{R}"
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=o.key, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and "haste" in Plan(s.state, "p1", cards, None).ch(c).keywords
    from tests.test_rules_conditionals import until

    hand = len(s.state.zones["p1:hand"])
    until(s, lambda current: current.state.cards[c.id].zone == "p1:graveyard")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    roundtrip(s)


@pytest.mark.parametrize("x", [0, 3, 4, 6])
def test_henzie_announced_x_minimum_and_actual_cost(cards, x):
    s = game(cards, ['Henzie "Toolbox" Torre', "Stonecoil Serpent"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    c = put(s, "Stonecoil Serpent", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": x})
    o = offer(s, c)
    action = dict(type="cast_spell", card_id=c.id, alt_cost=o.key, x_value=x, sources=[])
    if x < 4:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, "p1", **action)
        assert s.state.model_dump_json() == before
    else:
        act(s, "p1", **action)
        answer(s)
        assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == x
        assert "haste" in Plan(s.state, "p1", cards, None).ch(c).keywords
        roundtrip(s)


def test_herigast_own_sacrifice_preserves_selected_dynamic_emerge(cards):
    s = game(cards, ["Herigast, Erupting Nullkite", "Shivan Dragon"])
    source = put(s, "Herigast, Erupting Nullkite", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    o = offer(s, c)
    assert o.tag == "emerge"
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        alt_cost=o.key,
        sources=[],
        cost_choices=[{"component": 0, "cards": [source.id]}],
    )
    answer(s)
    assert source.zone == "p1:graveyard" and c.zone == "p1:battlefield"
    roundtrip(s)


def test_henzie_counts_actual_command_zone_cast_for_blitz_discount(cards):
    from app.rules import mana_units
    from tests.test_rules_bandmate_references import wait_priority

    s = game(cards, ['Henzie "Toolbox" Torre', "Shivan Dragon"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    commander = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    assert commander.zone == "p1:command"
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    assert sum(s.state.players["p1"].commander_casts.values()) == 1
    c = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "R": 2})
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=offer(s, c).key, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


@pytest.mark.parametrize("empty,accept", [(False, True), (True, True), (False, False)])
def test_herigast_optional_exile_hand_and_draw_even_when_empty(cards, empty, accept):

    s = game(cards, ["Herigast, Erupting Nullkite", "Grizzly Bears"])
    c = put(s, "Herigast, Erupting Nullkite", "hand")
    if not empty:
        put(s, "Grizzly Bears", "hand")
    other = [x for x in s.state.zones["p1:hand"] if x != c.id]
    if empty:
        for cid in list(other):
            act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"})
        other = []
    act(s, "p1", type="add_mana", player="p1", mana={"C": 7, "R": 2})
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[])
    # Passing priority resolves the native optional cast trigger before the spell.
    from tests.test_rules_designations import settle

    settle(s)
    d = s.state.rules.decision
    assert d is not None
    chosen = next(o for o in d.options if ("yes" in o.id.lower() or "yes" in o.label.lower()) == accept)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen.id])
    answer(s)
    assert c.zone == "p1:battlefield"
    if accept:
        assert all(s.state.cards[cid].zone == "p1:exile" for cid in other)
        assert len(s.state.zones["p1:hand"]) == 3
    else:
        assert all(s.state.cards[cid].zone == "p1:hand" for cid in other)
    roundtrip(s)


@pytest.mark.parametrize(
    "kind", ["henzie_x", "henzie_commander", "herigast_sacrifice", "herigast_empty_trigger"]
)
def test_true_cold_dynamic_keyword_and_whole_body(cards, tmp_path, kind):
    import subprocess
    import sys

    from app.rules import dynamic_keyword_costs55
    from tests.test_rules_bandmate_references import wait_priority

    if kind.startswith("henzie"):
        s = game(cards, ['Henzie "Toolbox" Torre', "Shivan Dragon", "Stonecoil Serpent"])
        put(s, 'Henzie "Toolbox" Torre', "battlefield")
        if kind == "henzie_commander":
            commander = next(
                c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1"
            )
            act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
            act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
            answer(s)
            wait_priority(s, "p1")
            c = put(s, "Shivan Dragon", "hand")
            mana = {"C": 3, "R": 2}
        else:
            c = put(s, "Stonecoil Serpent", "hand")
            mana = {"C": 4}
        act(s, "p1", type="add_mana", player="p1", mana=mana)
        action = dict(type="cast_spell", card_id=c.id, alt_cost=offer(s, c).key, sources=[])
        if kind == "henzie_x":
            action["x_value"] = 4
    else:
        s = game(cards, ["Herigast, Erupting Nullkite", "Shivan Dragon"])
        source = put(
            s, "Herigast, Erupting Nullkite", "battlefield" if kind == "herigast_sacrifice" else "hand"
        )
        if kind == "herigast_sacrifice":
            c = put(s, "Shivan Dragon", "hand")
            act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
            action = dict(
                type="cast_spell",
                card_id=c.id,
                alt_cost=offer(s, c).key,
                sources=[],
                cost_choices=[{"component": 0, "cards": [source.id]}],
            )
        else:
            c = source
            for cid in list(s.state.zones["p1:hand"]):
                if cid != c.id:
                    act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"})
            act(s, "p1", type="add_mana", player="p1", mana={"C": 7, "R": 2})
            action = dict(type="cast_spell", card_id=c.id, sources=[])
    saved = tmp_path / "game.json"
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(dict(action=action, kind=kind)))
    code = r"""
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import mana_units
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text());act(s,'p1',**spec['action']);answer(s)
c=s.state.cards[spec['action']['card_id']]
assert c.zone=='p1:battlefield' and not mana_units.visible_pool(s.state,'p1')
if spec['kind'].startswith('henzie'):assert 'haste' in Plan(s.state,'p1',repo,None).ch(c).keywords
if spec['kind']=='henzie_x':assert c.counters.get('+1/+1')==4
if spec['kind']=='herigast_empty_trigger':assert len(s.state.zones['p1:hand'])==3
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), str(spec)],
        cwd=Path(dynamic_keyword_costs55.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_henzie_reduces_printed_blitz_below_its_grant_mv_threshold_after_tax(cards):
    from app.rules import mana_units
    from tests.test_rules_bandmate_references import wait_priority

    s = game(cards, ['Henzie "Toolbox" Torre', "Riveteers Requisitioner", "Sphere of Resistance"])
    put(s, 'Henzie "Toolbox" Torre', "battlefield")
    commander = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
    act(s, "p1", type="cast_spell", card_id=commander.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    put(s, "Sphere of Resistance", "battlefield")
    c = put(s, "Riveteers Requisitioner", "hand")
    o = offer(s, c)
    assert o.tag == "blitz" and o.alt.mana_cost.text() == "{2}{R}"
    # Printed blitz 2R, Sphere +1, one actual commander cast -1 => 2R.
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 1})
    act(s, "p1", type="cast_spell", card_id=c.id, alt_cost=o.key, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and not mana_units.visible_pool(s.state, "p1")
    assert "haste" in Plan(s.state, "p1", cards, None).ch(c).keywords
    roundtrip(s)
