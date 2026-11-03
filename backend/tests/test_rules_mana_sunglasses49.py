from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting
from app.rules import mana as M
from app.rules.mana_allocation_masks import MaskedSource
from app.rules.mana_allocation_masks import solve as allocated
from app.rules.mana_requirement_rows import ProducerFact
from app.rules.mana_requirement_rows import ProducerRequirement as PR
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards():
    if not (Path(__file__).resolve().parents[2] / "data/cards.sqlite").is_file():
        pytest.skip("the real card database is needed (data/cards.sqlite)")
    r = CardRepository(
        Path(__file__).resolve().parents[2] / "data/cards.sqlite",
        ImageStore(Path(__file__).resolve().parents[2] / "data/images"),
    )
    yield r
    r.close()


def cost(text):
    return M.spend_as(M.parse_cost(text), "white_red")


@pytest.mark.parametrize(
    "text,white,life,expected",
    [
        ("{R}", 1, 0, True),
        ("{R}{R}", 1, 0, False),
        ("{U}", 1, 0, False),
        ("{B}", 1, 0, False),
        ("{G}", 1, 0, False),
        ("{C}", 1, 0, False),
        ("{S}", 1, 0, False),
        ("{R/G}", 1, 0, True),
        ("{2/R}", 1, 0, True),
        ("{R/P}", 1, 0, True),
        ("{R/P}", 0, 2, True),
    ],
)
def test_only_actual_white_gains_red_matching(text, white, life, expected):
    try:
        p = M.solve(cost(text), {"W": white}, [], life=life)
    except M.ManaError:
        assert not expected
    else:
        assert expected
        assert "R" not in p.spent


@pytest.mark.parametrize("iterative", [False, True])
def test_original_generic_producer_and_helper_limits_survive(iterative):
    from app.rules.mana_allocation_masks import constrain_producer

    c = constrain_producer(cost("{R}"), PR.BASIC_LAND)
    native = M.Source(
        "land",
        (("W",),),
        generic_allowed=(False,),
        producer_facts=((ProducerFact(("Basic", "Land"), "p1:battlefield"),),),
    )
    p = allocated(c, {}, [MaskedSource(native, native.generic_allowed)], iterative=iterative).payment
    assert p.spent == {"W": 1}
    helper = M.Source("white-helper", (("W",), ("1",)), abilities=(-1, -1))
    with pytest.raises(M.ManaError):
        M.solve(cost("{R}"), {}, [helper])
    red = M.Source("red-helper", (("R",), ("1",)), abilities=(-1, -1))
    assert M.solve(cost("{R}"), {}, [red]).spent == {"R": 1}
    blue = M.Source("blue", (("U", "U"),), generic_allowed=(False,))
    with pytest.raises(M.ManaError):
        allocated(cost("{2/R}"), {}, [MaskedSource(blue, blue.generic_allowed)], iterative=iterative)


def test_permissions_compose_without_reverse_or_invented_chain():
    c = M.spend_as(cost("{B}"), "colorless_color")
    with pytest.raises(M.ManaError):
        M.solve(c, {"W": 1}, [])
    assert M.solve(c, {"C": 1}, []).spent == {"C": 1}
    assert M.solve(M.spend_as(cost("{R}"), "color"), {"B": 1}, []).spent == {"B": 1}
    with pytest.raises(M.ManaError):
        M.solve(M.spend_as(cost("{C}"), "color"), {"W": 1}, [])
    assert M.solve(M.spend_as(cost("{C}"), "type"), {"W": 1}, []).spent == {"W": 1}


