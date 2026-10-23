"""Vine Gecko uses actual first kicked-spell payments and preserves other cast costs."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Astral Confrontation"]
DATA = json.loads((Path(__file__).parent / "fixtures/attacked_player_costs80_cards.json").read_text())


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


def setup(cards, battle=False, walker=False):
    ns = [c["name"] for c in DATA] * 2
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    attackers = [put(s, n, "battlefield") for n in ["Grizzly Bears", "Balduvian Bears", "Ornithopter"]]
    target = put(s, "Grizzly Bears", "battlefield", "p3")
    spell = put(s, "Astral Confrontation", "hand")
    special = None
    if walker:
        special = put(s, "Jace Beleren", "battlefield", "p2")
        act(s, "p2", type="set_counter", card_id=special.id, kind="loyalty", value=3)
    if battle:
        special = put(s, "Invasion of Zendikar // Awakened Skyclave", "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "G": 1})
        act(s, "p1", type="cast_spell", card_id=special.id, sources=[])
        answer(s)
        assert s.state.rules.protectors[s.state.rules.object_id(special.id)] == "p3"  # answer() selects p3.
    to_phase(s, "declare_attackers", 7)
    return s, spell, attackers, target, special


def attack(s, pairs):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def cast(s, c, target, generic, pid="p1"):
    act(s, pid, type="add_mana", player=pid, mana={"C": generic, "W": 1})
    wait_priority(s, pid)
    act(s, pid, type="cast_spell", card_id=c.id, sources=[], targets=[target.id])
    assert sum(s.state.players[pid].mana.values()) == 0
    return s.state.rules.payments[s.state.rules.object_id(c.id)].total_cost


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Astral Confrontation")).level == "FULL"


@pytest.mark.parametrize("destinations,price", [(["p2"], 3), (["p2", "p2"], 3), (["p2", "p3"], 2)])
def test_actual_attack_distinct_current_player_recipients(cards, destinations, price):
    s, c, attackers, target, _ = setup(cards)
    attack(s, list(zip(attackers, destinations, strict=False)))
    assert cast(s, c, target, price) == "{" + str(price) + "}{W}"
    answer(s)
    assert s.state.cards[target.id].zone == "p3:exile"


@pytest.mark.parametrize("battle,walker", [(False, True), (True, False)])
def test_actual_attack_planeswalker_or_battle_does_not_count_protector(cards, battle, walker):
    s, c, attackers, target, special = setup(cards, battle=battle, walker=walker)
    attack(s, [(attackers[0], special.id)])
    assert cast(s, c, target, 4) == "{4}{W}"


def test_no_attackers_does_not_discount(cards):
    s, c, _, target, _ = setup(cards)
    attack(s, [])
    assert cast(s, c, target, 4) == "{4}{W}"


def test_removed_attacker_no_longer_counts_historical_defender(cards):
    s, c, attackers, target, _ = setup(cards)
    attack(s, [(attackers[0], "p2")])
    act(s, "p1", type="move", card_ids=[attackers[0].id], to={"zone": "graveyard"})
    assert cast(s, c, target, 4) == "{4}{W}"


def test_defender_lost_after_declaration_no_longer_counts(cards):
    s, c, attackers, target, _ = setup(cards)
    attack(s, [(attackers[0], "p2"), (attackers[1], "p3")])
    act(s, "p2", type="concede")
    assert cast(s, c, target, 3) == "{3}{W}"


def test_other_casters_attacking_creatures_do_not_discount_this_caster(cards):
    s, _, attackers, target, _ = setup(cards)
    c = put(s, "Astral Confrontation", "hand", "p2")
    attack(s, [(attackers[0], "p3")])
    assert cast(s, c, target, 4, pid="p2") == "{4}{W}"


def test_attacker_control_change_removes_original_players_discount(cards):
    s, c, attackers, target, _ = setup(cards)
    attack(s, [(attackers[0], "p2")])
    act(s, "p1", type="set_controller", card_ids=[attackers[0].id], player="p2")
    assert cast(s, c, target, 4) == "{4}{W}"


def test_native_spell_tax_before_distinct_defender_reduction(cards):
    s, c, attackers, target, _ = setup(cards)
    attack(s, [(attackers[0], "p2"), (attackers[1], "p3")])
    put(s, "Sphere of Resistance", "battlefield")
    assert cast(s, c, target, 3) == "{3}{W}"


def test_true_cold_current_declared_distinct_players_drive_native_price(cards, tmp_path):
    import os
    import subprocess
    import sys

    s, c, attackers, target, _ = setup(cards)
    attack(s, [(attackers[0], "p2"), (attackers[1], "p3")])
    wait_priority(s, "p1")
    saved = tmp_path / "attacking.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
saved,database,cid,target=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
act(s,'p1',type='add_mana',player='p1',mana={'C':2,'W':1})
act(s,'p1',type='cast_spell',card_id=cid,sources=[],targets=[target])
assert sum(s.state.players['p1'].mana.values())==0
assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost=='{2}{W}'
answer(s)
assert s.state.cards[target].zone=='p3:exile'
GameState.model_validate_json(s.state.model_dump_json())
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), c.id, target.id],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert run.returncode == 0, run.stdout + run.stderr
