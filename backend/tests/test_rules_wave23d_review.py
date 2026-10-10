"""Wave 23D review: gift, exploit, saddle and discard causes against the rest of the engine (CR 2026-09-25). Real Oracle text;
every scenario checks the replay and a save and a load.

* 702.174k: a promised gift is read as "kicked" for the spell's own text only; "Whenever you cast a kicked spell" (702.33d) is not
  about gifts.
* 707.10: a copy of a spell copies its additional costs: the copy's gift is promised to the same opponent.
* 702.171a: saddling taps creatures to pay a saddle cost; "can't crew Vehicles" (702.122d) doesn't stop a creature from saddling.
* 701.9a / 616.1: a discard put onto the battlefield instead is still a discard; with Rest in Peace the card's owner chooses which
  replacement applies.
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand, zone_of

CARDS = [
    ("Roost of Drakes", "{U}", "Enchantment", None, None,
     "Kicker {2}{U} (You may pay an additional {2}{U} as you cast this spell.)\nWhen this enchantment enters, if it was kicked, create a 2/2 "
     "blue Drake creature token with flying.\nWhenever you cast a kicked spell, create a 2/2 blue Drake creature token with flying."),
    ("Wear Down", "{1}{G}", "Sorcery", None, None,
     "Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\n"
     "Destroy target artifact or enchantment. If the gift was promised, instead destroy two target artifacts and/or enchantments."),
    ("Twincast", "{U}{U}", "Instant", None, None, "Copy target instant or sorcery spell. You may choose new targets for the copy."),
    ("Rest in Peace", "{1}{W}", "Enchantment", None, None,
     "When this enchantment enters, exile all graveyards.\nIf a card or token would be put into a graveyard from anywhere, exile it instead."),
    ("Obstinate Baloth", "{2}{G}{G}", "Creature — Beast", "4", "4",
     "When this creature enters, you gain 4 life.\nIf a spell or ability an opponent controls causes you to discard this card, put it onto "
     "the battlefield instead of putting it into your graveyard."),
    ("Megrim", "{2}{B}", "Enchantment", None, None,
     "Whenever an opponent discards a card, this enchantment deals 2 damage to that player."),
    ("Mind Rot", "{2}{B}", "Sorcery", None, None, "Target player discards two cards."),
    ("Wheel of Fortune", "{2}{R}", "Sorcery", None, None, "Each player discards their hand, then draws seven cards."),
    ("Bridled Bighorn", "{3}{W}", "Creature — Sheep Mount", "3", "4",
     "Vigilance\nWhenever this creature attacks while saddled, create a 1/1 white Sheep creature token.\nSaddle 2 (Tap any number of other "
     "creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)"),
    ("Revoke Privileges", "{2}{W}", "Enchantment — Aura", None, None,
     "Enchant creature\nEnchanted creature can't attack, block, or crew Vehicles."),
    ("Colonel Autumn", "{1}{W}{B}", "Legendary Creature — Human Soldier", "2", "3",
     "Lifelink\nExploit (When this creature enters, you may sacrifice a creature.)\nOther legendary creatures you control have exploit.\n"
     "Whenever a creature you control exploits a creature, put a +1/+1 counter on each creature you control."),
    ("Sidisi, Undead Vizier", "{3}{B}{B}", "Legendary Creature — Zombie Snake", "4", "6",
     "Deathtouch\nExploit (When this creature enters, you may sacrifice a creature.)\n"
     "When Sidisi exploits a creature, you may search your library for a card, put it into your hand, then shuffle."),
    ("Fell Stinger", "{2}{B}", "Creature — Zombie Scorpion", "3", "2",
     "Deathtouch\nExploit (When this creature enters, you may sacrifice a creature.)\n"
     "When this creature exploits a creature, target player draws two cards and loses 2 life."),
    ("Unsummon", "{U}", "Instant", None, None, "Return target creature to its owner's hand."),
    ("Reckless Velocitaur", "{3}{R}", "Creature — Minotaur Pilot", "3", "3",
     "Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gets +2/+0 and gains trample "
     "until end of turn."),
    ("Metrognome", "{4}", "Artifact", None, None,
     "When a spell or ability an opponent controls causes you to discard this card, create four 1/1 colorless Gnome artifact creature tokens.\n"
     "{4}, {T}: Create a 1/1 colorless Gnome artifact creature token."),
    ("Probe Legend", "{B}", "Legendary Creature — Human", "1", "1", ""),
    ("Probe Relic", "{1}", "Artifact", None, None, "{T}: Add {C}."),
    ("Probe Totem", "{1}", "Artifact", None, None, "{T}: Add {C}."),
    ("Probe Giant", "{W}", "Creature — Giant", "5", "5", ""),
    ("Probe Soldier", "{W}", "Creature — Human Soldier", "2", "2", ""),
]
EXTRA = [card(n, set_code="t23r", number=f"R{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=[], color_identity=[], oracle_text=text, **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name]


@pytest.mark.parametrize("gift", [True, False])
def test_a_promised_gift_is_not_a_kicked_spell_for_whenever_you_cast_a_kicked_spell(cards, gift):
    s = build(cards, ["Roost of Drakes", "Wear Down"], ["Probe Relic", "Probe Totem"])
    put(s, "Roost of Drakes")
    relic, totem = put(s, "Probe Relic", "p2"), put(s, "Probe Totem", "p2")
    c = to_hand(s, "Wear Down")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"] if gift else [],
        targets=[relic.id, totem.id][: 2 if gift else 1], target_counts=[0, 2] if gift else [1, 0])
    answer(s)
    assert not tokens(s, "Drake")
    assert zone_of(s, "Probe Totem", "p2") == ("p2:graveyard" if gift else "p2:battlefield")
    check(s)


def test_a_copy_of_a_gift_spell_gives_the_gift_again_to_the_same_opponent(cards):
    """707.10: the copy copies the decision to pay the gift cost (the chosen opponent)."""
    s = build(cards, ["Wear Down", "Twincast"], ["Probe Relic", "Probe Totem"])
    relic, totem = put(s, "Probe Relic", "p2"), put(s, "Probe Totem", "p2")
    c = to_hand(s, "Wear Down")
    tw = to_hand(s, "Twincast")
    mana(s, G=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bob = hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"], targets=[relic.id, totem.id], target_counts=[0, 2])
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=tw.id, targets=[c.id])
    answer(s)  # (the copy keeps the targets and destroys both: the original then has no legal target and gives no gift, 702.174j)
    assert hand(s, "p2") == bob + 1 and zone_of(s, "Probe Totem", "p2") == "p2:graveyard"
    check(s)


def test_a_creature_that_cant_crew_vehicles_can_still_saddle(cards):
    s = build(cards, ["Bridled Bighorn", "Probe Soldier", "Revoke Privileges"])
    mount = put(s, "Bridled Bighorn")
    soldier = put(s, "Probe Soldier")
    aura = to_hand(s, "Revoke Privileges")
    mana(s, W=3)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[soldier.id])
    answer(s)
    from tests.test_rules_wave23d_triggers import saddle_index

    act(s, "p1", type="activate_ability", card_id=mount.id, ability=saddle_index(s, "Bridled Bighorn"), crew=[soldier.id])
    answer(s)
    assert s.state.cards[soldier.id].tapped
    assert any(f.kind == "saddled" for f in s.state.rules.turn_log.facts)
    check(s)


def opponent_discards(cards, spell, held=("Obstinate Baloth",), board=()):
    """Bob casts ``spell`` on his turn; Alice holds ``held``, controls ``board``."""
    from tests.test_rules_conditionals import until

    s = build(cards, [*held, *board], [spell, "Megrim"])
    for n in held:
        to_hand(s, n)
    for n in board:
        put(s, n)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p2", limit=300)
    to_hand(s, spell, "p2")
    mana(s, "p2", B=3, R=3)
    return s


def test_a_discard_put_onto_the_battlefield_instead_is_still_a_discard(cards):
    """Megrim (Bob's) sees Alice discard Obstinate Baloth to his Mind Rot although it enters instead (701.9a)."""
    s = opponent_discards(cards, "Mind Rot")
    put(s, "Megrim", "p2")
    assert hand(s) == 1
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Rot", "p2").id, targets=["p1"])
    answer(s)
    assert zone_of(s, "Obstinate Baloth") == "p1:battlefield"
    assert life(s) == 40 + 4 - 2
    check(s)


def test_a_wheel_puts_the_opponents_baloth_onto_the_battlefield_and_not_the_casters(cards):
    s = build(cards, ["Obstinate Baloth"], ["Wheel of Fortune", "Obstinate Baloth"])
    to_hand(s, "Obstinate Baloth")
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p2", limit=300)
    to_hand(s, "Wheel of Fortune", "p2")
    to_hand(s, "Obstinate Baloth", "p2")
    mana(s, "p2", R=3)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Wheel of Fortune", "p2").id)
    answer(s)
    assert zone_of(s, "Obstinate Baloth") == "p1:battlefield" and zone_of(s, "Obstinate Baloth", "p2") == "p2:graveyard"
    check(s)


def test_colonel_autumn_grants_exploit_and_sees_it(cards):
    """A legendary creature entering under Colonel Autumn has exploit (613.1f); its exploit is "a creature you control exploits"."""
    s = build(cards, ["Colonel Autumn", "Probe Legend", "Probe Soldier", "Probe Giant"])
    put(s, "Colonel Autumn")
    soldier = put(s, "Probe Soldier")
    put(s, "Probe Giant")
    sidisi = to_hand(s, "Probe Legend")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=sidisi.id)
    for _ in range(20):  # (resolve: yes to exploit, sacrifice the soldier; the save mid-decision is replayed)
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        s = reloaded(s)
        d = s.state.rules.decision
        ids = [o.id for o in d.options]
        pick = soldier.id if soldier.id in ids else "yes" if "yes" in ids else "no" if "no" in ids and d.kind == "confirm" else ids[: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick if isinstance(pick, list) else [pick])
    assert zone_of(s, "Probe Soldier") == "p1:graveyard"
    counters = s.state.cards[card_named(s, "Probe Giant").id].counters
    assert counters.get("+1/+1") == 1
    check(s)


