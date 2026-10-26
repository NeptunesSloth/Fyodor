"""Wave 110H session 9: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Desolation: at each end step every player who tapped a land for mana this turn sacrifices a land; one who sacrificed a Plains is dealt 2 damage (701.21a, 608.2h).
* Glimpse of Tomorrow: all permanents you own are shuffled into the library and that many cards revealed; permanent cards enter, Auras last, the rest go to the bottom (701.24a).
* Ashiok, Wicked Manipulator: its controller's payment of life becomes exiling that many cards from the top of the library, if it has that many (614.1a, 119.4).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110h_s5 import answer
from tests.wave9c_kit import build, check, life, mana, put
from tests.wave110j_kit import ability, ch, now

ASHIOK_TEXT = ("If you would pay life while your library has at least that many cards in it, exile that many cards from the top of your library instead.\n"
               "+1: Look at the top two cards of your library. Exile one of them and put the other into your hand.\n"
               "−2: Create two 1/1 black Nightmare creature tokens with \"At the beginning of combat on your turn, if a card was put into exile this turn, put a +1/+1 counter "
               "on this token.\"\n−7: Target player exiles the top X cards of their library, where X is the total mana value of cards you own in exile.")
EXTRA = [
    card("Ashiok, Wicked Manipulator", set_code="tst", number="110H-ash", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Legendary Planeswalker — Ashiok", oracle_text=ASHIOK_TEXT,
         colors=["B"], color_identity=["B"], keywords=[], loyalty="5"),
    card("Plains", set_code="tst", number="110H-pl", type_line="Basic Land \u2014 Plains", oracle_text="({T}: Add {W}.)", color_identity=["W"]),
    real("Desolation", "{1}{B}{B}", 3, "Enchantment", "At the beginning of each end step, each player who tapped a land for mana this turn sacrifices a land of their choice. "
         "This enchantment deals 2 damage to each player who sacrificed a Plains this way.", None, "B"),
    real("Glimpse of Tomorrow", "", 0, "Sorcery", "Suspend 3\u2014{R}{R}\nShuffle all permanents you own into your library, then reveal that many cards from the top of your library. "
         "Put all non-Aura permanent cards revealed this way onto the battlefield, then do the same for Aura cards, then put the rest on the bottom of your library in a random order.",
         None, "R"),
    real("Runeclaw Bear", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
    real("Pacifism", "{1}{W}", 2, "Enchantment \u2014 Aura", "Enchant creature\nEnchanted creature can't attack or block.", None, "W"),
    real("Pain Pylon", "{1}", 1, "Artifact", "{T}, Pay 2 life: Draw a card.", None, ""),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _pay(cards, owner, library):
    """p1 activates Pain Pylon (pay 2 life); Ashiok is on ``owner``'s side; p1's library is cut to ``library`` cards. Returns (state, life before, cards in p1's exile)."""
    s = build(cards, ["Pain Pylon"] + (["Ashiok, Wicked Manipulator"] if owner == "p1" else []), ["Ashiok, Wicked Manipulator"] if owner == "p2" else [])
    put(s, "Ashiok, Wicked Manipulator", owner)
    pylon = put(s, "Pain Pylon")
    keep = s.state.zones["p1:library"][:library]
    act(s, "p1", type="move", card_ids=[c for c in s.state.zones["p1:library"] if c not in keep], to={"zone": "graveyard"})
    before = life(s, "p1")
    act(s, "p1", type="activate_ability", card_id=pylon.id, ability=ability(s, pylon, "{T}, Pay 2 life"))
    answer(s)
    return s, before, pylon


@pytest.mark.parametrize(("owner", "library", "replaced"), [("p1", 5, True), ("p1", 2, True), ("p1", 1, False), ("p2", 5, False)])
def test_ashiok_replaces_paying_life_only_for_its_controller_with_enough_library(cards, owner, library, replaced):
    """614.1a: 2 life paid with Ashiok and at least 2 cards in the library exiles 2 cards instead (no life lost); too few cards, or another player's Ashiok: life is paid."""
    s, before, pylon = _pay(cards, owner, library)
    exiled = [c for c in s.state.zones["p1:exile"]]
    assert life(s, "p1") == (before if replaced else before - 2) and len(exiled) == (2 if replaced else 0)
    assert now(s, pylon).tapped  # (the cost was paid either way)
    check(s)


@pytest.mark.parametrize(("taps", "keep", "sacrificed", "dmg"), [
    ("Plains", "Forest", "Plains", 2),     # tapped a land: sacrifices one of its choice; a Plains costs 2 life
    ("Forest", "Plains", "Forest", 0),     # not a Plains: no damage
    (None, "Plains", None, 0),             # nobody tapped a land: nothing happens
])
def test_desolation_sacrifices_for_tappers_and_burns_plains_sacrificers(cards, taps, keep, sacrificed, dmg):
    s = build(cards, ["Desolation", "Plains"])
    put(s, "Desolation")
    plains, forest = put(s, "Plains"), put(s, "Forest")
    if taps:
        tapped = plains if taps == "Plains" else forest
        act(s, "p1", type="activate_ability", card_id=tapped.id, ability=ability(s, tapped, "{T}"))
    land = {"Plains": plains, "Forest": forest}
    turn, asked = s.state.turn.number, []
    while s.state.turn.number == turn:  # (the whole turn: pass priority, answer the one land choice)
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            asked.append(d.player)
            assert {o.id for o in d.options} >= {plains.id, forest.id}
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[land[sacrificed].id])
    assert asked == (["p1"] if sacrificed else [])  # (nobody else tapped a land; nobody who didn't is asked)
    assert [now(s, c).zone for c in (plains, forest)] == [("p1:graveyard" if sacrificed == "Plains" else "p1:battlefield"), ("p1:graveyard" if sacrificed == "Forest" else "p1:battlefield")]
    assert life(s, "p1") == 40 - dmg and life(s, "p2") == 40
    check(s)


def _glimpse(cards, others, on_battlefield):
    """Glimpse suspended (702.62: three upkeeps), then cast: ``others`` library cards besides the forests, ``on_battlefield`` extra permanents first."""
    s = build(cards, ["Glimpse of Tomorrow", *others])
    glimpse = next(c for c in s.state.cards.values() if c.name == "Glimpse of Tomorrow")
    act(s, "p1", type="move", card_ids=[glimpse.id], to={"zone": "hand"})
    for n in on_battlefield:
        put(s, n)
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=glimpse.id, ability=next(a.index for a in ch(s, glimpse).abilities if "suspend" in a.keywords))
    for _ in range(300):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "suspend_cast":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["yes"])
    answer(s)
    return s


def test_glimpse_reveals_as_many_cards_as_permanents_shuffled_and_they_enter(cards):
    """A Forest and a Bear on the battlefield: 2 permanents shuffled in, 2 of the (all-permanent) cards revealed enter, so 2 are on the battlefield and the library is as big as before."""
    s = _glimpse(cards, ["Runeclaw Bear"], ["Forest", "Runeclaw Bear"])
    mine = [c for c in s.state.cards.values() if c.owner == "p1"]
    assert len([c for c in mine if c.zone == "p1:battlefield"]) == 2 and len([c for c in mine if c.zone == "p1:library"]) == 5  # (10 cards, 3 drawn in the three turns)
    assert len([c for c in mine if c.zone == "p1:hand"]) == 3 and next(c for c in mine if c.name == "Glimpse of Tomorrow").zone == "p1:graveyard"
    check(s)


def test_glimpse_with_nothing_to_shuffle_reveals_nothing(cards):
    s = _glimpse(cards, [], [])
    assert not [c for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:battlefield"]
    check(s)
