"""Staged canonical random token modes and exact blocked-combat receipts."""

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
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_random_consequences import faces
from tests.test_rules_wave30m_durations import stops, three, to_phase

DATA = Path(__file__).parent / "fixtures/random_characteristic_choices41_cards.json"


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"],
            set_code="rc41",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code")},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())] + ["Grizzly Bears", "Sol Ring"]
    s = three(cards, names, names, names)
    stops(
        s, "upkeep", "main1", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2"
    )
    return s


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("name", ["Outlaws' Merriment", "Ydwen Efreet"])
def test_whole_canonical_card_supported_in_staged_native_pipeline(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(
    "mode,subtypes,pt,keywords",
    [
        (0, {"Human", "Warrior"}, (3, 1), {"trample", "haste"}),
        (1, {"Human", "Cleric"}, (2, 1), {"lifelink", "haste"}),
        (2, {"Human", "Rogue"}, (1, 2), {"haste"}),
    ],
)
def test_merriment_actual_upkeep_fixed_mode_creates_native_token(
    cards, monkeypatch, mode, subtypes, pt, keywords
):
    s = setup(cards)
    put(s, "Outlaws' Merriment", "battlefield")
    monkeypatch.setattr("secrets.SystemRandom.choice", lambda self, seq: seq[mode])
    to_phase(s, "upkeep", turn=4)
    entry = next(iter(s.state.rules.stack.values()))
    assert entry.modes == [mode]
    settle(s)
    if mode == 2:
        d = s.state.rules.decision
        assert d is not None and d.kind in {"choose_one", "choose_cards"}
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
        settle(s)
        assert s.state.players["p2"].life == 39
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 1
    current = ch(s, tokens[0])
    assert (
        current.subtypes == subtypes
        and current.pt == pt
        and current.keywords == keywords
        and current.colors == {"R", "W"}
    )
    roundtrip(s)


def ydwen_block(s, monkeypatch, win, *, other=False, multiple=False, thumb=False):
    efreet = put(s, "Ydwen Efreet", "battlefield", pid="p2")
    a = put(s, "Grizzly Bears", "battlefield")
    extra = put(s, "Grizzly Bears", "battlefield", pid="p2") if other else None
    second = put(s, "Grizzly Bears", "battlefield", pid="p3") if multiple else None
    if thumb:
        put(s, "Krark's Thumb", "battlefield", pid="p2")
    if second:
        act(s, "p1", type="set_controller", card_ids=[second.id], player="p1")
    start(s)
    if multiple:
        cast(s, "Entangler", [efreet.id], target_counts=[1])
    faces(monkeypatch, [1, 0] if thumb else [1 if win else 0])
    to_phase(s, "declare_attackers", turn=4)
    attackers = [{"card_id": a.id, "target": "p2"}] + (
        [{"card_id": second.id, "target": "p2"}] if second else []
    )
    act(s, "p1", type="declare_attackers", attackers=attackers)
    to_phase(s, "declare_blockers", turn=4)
    blocks = [{"blocker_id": efreet.id, "attacker_id": a.id}]
    if extra:
        blocks.append({"blocker_id": extra.id, "attacker_id": a.id})
    if second:
        blocks.append({"blocker_id": efreet.id, "attacker_id": second.id})
    act(s, "p2", type="declare_blockers", blocks=blocks)
    return efreet, a, second, extra


@pytest.mark.parametrize("win", [True, False])
def test_ydwen_actual_kept_coin_controls_unblocked_damage(cards, monkeypatch, win):
    s = setup(cards)
    efreet, a, _, _ = ydwen_block(s, monkeypatch, win)
    settle(s)
    assert (a.id in s.state.rules.blocked) == win
    assert ("cant_block" in ch(s, efreet).imposed) == (not win)
    to_phase(s, "end_combat", turn=4)
    assert s.state.players["p2"].life == (40 if win else 38)
    roundtrip(s)


@pytest.mark.parametrize("multiple", [False, True])
def test_ydwen_original_multiple_blockers_preserve_or_release_each_attacker(cards, monkeypatch, multiple):
    s = setup(cards)
    efreet, a, second, extra = ydwen_block(s, monkeypatch, False, other=not multiple, multiple=multiple)
    settle(s)
    assert (a.id in s.state.rules.blocked) == (not multiple)
    if multiple:
        assert second.id not in s.state.rules.blocked
    assert not s.state.cards[efreet.id].is_blocking
    roundtrip(s)


def test_merriment_native_token_replacement_and_source_independence(cards, monkeypatch):
    s = setup(cards)
    source = put(s, "Outlaws' Merriment", "battlefield")
    put(s, "Parallel Lives", "battlefield")
    monkeypatch.setattr("secrets.SystemRandom.choice", lambda self, seq: seq[0])
    to_phase(s, "upkeep", turn=4)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and all(
        ch(s, c).pt == (3, 1) and ch(s, c).keywords == {"trample", "haste"} for c in tokens
    )
    roundtrip(s)


def test_merriment_actual_ability_copy_keeps_preselected_mode(cards, monkeypatch):
    s = setup(cards)
    put(s, "Outlaws' Merriment", "battlefield")
    resonator = put(s, "Strionic Resonator", "battlefield")
    monkeypatch.setattr("secrets.SystemRandom.choice", lambda self, seq: seq[1])
    to_phase(s, "upkeep", turn=4)
    trigger = next(iter(s.state.rules.stack))
    assert s.state.rules.stack[trigger].modes == [1]

    def forbidden(*args):
        raise AssertionError("A preselected modal trigger was randomized again")

    monkeypatch.setattr("secrets.SystemRandom.choice", forbidden)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=resonator.id, ability=0, sources=[], targets=[trigger])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and all(
        ch(s, c).subtypes == {"Human", "Cleric"} and ch(s, c).pt == (2, 1) for c in tokens
    )
    roundtrip(s)