def test_a_baloth_discarded_by_an_opponent_under_rest_in_peace_asks_its_owner(cards):
    """616.1: Rest in Peace and Obstinate Baloth both replace the discard (neither is a self-replacement effect, 614.15): the owner
    chooses."""
    s = opponent_discards(cards, "Mind Rot", board=("Rest in Peace",))
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Rot", "p2").id, targets=["p1"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        labels = " | ".join(o.label for o in d.options)
        if "xile" in labels and "attlefield" in labels:
            pick = next(o.id for o in d.options if "xile" in o.label)
        else:
            pick = d.options[0].id
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert zone_of(s, "Obstinate Baloth") == "p1:exile"
    check(s)


def test_an_exploiter_gone_before_its_exploit_resolves_still_sacrifices_but_gets_no_bonus(cards):
    """702.110b: the sacrifice is still made as the exploit ability resolves, but Fell Stinger, back in the hand, isn't there to see it."""
    s = build(cards, ["Fell Stinger", "Unsummon", "Probe Soldier"])
    soldier = put(s, "Probe Soldier")
    stinger, unsummon = to_hand(s, "Fell Stinger"), to_hand(s, "Unsummon")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, B=3, U=1)
    act(s, "p1", type="cast_spell", card_id=stinger.id)
    act(s, "p1", type="pass_priority")  # (Fell Stinger resolves; its exploit trigger goes on the stack)
    assert zone_of(s, "Fell Stinger") == "p1:battlefield" and s.state.zones.get("stack")
    act(s, "p1", type="cast_spell", card_id=unsummon.id, targets=[card_named(s, "Fell Stinger").id])
    life_then, hand_then = life(s), hand(s)
    answer(s, "yes", soldier.id)
    assert zone_of(s, "Fell Stinger") == "p1:hand" and zone_of(s, "Probe Soldier") == "p1:graveyard"
    assert life(s) == life_then and life(s, "p2") == 40 and hand(s) == hand_then + 1  # (Fell Stinger only: no one drew)
    check(s)


