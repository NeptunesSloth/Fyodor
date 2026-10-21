"""Granted foretell freezes actual source templates and binds the later selected spell face."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, casting, coverage, mana_units
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    rows = []
    for filename in ["dynamic_keyword_costs55_cards.json", "granted_foretell56_cards.json"]:
        rows.extend(json.loads((Path(__file__).parent / "fixtures" / filename).read_text()))
    for i, c in enumerate(rows):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Dream Devourer", "Bohn, Beguiling Balladeer"])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def foretell(s, card):
    ability = next(
        a for a in Plan(s.state, "p1", s.cards, None).ch(card).abilities if "foretell" in a.keywords
    )
    assert ability.granted_mana_cost is not None
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=card.id, ability=ability.index, sources=[])
    assert card.zone == "p1:foretell"
    receipt = s.state.rules.foretell_templates[card.id]
    assert receipt.object_id == s.state.rules.object_id(card.id)
    return receipt


def later(s):
    to_phase(s, "main1", 7)
    wait_priority(s, "p1")


def test_actual_granted_foretell_survives_source_departure(cards):
    s = game(cards, ["Dream Devourer", "Shivan Dragon"])
    source = put(s, "Dream Devourer", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    before = Plan(s.state, "p1", cards, None).ch(source).pt
    foretell(s, c)
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(source).pt == (before[0] + 2, before[1])
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    later(s)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 2})
    assert casting.castable(s.state, "p1", c, cards)
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


@pytest.mark.parametrize("x,paid", [(0, 0), (1, 0), (3, 1), (6, 4)])
def test_granted_foretell_reduces_announced_x_before_payment(cards, x, paid):
    s = game(cards, ["Dream Devourer", "Stonecoil Serpent"])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, "Stonecoil Serpent", "hand")
    foretell(s, c)
    answer(s)
    later(s)
    if paid:
        act(s, "p1", type="add_mana", player="p1", mana={"C": paid})
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=x, sources=[])
    answer(s)
    assert c.zone == ("p1:graveyard" if x == 0 else "p1:battlefield")
    if x:
        assert c.counters.get("+1/+1") == x
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


@pytest.mark.parametrize("face,mana", [(0, {"G": 2}), (1, {"G": 1})])
def test_granted_foretell_uses_the_later_selected_mdfc_face(cards, face, mana):
    name = "Kolvori, God of Kinship // The Ringhart Crest"
    s = game(cards, ["Dream Devourer", name])
    source = put(s, "Dream Devourer", "battlefield")
    c = put(s, name, "hand")
    foretell(s, c)
    answer(s)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    later(s)
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    assert casting.castable(s.state, "p1", c, cards)
    act(s, "p1", type="cast_spell", card_id=c.id, face=face, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and c.face == face and not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_granted_foretell_cannot_play_a_back_land_face(cards):
    name = "Valakut Awakening // Valakut Stoneforge"
    s = game(cards, ["Dream Devourer", name])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, name, "hand")
    foretell(s, c)
    answer(s)
    later(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=c.id, face=1)
    assert s.state.model_dump_json() == before


def test_granted_foretell_no_mana_cost_can_be_foretold_but_not_cast(cards):
    s = game(cards, ["Dream Devourer", "Ancestral Vision"])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, "Ancestral Vision", "hand")
    foretell(s, c)
    answer(s)
    later(s)
    assert not casting.castable(s.state, "p1", c, cards)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, sources=[])
    assert s.state.model_dump_json() == before


def test_granted_foretell_reduction_precedes_additional_spell_tax(cards):
    s = game(cards, ["Dream Devourer", "Stonecoil Serpent", "Sphere of Resistance"])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, "Stonecoil Serpent", "hand")
    foretell(s, c)
    answer(s)
    later(s)
    put(s, "Sphere of Resistance", "battlefield")
    before = s.state.model_dump_json()
    # X1 becomes foretell0; Sphere's separate1 cannot consume the unused reduction.
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == 1
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_bohn_second_spell_native_goad_and_foretelling_is_not_casting(cards):
    from app.rules import keyword_actions

    s = game(
        cards, ["Bohn, Beguiling Balladeer", "Shivan Dragon", "Lightning Bolt", "Ponder"], ["Grizzly Bears"]
    )
    put(s, "Bohn, Beguiling Balladeer", "battlefield")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    future = put(s, "Shivan Dragon", "hand")
    foretell(s, future)
    answer(s)
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    answer(s)
    assert not keyword_actions.goaded_by(Plan(s.state, "p1", cards, None).ch(victim))
    wait_priority(s, "p1")
    ponder = put(s, "Ponder", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="cast_spell", card_id=ponder.id, sources=[])
    answer(s)
    assert keyword_actions.goaded_by(Plan(s.state, "p1", cards, None).ch(victim)) == {"p1"}
    roundtrip(s)


def test_granted_foretell_cannot_refresh_an_old_receipt_for_a_new_object(cards):
    s = game(cards, ["Dream Devourer", "Shivan Dragon"])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    receipt = foretell(s, c)
    answer(s)
    later(s)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "foretell"})
    assert receipt.object_id != s.state.rules.object_id(c.id)
    assert not casting.castable(s.state, "p1", c, cards)
    assert not alt_costs.offers(s.state, "p1", c, Plan(s.state, "p1", cards, None).ch(c), cards)


def test_unknown_legacy_foretold_card_does_not_infer_a_live_source_template(cards):
    s = game(cards, ["Dream Devourer", "Shivan Dragon"])
    put(s, "Dream Devourer", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    foretell(s, c)
    answer(s)
    later(s)
    saved = s.state.model_dump(mode="json")
    saved["rules"].pop("foretell_templates")
    from app.game.session import GameSession
    from app.game.state import GameState

    restored = GameSession(GameState.model_validate(saved), cards=cards)
    card = restored.state.cards[c.id]
    assert not casting.castable(restored.state, "p1", card, cards)
    assert not alt_costs.offers(
        restored.state, "p1", card, Plan(restored.state, "p1", cards, None).ch(card), cards
    )


def test_granted_foretell_retains_original_selected_cost_x_for_restricted_mana(cards):
    s = game(cards, ["Dream Devourer", "Stonecoil Serpent", "Rosheen Meanderer"])
    put(s, "Dream Devourer", "battlefield")
    rosheen = put(s, "Rosheen Meanderer", "battlefield")
    c = put(s, "Stonecoil Serpent", "hand")
    foretell(s, c)
    answer(s)
    later(s)
    index = next(i for i, _ in casting.mana_abilities(s.state, rosheen, cards))
    act(s, "p1", type="activate_ability", card_id=rosheen.id, ability=index, sources=[])
    assert sum(unit.sym == "C" for unit in s.state.players["p1"].mana_units) == 4
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, sources=[])
    answer(s)
    assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == 3
    assert sum(unit.sym == "C" for unit in s.state.players["p1"].mana_units) == 3
    roundtrip(s)


def test_printed_foretell_is_retained_and_also_triggers_dream_devourer(cards):
    s = game(cards, ["Dream Devourer", "Doomskar"])
    source = put(s, "Dream Devourer", "battlefield")
    c = put(s, "Doomskar", "hand")
    ability = next(a for a in Plan(s.state, "p1", cards, None).ch(c).abilities if "foretell" in a.keywords)
    assert ability.granted_mana_cost is None
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability.index, sources=[])
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(source).pt == (2, 3)
    assert c.id not in s.state.rules.foretell_templates
    roundtrip(s)


def test_effect_making_a_card_foretold_does_not_count_as_foretelling(cards):
    s = game(cards, ["Dream Devourer", "Ethereal Valkyrie", "Shivan Dragon"])
    source = put(s, "Dream Devourer", "battlefield")
    put(s, "Shivan Dragon", "hand")
    c = put(s, "Ethereal Valkyrie", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "W": 1, "U": 1})
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[])
    answer(s)
    assert s.state.rules.foretold and c.zone == "p1:battlefield"
    assert Plan(s.state, "p1", cards, None).ch(source).pt == (0, 3)
    roundtrip(s)


@pytest.mark.parametrize("kind", ["foretell_dream", "foretell_bohn", "cast_x", "cast_back", "legacy_unknown"])
def test_true_cold_granted_cost_template_receipts(cards, tmp_path, kind):
    import subprocess
    import sys

    from app.rules import dynamic_zone_keyword_costs56

    name = "Bohn, Beguiling Balladeer" if kind == "foretell_bohn" else "Dream Devourer"
    target = "Kolvori, God of Kinship // The Ringhart Crest" if kind == "cast_back" else "Stonecoil Serpent"
    s = game(cards, [name, target])
    source = put(s, name, "battlefield")
    c = put(s, target, "hand")
    if kind.startswith("foretell"):
        ability = next(
            a for a in Plan(s.state, "p1", cards, None).ch(c).abilities if "foretell" in a.keywords
        )
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
        action = dict(type="activate_ability", card_id=c.id, ability=ability.index, sources=[])
    else:
        foretell(s, c)
        answer(s)
        if kind != "legacy_unknown":
            act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
        later(s)
        act(s, "p1", type="add_mana", player="p1", mana={"G": 1} if kind == "cast_back" else {"C": 1})
        action = dict(type="cast_spell", card_id=c.id, sources=[])
        if kind == "cast_back":
            action["face"] = 1
        else:
            action["x_value"] = 3
    data = s.state.model_dump(mode="json")
    if kind == "legacy_unknown":
        data["rules"].pop("foretell_templates")
    saved = tmp_path / "game.json"
    saved.write_text(json.dumps(data))
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(dict(kind=kind, action=action, source=source.id)))
    code = r"""
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from app.rules import casting,mana_units
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text());c=s.state.cards[spec['action']['card_id']]
if spec['kind']=='legacy_unknown':
 assert not casting.castable(s.state,'p1',c,repo)
 before=s.state.model_dump_json()
 try:act(s,'p1',**spec['action'])
 except ActionError:pass
 else:raise AssertionError('Unknown legacy receipt acquired a guessed current-source cost')
 assert s.state.model_dump_json()==before
