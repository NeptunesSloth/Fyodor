"""CR 115.1, 115.2b, 701.6: spell types and ability kinds form one target union."""
import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_activation_x import cards as cards
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave31d_spell_copies import hold, resolve_one


@pytest.mark.parametrize("name,mana,extra", [
    ("Lightning Bolt", {"R": 1}, {"targets": ["p2"]}),
    ("Jolted Awake", {"W": 1}, {"target_counts": [0]}),
])
def test_spider_sense_counters_each_named_spell_type(cards, name, mana, extra):
    assert coverage.of_card_data(cards.resolve("Spider-Sense")).level == "FULL"
    s = build(cards, ["Spider-Sense", name])
    hold(s)
    act(s, "p1", type="add_mana", player="p1", mana={**mana, "U": 2, "C": 5})
    target = put(s, name, "hand")
    act(s, "p1", type="cast_spell", card_id=target.id, **extra)
    act(s, "p1", type="cast_spell", card_id=put(s, "Spider-Sense", "hand").id, targets=[target.id])
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 40 and not s.state.players["p1"].resources.get("energy", 0)
    roundtrip(s)


def test_spider_sense_counters_a_triggered_ability(cards):
    assert coverage.of_card_data(cards.resolve("Spider-Sense")).level == "FULL"
    s = build(cards, ["Spider-Sense", "Elvish Visionary"])
    hold(s)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "U": 2, "C": 5})
    act(s, "p1", type="cast_spell", card_id=put(s, "Elvish Visionary", "hand").id)
    resolve_one(s)
    trigger = s.state.zones["stack"][-1]
    before = len(s.state.zones.get("p1:hand", []))
    act(s, "p1", type="cast_spell", card_id=put(s, "Spider-Sense", "hand").id, targets=[trigger])
    settle(s)
    assert len(s.state.zones.get("p1:hand", [])) == before
    roundtrip(s)


def test_spider_sense_rejects_creature_spells(cards):
    s = build(cards, ["Spider-Sense", "Grizzly Bears"])
    hold(s)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "U": 2, "C": 5})
    target = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="cast_spell", card_id=target.id)
    spell = put(s, "Spider-Sense", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    assert s.state.cards[spell.id].zone == "p1:hand"
    roundtrip(s)


def test_spider_sense_rejects_activated_abilities(cards):
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ["Spider-Sense", "Prodigal Pyromancer"])
    source = put(s, "Prodigal Pyromancer", "battlefield")
    next_turn(s)
    hold(s)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=["p2"])
    target = s.state.zones["stack"][-1]
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2, "C": 5})
    spell = put(s, "Spider-Sense", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target])
    assert s.state.cards[spell.id].zone == "p1:hand"
    roundtrip(s)
