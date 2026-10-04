"""Wave 9A: wordings that define X by the text, researched against CR 2026-09-25.

* Discover N / "discover X, where X is …" (701.57a, 701.57c): exile from the top until a nonland card with mana value N or
  less; cast it for free (608.2g) or put it into the hand; the rest go to the bottom in a random order.
* Keyword actions sized by the text (107.3c): "bolster X", "amass Orcs X", "connives X", "endures X", "investigate X
  times", each "where X is …" (701.39a, 701.47a, 701.50d, 701.63a, 701.16a).
* "the amount of mana spent to cast this spell / that spell / her" (601.2h) and "creatures that died under your control
  this turn" (700.4) as amounts.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Trumpeting Carnosaur', set_code='tst', number='N01', mana_cost='{4}{R}{R}', cmc=6.0, type_line='Creature — Dinosaur', oracle_text='Trample\nWhen this creature enters, discover 5.\n{2}{R}, Discard this card: It deals 3 damage to target creature or planeswalker.', power='7', toughness='6', colors=['R'], color_identity=['R'], keywords=['Discover', 'Trample']),  # noqa: E501
    card('Monstrous Vortex', set_code='tst', number='N02', mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment', oracle_text="Whenever you cast a creature spell with power 5 or greater, discover X, where X is that spell's mana value. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)", colors=['G'], color_identity=['G'], keywords=['Discover']),  # noqa: E501
    card('Hurl into History', set_code='tst', number='N04', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Instant', oracle_text="Counter target artifact or creature spell. Discover X, where X is that spell's mana value. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)", colors=['U'], color_identity=['U'], keywords=['Discover']),  # noqa: E501
    card('Invade the City', set_code='tst', number='N05', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Sorcery', oracle_text="Amass Zombies X, where X is the number of instant and sorcery cards in your graveyard. (Put X +1/+1 counters on an Army you control. It's also a Zombie. If you don't control an Army, create a 0/0 black Zombie Army creature token first.)", colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Amass']),  # noqa: E501
    card('Warden of the Grove', set_code='tst', number='N07', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Hydra', oracle_text='At the beginning of your end step, put a +1/+1 counter on this creature.\nWhenever another nontoken creature you control enters, it endures X, where X is the number of counters on this creature. (Put X +1/+1 counters on the creature that entered or create an X/X white Spirit creature token.)', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Endure']),  # noqa: E501
    card('Saruman, the White Hand', set_code='tst', number='N08', mana_cost='{1}{U}{B}{R}', cmc=4.0, type_line='Legendary Creature — Avatar Wizard', oracle_text="Whenever you cast a noncreature spell, amass Orcs X, where X is that spell's mana value. (Put X +1/+1 counters on an Army you control. It's also an Orc. If you don't control an Army, create a 0/0 black Orc Army creature token first.)\nGoblins and Orcs you control have ward {2}.", power='2', toughness='5', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Amass']),  # noqa: E501
    card("Spymaster's Vault", set_code='tst', number='N09', mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped unless you control a Swamp.\n{T}: Add {B}.\n{B}, {T}: Target creature you control connives X, where X is the number of creatures that died this turn. (Draw X cards, then discard X cards. Put a +1/+1 counter on that creature for each nonland card discarded this way.)', colors=[], color_identity=['B'], keywords=['Connive']),  # noqa: E501
    card("Sunbringer's Touch", set_code='tst', number='N10', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Sorcery', oracle_text='Bolster X, where X is the number of cards in your hand. Each creature you control with a +1/+1 counter on it gains trample until end of turn. (To bolster X, choose a creature with the least toughness among creatures you control and put X +1/+1 counters on it.)', colors=['G'], color_identity=['G'], keywords=['Bolster']),  # noqa: E501
    card('Manaform Hellkite', set_code='tst', number='N11', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Creature — Dragon', oracle_text='Flying\nWhenever you cast a noncreature spell, create an X/X red Dragon Illusion creature token with flying and haste, where X is the amount of mana spent to cast that spell. Exile that token at the beginning of the next end step.', power='4', toughness='4', colors=['R'], color_identity=['R'], keywords=['Flying']),  # noqa: E501
    card('Toph, Greatest Earthbender', set_code='tst', number='N12', mana_cost='{2}{R}{G}', cmc=4.0, type_line='Legendary Creature — Human Warrior Ally', oracle_text='When Toph enters, earthbend X, where X is the amount of mana spent to cast her.\nLand creatures you control have double strike.', power='3', toughness='3', colors=['G', 'R'], color_identity=['G', 'R'], keywords=['Earthbend']),  # noqa: E501
    card('Memory Deluge', set_code='tst', number='N13', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Instant', oracle_text='Look at the top X cards of your library, where X is the amount of mana spent to cast this spell. Put two of them into your hand and the rest on the bottom of your library in a random order.\nFlashback {5}{U}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['U'], color_identity=['U'], keywords=['Flashback']),  # noqa: E501
    card('Molten Note', set_code='tst', number='N14', mana_cost='{X}{R}{W}', cmc=2.0, type_line='Sorcery', oracle_text='Molten Note deals damage to target creature equal to the amount of mana spent to cast this spell. Untap all creatures you control.\nFlashback {6}{R}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Flashback']),  # noqa: E501
    card('Priest of the Crossing', set_code='tst', number='N15', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Zombie Bird Cleric', oracle_text='Flying\nAt the beginning of each end step, put X +1/+1 counters on each creature you control, where X is the number of creatures that died under your control this turn.', power='3', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Aberrant Manawurm', set_code='tst', number='N16', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Wurm', oracle_text='Trample\nWhenever you cast an instant or sorcery spell, this creature gets +X/+0 until end of turn, where X is the amount of mana spent to cast that spell.', power='2', toughness='5', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('Craterhoof Behemoth', set_code='tst', number='N17', mana_cost='{5}{G}{G}{G}', cmc=8.0, type_line='Creature — Beast', oracle_text='Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.', power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Haste']),  # noqa: E501
    card('Colossal Dreadmaw', set_code='tst', number='N18', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Creature — Dinosaur', oracle_text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)", power='6', toughness='6', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('Runeclaw Bear', set_code='tst', number='N19', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Hit the Mother Lode', set_code='tst', number='N20', mana_cost='{4}{R}{R}{R}', cmc=7.0, type_line='Sorcery', oracle_text="Discover 10. If the discovered card's mana value is less than 10, create a number of tapped Treasure tokens equal to the difference. (To discover 10, exile cards from the top of your library until you exile a nonland card with mana value 10 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)", colors=['R'], color_identity=['R'], keywords=['Treasure', 'Discover']),  # noqa: E501
    card('Dragonscale General', set_code='tst', number='N21', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Human Warrior', oracle_text='At the beginning of your end step, bolster X, where X is the number of tapped creatures you control. (Choose a creature with the least toughness among creatures you control and put X +1/+1 counters on it.)', power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Bolster']),  # noqa: E501
    card('Pantlaza, Sun-Favored', set_code='tst', number='N31', mana_cost='{2}{R}{G}{W}', cmc=5.0, type_line='Legendary Creature — Dinosaur', oracle_text="Whenever Pantlaza or another Dinosaur you control enters, you may discover X, where X is that creature's toughness. Do this only once each turn. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)", power='4', toughness='4', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W'], keywords=['Discover']),  # noqa: E501
    card('Primordial Gnawer', set_code='tst', number='N32', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Insect Horror', oracle_text='When this creature dies, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)', power='5', toughness='2', colors=['B'], color_identity=['B'], keywords=['Discover']),  # noqa: E501
    card('Vile Redeemer', set_code='tst', number='N41', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Eldrazi', oracle_text='Devoid (This card has no color.)\nFlash\nWhen you cast this spell, you may pay {C}. If you do, create a 1/1 colorless Eldrazi Scion creature token for each nontoken creature that died under your control this turn. Those tokens have "Sacrifice this token: Add {C}."', power='3', toughness='3', colors=[], color_identity=['G'], keywords=['Devoid', 'Flash']),  # noqa: E501
    card('Gorma, the Gullet', set_code='tst', number='N42', mana_cost='{1}{B}{G}', cmc=3.0, type_line='Legendary Creature — Pest Frog', oracle_text='Lifelink\nWhenever another creature you control dies, put a +1/+1 counter on Gorma.\nNontoken creatures you control enter with an additional +1/+1 counter on them for each creature that died under your control this turn.', power='1', toughness='1', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Lifelink']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] not in ("Runeclaw Bear", "Craterhoof Behemoth", "Colossal Dreadmaw", "Hit the Mother Lode")]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def build(cards, *names, forests=9, players=2):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Ambush Viper"), (10, "Island")]))]
    if players == 3:
        seats.append(PlayerSetup("Cy", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])))
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_gy(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def stack_top(s, names):
    """Put these cards on top of Alice's library, the first named on top."""
    for n in reversed(names):
        act(s, "p1", type="move", card_ids=[named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def run(s, discover="yes", target="p2", limit=60):
    """Resolve everything: a discover offer is answered ``discover``, a target ``target`` (a player), anything else with its
    first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            if (d.resume or {}).get("step") == "suspend_cast":
                pick = [discover]
            elif target in ids:
                pick = [target]
            else:
                pick = ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never resolved")


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=named(s, name, pid).id, **kw)


def zone(s, pid, z):
    return [s.state.cards[i].name for i in s.state.zones.get(f"{pid}:{z}", [])]


def counters(s, name, kind="+1/+1"):
    return s.state.cards[named(s, name).id].counters.get(kind, 0)


def pt(s, c):
    from app.rules import sba

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return sba.power(s.state.cards[c.id], ch), sba.toughness(s.state.cards[c.id], ch)


def life(s, pid="p2"):
    return s.state.players[pid].life


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_unclear_wordings_stay_manual():
    """A discover that something follows (its cast ends the resolution), a bare X and a bare "it" (the spell or another)
    are not read."""
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics(
        "Hit the Mother Lode", "Sorcery", next(c for c in EXTRA if c["name"] == "Hit the Mother Lode")["oracle_text"])).level != "FULL"
    for kind, text in (("Creature — Bear", "When this creature enters, discover 3. Draw a card."),
                       ("Creature — Bear", "When this creature enters, discover X."),
                       ("Sorcery", "Bolster X."),
                       ("Creature — Bear", "When you cast this spell, create X 0/1 Kobold creature tokens, where X is the amount of "
                                           "mana spent to cast it.")):
        assert coverage.of_characteristics(characteristics("Test", kind, text)).level != "FULL", text


# -- discover ------------------------------------------------------------------------------------------------------
def test_discover_casts_the_first_cheap_nonland_card_and_buries_the_rest(cards):
    """Trumpeting Carnosaur: "discover 5". The land and the 8-drop are exiled and go to the bottom; Lightning Bolt is cast."""
    s = build(cards, "Trumpeting Carnosaur", "Craterhoof Behemoth", "Lightning Bolt")
    to_hand(s, "Trumpeting Carnosaur")
    stack_top(s, ["Forest", "Craterhoof Behemoth", "Lightning Bolt"])
    size = len(s.state.zones["p1:library"])
    mana(s, R=2, G=4)
    cast(s, "Trumpeting Carnosaur")
    run(s)
    assert life(s) == 37 and "Lightning Bolt" in zone(s, "p1", "graveyard")
    assert zone(s, "p1", "exile") == []
    library = zone(s, "p1", "library")
    assert len(library) == size - 1 and set(library[-2:]) == {"Forest", "Craterhoof Behemoth"}
    check(s)


def test_discover_declined_puts_the_card_into_the_hand(cards):
    s = build(cards, "Trumpeting Carnosaur", "Lightning Bolt")
    to_hand(s, "Trumpeting Carnosaur")
    stack_top(s, ["Lightning Bolt"])
    mana(s, R=2, G=4)
    cast(s, "Trumpeting Carnosaur")
    run(s, discover="no")
    assert "Lightning Bolt" in zone(s, "p1", "hand") and life(s) == 40
    assert zone(s, "p1", "exile") == []
    check(s)


def test_discover_with_nothing_to_find_buries_the_whole_library(cards):
    s = build(cards, "Trumpeting Carnosaur", "Craterhoof Behemoth")
    to_hand(s, "Trumpeting Carnosaur")
    mana(s, R=2, G=4)
    cast(s, "Trumpeting Carnosaur")
    stack_top(s, ["Craterhoof Behemoth"])  # (put on top before the trigger resolves: still too expensive)
    size = len(s.state.zones["p1:library"])
    run(s)
    assert len(s.state.zones["p1:library"]) == size and zone(s, "p1", "exile") == []
    assert s.state.rules.decision is None
    check(s)


def test_discover_x_reads_the_cast_spell_mana_value(cards):
    """Monstrous Vortex: "discover X, where X is that spell's mana value" - Carnosaur is 6, so the 6-drop under the 8-drop is
    found (and, a creature, it enters; its own discover 5 then finds nothing)."""
    s = build(cards, "Monstrous Vortex", "Trumpeting Carnosaur", "Craterhoof Behemoth", "Colossal Dreadmaw")
    put(s, "Monstrous Vortex")
    to_hand(s, "Trumpeting Carnosaur")
    stack_top(s, ["Craterhoof Behemoth", "Colossal Dreadmaw"])
    mana(s, R=2, G=4)
    cast(s, "Trumpeting Carnosaur")
    run(s)
    assert named(s, "Colossal Dreadmaw").zone == "p1:battlefield"
    assert named(s, "Trumpeting Carnosaur").zone == "p1:battlefield"
    check(s)


def test_pantlaza_discovers_the_toughness_of_the_creature_that_entered(cards):
    """"You may discover X, where X is that creature's toughness": Pantlaza itself (toughness 4) enters."""
    s = build(cards, "Pantlaza, Sun-Favored", "Craterhoof Behemoth", "Lightning Bolt")
    stack_top(s, ["Craterhoof Behemoth", "Lightning Bolt"])
    to_hand(s, "Pantlaza, Sun-Favored")
    mana(s, R=1, G=1, W=1, C=2)
    cast(s, "Pantlaza, Sun-Favored")
    run(s)
    assert life(s) == 37 and "Lightning Bolt" in zone(s, "p1", "graveyard")
    check(s)


def test_primordial_gnawer_discover_when_it_dies(cards):
    s = build(cards, "Primordial Gnawer", "Craterhoof Behemoth", "Elvish Visionary", "Lightning Bolt")
    put(s, "Primordial Gnawer")
    to_hand(s, "Lightning Bolt")
    stack_top(s, ["Craterhoof Behemoth", "Elvish Visionary"])
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[named(s, "Primordial Gnawer").id])
    run(s, discover="no", target="never")
    assert "Elvish Visionary" in zone(s, "p1", "hand") and "Primordial Gnawer" in zone(s, "p1", "graveyard")
    check(s)


def test_hurl_into_history_discovers_for_the_countered_spells_value(cards):
    s = build(cards, "Hurl into History", "Elvish Visionary", "Craterhoof Behemoth", "Lightning Bolt")
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p2", type="set_prefs", response="on")
    to_hand(s, "Hurl into History")
    to_hand(s, "Elvish Visionary")
    stack_top(s, ["Craterhoof Behemoth", "Lightning Bolt"])
    mana(s, G=2)
    cast(s, "Elvish Visionary")  # (Bob has priority with it on the stack)
    viper = to_hand(s, "Ambush Viper", "p2")
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=viper.id)
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=named(s, "Hurl into History").id, targets=[viper.id])
    run(s)
    assert s.state.cards[viper.id].zone == "p2:graveyard"
    assert life(s) == 37 and "Lightning Bolt" in zone(s, "p1", "graveyard")
    check(s)


# -- keyword actions sized by the text ---------------------------------------------------------------------------
def test_amass_x_counts_the_graveyard(cards):
    s = build(cards, "Invade the City", "Lightning Bolt", "Memory Deluge")
    to_hand(s, "Invade the City")
    to_gy(s, "Lightning Bolt")
    to_gy(s, "Memory Deluge")
    mana(s, U=1, R=1, C=1)
    cast(s, "Invade the City")
    run(s)
    army = next(c for c in s.state.cards.values() if c.name == "Zombie Army")
    assert army.counters.get("+1/+1") == 2 and "Zombie" in Plan(s.state, "p1", s.cards, None).ch(army).subtypes
    check(s)


def test_amass_x_reads_the_cast_spells_mana_value(cards):
    s = build(cards, "Saruman, the White Hand", "Lightning Bolt")
    put(s, "Saruman, the White Hand")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt")
    run(s)
    army = next(c for c in s.state.cards.values() if c.name == "Orc Army")
    assert army.counters.get("+1/+1") == 1
    check(s)


def test_bolster_x_counts_the_hand_and_the_next_sentence_follows(cards):
    s = build(cards, "Sunbringer's Touch", "Runeclaw Bear", "Lightning Bolt", "Memory Deluge")
    bear = put(s, "Runeclaw Bear")
    to_hand(s, "Sunbringer's Touch")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Memory Deluge")
    hand = len(s.state.zones["p1:hand"]) - 1  # (Touch leaves the hand as it is cast)
    mana(s, G=4)
    cast(s, "Sunbringer's Touch")
    run(s)
    assert s.state.cards[bear.id].counters.get("+1/+1") == hand
    assert "trample" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).keywords
    check(s)


@pytest.mark.parametrize("pick", ["counters", "token"])
def test_endure_x_counts_the_wardens_counters(cards, pick):
    s = build(cards, "Warden of the Grove", "Runeclaw Bear")
    warden = put(s, "Warden of the Grove")
    act(s, "p1", type="counter", card_ids=[warden.id], kind="+1/+1", delta=2)
    to_hand(s, "Runeclaw Bear")
    mana(s, G=2)
    cast(s, "Runeclaw Bear")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id,
                option_ids=[pick] if pick in [o.id for o in d.options] else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    if pick == "counters":
        assert counters(s, "Runeclaw Bear") == 2
    else:
        assert counters(s, "Runeclaw Bear") == 0
        spirit = next(c for c in s.state.cards.values() if c.name == "Spirit")
        assert pt(s, spirit) == (2, 2)
    check(s)


# -- amounts -------------------------------------------------------------------------------------------------------
def test_mana_spent_to_cast_this_spell(cards):
    """Molten Note {X}{R}{W} with X = 2: four mana spent, four damage."""
    s = build(cards, "Molten Note", "Runeclaw Bear")
    to_hand(s, "Molten Note")
    big = put(s, "Runeclaw Bear")
    act(s, "p1", type="counter", card_ids=[big.id], kind="+1/+1", delta=6)
    mana(s, R=1, W=1, C=2)
    cast(s, "Molten Note", targets=[big.id], x_value=2)
    run(s, target=big.id)
    assert s.state.cards[big.id].damage == 4
    check(s)


def test_mana_spent_to_cast_that_spell(cards):
    """Manaform Hellkite: a Lightning Bolt cast with one mana makes a 1/1 Dragon Illusion."""
    s = build(cards, "Manaform Hellkite", "Lightning Bolt")
    put(s, "Manaform Hellkite")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])
    run(s)
    token = next(c for c in s.state.cards.values() if c.name == "Dragon Illusion")
    assert pt(s, token) == (1, 1)
    check(s)


def test_mana_spent_to_cast_her(cards):
    """Toph: four mana spent, so earthbend 4 on a land."""
    s = build(cards, "Toph, Greatest Earthbender")
    to_hand(s, "Toph, Greatest Earthbender")
    forest = put(s, "Forest")
    mana(s, R=1, G=1, C=2)
    cast(s, "Toph, Greatest Earthbender")
    run(s, target=forest.id)
    assert s.state.cards[forest.id].counters.get("+1/+1") == 4
    check(s)


def test_memory_deluge_looks_at_as_many_cards_as_mana_spent(cards):
    s = build(cards, "Memory Deluge")
    to_hand(s, "Memory Deluge")
    mana(s, U=2, C=2)
    cast(s, "Memory Deluge")
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and len(d.options) == 4 and d.min_choices == 2
    check(s)


def test_creatures_that_died_under_your_control_only(cards):
    """Priest of the Crossing: at each end step, +X/+X counters where X counts only the creatures that died under your control."""
    s = build(cards, "Priest of the Crossing", "Runeclaw Bear")
    priest = put(s, "Priest of the Crossing")
    put(s, "Runeclaw Bear")
    to_gy(s, "Runeclaw Bear")
    viper = put(s, "Ambush Viper", "p2")
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "graveyard"})
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.cards[priest.id].counters.get("+1/+1", 0) > 0)
    assert s.state.cards[priest.id].counters.get("+1/+1") == 1
    check(s)


def test_connive_x_counts_the_creatures_that_died_this_turn(cards):
    """Spymaster's Vault: two creatures died (one each side), so connive 2 - two drawn, two discarded, a +1/+1 counter for
    each nonland card discarded."""
    s = build(cards, "Spymaster's Vault", "Runeclaw Bear", "Warden of the Grove", "Lightning Bolt", "Memory Deluge")
    put(s, "Spymaster's Vault")
    warden = put(s, "Warden of the Grove")
    bear = put(s, "Runeclaw Bear")
    viper = put(s, "Ambush Viper", "p2")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "graveyard"})
    for cid in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"}, position="bottom")
    stack_top(s, ["Lightning Bolt", "Memory Deluge"])
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=named(s, "Spymaster's Vault").id, ability=2, targets=[warden.id])
    run(s)
    assert s.state.cards[warden.id].counters.get("+1/+1") == 2
    check(s)


def test_gorma_counts_the_creatures_that_died_under_your_control(cards):
    """"Nontoken creatures you control enter with an additional +1/+1 counter on them for each creature that died under your
    control this turn": two of yours died, one of Bob's (not counted)."""
    s = build(cards, "Gorma, the Gullet", "Runeclaw Bear", "Warden of the Grove")
    put(s, "Gorma, the Gullet")
    bear = put(s, "Runeclaw Bear")
    viper = put(s, "Ambush Viper", "p2")
    warden = to_hand(s, "Warden of the Grove")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "graveyard"})
    mana(s, G=3)
    cast(s, "Warden of the Grove")
    run(s)
    assert s.state.cards[warden.id].counters.get("+1/+1", 0) == 1
    check(s)


def test_vile_redeemer_makes_a_scion_for_each_nontoken_creature_that_died_under_your_control(cards):
    s = build(cards, "Vile Redeemer", "Runeclaw Bear")
    to_hand(s, "Vile Redeemer")
    bear = put(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    mana(s, G=1, C=4)
    cast(s, "Vile Redeemer")
    run(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Eldrazi Scion" and c.zone == "p1:battlefield") == 1
    check(s)
