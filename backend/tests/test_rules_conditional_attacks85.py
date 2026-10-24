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
from tests.test_rules_wave30p_combat import attack

DATA = json.loads((Path(__file__).parent / "fixtures/conditional_attacks85_cards.json").read_text())
NAMES = ["Ironsoul Enforcer", "Wargling"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    keys = [
        "mana_cost",
        "cmc",
        "type_line",
        "oracle_text",
        "power",
        "toughness",
        "colors",
        "color_identity",
        "keywords",
    ]
    for i, d in enumerate(DATA):
        name = d["name"]
        base[name] = card(name, set_code="a85", number=str(i), **{k: d[k] for k in keys if k in d})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup85(cards, name):
    names = [
        *[c["name"] for c in DATA],
        "Sol Ring",
        "Grizzly Bears",
        "Forest",
        "Swords to Plowshares",
        "Giant Growth",
    ]
    s = table(cards, names, names, names)
    source = put(s, name, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    artifact = put(s, "Sol Ring", "graveyard")
    start(s)
    return s, source, bear, artifact


@pytest.mark.parametrize("name", NAMES)
def test_whole85(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("who", ["source", "commander"])
def test_ironsoul_returns_artifact_from_actual_alone_attack(cards, who):
    s, source, bear, artifact = setup85(cards, NAMES[0])
    if who == "commander":
        attacker = put(s, "Krenko, Mob Boss", "battlefield")
        to_phase(s, "main1", turn=7)
    else:
        attacker = source
    to_phase(s, "declare_attackers", turn=7 if who == "commander" else 4)
    attack(s, (attacker, "p2"))
    settle(s)
    d = s.state.rules.decision
    if d and artifact.id in {o.id for o in d.options}:
        pick(s, [artifact.id])
        settle(s)
    assert s.state.cards[artifact.id].zone == "p1:battlefield"


@pytest.mark.parametrize("mode", ["unrelated", "together"])
def test_ironsoul_does_not_trigger_for_unrelated_or_non_alone_attack(cards, mode):
    s, source, bear, artifact = setup85(cards, NAMES[0])
    to_phase(s, "declare_attackers", turn=4)
    attackers = [(bear, "p2")] if mode == "unrelated" else [(source, "p2"), (bear, "p2")]
    attack(s, *attackers)
    settle(s)
    assert s.state.cards[artifact.id].zone == "p1:graveyard"


@pytest.mark.parametrize("qualifies", [True, False])
def test_wargling_header_ferocious_native_pump_trample_and_expiry(cards, qualifies):
    s, source, bear, _ = setup85(cards, NAMES[1])
    if qualifies:
        put(s, "Ironsoul Enforcer", "battlefield")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"))
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(source)
    assert ch.pt == ((3, 2) if qualifies else (2, 2))
    assert ("trample" in ch.keywords) == qualifies
    assert ("trample" in Plan(s.state, "p1", s.cards, None).ch(bear).keywords) == qualifies
    to_phase(s, "main1", turn=7)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id]).pt == (2, 2)
    assert "trample" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).keywords


def test_wargling_ferocious_is_not_rechecked_on_resolution(cards):
    s, source, bear, _ = setup85(cards, NAMES[1])
    big = put(s, "Ironsoul Enforcer", "battlefield")
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"))
    assert s.state.zones.get("stack")
    spell = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[big.id])
    settle(s)
    assert s.state.cards[big.id].zone == "p1:exile"
    assert Plan(s.state, "p1", s.cards, None).ch(source).pt == (3, 2)
    assert "trample" in Plan(s.state, "p1", s.cards, None).ch(bear).keywords


@pytest.mark.parametrize("name", NAMES)
def test_native_printed_cast85(cards, name):
    s, source, bear, _ = setup85(cards, name)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    mana(s, C=4 if name == NAMES[0] else 1, **({"W": 1} if name == NAMES[0] else {"G": 1}))
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"


def test_ironsoul_ignores_opponents_commander(cards):
    s, source, bear, artifact = setup85(cards, NAMES[0])
    commander = put(s, "Atraxa, Praetors' Voice", "battlefield", "p2")
    to_phase(s, "declare_attackers", turn=5)
    attack(s, (commander, "p1"), pid="p2")
    settle(s)
    assert s.state.cards[artifact.id].zone == "p1:graveyard"


def test_commander_copy_matching_both_ironsoul_subjects_triggers_once(cards):
    s, source, bear, artifact = setup85(cards, NAMES[0])
    commander = put(s, "Krenko, Mob Boss", "battlefield")
    to_phase(s, "main1", turn=7)
    spell = put(s, "Cytoshape", "hand")
    mana(s, C=1, G=1, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[commander.id])
    settle(s)
    assert s.state.rules.decision and source.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [source.id])
    settle(s)
    sword = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=sword.id, targets=[source.id])
    settle(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=7)
    attack(s, (commander, "p2"))
    d = s.state.rules.decision
    if d and artifact.id in {o.id for o in d.options}:
        pick(s, [artifact.id])
    entries = list(s.state.rules.stack.values())
    assert len(entries) == 1, [e.model_dump() for e in entries]
    settle(s)
    assert s.state.cards[artifact.id].zone == "p1:battlefield"


@pytest.mark.parametrize("name", NAMES)
def test_genuine_fresh_process_pending_attack_trigger85(cards, tmp_path, name):
    import subprocess
    import sys

    import app

    s, source, bear, artifact = setup85(cards, name)
    big = put(s, NAMES[0], "battlefield") if name == NAMES[1] else None
    spell = put(s, "Swords to Plowshares", "hand") if big else None
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, W=1)
    attack(s, (source, "p2"))
    if name == NAMES[0]:
        assert s.state.rules.decision is not None
    else:
        assert s.state.zones.get("stack")
    saved = tmp_path / "attack85.json"
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
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,source,bear,artifact,big,spell=sys.argv[3:]
if name=='Ironsoul Enforcer':
 d=s.state.rules.decision
 assert d and artifact in {o.id for o in d.options}
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[artifact]);settle(s)
 assert s.state.cards[artifact].zone=='p1:battlefield'
else:
 act(s,'p1',type='cast_spell',card_id=spell,targets=[big]);settle(s)
 assert s.state.cards[big].zone=='p1:exile'
 assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source]).pt==(3,2)
 assert 'trample' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear]).keywords
roundtrip(s);repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            name,
            source.id,
            bear.id,
            artifact.id,
            big.id if big else "",
            spell.id if spell else "",
        ],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
