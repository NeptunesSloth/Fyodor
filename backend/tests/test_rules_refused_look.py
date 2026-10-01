"""Previously refused look-at-the-top and cast-without-paying forms (wave 3R5), read against the stored
Comprehensive Rules (2026-09-25): 608.2g (a spell cast during a resolution is cast then — 601.2a-i, no
priority — and becomes the topmost object while the resolving spell or ability goes on, "which may
include casting other spells this way"), 118.9 / 107.3b (without paying its mana cost: X is 0),
601.2h (a cancelled payment leaves the table as it was), 614.1a ("If that spell would be put into
your graveyard, exile it instead"), 701.20a/e (revealed cards are public; looked-at cards only the
looker's), 401.2 (a library and its order are hidden). The cards are real Commander cards, their
Oracle text transcribed from the card database. Every scenario replays from history and keeps the
looked-at cards out of the other player's view."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, run_until

REAL = [
    card("Rishkar's Expertise", set_code="tst", number="R50", mana_cost="{4}{G}{G}", cmc=6.0, type_line="Sorcery", colors=["G"],
         color_identity=["G"], oracle_text="Draw cards equal to the greatest power among creatures you control.\nYou may cast a spell "
         "with mana value 5 or less from your hand without paying its mana cost."),
    card("Goblin Dark-Dwellers", set_code="tst", number="R51", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Creature — Goblin",
         colors=["R"], color_identity=["R"], power="4", toughness="4", keywords=["Menace"],
         oracle_text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, you may "
         "cast target instant or sorcery card with mana value 3 or less from your graveyard without paying its mana cost. If that "
         "spell would be put into your graveyard, exile it instead."),
    card("Velomachus Lorehold", set_code="tst", number="R52", mana_cost="{5}{R}{W}", cmc=7.0, type_line="Legendary Creature — Elder Dragon",
         colors=["R", "W"], color_identity=["R", "W"], power="5", toughness="5", keywords=["Flying", "Vigilance", "Haste"],
         oracle_text="Flying, vigilance, haste\nWhenever Velomachus Lorehold attacks, look at the top seven cards of your library. You "
         "may cast an instant or sorcery spell with mana value less than or equal to Velomachus Lorehold's power from among them "
         "without paying its mana cost. Put the rest on the bottom of your library in a random order."),
    card("Wanda's Vision", set_code="tst", number="R53", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Enchantment", colors=["R"],
         color_identity=["R"], oracle_text="Whenever you cast your second spell each turn, exile cards from the top of your library "
         "until you exile a nonland card. You may cast that card without paying its mana cost."),
    card("Villainous Wealth", set_code="tst", number="R54", mana_cost="{X}{B}{G}{U}", cmc=3.0, type_line="Sorcery",
         colors=["B", "G", "U"], color_identity=["B", "G", "U"], oracle_text="Target opponent exiles the top X cards of their library. "
         "You may cast any number of spells with mana value X or less from among them without paying their mana costs."),
    card("Herald of Amity", set_code="tst", number="R55", mana_cost="{3}{W}", cmc=4.0, type_line="Creature — Griffin", colors=["W"],
         color_identity=["W"], power="2", toughness="2", keywords=["Flying"], oracle_text="Flying\nWhen this creature enters, exile the "
         "top eight cards of your library. You may cast an Aura spell from among them without paying its mana cost. Then put the "
         "rest on the bottom of your library in a random order.\nWhenever this creature attacks, it gets +X/+X until end of turn, "
         "where X is the number of Auras you control."),
    card("Collected Conjuring", set_code="tst", number="R56", mana_cost="{2}{U}{R}", cmc=4.0, type_line="Sorcery", colors=["R", "U"],
         color_identity=["R", "U"], oracle_text="Exile the top six cards of your library. You may cast up to two sorcery spells with "
         "mana value 3 or less from among them without paying their mana costs. Put the exiled cards not cast this way on the bottom "
         "of your library in a random order."),
    card("Buster Sword", set_code="tst", number="R57", mana_cost="{3}", cmc=3.0, type_line="Artifact — Equipment", keywords=["Equip"],
         oracle_text="Equipped creature gets +3/+2.\nWhenever equipped creature deals combat damage to a player, draw a card, then "
         "you may cast a spell from your hand with mana value less than or equal to that damage without paying its mana cost.\nEquip {2}"),
    card("Treasure Keeper", set_code="tst", number="R59", mana_cost="{4}", cmc=4.0, type_line="Artifact Creature — Construct",
         power="3", toughness="3", oracle_text="When this creature dies, reveal cards from the top of your library until you reveal a "
         "nonland card with mana value 3 or less. You may cast that card without paying its mana cost. Put all revealed cards not "
         "cast this way on the bottom of your library in a random order."),
    card("Omnispell Adept", set_code="tst", number="R510", mana_cost="{4}{U}", cmc=5.0, type_line="Creature — Human Wizard",
         colors=["U"], color_identity=["U"], power="3", toughness="4",
         oracle_text="{2}{U}, {T}: You may cast an instant or sorcery spell from your hand without paying its mana cost."),
    card("Fling", set_code="tst", number="R511", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", colors=["R"], color_identity=["R"],
         oracle_text="As an additional cost to cast this spell, sacrifice a creature.\nFling deals damage equal to the sacrificed "
         "creature's power to any target."),
    card("Rashmi, Eternities Crafter", set_code="tst", number="R60", mana_cost="{2}{G}{U}", cmc=4.0,
         type_line="Legendary Creature — Elf Druid", colors=["G", "U"], color_identity=["G", "U"], power="2", toughness="3",
         oracle_text="Whenever you cast your first spell each turn, reveal the top card of your library. You may cast it without "
         "paying its mana cost if it's a spell with lesser mana value. If you don't cast it, put it into your hand."),
    card("Yennett, Cryptic Sovereign", set_code="tst", number="R61", mana_cost="{2}{W}{U}{B}", cmc=5.0,
         type_line="Legendary Creature — Sphinx", colors=["B", "U", "W"], color_identity=["B", "U", "W"], power="3", toughness="5",
         keywords=["Flying", "Vigilance", "Menace"], oracle_text="Flying, vigilance, menace\nWhenever Yennett attacks, reveal the "
         "top card of your library. You may cast it without paying its mana cost if its mana value is odd. If you don't cast it, "
         "draw a card."),
    card("Breaching Dragonstorm", set_code="tst", number="R62", mana_cost="{4}{R}", cmc=5.0, type_line="Enchantment", colors=["R"],
         color_identity=["R"], oracle_text="When this enchantment enters, exile cards from the top of your library until you exile a "
         "nonland card. You may cast it without paying its mana cost if that spell's mana value is 8 or less. If you don't, put "
         "that card into your hand.\nWhen a Dragon you control enters, return this enchantment to its owner's hand."),
    card("Diviner of Mist", set_code="tst", number="R63", mana_cost="{4}{U}", cmc=5.0, type_line="Creature — Dragon", colors=["U"],
         color_identity=["U"], power="4", toughness="5", keywords=["Flying", "Mill"], oracle_text="Flying\nWhenever this creature "
         "attacks, mill four cards. You may cast an instant or sorcery spell from your graveyard with mana value 4 or less without "
         "paying its mana cost. If that spell would be put into your graveyard, exile it instead."),
    card("Epic Experiment", set_code="tst", number="R64", mana_cost="{X}{U}{R}", cmc=2.0, type_line="Sorcery", colors=["R", "U"],
         color_identity=["R", "U"], oracle_text="Exile the top X cards of your library. You may cast instant and sorcery spells with "
         "mana value X or less from among them without paying their mana costs. Then put all cards exiled this way that weren't "
         "cast into your graveyard."),
    card("Etali, Primal Storm", set_code="tst", number="R65", mana_cost="{4}{R}{R}", cmc=6.0,
         type_line="Legendary Creature — Elder Dinosaur", colors=["R"], color_identity=["R"], power="6", toughness="6",
         oracle_text="Whenever Etali attacks, exile the top card of each player's library, then you may cast any number of spells "
         "from among those cards without paying their mana costs."),
    card("Chaos Wand", set_code="tst", number="R66", mana_cost="{3}", cmc=3.0, type_line="Artifact",
         oracle_text="{4}, {T}: Target opponent exiles cards from the top of their library until they exile an instant or sorcery "
         "card. You may cast that card without paying its mana cost. Then put the exiled cards that weren't cast this way on the "
         "bottom of that library in a random order."),
    card("Sunbird's Invocation", set_code="tst", number="R67", mana_cost="{5}{R}", cmc=6.0, type_line="Enchantment", colors=["R"],
         color_identity=["R"], oracle_text="Whenever you cast a spell from your hand, reveal the top X cards of your library, where "
         "X is that spell's mana value. You may cast a spell with mana value X or less from among cards revealed this way without "
         "paying its mana cost. Put the rest on the bottom of your library in a random order."),
    card("Fact or Fiction", set_code="tst", number="R70", mana_cost="{3}{U}", cmc=4.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="Reveal the top five cards of your library. An opponent separates those cards into two "
         "piles. Put one pile into your hand and the other into your graveyard."),
    card("Steam Augury", set_code="tst", number="R71", mana_cost="{2}{U}{R}", cmc=4.0, type_line="Instant", colors=["R", "U"],
         color_identity=["R", "U"], oracle_text="Reveal the top five cards of your library and separate them into two piles. An "
         "opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard."),
    card("In the Presence of Ages", set_code="tst", number="R72", mana_cost="{2}{G}", cmc=3.0, type_line="Instant", colors=["G"],
         color_identity=["G"], oracle_text="Reveal the top four cards of your library. You may put a creature card and/or a land "
         "card from among them into your hand. Put the rest into your graveyard."),
    card("Atraxa, Grand Unifier", set_code="tst", number="R73", mana_cost="{3}{G}{W}{U}{B}", cmc=7.0,
         type_line="Legendary Creature — Phyrexian Angel", colors=["B", "G", "U", "W"], color_identity=["B", "G", "U", "W"],
         power="7", toughness="7", keywords=["Deathtouch", "Flying", "Lifelink", "Vigilance"],
         oracle_text="Flying, vigilance, deathtouch, lifelink\nWhen Atraxa enters, reveal the top ten cards of your library. For "
         "each card type, you may put a card of that type from among the revealed cards into your hand. Put the rest on the bottom "
         "of your library in a random order. (Artifact, battle, creature, enchantment, instant, land, planeswalker, and sorcery "
         "are card types.)"),
    card("Kaalia, Zenith Seeker", set_code="tst", number="R74", mana_cost="{R}{W}{B}", cmc=3.0,
         type_line="Legendary Creature — Human Cleric", colors=["B", "R", "W"], color_identity=["B", "R", "W"], power="3",
         toughness="3", keywords=["Flying", "Vigilance"], oracle_text="Flying, vigilance\nWhen Kaalia enters, look at the top six "
         "cards of your library. You may reveal an Angel card, a Demon card, and/or a Dragon card from among them and put them "
         "into your hand. Put the rest on the bottom of your library in a random order."),
    card("Ornithopter", set_code="tst", number="R75", mana_cost="{0}", cmc=0.0, type_line="Artifact Creature — Thopter",
         power="0", toughness="2", keywords=["Flying"], oracle_text="Flying"),
    card("Thassa's Oracle", set_code="tst", number="R80", mana_cost="{U}{U}", cmc=2.0, type_line="Creature — Merfolk Wizard",
         colors=["U"], color_identity=["U"], power="1", toughness="3",
         oracle_text="When this creature enters, look at the top X cards of your library, where X is your devotion to blue. Put up "
         "to one of them on top of your library and the rest on the bottom of your library in a random order. If X is greater than "
         "or equal to the number of cards in your library, you win the game. (Each {U} in the mana costs of permanents you control "
         "counts toward your devotion to blue.)"),
    card("Abyssal Persecutor", set_code="tst", number="R81", mana_cost="{2}{B}{B}", cmc=4.0, type_line="Creature — Demon",
         colors=["B"], color_identity=["B"], power="6", toughness="6", keywords=["Flying", "Trample"],
         oracle_text="Flying, trample\nYou can't win the game and your opponents can't lose the game."),
    card("Zaffai and the Tempests", set_code="tst", number="R82", mana_cost="{5}{U}{R}", cmc=7.0,
         type_line="Legendary Creature — Human Bard Sorcerer", colors=["R", "U"], color_identity=["R", "U"], power="5",
         toughness="7", oracle_text="Once during each of your turns, you may cast an instant or sorcery spell from your hand "
         "without paying its mana cost."),
    card("Jet, Rebel Leader", set_code="tst", number="R90", mana_cost="{3}{W}", cmc=4.0,
         type_line="Legendary Creature — Human Rebel Ally", colors=["W"], color_identity=["W"], power="3", toughness="4",
         oracle_text="Whenever Jet attacks, look at the top five cards of your library. You may put a creature card with mana value "
         "3 or less from among them onto the battlefield tapped and attacking. Put the rest on the bottom of your library in a "
         "random order."),
    card("Winota, Joiner of Forces", set_code="tst", number="R91", mana_cost="{2}{R}{W}", cmc=4.0,
         type_line="Legendary Creature — Human Warrior", colors=["R", "W"], color_identity=["R", "W"], power="4", toughness="4",
         oracle_text="Whenever a non-Human creature you control attacks, look at the top six cards of your library. You may put a "
         "Human creature card from among them onto the battlefield tapped and attacking. It gains indestructible until end of "
         "turn. Put the rest of the cards on the bottom of your library in a random order."),
    card("Raph & Mikey, Troublemakers", set_code="tst", number="R92", mana_cost="{5}{R/G}{R/G}", cmc=7.0,
         type_line="Legendary Creature — Mutant Ninja Turtle", colors=["G", "R"], color_identity=["G", "R"], power="7",
         toughness="7", keywords=["Haste", "Trample"], oracle_text="Trample, haste\nWhenever Raph & Mikey attack, reveal cards from "
         "the top of your library until you reveal a creature card. Put that card onto the battlefield tapped and attacking and "
         "the rest on the bottom of your library in a random order."),
    card("Divination", set_code="tst", number="R512", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Draw two cards."),
    card("Sign in Blood", set_code="tst", number="R513", mana_cost="{B}{B}", cmc=2.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Target player draws two cards and loses 2 life."),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


OURS = [c["name"] for c in REAL]


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in OURS] + [(4, "Grizzly Bears"), (2, "Lightning Bolt"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Divination"), (1, "Lightning Bolt"), (1, "Sign in Blood"),
                                                   (1, "Counterspell"), (2, "Grizzly Bears"), (20, "Island"), (1, "Gideon Jura")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def find(s, name, pid="p1", nth=0):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid][nth]


def put(s, name, where, pid="p1", nth=0):
    c = find(s, name, pid, nth)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": where, "player": pid})
    return s.state.cards[c.id]


def stack_library(s, names, pid="p1"):
    """Put these cards on top of the library, in this order (the first on top)."""
    ids = []
    for i, n in reversed(list(enumerate(names))):
        ids.insert(0, put(s, n, "library", pid, nth=sum(1 for m in names[:i] if m == n)).id)
    assert zone(s.state, pid, "library")[: len(names)] == ids
    return ids


def decision(s, step=None):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    if step is not None:
        assert (d.resume or {}).get("step") == step, (d.resume or {}).get("step")
    return d


def choose(s, ids, *, resolve=False):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if resolve:
        pass_until_stack_empty(s)


def hidden_from_bob(s, ids, *, names=True):
    """Nothing identifying these cards is in Bob's view (a reload too). ``names``: also their names (only
    when no card of that name is public)."""
    for session in (s, GameSession(s.history.rebuild(), cards=s.cards)):
        bob = json.dumps(session.view("p2"))
        for cid in ids:
            c = session.state.cards[cid]
            for secret in (cid, c.name if names else None, c.card_id if names else None):
                assert not secret or secret not in bob, secret


def hold(s):
    """Every priority is a stop for both players (nothing resolves on its own)."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", full_control=True)


