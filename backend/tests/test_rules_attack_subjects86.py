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

DATA = json.loads((Path(__file__).parent / "fixtures/attack_subjects86_cards.json").read_text())
NAMES = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="c86", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup86(cards, name):
    names = [
        *NAMES,
        "Grizzly Bears",
        "Llanowar Elves",
        "Forest",
        "Lightning Bolt",
        "Swords to Plowshares",
        "Gideon Jura",
    ]
    s = table(cards, names, names, names)
    source = put(s, name, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Llanowar Elves", "battlefield")
    start(s)
    return s, source, bear, other


@pytest.mark.parametrize("name", NAMES)
def test_whole86(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("different", [True, False])
def test_canal_native_declared_player_pair(cards, different):
    s, source, bear, _ = setup86(cards, "Canal Courier")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"), (bear, "p3" if different else "p2"))
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(source)
    assert ("cant_be_blocked" in ch.imposed) == different, ch


@pytest.mark.parametrize("count", [0, 1, 2])
def test_puppet_exact_other_original_declared_attacker(cards, count):
    s, source, bear, other = setup86(cards, "Creepy Puppeteer")
    to_phase(s, "declare_attackers", turn=4)
    pairs = [(source, "p2"), *([(bear, "p2")] if count else []), *([(other, "p2")] if count == 2 else [])]
    attack(s, *pairs)
    settle(s)
    if count == 1:
        d = s.state.rules.decision
        assert d
        pick(s, ["yes"])
        settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == ((4, 3) if count == 1 else (2, 2))


@pytest.mark.parametrize("target", [True, False])
def test_ballroom_native_zero_or_one_target_one_shared_choice(cards, target):
    s, source, bear, _ = setup86(cards, "Ballroom Brawlers")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"))
    d = s.state.rules.decision
    assert d
    pick(s, [bear.id] if target else [])
    settle(s)
    d = s.state.rules.decision
    assert d and {o.label for o in d.options} == {"First strike", "Lifelink"}
    pick(s, ["1"])
    settle(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert "lifelink" in plan.ch(source).keywords
    assert ("lifelink" in plan.ch(bear).keywords) == target


@pytest.mark.parametrize("walker_attacker", ["source", "other"])
def test_canal_requires_two_direct_player_attacks_not_planeswalker(cards, walker_attacker):
    s, source, bear, _ = setup86(cards, "Canal Courier")
    walker = put(s, "Gideon Jura", "battlefield", "p2")
    act(s, "p2", type="set_counter", card_id=walker.id, kind="loyalty", value=6)
    to_phase(s, "declare_attackers", turn=4)
    attack(
        s,
        (source, walker.id if walker_attacker == "source" else "p3"),
        (bear, walker.id if walker_attacker == "other" else "p3"),
    )
    settle(s)
    assert "cant_be_blocked" not in Plan(s.state, "p1", s.cards, None).ch(source).imposed


def test_canal_header_pair_remains_true_after_other_attacker_exiled(cards):
    s, source, bear, _ = setup86(cards, "Canal Courier")
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"), (bear, "p3"))
    spell = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    assert "cant_be_blocked" in Plan(s.state, "p1", s.cards, None).ch(source).imposed


@pytest.mark.parametrize("removed", ["source", "target"])
def test_ballroom_target_legality_and_original_nontarget_source(cards, removed):
    s, source, bear, _ = setup86(cards, "Ballroom Brawlers")
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"))
    pick(s, [bear.id])
    spell = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    victim = source if removed == "source" else bear
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    settle(s)
    if removed == "source":
        d = s.state.rules.decision
        assert d and {o.label for o in d.options} == {"First strike", "Lifelink"}
        pick(s, ["0"])
        settle(s)
        assert "first strike" in Plan(s.state, "p1", s.cards, None).ch(bear).keywords
    else:
        assert s.state.rules.decision is None or {o.label for o in s.state.rules.decision.options} != {
            "First strike",
            "Lifelink",
        }
        assert not {"first strike", "lifelink"} & set(Plan(s.state, "p1", s.cards, None).ch(source).keywords)


def test_puppet_original_other_can_change_controller_without_becoming_target(cards):
    s, source, bear, _ = setup86(cards, "Creepy Puppeteer")
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"), (bear, "p2"))
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p1"
    pick(s, ["yes"])
    settle(s)
    assert s.state.cards[bear.id].controller == "p2"
    assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == (4, 3)


@pytest.mark.parametrize("name", NAMES)
def test_actual_printed_cast86(cards, name):
    s, source, _, _ = setup86(cards, name)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    colors = {
        "Canal Courier": {"C": 5, "U": 1},
        "Creepy Puppeteer": {"C": 3, "R": 1},
        "Ballroom Brawlers": {"C": 3, "W": 2},
    }
    mana(s, **colors[name])
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    if name == "Canal Courier":
        assert s.state.table.monarch == "p1"
    if name == "Creepy Puppeteer":
        assert "haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id]).keywords


def test_canal_unblockable_expires_at_end_of_that_combat(cards):
    s, source, bear, _ = setup86(cards, "Canal Courier")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, "p2"), (bear, "p3"))
    settle(s)
    assert "cant_be_blocked" in Plan(s.state, "p1", s.cards, None).ch(source).imposed
    to_phase(s, "main2", turn=4)
    assert "cant_be_blocked" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id]).imposed


@pytest.mark.parametrize(
    "mode", ["Canal Courier", "Creepy Puppeteer", "Ballroom Brawlers", "puppet_new_other"]
)
def test_genuine_cold_native_attack_subject_packet86(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    name = "Creepy Puppeteer" if mode == "puppet_new_other" else mode
    s, source, bear, _ = setup86(cards, name)
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    if name == "Ballroom Brawlers":
        attack(s, (source, "p2"))
        pick(s, [bear.id])
        settle(s)
        assert s.state.rules.decision and {o.label for o in s.state.rules.decision.options} == {
            "First strike",
            "Lifelink",
        }
    else:
        attack(s, (source, "p2"), (bear, "p3" if name == "Canal Courier" else "p2"))
        if name == "Creepy Puppeteer":
            settle(s)
            assert s.state.rules.decision
    spell = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    saved = tmp_path / "subject86.json"
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
mode,source,bear,spell=sys.argv[3:]
if mode=='Canal Courier':
 act(s,'p1',type='cast_spell',card_id=spell,targets=[bear]);settle(s)
 assert s.state.cards[bear].zone=='p1:exile'
 assert 'cant_be_blocked' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source]).imposed
else:
 if mode=='puppet_new_other':
  act(s,'p1',type='move',card_ids=[bear],to={'player':'p1','zone':'hand'})
  act(s,'p1',type='move',card_ids=[bear],to={'player':'p1','zone':'battlefield'})
 d=s.state.rules.decision
 assert d and d.kind!='manual_resolution'
 answer='0' if mode=='Ballroom Brawlers' else 'yes'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer]);settle(s)
 if mode=='Ballroom Brawlers':
  assert 'first strike' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source]).keywords
  assert 'first strike' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear]).keywords
 else:assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear]).pt==((2,2) if mode=='puppet_new_other' else (4,3))
roundtrip(s);repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode, source.id, bear.id, spell.id],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
