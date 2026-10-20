"""Canonical whole-declaration companion restrictions and requirements."""

from __future__ import annotations

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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack, block

NAMES = ["Okk", "Orcish Conscripts", "Scarred Puma", "Ekundu Cyclops"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/declaration_groups_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="dgp", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads((Path(__file__).parent / "fixtures/declaration_groups_cards.json").read_text())
    ]
    return table(cards, names, names, ["Grizzly Bears", "Memnite"])


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(
    ("name", "support"),
    [("Okk", "Craw Wurm"), ("Orcish Conscripts", "Grizzly Bears"), ("Scarred Puma", "Grizzly Bears")],
)
def test_attack_companions_can_attack_different_defenders(cards, name, support):
    s = setup(cards)
    host = put(s, name, "battlefield", pid="p2")
    other = put(s, support, "battlefield", pid="p2")
    extra = put(s, "Memnite", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        attack(s, (host, "p1"), pid="p2")
    if name == "Orcish Conscripts":
        with pytest.raises(ActionError):
            attack(s, (host, "p1"), (other, "p3"), pid="p2")
        attack(s, (host, "p1"), (other, "p3"), (extra, "p3"), pid="p2")
    else:
        attack(s, (host, "p1"), (other, "p3"), pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("name", ["Okk", "Orcish Conscripts"])
def test_block_companions_can_block_different_attackers(cards, name):
    s = setup(cards)
    host = put(s, name, "battlefield", pid="p2")
    other = put(s, "Craw Wurm", "battlefield", pid="p2")
    extra = put(s, "Memnite", "battlefield", pid="p2")
    one = put(s, "Grizzly Bears", "battlefield")
    two = put(s, "Memnite", "battlefield")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (one, "p2"), (two, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    with pytest.raises(ActionError):
        block(s, "p2", (host, one))
    pairs = [(host, one), (other, two)]
    if name == "Orcish Conscripts":
        with pytest.raises(ActionError):
            block(s, "p2", *pairs)
        pairs.append((extra, one))
    block(s, "p2", *pairs)
    roundtrip(s)


@pytest.mark.parametrize("another", [False, True])
def test_ekundu_is_not_forced_to_attack_alone(cards, another):
    s = setup(cards)
    host = put(s, "Ekundu Cyclops", "battlefield", pid="p2")
    other = put(s, "Grizzly Bears", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    if another:
        with pytest.raises(ActionError):
            attack(s, (other, "p3"), pid="p2")
        attack(s, (host, "p1"), (other, "p3"), pid="p2")
    else:
        attack(s, pid="p2")
    roundtrip(s)


@pytest.mark.parametrize(
    ("name", "support"),
    [("Okk", "Craw Wurm"), ("Orcish Conscripts", "Grizzly Bears"), ("Mogg Flunkies", "Grizzly Bears")],
)
def test_requirements_can_use_optional_companions_but_obey_caps(cards, name, support):
    s = setup(cards)
    host = put(s, name, "battlefield", pid="p2")
    other = put(s, "Verdant Force" if name == "Okk" else support, "battlefield", pid="p2")
    extra = put(s, "Memnite", "battlefield", pid="p2")
    blade = put(s, "Bloodthirsty Blade", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        attack(s, pid="p2")
    pairs = [(host, "p3"), (other, "p1")]
    if name == "Orcish Conscripts":
        pairs.append((extra, "p1"))
    else:
        pairs.append((extra, "p3"))
    attack(s, *pairs, pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("name", ["Okk", "Orcish Conscripts", "Mogg Flunkies"])
def test_attack_capacity_prevents_illegal_support_for_requirements(cards, name):
    s = setup(cards)
    put(s, "Fumiko the Lowblood", "battlefield")
    put(s, "Silent Arbiter", "battlefield")
    put(s, name, "battlefield", pid="p2")
    other = put(s, "Craw Wurm", "battlefield", pid="p2")
    put(s, "Memnite", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (other, "p3"), pid="p2")
    roundtrip(s)


@pytest.mark.parametrize(("name", "companions"), [("Okk", 1), ("Orcish Conscripts", 2), ("Mogg Flunkies", 1)])
def test_lure_requires_legal_optional_companion_completion(cards, name, companions):
    s = setup(cards)
    host = put(s, name, "battlefield", pid="p2")
    other = put(s, "Craw Wurm", "battlefield", pid="p2")
    extra = put(s, "Memnite", "battlefield", pid="p2") if companions == 2 else None
    attacker = put(s, "Grizzly Bears", "battlefield")
    aura = put(s, "Lure", "hand")
    mana(s, G=2, C=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[attacker.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (attacker, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    with pytest.raises(ActionError):
        block(s, "p2")
    pairs = [(host, attacker), (other, attacker)]
    if extra:
        pairs.append((extra, attacker))
    block(s, "p2", *pairs)
    roundtrip(s)


def test_okk_multiple_blocks_are_not_a_companion(cards):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    put(s, "High Ground", "battlefield", pid="p2")
    one = put(s, "Grizzly Bears", "battlefield")
    two = put(s, "Memnite", "battlefield")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (one, "p2"), (two, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    with pytest.raises(ActionError):
        block(s, "p2", (host, one), (host, two))
    block(s, "p2")
    roundtrip(s)


def test_dress_down_removes_companion_restriction(cards):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    to_phase(s, "begin_combat", turn=2)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p1")
    dd = put(s, "Dress Down", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dd.id)
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (host, "p3"), pid="p2")
    roundtrip(s)


def test_optional_attack_support_is_never_forced_to_pay(cards):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    other = put(s, "Verdant Force", "battlefield", pid="p2")
    blade = put(s, "Bloodthirsty Blade", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[host.id])
    settle(s)
    aura = put(s, "Brainwash", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[other.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    mana(s, pid="p2", C=3)
    attack(s, pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("pay", [False, True])
def test_lure_optional_support_cost_is_not_forced(cards, pay):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    other = put(s, "Craw Wurm", "battlefield", pid="p2")
    attacker = put(s, "Grizzly Bears", "battlefield")
    for name, target, m in [("Lure", attacker, {"G": 2, "C": 1}), ("Oppressive Rays", other, {"W": 1})]:
        aura = put(s, name, "hand")
        mana(s, **m)
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[target.id])
        settle(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (attacker, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    mana(s, pid="p2", C=3)
    if pay:
        with pytest.raises(ActionError):
            block(s, "p2", (other, attacker))
        block(s, "p2", (host, attacker), (other, attacker))
    else:
        block(s, "p2")
    roundtrip(s)


def test_current_power_and_colors_not_printed_values(cards):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    support = put(s, "Grizzly Bears", "battlefield", pid="p2")
    growth = put(s, "Giant Growth", "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[support.id])
    settle(s)
    # Growth must still be active, so use p1's own Okk/support in this turn.
    act(s, "p1", type="set_controller", card_ids=[host.id, support.id], player="p1")
    # Creatures changing controller cannot attack without haste; native helper tests
    # below instead read the completed declaration predicate directly.
    from app.rules import declaration_groups
    from app.rules.plan import Plan

    p = Plan(s.state, "p1", s.cards, None)
    assert declaration_groups.legal(p, {host.id, support.id}, "attack")
    act(s, "p1", type="set_counter", card_id=host.id, kind="+1/+1", value=1)
    p = Plan(s.state, "p1", s.cards, None)
    assert not declaration_groups.legal(p, {host.id, support.id}, "attack")
    roundtrip(s)


def test_puma_cannot_count_itself_as_colored_companion(cards):
    s = setup(cards)
    host = put(s, "Scarred Puma", "battlefield", pid="p2")
    other = put(s, "Memnite", "battlefield", pid="p2")
    green = put(s, "Grizzly Bears", "battlefield", pid="p2")
    lace = put(s, "Lifelace", "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=lace.id, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        attack(s, (host, "p3"), (other, "p3"), pid="p2")
    attack(s, (host, "p3"), (green, "p3"), pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("strong", [False, True])
def test_menace_requires_legal_companion_completion(cards, strong):
    s = setup(cards)
    put(s, "Goblin War Drums", "battlefield")
    host = put(s, "Okk", "battlefield", pid="p2")
    support = put(s, "Craw Wurm" if strong else "Memnite", "battlefield", pid="p2")
    attacker = put(s, "Grizzly Bears", "battlefield")
    lure = put(s, "Lure", "hand")
    mana(s, G=2, C=1)
    act(s, "p1", type="cast_spell", card_id=lure.id, targets=[attacker.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (attacker, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    if strong:
        with pytest.raises(ActionError):
            block(s, "p2")
        block(s, "p2", (host, attacker), (support, attacker))
    else:
        block(s, "p2")
    roundtrip(s)


@pytest.mark.parametrize("mode", ["attack", "block"])
def test_saved_group_declaration_resumes_cold(cards, tmp_path, mode):
    import subprocess
    import sys

    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    support = put(s, "Craw Wurm", "battlefield", pid="p2")
    target = put(s, "Grizzly Bears", "battlefield")
    if mode == "attack":
        to_phase(s, "declare_attackers", turn=2)
    else:
        to_phase(s, "declare_attackers", turn=4)
        attack(s, (target, "p2"))
        to_phase(s, "declare_blockers", turn=4)
    roundtrip(s)
    path = tmp_path / "group-declaration.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
host,support,target,mode=sys.argv[3:]
if mode=='attack':
    bad={'type':'declare_attackers','attackers':[{'card_id':host,'target':'p1'}]}
    good={'type':'declare_attackers','attackers':[{'card_id':host,'target':'p1'},{'card_id':support,'target':'p3'}]}
else:
    bad={'type':'declare_blockers','blocks':[{'blocker_id':host,'attacker_id':target}]}
    good={'type':'declare_blockers','blocks':[{'blocker_id':host,'attacker_id':target},{'blocker_id':support,'attacker_id':target}]}
try:s.perform('p2',bad)
except ActionError:pass
else:raise AssertionError('missing companion accepted')
s.perform('p2',good)
assert s.state.cards[host].attacking is not None if mode=='attack' else bool(s.state.cards[host].blocking)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), host.id, support.id, target.id, mode],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_voluntary_paid_attacker_can_enable_free_required_companion(cards):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    other = put(s, "Verdant Force", "battlefield", pid="p2")
    blade = put(s, "Bloodthirsty Blade", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[host.id])
    settle(s)
    aura = put(s, "Brainwash", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[other.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    mana(s, pid="p2", C=3)
    with pytest.raises(ActionError):
        attack(s, (other, "p3"), pid="p2")
    attack(s, (host, "p3"), (other, "p3"), pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("cold", [False, True])
def test_sacrificing_declared_companion_during_payment_does_not_recheck_group(cards, tmp_path, cold):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    support = put(s, "Craw Wurm", "battlefield", pid="p2")
    altar = put(s, "Phyrexian Altar", "battlefield", pid="p2")
    put(s, "Island", "battlefield", pid="p2")
    aura = put(s, "Brainwash", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="set_prefs", payment="self")
    mana(s, pid="p2", C=2)
    attack(s, (host, "p1"), (support, "p3"), pid="p2")
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    if cold:
        import subprocess
        import sys

        saved = tmp_path / "sacrificed-attacker-payment.json"
        saved.write_text(s.state.model_dump_json())
        code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import mana_pool
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
host,support,altar=sys.argv[3:]
s.perform('p2',{'type':'activate_ability','card_id':altar,'ability':0,'mana_choice':'G','cost_choices':[{'component':0,'cards':[support]}]})
assert s.state.cards[host].attacking is not None
assert s.state.cards[support].zone=='p2:graveyard' and s.state.cards[support].attacking is None
assert mana_pool(s,'p2')=={}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(saved), str(cards.db_path), host.id, support.id, altar.id],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return
    act(
        s,
        "p2",
        type="activate_ability",
        card_id=altar.id,
        ability=0,
        mana_choice="G",
        cost_choices=[{"component": 0, "cards": [support.id]}],
    )
    assert s.state.cards[support.id].zone == "p2:graveyard"
    assert s.state.cards[host.id].attacking is not None
    assert s.state.cards[support.id].attacking is None
    from tests.game_helpers import mana_pool

    assert mana_pool(s, "p2") == {}
    roundtrip(s)


@pytest.mark.parametrize("changed", ["host", "support"])
def test_prepared_attack_does_not_reuse_a_returned_object(cards, changed):
    s = setup(cards)
    host = put(s, "Okk", "battlefield", pid="p2")
    support = put(s, "Craw Wurm", "battlefield", pid="p2")
    lands = [
        c.id
        for c in s.state.cards.values()
        if c.owner == "p2" and c.name == "Island" and c.zone == "p2:library"
    ][:3]
    act(s, "p2", type="move", card_ids=lands, to={"player": "p2", "zone": "battlefield"})
    aura = put(s, "Brainwash", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="set_prefs", payment="self")
    attack(s, (host, "p1"), (support, "p3"), pid="p2")
    assert s.state.rules.decision.resume["paid_then"]["stage"] == "declare_attackers"
    replacement = host if changed == "host" else support
    # Recorded table moves exercise an exact-object race in a saved payment;
    # the actual Phyrexian Altar case separately proves a canonical departure.
    act(s, "p2", type="move", card_ids=[replacement.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[replacement.id], to={"player": "p2", "zone": "battlefield"})
    for land in lands:
        act(s, "p2", type="activate_ability", card_id=land, ability=0)
    if s.state.rules.decision and s.state.rules.decision.resume.get("step") == "pay_mana":
        act(s, "p2", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    assert s.state.cards[replacement.id].attacking is None
    survivor = support if changed == "host" else host
    assert s.state.cards[survivor.id].attacking is not None
    roundtrip(s)
