"""Native copiable entry coin forms, including saved independent token flips."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import (
    copying,
)
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_random_consequences import faces
from tests.test_rules_wave30m_durations import three

DATA = Path(__file__).parent / "fixtures/random_characteristic_choices41_cards.json"


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"],
            set_code="ce41",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code")},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())] + ["Grizzly Bears"]
    s = three(cards, names, names, names)
    start(s)
    return s


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("heads", [True, False])
def test_actual_cast_uses_copiable_permanent_form_and_no_win_loss_event(cards, monkeypatch, heads):
    s = setup(cards)
    encounter = put(s, "Chance Encounter", "battlefield")
    faces(monkeypatch, [int(heads)])
    source = cast(s, "Molten Sentry")
    current = ch(s, source)
    assert current.pt == ((5, 2) if heads else (2, 5)) and current.keywords == (
        {"haste"} if heads else {"defender"}
    )
    assert current.types == {"Creature"} and current.subtypes == {"Elemental"} and current.colors == {"R"}
    recipe = copying.recipe_of(Plan(s.state, "p1", s.cards, None), s.state.cards[source.id])
    copied = copying.characteristics(recipe, s.cards)
    assert (copied.power, copied.toughness) == (("5", "2") if heads else ("2", "5"))
    assert copied.keywords == current.keywords and not s.state.cards[encounter.id].counters.get("luck")
    roundtrip(s)


def test_actual_blink_replaces_old_form_and_new_incarnation_flips_once(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 0])
    source = cast(s, "Molten Sentry")
    old = s.state.rules.object_id(source.id)
    cast(s, "Cloudshift", [source.id], target_counts=[1])
    assert (
        s.state.rules.object_id(source.id) != old
        and ch(s, source).pt == (2, 5)
        and ch(s, source).keywords == {"defender"}
    )
    roundtrip(s)


def test_already_battlefield_copy_takes_form_without_flipping(cards, monkeypatch):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    faces(monkeypatch, [1])
    source = cast(s, "Molten Sentry")
    cast(s, "Mirrorweave", [source.id], target_counts=[1])
    assert (
        ch(s, bear).pt == (5, 2)
        and ch(s, bear).keywords == {"haste"}
        and ch(s, bear).subtypes == {"Elemental"}
    )
    roundtrip(s)


def test_actual_entering_clone_flips_its_own_coin_and_keeps_copiable_abilities(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 0])
    source = cast(s, "Molten Sentry")
    clone = cast(s, "Clone")
    d = s.state.rules.decision
    assert d is not None and source.id in {o.id for o in d.options}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert ch(s, clone).pt == (2, 5) and ch(s, clone).keywords == {"haste", "defender"}
    assert ch(s, source).pt == (5, 2) and ch(s, source).keywords == {"haste"}
    roundtrip(s)


def test_actual_token_copy_performs_its_own_entry_flip(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 0])
    source = cast(s, "Molten Sentry")
    cast(s, "Cackling Counterpart", [source.id], target_counts=[1])
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert (
        len(tokens) == 1
        and ch(s, tokens[0]).pt == (2, 5)
        and ch(s, tokens[0]).keywords == {"haste", "defender"}
    )
    roundtrip(s)


def test_native_token_replacement_each_copy_gets_separate_saved_form(cards, monkeypatch):
    s = setup(cards)
    put(s, "Parallel Lives", "battlefield")
    faces(monkeypatch, [1, 0, 1])
    source = cast(s, "Molten Sentry")
    cast(s, "Cackling Counterpart", [source.id], target_counts=[1])
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and {ch(s, c).pt for c in tokens} == {(5, 2), (2, 5)}
    roundtrip(s)


def test_native_ability_removal_prevents_entry_flip_and_never_backfills_form(cards, monkeypatch):
    s = setup(cards)
    humility = cast(s, "Humility")
    faces(monkeypatch, [])
    source = cast(s, "Molten Sentry")
    assert ch(s, source).pt == (1, 1) and not ch(s, source).keywords
    cast(s, "Disenchant", [humility.id], target_counts=[1])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_native_thumb_keeps_actual_face_before_entry(cards, monkeypatch):
    s = setup(cards)
    put(s, "Krark's Thumb", "battlefield")
    faces(monkeypatch, [1, 0])
    source = cast(s, "Molten Sentry")
    d = s.state.rules.decision
    assert d.resume["phase"] == "ignore" and s.state.cards[source.id].zone == "stack"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["1"])
    settle(s)
    assert ch(s, source).pt == (2, 5) and ch(s, source).keywords == {"defender"}
    roundtrip(s)


@pytest.mark.parametrize("kind", ["counter_order", "token_coin"])
def test_saved_copiable_entry_form_or_token_coin_packet_resumes_fresh(cards, monkeypatch, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == "counter_order":
        for name in ["Renata, Called to the Hunt", "Hardened Scales", "Doubling Season"]:
            put(s, name, "battlefield")
        faces(monkeypatch, [1])
        source = cast(s, "Molten Sentry")
        d = s.state.rules.decision
        assert d.resume["step"] == "stack_enter_choice" and s.state.cards[source.id].zone == "stack"
        assert ch(s, source).pt == (5, 2)
    else:
        put(s, "Parallel Lives", "battlefield")
        faces(monkeypatch, [1])
        source = cast(s, "Molten Sentry")
        put(s, "Krark's Thumb", "battlefield")
        faces(monkeypatch, [1, 0, 1, 0])
        cast(s, "Cackling Counterpart", [source.id], target_counts=[1])
        d = s.state.rules.decision
        assert d.resume["phase"] == "ignore"
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["1"])
        settle(s)
        assert s.state.rules.decision.resume["phase"] == "ignore"
        act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
        assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")]
    saved = tmp_path / (kind + ".json")
    saved.write_text(s.state.model_dump_json())
    code = """
