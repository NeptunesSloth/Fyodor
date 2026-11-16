"""-- planechase more (wave E1) -- the face-up plane's leftover statics and planeswalk / encounter lines (app/rules/planar_more.py), each on
its real Oracle text with the face-up plane as the rules object ("you" is the planar controller, 311.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, to_turn
from tests.test_rules_planechase_plumbing import PLANES as BASE
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Lake Silencio': ('Plane — Earth', "Still Point in Time — All spells have split second. (As long as a spell with split second is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nWhenever chaos ensues, Lake Silencio deals 6 damage to target creature an opponent controls. If a creature dealt damage this way would die this turn, exile it instead."),  # noqa: E501
    'Naya': ('Plane — Alara', 'You may play any number of lands on each of your turns.\nWhenever chaos ensues, target red, green, or white creature you control gets +1/+1 until end of turn for each land you control.'),  # noqa: E501
    'Naktamun': ('Plane — Amonkhet', "Each creature card in your graveyard has embalm. Its embalm cost is equal to its mana cost. (Exile a creature card from your graveyard and pay its embalm cost: Create a token that's a copy of it, except it's a white Zombie in addition to its other types with no mana cost. Embalm only as a sorcery.)\nWhenever chaos ensues, you may discard a card. If you do, draw a card."),  # noqa: E501
    'Prahv': ('Plane — Ravnica', "If you cast a spell this turn, you can't attack with creatures.\nIf you attacked with creatures this turn, you can't cast spells.\nWhenever chaos ensues, you gain life equal to the number of cards in your hand."),  # noqa: E501
    'Skybreen': ('Plane — Kaldheim', "Players play with the top card of their libraries revealed.\nSpells that share a card type with the top card of a library can't be cast.\nWhenever chaos ensues, target player loses life equal to the number of cards in their hand."),  # noqa: E501
    'Horizon Boughs': ('Plane — Pyrulea', "All permanents untap during each player's untap step.\nWhenever chaos ensues, you may search your library for up to three basic land cards, put them onto the battlefield tapped, then shuffle."),  # noqa: E501
    'Edge of Malacol': ('Plane — Belenon', 'If a creature you control would untap during your untap step, put two +1/+1 counters on it instead.\nWhenever chaos ensues, untap each creature you control.'),  # noqa: E501
    'Bowie Base One': ('Plane — Mars', "At the beginning of your end step, goad target creature controlled by the player to your left. (Until your next turn, that creature attacks each combat if able and attacks a player other than you if able.)\nWhenever chaos ensues, target creature gains islandwalk until end of turn. (It can't be blocked as long as defending player controls an Island.)"),  # noqa: E501
    "The Doctor's Tomb": ('Plane — Trenzalore', "If a creature would die, instead exile it and that creature's controller loses 2 life.\nWhenever chaos ensues, redistribute any number of players' life totals. (Each of those players gets one life total back.)"),  # noqa: E501
    'We Hope You Like Squirrels': ('Plane — Secret Lair', "At the beginning of each player's upkeep and whenever a player casts a spell, that player creates a 1/1 green Squirrel creature token.\nWhenever chaos ensues, put a +1/+1 counter on each Squirrel you control."),  # noqa: E501
    'Sea of Sand': ('Plane — Rabiah', "Players reveal each card they draw.\nWhenever a player draws a land card, that player gains 3 life.\nWhenever a player draws a nonland card, that player loses 3 life.\nWhenever chaos ensues, put target permanent on top of its owner's library."),  # noqa: E501
    'Unyaro': ('Plane — Zhalfir', "At the beginning of your end step, if you planeswalked to Unyaro this turn, untap all creatures. They phase out until a player planeswalks. (Treat them and anything attached to them as though they didn't exist.)\nWhenever chaos ensues, create two 2/2 white and blue Knight creature tokens with vigilance."),  # noqa: E501
    'TARDIS Bay': ('Plane — Gallifrey', 'The first spell you cast during each of your turns with mana value 2 or greater has cascade. (When you cast that spell, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)\nWhen chaos ensues, gain control of target artifact. Then planeswalk.'),  # noqa: E501
    'Singing Towers of Darillium': ('Plane — Darillium', 'Each nonland card in your hand without foretell has foretell. Its foretell cost is equal to its mana cost reduced by {2}. (During your turn, you may pay {2} and exile it from your hand face down. Cast it on a later turn for its foretell cost.)\nWhenever chaos ensues, you may cast a foretold card you own from exile without paying its mana cost this turn.'),  # noqa: E501
    "Amy's Home": ('Plane — Earth', "When you planeswalk to Amy's Home and at the beginning of your upkeep, you may exile a nonland card from your hand with a number of time counters on it equal to its mana value. If it doesn't have suspend, it gains suspend.\nWhenever chaos ensues, time travel. (For each suspended card you own and each permanent you control with a time counter on it, you may add or remove a time counter.)"),  # noqa: E501
    'Enigma Ridges': ('Plane — Echoir', 'When you planeswalk to Enigma Ridges, each player who controls fewer lands than the player who controls the most lands searches their library for a number of basic land cards less than or equal to the difference, reveals them, puts them into their hand, then shuffles.\nWhenever chaos ensues, draw a card, then you may put a land card from your hand onto the battlefield.'),  # noqa: E501
}
FULL = [n for n in PLANES if n not in ("Singing Towers of Darillium",)]  # (its chaos line: not this wave)
from tests.test_rules_planechase_deck import PLANES as DECK  # noqa: E402  (wave D: Spatial Merging, two planes face up)

ALL = {**PLANES, "Krosa": BASE["Krosa"], "Spatial Merging": DECK["Spatial Merging"]}
EXTRA = [card(n, set_code="opca", number=f"PLM-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(ALL.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Battlegrowth", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
          real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R")]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


MINE = ((1, "Runeclaw Bear"), (1, "Battlegrowth"), (1, "Shock"), (9, "Forest"))


def table(cards, planes: list[str], *, mine=MINE, bob=((2, "Runeclaw Bear"), (1, "Shock"), (10, "Island"))) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", list(mine))
    bob_deck = deck(cards, "Atraxa, Praetors' Voice", list(bob))
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=ALL[n][0] == "Phenomenon") for n in planes]
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob_deck)], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=len(pool)), planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_zone(s, c, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": c.owner, "zone": zone})
    return c


def plan(s, pid="p1"):
    return Plan(s.state, pid, s.cards, None)


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Lake Silencio: every spell has split second (702.61a) ----------------------------------------------------------------------------
def test_lake_silencio_all_spells_have_split_second(cards):
    s = table(cards, ["Lake Silencio", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    shock = to_zone(s, named(s, "Shock", "p2"), "hand", "p2")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")  # (Bob has priority with Battlegrowth on the stack)
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=shock.id, targets=[bear.id])
    settle(s)
    assert bear.counters.get("+1/+1") == 1
    act(s, "p1", type="planeswalk")  # (to Krosa: no split second any more)
    growth2 = to_zone(s, growth, "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth2.id, targets=[bear.id])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=shock.id, targets=[bear.id])
    check(s)


# -- Naya: any number of lands (305.2) -------------------------------------------------------------------------------------------------
def test_naya_any_number_of_lands(cards):
    s = table(cards, ["Naya", "Krosa"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]
    for f in forests:
        to_zone(s, f, "hand")
        act(s, "p1", type="play_land", card_id=f.id)
    assert all(f.zone == "p1:battlefield" for f in forests)
    act(s, "p1", type="planeswalk")  # (Krosa: the four land plays still count, 305.2a; no more)
    extra = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    to_zone(s, extra, "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=extra.id)
    check(s)


# -- Naktamun: embalm for creature cards in your graveyard (702.128a) ----------------------------------------------------------------
def test_naktamun_creature_cards_in_your_graveyard_have_embalm(cards):
    s = table(cards, ["Naktamun", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "graveyard")
    granted = next(a for a in plan(s).ch(bear).abilities if "embalm" in a.keywords)
    assert granted.text == "Embalm {1}{G}"
    mana(s, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=granted.index, sources=[])
    settle(s)
    assert bear.zone == "p1:exile"
    token = next(c for c in s.state.cards.values() if c.token and c.name == "Runeclaw Bear")
    ch = plan(s).ch(token)
    assert ch.colors == frozenset({"W"}) and "Zombie" in ch.subtypes
    bob_bear = to_zone(s, named(s, "Runeclaw Bear", "p2"), "graveyard", "p2")  # ("your" graveyard: the planar controller's only)
    assert not any("embalm" in a.keywords for a in plan(s).ch(bob_bear).abilities)
    check(s)


# -- Prahv (508.1, 601.3) --------------------------------------------------------------------------------------------------------------
def test_prahv_a_spell_cast_stops_attacks(cards):
    from app.rules import combat

    s = table(cards, ["Prahv", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    s.state.rules.controlled_since[bear.id].turn = 0
    p = plan(s)
    assert combat.attack_problem(s.state, bear, p.ch(bear), s.cards) is None
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    settle(s)
    p = plan(s)
    assert "Prahv" in (combat.attack_problem(s.state, bear, p.ch(bear), s.cards) or "")
    check(s)


def test_prahv_an_attack_stops_spells(cards):
    from app.rules import cast_limits
    from tests.test_rules_conditionals import attack, through_combat

    s = table(cards, ["Prahv", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    s.state.rules.controlled_since[bear.id].turn = 0
    shock = to_zone(s, named(s, "Shock"), "hand")
    p = plan(s)
    assert cast_limits.cast_problem(s.state, "p1", shock, p.ch(shock), s.cards) is None
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    attack(s, (bear, "p2"))
    through_combat(s)
    assert "Prahv" in (cast_limits.cast_problem(s.state, "p1", shock, plan(s).ch(shock), s.cards) or "")
    bob_shock = to_zone(s, named(s, "Shock", "p2"), "hand", "p2")  # (Bob didn't attack)
    assert cast_limits.cast_problem(s.state, "p2", bob_shock, plan(s).ch(bob_shock), s.cards) is None
    check(s)


# -- Skybreen (601.3) ----------------------------------------------------------------------------------------------------------------
def test_skybreen_spells_sharing_a_type_with_a_top_card_cant_be_cast(cards):
    s = table(cards, ["Skybreen", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    to_zone(s, named(s, "Shock"), "graveyard")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])  # (tops: lands; an instant is fine)
    settle(s)
    to_zone(s, growth, "hand")
    act(s, "p2", type="move", card_ids=[named(s, "Shock", "p2").id], to={"player": "p2", "zone": "library"}, position="top")  # (Bob's top card: an instant)
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    check(s)


# -- untap steps (502.3) -----------------------------------------------------------------------------------------------------------
def test_horizon_boughs_every_players_permanents_untap(cards):
    s = table(cards, ["Horizon Boughs", "Krosa"])
    mine = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    bobs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    to_turn(s, 2)  # (Bob's untap step: Alice's bear untaps too)
    assert not mine.tapped
    act(s, "p2", type="tap", card_ids=[bobs.id], tapped=True)
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    to_turn(s, 3)
    assert not mine.tapped and not bobs.tapped
    check(s)


def test_edge_of_malacol_counters_instead_of_untapping(cards):
    s = table(cards, ["Edge of Malacol", "Krosa"])
    mine = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    to_turn(s, 2)  # (Bob's untap step: not Alice's; nothing happens to her bear)
    assert mine.tapped and not mine.counters.get("+1/+1")
    to_turn(s, 3)
    assert mine.tapped and mine.counters.get("+1/+1") == 2
    forest = to_zone(s, named(s, "Forest"), "battlefield")  # (other permanents untap as normal)
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=True)
    to_turn(s, 5)
    assert mine.counters.get("+1/+1") == 4 and not forest.tapped
    check(s)


# -- Bowie Base One: "the player to your left" is the seat to the left, whatever the turn order (103.1) -------------------------------
def test_the_player_to_your_left_is_the_seat_not_the_turn_order(cards):
    from app.rules import selectors

    decks = [deck(cards, cmd, [(2, "Runeclaw Bear"), (10, "Forest")]) for cmd in ("Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss")]
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n) for n in ("Bowie Base One", "Krosa")]
    state = new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Cleo"), decks, strict=True)], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=2), planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    assert s.state.seat_order == ["p1", "p2", "p3"]
    bobs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    cleos = to_zone(s, named(s, "Runeclaw Bear", "p3"), "battlefield", "p3")
    sel = selectors.parse("creature the opponent to your left controls")
    assert sel is not None
    for reversed_ in (False, True):
        s.state.rules.turn_reversed110m = reversed_  # (Time Distortion / Aeon Engine: the turn order runs the other way)
        p = plan(s)
        assert p.left("p1") == "p2" and p.after("p1") == ("p3" if reversed_ else "p2")
        assert selectors.matches(p, sel, bobs, p.ch(bobs), "p1", None)
        assert not selectors.matches(p, sel, cleos, p.ch(cleos), "p1", None)
    s.state.rules.turn_reversed110m = False
    check(s)


# -- The Doctor's Tomb: exile instead, and the controller loses 2 life (614.1a) --------------------------------------------------------
def test_the_doctors_tomb_exiles_a_dying_creature_and_its_controller_loses_two(cards):
    from tests.wave9c_kit import life

    s = table(cards, ["The Doctor's Tomb", "Krosa"])
    bobs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    shock = to_zone(s, named(s, "Shock"), "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=[bobs.id])
    settle(s)
    assert bobs.zone == "p2:exile" and life(s, "p2") == 38 and life(s, "p1") == 40
    check(s)


# -- We Hope You Like Squirrels: each upkeep and each spell cast (603.2) ----------------------------------------------------------------
def test_we_hope_you_like_squirrels(cards):
    s = table(cards, ["We Hope You Like Squirrels", "Krosa"])

    def squirrels(pid):
        return sum(1 for c in s.state.cards.values() if c.token and c.name == "Squirrel" and c.controller == pid and c.zone.endswith(":battlefield"))

    mine = squirrels("p1")
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    settle(s)
    assert squirrels("p1") == mine + 1 and squirrels("p2") == 0
    to_turn(s, 2)  # Bob's upkeep: Bob's Squirrel
    assert squirrels("p2") == 1 and squirrels("p1") == mine + 1
    check(s)


# -- Sea of Sand: draws are revealed; a land gains 3, a nonland loses 3 -----------------------------------------------------------------
def test_sea_of_sand_draw_triggers(cards):
    from tests.wave9c_kit import life

    s = table(cards, ["Sea of Sand", "Krosa"])
    to_turn(s, 2)  # Bob draws a Runeclaw Bear: revealed, he loses 3
    assert life(s, "p2") == 37
    assert any("reveals Runeclaw Bear" in " ".join(str(p.t or p.name) for p in e.parts) for e in s.state.log[-20:])
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "library"}, position="top")
    to_turn(s, 4)  # (Alice's turn 3: she draws her Runeclaw Bear and loses 3) Bob draws the Island: he gains 3
    assert life(s, "p1") == 37 and life(s, "p2") == 40
    check(s)


# -- Unyaro: phase out until a player planeswalks (702.26, 611.2a) -----------------------------------------------------------------------
def test_unyaro_phases_creatures_out_until_a_player_planeswalks(cards):
    s = table(cards, ["Krosa", "Unyaro"])
    mine = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    bobs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    act(s, "p1", type="planeswalk")  # (to Unyaro this turn)
    to_turn(s, 2)  # Alice's end step: they untap and phase out; Bob's untap step doesn't phase them in
    assert mine.zone.endswith(":phased") and bobs.zone.endswith(":phased") and not mine.tapped
    act(s, "p2", type="planeswalk")  # (a player planeswalks: they phase in; a table action is read as the next engine action begins)
    act(s, "p2", type="pass_priority")
    assert mine.zone == "p1:battlefield" and bobs.zone == "p2:battlefield"
    check(s)


def test_unyaro_needs_the_planeswalk_this_turn(cards):
    s = table(cards, ["Unyaro", "Krosa"])
    to_turn(s, 2)  # (Unyaro was face up from the start of turn 1: Alice's end step — planeswalked to it this turn? at the start of the game)
    mine = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    to_turn(s, 3)  # (Bob's end step: he didn't planeswalk to it)
    to_turn(s, 4)  # (Alice's end step: neither)
    assert mine.zone == "p1:battlefield"
    check(s)


# -- TARDIS Bay: cascade for the first spell with mana value 2 or greater during your turn (702.85a, 601.2i) -------------------------
def test_tardis_bay_first_spell_with_mana_value_two_or_more_has_cascade(cards):
    s = table(cards, ["TARDIS Bay", "Krosa"])

    def cascades():
        return sum(1 for e in s.state.log if "Runeclaw Bear’s ability" in " ".join(str(p.t or p.name) for p in e.parts))  # (its cascade trigger)

    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])  # (mana value 1: no cascade, and it doesn't count)
    settle(s)
    assert cascades() == 0
    to_zone(s, bear, "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    settle(s)
    first = cascades()
    assert first > 0 and bear.zone == "p1:battlefield"
    to_zone(s, bear, "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)  # (the second such spell this turn: no cascade)
    settle(s)
    assert cascades() == first
    check(s)


# -- Singing Towers of Darillium: Dream Devourer's foretell grant; the foretold card keeps its cost after a planeswalk (ruling) ----------
def test_singing_towers_foretell_survives_a_planeswalk(cards):
    s = table(cards, ["Singing Towers of Darillium", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "hand")
    ability = next(a for a in plan(s).ch(bear).abilities if "foretell" in a.keywords)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, sources=[])
    settle(s)
    assert bear.zone == "p1:foretell"
    act(s, "p1", type="planeswalk")  # (to Krosa)
    to_turn(s, 3)
    mana(s, G=1)  # ({1}{G} reduced by {2}: {G})
    act(s, "p1", type="cast_spell", card_id=bear.id, sources=[])
    settle(s)
    assert bear.zone == "p1:battlefield"
    check(s)


# -- Amy's Home: exile a nonland card from your hand, suspended with time counters equal to its mana value (702.62b) ----------------------
def test_amys_home_suspends_a_card_from_hand(cards):
    s = table(cards, ["Krosa", "Amy's Home"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "hand")
    act(s, "p1", type="planeswalk")  # (to Amy's Home by hand: no planeswalk trigger; its upkeep half works)
    to_turn(s, 3)  # Alice's upkeep: she may exile a card; the first nonland card offered is her Runeclaw Bear

    # (exiled with 2 time counters; the suspend tick of this same upkeep then removed one: 702.62b)
    assert bear.zone == "p1:exile" and bear.counters.get("time") in (1, 2) and bear.id in s.state.rules.suspended
    check(s)


# -- several face-up planes (901.11c: Spatial Merging): each one's statics work, the second's too ----------------------------------------
def test_two_face_up_planes_both_statics_apply(cards, monkeypatch):
    from tests.test_rules_planechase_deck import faces, roll

    s = table(cards, ["Krosa", "Spatial Merging", "Naya", "Lake Silencio"])
    roll(s, monkeypatch, 1)  # (the planeswalker symbol: Spatial Merging, then both Naya and Lake Silencio)
    assert faces(s) == ["Naya", "Lake Silencio"]
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:3]
    for f in forests:  # (Naya, the first face-up plane)
        to_zone(s, f, "hand")
        act(s, "p1", type="play_land", card_id=f.id)
    assert all(f.zone == "p1:battlefield" for f in forests)
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")  # (Lake Silencio, the second: split second)
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    shock = to_zone(s, named(s, "Shock", "p2"), "hand", "p2")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=shock.id, targets=[bear.id])
    settle(s)
    check(s)


# -- Enigma Ridges: players short of the most lands search for up to the difference (608.2h, 101.4) --------------------------------------
def test_enigma_ridges_the_player_with_fewer_lands_searches(cards, monkeypatch):
    from tests.test_rules_planechase_deck import roll

    s = table(cards, ["Krosa", "Enigma Ridges"])
    for f in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]:
        to_zone(s, f, "battlefield")
    asked = []
    hand = len(s.state.zones["p2:hand"])
    roll(s, monkeypatch, 1, picks=["Island", "Island", "Island", "Island"], seen=asked)  # (the planeswalker symbol: to Enigma Ridges)
    assert s.state.cards[s.state.planechase.face_id].name == "Enigma Ridges"
    islands = [c for c in s.state.zones["p2:hand"] if s.state.cards[c].name == "Island"]
    assert len(s.state.zones["p2:hand"]) == hand + 3 and len(islands) == 3  # (Bob: up to the difference, three)
    assert [d.max_choices for d in asked if d.kind == "choose_cards"] == [3]
    assert all(d.player == "p2" for d in asked if d.kind != "order")
    check(s)