def stack_names(s):
    return [s.state.cards[c].name for c in s.state.zones.get("stack", [])]


def full(cards, name):
    data = next(c for c in REAL if c["name"] == name)
    feats = coverage.features_of(printed_from_data(data, 0))
    return all(f.supported for f in feats), [f.label for f in feats if not f.supported]


# -- the wordings ---------------------------------------------------------------------------------------
def test_wordings_read_and_refused():
    among = scripts.parse_effects("Look at the top seven cards of your library. You may cast an instant or sorcery spell with mana value "
                                  "less than or equal to ~'s power from among them without paying its mana cost. Put the rest on the "
                                  "bottom of your library in a random order.", None)
    assert among is not None
    assert [e["do"] for e in among[0]] == ["look_top", "free_cast", "rest_looked"]
    assert among[0][1]["zone"] == "looked" and among[0][1]["mv"] == {"power": "self"}
    wealth = scripts.parse_effects("Target opponent exiles the top X cards of their library. You may cast any number of spells with "
                                   "mana value X or less from among them without paying their mana costs.")
    assert wealth is not None and wealth[0][1]["n"] == 99 and wealth[0][1]["zone"] == "that"
    # "its power" with nothing to bind, and a target whose legality would move with a value read on resolution: refused
    assert scripts.parse_effects("You may cast an instant spell with mana value less than or equal to its power from among them "
                                 "without paying its mana cost.") is None
    assert scripts.parse_effects("You may cast target instant or sorcery card with mana value less than or equal to ~'s power from your "
                                 "graveyard without paying its mana cost.") is None
    # "from among them" with nothing set aside before it, and several libraries ("each player's"): refused
    assert scripts.parse_effects("You may cast any number of spells from among them without paying their mana costs.") is None
    assert scripts.parse_effects("Look at the top card of each player's library. You may cast a spell from among them without paying "
                                 "its mana cost.") is None


