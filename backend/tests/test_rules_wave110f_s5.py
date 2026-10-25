"""Wave 110F session 5: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 701.24, 701.16a, 108.3: "Choose target creature. Its owner shuffles it into their library, then investigates." (Blink chapters I, III).
* 701.13a, 603.10, 110.2: "exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a ... Detective" (Unyielding Gatekeeper).
* 115.4, 205.1a, 611.2a: "choose any number of target planeswalkers you control. Until end of turn, they become 3/3 blue Bird creatures with flying, hexproof, and ..." (Sparkshaper Visionary).
* 614.1c, 707.9: "Creatures you control enter as a copy of this creature." (Essence of the Wild).
* 702.82a, 613.4b: "As this creature enters, sacrifice any number of creatures. This creature's power becomes the total power of those creatures ..." (Dracoplasm).
* 205.1b, 611.2a: token "Whenever an opponent casts a creature spell, this token isn't a creature until end of turn." (Blink chapters II, IV).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real('Blink', '{2}{U}{B}', 4, 'Enchantment — Saga',
         '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, III — Choose target creature. Its owner shuffles it into their library, then investigates. (They create a Clue token.)\nII, IV — Create a 2/2 black Alien Angel artifact creature token with first strike, vigilance, and "Whenever an opponent casts a creature spell, this token isn\'t a creature until end of turn."', None, 'BU'),
    real('Unyielding Gatekeeper', '{1}{W}', 2, 'Creature — Elephant Cleric',
         'Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a 2/2 white and blue Detective creature token.', ('3', '2'), 'W'),
    real('Sparkshaper Visionary', '{2}{U}', 3, 'Creature — Human Wizard',
         'At the beginning of combat on your turn, choose any number of target planeswalkers you control. Until end of turn, they become 3/3 blue Bird creatures with flying, hexproof, and "Whenever this creature deals combat damage to a player, scry 1." (They\'re no longer planeswalkers. Loyalty abilities can still be activated.)', ('0', '5'), 'U'),
    {**real('Test Walker 110F', '{2}{U}', 3, 'Legendary Planeswalker — Test', '+1: You gain 1 life.', None, 'U'), 'loyalty': '3'},
    real('Essence of the Wild', '{3}{G}{G}{G}', 6, 'Creature — Avatar',
         'Creatures you control enter as a copy of this creature.', ('6', '6'), 'G'),
    real('Dracoplasm', '{U}{R}', 2, 'Creature — Shapeshifter',
         "Flying\nAs this creature enters, sacrifice any number of creatures. This creature's power becomes the total power of those creatures and its toughness becomes their total toughness.\n{R}: This creature gets +1/+0 until end of turn.", ('0', '0'), 'RU'),
    real('Test Giant 110F', '{3}{R}', 4, 'Creature — Giant', 'Vigilance', ('3', '3'), 'R'),
    real('Test Flash Bear 110F', '{1}{U}', 2, 'Creature — Bear', 'Flash', ('2', '2'), 'U'),
]
_BASE.extend(EXTRA)
NAMES = ["Blink", "Unyielding Gatekeeper", "Sparkshaper Visionary", "Essence of the Wild", "Dracoplasm"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _resolve(s, pick=None):
    for _ in range(14):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick or d.options[0].id])


def test_blink_chapter_one_shuffles_target_and_its_owner_investigates(cards):
    """701.24, 701.16a: the owner (p2) shuffles the creature away, then p2 (not the Saga's controller) gets the Clue."""
    s = build(cards, ["Blink", "Grizzly Bears"], ["Grizzly Bears"], forests=20, islands=20)
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, B=1, C=2)
    cast(s, "Blink")
    _resolve(s, bear.id)
    assert s.state.cards[bear.id].zone == "p2:library"
    clues = [c for c in s.state.cards.values() if c.name == "Clue"]
    assert [c.controller for c in clues] == ["p2"]
    check(s)


def test_blink_chapter_two_token_stops_being_a_creature_when_opponent_casts_a_creature(cards):
    """205.1b, 611.2a: the Alien Angel (2/2, first strike, vigilance) is no creature until end of turn once an opponent casts a creature spell."""
    from tests.test_rules_wave100f_control import ch

    s = build(cards, ["Blink", "Grizzly Bears"], ["Grizzly Bears", "Test Flash Bear 110F"], forests=20, islands=20)
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, B=1, C=2)
    cast(s, "Blink")
    _resolve(s, bear.id)
    act(s, "p2", type="set_stops", others=["end"], smart_pass=False)
    to_phase(s, "main1", turn=3)
    _resolve(s)
    angel = next(c for c in s.state.cards.values() if c.name == "Alien Angel")
    got = ch(s, angel)
    assert "Creature" in got.types and got.pt == (2, 2) and {"first strike", "vigilance"} <= set(got.keywords)
    to_phase(s, "end", turn=3)
    mana(s, U=1, C=1, pid="p2")
    cast(s, "Test Flash Bear 110F", pid="p2")
    _resolve(s)
    assert "Creature" not in ch(s, angel).types and "Artifact" in ch(s, angel).types
    check(s)


