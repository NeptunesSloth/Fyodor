"""Conditional attachment and Army animation use native continuous effects."""

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
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Corrupted Shapeshifter", "Primal Clay", "Primal Plasma", "Aquamorph Entity", "Shapeshifter"]
DATA = json.loads((Path(__file__).parent / "fixtures/chosen_forms95_cards.json").read_text())
ALL = [c["name"] for c in DATA] + ["Clone"] * 2


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, "main1", 1)
    return s


def cast(s, name, pid="p1", targets=(), **kwargs):
    candidates = [
        c
        for c in s.state.cards.values()
        if c.name == name
        and c.owner == pid
        and c.zone not in (f"{pid}:battlefield", "stack")
        and c.ability is None
    ]
    source = next((c for c in candidates if c.zone == f"{pid}:hand"), candidates[0])
    if source.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[source.id], to={"player": pid, "zone": "hand"})
    mana(s, pid, C=20, W=10, U=10, B=10, R=10, G=10)
    wait_priority(s, pid)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


def ch(s, source):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[source.id])


def empty_hands(s, *players):
    for pid in players:
        hand = list(s.state.zones.get(f"{pid}:hand", []))
        if hand:
            act(s, pid, type="move", card_ids=hand, to={"player": pid, "zone": "library"})


@pytest.mark.parametrize("name", NAMES)
def test_canonical_cast_and_choice(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    s = game(cards)
    source = cast(s, name)
    d = s.state.rules.decision
    assert d is not None
    answer = "3" if name == "Shapeshifter" else d.options[0].id
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert ch(s, source).pt == (
        (3, 4) if name == "Shapeshifter" else (5, 1) if name == "Aquamorph Entity" else (3, 3)
    )
    roundtrip(s)


def choose(s, answer):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)


@pytest.mark.parametrize(
    "name,option,pt,keyword",
    [
        ("Corrupted Shapeshifter", "2/5 vigilance", (2, 5), "vigilance"),
        ("Corrupted Shapeshifter", "0/12 defender", (0, 12), "defender"),
        ("Primal Clay", "2/2 flying", (2, 2), "flying"),
        ("Primal Clay", "1/6 Wall defender", (1, 6), "defender"),
        ("Primal Plasma", "2/2 flying", (2, 2), "flying"),
        ("Primal Plasma", "1/6 defender", (1, 6), "defender"),
        ("Aquamorph Entity", "1/5", (1, 5), None),
    ],
)
def test_every_alternative_form(cards, name, option, pt, keyword):
    s = game(cards)
    source = cast(s, name)
    choose(s, option)
    assert ch(s, source).pt == pt
    if keyword:
        assert keyword in ch(s, source).keywords
    if "Wall" in option:
        assert "Wall" in ch(s, source).subtypes
    old = Plan.view(s.state, "p1", cards).oid(source)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, source).pt == (0, 0)
    assert not ch(s, source).keywords & {"flying", "vigilance", "defender"}
    assert Plan.view(s.state, "p1", cards).oid(s.state.cards[source.id]) != old


def test_actual_entering_clone_accumulates_keywords_and_wall(cards):
    s = game(cards)
    source = cast(s, "Primal Clay")
    choose(s, "2/2 flying")
    clone = cast(s, "Clone")
    choose(s, source.id)
    choose(s, "1/6 Wall defender")
    assert ch(s, clone).pt == (1, 6)
    assert {"flying", "defender"} <= ch(s, clone).keywords
    assert "Wall" in ch(s, clone).subtypes and "Artifact" in ch(s, clone).types
    assert ch(s, source).pt == (2, 2) and "defender" not in ch(s, source).keywords
    roundtrip(s)


def test_actual_mirrorweave_copies_current_form_without_new_choice(cards):
    s = game(cards)
    source = cast(s, "Corrupted Shapeshifter")
    choose(s, "0/12 defender")
    bear = cast(s, "Grizzly Bears")
    cast(s, "Mirrorweave", targets=[source.id])
    assert s.state.rules.decision is None
    assert ch(s, bear).pt == (0, 12) and "defender" in ch(s, bear).keywords
    to_phase(s, "main1", 2)
    assert ch(s, bear).pt == (2, 2)


def test_native_morph_paid_before_preflip_choice(cards):
    s = game(cards)
    source = cast(s, "Aquamorph Entity", face_down=True)
    assert s.state.rules.decision is None and ch(s, source).pt == (2, 2)
    mana(s, "p1", C=2, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="turn_face_up", card_id=source.id)
    assert s.state.cards[source.id].face_down and ch(s, source).pt == (2, 2)
    assert s.state.rules.decision.resume["step"] == "chosen_form_up95"
    paid_pool = dict(s.state.players["p1"].mana)
    choose(s, "1/5")
    assert s.state.players["p1"].mana == paid_pool
    assert not s.state.cards[source.id].face_down and ch(s, source).pt == (1, 5)
    roundtrip(s)