def setup(cards, names=(), spell="Lightning Bolt"):
    s = table(cards, ["Sunglasses of Urza", spell, *names], [], [])
    glasses = put(s, "Sunglasses of Urza", "battlefield")
    card = put(s, spell, "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    return s, glasses, card


def test_real_spell_spends_actual_white_and_remembers_original_producer(cards):
    s, g, bolt = setup(cards, ["Plains"])
    land = put(s, "Plains", "battlefield")
    index = next(i for i, ab in casting.mana_abilities(s.state, land, cards))
    act(s, "p1", type="activate_ability", card_id=land.id, ability=index)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(bolt.id)]
    assert record.mana_spent == {"W": 1}
    assert record.mana_sources == [s.state.rules.object_id(land.id)]
    answer(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("change", ["opponent", "gone", "phased", "loss"])
def test_current_permission_does_not_survive_controller_departure_phase_or_loss(cards, change):
    names = ["March of the Machines", "Humility"] if change == "loss" else []
    s, g, bolt = setup(cards, names)
    if change == "opponent":
        act(s, "p1", type="set_controller", card_ids=[g.id], player="p2")
    elif change == "gone":
        act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "graveyard"})
    elif change == "phased":
        act(s, "p1", type="phase_shift", card_ids=[g.id], out=True)
    else:
        put(s, "March of the Machines", "battlefield")
        put(s, "Humility", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    assert s.state.model_dump_json() == before


def test_actual_activated_red_cost_and_suspend_red_special_action(cards):
    s, g, bolt = setup(cards, ["Shivan Dragon", "Rift Bolt"])
    dragon = put(s, "Shivan Dragon", "battlefield")
    rift = put(s, "Rift Bolt", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=dragon.id,
        ability=next(a.index for a in casting.chars.of(dragon, cards).abilities if a.cost == "{R}"),
    )
    answer(s)
    wait_priority(s, "p1")
    assert s.state.players["p1"].mana == {"W": 1}
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=rift.id,
        ability=next(a.index for a in casting.chars.of(rift, cards).abilities if "suspend" in a.keywords),
    )
    assert s.state.cards[rift.id].zone == "p1:exile"
    assert s.state.cards[rift.id].counters.get("time") == 1


def test_self_actual_ironworks_cost_removes_last_permission_before_final_payment(cards):
    s, g, spell = setup(cards, ["Krark-Clan Ironworks", "Mountain"], spell="Rift Bolt")
    kci = put(s, "Krark-Clan Ironworks", "battlefield")
    mountain = put(s, "Mountain", "battlefield")
    act(s, "p1", type="set_prefs", payment="self")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    act(s, "p1", type="activate_ability", card_id=kci.id, ability=0)
    d = s.state.rules.decision
    assert g.id in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[g.id])
    assert s.state.cards[g.id].zone == "p1:graveyard"
    d = s.state.rules.decision
    assert d.resume["step"] == "pay_mana"
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.model_dump_json() == before
    index = next(i for i, ab in casting.mana_abilities(s.state, mountain, cards))
    act(s, "p1", type="activate_ability", card_id=mountain.id, ability=index)
    if s.state.cards[spell.id].zone == "p1:hand":
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[spell.id].zone == "stack"
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.mana_spent.get("R") == 1 and sum(record.mana_spent.values()) == 3


def cost_boundary_repo(cards, tmp_path, output="{C}{C}", life=False):
    from app.cards.importer import build_database
    from tests.fixtures.cards import card, fixture_cards

    rows = {c["name"]: c for c in fixture_cards()}
    for i, n in enumerate(
        ["Rift Bolt", "Night's Whisper", "Sign in Blood", "Graven Cairns", "Furnace of Rath", "Urza's Armor"]
    ):
        raw = cards.resolve(n)
        values = {
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
        }
        rows[n] = card(n, set_code="scost49", number=str(i), **values)
    name = "Spending Permission Source Cost Boundary " + output + (" Damage" if life else "")
    rows[name] = card(
        name,
        set_code="scost49",
        number="9",
        mana_cost="{3}",
        cmc=3,
        type_line="Artifact",
        oracle_text="You may spend white mana as though it were red mana.\n{T}, Sacrifice this artifact: Add "
        + output
        + "."
        + (" This artifact deals 1 damage to you." if life else ""),
    )
    db = tmp_path / "source.sqlite"
    build_database(rows.values(), db)
    return CardRepository(db, ImageStore(tmp_path / "images")), name


