"""Wave 21C: "if you do" / "this way" wordings, real Oracle text (CR 2026-09-25).

* 603.4 / 508.5: "if no opponent has more life than that player" (Alliance commanders' granted attack trigger).
* 701.9a: "discard any number of creature cards" (only cards of that kind can be chosen).
* 608.2c: "you may have target creature get +2/+0 … If you do, sacrifice it at the beginning of the next end step"; "you may exile
  Hikari. If you do, return it …"; "You may discard up to two cards. If you do, draw that many cards."; "pay any amount of life".
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card

TEXTS = {
    "Guild Artisan": ("{2}{W}", "Creature — Human Artificer",
                      'Commander creatures you own have "Whenever this creature attacks a player, if no opponent has more life than '
                      'that player, you create two Treasure tokens."'),
    "Sword Coast Sailor": ("{2}{U}", "Creature — Human Pirate",
                           'Commander creatures you own have "Whenever this creature attacks a player, if no opponent has more life '
                           'than that player, this creature can\'t be blocked this turn."'),
    "Mind Maggots": ("{3}{B}", "Creature — Insect",
                     "When this creature enters, discard any number of creature cards. For each card discarded this way, put two "
                     "+1/+1 counters on this creature."),
    "Malfegor": ("{2}{B}{B}{R}{R}", "Legendary Creature — Demon Dragon",
                 "Flying\nWhen Malfegor enters, discard your hand. Each opponent sacrifices a creature of their choice for each "
                 "card discarded this way."),
    "Hazoret's Favor": ("{2}{R}", "Enchantment",
                        "At the beginning of combat on your turn, you may have target creature you control get +2/+0 and gain haste "
                        "until end of turn. If you do, sacrifice it at the beginning of the next end step."),
    "Attack-in-the-Box": ("{3}", "Artifact Creature — Construct",
                          "Whenever this creature attacks, you may have it get +4/+0 until end of turn. If you do, sacrifice it at "
                          "the beginning of the next end step."),
    "Hikari, Twilight Guardian": ("{3}{W}{W}", "Legendary Creature — Spirit",
                                  "Flying\nWhenever you cast a Spirit or Arcane spell, you may exile Hikari. If you do, return it to "
                                  "the battlefield under its owner's control at the beginning of the next end step."),
    "Necrodominance": ("{B}{B}{B}", "Enchantment",
                       "You don't lose the game for having 0 or less life.\nIf you would gain life, you draw that many cards "
                       "instead.\nWhenever you lose life, exile that many cards from the top of your library.\nAt the beginning of "
                       "your end step, you may pay any amount of life. If you do, draw that many cards."),
    "Fable chapter": ("{2}{R}", "Enchantment — Saga",
                      "I — Create a 2/2 red Goblin Shaman creature token.\nII — You may discard up to two cards. If you do, draw "
                      "that many cards.\nIII — Exile this Saga, then return it to the battlefield transformed under your control."),
}


@pytest.mark.parametrize("name", [n for n in TEXTS if n not in ("Necrodominance", "Fable chapter")])
def test_wordings_are_automated(name):
    cost, types, text = TEXTS[name]
    c = card(name, set_code="tst", number="21C-" + name[:5], mana_cost=cost, type_line=types, oracle_text=text,
             power="2" if "Creature" in types else None, toughness="2" if "Creature" in types else None)
    assert coverage.of_card_data(c).level == "FULL"


def test_discard_selector_and_life_payment_parse():
    from app.rules import language, paid_x, scripts

    assert scripts._clause("discard any number of creature cards")[0][0]["sel"].startswith("sel:")
    assert paid_x.payment("pay any amount of life")["choose_x"]["life"] is True
    assert language is not None
