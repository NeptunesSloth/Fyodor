"""The trigger order prompt names each trigger by its source and what it does (a spell's cascade and demonstrate, both from the deck audit's
Ian Malcolm table: Wild-Magic Sorcerer and The Twelfth Doctor). With a table, the printed words of the ability (test_rules_landfall_reveal_order);
without one, the keyword, else the effects in words."""

from __future__ import annotations

from app.game.rules_state import PendingTrigger
from app.rules.triggers import order_labels


def trigger(name: str, ability: dict) -> PendingTrigger:
    return PendingTrigger(id=name + str(len(ability)), controller="p1", source_card="c", source_object="o", name=name, ability=ability)


def test_two_triggers_of_one_source_say_what_each_does() -> None:
    mine = [trigger("Craw Wurm", {"keyword": "Cascade", "effects": []}),
            trigger("Craw Wurm", {"effects": [{"do": "demonstrate_copy"}]}),
            trigger("Grizzly Bears", {"effects": [{"do": "draw", "n": 1}]})]
    assert order_labels(mine) == ["Craw Wurm — Cascade", "Craw Wurm — Copy it, and an opponent copies it too (demonstrate)",
                                  "Grizzly Bears — Draw 1 card(s)"]


def test_a_trigger_with_nothing_to_say_keeps_its_name() -> None:
    assert order_labels([trigger("A", {"effects": []}), trigger("B", {"effects": []})]) == ["A", "B"]


def test_printed_words_are_shortened() -> None:
    from app.rules.triggers import shorten_ability

    assert shorten_ability("Landfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.")         == "Landfall: you may put a +1/+1 counter on each Plant creature you control."
    assert shorten_ability("When this creature enters, draw a card. (Reminder text.)") == "When this creature enters, draw a card."
    long = shorten_ability("Whenever a creature dies, " + "each opponent loses one life and you gain one life " * 4)
    assert len(long) <= 111 and long.endswith("…")
