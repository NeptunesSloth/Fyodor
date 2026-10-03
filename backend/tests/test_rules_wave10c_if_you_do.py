"""Wave 10C: the "if you do" family, researched against CR 2026-09-25.

* 701.17a / 701.17c: to mill is to put the top cards of a library into its owner's graveyard; "cards milled this way" are the
  cards that instruction put there (a card a replacement sent elsewhere was not milled).
* 608.2c: instructions are followed in order; "If you don't" asks whether the optional instruction before it was done: a card
  picked from among the milled cards / the cards looked at that reached the hand.
* 120.3 / 120.4: "If a [player / Dragon / nonred permanent] is dealt damage this way" reads the damage actually dealt (after
  prevention), judging the recipient as it was when the damage was dealt (608.2h).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Ainok Wayfarer', set_code='tst', number='W01', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Dog Scout', oracle_text="When this creature enters, mill three cards. You may put a land card from among them into your hand. If you don't, put a +1/+1 counter on this creature. (To mill three cards, put the top three cards of your library into your graveyard.)", power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Mill']),  # noqa: E501
    card('Wasteful Harvest', set_code='tst', number='W02', mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text='Mill five cards. You may put a permanent card from among the cards milled this way into your hand. (To mill a card, put the top card of your library into your graveyard.)', colors=['G'], color_identity=['G'], keywords=['Mill']),  # noqa: E501
    card('Leyline Dowser', set_code='tst', number='W03', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='{1}, {T}: Mill a card. You may put an instant or sorcery card milled this way into your hand.\nTap an untapped legendary creature you control: Untap this artifact.', keywords=['Mill']),  # noqa: E501
    card('Adventure Awaits', set_code='tst', number='W04', mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text="Look at the top five cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in a random order. If you didn't put a card into your hand this way, draw a card.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Inscribed Tablet', set_code='tst', number='W05', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text="{1}, {T}, Sacrifice this artifact: Reveal the top five cards of your library. Put a land card from among them into your hand and the rest on the bottom of your library in a random order. If you didn't put a card into your hand this way, draw a card."),  # noqa: E501
    card('Play with Fire', set_code='tst', number='D01', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Play with Fire deals 2 damage to any target. If a player is dealt damage this way, scry 1. (Look at the top card of your library. You may put that card on the bottom.)', colors=['R'], color_identity=['R'], keywords=['Scry']),  # noqa: E501
    card('Provoke the Trolls', set_code='tst', number='D02', mana_cost='{3}{R}', cmc=4.0, type_line='Instant', oracle_text='Provoke the Trolls deals 3 damage to any target. If a creature is dealt damage this way, it gets +5/+0 until end of turn.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Redcap Melee', set_code='tst', number='D03', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Redcap Melee deals 4 damage to target creature or planeswalker. If a nonred permanent is dealt damage this way, you sacrifice a land.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('The Black Arrow', set_code='tst', number='D04', mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact — Equipment', oracle_text='Flash\nWhen The Black Arrow enters, it deals 1 damage to any target. If a Dragon is dealt damage this way, destroy it.\nEquipped creature gets +1/+1 and has reach.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)', keywords=['Equip', 'Flash']),  # noqa: E501
    card('Silver Bolt', set_code='tst', number='D05', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text='{3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature. If a Werewolf is dealt damage this way, destroy it.'),  # noqa: E501
    card('Marauding Raptor', set_code='tst', number='D06', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Dinosaur', oracle_text='Creature spells you cast cost {1} less to cast.\nWhenever another creature you control enters, this creature deals 2 damage to it. If a Dinosaur is dealt damage this way, this creature gets +2/+0 until end of turn.', power='2', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Colossadactyl', set_code='tst', number='D08', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Dinosaur', oracle_text='Reach, trample', power='4', toughness='5', colors=['G'], color_identity=['G'], keywords=['Reach', 'Trample']),  # noqa: E501
    card('Mending Hands', set_code='tst', number='D07', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Prevent the next 4 damage that would be dealt to any target this turn.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Vivien on the Hunt', set_code='tst', number='W06', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Legendary Planeswalker — Vivien', oracle_text="+2: You may sacrifice a creature. If you do, search your library for a creature card with mana value equal to 1 plus the sacrificed creature's mana value, put it onto the battlefield, then shuffle.\n+1: Mill five cards, then put any number of creature cards milled this way into your hand.\n−1: Create a 4/4 green Rhino Warrior creature token.", loyalty='4', colors=['G'], color_identity=['G'], keywords=['Mill']),  # noqa: E501
]
NAMES = ["Ainok Wayfarer", "Wasteful Harvest", "Leyline Dowser", "Adventure Awaits", "Inscribed Tablet", "Play with Fire",
         "Provoke the Trolls", "Redcap Melee", "The Black Arrow", "Silver Bolt", "Marauding Raptor"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def in_zone(s, name, zone, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:{zone}"]


def counters(s, name):
    return find(s, name).counters.get("+1/+1", 0)


def cast(s, name, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    pass_until_stack_empty(s)


def top_of_library(s, *names):
    """Put these cards on top of Alice's library, the first named ends up on top."""
    for n in reversed(names):
        put(s, n, "library", position="top")