@pytest.mark.parametrize("mountain", [False, True])
def test_auto_source_cost_cannot_freeze_permission_into_planned_payment(cards, tmp_path, mountain):
    repo, name = cost_boundary_repo(cards, tmp_path)
    try:
        s = table(repo, [name, "Rift Bolt", "Mountain"], [], [])
        source = put(s, name, "battlefield")
        spell = put(s, "Rift Bolt", "hand")
        land = put(s, "Mountain", "battlefield") if mountain else None
        to_phase(s, "main1", 4)
        wait_priority(s, "p1")
        act(
            s,
            "p1",
            type="set_prefs",
            mana_source=source.id,
            mana_source_protection="prefer",
            hold_priority=True,
        )
        if land:
            act(s, "p1", type="set_prefs", mana_source=land.id, mana_source_protection="save")
        act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
        before = s.state.model_dump_json()
        if not mountain:
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
            assert s.state.model_dump_json() == before
        else:
            act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
            assert s.state.cards[source.id].zone == "p1:graveyard"
            record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
            assert record.mana_spent.get("R") == 1 and sum(record.mana_spent.values()) == 3
            assert s.state.cards[land.id].tapped
    finally:
        repo.close()


@pytest.mark.parametrize("swamp", [False, True])
def test_auto_nested_filter_rechecks_original_input_and_allows_only_auto_replanning(cards, tmp_path, swamp):
    repo, name = cost_boundary_repo(cards, tmp_path, output="{W}")
    try:
        s = table(repo, [name, "Sign in Blood", "Graven Cairns", "Swamp"], [], [])
        source = put(s, name, "battlefield")
        spell = put(s, "Sign in Blood", "hand")
        filterland = put(s, "Graven Cairns", "battlefield")
        backup = put(s, "Swamp", "battlefield") if swamp else None
        to_phase(s, "main1", 4)
        wait_priority(s, "p1")
        act(
            s,
            "p1",
            type="set_prefs",
            mana_source=source.id,
            mana_source_protection="prefer",
            hold_priority=True,
        )
        if backup:
            act(s, "p1", type="set_prefs", mana_source=backup.id, mana_source_protection="save")
        before = s.state.model_dump_json()
        if backup is None:
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
            assert s.state.model_dump_json() == before
        else:
            oid = s.state.rules.object_id(source.id)
            act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
            assert s.state.cards[source.id].zone == "p1:graveyard"
            assert s.state.cards[backup.id].tapped
            record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
            assert record.mana_spent == {"B": 2}
            assert record.mana_sources == [s.state.rules.object_id(filterland.id)] * 2
            assert [(u.sym, u.src) for u in s.state.players["p1"].mana_units] == [("W", oid)]
    finally:
        repo.close()


def test_actual_upkeep_red_payment_uses_white_mana(cards):
    s, g, _ = setup(cards, ["Dragon Tyrant", *(["Plains"] * 4)])
    dragon = put(s, "Dragon Tyrant", "battlefield")
    ids = [c.id for c in s.state.cards.values() if c.name == "Plains" and c.owner == "p1"][:4]
    assert len(ids) == 4
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "battlefield"})
    lands = [s.state.cards[cid] for cid in ids]
    act(s, "p1", type="set_prefs", payment="self", hold_priority=True, auto_resolve_own_triggers="off")
    to_phase(s, "upkeep", 7)
    wait_priority(s, "p1")
    assert s.state.rules.decision is None
    for land in lands:
        index = next(i for i, ab in casting.mana_abilities(s.state, land, cards))
        act(s, "p1", type="activate_ability", card_id=land.id, ability=index)
    answer(s)
    assert s.state.cards[dragon.id].zone == "p1:battlefield"
    assert not s.state.players["p1"].mana_units


def test_actual_rhox_alternative_can_spend_treasure_white_as_red_without_retagging(cards):
    from app.rules import alt_costs
    from tests.test_rules_mana_security_rhox47 import produce, token

    s, g, r = setup(cards, spell="Security Rhox")
    for color in ["W", "G"]:
        t = token(s)
        produce(s, t, color)
    act(s, "p1", type="set_prefs", hold_priority=True)
    p = Plan(s.state, "p1", cards, None)
    selected = next(o for o in alt_costs.offers(s.state, "p1", r, p.ch(r), cards) if o.producer_requirement)
    act(s, "p1", type="cast_spell", card_id=r.id, alt_cost=selected.key, sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(r.id)]
    assert record.mana_spent == {"W": 1, "G": 1}
    assert all("Treasure" in tags for tags in record.mana_tags)


