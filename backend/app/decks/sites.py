"""Deck links from sites the host can't fetch, and how to bring those decks instead.

Only Archidekt offers a public deck feed (``archidekt.py``). The other sites were checked from a host on 2026-11-03
with a single plain request each, named as Fyodor (docs/DECK_FORMAT.md, "Deck links"):

- Moxfield: no export URL at all. Its Export menu builds the text in the browser from an API that needs a Moxfield
  key, and its pages answer non-browser clients with a Cloudflare block.
- MTGGoldfish: ``/deck/download/<id>`` is the deck page's Download menu, but robots.txt disallows ``/deck/download*``
  and it answers with a Cloudflare browser check (``cf-mitigated: challenge``), as do the deck pages.
- TappedOut (``<deck>?fmt=txt``) and Deckstats (``<deck>?export_txt=1``): every page, the exports included, answers
  with a Cloudflare browser check (JavaScript and cookies). Fyodor doesn't try to get around it.

So a link from one of these is refused before any network use (online or not), with that site's steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.decks.archidekt import ArchidektError


class DeckLinkRefused(ArchidektError):
    """A link the host won't fetch. The message says how to bring the deck as text instead (HTTP 422, not 502)."""


@dataclass(frozen=True)
class DeckSite:
    name: str
    host: re.Pattern[str]
    why: str
    steps: str

    def message(self) -> str:
        return f"{self.why} {self.steps}, then paste it as a deck list instead."


SITES = (
    DeckSite(
        "Moxfield", re.compile(r"\bmoxfield\.com\b", re.IGNORECASE),
        "Moxfield has no public export link (its deck data is only open to apps with a Moxfield API key).",
        "In Moxfield, open the deck and choose More → Export → Copy Plain Text",
    ),
    DeckSite(
        "MTGGoldfish", re.compile(r"\bmtggoldfish\.com\b", re.IGNORECASE),
        "MTGGoldfish doesn't let programs download decks (its robots.txt and a browser check block it).",
        "On the deck's page choose Download → Text File (Default), open the file and copy the list",
    ),
    DeckSite(
        "TappedOut", re.compile(r"\btappedout\.net\b", re.IGNORECASE),
        "TappedOut asks every visitor for a browser check, so the host can't fetch the deck.",
        "In your browser, add ?fmt=txt to the deck's address to see it as text, copy that",
    ),
    DeckSite(
        "Deckstats", re.compile(r"\bdeckstats\.net\b", re.IGNORECASE),
        "Deckstats asks every visitor for a browser check, so the host can't fetch the deck.",
        "In your browser, add ?export_txt=1 to the deck's address to get it as text, copy that",
    ),
)


def site_for(link: str) -> DeckSite | None:
    """The deck site a link points at, if it is one Fyodor knows it can't fetch."""
    return next((s for s in SITES if s.host.search(link or "")), None)


def refusal(link: str) -> str | None:
    """The message for a link from a site without a public export, or None."""
    site = site_for(link)
    return site.message() if site else None


def refuse_link(text: str) -> None:
    """Raise ``DeckLinkRefused`` when ``text`` is a single line holding another site's deck link (pasted as a list)."""
    line = (text or "").strip()
    message = refusal(line) if line and "\n" not in line else None
    if message:
        raise DeckLinkRefused(message)
