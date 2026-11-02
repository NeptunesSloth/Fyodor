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
from tests.pod_c_kit import card, ch, field, mana, on_top, put, settle, table, to_hand, until
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

    real('Ancient Greenwarden', '{4}{G}{G}', 6, 'Creature — Elemental',
         'Reach (This creature can block creatures with flying.)\nYou may play lands from your graveyard.\nIf a land entering causes a triggered '
         'ability of a permanent you control to trigger, that ability triggers an additional time.', ('5', '7'), 'G'),
    real('Annie Joins Up', '{1}{R}{G}{W}', 4, 'Legendary Enchantment',
         'When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a '
         'legendary creature you control triggers, that ability triggers an additional time.', None, 'GRW'),
    real('Ashaya, Soul of the Wild', '{3}{G}{G}', 5, 'Legendary Creature — Elemental',
         "Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control are Forest lands in "
         "addition to their other types. (They're still affected by summoning sickness.)", ('*', '*'), 'G'),
    real('Lotus Cobra', '{1}{G}', 2, 'Creature — Snake', 'Landfall — Whenever a land you control enters, add one mana of any color.', ('2', '1'), 'G'),
    real('Exploration', '{G}', 1, 'Enchantment', 'You may play an additional land on each of your turns.', None, 'G'),
    real('Azusa, Lost but Seeking', '{2}{G}', 3, 'Legendary Creature — Human Monk', 'You may play two additional lands on each of your turns.',
         ('1', '2'), 'G'),
    real('Selesnya Sanctuary', '', 0, 'Land',
         "This land enters tapped.\nWhen this land enters, return a land you control to its owner's hand.\n{T}: Add {G}{W}."),
    real('Amulet of Vigor', '{1}', 1, 'Artifact', 'Whenever a permanent you control enters tapped, untap it.'),
    real('Splendid Reclamation', '{3}{G}', 4, 'Sorcery', 'Return all land cards from your graveyard to the battlefield tapped.', None, 'G'),
    real('Omnath, Locus of Rage', '{3}{R}{R}{G}{G}', 7, 'Legendary Creature — Elemental',
         'Landfall — Whenever a land you control enters, create a 5/5 red and green Elemental creature token.\nWhenever Omnath or another '
         'Elemental you control dies, Omnath deals 3 damage to any target.', ('5', '5'), 'GR'),
    real('Risen Reef', '{1}{G}{U}', 3, 'Creature — Elemental',
         "Whenever this creature or another Elemental you control enters, look at the top card of your library. If it's a land card, you may "
         "put it onto the battlefield tapped. If you don't put the card onto the battlefield, put it into your hand.", ('1', '1'), 'GU'),
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
    """Alice plays a Forest from her library (the bottom one, moved to her hand first)."""
    forest = next(s.state.cards[i] for i in reversed(s.state.zones[f"{pid}:library"]) if s.state.cards[i].name == "Forest")
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


def life(s):
    return s.state.players["p1"].life, s.state.players["p2"].life


def pool(s):
    return sorted(u.sym for u in s.state.players["p1"].mana_units)


def test_omnath_counts_its_resolutions_each_turn(cards):
    """First land: 4 life; second: {R}{G}{W}{U}; third: 4 damage to Bob and to his planeswalker, not to Alice's; fourth: nothing."""
    s = omnath(cards, "Exploration", "Azusa, Lost but Seeking")
    put(s, "Exploration"), put(s, "Azusa, Lost but Seeking")
    walkers = {}
    for pid, name in (("p1", "Mine"), ("p2", "Theirs")):
        act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Legendary Planeswalker — Test"})
        walkers[pid] = next(c for c in s.state.cards.values() if c.name == name)
        act(s, pid, type="counter", card_ids=[walkers[pid].id], kind="loyalty", delta=6)
    land(s), settle(s)
    assert life(s) == (44, 40) and pool(s) == []
    land(s), settle(s)
    assert life(s) == (44, 40) and pool(s) == ["G", "R", "U", "W"]
    land(s), settle(s)
    assert life(s) == (44, 36) and s.state.cards[walkers["p2"].id].counters["loyalty"] == 2
    assert s.state.cards[walkers["p1"].id].counters["loyalty"] == 6
    land(s), settle(s)
    assert life(s) == (44, 36) and pool(s) == ["G", "R", "U", "W"]
    check(s)