def test_true_cold_nested_auto_filter_after_last_permission_source_is_sacrificed(cards, tmp_path):
    import subprocess
    import sys

    repo, name = cost_boundary_repo(cards, tmp_path, output="{W}", life=True)
    try:
        s = table(
            repo, [name, "Sign in Blood", "Graven Cairns", "Swamp", "Furnace of Rath", "Urza's Armor"], [], []
        )
        source = put(s, name, "battlefield")
        spell = put(s, "Sign in Blood", "hand")
        filterland = put(s, "Graven Cairns", "battlefield")
        backup = put(s, "Swamp", "battlefield")
        put(s, "Furnace of Rath", "battlefield")
        put(s, "Urza's Armor", "battlefield")
        to_phase(s, "main1", 4)
        wait_priority(s, "p1")
        act(
            s,
            "p1",
            type="set_prefs",
            mana_source=source.id,
            mana_source_protection="prefer",
            hold_priority=True,
        )
        act(s, "p1", type="set_prefs", mana_source=backup.id, mana_source_protection="save")
        oid = s.state.rules.object_id(source.id)
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
        assert s.state.cards[source.id].zone == "p1:graveyard"
        d = s.state.rules.decision
        assert d is not None
        assert "616.1" in d.prompt, (d.prompt, d.resume)
        saved = tmp_path / "sunglasses-filter.json"
        saved.write_text(s.state.model_dump_json())
        code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import mana_sunglasses49
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[1]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[2]).read_text()),cards=repo)
assert not mana_sunglasses49.present(s.state,'p1',repo)
s.view('p3')
for _ in range(10):
 d=s.state.rules.decision
 if d is None:break
 assert '616.1' in d.prompt,d.prompt
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':[d.options[0].id]})
else:raise AssertionError('Damage replacement ordering did not finish')
spell,filterland,backup,oldsource=sys.argv[3:]
assert s.state.cards[spell].zone=='stack'
assert s.state.cards[backup].tapped
record=s.state.rules.payments[s.state.rules.object_id(spell)]
assert record.mana_spent=={'B':2},record.mana_spent
assert record.mana_sources==[s.state.rules.object_id(filterland)]*2
assert [(u.sym,u.src) for u in s.state.players['p1'].mana_units]==[('W',oldsource)]
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(tmp_path / "source.sqlite"),
                str(saved),
                spell.id,
                filterland.id,
                backup.id,
                oid,
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stderr
    finally:
        repo.close()


@pytest.mark.parametrize("gone", [False, True])
def test_true_cold_pending_payment_rechecks_live_permission_and_keeps_original_cost(cards, tmp_path, gone):
    import subprocess
    import sys

    s, g, spell = setup(cards, ["Plains", "Sol Ring", "Mountain"], spell="Rift Bolt")
    plains = put(s, "Plains", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    mountain = put(s, "Mountain", "battlefield")
    act(s, "p1", type="set_prefs", payment="self")
    index = next(i for i, ab in casting.mana_abilities(s.state, plains, cards))
    act(s, "p1", type="activate_ability", card_id=plains.id, ability=index)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    assert s.state.rules.decision.resume["cost"] == "{2}{R}"
    if gone:
        act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "graveyard"})
    path = tmp_path / "sunglasses-pending.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from collections import Counter
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from app.rules import casting,mana_sunglasses49
repo=CardRepository(Path.cwd().parent/'data/cards.sqlite',ImageStore(Path.cwd().parent/'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spell,ring,mountain,plains=sys.argv[2:6];gone=sys.argv[6]=='True'
assert mana_sunglasses49.present(s.state,'p1',repo) is not gone
s.view('p3')
assert s.state.rules.decision.resume['cost']=='{2}{R}'
index=next(i for i,ab in casting.mana_abilities(s.state,s.state.cards[ring],repo))
s.perform('p1',{'type':'activate_ability','card_id':ring,'ability':index})
if gone:
 d=s.state.rules.decision
 assert d.resume['step']=='pay_mana'
 before=s.state.model_dump_json()
 try:s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
 except ActionError:pass
 else:raise AssertionError('Departed permission was frozen')
 assert s.state.model_dump_json()==before
 index=next(i for i,ab in casting.mana_abilities(s.state,s.state.cards[mountain],repo))
 s.perform('p1',{'type':'activate_ability','card_id':mountain,'ability':index})
if s.state.cards[spell].zone!='stack':
 d=s.state.rules.decision
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
assert s.state.cards[spell].zone=='stack'
r=s.state.rules.payments[s.state.rules.object_id(spell)]
if gone:assert r.mana_spent.get('R')==1,r.mana_spent
else:
 assert r.mana_spent=={'W':1,'C':2},r.mana_spent
 assert Counter(r.mana_sources)==Counter([s.state.rules.object_id(plains),s.state.rules.object_id(ring),s.state.rules.object_id(ring)])
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), spell.id, ring.id, mountain.id, plains.id, str(gone)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr


def test_actual_sculpting_steel_copy_retains_permission_after_original_leaves(cards):
    s, g, bolt = setup(cards, ["Sculpting Steel"])
    steel = put(s, "Sculpting Steel", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    act(s, "p1", type="cast_spell", card_id=steel.id, sources=[])
    from tests.test_rules_designations import settle

    settle(s)
    d = s.state.rules.decision
    assert d is not None
    option = next(o for o in d.options if g.id in o.id)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option.id])
    answer(s)
    wait_priority(s, "p1")
    act(s, "p1", type="move", card_ids=[g.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], sources=[])
    assert s.state.rules.payments[s.state.rules.object_id(bolt.id)].mana_spent == {"W": 1}