@pytest.mark.parametrize("win", [False, True])
def test_ydwen_trigger_receipt_survives_original_source_blink(cards, monkeypatch, win):
    s = setup(cards)
    source, attacker, _, _ = ydwen_block(s, monkeypatch, win)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p2", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p2", "zone": "battlefield"})
    settle(s)
    assert (attacker.id in s.state.rules.blocked) == win
    assert "cant_block" not in ch(s, source).imposed
    roundtrip(s)


def test_ydwen_original_other_blocker_leaving_does_not_make_attacker_unblocked(cards, monkeypatch):
    s = setup(cards)
    source, attacker, _, other = ydwen_block(s, monkeypatch, False, other=True)
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p2", "zone": "hand"})
    settle(s)
    assert attacker.id in s.state.rules.blocked and "cant_block" in ch(s, source).imposed
    to_phase(s, "main1", turn=5)
    assert "cant_block" not in ch(s, source).imposed and s.state.players["p2"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("kind", ["mode", "coin"])
def test_native_chosen_mode_or_block_coin_resumes_in_fresh_process(cards, monkeypatch, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == "mode":
        source = put(s, "Outlaws' Merriment", "battlefield")
        monkeypatch.setattr("secrets.SystemRandom.choice", lambda self, seq: seq[1])
        to_phase(s, "upkeep", turn=4)
        assert next(iter(s.state.rules.stack.values())).modes == [1]
        attacker = None
    else:
        source, attacker, _, _ = ydwen_block(s, monkeypatch, False, thumb=True)
        settle(s)
        assert s.state.rules.decision.resume["phase"] == "ignore" and s.state.rules.decision.player == "p2"
    saved = tmp_path / (kind + ".json")
    saved.write_text(s.state.model_dump_json())
    code = """
import importlib,secrets,sys,pytest
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
def forbidden(*args):raise AssertionError('A saved random outcome was sampled again')
secrets.SystemRandom.choice=forbidden
importlib.import_module('app.game.resolve')._rng_int=forbidden
if sys.argv[3]=='coin':
 d=s.state.rules.decision;s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['1']})
settle(s)
if sys.argv[3]=='mode':
 tokens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
 assert len(tokens)==1 and Plan(s.state,'p1',repo,None).ch(tokens[0]).subtypes=={'Human','Cleric'}
else:
 assert sys.argv[5] not in s.state.rules.blocked
 assert 'cant_block' in Plan(s.state,'p1',repo,None).ch(s.state.cards[sys.argv[4]]).imposed
roundtrip(s);repo.close()
"""
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            kind,
            source.id,
            attacker.id if attacker else "",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + r.stderr