def test_effect_driven_break_open_preflip_choice(cards):
    s = game(cards)
    source = cast(s, "Aquamorph Entity", face_down=True)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    cast(s, "Break Open", targets=[source.id])
    assert s.state.cards[source.id].face_down
    assert s.state.rules.decision.player == "p2"
    choose(s, "5/1")
    assert ch(s, source).pt == (5, 1) and not s.state.cards[source.id].face_down
    roundtrip(s)


def test_native_blink_rechooses_original_copiable_form(cards):
    s = game(cards)
    source = cast(s, "Primal Plasma")
    choose(s, "2/2 flying")
    old = Plan.view(s.state, "p1", cards).oid(s.state.cards[source.id])
    cast(s, "Ephemerate", targets=[source.id])
    choose(s, "1/6 defender")
    assert ch(s, source).pt == (1, 6) and "defender" in ch(s, source).keywords
    assert "flying" not in ch(s, source).keywords
    assert Plan.view(s.state, "p1", cards).oid(s.state.cards[source.id]) != old


def test_shapeshifter_number_cda_not_copied(cards):
    s = game(cards)
    source = cast(s, "Shapeshifter")
    choose(s, "6")
    assert ch(s, source).pt == (6, 1)
    clone = cast(s, "Clone")
    choose(s, source.id)
    choose(s, "2")
    assert ch(s, clone).pt == (2, 5) and ch(s, source).pt == (6, 1)
    bear = cast(s, "Grizzly Bears")
    cast(s, "Mirrorweave", targets=[source.id])
    assert ch(s, bear).pt == (0, 7)
    cast(s, "Giant Growth", targets=[source.id])
    assert ch(s, source).pt == (9, 4)
    roundtrip(s)


def test_actual_token_copy_chooses_own_form_and_inherits_keywords(cards):
    s = game(cards)
    source = cast(s, "Primal Plasma")
    choose(s, "2/2 flying")
    cast(s, "Cackling Counterpart", targets=[source.id])
    choose(s, "1/6 defender")
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 1
    assert ch(s, tokens[0]).pt == (1, 6) and {"flying", "defender"} <= ch(s, tokens[0]).keywords
    assert ch(s, source).pt == (2, 2) and "defender" not in ch(s, source).keywords
    roundtrip(s)


def test_preentry_form_visible_to_actual_power_trigger(cards):
    s = game(cards)
    cast(s, "Garruk's Packleader")
    source = cast(s, "Aquamorph Entity")
    before = len(s.state.zones["p1:hand"])
    choose(s, "5/1")
    assert ch(s, source).pt == (5, 1)
    choose(s, "yes")
    assert len(s.state.zones["p1:hand"]) == before + 1


def test_shapeshifter_upkeep_last_choice_and_optional_decline(cards):
    s = game(cards)
    source = cast(s, "Shapeshifter")
    choose(s, "6")
    to_phase(s, "upkeep", 4)
    settle(s)
    assert s.state.rules.decision is not None
    choose(s, "yes")
    choose(s, "1")
    assert ch(s, source).pt == (1, 6)
    to_phase(s, "upkeep", 7)
    settle(s)
    choose(s, "no")
    assert ch(s, source).pt == (1, 6)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, source).pt == (0, 7)


def cold(s, tmp_path, mode, source):
    import os
    import subprocess
    import sys

    import app

    saved = tmp_path / f"forms95-{mode}.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_chosen_forms95 import choose,ch,cast
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode,cid=sys.argv[3:5];source=s.state.cards[cid]
if mode=='morph':
 assert source.face_down and ch(s,source).pt==(2,2)
 paid_pool=dict(s.state.players['p1'].mana)
 choose(s,'1/5');assert not s.state.cards[cid].face_down and ch(s,source).pt==(1,5)
 assert s.state.players['p1'].mana==paid_pool
elif mode=='entry':
 assert source.zone=='stack';choose(s,'1/6 Wall defender');assert ch(s,source).pt==(1,6)
 assert 'Wall' in ch(s,source).subtypes and 'defender' in ch(s,source).keywords
elif mode=='copy':
 assert ch(s,source).pt==(1,6) and {'flying','defender'}<=ch(s,source).keywords
elif mode=='number':
 assert ch(s,source).pt==(6,1)
 clone=cast(s,'Clone');choose(s,cid);choose(s,'2')
 assert ch(s,clone).pt==(2,5) and ch(s,source).pt==(6,1)
else:
 assert source.face_down;choose(s,'5/1');assert ch(s,source).pt==(5,1)
 assert not s.state.cards[cid].face_down
roundtrip(s);repo.close()
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path), mode, source.id],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["morph", "entry", "copy", "number", "effect"])
def test_true_cold_form_continuations(cards, tmp_path, mode):
    s = game(cards)
    if mode == "morph":
        source = cast(s, "Aquamorph Entity", face_down=True)
        mana(s, "p1", C=2, U=1)
        wait_priority(s, "p1")
        act(s, "p1", type="turn_face_up", card_id=source.id)
    elif mode == "entry":
        source = cast(s, "Primal Clay")
    elif mode == "copy":
        original = cast(s, "Primal Plasma")
        choose(s, "2/2 flying")
        source = cast(s, "Clone")
        choose(s, original.id)
        choose(s, "1/6 defender")
    elif mode == "number":
        source = cast(s, "Shapeshifter")
        choose(s, "6")
    else:
        source = cast(s, "Aquamorph Entity", face_down=True)
        act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
        cast(s, "Break Open", targets=[source.id])
    cold(s, tmp_path, mode, source)


