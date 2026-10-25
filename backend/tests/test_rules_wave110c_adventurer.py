"""Wave 110C: Ravenloft Adventurer (614.6 an opponent's creature is exiled with a hit counter instead of dying; 508.5 the defending player's own
hit-counter cards drain them once a dungeon is completed, 309.7)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.test_rules_wave45b_dungeons import EXTRA as DUNGEON_CARDS
from tests.test_rules_wave45b_dungeons import drive, rules, season
from tests.wave110c_kit import build, check, life, make_db, mana, put, real, to_hand

EXTRA = [real("Ravenloft Adventurer", "{2}{W}", 3, "Creature — Human Warrior",
              "When this creature enters, you take the initiative.\nIf a creature an opponent controls would die, instead exile it and put a hit counter on it.\n"
              "Whenever this creature attacks, if you've completed a dungeon, defending player loses 1 life for each card they own in exile with a hit counter on it.",
              ("3", "3"), "W")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, [*DUNGEON_CARDS, *EXTRA])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Ravenloft Adventurer")).level == "FULL"


@pytest.mark.parametrize("dungeon", [True, False])
def test_exiles_with_hit_counter_and_drains_only_after_a_dungeon(cards, dungeon):
    s = build(cards, ["Ravenloft Adventurer", "Secret Door", "Lightning Bolt"], ["Grizzly Bears"])
    door = put(s, "Secret Door")
    if dungeon:
        for room in ("Lost Mine of Phandelver", "Goblin Lair", "Storeroom", "Temple of Dumathoin"):
            mana(s, "p1", U=1, C=4)
            act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
            drive(s, want=[room])
        assert rules(s).completed_dungeons["p1"]
    adv = put(s, "Ravenloft Adventurer")
    drive(s)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    drive(s)
    assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[bears.id].counters.get("hit") == 1
    season(s)
    to_phase(s, "declare_attackers", 3)
    before = life(s, "p2")
    attack(s, (adv, "p2"))
    drive(s)
    assert life(s, "p2") == before - (1 if dungeon else 0) - 3
    check(s)
