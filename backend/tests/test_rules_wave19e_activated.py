"""-- copy abilities (wave 19E) -- "Copy target activated or triggered ability you control from an enchantment / colorless / creature
source." (Weaver of Harmony, Abstruse Archaic, Echo, Perceptive Prodigy; 707.10b: a copy of an ability has the same source; the
source is read as it last existed, 608.2h). Oracle text transcribed from the card database."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, turn_on, zone
from tests.test_rules_copy import _card, hold, life, named, on_stack, pay, resolve_top, to_hand
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import responsive

EXTRA = [
    _card("Weaver of Harmony", "W1", "{1}{G}", "Enchantment Creature — Snake Druid",
          "Other enchantment creatures you control get +1/+1.\n{G}, {T}: Copy target activated or triggered ability you control from "
          "an enchantment source. You may choose new targets for the copy. (Mana abilities can't be targeted.)", ["G"],
          power="2", toughness="2"),
    _card("Abstruse Archaic", "W2", "{4}", "Creature — Avatar",
          "Vigilance\n{1}, {T}: Copy target activated or triggered ability you control from a colorless source. You may choose new "
          "targets for the copy. (Mana abilities can't be targeted.)", [], power="3", toughness="4"),
    _card("Angelic Chorus", "W3", "{3}{W}{W}", "Enchantment",
          "Whenever a creature you control enters, you gain life equal to its toughness.", ["W"]),
    _card("Ichor Wellspring", "W5", "{2}", "Artifact",
          "When this artifact enters or is put into a graveyard from the battlefield, draw a card.", []),
    _card("Furnace Brood", "W6", "{3}{R}", "Creature — Elemental", "{R}: Target creature can't be regenerated this turn.", ["R"],
          power="3", toughness="3"),
    _card("Drudge Skeletons", "W7", "{1}{B}", "Creature — Skeleton",
          "{B}: Regenerate this creature. (The next time this creature would be destroyed this turn, instead tap it, remove it from "
          "combat, and heal all damage on it.)", ["B"], power="1", toughness="1"),
    _card("Meek Attack", "W8", "{2}{R}", "Enchantment",
          "{1}{R}: You may put a creature card with total power and toughness 5 or less from your hand onto the battlefield. That "
          "creature gains haste. At the beginning of the next end step, sacrifice that creature.", ["R"]),
    _card("Purphoros, Bronze-Blooded", "W9", "{4}{R}", "Legendary Enchantment Creature — God",
          "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nOther creatures you control "
          "have haste.\n{2}{R}: You may put a red creature card or an artifact creature card from your hand onto the battlefield. "
          "Sacrifice it at the beginning of the next end step.", ["R"], power="7", toughness="6"),
    _card("Hill Giant", "W10", "{3}{R}", "Creature — Giant", "", ["R"], power="3", toughness="3"),
    _card("Soul Warden", "W4", "{W}", "Creature — Human Cleric",
          "Whenever another creature enters, you gain 1 life.", ["W"], power="1", toughness="1"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, on_battlefield, hand):
    """Alice's main phase; ``on_battlefield`` was already there (not summoning sick)."""
    names = [*on_battlefield, *hand]
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    for n in on_battlefield:
        act(s, "p1", type="move", card_ids=[named(s, n).id], to={"player": "p1", "zone": "battlefield"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    responsive(s)
    hold(s)
    for n in hand:
        to_hand(s, n)
    return s


def order_triggers(s):
    d = s.state.rules.decision
    assert d is not None and d.kind == "order"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])


def trigger_on_stack(s, source):
    return next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger" and s.state.cards[e.source_card].name == source)


