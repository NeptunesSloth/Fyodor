from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting
from app.rules import mana as M
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards():
    repo = CardRepository(
        Path(__file__).resolve().parents[2] / "data/cards.sqlite",
        ImageStore(Path(__file__).resolve().parents[2] / "data/images"),
    )
    yield repo
    repo.close()


def test_actual_creature_output_capture_and_native_restricted_payment(cards):
    s = table(cards, ["Myr Superion", "Llanowar Elves", "Elvish Mystic"], [], [])
    elf = put(s, "Llanowar Elves", "battlefield")
    mystic = put(s, "Elvish Mystic", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for source in (elf, mystic):
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    units = s.state.players["p1"].mana_units
    assert len(units) == 2 and all(
        u.production_zone == "p1:battlefield" and "Creature" in u.tags for u in units
    )
    plan = Plan(s.state, "p1", cards, None)
    paid = casting.find_payment(
        s.state, "p1", M.parse_cost("{2}"), cards, sources=[], purpose=casting.Purpose(spell=plan.ch(spell))
    )
    assert paid.spent == {"G": 2}
    settlement = __import__("app.rules.mana_units", fromlist=["settle"]).settle(plan, "p1", paid)
    assert set(settlement["spend_units"]) == {u.id for u in units}
    roundtrip(s)


def test_actual_unknown_plain_pool_cannot_pay_myr_native_solver(cards):
    s = table(cards, ["Myr Superion"], [], [])
    spell = put(s, "Myr Superion", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 2})
    with pytest.raises(ActionError):
        casting.find_payment(
            s.state,
            "p1",
            M.parse_cost("{2}"),
            cards,
            sources=[],
            purpose=casting.Purpose(spell=Plan(s.state, "p1", cards, None).ch(spell)),
        )


def test_actual_basic_land_independent_creature_bonus_keeps_two_producers(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Imperiosaur", "Keeper of Progenitus"], [], [])
    keeper = put(s, "Keeper of Progenitus", "battlefield")
    forest_ids = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=forest_ids, to={"player": "p1", "zone": "battlefield"})
    myr = put(s, "Myr Superion", "hand")
    dino = put(s, "Imperiosaur", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for cid in forest_ids:
        source = s.state.cards[cid]
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, "p1", type="activate_ability", card_id=cid, ability=index)
        answer(s)
    units = s.state.players["p1"].mana_units
    assert len(units) == 4
    land = [u for u in units if "Land" in u.tags]
    creature = [u for u in units if "Creature" in u.tags]
    assert len(land) == len(creature) == 2
    plan = Plan(s.state, "p1", cards, None)
    assert all(u.src == plan.oid(keeper) for u in creature)
    with pytest.raises(ActionError):
        casting.find_payment(
            s.state,
            "p1",
            M.parse_cost("{2}{G}{G}"),
            cards,
            sources=[],
            purpose=casting.Purpose(spell=plan.ch(dino)),
        )
    paid = casting.find_payment(
        s.state, "p1", M.parse_cost("{2}"), cards, sources=[], purpose=casting.Purpose(spell=plan.ch(myr))
    )
    settlement = __import__("app.rules.mana_units", fromlist=["settle"]).settle(plan, "p1", paid)
    assert set(settlement["spend_units"]) == {u.id for u in creature}
    act(s, "p1", type="cast_spell", card_id=myr.id, sources=[])
    answer(s)
    assert s.state.cards[myr.id].zone == "p1:battlefield"
    assert {u.id for u in s.state.players["p1"].mana_units} == {u.id for u in land}
    roundtrip(s)


def test_actual_same_color_unknown_pool_receipt_does_not_consume_known_creature_unit(cards):
    from app.rules import mana_units
    from app.rules.mana_requirement_rows import ProducerRequirement as P
    from app.rules.mana_requirement_rows import Requirement, RequirementPlan

    s = table(cards, ["Llanowar Elves"], [], [])
    elf = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=index)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    # Same-color unrestricted input + restricted output requirements. This is
    # the exact settlement hazard when unknown plain and known units coexist.
    plan = Plan(s.state, "p1", cards, None)
    cost = M.ManaCost(
        2,
        allocation=RequirementPlan(
            1, (Requirement(M.ALL_MANA, generic=True, producer=P.CREATURE_PERMANENT),)
        ),
    )
    payment = M.solve(cost, {"G": 1}, mana_units.unit_sources(s.state, "p1", None))
    settled = mana_units.settle(plan, "p1", payment)
    assert settled["delta"] == {"G": -1}
    assert settled["spend_units"] == [s.state.players["p1"].mana_units[0].id]


