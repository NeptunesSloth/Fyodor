"""Tutors (wave 3T): "Search your library for a card …, reveal it, put it into your hand / on top /
onto the battlefield, then shuffle" (CR 701.23 search, 701.24 shuffle, 401.2 a library is hidden).
Cards are transcribed from the card database (current Oracle). Only the searcher sees the library
while searching; a revealed card is public (701.20a); the search may find nothing for a stated
quality (701.23b) and the library is shuffled anyway; replay and reload reproduce the table."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.language import parse_sentence
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import pass_until_stack_empty, rules


def _spell(name, cost, cmc, type_line, text, colors):
    return card(name, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text, colors=colors, color_identity=colors)


REAL = [
    _spell("Demonic Tutor", "{1}{B}", 2.0, "Sorcery", "Search your library for a card, put that card into your hand, then shuffle.", ["B"]),
    _spell("Vampiric Tutor", "{B}", 1.0, "Instant", "Search your library for a card, then shuffle and put that card on top. You lose 2 life.", ["B"]),
    _spell("Worldly Tutor", "{G}", 1.0, "Instant", "Search your library for a creature card, reveal it, then shuffle and put the card on top.", ["G"]),
    _spell("Enlightened Tutor", "{W}", 1.0, "Instant",
           "Search your library for an artifact or enchantment card, reveal it, then shuffle and put that card on top.", ["W"]),
    _spell("Eladamri's Call", "{G}{W}", 2.0, "Instant", "Search your library for a creature card, reveal that card, put it into your hand, then shuffle.",
           ["G", "W"]),
    _spell("Fabricate", "{2}{U}", 3.0, "Sorcery", "Search your library for an artifact card, reveal it, put it into your hand, then shuffle.", ["U"]),
    _spell("Chord of Calling", "{X}{G}{G}{G}", 3.0, "Instant",
           "Search your library for a creature card with mana value X or less, put it onto the battlefield, then shuffle.", ["G"]),
    _spell("Cultivate", "{2}{G}", 3.0, "Sorcery",
           "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
           ["G"]),
    _spell("Farseek", "{1}{G}", 2.0, "Sorcery",
           "Search your library for a Plains, Island, Swamp, or Mountain card, put it onto the battlefield tapped, then shuffle.", ["G"]),
    _spell("Diabolic Intent", "{1}{B}", 2.0, "Sorcery",
           "As an additional cost to cast this spell, sacrifice a creature.\nSearch your library for a card, put that card into your hand, then shuffle.", ["B"]),
    _spell("Path to Exile", "{W}", 1.0, "Instant",
           "Exile target creature. Its controller may search their library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
           ["W"]),
    card("Krosan Verge", type_line="Land", oracle_text="This land enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Search your library for "
         "a Forest card and a Plains card, put them onto the battlefield tapped, then shuffle."),
    _spell("Wide Search Test", "{1}", 1.0, "Sorcery",
           "Search your library for any number of basic land cards, put them onto the battlefield, then shuffle.", []),
    _spell("Either Search Test", "{1}", 1.0, "Sorcery",
           "Search your library for a basic land card or an Equipment card, put it onto the battlefield, then shuffle.", []),
    card("Test Blade", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment", oracle_text=""),
    card("Plains", set_code="cmm", number="1000", type_line="Basic Land — Plains", oracle_text="({T}: Add {W}.)", color_identity=["W"]),
    _spell("Named Search Test", "{1}", 1.0, "Sorcery",
           "Search your library for a card named Sol Ring, reveal it, put it into your hand, then shuffle.", []),
    _spell("Exile Search Test", "{1}", 1.0, "Sorcery", "Search your library for an artifact card and exile it.", []),
    card("Sol Ring", mana_cost="{1}", cmc=1.0, type_line="Artifact", oracle_text="{T}: Add {C}{C}."),
    card("Mind Stone", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text="{T}: Add {C}."),
    card("Oblivion Ring", mana_cost="{2}{W}", cmc=3.0, type_line="Enchantment", oracle_text="", colors=["W"], color_identity=["W"]),
    card("Craterhoof Behemoth", mana_cost="{5}{G}{G}{G}", cmc=8.0, type_line="Creature — Beast", power="5", toughness="5", oracle_text="",
         colors=["G"], color_identity=["G"]),
]


@pytest.fixture()
def tcards(settings: Settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


LIBRARY = ((1, "Sol Ring"), (1, "Mind Stone"), (1, "Oblivion Ring"), (1, "Craterhoof Behemoth"), (1, "Elvish Visionary"),
           (1, "Ambush Viper"), (3, "Forest"), (2, "Island"))


def table(cards, spells, library=LIBRARY):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in spells] + list(library))
    bob = deck(cards, "Atraxa, Praetors' Voice", [(12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    if spells:
        act(s, "p1", type="draw", count=len(spells))
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def give(s, **m):
    act(s, "p1", type="add_mana", player="p1", mana=m)


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=named(s, name).id, **kw)
    pass_until_stack_empty(s)


def decision(s):
    d = rules(s).decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p1"
    return d


def pick(s, *names):
    d = decision(s)
    ids = [next(o.id for o in d.options if s.state.cards[o.id].name == n) for n in names]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
    pass_until_stack_empty(s)
    return ids


def option_names(s):
    return sorted(s.state.cards[o.id].name for o in decision(s).options)


def replay_matches(s):
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def hidden_from_bob(s, ids, prompt="Search your library"):
    """While Alice searches, Bob's view carries neither the options nor the library's cards (live or after a reload)."""
    for session in (s, reloaded(s)):
        bob = json.dumps(session.view("p2"))
        d = session.view("p2")["rules"]["decision"]
        assert d["kind"] == "waiting" and "options" not in d
        for cid in ids:
            assert cid not in bob and s.state.cards[cid].name not in bob
        alice = session.view("p1")["rules"]["decision"]
        assert alice["options"] and alice["prompt"].startswith(prompt)


# -- the wording --------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "search your library for a creature card, reveal it, then shuffle and put the card on top",
    "search your library for an artifact or enchantment card, reveal it, then shuffle and put that card on top",
    "search your library for a creature card, reveal that card, put it into your hand, then shuffle",
    "search your library for a creature card with mana value X or less, put it onto the battlefield, then shuffle",
    "search your library for a green creature card with mana value X or less, put it onto the battlefield, then shuffle",
    "search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle",
    "search your library for a Plains, Island, Swamp, or Mountain card, put it onto the battlefield tapped, then shuffle",
    "search your library for a basic land card and put it onto the battlefield tapped",
    "search your library for a creature card, reveal it, and put it into your hand",
    "search your library for a card named ~, reveal it, put it into your hand, then shuffle",
    "search your library for an artifact card and exile it",
])
def test_the_wordings_parse(text):
    found = parse_sentence(text)
    assert found is not None and found[0][0]["do"] == "search"


@pytest.mark.parametrize("text", [
    "search your library for a card, put that card into your hand, discard a card at random, then shuffle",  # (Gamble: not read)
    "search your library and/or graveyard for a creature card with mana value X or less and put it onto the battlefield",
    "search your library for a creature card with mana value X or greater, put it into your hand, then shuffle",
    "search your library for up to three creature cards, put one onto the battlefield and the other into your hand, then shuffle",
])
def test_what_cannot_be_done_correctly_is_refused(text):
    assert parse_sentence(text) is None


def test_the_shape_of_the_effect():
    e = parse_sentence("search your library for a card named ~, reveal it, put it into your hand, then shuffle")[0][0]
    assert e["name"] == "~" and e["to"] == "hand" and e["reveal"] and "shuffle" not in e
    e = parse_sentence("search your library for an artifact card and exile it")[0][0]
    assert e["to"] == "exile" and e["shuffle"] is False
    e = parse_sentence("search your library for a creature card with mana value X or less, put it onto the battlefield, then shuffle")[0][0]
    assert e["mv"] == ["<=", {"x": 1}]
    e = parse_sentence("search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped "
                       "and the other into your hand, then shuffle")[0][0]
    assert (e["to"], e["to2"], e["max"]) == ("battlefield_tapped", "hand", 2)


# -- Demonic Tutor ------------------------------------------------------------------------------
def test_demonic_tutor_is_a_private_search_of_the_whole_library(tcards):
    s = table(tcards, ["Demonic Tutor"])
    give(s, B=1, C=1)
    library = set(zone(s.state, "p1", "library"))
    cast(s, "Demonic Tutor")
    d = decision(s)
    assert {o.id for o in d.options} == library and d.min_choices == d.max_choices == 1  # 701.23d: a card, any card
    hidden_from_bob(s, library)
    [sol] = pick(s, "Sol Ring")
    assert s.state.cards[sol].zone == "p1:hand"
    assert not (set(zone(s.state, "p1", "library")) & library)  # shuffled: every card a new object (701.24)
    assert len(zone(s.state, "p1", "library")) == len(library) - 1
    assert "Sol Ring" not in json.dumps(s.view("p2"))  # not revealed: Bob learns nothing
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_diabolic_intent_sacrifices_a_creature_as_an_additional_cost_then_searches(tcards):
    """The search line is the Demonic Tutor grammar; "As an additional cost … sacrifice a creature" (601.2b) is paid
    as the spell is cast (wave 3$): with no creature to sacrifice the cast is refused, never half-automated."""
    assert parse_sentence("search your library for a card, put that card into your hand, then shuffle") is not None
    s = table(tcards, ["Diabolic Intent"])
    give(s, B=1, C=1)
    with pytest.raises(ActionError, match="can't pay"):
        act(s, "p1", type="cast_spell", card_id=named(s, "Diabolic Intent").id)
    act(s, "p1", type="create_token", player="p1", token={"name": "Bear", "type_line": "Token Creature — Bear", "power": "2", "toughness": "2"})
    act(s, "p1", type="cast_spell", card_id=named(s, "Diabolic Intent").id)
    pass_until_stack_empty(s)
    assert not any(c.name == "Bear" for c in s.state.cards.values())
    assert rules(s).decision is not None and rules(s).decision.kind != "manual_resolution"


# -- tutors that put the card on top ------------------------------------------------------------
def test_vampiric_tutor_puts_it_on_top_and_costs_life(tcards):
    s = table(tcards, ["Vampiric Tutor"])
    give(s, B=1)
    life = s.state.players["p1"].life
    cast(s, "Vampiric Tutor")
    ids = {o.id for o in decision(s).options}
    hidden_from_bob(s, ids)
    pick(s, "Craterhoof Behemoth")
    top = zone(s.state, "p1", "library")[0]
    assert s.state.cards[top].name == "Craterhoof Behemoth" and s.state.players["p1"].life == life - 2
    assert "Craterhoof" not in json.dumps(s.view("p2"))  # (not revealed, and a library is hidden)
    assert "Craterhoof" not in json.dumps(reloaded(s).view("p2"))
    replay_matches(s)


def test_worldly_tutor_finds_only_creatures_and_reveals_it(tcards):
    s = table(tcards, ["Worldly Tutor"])
    give(s, G=1)
    cast(s, "Worldly Tutor")
    assert option_names(s) == ["Ambush Viper", "Craterhoof Behemoth", "Elvish Visionary"]  # the server filtered
    hidden_from_bob(s, [o.id for o in decision(s).options])
    pick(s, "Elvish Visionary")
    top = zone(s.state, "p1", "library")[0]
    assert s.state.cards[top].name == "Elvish Visionary"
    assert "Elvish Visionary" in json.dumps(s.view("p2"))  # 701.20a: revealed to everyone
    replay_matches(s)


def test_enlightened_tutor_artifact_or_enchantment(tcards):
    s = table(tcards, ["Enlightened Tutor"])
    give(s, W=1)
    cast(s, "Enlightened Tutor")
    assert option_names(s) == ["Mind Stone", "Oblivion Ring", "Sol Ring"]
    pick(s, "Oblivion Ring")
    assert s.state.cards[zone(s.state, "p1", "library")[0]].name == "Oblivion Ring"


# -- tutors that put the card into hand ---------------------------------------------------------
def test_eladamris_call_and_fabricate_reveal_what_they_find(tcards):
    s = table(tcards, ["Eladamri's Call", "Fabricate"])
    give(s, G=1, W=1)
    cast(s, "Eladamri's Call")
    assert option_names(s) == ["Ambush Viper", "Craterhoof Behemoth", "Elvish Visionary"]
    [viper] = pick(s, "Ambush Viper")
    assert s.state.cards[viper].zone == "p1:hand" and "Ambush Viper" in json.dumps(s.view("p2"))
    give(s, U=1, C=2)
    cast(s, "Fabricate")
    assert option_names(s) == ["Mind Stone", "Sol Ring"]
    pick(s, "Sol Ring")
    assert named(s, "Sol Ring").zone == "p1:hand"
    replay_matches(s)


def test_a_search_with_a_stated_quality_may_find_nothing_and_still_shuffles(tcards):
    s = table(tcards, ["Fabricate"], library=((6, "Forest"), (1, "Elvish Visionary")))
    give(s, U=1, C=2)
    library = set(zone(s.state, "p1", "library"))
    cast(s, "Fabricate")
    d = decision(s)
    assert d.options == [] and d.min_choices == 0  # 701.23b: it may fail to find
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    pass_until_stack_empty(s)
    assert rules(s).decision is None
    assert len(zone(s.state, "p1", "hand")) == 0 and not (set(zone(s.state, "p1", "library")) & library)
    replay_matches(s)


# -- onto the battlefield -----------------------------------------------------------------------
@pytest.mark.parametrize(("x", "found"), [(0, []), (2, ["Ambush Viper", "Elvish Visionary"]),
                                           (8, ["Ambush Viper", "Craterhoof Behemoth", "Elvish Visionary"])])
def test_chord_of_calling_uses_x_as_a_mana_value_ceiling(tcards, x, found):
    s = table(tcards, ["Chord of Calling"])
    give(s, G=3, C=x)
    cast(s, "Chord of Calling", x_value=x)
    assert option_names(s) == found
    if found:
        hidden_from_bob(s, [o.id for o in decision(s).options])
        [cid] = pick(s, found[0])
        assert s.state.cards[cid].zone == "p1:battlefield" and not s.state.cards[cid].tapped
    else:
        act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    replay_matches(s)


def test_farseek_finds_a_basic_land_type_from_a_list(tcards):
    s = table(tcards, ["Farseek"])
    give(s, G=1, C=1)
    cast(s, "Farseek")
    assert option_names(s) == ["Island", "Island"]
    [isl] = pick(s, "Island")
    assert s.state.cards[isl].zone == "p1:battlefield" and s.state.cards[isl].tapped


def test_cultivate_splits_two_lands_between_battlefield_and_hand(tcards):
    s = table(tcards, ["Cultivate"])
    give(s, G=1, C=2)
    cast(s, "Cultivate")
    d = decision(s)
    assert d.max_choices == 2
    forest = next(o.id for o in d.options if s.state.cards[o.id].name == "Forest")
    island = next(o.id for o in d.options if s.state.cards[o.id].name == "Island")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest, island])
    split = decision(s)  # which goes onto the battlefield: Alice's private choice
    assert "tapped" in split.prompt
    hidden_from_bob(s, [], prompt="Choose the card that goes")
    act(s, "p1", type="choose", decision_id=split.id, option_ids=[island])
    pass_until_stack_empty(s)
    assert s.state.cards[island].zone == "p1:battlefield" and s.state.cards[island].tapped
    assert s.state.cards[forest].zone == "p1:hand"
    assert {"Forest", "Island"} <= {n for n in json.dumps(s.view("p2")).split('"') if n in ("Forest", "Island")}  # revealed
    replay_matches(s)


def test_cultivate_finding_one_land_lets_you_choose_where_it_goes(tcards):
    s = table(tcards, ["Cultivate"])
    give(s, G=1, C=2)
    cast(s, "Cultivate")
    [forest] = pick(s, "Forest")
    assert s.state.cards[forest].zone == "p1:battlefield"  # (one found: it is the one that goes first)
    assert rules(s).decision is None


# -- by name, and without a shuffle ---------------------------------------------------------------
def test_a_card_named_only_finds_that_name(tcards):
    s = table(tcards, ["Named Search Test"])
    give(s, C=1)
    cast(s, "Named Search Test")
    assert option_names(s) == ["Sol Ring"]
    pick(s, "Sol Ring")
    assert named(s, "Sol Ring").zone == "p1:hand"
    replay_matches(s)


def test_without_shuffle_in_the_text_the_library_keeps_its_order(tcards):
    s = table(tcards, ["Exile Search Test"])
    give(s, C=1)
    before = list(zone(s.state, "p1", "library"))
    cast(s, "Exile Search Test")
    [ring] = pick(s, "Mind Stone")
    assert s.state.cards[ring].zone == "p1:exile"
    assert zone(s.state, "p1", "library") == [c for c in before if c != ring]  # 701.24: only shuffled when told to
    replay_matches(s)


# -- other players, several kinds of card, any number -------------------------------------------
def test_path_to_exile_gives_its_controller_a_private_optional_search(tcards):
    s = table(tcards, ["Path to Exile"])
    act(s, "p2", type="create_token", player="p2", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "3",
                                                            "toughness": "3", "text": ""})
    brute = named(s, "Brute", "p2")
    give(s, W=1)
    bob_library = set(zone(s.state, "p2", "library"))
    cast(s, "Path to Exile", targets=[brute.id])
    d = rules(s).decision
    assert d.kind == "choose_cards" and d.player == "p2"  # Bob searches Bob's library: 701.23a
    assert {o.id for o in d.options} == bob_library  # (basic Islands: all of it)
    alice = json.dumps(s.view("p1"))
    assert not any(o.id in alice for o in d.options) and s.view("p1")["rules"]["decision"]["kind"] == "waiting"
    assert d.min_choices == 0  # "may": he can decline
    island = d.options[0].id
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[island])
    pass_until_stack_empty(s)
    assert s.state.cards[island].zone == "p2:battlefield" and s.state.cards[island].tapped
    assert not (set(zone(s.state, "p2", "library")) & bob_library)  # Bob's library was shuffled
    replay_matches(s)


def test_krosan_verge_finds_one_card_of_each_kind(tcards):
    s = table(tcards, [], library=((1, "Krosan Verge"), (2, "Forest"), (2, "Plains"), (1, "Island")))
    act(s, "p1", type="draw", count=1)
    verge = named(s, "Krosan Verge")
    act(s, "p1", type="play_land", card_id=verge.id)
    give(s, C=2)
    act(s, "p1", type="untap_all", player="p1")  # (it entered tapped)
    act(s, "p1", type="activate_ability", card_id=verge.id, ability=2)
    pass_until_stack_empty(s)
    assert option_names(s) == ["Forest", "Forest"]
    [forest] = pick(s, "Forest")
    assert option_names(s) == ["Plains", "Plains"]  # next kind: never the card already found
    [plains] = pick(s, "Plains")
    assert {s.state.cards[forest].zone, s.state.cards[plains].zone} == {"p1:battlefield"}
    assert s.state.cards[forest].tapped and s.state.cards[plains].tapped
    replay_matches(s)


def test_any_number_of_basic_lands(tcards):
    s = table(tcards, ["Wide Search Test"], library=((4, "Forest"), (2, "Island"), (1, "Sol Ring")))
    give(s, C=1)
    cast(s, "Wide Search Test")
    d = decision(s)
    assert d.min_choices == 0 and d.max_choices == 6 and len(d.options) == 6  # (Sol Ring isn't a basic land)
    ids = [o.id for o in d.options][:4]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
    pass_until_stack_empty(s)
    assert all(s.state.cards[i].zone == "p1:battlefield" and not s.state.cards[i].tapped for i in ids)
    replay_matches(s)


def test_alternatives_a_basic_land_or_an_equipment(tcards):
    s = table(tcards, ["Either Search Test"], library=((2, "Forest"), (1, "Test Blade"), (1, "Sol Ring")))
    give(s, C=1)
    cast(s, "Either Search Test")
    assert option_names(s) == ["Forest", "Forest", "Test Blade"]
    pick(s, "Test Blade")
    assert named(s, "Test Blade").zone == "p1:battlefield"