def test_explicit_sources_never_expand_to_backup_after_permission_loss(cards, tmp_path):
    repo, name = cost_boundary_repo(cards, tmp_path)
    try:
        s = table(repo, [name, "Rift Bolt", "Mountain"], [], [])
        source = put(s, name, "battlefield")
        spell = put(s, "Rift Bolt", "hand")
        backup = put(s, "Mountain", "battlefield")
        to_phase(s, "main1", 4)
        wait_priority(s, "p1")
        act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], sources=[source.id])
        assert s.state.model_dump_json() == before
        assert not s.state.cards[backup.id].tapped
    finally:
        repo.close()


def test_legacy_synchronous_payment_refuses_before_any_source_mutation(cards):
    s, g, spell = setup(cards, ["Plains"])
    put(s, "Plains", "battlefield")
    p = Plan(s.state, "p1", cards, None)
    before = p.state.model_dump_json()
    with pytest.raises(ActionError, match="Activate these mana sources"):
        casting.pay(p, "p1", M.parse_cost("{R}"), "synchronous API")
    assert p.state.model_dump_json() == before and p.steps == []


def test_actual_auto_filter_pays_original_red_input_with_white_and_preserves_output(cards):
    s, g, spell = setup(cards, ["Plains", "Graven Cairns"], spell="Sign in Blood")
    plains = put(s, "Plains", "battlefield")
    filterland = put(s, "Graven Cairns", "battlefield")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    assert s.state.cards[plains.id].tapped and s.state.cards[filterland.id].tapped
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.mana_spent == {"B": 2}
    assert record.mana_sources == [s.state.rules.object_id(filterland.id)] * 2


def test_canonical_whole_card_coverage(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Sunglasses of Urza")).level == "FULL"


@pytest.mark.parametrize("stage", ["payment_filter_next", "sequential_mana_next", "sequential_mana_result"])
def test_native_registered_payment_adapters_preserve_legacy_source_budget(stage):
    from dataclasses import asdict

    from app.rules import payment_continuations as pc

    data = {
        "player": "p1",
        "cost": asdict(M.parse_cost("{R}")),
        "label": "legacy payment",
        "payment": asdict(M.Payment()),
        "exclude": [],
        "purpose": None,
        "life_due": 0,
        "then": {},
        "at": 0,
    }
    if stage.startswith("sequential"):
        data.update(sources=[], source_life=0)
    adapter, _ = pc._HANDLERS[stage]
    loaded = adapter.validate_python(data)
    assert loaded.allow_more_sources is False
    encoded = adapter.dump_json(loaded)
    assert adapter.validate_json(encoded) == loaded
