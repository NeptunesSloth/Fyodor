"""Wave 110D: Tyvar the Bellicose, real Oracle text (tests/fixtures/wave110d_cards.json).

* 605.3b, 106.12a: a mana ability resolves as it is activated; "Whenever a mana ability of this creature resolves" sees how much mana it produced.
* 603.2h: "This ability triggers only once each turn" (per creature, each has its own copy).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import (  # noqa: F401
    activate,
    build,
    card_db,
    cast_on,
    ch,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    settle,
    to_phase,
)

NAME = "Tyvar the Bellicose"


def test_full():
    assert full(NAME)


def _board(cards, extra=()):
    s = build(cards, [NAME, "Llanowar Elves", "Priest of Titania", "Grizzly Bears", *extra], ["Grizzly Bears"])
    put_new(s, NAME)
    out = s, put_new(s, "Llanowar Elves"), put_new(s, "Priest of Titania"), put_new(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)
    return out


def counters(s, c):
    return now(s, c).counters.get("+1/+1", 0)


def test_counters_equal_the_mana_produced(cards):
    s, elf, priest, bears = _board(cards)
    activate(s, elf, "{T}: Add")
    activate(s, priest, "{T}: Add")
    assert (counters(s, elf), counters(s, priest), counters(s, bears)) == (1, 3, 0)  # the Priest adds {G} for each Elf: three (Tyvar is an Elf too)
    check(s)


def test_paying_a_cost_with_it_triggers_too(cards):
    s, elf, priest, bears = _board(cards, ["Lightning Bolt"])
    cast_on(s, "Lightning Bolt", "p2")  # (paid from its own mana)
    check(s)


def _pay_probe(cards, spell, source, *more):
    s = build(cards, [NAME, source, spell, *more], ["Grizzly Bears"])
    put_new(s, NAME)
    out = [put_new(s, n) for n in (source, *more)]
    c = hand_new(s, spell)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    return s, out


def test_cast_payment_counts_all_mana_produced(cards):
    # 106.12a/605.3b: Llanowar Tribe makes {G}{G}{G} although the spell needs one mana; the trigger still sees three.
    s, (tribe,) = _pay_probe(cards, "Bonesplitter", "Llanowar Tribe")
    assert counters(s, tribe) == 3
    check(s)


def test_cast_payment_with_a_variable_producer(cards):
    s, (priest, _elf) = _pay_probe(cards, "Bonesplitter", "Priest of Titania", "Llanowar Elves")
    assert counters(s, priest) == 3 and counters(s, _elf) == 0  # only the creature that was tapped; Priest: Tyvar + 2 Elves
    check(s)


def test_non_creature_source_never_triggers_it(cards):
    s, (ring,) = _pay_probe(cards, "Arcane Signet", "Sol Ring")  # (Sol Ring makes {C}{C}; Tyvar only watches its creature's own abilities)
    assert counters(s, ring) == 0
    assert all(c.counters.get("+1/+1", 0) == 0 for c in s.state.cards.values())
    check(s)


def test_two_mana_elf_in_and_out_of_casting(cards):
    # Elvish Archdruid ({T}: Add {G} for each Elf you control) with Tyvar: two Elves, two mana, two counters (605.3b).
    s, (druid,) = _pay_probe(cards, "Bonesplitter", "Elvish Archdruid")
    assert counters(s, druid) == 2
    check(s)
    s = build(cards, [NAME, "Elvish Archdruid"], ["Grizzly Bears"])
    put_new(s, NAME)
    druid = put_new(s, "Elvish Archdruid")
    to_phase(s, "main1", turn=3)
    activate(s, druid, "{T}: Add")
    assert counters(s, druid) == 2
    check(s)


def test_attacking_elves_gain_deathtouch_but_other_attackers_do_not(cards):
    """Tyvar's first line: only the Elves among the attackers gain deathtouch (until end of turn); Tyvar is an Elf himself (Bears are not)."""
    from tests.wave110b_kit import attack

    s, elf, priest, bears = _board(cards)
    attack(s, elf, bears)
    settle(s)
    assert "deathtouch" in ch(s, elf).keywords and "deathtouch" not in ch(s, bears).keywords and "deathtouch" not in ch(s, priest).keywords
    check(s)
