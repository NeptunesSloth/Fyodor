"""The pod's Disa the Restless deck (tests/fixtures/soak_decks/disa_the_restless_disa_eldrazo.txt): the rest of its plan, with real Oracle text.

The core (Maskwood Nexus or Conspiracy + Entomb / Buried Alive / a discard puts creature cards onto the battlefield) is in
test_rules_pod_disa.py. This file holds what the deck does around it (the pod deck audit):

* Disa's Tarmogoyf token counts the card types among the cards in all graveyards, as they change (205.2a, 604.3).
* Avatar of Slaughter gives every creature double strike: Disa's and Old Gnawbone's combat damage triggers trigger in both combat damage steps (510.4).
* Maskwood Nexus makes every creature you control a Demon and a Dragon (205.3m, layer 4): Ardyn gives them all menace, lifelink and haste (layer 6),
  and Earthquake Dragon costs {X} less for the total mana value of all of them (601.2f).
* Mimic Vat returns the card it held to its owner's graveyard: from exile, not from the battlefield, so Disa puts it onto the battlefield.
* Altar of Dementia milling yourself: each creature card milled comes back; the sacrificed creature (from the battlefield) doesn't.
* Polyraptor dealt damage by Blasphemous Act: the token is created after the damage, so it lives (603.10 look-back, 704.5g).
* Chainer lets one creature spell be cast from the graveyard; it gains haste (it wasn't cast from the hand).
* Hierophant Bio-Titan: the table menu offers the "remove +1/+1 counters" reduction when the counters make it payable (each counter is a pick,
  122.1). Before the audit the hint counted the creatures, not the counters, and three counters on one Taurean Mauler only took {2} off.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.view import hints
from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat, until
from tests.test_rules_pod_disa import EXTRA as CORE
from tests.test_rules_pod_disa import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

EXTRA = [
    real("Ardyn, the Usurper", "{5}{B}{B}{B}", 8, "Legendary Creature — Elder Human Noble",
         "Demons you control have menace, lifelink, and haste.\nStarscourge — At the beginning of combat on your turn, exile up to one target "
         "creature card from a graveyard. If you exiled a card this way, create a token that's a copy of that card, except it's a 5/5 black Demon.",
         ("4", "4"), "B"),
    real("Earthquake Dragon", "{14}{G}", 15, "Creature — Elemental Dragon",
         "This spell costs {X} less to cast, where X is the total mana value of Dragons you control.\nFlying, trample\n{2}{G}, Sacrifice a land: "
         "Return this card from your graveyard to your hand.", ("10", "10"), "G"),
    real("Mimic Vat", "{3}", 3, "Artifact",
         "Imprint — Whenever a nontoken creature dies, you may exile that card. If you do, return each other card exiled with this artifact to "
         "its owner's graveyard.\n{3}, {T}: Create a token that's a copy of a card exiled with this artifact. It gains haste. Exile it at the "
         "beginning of the next end step."),
    real("Altar of Dementia", "{2}", 2, "Artifact", "Sacrifice a creature: Target player mills cards equal to the sacrificed creature's power."),
    real("Avatar of Slaughter", "{6}{R}{R}", 8, "Creature — Avatar", "All creatures have double strike and attack each combat if able.",
         ("8", "8"), "R"),
    real("Polyraptor", "{6}{G}{G}", 8, "Creature — Dinosaur",
         "Enrage — Whenever this creature is dealt damage, create a token that's a copy of this creature.", ("5", "5"), "G"),
    real("Blasphemous Act", "{8}{R}", 9, "Sorcery",
         "This spell costs {1} less to cast for each creature on the battlefield.\nBlasphemous Act deals 13 damage to each creature.", None, "R"),
    real("Chainer, Nightmare Adept", "{2}{B}{R}", 4, "Legendary Creature — Human Minion",
         "Discard a card: You may cast a creature spell from your graveyard this turn. Activate only once each turn.\nWhenever a nontoken "
         "creature you control enters, if you didn't cast it from your hand, it gains haste until your next turn.", ("3", "2"), "BR"),
    real("Hierophant Bio-Titan", "{10}{G}{G}", 12, "Creature — Tyranid",
         "Frenzied Metabolism — As an additional cost to cast this spell, you may remove any number of +1/+1 counters from among creatures you "
         "control. This spell costs {2} less to cast for each counter removed this way.\nReach, vigilance, ward {2}\nTitanic — This creature "
         "can't be blocked by creatures with power 2 or less.", ("12", "12"), "G"),
    real("Taurean Mauler", "{2}{R}", 3, "Creature — Shapeshifter",
         "Changeling (This card is every creature type.)\nWhenever an opponent casts a spell, you may put a +1/+1 counter on this creature.",
         ("2", "2"), "R"),
]
NAMES = [c["name"] for c in CORE + EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *CORE, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def table(cards, *, theirs=()):
    s = build(cards, [*NAMES, "Rampant Growth", "Sol Ring"], theirs)
    put(s, "Disa the Restless")
    return s


def next_turn_of_alice(s):
    """Alice's next first main phase: what she controls now has been hers since her turn began (302.6)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and not s.state.zones.get("stack"))


