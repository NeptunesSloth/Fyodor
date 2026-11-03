"""Deck links from Moxfield, MTGGoldfish, TappedOut and Deckstats: recognised, refused before any network use, and
answered with that site's steps (docs/DECK_FORMAT.md, "Deck links"). No network in these tests."""

from __future__ import annotations

import pytest

from app.decks import archidekt, service, sites
from app.decks.models import DeckImportRequest

KRENKO = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n20 Mountain\n"
ATRAXA = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Counterspell\n20 Island\n"

LINKS = {
    "Moxfield": ["https://moxfield.com/decks/AbC123-xyz_9", "https://www.moxfield.com/decks/AbC123/primer", "moxfield.com/decks/x"],
    "MTGGoldfish": ["https://www.mtggoldfish.com/deck/8022091#paper", "https://www.mtggoldfish.com/deck/download/8022091",
                    "https://www.mtggoldfish.com/archetype/atraxa-praetors-voice"],
    "TappedOut": ["https://tappedout.net/mtg-decks/krenko-goblins/", "http://tappedout.net/mtg-decks/krenko-goblins/?fmt=txt"],
    "Deckstats": ["https://deckstats.net/decks/12345/678910-atraxa/en", "deckstats.net/decks/12345/678910-atraxa/?export_txt=1"],
}
STEPS = {
    "Moxfield": "More → Export → Copy Plain Text",
    "MTGGoldfish": "Download → Text File (Default)",
    "TappedOut": "?fmt=txt",
    "Deckstats": "?export_txt=1",
}


@pytest.mark.parametrize(("site", "link"), [(s, link) for s, links in LINKS.items() for link in links])
def test_links_are_recognised_by_site(site, link):
    found = sites.site_for(link)
    assert found is not None and found.name == site
    message = sites.refusal(link)
    assert message is not None and message.startswith(site) and STEPS[site] in message and message.endswith("as a deck list instead.")


@pytest.mark.parametrize("link", ["https://archidekt.com/decks/123/x", "123456", "https://notmoxfield.company/decks/1",
                                  "https://example.com/decks/1", "1 Sol Ring", ""])
def test_other_links_are_not_claimed(link):
    assert sites.site_for(link) is None and sites.refusal(link) is None


def test_each_site_says_why_it_cant_be_fetched():
    why = {s.name: s.why for s in sites.SITES}
    assert "API key" in why["Moxfield"]
    assert "robots.txt" in why["MTGGoldfish"] and "browser check" in why["MTGGoldfish"]
    assert "browser check" in why["TappedOut"] and "browser check" in why["Deckstats"]


def _no_fetch(deck_id: str) -> dict:
    raise AssertionError(f"the host fetched {deck_id} for a refused site")


@pytest.mark.parametrize("fetch", [_no_fetch, None], ids=["online", "offline"])
def test_a_link_is_refused_before_any_fetch_online_or_not(cards, fetch):
    for site, links in LINKS.items():
        with pytest.raises(sites.DeckLinkRefused) as refused:
            service.import_any(DeckImportRequest(archidekt=links[0]), cards, fetch=fetch)
        assert STEPS[site] in str(refused.value)
    # a link from an unknown site still gets the Archidekt hint, now as a refusal (the client's mistake, not a bad gateway)
    with pytest.raises(sites.DeckLinkRefused, match="look like an Archidekt deck URL"):
        service.import_any(DeckImportRequest(archidekt="https://example.com/decks/1"), cards, fetch=fetch)


def test_a_link_pasted_as_the_list_gets_the_same_message(cards):
    with pytest.raises(sites.DeckLinkRefused, match="Moxfield has no public export link"):
        service.import_any(DeckImportRequest(text="  https://moxfield.com/decks/AbC123 \n"), cards)
    # a real list that only mentions the site is a list
    result = service.import_any(DeckImportRequest(text="// from https://moxfield.com/decks/AbC123\n" + KRENKO), cards)
    assert result.report.commanders == ["Krenko, Mob Boss"]


def test_refusal_is_still_an_archidekt_error_for_existing_callers():
    assert issubclass(sites.DeckLinkRefused, archidekt.ArchidektError)


def test_api_answers_422_with_the_steps_and_never_fetches(client):
    calls: list[str] = []
    client.app.state.services.archidekt_fetch = lambda deck_id: calls.append(deck_id) or {}
    res = client.post("/api/decks/preview", json={"archidekt": "https://moxfield.com/decks/AbC123"})
    assert res.status_code == 422 and "More → Export → Copy Plain Text" in res.json()["detail"]
    res = client.post("/api/decks/preview", json={"text": "https://tappedout.net/mtg-decks/krenko/"})
    assert res.status_code == 422 and "?fmt=txt" in res.json()["detail"]
    assert calls == []


def test_table_importer_and_lobby_answer_422_with_the_steps(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    game = client.post("/api/games", json={"name": "Links", "players": [{"name": "A", "deck_id": a}, {"name": "B", "deck_id": b}]})
    gid = game.json()["game"]["id"]
    res = client.post(f"/api/games/{gid}/load-deck", json={"archidekt": "https://www.mtggoldfish.com/deck/8022091"})
    assert res.status_code == 422 and "Download → Text File (Default)" in res.json()["detail"]
    res = client.post(f"/api/games/{gid}/load-deck", json={"text": "https://deckstats.net/decks/1/2-x/en"})
    assert res.status_code == 422 and "?export_txt=1" in res.json()["detail"]