@pytest.mark.parametrize("name", [n for n in OURS if n not in ("Fling", "Divination", "Sign in Blood", "Ornithopter", "Abyssal Persecutor")])
def test_cards_are_full(cards, name):
    ok, missing = full(cards, name)
    assert ok, missing


# -- 608.2g: the cast happens during the resolution; what follows comes after it ----------------------
def test_velomachus_casts_from_the_cards_looked_at_then_the_rest_go_to_the_bottom(cards):
    s = build(cards)
    velo = put(s, "Velomachus Lorehold", "battlefield")
    top = stack_library(s, ["Divination", "Lightning Bolt", "Grizzly Bears", "Forest", "Sign in Blood", "Collected Conjuring", "Forest"])
    for _ in range(10):  # to the declare-attackers step
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": velo.id, "target": "p2"}])
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    # instants and sorceries with mana value 5 or less (its power) among the seven: not the creature, the lands
    assert {o.id for o in d.options} == {top[0], top[1], top[4], top[5]}
    hidden_from_bob(s, [top[0], top[2], top[3], top[4], top[5]])
    assert json.loads(json.dumps(s.view("p2")["rules"]["decision"]))["public"]["type"] == "PLAYER_MAKING_CHOICE"
    choose(s, [top[1]])  # Lightning Bolt: its target is chosen now, during the resolution
    d = decision(s, "cast_target")
    trigger_still_there = [c for c in s.state.zones["stack"] if s.state.cards[c].name != "Lightning Bolt"]
    assert trigger_still_there and zone(s.state, "p1", "library")[0] == top[0]  # the rest haven't moved yet
    choose(s, ["p2"])
    library = zone(s.state, "p1", "library")
    assert set(library[-6:]) == {top[0], top[2], top[3], top[4], top[5], top[6]}  # the rest, on the bottom
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37 - 5 or s.state.players["p2"].life == 37  # (the Bolt; combat damage may follow)
    assert s.state.cards[top[1]].zone == "p1:graveyard"
    replay_matches(s)


