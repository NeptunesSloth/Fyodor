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
