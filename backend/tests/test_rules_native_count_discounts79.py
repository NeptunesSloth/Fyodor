"""Vine Gecko uses actual first kicked-spell payments and preserves other cast costs."""

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
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Synchronized Eviction", "Delightful Discovery"]
DATA = json.loads((Path(__file__).parent / "fixtures/native_count_discounts79_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name="Synchronized Eviction"):
    ns = [c["name"] for c in DATA] * 2
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    return s, put(s, name, "hand")


def cast(s, c, mana, **kwargs):
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    wait_priority(s, "p1")
    return act(s, "p1", type="cast_spell", card_id=c.id, sources=[], **kwargs)


def opt(s, pid):
    spell = put(s, "Opt", "hand", pid)
    act(s, pid, type="add_mana", player=pid, mana={"U": 1})
    wait_priority(s, pid)
    act(s, pid, type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    return spell


def cost(s, c):
    assert sum(s.state.players["p1"].mana.values()) == 0
    return s.state.rules.payments[s.state.rules.object_id(c.id)].total_cost


def test_canonical_exact_two(cards):
    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in NAMES)


def test_two_shared_bears_and_native_second_from_top(cards):
    s, c = setup(cards)
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Balduvian Bears", "battlefield")
    cast(s, c, {"C": 2, "U": 1}, targets=[target.id])
    assert cost(s, c) == "{2}{U}"
    answer(s)
    assert s.state.cards[target.id].zone == "p2:library" and s.state.zones["p2:library"][1] == target.id


def test_changeling_and_elf_share_type(cards):
    s, c = setup(cards)
    target = put(s, "Ornithopter", "battlefield", "p2")
    put(s, "Universal Automaton", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    cast(s, c, {"C": 2, "U": 1}, targets=[target.id])
    assert cost(s, c) == "{2}{U}"


def test_disjoint_creatures_do_not_discount_atomic_failure(cards):
    s, c = setup(cards)
    target = put(s, "Ornithopter", "battlefield", "p2")
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "U": 1})
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="mana|pay"):
        act(s, "p1", type="cast_spell", card_id=c.id, sources=[], targets=[target.id])
    assert s.state.model_dump_json() == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[], targets=[target.id])
    assert cost(s, c) == "{4}{U}"


def test_opposing_shared_creatures_do_not_qualify(cards):
    s, c = setup(cards)
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Balduvian Bears", "battlefield", "p2")
    cast(s, c, {"C": 4, "U": 1}, targets=[target.id])
    assert cost(s, c) == "{4}{U}"


def test_two_opponents_native_casts_discount_and_scry_draw_resolves(cards):
    s, c = setup(cards, "Delightful Discovery")
    opt(s, "p2")
    opt(s, "p3")
    cast(s, c, {"C": 2, "U": 1})
    assert cost(s, c) == "{2}{U}"
    before = s.state.rules.turn_log.drew.get("p1", 0)
    answer(s)
    assert s.state.rules.turn_log.drew.get("p1", 0) == before + 2


def test_own_native_cast_does_not_discount(cards):
    s, c = setup(cards, "Delightful Discovery")
    opt(s, "p1")
    cast(s, c, {"C": 4, "U": 1})
    assert cost(s, c) == "{4}{U}"


@pytest.mark.parametrize("name", NAMES)
def test_tax_added_before_reduction(cards, name):
    s, c = setup(cards, name)
    put(s, "Sphere of Resistance", "battlefield")
    if name == "Synchronized Eviction":
        put(s, "Grizzly Bears", "battlefield")
        put(s, "Balduvian Bears", "battlefield")
        target = put(s, "Ornithopter", "battlefield", "p2")
        cast(s, c, {"C": 3, "U": 1}, targets=[target.id])
        assert cost(s, c) == "{3}{U}"
    else:
        spell = put(s, "Opt", "hand", "p2")
        act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "U": 1})
        wait_priority(s, "p2")
        act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
        answer(s)
        cast(s, c, {"C": 4, "U": 1})
        assert cost(s, c) == "{4}{U}"


def test_prior_turn_opponent_cast_does_not_discount(cards):
    s, c = setup(cards, "Delightful Discovery")
    opt(s, "p2")
    to_phase(s, "main1", 7)
    cast(s, c, {"C": 4, "U": 1})
    assert cost(s, c) == "{4}{U}"


def test_four_actual_opponent_casts_cannot_reduce_blue_component(cards):
    s, c = setup(cards, "Delightful Discovery")
    for pid in ["p2", "p3", "p2", "p3"]:
        opt(s, pid)
    cast(s, c, {"U": 1})
    assert cost(s, c) == "{U}"


def test_countered_opponent_spell_counts_own_counterspell_does_not(cards):
    s, c = setup(cards, "Delightful Discovery")
    spell = put(s, "Opt", "hand", "p2")
    counter = put(s, "Counterspell", "hand")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=spell.id, sources=[])
    cast(s, counter, {"U": 2}, targets=[spell.id])
    answer(s)
    assert s.state.cards[spell.id].zone == "p2:graveyard"
    cast(s, c, {"C": 3, "U": 1})
    assert cost(s, c) == "{3}{U}"


@pytest.mark.parametrize("name", NAMES)
def test_true_cold_native_board_or_opponent_cast_authority(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    s, c = setup(cards, name)
    target = ""
    if name == "Synchronized Eviction":
        put(s, "Grizzly Bears", "battlefield")
        put(s, "Balduvian Bears", "battlefield")
        target = put(s, "Ornithopter", "battlefield", "p2").id
    else:
        opt(s, "p2")
    wait_priority(s, "p1")
    saved = tmp_path / "discount.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
saved,database,cid,target=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
act(s,'p1',type='add_mana',player='p1',mana={'C':2 if target else 3,'U':1})
act(s,'p1',type='cast_spell',card_id=cid,sources=[],**({'targets':[target]} if target else {}))
assert sum(s.state.players['p1'].mana.values())==0
GameState.model_validate_json(s.state.model_dump_json())
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), c.id, target],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_departed_opponents_actual_prior_cast_is_retained_by_history(cards):
    s, c = setup(cards, "Delightful Discovery")
    opt(s, "p2")
    act(s, "p2", type="concede")
    cast(s, c, {"C": 3, "U": 1})
    assert cost(s, c) == "{3}{U}"