def test_a_cancelled_free_cast_lets_the_resolution_go_on(cards):
    s = build(cards)
    velo = put(s, "Velomachus Lorehold", "battlefield")
    put(s, "Grizzly Bears", "battlefield")
    top = stack_library(s, ["Fling", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": velo.id, "target": "p2"}])
    pass_until_stack_empty(s)
    choose(s, [top[0]])  # Fling: its additional cost (sacrifice a creature) is chosen next …
    d = s.state.rules.decision
    while d is not None and (d.resume or {}).get("step") != "ability_cost":
        assert (d.resume or {}).get("step") in ("cast_target",), d.resume
        choose(s, ["p2"])
        d = s.state.rules.decision
    assert d is not None
    choose(s, [])  # … and choosing nothing cancels the cast (601.2h: nothing was paid)
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert s.state.cards[velo.id].zone == "p1:battlefield"
    assert not s.state.zones.get("stack")  # the trigger finished resolving
    assert top[0] in zone(s.state, "p1", "library")[-7:]  # Fling went to the bottom with the rest
    assert s.state.rules.free_casts == []
    replay_matches(s)


def test_rishkars_expertise_two_lines_draw_then_cast_free(cards):
    s = build(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Goblin Dark-Dwellers", "hand")
    stack_library(s, ["Forest", "Forest"])
    exp = put(s, "Rishkar's Expertise", "hand")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=exp.id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    dwellers = find(s, "Goblin Dark-Dwellers")
    assert dwellers.id in {o.id for o in d.options}  # mana value 5
    assert len(zone(s.state, "p1", "hand")) >= 3  # drew two (the Bears' power) before
    choose(s, [dwellers.id])
    assert s.state.cards[exp.id].zone == "p1:graveyard"  # the Expertise finished resolving
    assert s.state.cards[dwellers.id].zone in ("stack", "p1:battlefield")
    assert s.state.players["p1"].mana == {}
    replay_matches(s)


# -- 614.1a: a spell cast from a graveyard this way is exiled instead -----------------------------------------
def test_goblin_dark_dwellers_casts_bolt_from_the_graveyard_and_exiles_it(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    dwellers = put(s, "Goblin Dark-Dwellers", "hand")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=dwellers.id)
    pass_until_stack_empty(s)  # the creature resolves; its trigger's target: the Bolt
    d = s.state.rules.decision
    if d is not None and (d.resume or {}).get("step") != "free_cast_pick" and d.kind in ("choose_one", "choose_cards") \
            and any(o.id == bolt.id for o in d.options):
        choose(s, [bolt.id], resolve=True)
    d = s.state.rules.decision
    if d is not None and d.kind == "confirm":
        choose(s, ["yes"], resolve=True)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [bolt.id]
    choose(s, [bolt.id])
    choose(s, ["p2"], resolve=True)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:exile"  # not the graveyard
    assert s.state.rules.exile_if_graveyard == []
    replay_matches(s)


def test_a_dwellers_cast_bolt_countered_is_exiled_too(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    dwellers = put(s, "Goblin Dark-Dwellers", "hand")
    counter = put(s, "Counterspell", "hand", pid="p2")
    mana(s, R=5)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=dwellers.id)
    pass_until_stack_empty(s)
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "free_cast_pick":
            break
        if d is not None and d.kind == "confirm":
            choose(s, ["yes"], resolve=True)
        elif d is not None and any(o.id == bolt.id for o in d.options):
            choose(s, [bolt.id], resolve=True)
    choose(s, [bolt.id])
    choose(s, ["p2"])
    assert stack_names(s) == ["Lightning Bolt"]  # the trigger finished; the Bolt is on the stack
    if s.state.rules.priority != "p2":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p1:exile" and s.state.players["p2"].life == 40
    replay_matches(s)


# -- several casts, one at a time; the rest afterwards ---------------------------------------------------------
def test_villainous_wealth_casts_any_number_one_after_another(cards):
    s = build(cards)
    top = stack_library(s, ["Divination", "Sign in Blood", "Island", "Lightning Bolt"], pid="p2")
    wealth = put(s, "Villainous Wealth", "hand")
    mana(s, B=2, G=2, U=2)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=wealth.id, x_value=3, targets=["p2"])
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {top[0], top[1]}  # X = 3: not the Island; the Bolt wasn't exiled (top three only)
    choose(s, [top[0]])  # Divination (Bob's card: Alice casts it, 608.2g)
    d = decision(s, "free_cast_pick")  # … then the next
    assert {o.id for o in d.options} == {top[1]}
    choose(s, [top[1]])
    choose(s, ["p2"])  # Sign in Blood's target
    assert s.state.rules.decision is None
    assert stack_names(s) == ["Divination", "Sign in Blood"]  # cast in that order: Sign in Blood is on top
    assert s.state.cards[wealth.id].zone == "p1:graveyard"
    assert s.state.cards[top[0]].controller == "p1"
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_collected_conjuring_up_to_two_then_the_rest_on_the_bottom(cards):
    s = build(cards)
    top = stack_library(s, ["Divination", "Rishkar's Expertise", "Lightning Bolt", "Forest", "Sign in Blood", "Forest"])
    cc = put(s, "Collected Conjuring", "hand")
    mana(s, U=2, R=2)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=cc.id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {top[0], top[4]}  # sorceries with mana value 3 or less
    choose(s, [top[0]])
    d = decision(s, "free_cast_pick")
    choose(s, [])  # only one after all
    assert stack_names(s) == ["Divination"]
    library = zone(s.state, "p1", "library")
    assert set(library[-5:]) == {top[1], top[2], top[3], top[4], top[5]}
    assert not [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    replay_matches(s)


def test_herald_of_amity_casts_an_aura_then_the_rest_go_to_the_bottom(cards):
    s = build(cards)
    put(s, "Grizzly Bears", "battlefield")
    top = stack_library(s, ["Forest", "Lightning Bolt", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"])
    herald = put(s, "Herald of Amity", "hand")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=herald.id)
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None  # no Aura among them (public, in exile): nothing to choose
    assert set(zone(s.state, "p1", "library")[-8:]) == set(top)
    replay_matches(s)


def test_treasure_keeper_reveals_until_then_puts_the_others_on_the_bottom(cards):
    s = build(cards)
    keeper = put(s, "Treasure Keeper", "battlefield")
    top = stack_library(s, ["Forest", "Collected Conjuring", "Divination", "Forest"])
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[keeper.id])
    pass_until_stack_empty(s)  # the Bolt, then the dies trigger
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top[2]]  # the first nonland card with mana value 3 or less
    choose(s, [top[2]])
    assert stack_names(s) == ["Divination"]
    library = zone(s.state, "p1", "library")
    assert set(library[-2:]) == {top[0], top[1]} and top[3] == library[0]
    replay_matches(s)


def test_omnispell_adept_casts_from_hand(cards):
    s = build(cards)
    adept = put(s, "Omnispell Adept", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    div = put(s, "Divination", "hand")
    mana(s, U=3)
    act(s, "p1", type="activate_ability", card_id=adept.id, ability=0)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert div.id in {o.id for o in d.options}
    choose(s, [div.id], resolve=True)
    assert s.state.cards[div.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {}
    replay_matches(s)


def to_attack(s, attacker):
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    pass_until_stack_empty(s)


# -- "You may cast it … if …" and "If you don't cast it, …" (608.2c: it reads what the cast did) -------------
def test_rashmi_lesser_mana_value_else_into_the_hand(cards):
    s = build(cards)
    put(s, "Rashmi, Eternities Crafter", "battlefield")
    top = stack_library(s, ["Divination", "Forest"])
    expert = put(s, "Rishkar's Expertise", "hand")  # mana value 6: Divination (3) is lesser
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=expert.id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top[0]]
    choose(s, [top[0]], resolve=True)
    assert s.state.cards[top[0]].zone != "p1:hand"  # cast, so not put into the hand
    for _ in range(4):
        if s.state.rules.decision is None:
            break
        choose(s, [], resolve=True)  # (the Expertise's own free cast: none)
    assert s.state.cards[top[0]].zone == "p1:graveyard"
    replay_matches(s)


def test_rashmi_declined_puts_it_into_the_hand(cards):
    s = build(cards)
    put(s, "Rashmi, Eternities Crafter", "battlefield")
    top = stack_library(s, ["Rishkar's Expertise", "Forest"])  # mana value 6: not lesser than Divination's 3
    div = put(s, "Divination", "hand")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=div.id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")  # (revealed: public; nothing eligible, asked all the same)
    assert d.options == []
    choose(s, [], resolve=True)
    assert s.state.cards[top[0]].zone == "p1:hand"
    replay_matches(s)


def test_yennett_odd_mana_value_or_draw(cards):
    s = build(cards)
    yen = put(s, "Yennett, Cryptic Sovereign", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    top = stack_library(s, ["Sign in Blood", "Forest", "Forest"])  # mana value 2: even
    to_attack(s, yen)
    d = decision(s, "free_cast_pick")
    assert d.options == []
    hand_before = len(zone(s.state, "p1", "hand"))
    choose(s, [], resolve=True)
    assert s.state.cards[top[0]].zone == "p1:hand" and len(zone(s.state, "p1", "hand")) == hand_before + 1  # drew it
    replay_matches(s)


def test_breaching_dragonstorm_puts_the_found_card_into_the_hand_if_not_cast(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Forest", "Divination", "Forest"])
    storm = put(s, "Breaching Dragonstorm", "hand")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=storm.id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top[2]]
    choose(s, [], resolve=True)
    assert s.state.cards[top[2]].zone == "p1:hand"
    assert s.state.cards[top[0]].zone == "p1:exile" and s.state.cards[top[1]].zone == "p1:exile"  # (the text leaves them)
    replay_matches(s)


def test_wandas_vision_casts_the_card_found(cards):
    s = build(cards)
    put(s, "Wanda's Vision", "battlefield")
    top = stack_library(s, ["Forest", "Divination", "Forest"])
    b1, b2 = put(s, "Lightning Bolt", "hand"), put(s, "Lightning Bolt", "hand", nth=1)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=b1.id, targets=["p2"])
    pass_until_stack_empty(s)
    act(s, "p1", type="cast_spell", card_id=b2.id, targets=["p2"])  # the second spell this turn
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top[1]]
    choose(s, [top[1]], resolve=True)
    assert s.state.cards[top[1]].zone == "p1:graveyard" and s.state.cards[top[0]].zone == "p1:exile"
    assert s.state.players["p2"].life == 34
    replay_matches(s)


# -- graveyards, several libraries, X ------------------------------------------------------------------------
def test_diviner_of_mist_casts_from_the_graveyard_and_exiles_it(cards):
    s = build(cards)
    diviner = put(s, "Diviner of Mist", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    top = stack_library(s, ["Forest", "Divination", "Forest", "Rishkar's Expertise"])
    to_attack(s, diviner)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top[1]]  # milled; mana value 4 or less (not the Expertise: 6)
    choose(s, [top[1]], resolve=True)
    assert s.state.cards[top[1]].zone == "p1:exile"
    replay_matches(s)


def test_epic_experiment_casts_any_number_then_the_rest_into_the_graveyard(cards):
    s = build(cards)
    top = stack_library(s, ["Divination", "Forest", "Lightning Bolt", "Grizzly Bears"])
    exp = put(s, "Epic Experiment", "hand")
    mana(s, U=3, R=3)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=exp.id, x_value=4)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {top[0], top[2]}  # instants and sorceries only
    choose(s, [top[2]])
    choose(s, ["p2"])  # the Bolt's target
    decision(s, "free_cast_pick")
    choose(s, [top[0]])
    assert s.state.rules.decision is None
    assert stack_names(s) == ["Lightning Bolt", "Divination"]  # cast one after another during the resolution
    assert s.state.cards[top[1]].zone == "p1:graveyard" and s.state.cards[top[3]].zone == "p1:graveyard"
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    replay_matches(s)


def test_etali_casts_from_each_players_exiled_card(cards):
    s = build(cards)
    etali = put(s, "Etali, Primal Storm", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    mine = stack_library(s, ["Divination"])
    theirs = stack_library(s, ["Sign in Blood"], pid="p2")
    to_attack(s, etali)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {mine[0], theirs[0]}
    choose(s, [theirs[0]])
    choose(s, ["p2"])
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [mine[0]]
    choose(s, [], resolve=True)
    assert s.state.cards[theirs[0]].zone == "p2:graveyard" and s.state.cards[mine[0]].zone == "p1:exile"
    assert s.state.players["p2"].life <= 38
    replay_matches(s)


def test_chaos_wand_casts_an_opponents_instant_then_the_rest_go_back(cards):
    s = build(cards)
    wand = put(s, "Chaos Wand", "battlefield")
    theirs = stack_library(s, ["Island", "Grizzly Bears", "Lightning Bolt", "Island"], pid="p2")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=wand.id, ability=0, targets=["p2"])
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [theirs[2]]
    choose(s, [theirs[2]])
    choose(s, ["p2"], resolve=True)
    assert s.state.players["p2"].life == 37 and s.state.cards[theirs[2]].zone == "p2:graveyard"
    library = zone(s.state, "p2", "library")
    assert set(library[-2:]) == {theirs[0], theirs[1]} and library[0] == theirs[3]
    replay_matches(s)


def test_sunbirds_invocation_x_is_the_spells_mana_value():
    data = next(c for c in REAL if c["name"] == "Sunbird's Invocation")
    d = scripts.definitions(printed_from_data(data, 0))[0]
    cast = next(e for e in d["effects"] if e["do"] == "free_cast")
    assert cast["mv"] == {"mana_value": "event"} and cast["zone"] == "looked"



# -- 700.3: piles of revealed cards ---------------------------------------------------------------------------
def test_fact_or_fiction_the_opponent_separates_you_choose(cards):
    s = build(cards)
    top = stack_library(s, ["Divination", "Lightning Bolt", "Forest", "Grizzly Bears", "Sign in Blood"])
    fof = put(s, "Fact or Fiction", "hand")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=fof.id)
    pass_until_stack_empty(s)
    d = decision(s, "piles_split")
    assert d.player == "p2" and {o.id for o in d.options} == set(top)  # revealed: the opponent sees them (701.20a)
    choose(s, [top[0], top[1]])  # pile 1: Divination, Bolt; pile 2: the rest
    d = decision(s, "piles_pick")
    assert d.player == "p1" and len(d.options) == 2
    choose(s, ["2"], resolve=True)
    assert {s.state.cards[c].zone for c in top[2:]} == {"p1:hand"}
    assert {s.state.cards[c].zone for c in top[:2]} == {"p1:graveyard"}
    replay_matches(s)


