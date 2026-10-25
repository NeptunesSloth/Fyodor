"""Wave 110C: Crackling Emergence / Harmonious Emergence (614.1a: destruction of the enchanted land is replaced by sacrificing the Aura, 701.17a;
702.12b: the land gains indestructible until end of turn, so it survives destroy effects and lethal damage)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_hand, zone

LINE = ("Enchant land you control\n{0}\nIf enchanted land would be destroyed, instead sacrifice this Aura and that land gains indestructible "
        "until end of turn.")
EXTRA = [real("Crackling Emergence", "{R}", 1, "Enchantment — Aura",
              LINE.format("Enchanted land is a 3/3 red Spirit creature with haste. It's still a land."), None, "R"),
         real("Harmonious Emergence", "{1}{G}", 2, "Enchantment — Aura",
              LINE.format("Enchanted land is a 4/5 green Spirit creature with vigilance and haste. It's still a land."), None, "G"),
         real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R")]
NAMES = ["Crackling Emergence", "Harmonious Emergence"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def enchant(s, name):
    land = put(s, "Forest")
    aura = to_hand(s, name)
    mana(s, R=2, G=2)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[land.id])
    answer(s)
    assert s.state.cards[aura.id].attached_to == land.id
    return land, aura


@pytest.mark.parametrize("name", NAMES)
def test_destroy_sacrifices_the_aura_instead(name, cards):
    s = build(cards, [name, "Stone Rain", "Forest"])
    land, aura = enchant(s, name)
    mana(s, R=3)
    cast(s, "Stone Rain", [land.id])
    answer(s)
    assert zone(s, land) == "p1:battlefield" and zone(s, aura) == "p1:graveyard"
    mana(s, R=3)  # indestructible until end of turn: a second Stone Rain does nothing either
    cast(s, "Stone Rain", [land.id])
    answer(s)
    assert zone(s, land) == "p1:battlefield"
    check(s)


def test_lethal_damage_is_replaced_too(cards):
    s = build(cards, ["Crackling Emergence", "Lightning Bolt", "Forest"])
    land, aura = enchant(s, "Crackling Emergence")
    mana(s, R=1)
    cast(s, "Lightning Bolt", [land.id])  # 3 damage to the 3/3 land creature (704.5g)
    answer(s)
    assert zone(s, land) == "p1:battlefield" and zone(s, aura) == "p1:graveyard"
    check(s)