@pytest.mark.parametrize("legacy", [False, True])
def test_true_cold_saved_producer_units_after_sources_left(cards, tmp_path, legacy):
    import subprocess
    import sys

    s = table(cards, ["Myr Superion", "Llanowar Elves", "Elvish Mystic"], [], [])
    sources = [put(s, name, "battlefield") for name in ("Llanowar Elves", "Elvish Mystic")]
    spell = put(s, "Myr Superion", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for source in sources:
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
        act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    data = s.state.model_dump(mode="json")
    if legacy:
        for unit in data["players"]["p1"]["mana_units"]:
            unit.pop("production_zone")
    path = tmp_path / "producer.json"
    path.write_text(__import__("json").dumps(data))
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
path,spell,legacy=sys.argv[1:]
repo=CardRepository(Path.cwd().parent / 'data/cards.sqlite',ImageStore(Path.cwd().parent / 'data/images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
before=s.state.model_dump_json()
if legacy=='True':
 try: s.perform('p1',{'type':'cast_spell','card_id':spell,'sources':[]})
 except ActionError: pass
 else: raise AssertionError('Unknown legacy production zone must not establish creature mana')
 assert s.state.model_dump_json()==before
else:
 s.perform('p1',{'type':'cast_spell','card_id':spell,'sources':[]})
 assert s.state.cards[spell].zone=='stack'
 assert not s.state.players['p1'].mana_units
 assert s.state.rules.payments[s.state.rules.object_id(spell)].mana_spent=={'G':2}
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    done = subprocess.run(
        [sys.executable, "-c", code, str(path), spell.id, str(legacy)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=90,
    )
    assert done.returncode == 0, done.stderr


def test_actual_creature_filter_input_uses_basic_mana_then_myr_uses_output(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Prismite"], [], [])
    prism = put(s, "Prismite", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    forest_ids = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:4]
    act(s, "p1", type="move", card_ids=forest_ids, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for cid in forest_ids:
        index = next(i for i, _ in casting.mana_abilities(s.state, s.state.cards[cid], cards))
        act(s, "p1", type="activate_ability", card_id=cid, ability=index)
    index = next(i for i, _ in casting.mana_abilities(s.state, prism, cards))
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=prism.id, ability=index)
        answer(s)
    assert len(s.state.players["p1"].mana_units) == 2
    assert all("Creature" in u.tags and "Land" not in u.tags for u in s.state.players["p1"].mana_units)
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"


def test_actual_doubling_cube_new_mana_is_cube_artifact_not_original_creature_or_basic(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(
        cards,
        ["Doubling Cube", "Myr Superion", "Imperiosaur", "Grizzly Bears", "Llanowar Elves", "Elvish Mystic"],
        [],
        [],
    )
    cube = put(s, "Doubling Cube", "battlefield")
    elves = [put(s, n, "battlefield") for n in ("Llanowar Elves", "Elvish Mystic")]
    forests = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    myr = put(s, "Myr Superion", "hand")
    dino = put(s, "Imperiosaur", "hand")
    bears = put(s, "Grizzly Bears", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for source in [*elves, *(s.state.cards[cid] for cid in forests)]:
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(cube).abilities if "Double" in a.text)
    act(s, "p1", type="activate_ability", card_id=cube.id, ability=index)
    answer(s)
    oid = Plan(s.state, "p1", cards, None).oid(cube)
    generated = [u for u in s.state.players["p1"].mana_units if u.src == oid]
    assert len(generated) == 4 and all(
        "Artifact" in u.tags and "Creature" not in u.tags and "Land" not in u.tags for u in generated
    )
    act(s, "p1", type="cast_spell", card_id=myr.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=bears.id, sources=[])
    answer(s)
    assert len(s.state.players["p1"].mana_units) == 4
    assert all(u.src == oid for u in s.state.players["p1"].mana_units)
    act(s, "p1", type="move", card_ids=[myr.id], to={"player": "p1", "zone": "hand"})
    for spell in (myr, dino):
        wait_priority(s, "p1")
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
        assert s.state.model_dump(mode="json") == before


def test_actual_auto_two_forests_animated_mana_flare_pays_myr_with_bonus_only(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Mana Flare", "Opalescence"], [], [])
    keeper = put(s, "Mana Flare", "battlefield")
    put(s, "Opalescence", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    forests = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=forests)
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    units = s.state.players["p1"].mana_units
    assert len(units) == 2 and all("Basic" in u.tags and "Creature" not in u.tags for u in units)
    payment = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert payment.mana_sources == [Plan(s.state, "p1", cards, None).oid(keeper)] * 2
    roundtrip(s)


@pytest.mark.parametrize("name", ["Myr Superion", "Imperiosaur"])
def test_hidden_library_restriction_does_not_change_tracking_or_public_history(cards, name):
    import json

    from app.game.views import SPECTATOR, build_view

    s = table(cards, [name, "Llanowar Elves"], [], [])
    spell = put(s, name, "library")
    elf = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    # Keep the card hidden even after the intervening turn's draw.
    act(s, "p1", type="move", card_ids=[spell.id], to={"player": "p1", "zone": "library"})
    index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=index)
    units = s.state.players["p1"].mana_units
    assert len(units) == 1 and units[0].production_zone == "p1:battlefield"
    assert "Creature" in units[0].tags and units[0].src == Plan(s.state, "p1", cards, None).oid(elf)
    for who in ("p2", SPECTATOR):
        view = build_view(s.state, who)
        text = json.dumps(view)
        assert name not in text and "production_zone" not in text
        player = next(p for p in view["players"] if p["id"] == "p1")
        assert player["mana"].get("G") == 1 and player["mana_units"] == []
    roundtrip(s)


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_native_paid_choice_same_nominal_output_keeps_exact_option_index(cards, tmp_path, legacy):
    import subprocess
    import sys

    from app.game.rules_state import DecisionOption
    from app.rules import payment_continuations as pc
    from app.rules.mana_requirement_rows import OutputProducer, ProducerFact
    from app.rules.plan import decide

    s = table(cards, ["Llanowar Elves", "Elvish Mystic"], [], [])
    elf = put(s, "Llanowar Elves", "battlefield")
    mystic = put(s, "Elvish Mystic", "battlefield")
    forest = put(s, "Forest", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    plan = Plan(s.state, "p1", cards, None)
    elf_oid, mystic_oid, forest_oid = (plan.oid(c) for c in (elf, mystic, forest))
    creature = ProducerFact(("Creature", "Elf", "Druid"), "p1:battlefield")
    ability = M.ManaAbility(
        tap=False,
        sacrifice_self=False,
        options=(("G", "G"), ("G", "G")),
        output_producers=(
            (None, OutputProducer(elf_oid, creature)),
            (None, OutputProducer(mystic_oid, creature)),
        ),
    )
    snapshot = pc.ability_data(ability)
    if legacy:
        snapshot.pop("output_producers")
    decide(
        plan,
        player="p1",
        kind="choose_one",
        prompt="Choose the original producer option",
        options=[DecisionOption(id=str(i), label="GG") for i in range(2)],
        resume={
            "step": "mana_ability",
            "paid": True,
            "card": forest.id,
            "ability": 0,
            "who": "p1",
            "oid": forest_oid,
            "options": [["G", "G"], ["G", "G"]],
            "ability_snapshot": snapshot,
            "mana_context": {"source_card": forest.id, "source_object": forest_oid},
        },
    )
    path = tmp_path / "duplicate-output.json"
    path.write_text(plan.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,forest,elf,mystic,legacy=sys.argv[1:]
repo=CardRepository(Path.cwd().parent / 'data/cards.sqlite',ImageStore(Path.cwd().parent / 'data/images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
if legacy=='True':
 from app.game.errors import ActionError
 before=s.state.model_dump_json()
 try: s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['1']})
 except ActionError as error: assert 'unknown producer' in str(error)
 else: raise AssertionError('Missing producer history must refuse before attribution')
 assert s.state.model_dump_json()==before
 assert not s.state.players['p1'].mana_units
 raise SystemExit(0)
s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['1']})
units=s.state.players['p1'].mana_units
assert len(units)==2
assert [u.src for u in units]==[forest,mystic]
assert all(u.src!=elf for u in units)
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), forest_oid, elf_oid, mystic_oid, str(legacy)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=90,
    )
    assert result.returncode == 0, result.stderr


def test_actual_spirit_guide_creature_card_mana_is_not_battlefield_creature_mana(cards):
    s = table(cards, ["Myr Superion", "Elvish Spirit Guide", "Simian Spirit Guide"], [], [])
    spell = put(s, "Myr Superion", "hand")
    guides = [put(s, n, "hand") for n in ("Elvish Spirit Guide", "Simian Spirit Guide")]
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for guide in guides:
        index = next(
            a.index for a in Plan(s.state, "p1", cards, None).ch(guide).abilities if "Exile" in a.text
        )
        act(s, "p1", type="activate_ability", card_id=guide.id, ability=index)
    units = s.state.players["p1"].mana_units
    assert len(units) == 2 and all(u.production_zone == "p1:hand" and "Creature" in u.tags for u in units)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    assert s.state.model_dump(mode="json") == before


def test_native_complex_sacrifice_cost_removes_bonus_source_before_production(cards, tmp_path):
    """Synthetic cost boundary, canonical Mana Flare/Opalescence effects."""
    from app.cards.importer import build_database
    from tests.fixtures.cards import card, fixture_cards
    from tests.test_rules_activated_copy_family import answer

    rows = {c["name"]: c for c in fixture_cards()}
    for i, name in enumerate(("Mana Flare", "Opalescence")):
        raw = cards.resolve(name)
        rows[name] = card(
            name,
            set_code="pcost45",
            number=str(i),
            **{
                k: raw[k]
                for k in (
                    "mana_cost",
                    "cmc",
                    "type_line",
                    "oracle_text",
                    "colors",
                    "color_identity",
                    "power",
                    "toughness",
                    "keywords",
                )
                if k in raw
            },
        )
    name = "Producer Boundary Land"
    rows[name] = card(
        name,
        set_code="pcost45",
        number="2",
        type_line="Land",
        oracle_text="{T}, Sacrifice a creature: Add {G}.",
    )
    database = tmp_path / "cost.sqlite"
    build_database(rows.values(), database)
    repo = CardRepository(database, ImageStore(tmp_path / "images"))
    try:
        s = table(repo, [name, "Mana Flare", "Opalescence"], [], [])
        source = put(s, name, "battlefield")
        flare = put(s, "Mana Flare", "battlefield")
        put(s, "Opalescence", "battlefield")
        to_phase(s, "main1", 4)
        wait_priority(s, "p1")
        assert "Creature" in Plan(s.state, "p1", repo, None).ch(flare).types
        parsed = dict(casting.mana_abilities(s.state, source, repo))[0]
        assert parsed.native_body
        act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
        d = s.state.rules.decision
        if d is not None:
            assert any(o.id == flare.id for o in d.options)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[flare.id])
        answer(s)
        assert s.state.cards[flare.id].zone == "p1:graveyard"
        units = s.state.players["p1"].mana_units
        assert len(units) == 1 and units[0].sym == "G" and "Land" in units[0].tags
        assert units[0].src == Plan(s.state, "p1", repo, None).oid(source)
        roundtrip(s)
    finally:
        repo.close()


def test_actual_nyxbloom_replacement_preserves_original_basic_or_creature_producer(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Imperiosaur", "Nyxbloom Ancient", "Elvish Mystic"], [], [])
    put(s, "Nyxbloom Ancient", "battlefield")
    elf = put(s, "Elvish Mystic", "battlefield")
    forests = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    myr = put(s, "Myr Superion", "hand")
    dino = put(s, "Imperiosaur", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for at, cid in enumerate(forests):
        index = next(i for i, _ in casting.mana_abilities(s.state, s.state.cards[cid], cards))
        act(s, "p1", type="activate_ability", card_id=cid, ability=index)
        assert len(s.state.players["p1"].mana_units) == 3 * (at + 1)
        assert all("Basic" in u.tags and "Creature" not in u.tags for u in s.state.players["p1"].mana_units)
        if at == 0:
            before = s.state.model_dump(mode="json")
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=myr.id, sources=[])
            assert s.state.model_dump(mode="json") == before
    act(s, "p1", type="cast_spell", card_id=dino.id, sources=[])
    answer(s)
    wait_priority(s, "p1")
    assert len(s.state.players["p1"].mana_units) == 2
    index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=index)
    act(s, "p1", type="cast_spell", card_id=myr.id, sources=[])
    answer(s)
    units = s.state.players["p1"].mana_units
    assert len(units) == 3
    assert sum("Basic" in u.tags for u in units) == 2
    assert sum(u.src == Plan(s.state, "p1", cards, None).oid(elf) for u in units) == 1
    roundtrip(s)


def test_actual_producer_types_freeze_before_animation_and_survive_loss_departure_control(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Living Plane"], [], [])
    spell = put(s, "Myr Superion", "hand")
    forests = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:3]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")

    def produce(cid):
        index = next(i for i, _ in casting.mana_abilities(s.state, s.state.cards[cid], cards))
        act(s, "p1", type="activate_ability", card_id=cid, ability=index)

    produce(forests[0])
    old = s.state.players["p1"].mana_units[0].id
    assert "Creature" not in s.state.players["p1"].mana_units[0].tags
    plane = put(s, "Living Plane", "battlefield")
    produce(forests[1])
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    assert s.state.model_dump(mode="json") == before
    produce(forests[2])
    act(s, "p1", type="move", card_ids=[plane.id, forests[1]], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_controller", card_ids=[forests[2]], player="p2")
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    assert [u.id for u in s.state.players["p1"].mana_units] == [old]
    assert "Creature" not in s.state.players["p1"].mana_units[0].tags
    roundtrip(s)


def test_actual_myr_tax_requires_creature_mana_and_departed_priest_trigger_qualifies(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(
        cards,
        ["Myr Superion", "Sphere of Resistance", "Priest of Urabrask", "Llanowar Elves", "Elvish Mystic"],
        [],
        [],
    )
    put(s, "Sphere of Resistance", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    elves = [put(s, n, "battlefield") for n in ("Llanowar Elves", "Elvish Mystic")]
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for elf in elves:
        index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
        act(s, "p1", type="activate_ability", card_id=elf.id, ability=index)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    assert s.state.model_dump(mode="json") == before
    from tests.test_rules_copy import resolve_top

    act(s, "p1", type="set_prefs", hold_priority=True)
    priest = put(s, "Priest of Urabrask", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "R": 1})
    act(s, "p1", type="cast_spell", card_id=priest.id, sources=[])
    resolve_top(s)
    oid = Plan(s.state, "p1", cards, None).oid(s.state.cards[priest.id])
    assert s.state.zone("stack")
    act(s, "p1", type="move", card_ids=[priest.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    wait_priority(s, "p1")
    red = [u for u in s.state.players["p1"].mana_units if u.src == oid]
    assert len(red) == 3 and all("Creature" in u.tags and u.production_zone == "p1:battlefield" for u in red)
    act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
    answer(s)
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert sum(record.mana_spent.values()) == 3
    assert s.state.players["p1"].mana.get("C") == 1
    roundtrip(s)


@pytest.mark.parametrize("name", ["Myr Superion", "Imperiosaur"])
def test_actual_zero_mana_free_cast_does_not_require_any_producer(cards, name):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, [name, "Omniscience"], [], [])
    put(s, "Omniscience", "battlefield")
    spell = put(s, name, "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    act(s, "p1", type="cast_spell", card_id=spell.id, free=True, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    assert s.state.players["p1"].mana.get("C") == 3
    assert not s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent
    roundtrip(s)


def test_actual_myr_convoke_helpers_are_nonmana_even_from_artifact_creatures(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Chief Engineer", "Ornithopter", "Memnite"], [], [])
    put(s, "Chief Engineer", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    artifacts = [put(s, n, "battlefield") for n in ("Ornithopter", "Memnite")]
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    assert casting.castable(s.state, "p1", spell, cards)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        sources=[],
        contributions=[{"kind": "convoke", "card": a.id} for a in artifacts],
    )
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    assert all(s.state.cards[a.id].tapped for a in artifacts)
    assert not s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent
    roundtrip(s)


def test_actual_imperiosaur_convoke_colored_helpers_do_not_become_creature_mana(cards):
    from tests.test_rules_activated_copy_family import answer

    names = ["Llanowar Elves", "Elvish Mystic", "Fyndhorn Elves", "Boreal Druid"]
    s = table(cards, ["Imperiosaur", "Wand of the Worldsoul", *names], [], [])
    wand = put(s, "Wand of the Worldsoul", "battlefield")
    spell = put(s, "Imperiosaur", "hand")
    helpers = [put(s, n, "battlefield") for n in names]
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan(s.state, "p1", cards, None).ch(wand).abilities if "next spell" in a.text
    )
    act(s, "p1", type="activate_ability", card_id=wand.id, ability=index)
    answer(s)
    wait_priority(s, "p1")
    assert casting.castable(s.state, "p1", spell, cards)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        sources=[],
        contributions=[{"kind": "convoke", "card": a.id} for a in helpers],
    )
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    assert not s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent
    roundtrip(s)


@pytest.mark.parametrize(("aura_name", "allowed"), [("Gift of Paradise", True), ("Wild Growth", False)])
def test_actual_basic_land_granted_mana_vs_independent_aura_mana(cards, aura_name, allowed):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Imperiosaur", aura_name, "Voyaging Satyr"], [], [])
    forest = put(s, "Forest", "battlefield")
    satyr = put(s, "Voyaging Satyr", "battlefield")
    aura = put(s, aura_name, "hand")
    spell = put(s, "Imperiosaur", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "G": 1} if allowed else {"G": 1})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[forest.id], sources=[])
    answer(s)
    wait_priority(s, "p1")
    act(s, "p1", type="set_controller", card_ids=[aura.id], player="p2")

    def produce():
        index = next(
            i
            for i, ab in casting.mana_abilities(s.state, s.state.cards[forest.id], cards)
            if max(map(len, ab.options)) == 2
        )
        act(s, "p1", type="activate_ability", card_id=forest.id, ability=index, mana_choice="G")

    produce()
    index = next(a.index for a in Plan(s.state, "p1", cards, None).ch(satyr).abilities if "Untap" in a.text)
    act(s, "p1", type="activate_ability", card_id=satyr.id, ability=index, targets=[forest.id])
    answer(s)
    wait_priority(s, "p1")
    produce()
    units = s.state.players["p1"].mana_units
    assert len(units) == 4
    assert sum("Basic" in u.tags for u in units) == (4 if allowed else 2)
    if allowed:
        assert all(u.src == Plan(s.state, "p1", cards, None).oid(forest) for u in units)
        act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
        answer(s)
        assert s.state.cards[spell.id].zone == "p1:battlefield"
    else:
        assert sum(u.src == Plan(s.state, "p1", cards, None).oid(aura) for u in units) == 2
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, sources=[])
        assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_true_cold_nested_filter_input_purpose_is_separate_from_restricted_spell(cards, tmp_path):
    import subprocess
    import sys

    s = table(cards, ["Myr Superion", "Prismite"], [], [])
    prism = put(s, "Prismite", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    forests = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:4]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="set_prefs", payment="self")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    for cid in forests:
        index = next(i for i, _ in casting.mana_abilities(s.state, s.state.cards[cid], cards))
        act(s, "p1", type="activate_ability", card_id=cid, ability=index)
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    index = next(i for i, _ in casting.mana_abilities(s.state, prism, cards))
    act(s, "p1", type="activate_ability", card_id=prism.id, ability=index, mana_choice="W")
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    assert len(s.state.players["p1"].mana_units) == 3
    path = tmp_path / "nested-producer.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting
path,prism,spell=sys.argv[1:]
repo=CardRepository(Path.cwd().parent / 'data/cards.sqlite',ImageStore(Path.cwd().parent / 'data/images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
assert s.state.rules.decision.resume['step']=='pay_mana'
index=next(i for i,_ in casting.mana_abilities(s.state,s.state.cards[prism],repo))
s.perform('p1',{'type':'activate_ability','card_id':prism,'ability':index,'mana_choice':'W'})
units=s.state.players['p1'].mana_units
if s.state.cards[spell].zone!='stack':
 assert len(units)==2 and all('Creature' in u.tags and 'Land' not in u.tags for u in units)
d=s.state.rules.decision
if d is not None:
 assert d.resume['step']=='pay_mana'
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
assert s.state.cards[spell].zone=='stack'
assert not s.state.players['p1'].mana_units
record=s.state.rules.payments[s.state.rules.object_id(spell)]
assert record.mana_spent=={'W':2}
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    done = subprocess.run(
        [sys.executable, "-c", code, str(path), prism.id, spell.id],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=90,
    )
    assert done.returncode == 0, done.stderr


def test_actual_auto_filter_uses_unknown_input_for_creature_produced_final_mana(cards):
    from tests.test_rules_activated_copy_family import answer

    s = table(cards, ["Myr Superion", "Crystal Quarry", "Living Plane"], [], [])
    quarry = put(s, "Crystal Quarry", "battlefield")
    put(s, "Living Plane", "battlefield")
    spell = put(s, "Myr Superion", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5})
    assert casting.castable(s.state, "p1", spell, cards)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield"
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert sum(record.mana_spent.values()) == 2 and "C" not in record.mana_spent
    assert s.state.players["p1"].mana.get("C", 0) == 0
    units = s.state.players["p1"].mana_units
    assert len(units) == 3 and all(
        u.src == Plan(s.state, "p1", cards, None).oid(quarry) and "Creature" in u.tags for u in units
    )
    roundtrip(s)
