"""Activation modifiers remain relative to their source and chosen activation kind."""

import pytest

from app.game.errors import ActionError
from app.rules import mana_units
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import activate, game
from tests.test_rules_table_activation_modifiers52 import cards as cards


def test_power_artifact_reduces_opponents_enchanted_artifact_too(cards):
    s = game(cards, ["Power Artifact"], ["Basalt Monolith"])
    source = put(s, "Basalt Monolith", "battlefield", "p2")
    aura = put(s, "Power Artifact", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[source.id], sources=[])
    answer(s)
    act(s, "p2", type="tap", card_ids=[source.id], tapped=True)
    activate(s, source, "Untap", pid="p2", mana={"C": 1})
    assert not source.tapped and not mana_units.visible_pool(s.state, "p2")
    roundtrip(s)


def test_embalmers_does_not_reduce_opponents_graveyard_activation(cards):
    s = game(cards, ["Embalmer's Tools"], ["Reassembling Skeleton"])
    put(s, "Embalmer's Tools", "battlefield")
    source = put(s, "Reassembling Skeleton", "graveyard", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"B": 1})
    ability = next(a for a in Plan(s.state, "p2", cards, None).ch(source).abilities if "Return" in a.text)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    assert s.state.model_dump_json() == before
    activate(s, source, "Return", pid="p2", mana={"C": 1})
    assert source.zone == "p2:battlefield" and source.tapped
    assert not mana_units.visible_pool(s.state, "p2")
    roundtrip(s)


def test_boom_does_not_reduce_an_ordinary_activated_ability(cards):
    s = game(cards, ["Boom Scholar", "Spectral Sailor"])
    put(s, "Boom Scholar", "battlefield")
    source = put(s, "Spectral Sailor", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 1})
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Draw a card" in a.text
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    assert s.state.model_dump_json() == before
    activate(s, source, "Draw a card", mana={"C": 2})
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_power_artifact_does_not_reduce_snow_symbol_requirement(cards):
    from app.rules import casting

    s = game(cards, ["Power Artifact", "Phyrexian Ironfoot", "Snow-Covered Forest"])
    source = put(s, "Phyrexian Ironfoot", "battlefield")
    snow = put(s, "Snow-Covered Forest", "battlefield")
    aura = put(s, "Power Artifact", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[source.id], sources=[])
    answer(s)
    act(s, "p1", type="tap", card_ids=[source.id], tapped=True)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    ability = next(a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Untap" in a.text)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    assert s.state.model_dump_json() == before
    index = next(i for i, _ in casting.mana_abilities(s.state, snow, cards))
    act(s, "p1", type="activate_ability", card_id=snow.id, ability=index)
    answer(s)
    activate(s, source, "Untap")
    assert not source.tapped and mana_units.visible_pool(s.state, "p1") == {"C": 2}
    roundtrip(s)


@pytest.mark.parametrize("announced,paid", [(0, 0), (1, 1), (3, 1), (6, 4)])
def test_power_artifact_reads_announced_x_before_applying_its_floor(cards, announced, paid):
    s = game(cards, ["Power Artifact", "Chimeric Staff"])
    source = put(s, "Chimeric Staff", "battlefield")
    aura = put(s, "Power Artifact", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[source.id], sources=[])
    answer(s)
    if paid:
        act(s, "p1", type="add_mana", player="p1", mana={"C": paid})
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if a.text.startswith("{X}:")
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability.index,
        x_value=announced,
        sources=[],
    )
    answer(s)
    assert not mana_units.visible_pool(s.state, "p1")
    if announced:
        assert source.zone == "p1:battlefield"
        assert Plan(s.state, "p1", cards, None).ch(source).pt == (announced, announced)
    else:
        assert source.zone == "p1:graveyard" and aura.zone == "p1:graveyard"
    roundtrip(s)


def test_convergence_own_floor_leaves_one_generic_mana(cards):
    s = game(
        cards, ["Convergence of Dominion", "Isamaru, Hound of Konda", "Gravestone Strider"], ["Grizzly Bears"]
    )
    put(s, "Convergence of Dominion", "battlefield")
    commander = put(s, "Isamaru, Hound of Konda", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id, value=True)
    source = put(s, "Gravestone Strider", "graveyard")
    victim = put(s, "Grizzly Bears", "graveyard", "p2")
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Exile this card" in a.text
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=ability.index,
            targets=[victim.id],
            sources=[],
        )
    assert s.state.model_dump_json() == before
    activate(s, source, "Exile this card", mana={"C": 1}, targets=[victim.id])
    assert source.zone == "p1:exile" and victim.zone == "p2:exile"
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_convergence_reduces_land_card_but_embalmers_creature_only_filter_does_not(cards):
    s = game(
        cards, ["Convergence of Dominion", "Embalmer's Tools", "Isamaru, Hound of Konda", "Drownyard Temple"]
    )
    put(s, "Convergence of Dominion", "battlefield")
    put(s, "Embalmer's Tools", "battlefield")
    commander = put(s, "Isamaru, Hound of Konda", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id, value=True)
    source = put(s, "Drownyard Temple", "graveyard")
    activate(s, source, "Return", mana={"C": 1})
    assert source.zone == "p1:battlefield" and source.tapped
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def setup_taxed_loot(cards):
    s = game(
        cards, ["Boom Scholar", "Loot, the Pathfinder", "Painter's Servant", "Enchanted Evening", "Gloom"]
    )
    put(s, "Boom Scholar", "battlefield")
    source = put(s, "Loot, the Pathfinder", "battlefield")
    put(s, "Enchanted Evening", "battlefield")
    painter = put(s, "Painter's Servant", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="cast_spell", card_id=painter.id, sources=[])
    answer(s)
    put(s, "Gloom", "battlefield")
    ch = Plan(s.state, "p1", cards, None).ch(source)
    assert "W" in ch.colors and "Enchantment" in ch.types
    return s, source


def test_boom_reduces_actual_taxed_exhaust_mana_ability(cards):
    from app.rules import casting

    s, source = setup_taxed_loot(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index, mana_choice="R", sources=[])
    answer(s)
    assert source.tapped and mana_units.visible_pool(s.state, "p1") == {"R": 3}
    roundtrip(s)