@pytest.mark.parametrize(
    "name,first,second,expected,keywords",
    [
        ("Corrupted Shapeshifter", "0/12 defender", "3/3 flying", (3, 3), {"flying", "defender"}),
        ("Aquamorph Entity", "1/5", "5/1", (5, 1), set()),
    ],
)
def test_actual_entering_clone_other_forms_and_original(cards, name, first, second, expected, keywords):
    s = game(cards)
    source = cast(s, name)
    choose(s, first)
    original = ch(s, source).pt
    clone = cast(s, "Clone")
    choose(s, source.id)
    choose(s, second)
    assert ch(s, clone).pt == expected and keywords <= ch(s, clone).keywords
    assert ch(s, source).pt == original
    roundtrip(s)


def test_shapeshifter_bounded_seven_has_zero_toughness_and_dies(cards):
    s = game(cards)
    source = cast(s, "Shapeshifter")
    choose(s, "7")
    assert s.state.cards[source.id].zone == "p1:graveyard" and ch(s, source).pt == (0, 7)
    roundtrip(s)


def test_actual_ixidron_then_break_open_copied_entity_rechooses(cards):
    s = game(cards)
    original = cast(s, "Aquamorph Entity")
    choose(s, "1/5")
    clone = cast(s, "Clone")
    choose(s, original.id)
    choose(s, "1/5")
    cast(s, "Ixidron")
    assert s.state.cards[clone.id].face_down and ch(s, clone).pt == (2, 2)
    act(s, "p1", type="set_controller", card_ids=[clone.id], player="p2")
    cast(s, "Break Open", targets=[clone.id])
    assert s.state.rules.decision is not None and s.state.cards[clone.id].face_down
    choose(s, "5/1")
    assert ch(s, clone).pt == (5, 1) and not s.state.cards[clone.id].face_down
    assert s.state.cards[original.id].face_down and ch(s, original).pt == (2, 2)
    roundtrip(s)


def test_copied_away_entity_has_no_turnup_form_replacement(cards):
    s = game(cards)
    entity = cast(s, "Aquamorph Entity")
    choose(s, "1/5")
    bear = cast(s, "Grizzly Bears")
    cast(s, "Mirrorweave", targets=[bear.id])
    assert ch(s, entity).pt == (2, 2)
    cast(s, "Ixidron")
    assert s.state.cards[entity.id].face_down
    act(s, "p1", type="set_controller", card_ids=[entity.id], player="p2")
    cast(s, "Break Open", targets=[entity.id])
    assert s.state.rules.decision is None
    assert not s.state.cards[entity.id].face_down and ch(s, entity).pt == (2, 2)
    roundtrip(s)


def test_native_humility_removes_preflip_replacement_then_zero_original_dies(cards):
    s = game(cards)
    entity = cast(s, "Aquamorph Entity", face_down=True)
    humility = cast(s, "Humility")
    act(s, "p1", type="set_controller", card_ids=[entity.id], player="p2")
    cast(s, "Break Open", targets=[entity.id])
    assert s.state.rules.decision is None
    assert not s.state.cards[entity.id].face_down and ch(s, entity).pt == (1, 1)
    cast(s, "Disenchant", targets=[humility.id])
    assert s.state.cards[entity.id].zone == "p1:graveyard"
    assert ch(s, entity).pt == (0, 0)
    roundtrip(s)


def test_copied_entity_can_pay_prospective_morph_cost(cards):
    s = game(cards)
    original = cast(s, "Aquamorph Entity")
    choose(s, "1/5")
    clone = cast(s, "Clone")
    choose(s, original.id)
    choose(s, "1/5")
    cast(s, "Ixidron")
    assert s.state.cards[clone.id].face_down
    mana(s, "p1", C=2, U=1)
    wait_priority(s, "p1")
    before = sum(s.state.players["p1"].mana.values())
    act(s, "p1", type="turn_face_up", card_id=clone.id, method="morph")
    assert s.state.cards[clone.id].face_down
    assert before - sum(s.state.players["p1"].mana.values()) == 3
    paid = dict(s.state.players["p1"].mana)
    choose(s, "5/1")
    assert s.state.players["p1"].mana == paid
    assert not s.state.cards[clone.id].face_down and ch(s, clone).pt == (5, 1)
    roundtrip(s)


def test_copied_away_entity_cannot_pay_original_morph_cost(cards):
    from app.game.errors import ActionError

    s = game(cards)
    entity = cast(s, "Aquamorph Entity")
    choose(s, "1/5")
    bear = cast(s, "Grizzly Bears")
    cast(s, "Mirrorweave", targets=[bear.id])
    cast(s, "Ixidron")
    mana(s, "p1", C=2, U=1)
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="can't be turned face up"):
        act(s, "p1", type="turn_face_up", card_id=entity.id, method="morph")
    assert s.state.model_dump_json() == before and s.state.cards[entity.id].face_down
