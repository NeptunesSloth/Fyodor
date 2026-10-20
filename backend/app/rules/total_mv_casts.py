"""Immediate spell casting with a shared total mana-value budget."""
from __future__ import annotations

import re
from typing import Any

_AMONG = re.compile(r"^(?:you may )?cast (?P<count>any number of|up to two) (?:(?P<sel>instant and/or sorcery) )?spells(?: with total mana value (?P<a>\d+|X) or less)? from among (?P<pool>them|those cards|the copies)(?: with total mana value (?P<b>\d+|X) or less)? without paying their mana costs$")
_HAND_GRAVE = re.compile(r"^(?:you may )?cast up to two instant and/or sorcery spells with total mana value (?P<n>\d+|X) or less from your graveyard and/or hand without paying their mana costs$")


def clause(text: str) -> list[dict[str, Any]] | None:
    from app.rules import permissions

    if (hand := _HAND_GRAVE.fullmatch(text)) is not None:
        amount = hand['n']
        return [{'do': 'free_cast', 'zone': 'hand_graveyard', 'filter': permissions.spell_filter('instant or sorcery'),
                 'optional': True, 'mv_total': {'x': 1} if amount == 'X' else int(amount), 'n': 2}]
    m = _AMONG.fullmatch(text)
    if m is None or bool(m['a']) == bool(m['b']):
        return None
    amount = m['a'] or m['b']
    return [{'do': 'free_cast', 'zone': 'among', 'who': 'them:copy' if m['pool'] == 'the copies' else 'them:card',
             'filter': permissions.spell_filter('instant or sorcery') if m['sel'] else None,
             'optional': True, 'mv_total': {'x': 1} if amount == 'X' else int(amount),
             **({'all': True} if m['count'] == 'any number of' else {'n': 2})}]


def supported_wording(text: str) -> bool:
    # Only exempt the supported casting instruction from the old broad total-value refusal.
    # The remaining instructions still need complete normal definitions.
    text = re.sub(r"from among (?:the )?cards exiled with (?:this (?:artifact|creature|enchantment)|~)", 'from among them', text)
    return any(clause(part[0].lower() + part[1:]) is not None for part in re.split(r'(?<=\.)\s+|:\s+', text.rstrip('.')) if part)
