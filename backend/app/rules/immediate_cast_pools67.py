"""Exact immediate casting instructions over native pools and dynamic values."""

from __future__ import annotations

from typing import Any


def clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import selectors, values

    text = text.lower().rstrip(".")
    if text.startswith("~ deals "):
        text = text.replace("equipment attached to it", "equipment attached to ~")
    basic: dict[str, Any] = {"do": "free_cast", "zone": "hand", "optional": True}
    if text == "you may cast any number of spells from your hand without paying their mana costs":
        return [{**basic, "all": True}], None
    if (
        text
        == "cast any number of red instant and/or sorcery cards from your graveyard without paying their mana costs"
    ):
        red = selectors.Selector(zones=("stack",), types=("Instant", "Sorcery"), colors=("R",)).key()
        return [{**basic, "zone": "graveyard", "whose": "you", "all": True, "filter": red}], None
    if (
        text
        == "you may cast up to three spells from among face-up cards your opponents own from exile without paying their mana costs"
    ):
        pool = selectors.parse("face-up card your opponents own in exile")
        if pool is None:
            return None
        return [{**basic, "zone": "selector", "pool_selector": pool.key(), "n": 3}], None
    if (
        text
        == "you may cast a spell that shares a card type with it from your hand without paying its mana cost"
    ):
        return [{**basic, "shares_type": "target"}], None
    if (
        text
        == "you may cast an instant or sorcery spell with mana value equal to the number of charge counters on ~ from your hand without paying its mana cost"
    ):
        card_type = selectors.Selector(zones=("stack",), types=("Instant", "Sorcery")).key()
        return [
            {**basic, "mv": {"counters": "charge", "on": "self"}, "mv_eq": True, "filter": card_type}
        ], None
    if (
        text
        == "you may cast an instant or sorcery spell from your hand with mana value less than or equal to the greatest mana value among equipment attached to ~ without paying its mana cost"
    ):
        card_type = selectors.Selector(zones=("stack",), types=("Instant", "Sorcery")).key()
        maximum = values.parse_count("the greatest mana value among Equipment attached to ~")
        if maximum is None:
            return None
        return [{**basic, "mv": maximum, "filter": card_type}], None
    if text == "~ deals damage equal to the greatest mana value among equipment attached to ~ to any target":
        maximum = values.parse_count("the greatest mana value among Equipment attached to ~")
        if maximum is None:
            return None
        return [{"do": "damage", "who": "target", "n": maximum}], "any"
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    body = " ".join(body.split()).strip().rstrip(".")
    direct = clause(body)
    if direct is not None:
        return *direct, False
    if (
        body
        == "Return target nonland permanent to its owner's hand, then that player exiles a card from their hand"
    ):
        native = scripts.parse_effects("Return target nonland permanent to its owner's hand.")
        if native is None:
            return None
        return [*native[0], {"do": "discard", "who": "target_owner", "n": 1, "to": "exile"}], native[1], False
    prefixes = {
        "Draw seven cards. You may cast any number of spells from your hand without paying their mana costs": (
            "Draw seven cards.",
            "You may cast any number of spells from your hand without paying their mana costs",
        ),
        "Counter target spell. You may cast a spell that shares a card type with it from your hand without paying its mana cost": (
            "Counter target spell.",
            "You may cast a spell that shares a card type with it from your hand without paying its mana cost",
        ),
        "Put a charge counter on ~, then you may cast an instant or sorcery spell with mana value equal to the number of charge counters on ~ from your hand without paying its mana cost": (
            "Put a charge counter on ~.",
            "You may cast an instant or sorcery spell with mana value equal to the number of charge counters on ~ from your hand without paying its mana cost",
        ),
    }
    pair = prefixes.get(body)
    if pair is None:
        return None
    native, following = scripts.parse_effects(pair[0]), clause(pair[1])
    if native is None or following is None:
        return None
    return [*native[0], *following[0]], native[1], False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import modal_abilities, scripts

    expected = (
        "Whenever ~ attacks, if it's equipped, choose one —",
        "• ~ deals damage equal to the greatest mana value among Equipment attached to it to any target.",
        "• You may cast an instant or sorcery spell from your hand with mana value less than or equal to the greatest mana value among Equipment attached to ~ without paying its mana cost.",
    )
    lines = tuple(scripts.self_text(a.text, ch.name) for a in ch.abilities)
    if lines != expected or scripts.self_text(ability.text, ch.name) not in expected:
        return None
    first = ch.abilities[0]
    header = replace(first, text="Whenever this creature attacks, choose one —")
    normalized = replace(ch, abilities=(header, *ch.abilities[1:]))
    native = modal_abilities.definitions(header, normalized)
    base = native.get(first.index)
    equipped = scripts.define(
        replace(first, text="Whenever this creature attacks, if it's equipped, draw a card."), ch
    )
    if base is None or equipped is None or equipped.get("if") is None:
        return None
    if ability.index == first.index:
        return {**base, "if": equipped["if"]}
    return native.get(ability.index)
