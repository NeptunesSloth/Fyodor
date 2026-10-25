"""Wave 110D: Gutter Grime and Holy Frazzle-Cannon, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 608.2h, 613.4a: "put a slime counter on Gutter Grime, then create a green Ooze creature token with "This token's power and toughness are each equal to the number
  of slime counters on Gutter Grime."" — every Ooze is as big as the counters on the enchantment, so all grow together.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, ch, check, full, now, put_new, to_phase  # noqa: F401


def oozes(s):
    return [c for c in s.state.cards.values() if c.name == "Ooze" and c.zone.endswith(":battlefield")]


def test_grime_is_full():
    assert full("Gutter Grime")


def test_oozes_count_the_enchantments_counters(cards):
    s = build(cards, ["Gutter Grime", "Grizzly Bears", "Grizzly Bears", "Murder", "Murder"])
    grime = put_new(s, "Gutter Grime")
    for n in (1, 2):
        bears = put_new(s, "Grizzly Bears")
        cast_on(s, "Murder", bears)
        assert now(s, grime).counters.get("slime") == n and len(oozes(s)) == n
        assert all(ch(s, o).pt == (n, n) for o in oozes(s))
    check(s)


def test_frazzle_cannon_counters_on_the_attacker_and_creatures_sharing_a_type(cards):
    """205.3m: "put a +1/+1 counter on that creature and each other creature you control that shares a creature type with it" (Holy Frazzle-Cannon)."""
    from tests.game_helpers import act
    from tests.wave110d_kit import settle

    s = build(cards, ["Invasion of New Capenna // Holy Frazzle-Cannon", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"])
    cannon = put_new(s, "Invasion of New Capenna // Holy Frazzle-Cannon")
    settle(s)
    act(s, "p1", type="set_face", card_id=cannon.id, face=1)
    a, b, elf = (put_new(s, n) for n in ("Grizzly Bears", "Grizzly Bears", "Llanowar Elves"))
    to_phase(s, "main1", turn=3)
    from tests.wave9c_kit import mana

    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=cannon.id, ability=next(x.index for x in ch(s, cannon).abilities if x.text.startswith("Equip")), targets=[a.id])
    settle(s)
    assert now(s, cannon).attached_to == a.id
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    settle(s)
    assert [now(s, c).counters.get("+1/+1", 0) for c in (a, b, elf)] == [1, 1, 0]
    check(s)