def attack(s, *names):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": "p2"} for n in names])
    through_combat(s)


def on_field(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == "p1:battlefield"]


def to_graveyard(s, name, pid="p1"):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "graveyard"})


def test_disas_tarmogoyf_token_counts_the_card_types_in_every_graveyard(cards):
    s = table(cards, theirs=["Lightning Bolt"])
    next_turn_of_alice(s)
    for name in ("Sol Ring", "Rampant Growth", "Forest", "Polyraptor"):  # (anything the opening hand drew: out of the graveyards)
        if zone_of(s, name) != "p1:library":
            act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "library"})
    attack(s, "Disa the Restless")
    (goyf,) = on_field(s, "Tarmogoyf")
    assert pt(s, "Tarmogoyf") == (0, 1)
    to_graveyard(s, "Sol Ring")
    to_graveyard(s, "Lightning Bolt", "p2")  # (an opponent's graveyard counts too)
    to_graveyard(s, "Rampant Growth")
    assert pt(s, "Tarmogoyf") == (3, 4)
    to_graveyard(s, "Forest")
    to_graveyard(s, "Polyraptor")
    assert pt(s, "Tarmogoyf") == (5, 6)
    act(s, "p2", type="move", card_ids=[card_named(s, "Lightning Bolt", "p2").id], to={"zone": "exile"})
    assert pt(s, "Tarmogoyf") == (4, 5)
    check(s)


def test_avatar_of_slaughter_double_strike_triggers_disa_and_old_gnawbone_in_each_damage_step(cards):
    s = table(cards)
    put(s, "Old Gnawbone")
    next_turn_of_alice(s)
    put(s, "Avatar of Slaughter")  # (summoning-sick: it doesn't have to attack)
    attack(s, "Disa the Restless", "Old Gnawbone")
    assert s.state.players["p2"].life == 40 - 2 * (5 + 7)
    assert len(on_field(s, "Tarmogoyf")) == 2 and len(on_field(s, "Treasure")) == 2 * (5 + 7)
    check(s)


def test_maskwood_nexus_makes_every_creature_a_demon_for_ardyn_and_a_dragon_for_earthquake_dragon(cards):
    s = table(cards)
    ardyn, gnawbone = put(s, "Ardyn, the Usurper"), put(s, "Old Gnawbone")
    from app.rules.plan import Plan

    keywords = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords  # noqa: E731
    assert "haste" not in keywords(gnawbone)
    put(s, "Maskwood Nexus")
    for c in (card_named(s, "Disa the Restless"), ardyn, gnawbone):
        assert {"menace", "lifelink", "haste"} <= set(keywords(c))
    # Dragons you control: Disa (5) + Ardyn (8) + Old Gnawbone (7) = 20 ≥ 14, so Earthquake Dragon costs {G}
    to_hand(s, "Earthquake Dragon")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Earthquake Dragon").id, targets=[])
    settle(s)
    assert zone_of(s, "Earthquake Dragon") == "p1:battlefield"
    check(s)


def test_mimic_vat_sends_the_card_it_held_to_the_graveyard_from_exile_and_disa_puts_it_onto_the_battlefield(cards):
    s = table(cards)
    put(s, "Maskwood Nexus")
    put(s, "Mimic Vat")
    gnawbone, mammoth = put(s, "Old Gnawbone"), put(s, "Aggressive Mammoth")
    for victim in (gnawbone, mammoth):
        to_hand(s, "Terminate")
        mana(s, B=1, R=1)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Terminate").id, targets=[victim.id])
        until(s, lambda s: s.state.rules.decision is not None)
        assert s.state.rules.decision.prompt == "Mimic Vat: Exile, return each other card exiled with it to its owner's graveyard?"
        settle(s, "Yes")  # (Mimic Vat: exile it)
    assert zone_of(s, "Aggressive Mammoth") == "p1:exile"
    assert zone_of(s, "Old Gnawbone") == "p1:battlefield"
    check(s)


