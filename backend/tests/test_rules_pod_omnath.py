"""The pod's Omnath, Locus of Creation deck (tests/fixtures/soak_decks/omnath_elem.txt): its plan, with real Oracle text.

Omnath's landfall counts its own resolutions each turn: the first gains 4 life, the second adds {R}{G}{W}{U}, the third deals 4 damage to each
opponent and each planeswalker Alice doesn't control. The deck plays several lands a turn (Exploration, Azusa), replays bounce lands (Selesnya
Sanctuary, untapped by Amulet of Vigor), returns lands from the graveyard (Splendid Reclamation), doubles the triggers (Ancient Greenwarden for a
land entering, Annie Joins Up for a legendary creature's ability: both apply, so one land makes three) and turns its creatures into lands (Ashaya:
a creature spell that resolves is a land entering).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import hints
from tests.game_helpers import act
from tests.pod_c_kit import ch, field, mana, put, settle, table, to_hand, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

OMNATH = "Omnath, Locus of Creation"
EXTRA = [
    real('Omnath, Locus of Creation', '{R}{G}{W}{U}', 4, 'Legendary Creature — Elemental',
         "When Omnath enters, draw a card.\nLandfall — Whenever a land you control enters, you gain 4 life if this is the first time this ability "
         "has resolved this turn. If it's the second time, add {R}{G}{W}{U}. If it's the third time, Omnath deals 4 damage to each opponent and "
         "each planeswalker you don't control.", ('4', '4'), 'GRUW'),
    real('Springheart Nantuko', '{1}{G}', 2, 'Enchantment Creature — Insect Monk',
         "Bestow {1}{G}\nEnchanted creature gets +1/+1.\nLandfall — Whenever a land you control enters, you may pay {1}{G} if this permanent is "
         "attached to a creature you control. If you do, create a token that's a copy of that creature. If you didn't create a token this way, "
         "create a 1/1 green Insect creature token.", ('1', '1'), 'G'),
    real('Roil Elemental', '{3}{U}{U}{U}', 6, 'Creature — Elemental',
         'Flying\nLandfall — Whenever a land you control enters, you may gain control of target creature for as long as you control this '
         'creature.', ('3', '2'), 'U'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def omnath(cards, *mine, theirs=(), on_field=True):
    s = table(cards, mine, theirs, commander=OMNATH)
    if on_field:
        put(s, OMNATH)
    return s


def land(s, pid: str = "p1"):
    """Alice plays a Forest from her library (moved to her hand first)."""
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == pid and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, pid, type="play_land", card_id=forest.id)
    return forest


def test_bestow_is_offered_only_with_a_creature_to_enchant(cards):
    """702.103b, 601.2c: cast bestowed, Springheart Nantuko is an Aura spell that targets a creature; with no creature on the battlefield the
    alternative cost isn't offered (cast_spell refuses it), but casting it as a creature is. Once there is one, it is offered and works."""
    s = omnath(cards, "Springheart Nantuko", theirs=["Grizzly Bears"], on_field=False)
    nantuko = to_hand(s, "Springheart Nantuko")
    mana(s, G=2)
    offered = hints(s.state, "p1", s.cards)
    assert nantuko.id not in offered.get("alt_castable", {}) and nantuko.id in offered["castable"]
    with pytest.raises(ActionError, match="no legal target"):
        act(s, "p1", type="cast_spell", card_id=nantuko.id, alt_cost=f"{nantuko.id}:0")
    bears = put(s, "Grizzly Bears", "p2")
    assert [o["id"] for o in hints(s.state, "p1", s.cards)["alt_castable"][nantuko.id]] == [f"{nantuko.id}:0"]
    act(s, "p1", type="cast_spell", card_id=nantuko.id, alt_cost=f"{nantuko.id}:0", targets=[bears.id])
    settle(s)
    assert s.state.cards[nantuko.id].attached_to == bears.id
    check(s)


def test_roil_elemental_asks_in_words_and_keeps_control_while_it_stays(cards):
    """Its landfall's "you may" question reads as English (it said "Until, gain_control?"); the stolen creature stays Alice's past the turn and
    goes back once Roil Elemental leaves."""
    s = omnath(cards, "Roil Elemental", "Swords to Plowshares", theirs=["Grizzly Bears"], on_field=False)
    roil = put(s, "Roil Elemental")
    bears = put(s, "Grizzly Bears", "p2")
    land(s)
    asked = settle(s, "Grizzly Bears", "Yes")
    assert "Roil Elemental: Gain control of it?" in asked
    assert s.state.cards[bears.id].controller == "p1"
    until(s, "p2", "main1")
    until(s, "p1", "main1")
    assert s.state.cards[bears.id].controller == "p1"
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Swords to Plowshares").id, targets=[roil.id])
    settle(s)
    assert s.state.cards[bears.id].controller == "p2" and field(s, "p2")["Grizzly Bears"] == 1
    check(s)


def test_an_animated_mutavault_taps_for_mana(cards):
    """Mutavault animated is a creature with all creature types (205.3m: over 300 of them); tapped for mana, the mana remembers what made it
    (106.12, 608.2h). The remembered types had a cap of 40, so this crashed (an AUTOMATION ERROR) instead of adding {C}."""
    s = omnath(cards, "Mutavault", on_field=False)
    vault = put(s, "Mutavault")
    until(s, "p2", "main1")
    until(s, "p1", "main1")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    settle(s)
    assert "Creature" in ch(s, vault).types and len(ch(s, vault).subtypes) > 300
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=0)
    assert [u.sym for u in s.state.players["p1"].mana_units] == ["C"] and s.state.cards[vault.id].tapped
    check(s)