def test_copy_ability_from_an_enchantment_source(cards):
    """Weaver of Harmony copies Angelic Chorus's trigger (an enchantment source) with its event: the Bears' toughness twice (707.10b,
    603.2) — but not Soul Warden's trigger (a creature source: the target isn't legal) — and the new-targets rider is carried out."""
    s = table(cards, ["Weaver of Harmony", "Angelic Chorus", "Soul Warden"], ["Grizzly Bears"])
    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in ("Weaver of Harmony", "Abstruse Archaic"))
    pay(s, G=3)
    act(s, "p1", type="cast_spell", card_id=named(s, "Grizzly Bears").id)
    resolve_top(s)  # the Bears enter: Angelic Chorus and Soul Warden trigger
    order_triggers(s)
    weaver = named(s, "Weaver of Harmony")
    warden = trigger_on_stack(s, "Soul Warden")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=weaver.id, ability=1, targets=[warden])  # a creature source: not legal
    chorus = trigger_on_stack(s, "Angelic Chorus")
    act(s, "p1", type="activate_ability", card_id=weaver.id, ability=1, targets=[chorus])
    resolve_top(s)  # Weaver's ability: a copy of the Chorus trigger
    copy = next(c for c, e in s.state.rules.stack.items() if e.copy_of is not None)
    assert s.state.rules.stack[copy].source_card == s.state.rules.stack[chorus].source_card
    before = life(s, "p1")
    pass_until_stack_empty(s)
    assert life(s, "p1") == before + 2 + 2 + 1  # the Bears' toughness twice, and Soul Warden's 1
    replay_matches(s)
    assert on_stack(s) == []


def test_copy_ability_from_a_colorless_source(cards):
    """Abstruse Archaic copies the draw trigger of a colorless artifact (Ichor Wellspring)."""
    s = table(cards, ["Abstruse Archaic"], ["Ichor Wellspring"])
    pay(s, C=3)
    act(s, "p1", type="cast_spell", card_id=named(s, "Ichor Wellspring").id)
    resolve_top(s)  # the Wellspring enters: its trigger
    archaic = named(s, "Abstruse Archaic")
    act(s, "p1", type="activate_ability", card_id=archaic.id, ability=1, targets=[trigger_on_stack(s, "Ichor Wellspring")])
    hand = len(zone(s.state, "p1", "hand"))
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 2  # the trigger and its copy
    replay_matches(s)


@pytest.mark.parametrize("brood", [False, True])
def test_cant_be_regenerated_this_turn(cards, brood):
    """701.19c: with Furnace Brood's ability resolved, Drudge Skeletons' regeneration shield isn't applied to the lethal damage
    (state-based action, 704.5g); without it the shield saves the Skeletons. The restriction ends at cleanup (514.2)."""
    s = table(cards, ["Furnace Brood", "Drudge Skeletons"], ["Lightning Bolt"])
    skeletons = named(s, "Drudge Skeletons")
    pay(s, B=1)
    act(s, "p1", type="activate_ability", card_id=skeletons.id, ability=0)
    resolve_top(s)
    if brood:
        pay(s, R=1)
        act(s, "p1", type="activate_ability", card_id=named(s, "Furnace Brood").id, ability=0, targets=[skeletons.id])
        resolve_top(s)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=[skeletons.id])
    pass_until_stack_empty(s)
    assert s.state.cards[skeletons.id].zone == ("p1:graveyard" if brood else "p1:battlefield")
    replay_matches(s)


@pytest.mark.parametrize(("name", "cost", "offered"), [("Meek Attack", {"R": 2}, "Grizzly Bears"),
                                                       ("Purphoros, Bronze-Blooded", {"R": 3}, "Hill Giant")])
def test_put_from_hand_narrowed_by_the_wording(cards, name, cost, offered):
    """"… card with total power and toughness 5 or less" (Meek Attack: Bears 2+2, not the Giant's 3+3) and "a red creature card or an
    artifact creature card" (Purphoros: the Giant, not the green Bears): only those are offered; it's sacrificed at the next end step."""
    s = table(cards, [name], ["Grizzly Bears", "Hill Giant"])
    pay(s, **cost)
    act(s, "p1", type="activate_ability", card_id=named(s, name).id, ability=3 if name.startswith("Purph") else 0)
    resolve_top(s)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == [offered]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert s.state.cards[named(s, offered).id].zone == "p1:battlefield"
    replay_matches(s)