def test_greenwarden_and_annie_make_one_land_three_omnath_triggers(cards):
    """Each "triggers an additional time" applies (Ancient Greenwarden: a land entering; Annie Joins Up: a legendary creature's ability): one
    land is all three of Omnath's effects."""
    s = omnath(cards, "Ancient Greenwarden", "Annie Joins Up")
    put(s, "Ancient Greenwarden"), put(s, "Annie Joins Up")
    settle(s)
    land(s), settle(s)
    assert life(s) == (44, 36) and pool(s) == ["G", "R", "U", "W"]
    check(s)


def test_ashaya_makes_a_creature_spell_a_land_entering(cards):
    """Ashaya's creatures are Forest lands, so a creature that resolves is a land entering: Omnath's landfall, and the Cobra's own (603.6a: it
    looks at the permanent as it is on the battlefield)."""
    s = omnath(cards, "Ashaya, Soul of the Wild", "Lotus Cobra")
    put(s, "Ashaya, Soul of the Wild")
    assert "Land" in ch(s, card(s, OMNATH)).types
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lotus Cobra").id)
    settle(s, "{W}")
    assert life(s) == (44, 40) and pool(s) == ["W"]
    check(s)


def test_a_bounce_land_untapped_by_amulet_and_replayed_with_extra_land_drops(cards):
    """Selesnya Sanctuary enters tapped (Amulet of Vigor untaps it) and returns a Forest; Exploration and Azusa give four land plays, not five."""
    s = omnath(cards, "Selesnya Sanctuary", "Amulet of Vigor", "Exploration", "Azusa, Lost but Seeking")
    for name in ("Amulet of Vigor", "Exploration", "Azusa, Lost but Seeking"):
        put(s, name)
    forest = land(s)
    settle(s)
    sanctuary = to_hand(s, "Selesnya Sanctuary")
    act(s, "p1", type="play_land", card_id=sanctuary.id)
    settle(s, "Forest")
    assert not s.state.cards[sanctuary.id].tapped and s.state.cards[forest.id].zone == "p1:hand"
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    land(s), settle(s)
    assert life(s) == (44, 36) and pool(s) == ["G", "R", "U", "W"]
    with pytest.raises(ActionError, match="already played all the lands"):
        land(s)
    check(s)


def test_splendid_reclamation_returns_three_lands_at_once(cards):
    """Three lands entering together are three landfall triggers: all of Omnath's effects."""
    s = omnath(cards, "Splendid Reclamation")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "graveyard"})
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Splendid Reclamation").id)
    settle(s)
    assert all(s.state.cards[f].zone == "p1:battlefield" and s.state.cards[f].tapped for f in forests)
    assert life(s) == (44, 36) and pool(s) == ["G", "R", "U", "W"]
    check(s)


def test_omnath_locus_of_rage_and_risen_reef_chain(cards):
    """A land makes a 5/5 Elemental; Risen Reef sees it enter and puts the top Forest onto the battlefield, a second landfall and a second
    Elemental (whose Reef trigger finds no land: that card goes to the hand). An Elemental dying deals 3 damage."""
    s = omnath(cards, "Omnath, Locus of Rage", "Risen Reef", "Exploration", "Lightning Bolt", on_field=False)
    put(s, "Omnath, Locus of Rage"), put(s, "Risen Reef")
    on_top(s, "Forest", "Exploration")
    land(s)
    settle(s, "Forest")
    assert field(s)["Elemental"] == 2 and field(s)["Forest"] == 2 and card(s, "Exploration").zone == "p1:hand"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[card(s, "Risen Reef").id])
    settle(s, "Bob")
    assert card(s, "Risen Reef").zone == "p1:graveyard" and s.state.players["p2"].life == 37
    check(s)
