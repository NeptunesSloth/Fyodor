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

NAMES = ["Dire Downdraft", "Lullmage's Domination"]
DATA = json.loads((Path(__file__).parent / "fixtures/target_conditional_costs81_cards.json").read_text())


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


def setup(cards, name="Dire Downdraft", target_name="Grizzly Bears", target_pid="p2"):
    ns = [c["name"] for c in DATA] * 2
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    return s, put(s, name, "hand"), put(s, target_name, "battlefield", target_pid)


def gy(s, pid, n):
    for cid in list(s.state.zones[pid + ":library"])[:n]:
        act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "graveyard"})
    assert len(s.state.zones[pid + ":graveyard"]) == n


def cast(s, c, target, mana, x=None, window=False):
    if window:
        act(s, "p1", type="set_prefs", payment="self")
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    wait_priority(s, "p1")
    return act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        targets=[target.id],
        sources=None if window else [],
        **({"x_value": x} if x is not None else {}),
    )


def payment(s, c):
    return s.state.rules.payments[s.state.rules.object_id(c.id)]


def choose_place(s, pid, place):
    from tests.test_rules_designations import settle

    settle(s)
    d = s.state.rules.decision
    assert d and d.player == pid and {"top", "bottom"} == {o.id for o in d.options}
    act(s, pid, type="choose", decision_id=d.id, option_ids=[place])


def test_canonical_two(cards):
    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in NAMES)


@pytest.mark.parametrize("tapped,price,place", [(False, 3, "top"), (True, 2, "bottom")])
def test_dire_target_current_tapped_state_and_native_owner_choice(cards, tapped, price, place):
    s, c, target = setup(cards)
    if tapped:
        act(s, "p2", type="tap", card_ids=[target.id], tapped=True)
    cast(s, c, target, {"C": price, "U": 1})
    assert payment(s, c).total_cost == "{" + str(price) + "}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    choose_place(s, "p2", place)
    assert s.state.cards[target.id].zone == "p2:library"
    assert s.state.zones["p2:library"][0 if place == "top" else -1] == target.id


def test_dire_owner_chooses_even_when_another_player_controls_target(cards):
    s, c, target = setup(cards)
    act(s, "p2", type="set_controller", card_ids=[target.id], player="p3")
    act(s, "p3", type="tap", card_ids=[target.id], tapped=True)
    cast(s, c, target, {"C": 2, "U": 1})
    choose_place(s, "p2", "bottom")
    assert s.state.zones["p2:library"][-1] == target.id


@pytest.mark.parametrize("count,generic", [(7, 2), (8, 0)])
def test_lullmage_target_controller_exact_threshold_and_native_permanent_control(cards, count, generic):
    s, c, target = setup(cards, "Lullmage's Domination")
    gy(s, "p2", count)
    cast(s, c, target, {"C": generic, "U": 3}, x=2)
    assert payment(s, c).total_cost == ("{" + str(generic) + "}" if generic else "") + "{U}{U}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    answer(s)
    assert s.state.cards[target.id].controller == "p1" and s.state.cards[target.id].zone == "p1:battlefield"
    to_phase(s, "end", 4)
    assert s.state.cards[target.id].controller == "p1"


def test_lullmage_other_opponents_graveyard_is_not_chosen_controller(cards):
    s, c, target = setup(cards, "Lullmage's Domination")
    gy(s, "p2", 7)
    gy(s, "p3", 8)
    cast(s, c, target, {"C": 2, "U": 3}, x=2)
    assert payment(s, c).total_cost == "{2}{U}{U}{U}"


def test_lullmage_current_controller_not_owner_controls_discount(cards):
    s, c, target = setup(cards, "Lullmage's Domination")
    act(s, "p2", type="set_controller", card_ids=[target.id], player="p3")
    gy(s, "p3", 8)
    cast(s, c, target, {"U": 3}, x=2)
    assert payment(s, c).total_cost == "{U}{U}{U}"
    answer(s)
    assert s.state.cards[target.id].controller == "p1" and s.state.cards[target.id].owner == "p2"


