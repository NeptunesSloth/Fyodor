"""The trigger order prompt names each trigger by its source and, when two share a source (a spell's cascade and demonstrate, both from
the deck audit's Ian Malcolm table: Wild-Magic Sorcerer and The Twelfth Doctor), by what each one does."""

from __future__ import annotations

from app.game.rules_state import PendingTrigger
from app.rules.triggers import order_labels


def trigger(name: str, ability: dict) -> PendingTrigger:
    return PendingTrigger(id=name + str(len(ability)), controller="p1", source_card="c", source_object="o", name=name, ability=ability)


def test_two_triggers_of_one_source_say_what_each_does() -> None:
    mine = [trigger("Craw Wurm", {"keyword": "Cascade", "effects": []}),
            trigger("Craw Wurm", {"effects": [{"do": "demonstrate_copy"}]}),
            trigger("Grizzly Bears", {"effects": [{"do": "draw", "n": 1}]})]
    assert order_labels(mine) == ["Craw Wurm: Cascade", "Craw Wurm: Copy it, and an opponent copies it too (demonstrate)", "Grizzly Bears"]


def test_different_sources_keep_their_names() -> None:
    assert order_labels([trigger("A", {"effects": []}), trigger("B", {"effects": []})]) == ["A", "B"]