def test_steam_augury_you_separate_the_opponent_chooses_an_empty_pile_allowed(cards):
    s = build(cards)
    top = stack_library(s, ["Divination", "Lightning Bolt", "Forest", "Grizzly Bears", "Sign in Blood"])
    aug = put(s, "Steam Augury", "hand")
    mana(s, U=2, R=2)
    act(s, "p1", type="cast_spell", card_id=aug.id)
    pass_until_stack_empty(s)
    d = decision(s, "piles_split")
    assert d.player == "p1"
    choose(s, list(top))  # every card in pile 1, pile 2 empty (700.3d)
    d = decision(s, "piles_pick")
    assert d.player == "p2"
    choose(s, ["2"], resolve=True)  # the empty pile: everything goes to the graveyard
    assert {s.state.cards[c].zone for c in top} == {"p1:graveyard"}
    replay_matches(s)


def test_fact_or_fiction_in_multiplayer_the_caster_chooses_the_opponent(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Fact or Fiction"), (20, "Forest")])
    others = [deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")]) for _ in range(2)]
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=others[0]),
                                     PlayerSetup("Carol", cards=others[1])], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    fof = put(s, "Fact or Fiction", "hand")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=fof.id)
    pass_until_stack_empty(s)
    d = decision(s, "piles_opponent")
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # 608.2d
    choose(s, ["p3"])
    assert decision(s, "piles_split").player == "p3"
    choose(s, [])
    choose(s, ["1"], resolve=True)  # pile 1 is empty: nothing to the hand
    assert len([c for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.name == "Forest"]) == 5
    replay_matches(s)