import importlib,sys,pytest
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
def forbidden(*args):raise AssertionError('A saved entry form or coin was randomized again')
importlib.import_module('app.game.resolve')._rng_int=forbidden
s.view('p3')
d=s.state.rules.decision
option=next(o.id for o in d.options if 'Hardened Scales' in o.label) if sys.argv[3]=='counter_order' else '0'
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]});settle(s)
if sys.argv[3]=='counter_order':
 c=s.state.cards[sys.argv[4]];ch=Plan(s.state,'p1',repo,None).ch(c)
 assert c.zone=='p1:battlefield' and c.counters.get('+1/+1')==4 and ch.pt==(9,6) and ch.keywords=={'haste'}
else:
 tokens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
 assert len(tokens)==2 and {Plan(s.state,'p1',repo,None).ch(c).pt for c in tokens}=={(5,2),(2,5)}, [(c.id,c.zone,Plan(s.state,'p1',repo,None).ch(c).pt) for c in tokens]
 assert s.state.cards[sys.argv[4]].zone=='p1:hand'
roundtrip(s);repo.close()
"""
    r = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), kind, source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_unchosen_printed_coin_form_has_zero_base_in_all_nonbattlefield_zones(cards):
    from app.rules import characteristics

    s = setup(cards)
    for zone in ('hand', 'graveyard', 'stack'):
        c = put(s, 'Molten Sentry', zone)
        raw = characteristics.of(s.state.cards[c.id], s.cards)
        assert (raw.power, raw.toughness) == ('0', '0')
        assert raw.mana_cost == '{3}{R}' and raw.mana_value == 4
        assert raw.colors == {'R'} and raw.subtypes == {'Elemental'}
        assert not raw.keywords and any('flip a coin' in a.text for a in raw.abilities)


def test_chosen_copiable_form_survives_later_ability_suppression(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1])
    source = cast(s, 'Molten Sentry')
    humility = cast(s, 'Humility')
    assert ch(s, source).pt == (1, 1) and not ch(s, source).keywords
    recipe = copying.recipe_of(Plan(s.state, 'p1', s.cards, None), s.state.cards[source.id])
    copied = copying.characteristics(recipe, s.cards)
    assert (copied.power, copied.toughness) == ('5', '2') and copied.keywords == {'haste'}
    cast(s, 'Disenchant', [humility.id], target_counts=[1])
    assert ch(s, source).pt == (5, 2) and ch(s, source).keywords == {'haste'}
    roundtrip(s)