def test_lullmage_zero_mana_value_colored_components_not_reduced(cards):
    s, c, target = setup(cards, "Lullmage's Domination", "Ornithopter")
    gy(s, "p2", 8)
    cast(s, c, target, {"U": 3}, x=0)
    assert payment(s, c).total_cost == "{U}{U}{U}"
    answer(s)
    assert s.state.cards[target.id].controller == "p1"


def test_lullmage_x_must_match_chosen_target_before_any_payment(cards):
    s, c, target = setup(cards, "Lullmage's Domination")
    gy(s, "p2", 8)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "U": 3})
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id], x_value=1, sources=[])
    assert s.state.model_dump_json() == before


def test_pending_native_target_cannot_be_sacrificed_for_mana_or_rebound(cards):
    s, c, target = setup(cards, "Lullmage's Domination", target_pid="p1")
    altar = put(s, "Phyrexian Altar", "battlefield")
    gy(s, "p1", 8)
    original = s.state.rules.object_id(target.id)
    cast(s, c, target, {"U": 2}, x=2, window=True)
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="already uses it"):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=altar.id,
            ability=0,
            mana_choice="U",
            sources=[],
            cost_choices=[{"component": 0, "cards": [target.id]}],
        )
    assert s.state.model_dump_json() == before
    assert s.state.rules.object_id(target.id) == original
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    d = s.state.rules.decision
    if d:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[c.id].zone == "stack"
    assert s.state.rules.stack[c.id].targets[0].object_id == original
    assert payment(s, c).total_cost == "{U}{U}{U}"
    answer(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"


def test_real_altar_mana_raises_graveyard_threshold_without_repricing_locked_spell(cards):
    s, c, target = setup(cards, "Lullmage's Domination", target_pid="p1")
    altar = put(s, "Ashnod's Altar", "battlefield")
    sacrifice = put(s, "Ornithopter", "battlefield")
    gy(s, "p1", 7)
    cast(s, c, target, {"U": 3}, x=2, window=True)
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=altar.id,
        ability=0,
        sources=[],
        cost_choices=[{"component": 0, "cards": [sacrifice.id]}],
    )
    assert len(s.state.zones["p1:graveyard"]) == 8
    d = s.state.rules.decision
    if d:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert payment(s, c).total_cost == "{2}{U}{U}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    answer(s)
    assert s.state.cards[target.id].controller == "p1"