def test_mill_then_pick_a_land_from_among_them_puts_it_in_hand(cards):
    s = build(cards, p1=("Ainok Wayfarer",))
    top_of_library(s, "Forest")
    cast(s, "Ainok Wayfarer", G=2)
    answer(s)
    assert len(in_zone(s, "Forest", "graveyard")) == 2 and len(in_zone(s, "Forest", "hand")) == 1  # three milled, one taken
    assert counters(s, "Ainok Wayfarer") == 0  # "If you don't" is false: a card reached the hand
    roundtrip(s)


def test_if_you_dont_pick_one_the_counter_goes_on(cards):
    s = build(cards, p1=("Ainok Wayfarer",))
    cast(s, "Ainok Wayfarer", G=2)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0  # "You may": nothing is taken
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert len(in_zone(s, "Forest", "graveyard")) == 3 and not in_zone(s, "Forest", "hand")
    assert counters(s, "Ainok Wayfarer") == 1
    roundtrip(s)


def test_no_land_among_the_milled_cards_gives_the_counter(cards):
    s = build(cards, p1=("Ainok Wayfarer", "Sol Ring", "Arcane Signet", "Counterspell"))
    top_of_library(s, "Sol Ring", "Arcane Signet", "Counterspell")
    cast(s, "Ainok Wayfarer", G=2)
    answer(s)
    assert len(in_zone(s, "Sol Ring", "graveyard")) == 1 and not in_zone(s, "Forest", "graveyard")  # no land was milled
    assert counters(s, "Ainok Wayfarer") == 1  # nothing to put into the hand: "If you don't" is true
    roundtrip(s)


def test_only_the_cards_this_mill_put_there_can_be_picked(cards):
    s = build(cards, p1=("Wasteful Harvest", "Sol Ring"))
    put(s, "Sol Ring", "graveyard")  # already in the graveyard: not "milled this way"
    cast(s, "Wasteful Harvest", G=3)
    d = s.state.rules.decision
    assert d is not None
    ids = {o.card_id for o in d.options}
    assert find(s, "Sol Ring").id not in ids and len(ids) == 5  # the five Forests it milled
    assert d.max_choices == 1 and d.min_choices == 0
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert len(in_zone(s, "Forest", "hand")) == 1 and len(in_zone(s, "Forest", "graveyard")) == 4
    roundtrip(s)


def test_declining_the_pick_leaves_every_milled_card_in_the_graveyard(cards):
    s = build(cards, p1=("Wasteful Harvest",))
    cast(s, "Wasteful Harvest", G=3)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 5
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert len(in_zone(s, "Forest", "graveyard")) == 5
    roundtrip(s)


def test_the_selector_filters_what_may_be_picked(cards):
    s = build(cards, p1=("Leyline Dowser", "Counterspell", "Sol Ring"))
    dowser = put(s, "Leyline Dowser", "battlefield")
    top_of_library(s, "Counterspell")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=dowser.id, ability=0)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and [o.card_id for o in d.options] == [find(s, "Counterspell").id]  # an instant: offered
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert in_zone(s, "Counterspell", "hand")
    roundtrip(s)


