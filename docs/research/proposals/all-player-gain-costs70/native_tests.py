"""Every other player pays one shared nominal life-gain event as a real alternative cost."""

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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Reverent Silence", "Skyshroud Cutter"]
DATA = json.loads((Path(__file__).parent / "fixtures/all_player_gain_costs70_cards.json").read_text())


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


def setup(cards, name, forest="Forest"):
    ns = [c["name"] for c in DATA]
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    land = put(s, forest, "battlefield") if forest else None
    source = put(s, name, "hand")
    return s, source, land


def alt(s, source, **kwargs):
    wait_priority(s, "p1")
    return act(s, "p1", type="cast_spell", card_id=source.id, alt_cost=f"{source.id}:0", sources=[], **kwargs)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_whole_card(name, cards):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("forest", ["Forest", "Savannah"])
def test_native_alternative_has_every_other_player_gain_nominal_life_in_one_batch(name, forest, cards):
    s, source, _ = setup(cards, name, forest)
    resolved = alt(s, source)
    n = 6 if name == NAMES[0] else 5
    assert [s.state.players[p].life for p in ["p1", "p2", "p3"]] == [40, 40 + n, 40 + n]
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert [(r.recipient, r.nominal_amount) for r in record.opponent_gain_costs] == [("p2", n), ("p3", n)]
    changes = [step for step in resolved.r if step["type"] == "rules_life_changes"]
    assert len(changes) == 1 and changes[0]["changes"] == [
        {"player": "p2", "delta": n},
        {"player": "p3", "delta": n},
    ]
    answer(s)
    assert source.zone == ("p1:graveyard" if name == NAMES[0] else "p1:battlefield")
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_cannot_choose_only_one_other_player_or_the_payer(name, cards):
    s, source, _ = setup(cards, name)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source, cost_choices=[{"component": 0, "cards": ["p2"]}])
    assert s.state.model_dump_json() == before
    with pytest.raises(ActionError):
        alt(s, source, cost_choices=[{"component": 0, "cards": ["p1", "p2", "p3"]}])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("name", NAMES)
def test_any_blocked_other_player_or_missing_forest_prevents_the_whole_cost_atomically(name, cards):
    s, source, _ = setup(cards, name, forest=None)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source)
    assert s.state.model_dump_json() == before
    put(s, "Forest", "battlefield")
    put(s, "Platinum Emperion", "battlefield", pid="p3")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source)
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("name", NAMES)
def test_actual_normal_mana_cost_never_gives_other_players_life(name, cards):
    s, source, _ = setup(cards, name, forest=None)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "G": 1})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert not record.opponent_gain_costs
    assert [s.state.players[p].life for p in ["p1", "p2", "p3"]] == [40, 40, 40]
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_real_alternative_still_pays_total_generic_cost_increase_once(name, cards):
    s, source, _ = setup(cards, name)
    put(s, "Sphere of Resistance", "battlefield", pid="p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s, source)
    assert s.state.model_dump_json() == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    alt(s, source)
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.mana_spent == {"C": 1} and len(record.opponent_gain_costs) == 2
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("modifier", ["Sulfuric Vortex", "Tainted Remedy", "Alhammarret's Archive"])
def test_modified_actual_gain_or_loss_still_pays_both_nominal_costs(name, modifier, cards):
    s, source, _ = setup(cards, name)
    put(s, modifier, "battlefield", pid="p2" if modifier == "Alhammarret's Archive" else "p1")
    alt(s, source)
    n = 6 if name == NAMES[0] else 5
    expected = {
        "Sulfuric Vortex": (40, 40),
        "Tainted Remedy": (40 - n, 40 - n),
        "Alhammarret's Archive": (40 + 2 * n, 40 + n),
    }[modifier]
    assert tuple(s.state.players[p].life for p in ["p2", "p3"]) == expected
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert [(r.recipient, r.nominal_amount) for r in record.opponent_gain_costs] == [("p2", n), ("p3", n)]
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_real_counterspell_does_not_refund_paid_other_player_life(name, cards):
    s, source, _ = setup(cards, name)
    alt(s, source)
    counter = put(s, "Counterspell", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 2})
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[source.id], sources=[])
    answer(s)
    n = 6 if name == NAMES[0] else 5
    assert source.zone == "p1:graveyard" and [s.state.players[p].life for p in ["p2", "p3"]] == [
        40 + n,
        40 + n,
    ]
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_genuine_cold_all_other_players_wait_for_both_replacement_choices(name, cards, tmp_path):
    import subprocess
    import sys

    from app.rules import opponent_gain_costs44

    s, source, _ = setup(cards, name)
    put(s, "Sphere of Resistance", "battlefield", pid="p2")
    for pid in ["p2", "p3"]:
        put(s, "Alhammarret's Archive", "battlefield", pid=pid)
        put(s, "Angel of Vitality", "battlefield", pid=pid)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    alt(s, source)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    assert [s.state.players[p].life for p in ["p2", "p3"]] == [40, 40]
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    n = 6 if name == NAMES[0] else 5
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
source,n=sys.argv[3],int(sys.argv[4])
d=s.state.rules.decision
assert d and d.player=='p2'
first=next(o.id for o in d.options if "Alhammarret" in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[first])
assert [s.state.players[p].life for p in ['p2','p3']]==[40,40]
d=s.state.rules.decision
assert d and d.player=='p3'
first=next(o.id for o in d.options if "Angel of Vitality" in o.label)
resolved=act(s,d.player,type='choose',decision_id=d.id,option_ids=[first])
assert [s.state.players[p].life for p in ['p2','p3']]==[40+2*n+1,40+2*(n+1)]
record=s.state.rules.payments[s.state.rules.object_id(source)]
assert [(v.recipient,v.nominal_amount) for v in record.opponent_gain_costs]==[('p2',n),('p3',n)]
assert record.mana_spent=={'C':1}
steps=[v for v in resolved.r if v['type']=='rules_life_changes']
assert len(steps)==1 and len(steps[0]['changes'])==2
assert not s.state.rules.decision
answer(s)
assert s.state.cards[source].zone in ['p1:graveyard','p1:battlefield']
roundtrip(s)
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, str(n)],
        cwd=Path(opponent_gain_costs44.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
