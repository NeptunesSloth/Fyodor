"""The pod's Kiora deck (tests/fixtures/soak_decks/kiora_underdasea.txt): its plan, with real Oracle text.

Kiora, Sovereign of the Deep turns each Kraken, Leviathan, Octopus or Serpent spell cast from the hand into a free spell from the top X cards
(X: that spell's mana value, its last known one if it's gone: 608.2h), cast while the trigger resolves (608.2g: so a sorcery can be cast on
Bob's turn). A spell cast that way, by cascade (Imoti) or from exile isn't cast from the hand, so it doesn't trigger Kiora again. The rest of the
deck ramps into sea creatures that dodge blockers (Serpent of Yawning Depths) and multiply (Spawning Kraken, doubled by Adrix and Nev).
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.views import build_view
from app.rules import coverage
from tests.game_helpers import act
from tests.pod_c_kit import (
    card,
    cast,
    ch,
    field,
    hold,
    mana,
    on_top,
    put,
    settle,
    table,
    to_hand,
    until,
    zone_names,
)
from tests.test_rules_pod_adrix import EXTRA as ADRIX_EXTRA
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

KIORA = "Kiora, Sovereign of the Deep"
EXTRA = [
    real(KIORA, '{3}{G}{U}', 5, 'Legendary Creature — Merfolk Noble',
         "Vigilance, ward {3}\nWhenever you cast a Kraken, Leviathan, Octopus, or Serpent spell from your hand, look at the top X cards of your "
         "library, where X is that spell's mana value. You may cast a spell with mana value less than X from among them without paying its mana "
         "cost. Put the rest on the bottom of your library in a random order.", ("4", "5"), 'GU'),
    real('Tidal Kraken', '{5}{U}{U}{U}', 8, 'Creature — Kraken', "This creature can't be blocked.", ("6", "6"), 'U'),
    real('Stormsurge Kraken', '{3}{U}{U}', 5, 'Creature — Kraken',
         'Hexproof\nLieutenant — As long as you control your commander, this creature gets +2/+2 and has "Whenever this creature becomes blocked, '
         'you may draw two cards."', ("5", "5"), 'U'),
    real('Nadir Kraken', '{1}{U}{U}', 3, 'Creature — Kraken',
         'Whenever you draw a card, you may pay {1}. If you do, put a +1/+1 counter on this creature and create a 1/1 blue Tentacle creature token.',
         ("2", "3"), 'U'),
    real('Harmonize', '{2}{G}{G}', 4, 'Sorcery', 'Draw three cards.', None, 'G'),
    real('Imoti, Celebrant of Bounty', '{3}{G}{U}', 5, 'Legendary Creature — Snake Druid',
         'Cascade (When you cast this spell, exile cards from the top of your library until you exile a nonland card that costs less. You may cast '
         'it without paying its mana cost. Put the exiled cards on the bottom in a random order.)\nSpells you cast with mana value 6 or greater have '
         'cascade.', ("3", "1"), 'GU'),
    real('Scourge of Fleets', '{5}{U}{U}', 7, 'Creature — Kraken',
         "When this creature enters, return each creature your opponents control with toughness X or less to its owner's hand, where X is the "
         "number of Islands you control.", ("6", "6"), 'U'),
    real('Spawning Kraken', '{5}{U}', 6, 'Creature — Kraken',
         'Whenever a Kraken, Leviathan, Octopus, or Serpent you control deals combat damage to a player, create a 9/9 blue Kraken creature token.',
         ("6", "6"), 'U'),
    real('Serpent of Yawning Depths', '{4}{U}{U}', 6, 'Enchantment Creature — Serpent',
         "Krakens, Leviathans, Octopuses, and Serpents you control can't be blocked except by Krakens, Leviathans, Octopuses, and Serpents.",
         ("6", "6"), 'U'),
    real('Concordant Crossroads', '{G}', 1, 'World Enchantment', 'All creatures have haste.', None, 'G'),
    real('Stormtide Leviathan', '{5}{U}{U}{U}', 8, 'Creature — Leviathan',
         "Islandwalk (This creature can't be blocked as long as defending player controls an Island.)\nAll lands are Islands in addition to their "
         "other types.\nCreatures without flying or islandwalk can't attack.", ("8", "8"), 'U'),
    real('Hullbreaker Horror', '{5}{U}{U}', 7, 'Creature — Kraken Horror',
         "Flash\nThis spell can't be countered.\nWhenever you cast a spell, choose up to one —\n• Return target spell you don't control to its "
         "owner's hand.\n• Return target nonland permanent to its owner's hand.", ("7", "8"), 'U'),
    real('Arixmethes, Slumbering Isle', '{2}{G}{U}', 4, 'Legendary Creature — Kraken',
         "Arixmethes enters tapped with five slumber counters on it.\nAs long as Arixmethes has a slumber counter on it, it's a land. (It's not a "
         "creature.)\nWhenever you cast a spell, you may remove a slumber counter from Arixmethes.\n{T}: Add {G}{U}.", ("12", "12"), 'GU'),
    real('Whelming Wave', '{2}{U}{U}', 4, 'Sorcery',
         "Return all creatures to their owners' hands except for Krakens, Leviathans, Octopuses, and Serpents.", None, 'U'),
]
NAMES = [c["name"] for c in EXTRA]
ADRIX = next(c for c in ADRIX_EXTRA if c["name"] == "Adrix and Nev, Twincasters")
FREE = "Choose a spell to cast without paying its mana cost"


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, ADRIX], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def kiora(cards, *mine, theirs=()):
    s = table(cards, mine, theirs, commander=KIORA)
    put(s, KIORA)
    return s


def offered(s):
    d = s.state.rules.decision
    return sorted(o.label for o in d.options) if d is not None and d.prompt.startswith(FREE) else None


def test_kiora_casts_a_cheaper_spell_from_the_top_and_bottoms_the_rest(cards):
    """Tidal Kraken (mana value 8): the top eight cards; the nonland ones with mana value less than 8 are offered. Stormsurge Kraken cast
    this way isn't cast from the hand: no second trigger. Bob never sees the cards Alice looked at."""
    s = kiora(cards, "Tidal Kraken", "Harmonize", "Stormsurge Kraken", "Sol Ring")
    on_top(s, "Harmonize", "Stormsurge Kraken", "Sol Ring")
    mana(s, U=3, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Tidal Kraken").id)
    settle(s, stop_at=FREE)
    assert offered(s) == ["Harmonize", "Sol Ring", "Stormsurge Kraken"]
    asked = settle(s, "Stormsurge Kraken")
    assert sum(p.startswith(FREE) for p in asked) == 1
    assert field(s)["Stormsurge Kraken"] == 1 and field(s)["Tidal Kraken"] == 1
    bottom = [s.state.cards[i].name for i in s.state.zones["p1:library"][-7:]]
    assert sorted(bottom) == ["Forest"] * 5 + ["Harmonize", "Sol Ring"]
    seen = json.dumps(build_view(s.state, "p2"), default=str)
    assert "Harmonize" not in seen and "Sol Ring" not in seen
    check(s)


def test_kiora_offers_only_lower_mana_values(cards):
    """Nadir Kraken (3): Murder (3) and Harmonize (4) aren't offered; Grizzly Bears (2) is."""
    s = kiora(cards, "Nadir Kraken", "Harmonize", "Murder", "Grizzly Bears")
    on_top(s, "Harmonize", "Murder", "Grizzly Bears")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Nadir Kraken").id)
    settle(s, stop_at=FREE)
    assert offered(s) == ["Grizzly Bears"]
    settle(s, lambda d: [])
    assert field(s)["Nadir Kraken"] == 1 and field(s)["Grizzly Bears"] == 0
    check(s)


def test_imoti_cascade_chains_off_kiora_without_retriggering_her(cards):
    """Imoti: the free Scourge of Fleets (mana value 7) has cascade too; the Stormsurge Kraken cascade casts comes from exile, so Kiora triggers
    only for Tidal Kraken."""
    s = kiora(cards, "Tidal Kraken", "Imoti, Celebrant of Bounty", "Scourge of Fleets", "Stormsurge Kraken")
    put(s, "Imoti, Celebrant of Bounty")
    on_top(s, "Forest", "Scourge of Fleets", "Stormsurge Kraken")
    mana(s, U=3, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Tidal Kraken").id)
    asked = settle(s, "Scourge of Fleets", "Cast it")
    assert sum(p.startswith(FREE) for p in asked) == 1
    assert {"Tidal Kraken", "Scourge of Fleets", "Stormsurge Kraken"} <= set(field(s))
    check(s)


def test_kiora_reads_the_countered_krakens_last_known_mana_value(cards):
    """608.2h: Bob counters Tidal Kraken in response; Kiora's trigger still looks at eight cards."""
    s = kiora(cards, "Tidal Kraken", "Stormsurge Kraken", theirs=["Counterspell"])
    hold(s)
    act(s, "p2", type="set_prefs", response="on")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    on_top(s, "Stormsurge Kraken")
    tidal = to_hand(s, "Tidal Kraken")
    mana(s, U=3, C=5)
    act(s, "p1", type="cast_spell", card_id=tidal.id)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[tidal.id])
    settle(s, "Stormsurge Kraken")
    assert s.state.cards[tidal.id].zone == "p1:graveyard" and field(s)["Stormsurge Kraken"] == 1
    check(s)


def test_kiora_casts_a_sorcery_on_bobs_turn_off_a_flashed_hullbreaker(cards):
    """608.2g: a spell cast while the trigger resolves ignores its card type's timing, so Harmonize is cast in Bob's main phase."""
    s = kiora(cards, "Hullbreaker Horror", "Harmonize", theirs=["Grizzly Bears"])
    on_top(s, "Harmonize")
    until(s, "p2", "main1")
    hold(s, "p2")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Grizzly Bears", "p2").id)
    act(s, "p2", type="pass_priority")
    mana(s, U=2, C=5)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hullbreaker Horror").id)
    settle(s, "Harmonize", lambda d: [])
    assert card(s, "Harmonize").zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 3
    check(s)


def test_spawning_kraken_doubled_and_serpent_of_yawning_depths_blocks(cards):
    """Bob's Grizzly Bears can't block a Serpent; each sea creature that connects makes a 9/9 Kraken, doubled by Adrix: four."""
    s = kiora(cards, "Spawning Kraken", "Tidal Kraken", "Serpent of Yawning Depths", "Concordant Crossroads", "Adrix and Nev, Twincasters",
              theirs=["Grizzly Bears"])
    for name in ("Spawning Kraken", "Tidal Kraken", "Serpent of Yawning Depths", "Concordant Crossroads", "Adrix and Nev, Twincasters"):
        put(s, name)
    bears = put(s, "Grizzly Bears", "p2")
    attackers = [card(s, "Tidal Kraken"), card(s, "Serpent of Yawning Depths")]
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    with pytest.raises(ActionError) as refused:
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": attackers[1].id}])
    assert "except by Krakens, Leviathans, Octopuses or Serpents" in str(refused.value)  # (said in words, not "Serpent Octopus Leviathan Krakens")
    act(s, "p2", type="declare_blockers", blocks=[])
    until(s, "p1", "main2")
    assert s.state.players["p2"].life == 28 and field(s)["Kraken"] == 4
    check(s)


def test_stormtide_makes_scourge_of_fleets_count_every_land(cards):
    """All lands are Islands: three Forests make X = 3, so Scourge returns Grizzly Bears and Albino Troll (toughness 2 and 3), not Courser of
    Kruphix (4)."""
    s = kiora(cards, "Stormtide Leviathan", "Scourge of Fleets", theirs=["Grizzly Bears", "Albino Troll", "Courser of Kruphix"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    put(s, "Stormtide Leviathan")
    for name in ("Grizzly Bears", "Albino Troll", "Courser of Kruphix"):
        put(s, name, "p2")
    assert "Island" in ch(s, forests[0]).subtypes
    mana(s, U=2, C=5)
    cast(s, "Scourge of Fleets")
    assert {"Grizzly Bears", "Albino Troll"} <= set(zone_names(s, "p2", "hand"))
    assert field(s, "p2")["Courser of Kruphix"] == 1
    check(s)


def test_arixmethes_asks_to_remove_a_slumber_counter_in_words(cards):
    """Arixmethes is a Kraken spell (it would trigger Kiora) and a land while it slumbers; its cast trigger's question reads as English."""
    s = kiora(cards, "Arixmethes, Slumbering Isle", "Harmonize")
    hold(s)
    mana(s, G=1, U=1, C=2)
    cast(s, "Arixmethes, Slumbering Isle", lambda d: [])
    arix = card(s, "Arixmethes, Slumbering Isle")
    assert s.state.cards[arix.id].counters == {"slumber": 5} and ch(s, arix).types == frozenset({"Land"})
    mana(s, G=4)
    asked = cast(s, "Harmonize", "Yes")
    assert "Arixmethes, Slumbering Isle: Remove 1 slumber counter(s)?" in asked
    assert s.state.cards[arix.id].counters == {"slumber": 4}
    check(s)