def test_a_milled_card_that_is_not_an_instant_or_sorcery_gives_no_choice(cards):
    s = build(cards, p1=("Leyline Dowser",))
    dowser = put(s, "Leyline Dowser", "battlefield")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=dowser.id, ability=0)
    answer(s)
    assert len(in_zone(s, "Forest", "graveyard")) == 1 and not in_zone(s, "Forest", "hand")
    roundtrip(s)


def test_any_number_of_the_milled_creature_cards(cards):
    s = build(cards, p1=("Vivien on the Hunt", "Grizzly Bears", "Sol Ring"))
    bears = put(s, "Grizzly Bears", "library", position="top")
    cast(s, "Vivien on the Hunt", G=6)
    act(s, "p1", type="activate_ability", card_id=find(s, "Vivien on the Hunt").id, ability=1)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and [o.card_id for o in d.options] == [bears.id] and d.min_choices == 0
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:hand"
    roundtrip(s)


def test_look_pick_and_if_you_didnt_put_a_card_into_your_hand_this_way(cards):
    s = build(cards, p1=("Adventure Awaits", "Grizzly Bears"))
    cast(s, "Adventure Awaits", G=2)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])  # no creature among the five: nothing taken
    answer(s)
    assert len(in_zone(s, "Forest", "hand")) == 1  # "draw a card"
    roundtrip(s)


def test_look_pick_takes_a_creature_so_no_draw(cards):
    s = build(cards, p1=("Adventure Awaits", "Grizzly Bears"))
    bears = put(s, "Grizzly Bears", "library", position="top")
    cast(s, "Adventure Awaits", G=2)
    answer(s, pick=bears.id)
    assert s.state.cards[bears.id].zone == "p1:hand" and not in_zone(s, "Forest", "hand")
    roundtrip(s)


def test_mandatory_pick_with_nothing_to_pick_draws(cards):
    s = build(cards, p1=("Inscribed Tablet", "Sol Ring", "Arcane Signet", "Counterspell", "Grizzly Bears", "Lightning Bolt"))
    tablet = put(s, "Inscribed Tablet", "battlefield")
    top_of_library(s, "Sol Ring", "Arcane Signet", "Counterspell", "Grizzly Bears", "Lightning Bolt")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=tablet.id, ability=0)
    answer(s)
    assert len(in_zone(s, "Forest", "hand")) == 1  # no land among the five revealed: draw a card
    roundtrip(s)


# -- "If a [player / creature / Dragon / nonred permanent] is dealt damage this way" -----------------------------------------
def token(s, name, type_line, pt, pid="p2"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": ""})
    return find(s, name, pid)


def settle(s, target=None, limit=30):
    """Resolve everything; a trigger's target is ``target``, any other decision is answered with its first minimal choice.
    Returns the prompts of the decisions that were asked."""
    asked: list[str] = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
            ids = [o.id for o in d.options]
            if d.prompt.endswith("choose a target") and target in ids:
                chosen = [target]
            else:
                chosen = ids[: max(1, d.min_choices)] if d.min_choices else []
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen[:max(1, d.max_choices or 1)] if chosen else [])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def cast_at(s, name, targets, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=targets)
    return settle(s)