def test_dire_actual_vigilant_attacker_is_untapped_but_discounted(cards):
    s, c, target = setup(cards, target_name="Serra Angel", target_pid="p1")
    s.state.rules.controlled_since[target.id].turn = 0
    to_phase(s, "declare_attackers", 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": target.id, "target": "p2"}])
    assert not s.state.cards[target.id].tapped
    cast(s, c, target, {"C": 2, "U": 1})
    assert payment(s, c).total_cost == "{2}{U}"
    choose_place(s, "p1", "top")
    assert s.state.zones["p1:library"][0] == target.id


def test_dire_actual_target_taps_for_mana_after_undiscounted_cost_is_locked(cards):
    s, c, target = setup(cards, target_name="Llanowar Elves", target_pid="p1")
    s.state.rules.controlled_since[target.id].turn = 0
    cast(s, c, target, {"C": 2, "U": 1}, window=True)
    assert s.state.rules.decision.resume["cost"] == "{3}{U}"
    act(s, "p1", type="activate_ability", card_id=target.id, ability=0, sources=[])
    assert s.state.cards[target.id].tapped
    assert payment(s, c).total_cost == "{3}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    choose_place(s, "p1", "bottom")


def test_dire_actual_pili_untap_mana_preserves_original_discounted_price(cards):
    s, c, target = setup(cards, target_name="Pili-Pala", target_pid="p1")
    s.state.rules.controlled_since[target.id].turn = 0
    act(s, "p1", type="tap", card_ids=[target.id], tapped=True)
    cast(s, c, target, {"C": 4}, window=True)
    assert s.state.rules.decision.resume["cost"] == "{2}{U}"
    act(s, "p1", type="activate_ability", card_id=target.id, ability=1, mana_choice="U", sources=[])
    assert not s.state.cards[target.id].tapped
    assert payment(s, c).total_cost == "{2}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    choose_place(s, "p1", "top")


def test_lullmage_x5_tax_before_single_threshold_discount(cards):
    s, c, target = setup(cards, "Lullmage's Domination", "Serra Angel")
    gy(s, "p2", 8)
    gy(s, "p3", 8)
    put(s, "Sphere of Resistance", "battlefield")
    cast(s, c, target, {"C": 3, "U": 3}, x=5)
    assert payment(s, c).total_cost == "{3}{U}{U}{U}"
    assert sum(s.state.players["p1"].mana.values()) == 0
    answer(s)
    assert s.state.cards[target.id].controller == "p1"


def test_dire_actual_gisela_meld_root_has_one_destination_and_private_component_order(cards):
    from tests.test_rules_designations import settle

    s, c, _ = setup(cards)
    gisela = put(s, "Gisela, the Broken Blade", "battlefield", "p2")
    put(s, "Bruna, the Fading Light", "battlefield", "p2")
    to_phase(s, "end", 5)
    answer(s)
    target = s.state.cards[gisela.id]
    assert target.melded and len(target.merged) == 2 and target.name == "Brisela, Voice of Nightmares"
    act(s, "p2", type="tap", card_ids=[target.id], tapped=True)
    cast(s, c, target, {"C": 2, "U": 1})
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p2" and d.kind == "choose_cards" and len(d.options) == 1
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[target.id])
    d = s.state.rules.decision
    assert d and d.player == "p2" and d.kind == "order" and len(d.options) == 2
    assert "options" not in s.view("p1")["rules"]["decision"]
    assert "options" not in s.view("p3")["rules"]["decision"]
    selected = list(reversed(d.options))
    names = [o.label for o in selected]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in selected])
    assert [s.state.cards[cid].name for cid in s.state.zones["p2:library"][:2]] == names
    assert set(names) == {"Gisela, the Broken Blade", "Bruna, the Fading Light"}


def test_true_cold_dire_owner_destination_choice_keeps_original_target(cards, tmp_path):
    import os
    import subprocess
    import sys

    from tests.test_rules_designations import settle

    s, c, target = setup(cards)
    act(s, "p2", type="tap", card_ids=[target.id], tapped=True)
    cast(s, c, target, {"C": 2, "U": 1})
    settle(s)
    assert s.state.rules.decision.player == "p2"
    saved = tmp_path / "owner.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
saved,database,target=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
d=s.state.rules.decision
assert d.player=='p2' and {o.id for o in d.options}=={'top','bottom'}
act(s,'p2',type='choose',decision_id=d.id,option_ids=['bottom'])
assert s.state.zones['p2:library'][-1]==target
GameState.model_validate_json(s.state.model_dump_json())
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), target.id],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_true_cold_actual_tapped_elf_keeps_original_higher_payment(cards, tmp_path):
    import os
    import subprocess
    import sys

    s, c, target = setup(cards, target_name="Llanowar Elves", target_pid="p1")
    s.state.rules.controlled_since[target.id].turn = 0
    cast(s, c, target, {"C": 1, "U": 1}, window=True)
    act(s, "p1", type="activate_ability", card_id=target.id, ability=0, sources=[])
    d = s.state.rules.decision
    assert d and d.resume["cost"] == "{3}{U}"
    saved = tmp_path / "cost.json"
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
s.view('p1');s.view('p3')
assert s.state.cards[target].tapped and s.state.rules.decision.resume['cost']=='{3}{U}'
act(s,'p1',type='add_mana',player='p1',mana={'C':1})
d=s.state.rules.decision
if d:act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost=='{3}{U}'
assert sum(s.state.players['p1'].mana.values())==0
GameState.model_validate_json(s.state.model_dump_json())
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), c.id, target.id],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert run.returncode == 0, run.stdout + run.stderr
