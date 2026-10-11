"""Wave 35C: damage that is replaced by instructions (CR 614.1a, 614.6, 616.1, 120.3), real Oracle text (tests/fixtures/wave35c_cards.json). Every scenario checks
the replay and a save and a load.

* "If damage would be dealt to this creature, put that many +1/+1 counters on it instead." (Phytohydra; -1/-1: Lichenthrope), "… dealt to you, put that many
  depletion counters on this enchantment instead." (Force Bubble), "… to a player, that player exiles that many cards from the top of their library instead."
  (Crumbling Sanctuary), "If a source you control would deal noncombat damage to a creature an opponent controls, put that many -1/-1 counters on that creature
  instead." (Soul-Scar Mage), "If Szadek would deal combat damage to a player, instead put that many +1/+1 counters on Szadek and that player mills that many
  cards.": the damage is never dealt (614.6: no lifelink, nothing that needs it), the instructions count it as the replacement applies.
* 616.1: Furnace of Rath's doubling and Phytohydra's counters both apply to one Bolt, and the results differ (6 counters or 3): the creature's controller chooses.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded
from tests.wave35c_kit import bolt, repository

FULL = ["Phytohydra", "Lichenthrope", "Force Bubble", "Crumbling Sanctuary", "Soul-Scar Mage", "Szadek, Lord of Secrets"]


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters(s, name, kind, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get(kind, 0)


def marked(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].damage


def test_phytohydra_grows_instead_of_taking_damage(cards):
    s = build(cards, ["Phytohydra", "Lightning Bolt"], [])
    hydra = put(s, "Phytohydra")
    bolt(s, hydra.id)
    assert counters(s, "Phytohydra", "+1/+1") == 3 and marked(s, "Phytohydra") == 0
    s = reloaded(s)
    check(s)


def test_lichenthrope_shrinks_instead_of_taking_damage(cards):
    s = build(cards, ["Lichenthrope", "Lightning Bolt"], [])
    thrope = put(s, "Lichenthrope")
    act(s, "p1", type="counter", card_ids=[thrope.id], kind="+1/+1", delta=4)  # (a 5/5: it survives the three -1/-1 counters)
    bolt(s, thrope.id)
    assert counters(s, "Lichenthrope", "-1/-1") == 0 and counters(s, "Lichenthrope", "+1/+1") == 1  # (704.5q: removed in pairs) 4 - 3
    assert marked(s, "Lichenthrope") == 0
    check(s)


def test_force_bubble_takes_the_damage_for_you_and_goes_at_four_counters(cards):
    s = build(cards, ["Force Bubble", "Lightning Bolt", "Lightning Bolt"], [])
    put(s, "Force Bubble")
    bolt(s, "p1")
    assert life(s) == 40 and counters(s, "Force Bubble", "depletion") == 3
    s = reloaded(s)
    bolt(s, "p1")  # 6 depletion counters: four or more, sacrificed (the life stays)
    assert life(s) == 40 and card_named(s, "Force Bubble").zone == "p1:graveyard"
    check(s)


def test_crumbling_sanctuary_exiles_the_top_of_their_library_instead(cards):
    s = build(cards, ["Crumbling Sanctuary", "Lightning Bolt"], [])
    put(s, "Crumbling Sanctuary")
    library = len(s.state.zones["p2:library"])
    bolt(s, "p2")
    assert life(s, "p2") == 40 and len(s.state.zones["p2:library"]) == library - 3 and len(s.state.zones["p2:exile"]) == 3
    check(s)


def test_soul_scar_mage_puts_counters_on_an_opponents_creature_not_on_yours(cards):
    s = build(cards, ["Soul-Scar Mage", "Grizzly Bears", "Lightning Bolt", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Soul-Scar Mage")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[theirs.id], kind="+1/+1", delta=4)  # (a 6/6: it survives, and counters and damage can be told apart)
    bolt(s, theirs.id)
    assert s.state.cards[theirs.id].damage == 0 and s.state.cards[theirs.id].counters == {"+1/+1": 1}  # three -1/-1 counters, removed in pairs (704.5q)
    s = reloaded(s)
    bolt(s, mine.id)  # a creature of its own is dealt damage as usual (and dies); so is the opponent
    assert s.state.cards[mine.id].zone == "p1:graveyard"
    bolt(s, "p2")
    assert life(s, "p2") == 37
    check(s)


def through_combat(s, limit=60):
    """Play on to the second main phase; nobody blocks."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def test_szadek_grows_and_mills_instead_of_dealing_combat_damage(cards):
    """614.1a: a self-replacement of the damage Szadek would deal: no damage is dealt to Bob (his life is the same), Szadek gets that many counters and Bob mills
    that many cards (power 3 here: Szadek is a 3/3 flier)."""
    s = build(cards, ["Szadek, Lord of Secrets"], [])
    szadek = put(s, "Szadek, Lord of Secrets")
    s.state.rules.controlled_since[szadek.id].turn = 0
    library = len(s.state.zones["p2:library"])
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": szadek.id, "target": "p2"}])
    through_combat(s)
    n = counters(s, "Szadek, Lord of Secrets", "+1/+1")
    assert n >= 1 and life(s, "p2") == 40 and len(s.state.zones["p2:library"]) == library - n and len(s.state.zones["p2:graveyard"]) == n
    s = reloaded(s)
    check(s)


@pytest.mark.parametrize("first, counters_made", [("Furnace of Rath first", 6), ("Phytohydra first", 3)])
def test_two_replacements_of_one_bolt_ask_the_creatures_controller_which_applies_first(cards, first, counters_made):
    """616.1: Furnace of Rath (the Bolt deals double damage) and Phytohydra (counters instead of damage) both apply to a Bolt at Phytohydra: doubling first makes
    6 counters, counters first makes 3 (nothing is left to double, 614.5). Alice, its controller, is asked; the question names both."""
    s = build(cards, ["Phytohydra", "Furnace of Rath", "Lightning Bolt"], [])
    hydra = put(s, "Phytohydra")
    put(s, "Furnace of Rath")
    mana(s, "p1", R=1)
    from tests.wave9c_kit import to_hand

    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[hydra.id])
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    labels = {o.id: o.label for o in d.options}
    assert any("Furnace of Rath first" in v for v in labels.values()) and any("Phytohydra first" in v for v in labels.values()), labels
    s = reloaded(s)  # the question survives a save and a load
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if first in o.label)])
    settle(s)
    assert counters(s, "Phytohydra", "+1/+1") == counters_made and marked(s, "Phytohydra") == 0
    check(s)