def test_saddling_asks_which_creatures_and_survives_a_save(cards):
    s = build(cards, ["Bridled Bighorn", "Probe Soldier"])
    mount, soldier = put(s, "Bridled Bighorn"), put(s, "Probe Soldier")
    from tests.test_rules_wave23d_triggers import saddle_index

    act(s, "p1", type="activate_ability", card_id=mount.id, ability=saddle_index(s, "Bridled Bighorn"))
    s = reloaded(s)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and [o.id for o in d.options] == [soldier.id]  # (not the Mount itself: "other", 702.171a)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[soldier.id])
    answer(s)
    assert s.state.cards[soldier.id].tapped and any(f.kind == "saddled" for f in s.state.rules.turn_log.facts)
    check(s)


def test_metrognome_discarded_into_exile_by_rest_in_peace_still_triggers(cards):
    """113.6k: the discard trigger works from the zone the card went to; Rest in Peace exiled it, but it was discarded (701.9a)."""
    s = opponent_discards(cards, "Mind Rot", held=("Metrognome",), board=("Rest in Peace",))
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Rot", "p2").id, targets=["p1"])
    answer(s)
    assert zone_of(s, "Metrognome") == "p1:exile" and len(tokens(s, "Gnome")) == 4
    check(s)


def test_a_creature_that_saddles_a_mount_pumps_that_mount(cards):
    """Reckless Velocitaur's "saddles a Mount" half (702.171c): the Mount gets +2/+0 and trample, not the Velocitaur."""
    from app.rules.plan import Plan
    from tests.test_rules_wave23d_triggers import saddle_index
    from tests.wave9c_kit import pt

    s = build(cards, ["Bridled Bighorn", "Reckless Velocitaur"])
    mount, pilot = put(s, "Bridled Bighorn"), put(s, "Reckless Velocitaur")
    act(s, "p1", type="activate_ability", card_id=mount.id, ability=saddle_index(s, "Bridled Bighorn"), crew=[pilot.id])
    answer(s)
    assert pt(s, "Bridled Bighorn") == (5, 4) and pt(s, "Reckless Velocitaur") == (3, 3)
    assert "trample" in {k.lower() for k in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[mount.id]).keywords}
    check(s)


