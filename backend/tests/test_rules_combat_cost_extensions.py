"""Canonical mode, defender, and resolution-frozen declaration costs."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import combat_rules, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = [
    "War Cadence",
    "War Tax",
    "Brainwash",
    "Phyrexian Marauder",
    "Nils, Discipline Enforcer",
    "Onakke Oathkeeper",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for path in ["creature_combat_cost_cards.json", "combat_cost_extensions_cards.json"]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / path).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="ccx",
                number=f"{path[:3]}{i}",
                **{k: v for k, v in c.items() if k != "name"},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        *NAMES,
        "Grizzly Bears",
        "Memnite",
        "Disenchant",
        "Dress Down",
        "Llanowar Elves",
        "Jace Beleren",
        "Chandra Nalaar",
    ]
    return table(cards, names, names, ["Grizzly Bears"])


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Brainwash", "Phyrexian Marauder"])
def test_attack_only_fee_does_not_tax_blocks(cards, name):
    s = setup(cards)
    host = put(s, "Grizzly Bears" if name == "Brainwash" else name, "battlefield", pid="p2")
    if name == "Brainwash":
        a = put(s, name, "hand")
        mana(s, W=1)
        act(s, "p1", type="cast_spell", card_id=a.id, targets=[host.id])
        settle(s)
    else:
        act(s, "p2", type="set_counter", card_id=host.id, kind="+1/+1", value=3)
    p = Plan(s.state, "p2", s.cards, None)
    assert combat_rules.block_cost(p, {host.id}) == "{0}"
    assert combat_rules.attack_cost(p, [(host.id, "p3")]) == "{3}"
    roundtrip(s)


@pytest.mark.parametrize(
    ("name", "color", "mode"), [("War Tax", "U", "attack"), ("War Cadence", "R", "block")]
)
def test_war_cost_is_frozen_rule_and_includes_later_creatures(cards, name, color, mode):
    s = setup(cards)
    source = put(s, name, "battlefield")
    host = put(s, "Grizzly Bears", "battlefield", pid="p2")
    mana(s, C=3, **{color: 2})
    for x in [1, 2]:
        act(s, "p1", type="activate_ability", card_id=source.id, ability=0, x_value=x)
        settle(s)
    late = put(s, "Memnite", "battlefield", pid="p2")
    p = Plan(s.state, "p2", s.cards, None)

    def cost():
        return (
            combat_rules.attack_cost(p, [(host.id, "p3"), (late.id, "p3")])
            if mode == "attack"
            else combat_rules.block_cost(p, {host.id, late.id})
        )

    assert cost() == "{6}"
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    p = Plan(s.state, "p2", s.cards, None)
    assert cost() == "{6}"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Nils, Discipline Enforcer", "Onakke Oathkeeper"])
def test_defender_scope_and_individual_counter_totals(cards, name):
    s = setup(cards)
    put(s, name, "battlefield")
    one = put(s, "Grizzly Bears", "battlefield", pid="p2")
    two = put(s, "Memnite", "battlefield", pid="p2")
    jace = put(s, "Jace Beleren", "battlefield")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    chandra = put(s, "Chandra Nalaar", "battlefield")
    for kind, n in [("+1/+1", 2), ("charge", 3)]:
        act(s, "p2", type="set_counter", card_id=one.id, kind=kind, value=n)
    p = Plan(s.state, "p2", s.cards, None)
    assert combat_rules.attack_cost(p, [(one.id, "p3")]) == ""
    assert combat_rules.attack_cost(p, [(one.id, "p1")]) == ("{5}" if name.startswith("Nils") else "")
    assert combat_rules.attack_cost(p, [(one.id, jace.id), (two.id, chandra.id)]) == (
        "{5}" if name.startswith("Nils") else "{2}"
    )
    assert combat_rules.block_cost(p, {one.id, two.id}) == "{0}"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Brainwash", "Phyrexian Marauder"])
def test_actual_attack_pays_once_and_rejects_underpayment(cards, name):
    s = setup(cards)
    if name == "Brainwash":
        host = put(s, "Grizzly Bears", "battlefield", pid="p2")
        a = put(s, name, "hand")
        mana(s, W=1)
        act(s, "p1", type="cast_spell", card_id=a.id, targets=[host.id])
        settle(s)
    else:
        host = put(s, name, "hand", pid="p2")
        to_phase(s, "main1", turn=2)
        mana(s, pid="p2", C=3)
        act(s, "p2", type="cast_spell", card_id=host.id, x_value=3)
        settle(s)
        assert s.state.cards[host.id].counters["+1/+1"] == 3
    to_phase(s, "declare_attackers", turn=2 if name == "Brainwash" else 5)
    with pytest.raises(ActionError):
        attack(s, (host, "p3"), pid="p2")
    mana(s, pid="p2", C=3)
    attack(s, (host, "p3"), pid="p2")
    assert mana_pool(s, "p2") == {}
    roundtrip(s)


@pytest.mark.parametrize(
    ("name", "color", "mode"), [("War Tax", "U", "attack"), ("War Cadence", "R", "block")]
)
def test_war_actual_declaration_payment_and_cleanup(cards, name, color, mode):
    from tests.test_rules_wave30p_combat import block

    s = setup(cards)
    source = put(s, name, "battlefield")
    host = put(s, "Grizzly Bears", "battlefield", pid="p2")
    attacker = put(s, "Memnite", "battlefield")
    turn = 2 if mode == "attack" else 4
    to_phase(s, "begin_combat", turn=turn)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p1")
    mana(s, C=2, **{color: 1})
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, x_value=2)
    settle(s)
    to_phase(s, "declare_attackers", turn=turn)
    if mode == "block":
        attack(s, (attacker, "p2"))
        to_phase(s, "declare_blockers", turn=turn)

    def declare():
        if mode == "attack":
            attack(s, (host, "p3"), pid="p2")
        else:
            block(s, "p2", (host, attacker))

    with pytest.raises(ActionError):
        declare()
    mana(s, pid="p2", C=2)
    declare()
    assert mana_pool(s, "p2") == {}
    roundtrip(s)
    to_phase(s, "main1", turn=turn + 1)
    p = Plan(s.state, "p2", s.cards, None)
    assert combat_rules.attack_cost(p, [(host.id, "p1")]) == ""
    assert combat_rules.block_cost(p, {host.id}) == "{0}"
    roundtrip(s)


@pytest.mark.parametrize(
    ("name", "color", "mode"), [("War Tax", "U", "attack"), ("War Cadence", "R", "block")]
)
def test_war_rule_survives_actual_dress_down_and_zero_cost(cards, name, color, mode):
    s = setup(cards)
    source = put(s, name, "battlefield")
    host = put(s, "Grizzly Bears", "battlefield", pid="p2")
    mana(s, C=2, **{color: 2})
    for x in [0, 2]:
        act(s, "p1", type="activate_ability", card_id=source.id, ability=0, x_value=x)
        settle(s)
    dd = put(s, "Dress Down", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dd.id)
    settle(s)
    p = Plan(s.state, "p2", s.cards, None)
    assert (
        combat_rules.attack_cost(p, [(host.id, "p3")])
        if mode == "attack"
        else combat_rules.block_cost(p, {host.id})
    ) == "{2}"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Nils, Discipline Enforcer", "Onakke Oathkeeper"])
def test_actual_planeswalker_attack_payment_uses_locked_fee(cards, name):
    s = setup(cards)
    put(s, name, "battlefield")
    host = put(s, "Grizzly Bears", "battlefield", pid="p2")
    jace = put(s, "Jace Beleren", "battlefield")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    if name.startswith("Nils"):
        act(s, "p2", type="set_counter", card_id=host.id, kind="charge", value=2)
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        attack(s, (host, jace.id), pid="p2")
    n = sum(s.state.cards[host.id].counters.values()) if name.startswith("Nils") else 1
    mana(s, pid="p2", C=n)
    attack(s, (host, jace.id), pid="p2")
    assert mana_pool(s, "p2") == {}
    roundtrip(s)


@pytest.mark.parametrize("name", ["Nils, Discipline Enforcer", "Onakke Oathkeeper"])
def test_static_source_ability_loss_and_new_controller(cards, name):
    s = setup(cards)
    source = put(s, name, "battlefield")
    host = put(s, "Grizzly Bears", "battlefield", pid="p2")
    walker = put(s, "Jace Beleren", "battlefield")
    act(s, "p1", type="set_counter", card_id=walker.id, kind="loyalty", value=3)
    act(s, "p1", type="set_controller", card_ids=[walker.id], player="p3")
    act(s, "p2", type="set_counter", card_id=host.id, kind="charge", value=2)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    p = Plan(s.state, "p2", s.cards, None)
    assert combat_rules.attack_cost(p, [(host.id, walker.id)]) == (
        "{2}" if name.startswith("Nils") else "{1}"
    )
    dd = put(s, "Dress Down", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dd.id)
    settle(s)
    p = Plan(s.state, "p2", s.cards, None)
    assert combat_rules.attack_cost(p, [(host.id, walker.id)]) == ""
    roundtrip(s)


def test_onakke_actual_graveyard_activation(cards):
    s = setup(cards)
    source = put(s, "Onakke Oathkeeper", "graveyard")
    walker = put(s, "Jace Beleren", "graveyard")
    mana(s, W=2, C=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[walker.id])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:exile"
    assert s.state.cards[walker.id].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("phase", ["attack", "block"])
def test_saved_war_rule_payment_resumes_cold(cards, tmp_path, phase):
    import subprocess
    import sys

    s = setup(cards)
    qal = put(s, "Grizzly Bears", "battlefield", pid="p2")
    source = put(s, "War Tax" if phase == "attack" else "War Cadence", "battlefield")
    act(s, "p2", type="set_prefs", payment="self")
    lands = [
        c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island" and c.zone == "p2:library"
    ][:2]
    act(s, "p2", type="move", card_ids=[c.id for c in lands], to={"player": "p2", "zone": "battlefield"})
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30p_combat import block

    bear = put(s, "Grizzly Bears", "battlefield") if phase == "block" else None
    turn = 2 if phase == "attack" else 4
    to_phase(s, "begin_combat", turn=turn)
    wait_priority(s, "p1")
    mana(s, C=2, **({"U": 1} if phase == "attack" else {"R": 1}))
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, x_value=2)
    settle(s)
    if phase == "attack":
        to_phase(s, "declare_attackers", turn=2)
        attack(s, (qal, "p1"), pid="p2")
    else:
        to_phase(s, "declare_attackers", turn=4)
        attack(s, (bear, "p2"))
        to_phase(s, "declare_blockers", turn=4)
        block(s, "p2", (qal, bear))
    d = s.state.rules.decision
    assert d and d.resume["step"] == "pay_mana" and d.resume["cost"] == "{2}"
    act(s, "p2", type="activate_ability", card_id=lands[0].id, ability=0)
    assert s.state.rules.decision and mana_pool(s, "p2") == {"U": 1}
    roundtrip(s)
    saved = tmp_path / "combat-payment.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act, mana_pool
repo = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()), cards=repo)
act(s, 'p2', type='activate_ability', card_id=sys.argv[3], ability=0)
d = s.state.rules.decision
if d:
    assert d.resume['step'] == 'pay_mana'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
assert mana_pool(s, 'p2') == {}
c = s.state.cards[sys.argv[4]]
assert c.attacking is not None if sys.argv[5] == 'attack' else bool(c.blocking)
assert s.history.state_at(s.history.cursor).model_dump() == s.state.model_dump()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), lands[1].id, qal.id, phase],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
