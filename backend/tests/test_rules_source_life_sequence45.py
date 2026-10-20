import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

ROWS = json.loads((Path(__file__).parent / "fixtures/source_life_sequence45_cards.json").read_text())
ROWS += [
    r
    for r in json.loads((Path(__file__).parent / "fixtures/abundance_cards.json").read_text())
    if r["name"] == "Abundance"
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, r in enumerate(ROWS):
        base[r["name"]] = card(r["name"], number=str(i), **{k: v for k, v in r.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [r["name"] for r in ROWS]
    s = table(cards, names, names, names)
    act(s, "p1", type="set_prefs", hold_priority=True)
    land = put(s, "Mana Confluence", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    return s, land, bear


@pytest.mark.parametrize("activation", [False, True])
def test_source_cost_before_final_cost_preserves_records(cards, activation):
    s, land, bear = setup(cards)
    source = put(s, "Greed" if activation else "Dismember", "battlefield" if activation else "hand")
    before = set(s.state.zones.get("stack", []))
    oid = s.state.rules.object_id(land.id)
    args = (
        dict(type="activate_ability", card_id=source.id, ability=0, sources=[land.id])
        if activation
        else dict(
            type="cast_spell",
            card_id=source.id,
            targets=[bear.id],
            life_symbols=["B", "B"],
            sources=[land.id],
        )
    )
    action = act(s, "p1", **args)
    losses = [
        -e["delta"]
        for e in action.r
        if e.get("type") == "life" and e.get("player") == "p1" and e.get("delta", 0) < 0
    ]
    assert losses == [1, 2 if activation else 4], losses
    aid = next(cid for cid in s.state.zones["stack"] if cid not in before)
    record = s.state.rules.payments[s.state.rules.object_id(aid)]
    assert record.life == (3 if activation else 5), record
    assert sum(record.mana_spent.values()) == 1 and record.mana_sources == [oid], record
    if activation:
        assert record.activation_life_paid == 2
    roundtrip(s)


def test_saved_native_game_uses_source_sequence_without_bootstrap(cards, tmp_path):
    s, land, bear = setup(cards)
    spell = put(s, "Dismember", "hand")
    path = tmp_path / "state.json"
    path.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
a=s.perform('p1',dict(type='cast_spell',card_id=sys.argv[3],targets=[sys.argv[4]],life_symbols=['B','B'],sources=[sys.argv[5]]))
losses=[-e['delta']for e in a.r if e.get('type')=='life'and e.get('player')=='p1'and e.get('delta',0)<0]
assert losses==[1,4],losses
r=s.state.rules.payments[s.state.rules.object_id(sys.argv[3])]
assert r.life==5 and r.mana_sources==[s.state.rules.object_id(sys.argv[5])]
assert s.state.players['p1'].life==35
"""
    env = dict(os.environ)
    p = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), spell.id, bear.id, land.id],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_saved_mid_source_draw_keeps_life_and_final_receipt(cards, tmp_path, monkeypatch):
    # Structured rider injection isolates persistence, with no card eligibility claim.
    from tests.payment_rider_injection import inject_mana_draw_rider
    from tests.test_rules_abundance import set_library

    inject_mana_draw_rider(monkeypatch, {"Mana Confluence"})
    s, land, bear = setup(cards)
    put(s, "Abundance", "battlefield")
    set_library(s, ["Forest", "Swamp"])
    spell = put(s, "Dismember", "hand")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[bear.id],
        life_symbols=["B", "B"],
        sources=[land.id],
    )
    assert s.state.rules.decision is not None and s.state.players["p1"].life == 39
    path = tmp_path / "mid.json"
    path.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
for _ in range(8):
 d=s.state.rules.decision
 if d is None:break
 ids={o.id for o in d.options}
 chosen=[next(o.id for o in d.options if o.id!='decline')]if 'decline'in ids else ['land']if 'land'in ids else [o.id for o in d.options]
 s.perform(d.player,dict(type='choose',decision_id=d.id,option_ids=chosen))
assert s.state.rules.decision is None
assert s.state.players['p1'].life==35
r=s.state.rules.payments[s.state.rules.object_id(sys.argv[3])]
assert r.life==5 and r.mana_sources==[s.state.rules.object_id(sys.argv[4])],r
assert s.state.cards[sys.argv[3]].zone=='stack'
"""
    p = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), spell.id, land.id],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ},
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