@pytest.mark.parametrize("mine", [True, False])
def test_gatekeeper_returns_your_permanent_tapped_or_gives_its_controller_a_detective(cards, mine):
    """Exiling your own permanent returns it tapped (no Detective); exiling an opponent's gives that opponent the 2/2 Detective."""
    s = build(cards, ["Unyielding Gatekeeper", "Grizzly Bears"], ["Grizzly Bears"])
    mana(s, C=3)
    gate = to_hand(s, "Unyielding Gatekeeper")
    act(s, "p1", type="cast_spell", card_id=gate.id, face_down=True)
    _resolve(s)
    bear = put(s, "Grizzly Bears", "p1" if mine else "p2")
    mana(s, W=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=gate.id, method="disguise")
    _resolve(s, bear.id)
    detectives = [c for c in s.state.cards.values() if c.name == "Detective"]
    if mine:
        assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped and not detectives
    else:
        assert s.state.cards[bear.id].zone == "p2:exile" and [c.controller for c in detectives] == ["p2"]
    check(s)


@pytest.mark.parametrize("pick", [True, False])
def test_sparkshaper_turns_chosen_planeswalkers_into_birds_for_the_turn(cards, pick):
    """Any number (zero too) of targets; a chosen walker is a 3/3 flying hexproof Bird creature, not a planeswalker, until end of turn."""
    from tests.test_rules_wave100f_control import ch

    s = build(cards, ["Sparkshaper Visionary", "Test Walker 110F"])
    put(s, "Sparkshaper Visionary")
    walker = put(s, "Test Walker 110F")
    act(s, "p1", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    to_phase(s, "main1", turn=3)
    for _ in range(14):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[walker.id] if pick and d.options else [])
    got = ch(s, walker)
    assert ("Creature" in got.types) is pick and ("Planeswalker" in got.types) is not pick
    if pick:
        assert got.pt == (3, 3) and {"flying", "hexproof"} <= set(got.keywords) and "Bird" in got.subtypes
    check(s)


@pytest.mark.parametrize("pid,copied", [("p1", True), ("p2", False)])
def test_essence_makes_only_its_controllers_creatures_enter_as_copies(cards, pid, copied):
    """614.1c: a Bear entering under Essence's controller is a 6/6 copy of Essence (and copies again, 707.2); an opponent's Bear is unchanged."""
    from tests.test_rules_wave100f_control import ch

    s = build(cards, ["Essence of the Wild", "Grizzly Bears"], ["Grizzly Bears"], forests=20, islands=20)
    put(s, "Essence of the Wild")
    if pid == "p2":
        to_phase(s, "main1", turn=2)
    mana(s, pid, G=2)
    bear = cast(s, "Grizzly Bears", pid=pid)
    _resolve(s)
    got = ch(s, s.state.cards[bear.id])
    assert s.state.cards[bear.id].zone == f"{pid}:battlefield"
    assert (got.name, got.pt) == (("Essence of the Wild", (6, 6)) if copied else ("Grizzly Bears", (2, 2)))
    check(s)


@pytest.mark.parametrize("sacrifice,pt", [(("Grizzly Bears", "Test Giant 110F"), (5, 5)), (("Test Giant 110F",), (3, 3)), ((), None)])
def test_dracoplasm_takes_the_total_power_and_toughness_of_what_it_sacrificed(cards, sacrifice, pt):
    """The totals are fixed as it enters (2/2 + 3/3 = 5/5); sacrificing nothing leaves 0/0, which dies (704.5f)."""
    from tests.test_rules_wave100f_control import ch

    s = build(cards, ["Dracoplasm", "Grizzly Bears", "Test Giant 110F"])
    fodder = {n: put(s, n) for n in ("Grizzly Bears", "Test Giant 110F")}
    mana(s, U=1, R=1)
    draco = cast(s, "Dracoplasm")
    todo = [fodder[n].id for n in sacrifice]
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[todo.pop(0) if todo else "done"])
    _resolve(s)
    for n, c in fodder.items():
        assert s.state.cards[c.id].zone == ("p1:graveyard" if n in sacrifice else "p1:battlefield")
    if pt is None:
        assert s.state.cards[draco.id].zone == "p1:graveyard"
    else:
        assert ch(s, s.state.cards[draco.id]).pt == pt
    check(s)