# -- one card of each kind --------------------------------------------------------------------------------------
def test_in_the_presence_of_ages_a_creature_and_or_a_land(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Ornithopter", "Forest", "Divination"])
    ages = put(s, "In the Presence of Ages", "hand")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=ages.id)
    pass_until_stack_empty(s)
    d = decision(s, "pick_looked")
    assert {o.id for o in d.options} == {top[0], top[1], top[2]}  # creatures and lands only
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[top[0], top[1]])  # two creatures: one of each kind only
    choose(s, [top[1], top[2]], resolve=True)
    assert s.state.cards[top[1]].zone == "p1:hand" and s.state.cards[top[2]].zone == "p1:hand"
    assert s.state.cards[top[0]].zone == "p1:graveyard" and s.state.cards[top[3]].zone == "p1:graveyard"
    replay_matches(s)


def test_atraxa_one_card_of_each_type_an_artifact_creature_counts_once(cards):
    s = build(cards)
    top = stack_library(s, ["Ornithopter", "Grizzly Bears", "Forest", "Divination", "Lightning Bolt", "Forest", "Forest", "Fling",
                            "Sign in Blood", "Forest"])
    atraxa = put(s, "Atraxa, Grand Unifier", "hand")
    mana(s, G=2, W=2, U=2, B=1)
    act(s, "p1", type="cast_spell", card_id=atraxa.id)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    decision(s, "pick_looked")
    # Ornithopter (artifact or creature) + Bears (creature) + a land + Divination (sorcery) + Bolt (instant): five kinds
    choose(s, [top[0], top[1], top[2], top[3], top[4]], resolve=True)
    assert {s.state.cards[c].zone for c in top[:5]} == {"p1:hand"}
    assert set(zone(s.state, "p1", "library")[-5:]) == set(top[5:])
    replay_matches(s)


