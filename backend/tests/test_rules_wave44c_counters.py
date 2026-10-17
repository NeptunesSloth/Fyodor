"""Wave 44C (counters / static family, commanders): one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave44c_cards.json).
Every scenario checks the replay and a save and a load.

* 605.1a, 106.1b: "Human creatures you control have "{T}: Add one mana of any of this creature's colors."" (Katilda, Dawnhart Prime [4535]) - the colors it has now; none, no mana.
* 702.45a, 613.4c: "Each other Samurai creature you control gets +1/+1 for each point of bushido it has." (Takeno, Samurai General [17582]) - read for each one, not for Takeno.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, next_turn, settle
from tests.wave9c_kit import build, card_named, check, pt, put
from tests.wave44c_kit import DATA, ch, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Katilda, Dawnhart Prime", "Takeno, Samurai General"])
def test_coverage_full(cards, name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [data], "oracle_id": name}).level == "FULL"


def base(name):
    data = next(c for c in DATA if c["name"] == name)
    return int(data["power"]), int(data["toughness"])


# ---- Katilda, Dawnhart Prime [4535] -------------------------------------------------------------------------------------------------------------------
def tap_for_mana(s, c):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=next(a.index for a in ch(s, c).abilities if a.kind == "mana"))


def pool(s, pid="p1"):
    return {k: v for k, v in s.state.players[pid].mana.items() if v}


def test_katilda_gives_a_human_mana_of_one_of_its_own_colors(cards):
    s = build(cards, ["Katilda, Dawnhart Prime"], [])
    kat = put(s, "Katilda, Dawnhart Prime")  # a green and white Human
    settle(s)
    next_turn(s)
    tap_for_mana(s, kat)
    d = ask(s)
    assert len(d.options) == 2, [o.label for o in d.options]  # green or white
    white = next(o.id for o in d.options if "W" in o.label or "hite" in o.label)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[white])
    assert pool(s) == {"W": 1} and s.state.cards[kat.id].tapped
    check(s)


def test_katilda_gives_a_colorless_human_no_mana_and_a_nonhuman_nothing(cards):
    s = build(cards, ["Katilda, Dawnhart Prime", "Grizzly Bears"], [])
    put(s, "Katilda, Dawnhart Prime")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="create_token", player="p1", token={"name": "Pale Human", "type_line": "Token Creature — Human", "power": "1", "toughness": "1", "colors": []})
    pale = next(c for c in s.state.cards.values() if c.name == "Pale Human")
    settle(s)
    next_turn(s)
    assert not any(a.kind == "mana" for a in ch(s, bears).abilities)  # a Bear is no Human
    with pytest.raises(ActionError):
        tap_for_mana(s, pale)  # colorless: it has no color to add
    assert pool(s) == {} and not s.state.cards[pale.id].tapped
    check(s)


# ---- Takeno, Samurai General [17582] ------------------------------------------------------------------------------------------------------------------
def test_takeno_gives_each_other_samurai_a_bonus_for_each_point_of_its_bushido(cards):
    s = build(cards, ["Takeno, Samurai General", "Jade Avenger", "Devoted Retainer", "Grizzly Bears"], [])
    for n in ("Takeno, Samurai General", "Jade Avenger", "Devoted Retainer", "Grizzly Bears"):
        put(s, n)
    settle(s)
    (jp, jt), (rp, rt), (tp, tt) = base("Jade Avenger"), base("Devoted Retainer"), base("Takeno, Samurai General")
    assert pt(s, "Jade Avenger") == (jp + 2, jt + 2)  # bushido 2
    assert pt(s, "Devoted Retainer") == (rp + 1, rt + 1)  # bushido 1
    assert pt(s, "Takeno, Samurai General") == (tp, tt)  # "other"
    assert pt(s, "Grizzly Bears") == base("Grizzly Bears")  # not a Samurai
    act(s, "p1", type="move", card_ids=[card_named(s, "Takeno, Samurai General").id], to={"zone": "graveyard"})
    assert pt(s, "Jade Avenger") == (jp, jt)
    check(s)
