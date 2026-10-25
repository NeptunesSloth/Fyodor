"""Wave 110D: Pyxis of Pandemonium, real Oracle text (tests/fixtures/wave110d_cards.json).

* 607.2a, 406.3, 400.3: the cards both players exiled face down turn face up; the permanent cards enter under their owners' control, the rest stay exiled.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import activate, card_db, check, full, mana, now, put, settle  # noqa: F401


def test_pyxis_is_full():
    assert full("Pyxis of Pandemonium")


def test_permanents_enter_the_rest_stay_face_up(cards):
    s = build(cards, ["Pyxis of Pandemonium", "Lightning Bolt"], ["Grizzly Bears"])
    pyxis = put(s, "Pyxis of Pandemonium")
    bolt, bears = card_named(s, "Lightning Bolt"), card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    activate(s, pyxis, "{T}: Each player exiles")
    assert now(s, bolt).zone == "p1:exile" and now(s, bolt).face_down and now(s, bears).zone == "p2:exile"
    act(s, "p1", type="tap", card_ids=[pyxis.id], tapped=False)  # (untapped for the second activation)
    mana(s, "p1", C=7)
    activate(s, pyxis, "{7}, {T}")
    assert now(s, bears).zone == "p2:battlefield" and not now(s, bears).face_down
    assert now(s, bolt).zone == "p1:exile" and not now(s, bolt).face_down
    check(s)