def test_kaalia_looks_privately_and_reveals_what_she_takes(cards):
    s = build(cards)
    top = stack_library(s, ["Atraxa, Grand Unifier", "Grizzly Bears", "Forest", "Forest", "Forest", "Forest"])
    kaalia = put(s, "Kaalia, Zenith Seeker", "hand")
    mana(s, R=1, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=kaalia.id)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    d = decision(s, "pick_looked")
    assert [o.id for o in d.options] == [top[0]]  # the Angel
    hidden_from_bob(s, top)
    choose(s, [top[0]], resolve=True)
    assert s.state.cards[top[0]].zone == "p1:hand"
    replay_matches(s)



# -- Thassa's Oracle: X against the library (104.2b) ---------------------------------------------------------
def thin_library(s, keep):
    """Leave only these cards (by name) in Alice's library: the rest go to exile."""
    lib = zone(s.state, "p1", "library")
    names = list(keep)
    kept = []
    for cid in lib:
        name = s.state.cards[cid].name
        if name in names:
            names.remove(name)
            kept.append(cid)
    act(s, "p1", type="move", card_ids=[c for c in lib if c not in kept], to={"zone": "exile", "player": "p1"})
    return kept


def test_thassas_oracle_wins_when_devotion_covers_the_library(cards):
    s = build(cards)
    oracle = put(s, "Thassa's Oracle", "hand")
    kept = thin_library(s, ["Forest", "Divination"])
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=oracle.id)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    d = decision(s, "pick_looked")  # devotion to blue 2: both cards looked at, privately
    assert {o.id for o in d.options} == set(kept)
    hidden_from_bob(s, kept, names=False)
    choose(s, [kept[1]], resolve=True)
    assert zone(s.state, "p1", "library")[0] == kept[1]
    assert s.state.rules.winner == "p1" and "p2" in s.state.rules.lost
    replay_matches(s)


