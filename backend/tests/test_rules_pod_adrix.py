"""The pod's Adrix and Nev deck (tests/fixtures/soak_decks/adrix_nev_super_clons.txt): its plan, with real Oracle text.

Token doublers (Adrix and Nev, Primal Vigor, and copies of Adrix) stack: each one doubles what the others already doubled (616.1f: one
replacement applies, then the rest are checked again). Esix's "instead create copies" is one more token replacement; the controller picks
the order (616.1e) and gets the same number either way. Clone and copy spells aimed at token makers (Rite of Replication on Rampaging
Baloths, Scute Swarm copying itself) compound. A copy of a creature spell becomes a token but isn't "created" (111.13), so Double Major's
copy isn't doubled. Biovisionary is the alternate win.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.pod_c_kit import card, cast, ch, field, hold, mana, named, put, settle, table, to_hand, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

EXTRA = [
    real('Adrix and Nev, Twincasters', '{2}{G}{U}', 4, 'Legendary Creature — Merfolk Wizard',
         'Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\n'
         'If one or more tokens would be created under your control, twice that many of those tokens are created instead.', ("2", "2"), 'GU'),
    real('Primal Vigor', '{4}{G}', 5, 'Enchantment',
         'If one or more tokens would be created, twice that many of those tokens are created instead.\nIf one or more +1/+1 counters would be put on '
         'a creature, twice that many +1/+1 counters are put on that creature instead.', None, 'G'),
    real('Awaken the Woods', '{X}{G}{G}', 2, 'Sorcery',
         "Create X 1/1 green Forest Dryad land creature tokens. (They're affected by summoning sickness.)", None, 'G'),
    real('Esix, Fractal Bloom', '{4}{G}{U}', 6, 'Legendary Creature — Fractal',
         'Flying\nThe first time you would create one or more tokens during each of your turns, you may instead choose a creature other than Esix '
         'and create that many tokens that are copies of that creature.', ("4", "4"), 'GU'),
    real('Biovisionary', '{1}{G}{U}', 3, 'Creature — Human Wizard',
         'At the beginning of the end step, if you control four or more creatures named Biovisionary, you win the game.', ("2", "3"), 'GU'),
    real('Scute Swarm', '{2}{G}', 3, 'Creature — Insect',
         "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a "
         "token that's a copy of this creature instead.", ("1", "1"), 'G'),
    real('Spark Double', '{3}{U}', 4, 'Creature — Illusion',
         "You may have this creature enter as a copy of a creature or planeswalker you control, except it enters with an additional +1/+1 counter "
         "on it if it's a creature, it enters with an additional loyalty counter on it if it's a planeswalker, and it isn't legendary.", ("0", "0"), 'U'),
    real('Double Major', '{G}{U}', 2, 'Instant',
         "Copy target creature spell you control, except it isn't legendary if the spell is legendary. (A copy of a creature spell becomes a token.)",
         None, 'GU'),
    real('Mister Fantastic, Reed Richards', '{3}{U}', 4, 'Legendary Creature — Human Scientist Hero',
         'Reach\nWhenever one or more tokens you control enter, you may draw a card.', ("2", "4"), 'U'),
    real('Rite of Replication', '{2}{U}{U}', 4, 'Sorcery',
         "Kicker {5} (You may pay an additional {5} as you cast this spell.)\nCreate a token that's a copy of target creature. If this spell was "
         "kicked, create five of those tokens instead.", None, 'U'),
    real('Rampaging Baloths', '{4}{G}{G}', 6, 'Creature — Beast',
         'Trample\nLandfall — Whenever a land you control enters, create a 4/4 green Beast creature token.', ("6", "6"), 'G'),
    real('Helm of the Host', '{4}', 4, 'Legendary Artifact — Equipment',
         "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That "
         "token gains haste.\nEquip {5}", None, ''),
    real('Echocasting Symposium', '{4}{U}{U}', 6, 'Sorcery — Lesson',
         "Target player creates a token that's a copy of target creature you control.\nParadigm (Then exile this spell. After you first resolve a "
         "spell with this name, you may cast a copy of it from exile without paying its mana cost at the beginning of each of your first main "
         "phases.)", None, 'U'),
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


def adrix(cards, *mine, theirs=()):
    s = table(cards, ["Adrix and Nev, Twincasters", *mine], theirs)
    put(s, "Adrix and Nev, Twincasters")
    return s


def test_adrix_and_primal_vigor_each_double(cards):
    """616.1f: Adrix doubles one Dryad to two, then Primal Vigor doubles those to four."""
    s = adrix(cards, "Primal Vigor", "Awaken the Woods")
    put(s, "Primal Vigor")
    mana(s, G=3)
    cast(s, "Awaken the Woods", x_value=1)
    assert field(s)["Forest Dryad"] == 4
    check(s)


def test_esix_and_both_doublers_make_four_biovisionaries_and_win(cards):
    """616.1e: the three token replacements are offered in the order Alice picks; Esix's copies of Biovisionary are still doubled twice. With
    five creatures named Biovisionary, its end step trigger wins the game (104.2b)."""
    s = adrix(cards, "Primal Vigor", "Awaken the Woods", "Esix, Fractal Bloom", "Biovisionary")
    for name in ("Primal Vigor", "Esix, Fractal Bloom", "Biovisionary"):
        put(s, name)
    mana(s, G=3)
    asked = cast(s, "Awaken the Woods", "Apply Esix", "Biovisionary", x_value=1)
    assert any("token replacement" in p for p in asked)
    assert field(s)["Biovisionary"] == 5 and field(s)["Forest Dryad"] == 0
    check(s)
    until(s, "p2", "main1")
    assert s.state.rules.winner == "p1"


def test_scute_swarm_copies_are_doubled_and_compound(cards):
    """Six lands: each Scute Swarm landfall makes a copy of itself, doubled by Adrix (1 → 3); the next land triggers all three (3 → 9)."""
    s = adrix(cards, "Scute Swarm", "Rampant Growth")
    put(s, "Scute Swarm")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[f.id for f in forests[:5]], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[forests[5].id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forests[5].id)
    settle(s)
    assert field(s)["Scute Swarm"] == 3
    mana(s, G=2)
    cast(s, "Rampant Growth", "Forest")
    assert field(s)["Scute Swarm"] == 9 and all(ch(s, c).power == "1" for c in named(s, "Scute Swarm"))
    check(s)


def test_spark_double_as_adrix_doubles_again(cards):
    """Spark Double copies Adrix (not legendary, an extra +1/+1 counter); two doublers turn one Dryad into four."""
    s = adrix(cards, "Spark Double", "Awaken the Woods")
    mana(s, U=4)
    cast(s, "Spark Double", "Adrix and Nev")
    double = card(s, "Spark Double")
    assert ch(s, double).name == "Adrix and Nev, Twincasters" and "Legendary" not in ch(s, double).supertypes
    assert s.state.cards[double.id].counters == {"+1/+1": 1}
    mana(s, G=3)
    cast(s, "Awaken the Woods", x_value=1)
    assert field(s)["Forest Dryad"] == 4
    check(s)


def test_double_majors_copy_isnt_created_so_it_isnt_doubled(cards):
    """111.13: the copy of a creature spell becomes a token as it resolves but isn't "created": Adrix doesn't double it. It still enters,
    so Mister Fantastic's "tokens you control enter" triggers once."""
    s = adrix(cards, "Biovisionary", "Double Major", "Mister Fantastic, Reed Richards")
    put(s, "Mister Fantastic, Reed Richards")
    hold(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=2, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Biovisionary").id)
    cast(s, "Double Major", "Yes", targets=[card(s, "Biovisionary").id])
    assert field(s)["Biovisionary"] == 2
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (two cards moved to the hand and cast, one drawn)
    check(s)


def test_rite_on_rampaging_baloths_then_landfall(cards):
    """Rite of Replication on Rampaging Baloths: two token Baloths. A land then triggers all three, each Beast doubled: six Beasts."""
    s = adrix(cards, "Rite of Replication", "Rampaging Baloths")
    baloths = put(s, "Rampaging Baloths")
    mana(s, U=4)
    cast(s, "Rite of Replication", targets=[baloths.id])
    assert field(s)["Rampaging Baloths"] == 3
    forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert field(s)["Beast"] == 6
    check(s)


def test_helm_of_the_host_on_adrix_makes_two_hasty_nonlegendary_copies(cards):
    s = adrix(cards, "Helm of the Host")
    helm = put(s, "Helm of the Host")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=helm.id, ability=1, targets=[card(s, "Adrix and Nev, Twincasters").id])
    settle(s)
    until(s, "p1", "main2")
    adrixes = named(s, "Adrix and Nev, Twincasters")
    tokens = [c for c in adrixes if c.is_token]
    assert len(adrixes) == 3 and len(tokens) == 2
    assert all("Legendary" not in ch(s, c).supertypes and "haste" in ch(s, c).granted for c in tokens)
    check(s)


def test_echocasting_symposium_for_an_opponent_isnt_doubled(cards):
    """Adrix doubles only tokens created under Alice's control: Bob's copy is one token."""
    s = adrix(cards, "Echocasting Symposium")
    mana(s, U=6)
    cast(s, "Echocasting Symposium", targets=["p2", card(s, "Adrix and Nev, Twincasters").id], target_counts=[1, 1])
    assert field(s, "p2")["Adrix and Nev, Twincasters"] == 1 and field(s)["Adrix and Nev, Twincasters"] == 1
    check(s)