def test_a_gift_promised_to_a_player_who_left_is_not_given_and_the_promise_still_counts(cards):
    """Three players: the caster names Cy (asked, then a save and a load); Cy concedes with the spell on the stack (800.4a): no one
    gets the gift, and the spell still does what a promised gift adds (702.174k)."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    def side(commander, names):
        return deck(cards, commander, [*((1, n) for n in names), (10, "Island")])

    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=side("Krenko, Mob Boss", ["Wear Down"])),
                                     PlayerSetup("Bob", cards=side("Atraxa, Praetors' Voice", ["Probe Relic", "Probe Totem"])),
                                     PlayerSetup("Cy", cards=side("Krenko, Mob Boss", []))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    relic, totem = put(s, "Probe Relic", "p2"), put(s, "Probe Totem", "p2")
    c = to_hand(s, "Wear Down")
    mana(s, G=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:gift"], targets=[relic.id, totem.id], target_counts=[0, 2])
    s = reloaded(s)
    d = s.state.rules.decision
    assert d.kind == "choose_one" and {o.id for o in d.options} == {"p2", "p3"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    assert s.state.rules.payments[s.state.rules.stack[c.id].source_object].gift_to == "p3"
    bob = hand(s, "p2")
    act(s, "p3", type="concede")
    answer(s)
    assert hand(s, "p2") == bob and zone_of(s, "Probe Totem", "p2") == "p2:graveyard"
    check(s)
