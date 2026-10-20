"""Mana added by effects (wave 3M): rituals, "for each" amounts, choices, triggers, and mana-ability
wordings (CR 106.3, 605.1a / 605.5). Cards are transcribed from the card database (current Oracle)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, mana_pool, zone
from tests.test_rules_effects import pass_until_stack_empty, rules

REAL = [
    card("Dark Ritual", mana_cost="{B}", cmc=1.0, type_line="Instant", oracle_text="Add {B}{B}{B}.", colors=["B"], color_identity=["B"]),
    card("Seething Song", set_code="mm", mana_cost="{2}{R}", cmc=3.0, type_line="Instant", oracle_text="Add {R}{R}{R}{R}{R}.",
         colors=["R"], color_identity=["R"]),
    card("Cabal Ritual", mana_cost="{1}{B}", cmc=2.0, type_line="Instant", colors=["B"], color_identity=["B"],
         oracle_text="Add {B}{B}{B}.\nThreshold — Add {B}{B}{B}{B}{B} instead if there are seven or more cards in your graveyard."),
    card("Mana Geyser", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Add {R} for each tapped land your opponents control."),
    card("Jeska's Will", mana_cost="{2}{R}", cmc=3.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Choose one. If you control a commander as you cast this spell, you may choose both instead.\n"
                     "• Add {R} for each card in target opponent's hand.\n• Exile the top three cards of your library. You may play them this turn."),
    card("Lotus Cobra", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Snake", power="2", toughness="1", colors=["G"], color_identity=["G"],
         oracle_text="Landfall — Whenever a land you control enters, add one mana of any color."),
    card("Priest of Gix", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Phyrexian Human Cleric Minion", power="2", toughness="1",
         colors=["B"], color_identity=["B"], oracle_text="When this creature enters, add {B}{B}{B}."),
    card("Prismatic Geoscope", mana_cost="{5}", cmc=5.0, type_line="Artifact",
         oracle_text="This artifact enters tapped.\nDomain — {T}: Add X mana in any combination of colors, where X is the number of basic land types among lands you control."),
    card("Everflowing Chalice", mana_cost="{0}", cmc=0.0, type_line="Artifact",
         oracle_text="Multikicker {2} (You may pay an additional {2} any number of times as you cast this spell.)\n"
                     "This artifact enters with a charge counter on it for each time it was kicked.\n{T}: Add {C} for each charge counter on this artifact."),
    card("Wastewood Verge", type_line="Land", color_identity=["B", "G"],
         oracle_text="{T}: Add {G}.\n{T}: Add {B}. Activate only if you control a Swamp or a Forest."),
    card("Temple of the False God", type_line="Land", oracle_text="{T}: Add {C}{C}. Activate only if you control five or more lands."),
    card("Eldrazi Temple", type_line="Land",
         oracle_text="{T}: Add {C}.\n{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi."),
    card("Mana Reflection Test", mana_cost="{1}", cmc=1.0, type_line="Instant", oracle_text="Add one mana of any color."),
    card("Chromatic Surge Test", mana_cost="{1}", cmc=1.0, type_line="Instant",
         oracle_text="Add three mana in any combination of colors."),
    card("Powerstone Test", type_line="Artifact", oracle_text="{T}: Add {C}. This mana can't be spent to cast a nonartifact spell."),
    card("Mox Test Spell", mana_cost="{1}", cmc=1.0, type_line="Instant", oracle_text="Add {R} or {G}."),
    card("Colorless Eldrazi Test", mana_cost="{2}", cmc=2.0, type_line="Creature — Eldrazi", power="3", toughness="3",
         oracle_text=""),
    card("Two Drop Test", mana_cost="{2}", cmc=2.0, type_line="Creature — Bear", power="2", toughness="2", oracle_text=""),
    card("Black Market", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Enchantment", colors=["B"], color_identity=["B"],
         oracle_text="Whenever a creature dies, put a charge counter on this enchantment.\n"
                     "At the beginning of your first main phase, add {B} for each charge counter on this enchantment."),
]


@pytest.fixture()
def mcards(settings: Settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards, spells, library=((10, "Island"),)):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in spells] + list(library))
    bob = deck(cards, "Atraxa, Praetors' Voice", [(12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    act(s, "p1", type="draw", count=len(spells))
    return s


def named(s, name, pid="p1"):
    return next(s.state.cards[c] for c in s.state.cards if s.state.cards[c].name == name and s.state.cards[c].owner == pid)


def give(s, **m):
    act(s, "p1", type="add_mana", player="p1", mana=m)


def pool(s, pid="p1"):
    return mana_pool(s, pid)


def cast_and_resolve(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=named(s, name).id, **kw)
    pass_until_stack_empty(s)


def replay_matches(s):
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_dark_ritual_adds_three_black(mcards):
    s = table(mcards, ["Dark Ritual"])
    give(s, B=1)
    cast_and_resolve(s, "Dark Ritual")
    assert pool(s) == {"B": 3} and named(s, "Dark Ritual").zone == "p1:graveyard"
    replay_matches(s)


def test_seething_song_five_red(mcards):
    s = table(mcards, ["Seething Song"])
    give(s, R=1, C=2)
    cast_and_resolve(s, "Seething Song")
    assert pool(s) == {"R": 5}


def test_cabal_ritual_threshold_line_replaces_the_first_line(mcards):
    """(wave 3R3) Cabal Ritual's threshold line is an "instead" of the line above it (207.2c: the
    ability word has no rules meaning; 614.1a): three {B} with fewer than seven cards in the
    graveyard, five with seven or more (the resolving spell itself is on the stack, not counted)."""
    s = table(mcards, ["Cabal Ritual"], library=((10, "Swamp"),))
    give(s, B=1, C=1)
    cast_and_resolve(s, "Cabal Ritual")
    assert pool(s) == {"B": 3}
    replay_matches(s)
    s = table(mcards, ["Cabal Ritual"], library=((10, "Swamp"),))
    act(s, "p1", type="move", card_ids=list(zone(s.state, "p1", "library"))[:7], to={"zone": "graveyard"})
    give(s, B=1, C=1)
    cast_and_resolve(s, "Cabal Ritual")
    assert pool(s) == {"B": 5}
    replay_matches(s)


def test_mana_geyser_counts_tapped_opponent_lands(mcards):
    s = table(mcards, ["Mana Geyser"])
    for cid in list(zone(s.state, "p2", "library"))[:3]:
        act(s, "p2", type="move", card_ids=[cid], to={"zone": "battlefield"})
    lands = [c for c in zone(s.state, "p2", "battlefield")]
    for cid in lands[:2]:
        act(s, "p2", type="tap", card_ids=[cid], tapped=True)
    give(s, R=2, C=3)
    cast_and_resolve(s, "Mana Geyser")
    assert pool(s) == {"R": 2}
    replay_matches(s)


def test_any_color_asks_and_adds_the_chosen_mana(mcards):
    s = table(mcards, ["Mana Reflection Test"])
    give(s, C=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Mana Reflection Test").id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d is not None and {o.id for o in d.options} == set("WUBRG")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["G"])
    assert pool(s) == {"G": 1} and rules(s).decision is None
    replay_matches(s)


def test_any_combination_asks_once_per_mana(mcards):
    s = table(mcards, ["Chromatic Surge Test"])
    give(s, C=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Chromatic Surge Test").id)
    pass_until_stack_empty(s)
    for pick in ("U", "U", "R"):
        d = rules(s).decision
        assert d is not None
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick])
    assert pool(s) == {"U": 2, "R": 1}


def test_either_of_two_colors(mcards):
    s = table(mcards, ["Mox Test Spell"])
    give(s, C=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Mox Test Spell").id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert {o.id for o in d.options} == {"R", "G"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["R"])
    assert pool(s) == {"R": 1}


def test_etb_trigger_adds_mana(mcards):
    s = table(mcards, ["Priest of Gix"])
    give(s, B=1, C=2)
    cast_and_resolve(s, "Priest of Gix")
    pass_until_stack_empty(s)
    assert pool(s) == {"B": 3}


def test_landfall_trigger_adds_chosen_color(mcards):
    s = table(mcards, ["Lotus Cobra"], library=((10, "Forest"),))
    give(s, G=1, C=1)
    cast_and_resolve(s, "Lotus Cobra")
    forest = named(s, "Forest")
    act(s, "p1", type="draw", count=1)
    act(s, "p1", type="play_land", card_id=forest.id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d is not None and {o.id for o in d.options} == set("WUBRG")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["U"])
    pass_until_stack_empty(s)
    assert pool(s) == {"U": 1}


def test_mana_empties_at_end_of_step(mcards):
    s = table(mcards, ["Dark Ritual"])
    give(s, B=1)
    cast_and_resolve(s, "Dark Ritual")
    assert pool(s) == {"B": 3}
    act(s, "p1", type="pass_priority")  # → combat / next step: unspent mana is lost (106.4)
    for _ in range(3):
        if s.state.turn.phase != "main1":
            break
        act(s, rules(s).priority, type="pass_priority")
    assert s.state.turn.phase != "main1" and pool(s) == {}


def test_for_each_cards_in_hand_amount():
    from app.rules.scripts import parse_effects

    found = parse_effects("Add {R} for each card in your hand.")
    assert found is not None and found[0] == [{"do": "add_mana", "sym": "R", "n": {"hand": "you"}}]
    # (wave 3R3) Jeska's Will's mode: the opponent is the instruction's target
    assert parse_effects("Add {R} for each card in target opponent's hand.")[1] == "opponent"


@pytest.mark.parametrize("text", [
    "add {R}{R}{R}. spend this mana only to cast instant or sorcery spells",
    "add {C} for each creature that died this turn",
    "add one mana of any color. until end of turn, you don't lose this mana as steps and phases end",
])
def test_unsupported_mana_wordings_stay_unparsed(text):
    from app.rules.scripts import parse_effects

    assert parse_effects(text) is None


# -- mana-ability wordings (wave 3M) -----------------------------------------------------------------------
def _abilities(s, cards, name):
    from app.rules.casting import mana_abilities

    return dict(mana_abilities(s.state, named(s, name), cards))


def _to_battlefield(s, *names):
    for n in names:
        act(s, "p1", type="move", card_ids=[named(s, n).id], to={"zone": "battlefield"})


def test_verge_second_ability_needs_a_swamp_or_forest(mcards):
    s = table(mcards, ["Wastewood Verge", "Forest"])
    _to_battlefield(s, "Wastewood Verge")
    assert [ab.options for ab in _abilities(s, mcards, "Wastewood Verge").values()] == [(("G",),)]
    _to_battlefield(s, "Forest")
    got = _abilities(s, mcards, "Wastewood Verge")
    assert sorted(o for ab in got.values() for opt in ab.options for o in opt) == ["B", "G"]


def test_temple_of_the_false_god_needs_five_lands(mcards):
    s = table(mcards, ["Temple of the False God"], library=((10, "Forest"),))
    _to_battlefield(s, "Temple of the False God")
    assert _abilities(s, mcards, "Temple of the False God") == {}
    act(s, "p1", type="draw", count=4)
    for cid in list(zone(s.state, "p1", "hand")):
        if s.state.cards[cid].name == "Forest":
            act(s, "p1", type="move", card_ids=[cid], to={"zone": "battlefield"})
    (ab,) = _abilities(s, mcards, "Temple of the False God").values()
    assert ab.options == (("C", "C"),)


def test_everflowing_chalice_adds_one_per_charge_counter(mcards):
    s = table(mcards, ["Everflowing Chalice"])
    _to_battlefield(s, "Everflowing Chalice")
    assert _abilities(s, mcards, "Everflowing Chalice") == {}  # no counters: nothing to add
    act(s, "p1", type="counter", card_ids=[named(s, "Everflowing Chalice").id], kind="charge", delta=2)
    (ab,) = _abilities(s, mcards, "Everflowing Chalice").values()
    assert ab.options == (("C", "C"),)


def test_eldrazi_temple_restriction_is_enforced_when_paying(mcards):
    from app.rules.casting import castable

    s = table(mcards, ["Eldrazi Temple", "Colorless Eldrazi Test", "Two Drop Test"])
    _to_battlefield(s, "Eldrazi Temple")
    assert castable(s.state, "p1", named(s, "Colorless Eldrazi Test"), mcards)  # the restricted {C}{C} pays for it
    assert not castable(s.state, "p1", named(s, "Two Drop Test"), mcards)  # a non-Eldrazi only gets the plain {C}


def test_powerstone_mana_pays_for_artifacts_and_abilities_only(mcards):
    from app.rules.casting import castable

    s = table(mcards, ["Powerstone Test", "Everflowing Chalice", "Mox Test Spell"])
    _to_battlefield(s, "Powerstone Test")
    assert not castable(s.state, "p1", named(s, "Mox Test Spell"), mcards)  # a nonartifact spell
    assert castable(s.state, "p1", named(s, "Everflowing Chalice"), mcards)  # {0}: free anyway
