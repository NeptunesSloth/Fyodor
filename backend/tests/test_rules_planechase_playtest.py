"""-- planechase playtest planes (wave G1) -- the defined lines of the playtest planes (app/rules/planar_playtest.py), on real Oracle text with
the rules engine on, then ``check`` (replay + save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import to_turn, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Shy Town': ('Plane — Chicago', 'Whenever you planeswalk here and whenever chaos ensues, for each opponent, put a shy counter on up to one target creature they control. That creature becomes a Coward in addition to its other types.\nAt the beginning of your upkeep, create a 2/2 red Warrior creature token with haste and "Cowards can\'t block Warriors."'),  # noqa: E501
    "Jalira's Show": ('Plane — Las Vegas', 'Whenever you attack, create a 1/1 red Performer creature token with flying.\nWhenever you planeswalk here or chaos ensues, destroy up to one target creature. When you do, its controller reveals cards from the top of their library until they reveal a creature card. The player puts that card onto the battlefield, then puts the rest on the bottom of their library in a random order.'),  # noqa: E501
    'Pursued by Something': ('Plane — Duskmourn', "At the beginning of your second main phase, if you control a tapped creature, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nWhenever Chaos ensues, exile target creature. If it's an instant or sorcery, cast it without paying its mana cost. Otherwise put it onto the battlefield under its owner's control."),  # noqa: E501
    'The Bean': ('Plane — Chicago', "When you planeswalk here, each player chooses a creature they control and creates a token that's a copy of it, except it's a Reflection in addition to its other types.\nAll Reflections have shadow. (They can block or be blocked only by creatures with shadow.)\nWhenever chaos ensues, create a token that's a copy of a creature you control, except it's a Reflection in addition to its other types."),  # noqa: E501
    'Tarnation': ('Plane — Thunder Junction', 'Whenever a player commits a crime, they may draw a card. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nWhenever chaos ensues, Tarnation deals 1 damage to any target.'),  # noqa: E501
    'Welcome to Valley': ('Plane — Bloomburrow', "Whenever you cast an animal spell, draw a card. (Animals are any non-human creature types that are animals in real life.)\nWhenever Chaos ensues, create a token that's a copy of target creature you control, except it's a 1/1."),  # noqa: E501
    "Sorin's Remastered Manor": ('Plane — Innistrad', 'When you planeswalk here and at the beginning your upkeep, put a spooky counter on target creature you control.\nSpooky creatures you control have +1/+1 and menace. (A creature is spooky if it has a spooky counter or it could be a horror movie monster.)\nA Murder at Markov Manor — Whenever chaos ensues, target spooky creature you control bites target opponent or creature an opponent controls. (The creature deals damage equal to its power to the creature your opponent controls. You gain that much life.)'),  # noqa: E501
    'Circus of the Sun': ('Plane — Las Vegas', 'Whenever you planeswalk here or at the beginning of your upkeep, create two 1/1 red performer creature tokens with flying and haste.\nWhenever one or more creatures you control with flying deal combat damage to a player, you may return it to your hand. If you do, draw cards equal to its power.\nWhenever Chaos ensues, put a flying counter on up to one target creature. It becomes a Performer in addition to its other types.'),  # noqa: E501
    'Black Lotus Lounge': ('Plane — MagicCon', 'When you planeswalk here and at the beginning of your upkeep, create a Black Lotus artifact token.\nWhenever Chaos ensues, each player draws a card for each artifact token they control.'),  # noqa: E501
    'City Hall': ('Plane — Chicago', "When you planeswalk here, you become the Monarch.\nWhenever Chaos ensues, each player may create two tapped treasure tokens. Each player who does can't attack you during their next turn."),  # noqa: E501
    'Game Knights Live': ('Plane — MagicCon', 'Whenever a player casts their commander or attacks with their commander, they may say "Only one may stand." If they do, that commander becomes a Knight in addition to its other types until a player planeswalks away from Game Knights Live.\nKnights you control have double strike and trample.\nWhenever chaos ensues, commanders you control can\'t be blocked this turn and gain "Whenever this creature deals combat damage to a player, draw a card" until end of turn.'),  # noqa: E501
    'The Windy City': ('Plane — Chicago', 'When you planeswalk here and at the beginning of your upkeep, put a flying counter on target nontoken creature you control without flying.\nWhenever chaos ensues, exile target creature with flying. For as long as it remains exiled, its owner may cast it by paying {2} rather than paying its mana cost.\nWhen you planeswalk away from The Windy City, remove all flying counters from all creatures.'),  # noqa: E501
    'Mojave Desert': ('Plane — Las Vegas', "Whenever you planeswalk here, each player searches their library for up to two basic land or Desert cards and puts them onto the battlefield tapped, then shuffles their library. If a Desert entered the battlefield under a player's control this way, they create a 1/1 black Snake creature token with deathtouch.\nWhenever Chaos ensues, create X 1/1 black Snake creature token with deathtouch, where X is 1 plus the number of nonbasic land types among lands that player controls."),  # noqa: E501
    "Raiders' Allegiance": ('Plane — Ixalan', 'Raid — At the beginning of your second main phase, for each player dealt combat damage this turn, you get a point counter and create a 2/2 black Pirate creature token with menace.\nWhenever you planeswalk away from here, each player with the most point counters or tied for the most point counters creates three Treasure tokens and draws three cards. Then remove all point counters from each player.\nWhenever Chaos ensues, proliferate for each Pirate you control.'),  # noqa: E501
    'Bicycle Rack': ('Plane — Amsterdam', 'Cards in each player\'s hand have cycling {2}.\nChaos: Until end of turn, creatures you control have "This creature gets +1/+1 for each card you\'ve discarded this turn."'),  # noqa: E501
    'The Command Zone': ('Plane — MagicCon', 'When you planeswalk here, each player who controls their commander draws a card. Other players may put their commander from the command zone onto the battlefield.\nIf an ability of your commander would trigger during your turn, that ability triggers an additional time.\nWhenever chaos ensues, the number of times each commander has been cast from the command zone becomes 0. (This resets commander tax.)'),  # noqa: E501
    'Ghirapur Grand Prix': ('Plane — Avishkar', 'When you planeswalk here, all players start their engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nAt the beginning of your end step, put X +1/+1 counters on target creature you control, where X is your speed.\nWhen you planeswalk away from Ghirapur Grand Prix, each player with the highest speed among players creates three Treasure tokens.'),  # noqa: E501
    'Academy at Tolaria West': ('Plane — Dominaria', 'At the beginning of your end step, if you have no cards in hand, draw seven cards.\nWhenever chaos ensues, discard your hand.'),  # noqa: E501
}
FILLER = "Academy at Tolaria West"
EXTRA = [card(n, set_code="punk", number=f"PG1-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G"),
          real("Serra Angel", "{3}{W}{W}", 5, "Creature — Angel", "Flying, vigilance", ("4", "4"), "W"),
          real("Kitesail Corsair", "{1}{U}", 2, "Creature — Human Pirate", "Kitesail Corsair has flying as long as it's attacking.", ("2", "1"), "U"),
          real("Indestructible Golem", "{4}", 4, "Artifact Creature — Golem", "Indestructible", ("3", "3"), ""),
          real("Opt", "{U}", 1, "Instant", "Scry 1.\nDraw a card.", None, "U"),
          real("Careful Study", "{U}", 1, "Sorcery", "Draw two cards, then discard two cards.", None, "U"),
          real("Desert", "", 0, "Land — Desert", "{T}: Add {C}.\n{T}: Desert deals 1 damage to target attacking creature. Activate only during the end "
               "of combat step.", None, "")]

# the lines this wave reads; the planes whose every line is read
FULL = ["Shy Town", "Jalira's Show", "Pursued by Something", "The Bean", "Tarnation", "Raiders' Allegiance", "Bicycle Rack", "City Hall",
        "The Windy City"]
PARTIAL = {"Welcome to Valley": [1], "Sorin's Remastered Manor": [0], "Circus of the Sun": [0, 2], "Black Lotus Lounge": [1], "Game Knights Live": [1, 2],
           "Mojave Desert": [0], "The Command Zone": [0, 2], "Ghirapur Grand Prix": [1, 2]}


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


def table(cards, planes: list[str], players: int = 3) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(3, "Runeclaw Bear"), (1, "Craw Wurm"), (1, "Serra Angel"), (2, "Kitesail Corsair"), (1, "Opt"),
                                             (1, "Careful Study"), (1, "Lightning Bolt"), (1, "Desert"), (1, "Indestructible Golem"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Runeclaw Bear"), (1, "Craw Wurm"), (1, "Opt"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(2, "Runeclaw Bear"), (1, "Serra Angel"), (10, "Forest")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)][:players]
    state = new_game(setups, shuffle=False, first_player=0, settings=GameSettings(planechase=True, planar_deck_size=len(pool)),
                     planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def resolve(s, picks=()):
    """Everything resolves; a choice takes the ``picks`` (ids, card ids or labels, in this order of preference) when offered, else the
    fewest it may."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def roll(s, monkeypatch, value, picks=()):
    """Alice rolls the planar die for the server's d6 ``value`` (1 planeswalker, 2 chaos, 3-6 blank), paying its cost (901.9)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [value])
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks)


def place(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith((":battlefield", ":command")))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_hand(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "hand"})
    return c


def on_battlefield(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield") and (pid is None or c.controller == pid)]


def tokens(s, pid, name=None):
    return [c for c in s.state.cards.values() if c.is_token and c.controller == pid and c.zone.endswith(":battlefield") and (name is None or c.name == name)]


def plan(s, pid="p1"):
    return Plan(s.state, pid, s.cards, None)


def commander(s, pid):
    return next(c for c in s.state.cards.values() if c.owner == pid and c.commander_key)


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name,lines", PARTIAL.items())
def test_lines_read(cards, name, lines):
    from app.rules import planar, scripts
    from app.rules.characteristics import printed_from_data

    ch = printed_from_data(cards.resolve(name), 0)
    defs = scripts.definitions(ch)
    assert [i for i in sorted(defs) if planar.ability_ok(defs[i])] == lines


# -- Shy Town: per opponent, a shy counter and Coward (planeswalking here, and chaos) ------------------------------------------------------------
def test_shy_town_marks_a_creature_of_each_opponent(cards, monkeypatch):
    s = table(cards, [FILLER, "Shy Town"])
    bear, angel = place(s, "Runeclaw Bear", "p2"), place(s, "Serra Angel", "p3")
    roll(s, monkeypatch, 1, picks=[bear.id, angel.id])
    for c in (bear, angel):
        assert s.state.cards[c.id].counters.get("shy") == 1 and "Coward" in plan(s).ch(s.state.cards[c.id]).subtypes
    roll(s, monkeypatch, 2, picks=[bear.id])  # (chaos: the same ability; Carol's creature is "up to one")
    assert s.state.cards[bear.id].counters.get("shy") == 2
    check(s)


# -- Jalira's Show: "When you do" — only after a destroy ----------------------------------------------------------------------------------
def test_jalira_s_show_the_destroyed_creature_s_controller_reveals_a_creature(cards, monkeypatch):
    s = table(cards, ["Jalira's Show", FILLER])
    lib = s.state.zones["p1:library"]
    early = [c for c in lib if s.state.cards[c].name in ("Runeclaw Bear", "Craw Wurm", "Serra Angel", "Kitesail Corsair")]
    act(s, "p1", type="move", card_ids=early, to={"player": "p1", "zone": "hand"})  # (the library's top: Opt, …, Indestructible Golem)
    bear = place(s, "Runeclaw Bear", "p1")
    assert [s.state.cards[c].name for c in lib[:5]] == ["Opt", "Careful Study", "Lightning Bolt", "Desert", "Indestructible Golem"]
    roll(s, monkeypatch, 2, picks=[bear.id])
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert len(on_battlefield(s, "Indestructible Golem", "p1")) == 1  # (the first creature card revealed)
    lib = s.state.zones["p1:library"]
    assert sorted(s.state.cards[c].name for c in lib[-4:]) == ["Careful Study", "Desert", "Lightning Bolt", "Opt"]
    check(s)


def test_jalira_s_show_nothing_destroyed_nothing_revealed(cards, monkeypatch):
    s = table(cards, ["Jalira's Show", FILLER])
    golem = place(s, "Indestructible Golem", "p1")
    library = list(s.state.zones["p1:library"])
    roll(s, monkeypatch, 2, picks=[golem.id])
    assert s.state.cards[golem.id].zone == "p1:battlefield" and s.state.zones["p1:library"] == library
    check(s)


# -- Pursued by Something: exiled, back under its owner's control ---------------------------------------------------------------------------
def test_pursued_by_something_returns_the_creature_card(cards, monkeypatch):
    s = table(cards, ["Pursued by Something", FILLER])
    bear = place(s, "Runeclaw Bear", "p2")
    before = plan(s).oid(bear.id)
    roll(s, monkeypatch, 2, picks=[bear.id])
    c = s.state.cards[bear.id]
    assert c.zone == "p2:battlefield" and c.controller == "p2" and plan(s).oid(c.id) != before
    check(s)


# -- The Bean: Reflection copies --------------------------------------------------------------------------------------------------------------
def test_the_bean_each_player_copies_a_creature_as_a_reflection(cards, monkeypatch):
    s = table(cards, [FILLER, "The Bean"])
    place(s, "Runeclaw Bear", "p1")
    angel = place(s, "Serra Angel", "p1")
    place(s, "Craw Wurm", "p2")
    roll(s, monkeypatch, 1, picks=[angel.id])
    assert [t.name for t in tokens(s, "p1")] == ["Serra Angel"] and [t.name for t in tokens(s, "p2")] == ["Craw Wurm"] and not tokens(s, "p3")
    for t in tokens(s, "p1") + tokens(s, "p2"):
        ch = plan(s).ch(t)
        assert "Reflection" in ch.subtypes and "shadow" in ch.keywords
    roll(s, monkeypatch, 2, picks=[angel.id])  # (chaos: one of yours, chosen)
    assert sorted(t.name for t in tokens(s, "p1")) == ["Serra Angel", "Serra Angel"]
    check(s)


# -- Tarnation: the criminal may draw ---------------------------------------------------------------------------------------------------------
def test_tarnation_a_crime_lets_its_committer_draw(cards, monkeypatch):
    s = table(cards, ["Tarnation", FILLER])
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    before = hand(s, "p1")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve(s, picks=["yes", "Yes", "draw a card", "Draw a card"])
    assert hand(s, "p1") == before  # (the Bolt left, a card was drawn)
    assert s.state.players["p2"].life == 37
    check(s)


# -- Welcome to Valley: a 1/1 copy ----------------------------------------------------------------------------------------------------------
def test_welcome_to_valley_copies_as_a_1_1(cards, monkeypatch):
    s = table(cards, ["Welcome to Valley", FILLER])
    wurm = place(s, "Craw Wurm", "p1")
    roll(s, monkeypatch, 2, picks=[wurm.id])
    [t] = tokens(s, "p1", "Craw Wurm")
    from app.rules import sba

    assert (sba.power(t, plan(s).ch(t)), sba.toughness(t, plan(s).ch(t))) == (1, 1)
    check(s)


# -- Sorin's Remastered Manor / Circus of the Sun: planeswalking here ------------------------------------------------------------------------
def test_sorin_s_manor_and_circus_of_the_sun_when_planeswalked_to(cards, monkeypatch):
    s = table(cards, [FILLER, "Sorin's Remastered Manor", "Circus of the Sun"])
    bear = place(s, "Runeclaw Bear", "p1")
    roll(s, monkeypatch, 1, picks=[bear.id])
    assert s.state.cards[bear.id].counters.get("spooky") == 1
    roll(s, monkeypatch, 1)
    performers = tokens(s, "p1", "Performer")
    assert len(performers) == 2 and all({"flying", "haste"} <= set(plan(s).ch(t).keywords) for t in performers)
    check(s)


# -- Black Lotus Lounge: each player draws for their artifact tokens; City Hall: tapped Treasures ---------------------------------------------
def test_city_hall_then_black_lotus_lounge(cards, monkeypatch):
    s = table(cards, ["City Hall", "Black Lotus Lounge", FILLER])
    roll(s, monkeypatch, 2, picks=["yes", "Yes"])  # (each player is asked; a "yes" for whoever is offered one)
    made = {p: tokens(s, p, "Treasure") for p in ("p1", "p2", "p3")}
    assert all(len(ts) == 2 and all(t.tapped for t in ts) for ts in made.values())
    roll(s, monkeypatch, 1)  # (to Black Lotus Lounge)
    hands = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    roll(s, monkeypatch, 2)
    assert {p: hand(s, p) - hands[p] for p in hands} == {"p1": 2, "p2": 2, "p3": 2}
    check(s)


# -- Game Knights Live (chaos): commanders can't be blocked and draw on damage --------------------------------------------------------------
def test_game_knights_live_chaos_grants_the_commander(cards, monkeypatch):
    s = table(cards, ["Game Knights Live", FILLER])
    krenko = commander(s, "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    roll(s, monkeypatch, 2)
    ch = plan(s).ch(s.state.cards[krenko.id])
    assert any("deals combat damage to a player" in a.text for a in ch.abilities)
    check(s)


# -- The Windy City: cast from exile for {2} ----------------------------------------------------------------------------------------------
def test_the_windy_city_exiles_a_flier_castable_for_two(cards, monkeypatch):
    s = table(cards, ["The Windy City", FILLER])
    angel = place(s, "Serra Angel", "p3")
    roll(s, monkeypatch, 2, picks=[angel.id])
    assert s.state.cards[angel.id].zone == "p3:exile"
    [perm] = [p for p in s.state.rules.permissions if p.card == angel.id]
    assert perm.player == "p3" and perm.alt_mana == "{2}" and perm.until == "permanent"
    check(s)


# -- Mojave Desert: a Desert entered: a Snake ------------------------------------------------------------------------------------------------
def test_mojave_desert_a_desert_brings_a_snake(cards, monkeypatch):
    s = table(cards, [FILLER, "Mojave Desert"], players=2)
    desert = next(c for c in s.state.cards.values() if c.name == "Desert" and c.owner == "p1")
    roll(s, monkeypatch, 1, picks=[desert.id])
    assert s.state.cards[desert.id].zone == "p1:battlefield" and s.state.cards[desert.id].tapped
    assert len(tokens(s, "p1", "Snake")) == 1 and not tokens(s, "p2", "Snake")
    check(s)


# -- Raiders' Allegiance -----------------------------------------------------------------------------------------------------------------------
def test_raiders_allegiance_raid_counts_players_dealt_combat_damage(cards):
    s = table(cards, ["Raiders' Allegiance", FILLER], players=2)
    bear = place(s, "Runeclaw Bear", "p1")
    to_turn(s, 3)
    until(s, lambda cur: cur.state.rules.decision is not None and cur.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda cur: cur.state.turn.phase == "main2")
    resolve(s)
    assert s.state.players["p1"].resources.get("point") == 1 and len(tokens(s, "p1", "Pirate")) == 1
    check(s)


def test_raiders_allegiance_the_most_points_and_proliferate(cards, monkeypatch):
    s = table(cards, ["Raiders' Allegiance", FILLER])
    for p, n in (("p1", 1), ("p2", 2), ("p3", 2)):
        act(s, p, type="set_resource", player=p, key="point", value=n)
    corsairs = [place(s, "Kitesail Corsair"), place(s, "Kitesail Corsair")]
    roll(s, monkeypatch, 2, picks=["p1", "p2", "p3"])  # (proliferate twice: each chooses every player with a counter)
    assert {p: s.state.players[p].resources.get("point") for p in ("p1", "p2", "p3")} == {"p1": 3, "p2": 4, "p3": 4}
    hands = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    roll(s, monkeypatch, 1)  # (planeswalk away: Bob and Carol are tied for the most)
    assert {p: len(tokens(s, p, "Treasure")) for p in hands} == {"p1": 0, "p2": 3, "p3": 3}
    assert {p: hand(s, p) - hands[p] for p in hands} == {"p1": 0, "p2": 3, "p3": 3}
    assert all(not s.state.players[p].resources.get("point") for p in hands)
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in corsairs)
    check(s)


# -- Bicycle Rack: +1/+1 for each card its controller discarded this turn ------------------------------------------------------------------
def test_bicycle_rack_chaos_counts_discards(cards, monkeypatch):
    s = table(cards, ["Bicycle Rack", FILLER])
    bear = place(s, "Runeclaw Bear", "p1")
    roll(s, monkeypatch, 2)
    from app.rules import sba

    assert sba.power(s.state.cards[bear.id], plan(s).ch(s.state.cards[bear.id])) == 2
    mana(s, U=1)
    study = to_hand(s, "Careful Study")
    act(s, "p1", type="cast_spell", card_id=study.id, targets=[])
    resolve(s)
    b = s.state.cards[bear.id]
    assert (sba.power(b, plan(s).ch(b)), sba.toughness(b, plan(s).ch(b))) == (4, 4)
    check(s)


# -- The Command Zone ---------------------------------------------------------------------------------------------------------------------
def test_the_command_zone_draws_and_commanders_and_tax(cards, monkeypatch):
    s = table(cards, [FILLER, "The Command Zone"])
    krenko = commander(s, "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    atraxa = commander(s, "p2")
    hands = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    roll(s, monkeypatch, 1, picks=[atraxa.id])  # (Bob puts Atraxa onto the battlefield; Carol declines)
    assert {p: hand(s, p) - hands[p] for p in hands} == {"p1": 1, "p2": 0, "p3": 0}
    assert s.state.cards[atraxa.id].zone == "p2:battlefield" and commander(s, "p3").zone == "p3:command"
    for p in ("p1", "p2"):
        act(s, p, type="commander_tax", commander=commander(s, p).commander_key, value=4)
    assert s.state.players["p1"].commander_tax[krenko.commander_key] == 4
    roll(s, monkeypatch, 2)
    assert all(v == 0 for p in ("p1", "p2") for v in [*s.state.players[p].commander_casts.values(), *s.state.players[p].commander_tax.values()])
    check(s)


# -- Ghirapur Grand Prix: the fastest players get Treasures --------------------------------------------------------------------------------
def test_ghirapur_grand_prix_the_highest_speed(cards, monkeypatch):
    s = table(cards, ["Ghirapur Grand Prix", FILLER])
    act(s, "p2", type="set_resource", player="p2", key="speed", value=2)
    act(s, "p3", type="set_resource", player="p3", key="speed", value=1)
    roll(s, monkeypatch, 1)
    assert {p: len(tokens(s, p, "Treasure")) for p in ("p1", "p2", "p3")} == {"p1": 0, "p2": 3, "p3": 0}
    check(s)
