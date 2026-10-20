"""CR 107.3a, 602.2b, 608.2h: announced X costs and copies of cost-exiled cards."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave31d_spell_copies import hold
from tests.test_rules_wave34b_activated import next_turn, stops
from tests.wave9c_kit import pt


@pytest.fixture()
def cards(settings):
    base = {c["name"]:c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "announced_cost_filters_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="tkc", number=str(i), **{k:v for k,v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("spell,discard,mana,x", [("Lightning Bolt", "Sol Ring", {"R": 1}, 1), ("Ornithopter", "Forest", {}, 0)])
def test_kozilek_announces_x_before_targets_and_discards_a_matching_card(cards, spell, discard, mana, x):
    assert coverage.of_card_data(cards.resolve("Kozilek, the Great Distortion")).level == "FULL"
    s = build(cards, ["Kozilek, the Great Distortion", spell, discard])
    kozilek = put(s, "Kozilek, the Great Distortion", "battlefield")
    payment = put(s, discard, "hand")
    hold(s)
    if mana:
        act(s, "p1", type="add_mana", player="p1", mana=mana)
    target = put(s, spell, "hand")
    act(s, "p1", type="cast_spell", card_id=target.id, **({"targets": ["p2"]} if spell == "Lightning Bolt" else {}))
    ability = next(a for a in Plan(s.state, "p1", cards, None).ch(kozilek).abilities if a.cost and a.cost.startswith("Discard"))
    assert any(a["card_id"] == kozilek.id and a["ability"] == ability.index and a["x"] for a in casting.activatable(s.state, "p1", cards))
    act(s, "p1", type="activate_ability", card_id=kozilek.id, ability=ability.index, x_value=x, targets=[target.id], cost_choices=[{"component": 0, "cards": [payment.id]}])
    assert s.state.cards[payment.id].zone == "p1:graveyard"
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].zone == "p1:graveyard" and s.state.players["p2"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("name,x", [("Sol Ring", 1), ("Ornithopter", 0)])
def test_osgir_exiles_the_matching_artifact_and_copies_its_last_known_characteristics(cards, name, x):
    assert coverage.of_card_data(cards.resolve("Osgir, the Reconstructor")).level == "FULL"
    s = build(cards, ["Osgir, the Reconstructor", name])
    osgir = put(s, "Osgir, the Reconstructor", "battlefield")
    artifact = put(s, name, "graveyard")
    next_turn(s)
    stops(s)
    if x:
        act(s, "p1", type="add_mana", player="p1", mana={"C": x})
    a = next(a for a in Plan(s.state, "p1", cards, None).ch(s.state.cards[osgir.id]).abilities if a.cost and a.cost.startswith("{X}"))
    cost = costs.parse_ability_cost(a.cost, card_name="Osgir, the Reconstructor")
    component = next(i for i,c in enumerate(cost.components) if c.kind == costs.EXILE_FROM_GRAVEYARD)
    act(s, "p1", type="activate_ability", card_id=osgir.id, ability=a.index, x_value=x, cost_choices=[{"component":component, "cards":[artifact.id]}])
    assert s.state.cards[artifact.id].zone == "p1:exile" and s.state.cards[osgir.id].tapped
    roundtrip(s)
    settle(s)
    made = [c for c in s.state.cards.values() if c.is_token and c.name == name]
    assert len(made) == 2
    assert all(Plan(s.state,"p1",cards,None).ch(c).mana_value == x for c in made)
    roundtrip(s)


@pytest.mark.parametrize("missing_x", [True, False])
def test_kozilek_rejects_missing_x_or_wrong_mana_value_without_discarding(cards, missing_x):
    s = build(cards, ["Kozilek, the Great Distortion", "Lightning Bolt", "Sol Ring", "Grizzly Bears"])
    source = put(s, "Kozilek, the Great Distortion", "battlefield")
    ring = put(s, "Sol Ring", "hand")
    bear = put(s, "Grizzly Bears", "hand")
    hold(s)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    target = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="cast_spell", card_id=target.id, targets=["p2"])
    ability = next(a for a in Plan(s.state,"p1",cards,None).ch(source).abilities if a.cost and a.cost.startswith("Discard"))
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, targets=[target.id],
            cost_choices=[{"component":0,"cards":[ring.id if missing_x else bear.id]}], **({} if missing_x else {"x_value":1}))
    assert s.state.cards[ring.id].zone == s.state.cards[bear.id].zone == "p1:hand"
    assert s.state.cards[target.id].zone == "stack"
    roundtrip(s)


def test_selector_x_cannot_be_an_unannounced_optional_payment():
    from app.rules import optional_payment

    assert optional_payment.cost_text("discard a card with mana value X") is None


def test_osgir_copies_last_known_exiled_card_when_it_leaves_exile_in_response(cards):
    s = build(cards, ["Osgir, the Reconstructor", "Sol Ring"])
    osgir = put(s, "Osgir, the Reconstructor", "battlefield")
    artifact = put(s, "Sol Ring", "graveyard")
    next_turn(s)
    stops(s)
    act(s, "p1", type="add_mana", player="p1", mana={"C":1})
    act(s, "p1", type="activate_ability", card_id=osgir.id, ability=2, x_value=1, cost_choices=[{"component":2,"cards":[artifact.id]}])
    act(s, "p1", type="move", card_ids=[artifact.id], to={"player":"p1","zone":"hand"})
    roundtrip(s)
    settle(s)
    made=[c for c in s.state.cards.values() if c.is_token and c.name == "Sol Ring"]
    assert len(made)==2 and all(Plan(s.state,"p1",cards,None).ch(c).mana_cost == "{1}" for c in made)
    roundtrip(s)


def test_osgir_wrong_mana_value_does_not_spend_mana_tap_or_exile(cards):
    s = build(cards, ["Osgir, the Reconstructor", "Sol Ring"])
    osgir = put(s, "Osgir, the Reconstructor", "battlefield")
    artifact = put(s, "Sol Ring", "graveyard")
    next_turn(s)
    act(s, "p1", type="add_mana", player="p1", mana={"C":2})
    with pytest.raises(ActionError):
        act(s,"p1",type="activate_ability",card_id=osgir.id,ability=2,x_value=2,cost_choices=[{"component":2,"cards":[artifact.id]}])
    assert s.state.cards[artifact.id].zone == "p1:graveyard" and not s.state.cards[osgir.id].tapped
    assert s.state.players["p1"].mana.get("C")==2
    roundtrip(s)


def treasure(s):
    before=set(s.state.cards)
    act(s,"p1",type="create_token",player="p1",token={"name":"Treasure","type_line":"Token Artifact — Treasure","text":"{T}, Sacrifice this artifact: Add one mana of any color."})
    return next(c for c in s.state.cards.values() if c.id not in before)


def test_tawnos_combines_sacrifices_and_one_exiled_copy_source(cards):
    assert coverage.of_card_data(cards.resolve("Tawnos, Solemn Survivor")).level == "FULL"
    s = build(cards,["Tawnos, Solemn Survivor","Grizzly Bears"])
    source=put(s,"Tawnos, Solemn Survivor","battlefield")
    artifact=put(s,"Grizzly Bears","graveyard")
    tokens=[treasure(s),treasure(s)]
    next_turn(s)
    stops(s)
    act(s,"p1",type="add_mana",player="p1",mana={"C":1,"W":1,"U":1,"B":1})
    act(s,"p1",type="activate_ability",card_id=source.id,ability=1,cost_choices=[{"component":2,"cards":[c.id for c in tokens]},{"component":3,"cards":[artifact.id]}])
    assert s.state.cards[artifact.id].zone=="p1:exile"
    assert all(c.id not in s.state.cards or s.state.cards[c.id].zone!="p1:battlefield" for c in tokens)
    roundtrip(s)
    settle(s)
    made=[c for c in s.state.cards.values() if c.is_token and c.name=="Grizzly Bears"]
    assert len(made)==1
    ch=Plan(s.state,"p1",cards,None).ch(made[0])
    assert {"Artifact","Creature"} <= ch.types and ch.mana_cost=="{1}{G}" and ch.colors==frozenset({"G"})
    roundtrip(s)


@pytest.mark.parametrize("choose",[True,False])
def test_tawnos_mills_two_even_when_no_copy_target_is_chosen(cards,choose):
    s=build(cards,["Tawnos, Solemn Survivor"])
    source=put(s,"Tawnos, Solemn Survivor","battlefield")
    token=treasure(s)
    next_turn(s)
    before=len(s.state.zones["p1:library"])
    act(s,"p1",type="add_mana",player="p1",mana={"C":2})
    act(s,"p1",type="activate_ability",card_id=source.id,ability=0,targets=[token.id] if choose else [],target_counts=[1 if choose else 0])
    settle(s)
    assert len(s.state.zones["p1:library"])==before-2
    assert len([c for c in s.state.cards.values() if c.is_token and c.name=="Treasure"])==(2 if choose else 1)
    roundtrip(s)


def test_dollhouse_copy_exception_applies_before_state_based_actions_and_haste_expires(cards):
    assert coverage.of_card_data(cards.resolve("Dollhouse of Horrors")).level == "FULL"
    s=build(cards,["Dollhouse of Horrors","Grizzly Bears"])
    source=put(s,"Dollhouse of Horrors","battlefield")
    original=put(s,"Grizzly Bears","graveyard")
    act(s,"p1",type="create_token",player="p1",token={"name":"Existing Construct","type_line":"Token Artifact Creature — Construct","power":"1","toughness":"1"})
    act(s,"p1",type="add_mana",player="p1",mana={"C":1})
    act(s,"p1",type="activate_ability",card_id=source.id,ability=0,cost_choices=[{"component":2,"cards":[original.id]}])
    settle(s)
    made=next(c for c in s.state.cards.values() if c.is_token and c.name=="Grizzly Bears")
    ch=Plan(s.state,"p1",cards,None).ch(made)
    assert {"Artifact","Creature"}<=ch.types and {"Construct","Bear"}<=ch.subtypes
    assert pt(s,"Grizzly Bears")== (2,2) and "haste" in ch.keywords
    act(s,"p1",type="move",card_ids=[source.id],to={"player":"p1","zone":"hand"})
    roundtrip(s)
    next_turn(s)
    ch=Plan(s.state,"p1",cards,None).ch(s.state.cards[made.id])
    assert pt(s,"Grizzly Bears")== (2,2) and "haste" not in ch.keywords
    roundtrip(s)


@pytest.mark.parametrize("discard,x", [("Sol Ring",1),("Forest",0)])
def test_knollspine_uses_the_announced_cost_x_for_damage(cards,discard,x):
    assert coverage.of_card_data(cards.resolve("Knollspine Invocation")).level=="FULL"
    s=build(cards,["Knollspine Invocation",discard])
    source=put(s,"Knollspine Invocation","battlefield")
    payment=put(s,discard,"hand")
    if x:
        act(s,"p1",type="add_mana",player="p1",mana={"C":x})
    act(s,"p1",type="activate_ability",card_id=source.id,ability=0,x_value=x,targets=["p2"],cost_choices=[{"component":1,"cards":[payment.id]}])
    assert s.state.cards[payment.id].zone=="p1:graveyard"
    roundtrip(s)
    settle(s)
    assert s.state.players["p2"].life==40-x
    roundtrip(s)


def test_osgir_sacrifices_an_artifact_to_pump_only_until_end_of_turn(cards):
    s=build(cards,["Osgir, the Reconstructor","Sol Ring","Grizzly Bears"])
    source=put(s,"Osgir, the Reconstructor","battlefield")
    artifact=put(s,"Sol Ring","battlefield")
    bear=put(s,"Grizzly Bears","battlefield")
    act(s,"p1",type="add_mana",player="p1",mana={"C":1})
    act(s,"p1",type="activate_ability",card_id=source.id,ability=1,targets=[bear.id],cost_choices=[{"component":1,"cards":[artifact.id]}])
    assert s.state.cards[artifact.id].zone=="p1:graveyard"
    roundtrip(s)
    settle(s)
    assert pt(s,"Grizzly Bears")== (4,2)
    next_turn(s)
    assert pt(s,"Grizzly Bears")== (2,2)
    roundtrip(s)


def test_kozilek_cast_trigger_draws_to_seven_before_the_creature_resolves(cards):
    s=build(cards,["Kozilek, the Great Distortion"])
    source=put(s,"Kozilek, the Great Distortion","hand")
    act(s,"p1",type="add_mana",player="p1",mana={"C":10})
    act(s,"p1",type="cast_spell",card_id=source.id)
    settle(s)
    assert len(s.state.zones["p1:hand"])==7
    assert s.state.cards[source.id].zone=="p1:battlefield"
    assert "menace" in Plan(s.state,"p1",cards,None).ch(s.state.cards[source.id]).keywords
    roundtrip(s)
