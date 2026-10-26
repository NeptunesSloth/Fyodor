"""Wave 110G session 9: cards that need a cause on zone changes or a new prohibition.

* Sacred Ground: 603.2 / 704.3 an opponent's resolving spell or ability that puts a land into your graveyard returns it; your own spell and state-based actions do not.
* Whippoorwill: 701.19c / 615.12 / 614.9 / 700.4 the creature can't regenerate, its damage can't be prevented or dealt instead to another permanent, and it is exiled if it dies.
* Tatsumasa, the Dragon's Fang: 610.3 / 400.7 exiled as a cost, it returns when the Dragon Spirit token dies (not when it is exiled).
* Idol of Endurance: 610.3 creature cards with mana value 3 or less leave your graveyard until it leaves (and go back there); 118.9 one may be cast free this turn.
* Season of the Witch: 508.1 / 502.4 at the end step untapped creatures that could attack but did not are destroyed; summoning-sick ones and the other player's are safe.
* Thijarian Witness: 506.5 / 603.10a a creature that died attacking alone or blocking alone is exiled and investigates; not when another creature was attacking (blocking) too.
* Halfdane: 608.2h / 611.2a the target's power and toughness are read once at resolution and are Halfdane's base values until the end of its controller's next upkeep.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named
from tests.wave110b_kit import attack, cast, check, mana, pt, put, through_combat

EXTRA = [
    real("Sacred Ground", "{1}{W}", 2, "Enchantment", "Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield.", None, "W"),
    real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R"),
    real("Dryad Arbor", "", 0, "Land Creature — Forest Dryad", "(This land isn't a spell, it's affected by summoning sickness, and it has \"{T}: Add {G}.\")", ("1", "1"), "G"),
]
EXTRA += [
    real("Whippoorwill", "{G}", 1, "Creature \u2014 Bird", "{G}{G}, {T}: Target creature can't be regenerated this turn. Damage that would be dealt to that creature this turn can't be "
         "prevented or dealt instead to another permanent or player. When the creature dies this turn, exile the creature.", ("1", "1"), "G"),
    real("Carom", "{1}{W}", 2, "Instant", "The next 1 damage that would be dealt to target creature this turn is dealt to another target creature instead.\nDraw a card.", None, "W"),
    real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
]
EXTRA += [
    real("Thijarian Witness", "{1}{G}", 2, "Creature \u2014 Alien Cleric", "Flash\nBear Witness \u2014 Whenever another creature dies, if it was attacking or blocking alone, exile it and investigate. "
         "(Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")", ("0", "4"), "G"),
    real("Season of the Witch", "{B}{B}{B}", 3, "Enchantment", "At the beginning of your upkeep, sacrifice this enchantment unless you pay 2 life.\n"
         "At the beginning of the end step, destroy all untapped creatures that didn't attack this turn, except for creatures that couldn't attack.", None, "B"),
    real("Tatsumasa, the Dragon's Fang", "{6}", 6, "Legendary Artifact \u2014 Equipment", "Equipped creature gets +5/+5.\n{6}, Exile Tatsumasa: Create a 5/5 blue Dragon Spirit creature token "
         "with flying. Return Tatsumasa to the battlefield under its owner's control when that token dies.\nEquip {3}", None, ""),
    real("Shatter", "{1}{R}", 2, "Instant", "Destroy target artifact.", None, "R"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
    real("Swords to Plowshares", "{W}", 1, "Instant", "Exile target creature. Its controller gains life equal to its power.", None, "W"),
]
EXTRA += [
    real("Idol of Endurance", "{2}{W}", 3, "Artifact", "When this artifact enters, exile all creature cards with mana value 3 or less from your graveyard until this artifact leaves the battlefield.\n"
         "{1}{W}, {T}: Until end of turn, you may cast a creature spell from among cards exiled with this artifact without paying its mana cost.", None, "W"),
]
EXTRA.append(real("Halfdane", "{1}{W}{U}{B}", 4, "Legendary Creature \u2014 Shapeshifter", "At the beginning of your upkeep, Halfdane's base power and toughness become equal to the power and "
                  "toughness of target creature other than Halfdane until the end of your next upkeep.", ("3", "3"), "WUB"))
NAMES = [c["name"] for c in EXTRA if c["name"] not in ("Stone Rain", "Carom", "Hill Giant", "Murder", "Swords to Plowshares", "Shatter")]


def answer(s, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("owner_casts, back", [(False, True), (True, False)])
def test_sacred_ground_returns_a_land_only_when_an_opponents_spell_caused_it(cards, owner_casts, back):
    """Sacred Ground: Stone Rain from the opponent returns your land; your own Stone Rain on it does not."""
    s = build(cards, ["Stone Rain", "Sacred Ground"], ["Sacred Ground"])
    you = "p1" if owner_casts else "p2"
    put(s, "Sacred Ground", you)
    land = put(s, "Forest") if owner_casts else put(s, "Island", "p2")
    mana(s, "p1", C=1, R=1, G=1)
    cast(s, "Stone Rain", [land.id])
    assert s.state.cards[land.id].zone == f"{you}:{'battlefield' if back else 'graveyard'}"
    check(s)


def test_sacred_ground_ignores_a_land_that_dies_to_state_based_damage(cards):
    """Sacred Ground (704.5g): the land creature dies to lethal damage, a state-based action, not as a spell or ability puts it there."""
    s = build(cards, ["Lightning Bolt"], ["Sacred Ground", "Dryad Arbor"])
    put(s, "Sacred Ground", "p2")
    arbor = put(s, "Dryad Arbor", "p2")
    mana(s, "p1", R=1)
    cast(s, "Lightning Bolt", [arbor.id])
    assert s.state.cards[arbor.id].zone == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("firm", [True, False])
def test_whippoorwill_damage_ignores_carom_and_the_creature_is_exiled(cards, firm):
    """Whippoorwill: with it, Bolt's 3 damage stays on the Giant (Carom can't redirect it) and the dead Giant is exiled; without it Carom moves 1."""
    s = build(cards, ["Whippoorwill", "Carom", "Lightning Bolt", "Hill Giant", "Grizzly Bears"])
    from tests.test_rules_conditionals import until

    giant, bears, bird = (put(s, n) for n in ("Hill Giant", "Grizzly Bears", "Whippoorwill"))
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # past summoning sickness
    if firm:
        mana(s, "p1", G=2)
        act(s, "p1", type="activate_ability", card_id=bird.id, ability=0, targets=[giant.id])
        answer(s)
    mana(s, "p1", W=1, C=1, R=1)
    cast(s, "Carom", [giant.id, bears.id], target_counts=[1, 1])
    answer(s)
    cast(s, "Lightning Bolt", [giant.id])
    answer(s)
    got = s.state.cards
    if firm:
        assert got[giant.id].zone == "p1:exile" and got[bears.id].damage == 0
    else:
        assert (got[giant.id].damage, got[bears.id].damage) == (2, 1)
    check(s)


@pytest.mark.parametrize("removal, back", [("Murder", True), ("Swords to Plowshares", False)])
def test_tatsumasa_returns_when_the_dragon_token_dies(cards, removal, back):
    """Tatsumasa: the Dragon Spirit dying returns the exiled Equipment; the token being exiled does not."""
    s = build(cards, ["Tatsumasa, the Dragon's Fang", removal])
    tat = put(s, "Tatsumasa, the Dragon's Fang")
    mana(s, "p1", C=6)
    act(s, "p1", type="activate_ability", card_id=tat.id, ability=1)
    answer(s)
    assert s.state.cards[tat.id].zone == "p1:exile"
    dragon = next(c for c in s.state.cards.values() if c.name == "Dragon Spirit")
    mana(s, "p1", B=2, C=1, W=1)
    cast(s, removal, [dragon.id])
    answer(s)
    assert s.state.cards[tat.id].zone == ("p1:battlefield" if back else "p1:exile")
    check(s)


def test_idol_of_endurance_exiles_small_creatures_casts_one_free_and_gives_the_rest_back(cards):
    """Idol of Endurance: Bears (MV 2) leave the graveyard, Hill Giant (MV 4) stays; Bears can be cast free; when the Idol dies the exiled card returns."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Idol of Endurance", "Grizzly Bears", "Hill Giant", "Murder"], ["Murder"])
    bears, giant, murder = (card_named(s, n) for n in ("Grizzly Bears", "Hill Giant", "Murder"))
    act(s, "p1", type="move", card_ids=[bears.id, giant.id], to={"zone": "graveyard"})
    mana(s, "p1", W=1, C=2)
    cast(s, "Idol of Endurance")
    answer(s)
    assert (s.state.cards[bears.id].zone, s.state.cards[giant.id].zone) == ("p1:exile", "p1:graveyard")
    idol = card_named(s, "Idol of Endurance")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    mana(s, "p1", W=2)
    act(s, "p1", type="activate_ability", card_id=idol.id, ability=1)
    answer(s)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_idol_of_endurance_leaving_returns_the_cards_to_the_graveyard(cards):
    s = build(cards, ["Idol of Endurance", "Grizzly Bears", "Shatter"])
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, "p1", W=1, C=2)
    cast(s, "Idol of Endurance")
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    mana(s, "p1", R=1, C=1)
    cast(s, "Shatter", [card_named(s, "Idol of Endurance").id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("attacks", [True, False])
def test_season_of_the_witch_destroys_only_idle_creatures_that_could_attack(cards, attacks):
    """Season of the Witch: the idle ready Bears dies; the attacker, the summoning-sick Giant and the opponent's Bears live. Without combat damage nothing else changes."""
    s = build(cards, ["Season of the Witch", "Grizzly Bears", "Hill Giant"], ["Grizzly Bears"])
    put(s, "Season of the Witch")
    bears, giant, theirs = put(s, "Grizzly Bears"), put(s, "Hill Giant"), put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    if attacks:
        attack(s, bears)
        through_combat(s)
    for _ in range(40):
        if s.state.turn.number == 2:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    z = {n: s.state.cards[c.id].zone for n, c in (("bears", bears), ("giant", giant), ("theirs", theirs))}
    assert z == {"bears": "p1:battlefield" if attacks else "p1:graveyard", "giant": "p1:battlefield", "theirs": "p2:battlefield"}
    check(s)


@pytest.mark.parametrize("attackers, blocker, exiled, clues", [
    (["Grizzly Bears"], "Hill Giant", ["Grizzly Bears"], 1),                      # attacking alone, dies
    (["Grizzly Bears", "Hill Giant"], "Hill Giant", [], 0),                   # one of two attackers dies
    (["Hill Giant"], "Grizzly Bears", ["Grizzly Bears"], 1),                       # blocking alone, dies
])
def test_thijarian_witness_exiles_the_lone_attacker_or_blocker_that_dies(cards, attackers, blocker, exiled, clues):
    """Thijarian Witness: only a creature that was the lone attacker or lone blocker is exiled with a Clue."""
    s = build(cards, ["Thijarian Witness", *dict.fromkeys(attackers)], [blocker])
    put(s, "Thijarian Witness")
    mine = [put(s, n) for n in dict.fromkeys(attackers)]
    blk = put(s, blocker, "p2")
    attack(s, *mine)
    through_combat(s, [(blk, mine[0])])
    gone = [c.name for c in s.state.cards.values() if c.zone.endswith(":exile")]
    assert sorted(gone) == sorted(exiled)
    assert sum(1 for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield") == clues
    check(s)


def test_halfdane_copies_the_targets_size_at_upkeep_until_the_end_of_its_next_upkeep(cards):
    """Halfdane: 3/3 becomes the 1/1 target's size at the turn-3 upkeep, still when that target changes later, and 3/3 again after the turn-5 upkeep ends (no target left)."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Halfdane", "Hill Giant", "Grizzly Bears"], forests=12, islands=12)
    put(s, "Halfdane")
    giant = put(s, "Hill Giant")
    s.state.cards[giant.id].counters["+1/+1"] = 2  # a 5/5 now
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert pt(s, "Halfdane") == (5, 5)
    s.state.cards[giant.id].counters["+1/+1"] = 0  # the target shrinks: Halfdane keeps what was read (608.2h)
    answer(s)
    assert pt(s, "Halfdane") == (5, 5)
    act(s, "p1", type="move", card_ids=[giant.id], to={"zone": "graveyard"})
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert pt(s, "Halfdane") == (3, 3)
    check(s)