else:
 act(s,'p1',**spec['action']);answer(s)
 assert not mana_units.visible_pool(s.state,'p1')
 if spec['kind'].startswith('foretell'):
  assert c.zone=='p1:foretell' and s.state.rules.foretell_templates[c.id].object_id==s.state.rules.object_id(c.id)
  if spec['kind']=='foretell_dream':assert Plan(s.state,'p1',repo,None).ch(s.state.cards[spec['source']]).pt==(2,3)
 else:
  assert c.zone=='p1:battlefield'
  if spec['kind']=='cast_x':assert c.counters.get('+1/+1')==3
  if spec['kind']=='cast_back':assert c.face==1
 roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), str(spec)],
        cwd=Path(dynamic_zone_keyword_costs56.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_opponent_and_spectator_protocol_hide_new_foretell_event_and_receipt_details(cards):
    from app.game.visibility import SPECTATOR

    s = game(cards, ["Dream Devourer", "Shivan Dragon"])
    source = put(s, "Dream Devourer", "battlefield")
    c = put(s, "Shivan Dragon", "hand")
    foretell(s, c)
    protocols = [s.view(viewer) for viewer in ["p2", SPECTATOR]]
    answer(s)
    assert Plan(s.state, "p1", cards, None).ch(source).pt == (2, 3)
    protocols.extend(s.view(viewer) for viewer in ["p2", SPECTATOR])
    assert s.state.rules.foretell_templates[c.id].object_id == s.state.rules.object_id(c.id)
    assert s.view("p1")["cards"][c.id].get("name") == "Shivan Dragon"
    for payload in protocols:
        serialized = json.dumps(payload)
        assert "Shivan Dragon" not in serialized and c.card_id not in serialized
        assert "{4}{R}{R}" not in serialized
        card = payload["cards"].get(c.id, {})
        assert card.get("name") != "Shivan Dragon" and card.get("mana_cost") not in ("{4}{R}{R}",)
    roundtrip(s)