def test_altar_of_dementia_milling_yourself_puts_the_creature_cards_onto_the_battlefield(cards):
    s = table(cards)
    put(s, "Maskwood Nexus")
    altar, ghalta = put(s, "Altar of Dementia"), put(s, "Ghalta, Primal Hunger")
    library = [s.state.cards[c] for c in s.state.zones["p1:library"][:12]]
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, targets=["p1"], sources=[],
        cost_choices=[{"component": 0, "cards": [ghalta.id]}])
    settle(s)
    assert zone_of(s, "Ghalta, Primal Hunger") == "p1:graveyard"  # (it died: from the battlefield)
    milled_creatures = [c for c in library if "Creature" in (s.cards.resolve(c.name) or {}).get("type_line", "")]
    assert milled_creatures and all(s.state.cards[c.id].zone == "p1:battlefield" for c in milled_creatures)
    assert all(s.state.cards[c.id].zone == "p1:graveyard" for c in library if c not in milled_creatures)
    check(s)


def test_polyraptor_dealt_damage_by_blasphemous_act_leaves_a_token_that_lives(cards):
    s = table(cards, theirs=["Grizzly Bears"])
    put(s, "Polyraptor")
    put(s, "Grizzly Bears", "p2")
    mana(s, R=1, C=5)  # (three creatures: {8}{R} costs {5}{R})
    to_hand(s, "Blasphemous Act")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Blasphemous Act").id, targets=[])
    settle(s)
    assert zone_of(s, "Polyraptor") == "p1:graveyard" and zone_of(s, "Disa the Restless") != "p1:battlefield"
    assert len(on_field(s, "Polyraptor")) == 1 and pt(s, "Polyraptor") == (5, 5)
    check(s)


def test_chainer_casts_one_creature_spell_from_the_graveyard_and_it_gains_haste(cards):
    s = table(cards)
    chainer = put(s, "Chainer, Nightmare Adept")
    to_graveyard(s, "Old Gnawbone")
    to_graveyard(s, "Aggressive Mammoth")
    to_hand(s, "Sol Ring")
    act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0, targets=[], sources=[])
    settle(s, "Sol Ring")
    mana(s, G=2, C=5)
    assert card_named(s, "Old Gnawbone").id in hints(s.state, "p1", s.cards)["castable"]
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Old Gnawbone").id, targets=[])
    settle(s)
    from app.rules.plan import Plan

    gnawbone = s.state.cards[card_named(s, "Old Gnawbone").id]
    assert gnawbone.zone == "p1:battlefield" and "haste" in Plan(s.state, "p1", s.cards, None).ch(gnawbone).keywords
    mana(s, G=3, C=3)
    assert card_named(s, "Aggressive Mammoth").id not in hints(s.state, "p1", s.cards)["castable"]  # (one creature spell)
    check(s)


def test_hierophant_bio_titan_is_offered_when_the_counters_on_one_creature_make_it_payable(cards):
    """{10}{G}{G} with {G}{G}{C}{C}{C}{C} floating: two +1/+1 counters on Taurean Mauler take {4} off (not enough), three take {6} off ({4}{G}{G})."""
    s = table(cards)
    mauler = put(s, "Taurean Mauler")
    act(s, "p1", type="counter", card_ids=[mauler.id], kind="+1/+1", delta=2)
    titan = to_hand(s, "Hierophant Bio-Titan")
    mana(s, G=2, C=4)
    offered = lambda: [o["id"] for o in hints(s.state, "p1", s.cards).get("optional_costs", {}).get(titan.id, [])]  # noqa: E731
    assert offered() == [] and titan.id not in hints(s.state, "p1", s.cards)["castable"]
    act(s, "p1", type="counter", card_ids=[mauler.id], kind="+1/+1", delta=1)
    assert offered() == [f"{titan.id}:reduce"]
    act(s, "p1", type="cast_spell", card_id=titan.id, optional_costs=[f"{titan.id}:reduce"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)
    assert zone_of(s, "Hierophant Bio-Titan") == "p1:battlefield" and not s.state.cards[mauler.id].counters.get("+1/+1")
    check(s)
