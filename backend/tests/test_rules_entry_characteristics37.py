"""Canonical exact-target delayed watches, event batching and source/controller identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/entry_characteristics37_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/entry_characteristics37_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize("x", [0, 2])
def test_abuelo_actual_fixed_spirit_flying_and_additional_x_counters(cards, x):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=x, target_counts=[1])
    current = s.state.cards[artifact.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert current.zone == "p1:battlefield"
    assert ch.types == {"Artifact", "Creature"}
    assert ch.subtypes == {"Spirit"}
    assert ch.pt == (1 + x, 1 + x)
    assert "flying" in ch.keywords
    assert current.counters.get("+1/+1", 0) == x
    assert current.entry_characteristics is not None
    roundtrip(s)


def test_abuelo_noncreature_card_enters_as_creature_for_authority_replacement(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=0, target_counts=[1])
    assert s.state.cards[artifact.id].tapped
    assert s.state.players["p2"].life == 41
    roundtrip(s)


def test_abuelo_form_applies_to_containment_priest_redirect_and_not_exiled_card(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    put(s, "Containment Priest", "battlefield", pid="p2")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=2, target_counts=[1])
    assert s.state.cards[artifact.id].zone == "p1:exile"
    assert s.state.cards[artifact.id].entry_characteristics is None
    assert not s.state.cards[artifact.id].counters
    roundtrip(s)


def test_existing_enduring_returns_noncreature_before_tapped_replacement(cards):
    s = setup(cards)
    put(s, "Blind Obedience", "battlefield", pid="p2")
    start(s)
    cat = cast(s, "Enduring Curiosity")
    assert s.state.cards[cat.id].tapped
    cast(s, "Lightning Bolt", [cat.id], target_counts=[1])
    current = s.state.cards[cat.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert current.zone == "p1:battlefield" and ch.types == {"Enchantment"}
    assert not current.tapped
    roundtrip(s)


def test_existing_enduring_noncreature_return_not_exiled_by_priest(cards):
    s = setup(cards)
    put(s, "Containment Priest", "battlefield", pid="p2")
    start(s)
    cat = cast(s, "Enduring Curiosity")
    cast(s, "Lightning Bolt", [cat.id], target_counts=[1])
    current = s.state.cards[cat.id]
    assert current.zone == "p1:battlefield"
    assert Plan(s.state, "p1", cards, None).ch(current).types == {"Enchantment"}
    roundtrip(s)


def test_existing_rise_grave_adds_black_zombie_without_overwriting_green(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    put(s, "Champion of the Perished", "battlefield")
    start(s)
    cast(s, "Rise from the Grave", [bear.id], target_counts=[1])
    current = s.state.cards[bear.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert ch.colors == {"G", "B"} and ch.subtypes == {"Bear", "Zombie"}
    assert current.entry_characteristics is not None
    roundtrip(s)


def test_cloning_returned_spirit_artifact_does_not_copy_entry_form(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=2, target_counts=[1])
    clone = cast(s, "Clone")
    pick(s, [artifact.id])
    settle(s)
    ch = Plan(s.state, "p1", cards, None).ch(s.state.cards[clone.id])
    assert ch.name == "Sol Ring" and ch.types == {"Artifact"}
    assert not ch.subtypes and "flying" not in ch.keywords
    assert s.state.cards[clone.id].entry_characteristics is None
    roundtrip(s)


@pytest.mark.parametrize("x", [5, 6])
def test_dance_threshold_entry_replacements_and_mana_value(cards, x):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    start(s)
    cast(s, "Dance of the Manse", [artifact.id], x_value=x, target_counts=[1])
    current = s.state.cards[artifact.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert ("Creature" in ch.types) == (x >= 6)
    assert current.tapped == (x >= 6)
    assert ch.pt == ((4, 4) if x >= 6 else None)
    roundtrip(s)


def test_grimoire_actual_sacrificed_source_all_graveyards_atomic_entry(cards):
    from tests.game_helpers import act

    s = setup(cards)
    book = put(s, "Grimoire of the Dead", "battlefield")
    bears = [put(s, "Grizzly Bears", "graveyard", pid=p) for p in ["p1", "p2", "p3"]]
    start(s)
    act(s, "p1", type="counter", card_ids=[book.id], kind="study", delta=3)
    act(s, "p1", type="activate_ability", card_id=book.id, ability=1)
    settle(s)
    assert s.state.cards[book.id].zone == "p1:graveyard"
    for bear in bears:
        current = s.state.cards[bear.id]
        ch = Plan(s.state, "p1", cards, None).ch(current)
        assert current.zone == "p1:battlefield" and current.controller == "p1"
        assert ch.colors == {"G", "B"} and ch.subtypes == {"Bear", "Zombie"}
    roundtrip(s)


def test_drana_defender_chooses_original_controllers_graveyard(cards):
    from tests.test_rules_defender_relative36 import attack

    s = setup(cards)
    source = put(s, "Drana, the Last Bloodchief", "battlefield")
    bear = put(s, "Grizzly Bears", "graveyard")
    other = put(s, "Runeclaw Bear", "graveyard")
    wrong = put(s, "Memnite", "graveyard", pid="p2")
    start(s)
    attack(s, source)
    decision = s.state.rules.decision
    assert decision and decision.player == "p2"
    assert {o.card_id for o in decision.options} == {bear.id, other.id}
    assert wrong.id not in {o.card_id for o in decision.options}
    roundtrip(s)
    pick(s, [bear.id])
    settle(s)
    ch = Plan(s.state, "p1", cards, None).ch(s.state.cards[bear.id])
    assert ch.subtypes == {"Bear", "Vampire"} and ch.pt == (3, 3)
    roundtrip(s)


def test_excava_noncreature_artifact_spirit_entry_with_finality(cards):
    from tests.test_rules_defender_relative36 import attack

    s = setup(cards)
    source = put(s, "Excava, the Risen Past", "battlefield")
    artifact = put(s, "Sol Ring", "graveyard")
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    start(s)
    attack(s, source)
    pick(s, [artifact.id])
    settle(s)
    current = s.state.cards[artifact.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert current.zone == "p1:battlefield" and current.tapped
    assert ch.pt == (1, 1) and ch.subtypes == {"Spirit"} and "flying" in ch.keywords
    assert current.counters["finality"] == 1
    cast(s, "Lightning Bolt", [artifact.id], target_counts=[1])
    assert s.state.cards[artifact.id].zone == "p1:exile"
    roundtrip(s)


def test_relive_returns_three_target_groups_simultaneously_as_elementals(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    land = put(s, "Forest", "graveyard")
    enchantment = put(s, "Blind Obedience", "graveyard")
    start(s)
    cast(s, "Relive the Past", [artifact.id, land.id, enchantment.id], target_counts=[1, 1, 1])
    for cid in [artifact.id, land.id, enchantment.id]:
        current = s.state.cards[cid]
        ch = Plan(s.state, "p1", cards, None).ch(current)
        assert current.zone == "p1:battlefield" and ch.pt == (5, 5)
        assert ch.subtypes == ({"Elemental", "Forest"} if cid == land.id else {"Elemental"})
    roundtrip(s)


def test_ghouls_choices_all_before_entry_and_added_color_type_decayed(cards):
    s = setup(cards)
    bears = [put(s, "Grizzly Bears", "graveyard", pid=p) for p in ["p1", "p2", "p3"]]
    extras = [put(s, "Runeclaw Bear", "graveyard", pid=p) for p in ["p1", "p2", "p3"]]
    start(s)
    cast(s, "Ghouls' Night Out")
    for bear in bears:
        assert all(s.state.cards[b.id].zone.endswith(":graveyard") for b in bears)
        assert s.state.rules.decision.player == "p1"
        pick(s, [bear.id])
        settle(s)
    for bear in bears:
        current = s.state.cards[bear.id]
        ch = Plan(s.state, "p1", cards, None).ch(current)
        assert current.zone == "p1:battlefield" and ch.subtypes == {"Bear", "Zombie"}
        assert ch.colors == {"G", "B"} and "decayed" in ch.keywords
    assert all(s.state.cards[c.id].zone.endswith(":graveyard") for c in extras)
    roundtrip(s)


@pytest.mark.parametrize(
    "name,damage,types,subtypes,counters",
    [
        ("Tom, Bert, and William", 6, {"Artifact"}, set(), {}),
        ("Otherworldly Escort", 2, {"Creature"}, {"Spirit", "Detective"}, {"charge": 4}),
    ],
)
def test_actual_dies_returns_as_new_form_and_does_not_repeat(cards, name, damage, types, subtypes, counters):
    s = setup(cards)
    source = put(s, name, "battlefield")
    start(s)
    if damage == 6:
        cast(s, "Lightning Bolt", [source.id], target_counts=[1])
    cast(s, "Lightning Bolt", [source.id], target_counts=[1])
    current = s.state.cards[source.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert current.zone == "p1:battlefield" and ch.types == types and ch.subtypes == subtypes
    assert current.counters == counters
    if name == "Otherworldly Escort":
        cast(s, "Lightning Bolt", [source.id], target_counts=[1])
        assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_grave_betrayal_frozen_delayed_new_graveyard_object_and_added_counter(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, "Grave Betrayal", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Lightning Bolt", [bear.id], target_counts=[1])
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert len(s.state.rules.delayed) == 1
    roundtrip(s)
    to_phase(s, "end", turn=4)
    settle(s)
    current = s.state.cards[bear.id]
    ch = Plan(s.state, "p1", cards, None).ch(current)
    assert current.zone == "p1:battlefield" and current.controller == "p1"
    assert ch.subtypes == {"Bear", "Zombie"} and ch.colors == {"G", "B"} and ch.pt == (3, 3)
    roundtrip(s)


def test_war_third_chapter_native_target_total_and_artifact_entry(cards):

    s = setup(cards)
    from tests.test_rules_wave30m_durations import to_phase

    bear = put(s, "Grizzly Bears", "graveyard")
    wall = put(s, "Wall of Omens", "graveyard")
    start(s)
    cast(s, "The War in Heaven")
    to_phase(s, "main1", turn=7)
    settle(s)
    to_phase(s, "main1", turn=10)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == "choose_cards"
    pick(s, [bear.id, wall.id])
    settle(s)
    for c in [bear, wall]:
        current = s.state.cards[c.id]
        assert current.zone == "p1:battlefield" and current.counters["necrodermis"] == 1
        assert "Artifact" in Plan(s.state, "p1", cards, None).ch(current).types
    roundtrip(s)


@pytest.mark.parametrize("accept", [True, False])
def test_arbiter_reveal_optional_top_becomes_enchantment_before_constellation(cards, accept):
    from tests.game_helpers import act

    s = setup(cards)
    source = put(s, "Arbiter of the Ideal", "battlefield")
    put(s, "Eidolon of Blossoms", "battlefield")
    start(s)
    top = put(s, "Sol Ring", "library")
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="tap", card_ids=[source.id], tapped=True)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "upkeep", turn=7)
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == "p1"
    roundtrip(s)
    pick(s, [top.id] if accept else [])
    settle(s)
    current = s.state.cards[top.id]
    if accept:
        assert current.zone == "p1:battlefield" and current.counters["manifestation"] == 1
        assert Plan(s.state, "p1", cards, None).ch(current).types == {"Artifact", "Enchantment"}
        assert len(s.state.zones["p1:hand"]) == before + 1
        act(s, "p1", type="counter", card_ids=[top.id], kind="manifestation", delta=-1)
        assert "Enchantment" in Plan(s.state, "p1", cards, None).ch(s.state.cards[top.id]).types
    else:
        assert current.zone == "p1:library" and s.state.zones["p1:library"][0] == top.id
    roundtrip(s)


def test_grave_betrayal_does_not_recover_a_later_graveyard_incarnation(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, "Grave Betrayal", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Lightning Bolt", [bear.id], target_counts=[1])
    first = Plan(s.state, "p1", cards, None).oid(bear.id)
    cast(s, "Rise from the Grave", [bear.id], target_counts=[1])
    cast(s, "Lightning Bolt", [bear.id], target_counts=[1])
    assert Plan(s.state, "p1", cards, None).oid(bear.id) != first
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    roundtrip(s)


def test_abuelo_form_clears_when_same_physical_card_blinks(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=2, target_counts=[1])
    cast(s, "Cloudshift", [artifact.id], target_counts=[1])
    current = s.state.cards[artifact.id]
    assert current.zone == "p1:battlefield" and current.entry_characteristics is None
    assert Plan(s.state, "p1", cards, None).ch(current).types == {"Artifact"}
    assert not current.counters
    roundtrip(s)


def test_abuelo_creature_before_counters_doubling_replacement(cards):
    s = setup(cards)
    artifact = put(s, "Sol Ring", "graveyard")
    put(s, "Doubling Season", "battlefield")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=2, target_counts=[1])
    current = s.state.cards[artifact.id]
    assert current.counters["+1/+1"] == 4
    assert Plan(s.state, "p1", cards, None).ch(current).pt == (5, 5)
    roundtrip(s)


def test_drana_saved_opposing_choice_resumes_cold_with_entry_form(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_defender_relative36 import attack

    s = setup(cards)
    source = put(s, "Drana, the Last Bloodchief", "battlefield")
    bear = put(s, "Grizzly Bears", "graveyard")
    put(s, "Runeclaw Bear", "graveyard")
    start(s)
    attack(s, source)
    assert s.state.rules.decision.player == "p2"
    saved = tmp_path / "entry37.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.rules.decision.player=='p2'
pick(s,[sys.argv[3]]);settle(s)
c=s.state.cards[sys.argv[3]]
assert c.zone=='p1:battlefield' and c.entry_characteristics is not None
assert Plan(s.state,'p1',repo,None).ch(c).subtypes=={'Bear','Vampire'}
assert c.counters['+1/+1']==1
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), bear.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_saved_copy_entry_replacement_retains_prospective_form_cold(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    artifact = put(s, "Phyrexian Metamorph", "graveyard")
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    cast(s, "Abuelo's Awakening", [artifact.id], x_value=2, target_counts=[1])
    d = s.state.rules.decision
    assert d and any(o.card_id == bear.id for o in d.options)
    assert s.state.cards[artifact.id].zone == "p1:graveyard"
    saved = tmp_path / "entry-copy37.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,[sys.argv[4]]);settle(s)
c=s.state.cards[sys.argv[3]]
assert c.zone=='p1:battlefield' and c.entry_characteristics is not None
ch=Plan(s.state,'p1',repo,None).ch(c)
assert ch.name=='Grizzly Bears' and ch.types=={'Creature','Artifact'}
assert ch.subtypes=={'Spirit'} and ch.pt==(3,3) and 'flying' in ch.keywords
assert c.counters['+1/+1']==2
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), artifact.id, bear.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