def cast_at_self(s, name, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return settle(s)


def pt(s, card):
    from tests.test_rules_attachments import ch

    return ch(s, card).pt


def scried(asked):
    return any("scry" in p.lower() for p in asked)


def test_player_dealt_damage_this_way_scries(cards):
    s = build(cards, p1=("Play with Fire",))
    asked = cast_at(s, "Play with Fire", ["p2"], R=1)
    assert s.state.players["p2"].life == 38
    assert scried(asked)
    roundtrip(s)


def test_a_creature_dealt_damage_is_not_a_player_so_no_scry(cards):
    s = build(cards, p1=("Play with Fire",))
    brute = token(s, "Brute", "Token Creature — Test", "4/4")
    asked = cast_at(s, "Play with Fire", [brute.id], R=1)
    assert s.state.cards[brute.id].damage == 2 and not scried(asked)
    roundtrip(s)


def test_creature_dealt_damage_gets_the_bonus(cards):
    s = build(cards, p1=("Provoke the Trolls",))
    brute = token(s, "Brute", "Token Creature — Test", "2/5")
    cast_at(s, "Provoke the Trolls", [brute.id], R=4)
    assert pt(s, brute) == (7, 5)  # +5/+0 until end of turn
    roundtrip(s)


def test_a_player_dealt_damage_by_the_same_spell_gets_no_bonus(cards):
    s = build(cards, p1=("Provoke the Trolls",))
    brute = token(s, "Brute", "Token Creature — Test", "2/5", pid="p1")
    cast_at(s, "Provoke the Trolls", ["p2"], R=4)
    assert s.state.players["p2"].life == 37 and pt(s, brute) == (2, 5)
    roundtrip(s)


def test_damage_that_is_all_prevented_deals_none_so_the_condition_is_false(cards):
    s = build(cards, p1=("Provoke the Trolls", "Mending Hands"))
    brute = token(s, "Brute", "Token Creature — Test", "2/5")
    cast_at(s, "Mending Hands", [brute.id], W=1)
    cast_at(s, "Provoke the Trolls", [brute.id], R=4)
    assert s.state.cards[brute.id].damage == 0 and pt(s, brute) == (2, 5)  # 615.1: prevented damage was never dealt
    roundtrip(s)


def test_nonred_permanent_dealt_damage_makes_you_sacrifice_a_land(cards):
    s = build(cards, p1=("Redcap Melee",))
    brute = token(s, "Brute", "Token Creature — Test", "2/5")
    put(s, "Forest", "battlefield")
    cast_at(s, "Redcap Melee", [brute.id], R=1)
    assert s.state.cards[brute.id].damage == 4
    assert not [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield"]  # the one land sacrificed
    roundtrip(s)


def test_a_red_permanent_dealt_damage_costs_no_land(cards):
    s = build(cards, p1=("Redcap Melee",), p2=("Abbot of Keral Keep",))
    abbot = put(s, "Abbot of Keral Keep", "battlefield", pid="p2")
    put(s, "Forest", "battlefield")
    cast_at(s, "Redcap Melee", [abbot.id], R=1)
    assert s.state.cards[abbot.id].zone == "p2:graveyard"  # it was red when the damage was dealt (608.2h)
    assert [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield"]
    roundtrip(s)


def test_the_black_arrow_destroys_a_dragon_it_damages_not_itself(cards):
    s = build(cards, p1=("The Black Arrow",))
    dragon = token(s, "Drake", "Token Creature — Dragon", "4/4")
    c = find(s, "The Black Arrow")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, target=dragon.id)
    assert dragon.id not in s.state.cards  # a 4/4 token that took 1 damage: only the destroy removes it
    assert s.state.cards[c.id].zone == "p1:battlefield"
    roundtrip(s)


def test_the_black_arrow_leaves_a_non_dragon_alone(cards):
    s = build(cards, p1=("The Black Arrow",))
    brute = token(s, "Brute", "Token Creature — Test", "4/4")
    c = find(s, "The Black Arrow")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, target=brute.id)
    assert s.state.cards[brute.id].zone == "p2:battlefield" and s.state.cards[brute.id].damage == 1
    roundtrip(s)


def test_silver_bolt_destroys_a_werewolf_it_damages(cards):
    s = build(cards, p1=("Silver Bolt",))
    wolf = token(s, "Wolf", "Token Creature — Werewolf", "5/5")
    bolt = put(s, "Silver Bolt", "battlefield")
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=0, targets=[wolf.id])
    settle(s)
    assert wolf.id not in s.state.cards  # (5 toughness, 3 damage: only the destroy removes it)
    roundtrip(s)


def test_marauding_raptor_grows_only_when_a_dinosaur_enters(cards):
    s = build(cards, p1=("Marauding Raptor", "Grizzly Bears", "Colossadactyl"))
    raptor = put(s, "Marauding Raptor", "battlefield")
    cast_at_self(s, "Grizzly Bears", G=2)
    assert find(s, "Grizzly Bears").zone == "p1:graveyard"  # dealt 2 damage by the trigger
    assert pt(s, raptor) == (2, 3)  # not a Dinosaur: no bonus
    cast_at_self(s, "Colossadactyl", G=4)
    assert find(s, "Colossadactyl").damage == 2 and pt(s, raptor) == (4, 3)  # +2/+0 until end of turn
    roundtrip(s)