def test_thassas_oracle_no_win_with_a_bigger_library_or_a_persecutor(cards):
    s = build(cards)
    oracle = put(s, "Thassa's Oracle", "hand")
    thin_library(s, ["Forest", "Forest", "Forest"])  # devotion 2 < 3
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=oracle.id)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    choose(s, [], resolve=True)
    assert s.state.rules.winner is None
    s2 = build(cards)
    put(s2, "Abyssal Persecutor", "battlefield")
    oracle = put(s2, "Thassa's Oracle", "hand")
    thin_library(s2, ["Forest"])
    mana(s2, U=2)
    act(s2, "p1", type="cast_spell", card_id=oracle.id)
    pass_until_stack_empty(s2)
    pass_until_stack_empty(s2)
    choose(s2, [], resolve=True)
    assert s2.state.rules.winner is None  # "You can't win the game": left to the players
    replay_matches(s2)


# -- a once-each-turn free cast (a static permission) ----------------------------------------------------------
def test_zaffai_one_free_instant_or_sorcery_each_of_your_turns(cards):
    s = build(cards)
    put(s, "Zaffai and the Tempests", "battlefield")
    div, bolt, bears = put(s, "Divination", "hand"), put(s, "Lightning Bolt", "hand"), put(s, "Grizzly Bears", "hand")
    hints = s.view("p1")["rules"]["hints"]
    assert div.id in hints["free_castable"] and bolt.id in hints["free_castable"] and bears.id not in hints["free_castable"]
    act(s, "p1", type="cast_spell", card_id=div.id, free=True)
    pass_until_stack_empty(s)
    assert s.state.cards[div.id].zone == "p1:graveyard" and s.state.players["p1"].mana == {}
    with pytest.raises(ActionError):  # once each turn: used up
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])
    replay_matches(s)



# -- 508.4: onto the battlefield tapped and attacking ------------------------------------------------------------
def test_jet_puts_a_small_creature_in_attacking_and_it_never_attacked(cards):
    s = build(cards)
    jet = put(s, "Jet, Rebel Leader", "battlefield")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    top = stack_library(s, ["Divination", "Grizzly Bears", "Goblin Dark-Dwellers", "Forest", "Forest"])
    hold(s)
    to_attack(s, jet)
    d = decision(s, "pick_looked")
    assert [o.id for o in d.options] == [top[1]]  # creature cards with mana value 3 or less
    hidden_from_bob(s, [top[0], top[2]], names=False)
    choose(s, [top[1]])
    bears = s.state.cards[top[1]]
    assert bears.zone == "p1:battlefield" and bears.tapped and bears.attacking is not None and bears.attacking.id == "p2"
    assert not any("attack" in json.dumps(e.model_dump(mode="json")) for e in s.state.rules.pending_triggers)
    run_until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 40 - 3 - 2
    replay_matches(s)


def test_winota_human_enters_attacking_a_chosen_planeswalker_and_is_indestructible(cards):
    s = build(cards)
    put(s, "Winota, Joiner of Forces", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield")
    gideon = put(s, "Gideon Jura", "battlefield", pid="p2")
    act(s, "p2", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    top = stack_library(s, ["Forest", "Jet, Rebel Leader", "Forest", "Forest", "Forest", "Forest"])
    hold(s)
    to_attack(s, bears)
    d = decision(s, "pick_looked")
    choose(s, [top[1]])
    d = decision(s, "token_attack")  # 508.4: Bob, or Bob's planeswalker
    assert {o.id for o in d.options} == {"p2", gideon.id}
    choose(s, [gideon.id])
    jet = s.state.cards[top[1]]
    assert jet.attacking is not None and jet.attacking.id == gideon.id
    assert "indestructible" in s.state.rules.effects[-1].model_dump_json()
    replay_matches(s)


def test_raph_and_mikey_reveal_until_a_creature_and_put_it_in_attacking(cards):
    s = build(cards)
    rm = put(s, "Raph & Mikey, Troublemakers", "battlefield")
    top = stack_library(s, ["Forest", "Divination", "Grizzly Bears", "Forest"])
    to_attack(s, rm)
    assert s.state.cards[top[2]].zone == "p1:battlefield"
    assert s.state.players["p2"].life == 40 - 7 - 2  # Raph & Mikey and the Bears, unblocked
    library = zone(s.state, "p1", "library")
    assert set(library[-2:]) == {top[0], top[1]} and library[0] == top[3]
    replay_matches(s)
