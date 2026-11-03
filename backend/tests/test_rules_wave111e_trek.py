"""Wave 111E: Star Trek cards (trk, trc) of group E (this-turn state, X values, ability words, Sagas, look at the top). Real Oracle text
(Scryfall, 2026-10-30); every scenario checks the replay and a save and a load.

* The Star Trek creature types (Officer, Klingon, Borg, Tribble, …: app/rules/creature_types.py) make their tokens and selectors readable.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real("M'Ress, Crew Coordinator", "{4}{W}", 5, "Legendary Creature — Caitian Officer", "Landfall — Whenever a land you control enters, create two 1/1 red Officer creature tokens.", ("4", "4"), "W"),
    real("Shuttlecraft Galileo", "{3}{W}", 4, "Legendary Artifact — Spacecraft", "Landfall — Whenever a land you control enters, create a 1/1 red Officer creature token.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying\nWhenever Shuttlecraft Galileo attacks, up to seven target attacking creatures gain flying until end of turn.", ("3", "3"), "W"),
    real("Hoshi Sato, Exolinguist", "{4}{U}", 5, "Legendary Creature — Human Scientist", "Federation — When Hoshi Sato enters, look at the top X cards of your library, where X is the number of creature types among non-Borg creatures you control. Put one of them into your hand and the rest on the bottom of your library in a random order.", ("3", "3"), "U"),
    real("The Sword of Kahless", "{4}", 4, "Legendary Artifact — Equipment", "Equipped creature gets +2/+2 and has \"Whenever this creature attacks, look at the top five cards of your library. You may put a Klingon or Warrior creature card from among them onto the battlefield. Put the rest on the bottom of your library in a random order.\"\nEquip {2}", None, ""),
    real("Sins of the Father", "{3}{B}{R}", 5, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Each opponent sacrifices a nontoken creature of their choice.\nII — For each opponent, you create a 2/1 red Klingon Warrior creature token with haste.\nIII — Exile target player's graveyard. Each opponent loses life equal to the number of creature cards exiled this way.", None, "BR"),
    real("Rite of Ascension", "{2}{R}{W}", 4, "Enchantment", "Battlefront — Whenever you attack, for each opponent you attacked this turn, create a tapped and attacking 2/1 red Klingon Warrior creature token with haste.", None, "RW"),
    real("Deliver from Chaos", "{3}{W}{B}", 5, "Instant", "Exile target artifact or creature. Create X 1/1 colorless Borg artifact creature tokens, where X is that permanent's mana value.", None, "BW"),
    real("Excalbian Gamemaster", "{5}{W}", 6, "Creature — Excalbian", "Strange new worlds — When this creature enters, create X 1/1 red Officer creature tokens, where X is the number of differently named lands you control.\nWhenever this creature or another creature you control dies, put a +1/+1 counter on target creature you control.", ("6", "6"), "W"),
    real("Stratagem Emulator", "{2}{W}", 3, "Artifact Creature — Borg", "When this creature dies, create X 1/1 colorless Borg artifact creature tokens, where X is its power.", ("2", "1"), "W"),
    real("The Destruction of Praxis", "{3}{B}{B}", 5, "Sorcery", "Strange new worlds — All creatures get -X/-X until end of turn, where X is the number of differently named lands you control. If X is 6 or more, create two 2/1 red Klingon Warrior creature tokens with haste.", None, "B"),
    real("Tribble Cluster", "{2}{W}", 3, "Creature — Tribble", "At the beginning of combat on your turn, put a +1/+1 counter on this creature.\nWhen this creature dies, create X 1/1 white Tribble creature tokens with \"This token can't block,\" where X is this creature's power.", ("1", "1"), "W"),
    real("Ambassador K'Ehleyr", "{2}{W}", 3, "Legendary Creature — Klingon Human Advisor", "Vigilance\nParley — At the beginning of combat on your turn, each player reveals the top card of their library, then draws a card. For each nonland card revealed this way, put a +1/+1 counter on Ambassador K'Ehleyr.", ("2", "2"), "W"),
    real("Exploratory Mission", "{2}{R}{R}", 4, "Enchantment", "Landfall — Whenever a land you control enters, put a quest counter on this enchantment. Then exile cards from the top of your library until you exile a nonland card. You may play that card this turn. If this enchantment has five or more quest counters on it, add {R}{R}.", None, "R"),
    real("U.S.S. Farragut, Bold Explorer", "{6}", 6, "Legendary Artifact — Spacecraft", "Landfall — Whenever a land you control enters, you may put a creature card from your hand onto the battlefield. That creature gains haste. At the beginning of the next end step, put it on the bottom of your library. When you do, draw a card.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying", ("4", "4"), ""),
    real("The City on the Edge of Forever", "{3}{W}{B}", 5, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — All artifacts and creatures phase out. Create a 0/1 white Human creature token with \"Permanents can't phase in.\" (Treat phased-out permanents and anything attached to them as though they don't exist.)\nII — You draw two cards and each player loses 2 life.\nIII — Sacrifice a creature token. If you do, you gain 5 life.", None, "BW"),
    real("Those Old Scientists", "{2}{U}", 3, "Enchantment — Saga", "(As this Saga enters and after your draw\nstep, add a lore counter. Sacrifice after III.)\nI — Draw two cards, then discard two cards.\nII — Return up to one target artifact, instant, or sorcery card from your graveyard to your hand.\nIII — Choose up to two target cards in graveyards. The owners of those cards shuffle them into their libraries.", None, "U"),
    real("Unification", "{3}{W}{U}", 5, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — The owner of up to one target creature draws two cards, then shuffles that creature into their library.\nII — You may put a Spacecraft card from your hand or graveyard onto the battlefield.\nIII — You and target opponent each draw two cards.", None, "UW"),
    real("Captain Michael Burnham", "{2}{R}", 3, "Legendary Creature — Human Officer", "Trample\nLandfall — Whenever a land you control enters, Captain Burnham deals 1 damage to each opponent. If this is the second time this ability has resolved this turn, put a +1/+1 counter on Captain Burnham.", ("3", "3"), "R"),
    real("Miles O'Brien, Transporter Ops", "{2}{W}", 3, "Legendary Creature — Human Artificer", "When Miles O'Brien enters, return up to one other target creature or artifact you control to its owner's hand.\nAt the beginning of each end step, if a permanent was returned to your hand from the battlefield this turn, draw a card.", ("3", "3"), "W"),
    real("The Wrath of Khan", "{2}{R}", 3, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — This Saga deals 4 damage to target creature an opponent controls. At the beginning of the next combat this turn, gain control of that creature until end of turn. Untap it. It gains haste until end of turn.\nII — You may exile a card from your hand. If you do, draw a card.\nIII — Each opponent sacrifices a nontoken permanent of their choice.", None, "R"),
    real("La Forge, Thoughtful as Ever", "{3}{U}", 4, "Legendary Creature — Human Artificer", "{T}: For each permanent you control that you've put a counter on this turn, create a 1/1 blue Faerie creature token with flying.", ("2", "4"), "U"),
    real("Ezri Dax, Newly Joined", "{1}{W}", 2, "Legendary Creature — Trill Advisor", "Flash\nYou may have Ezri Dax enter as a copy of any creature card in your graveyard that was put there from the battlefield this turn, except her name is Ezri Dax, Newly Joined and she's a legendary Trill in addition to her other types.", ("2", "2"), "W"),
    real("T'Pring, Never Parted", "{3}{G}{U}", 5, "Legendary Creature — Vulcan Citizen", "Kal-if-fee — When T'Pring enters, choose another target creature you control and target creature an opponent controls. You may have the chosen creatures fight each other. Whenever a creature that fought this way dies this turn, you draw a card.", ("3", "3"), "GU"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Test Ramp 111E", "{G}", 1, "Instant", "You may put a land card from your hand onto the battlefield.", None, "G"),
    real("Test Warrior 111E", "{1}{R}", 2, "Creature — Human Warrior", "", ("2", "2"), "R"),
    real("Test Officer Pump 111E", "{R}", 1, "Instant", "Target creature gets +3/+0 until end of turn.", None, "R"),
    *(real(f"Test Land {c} 111E", "", 0, "Land", "{T}: Add {C}.") for c in "ABCDE"),
    real("Test Proliferate 111E", "{U}", 1, "Instant", "Proliferate.", None, "U"),
    real("Test Counter 111E", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
]


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


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def stats(s, c):
    """Current power and toughness of ``c`` (layers applied, counters counted)."""
    card = s.state.cards[c.id]
    return sba.power(card, ch(s, c)), sba.toughness(card, ch(s, c))


def mine(s, name, pid="p1"):
    """The battlefield objects named ``name`` that ``pid`` controls."""
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


def play_land(s, name="Forest", pid="p1"):
    c = to_hand(s, name, pid)
    act(s, pid, type="play_land", card_id=c.id)
    answer(s)
    return c


def library(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:library", []))


# -- landfall: Officer tokens --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name, n", [("M'Ress, Crew Coordinator", 2), ("Shuttlecraft Galileo", 1)])
def test_landfall_creates_red_officer_tokens(cards, name, n):
    s = build(cards, [name])
    put(s, name)
    play_land(s)
    officers = mine(s, "Officer")
    assert len(officers) == n
    for o in officers:
        c = ch(s, o)
        assert c.colors == {"R"} and "Officer" in c.subtypes and c.is_creature and stats(s, o) == (1, 1)
    check(s)


def build3(cards, p1=(), p2=(), p3=()):
    """Alice, Bob and Carol (rules on), in Alice's first main phase."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = (("Alice", "Krenko, Mob Boss", p1), ("Bob", "Atraxa, Praetors' Voice", p2), ("Carol", "Krenko, Mob Boss", p3))
    s = GameSession(enable(new_game([PlayerSetup(n, cards=deck(cards, c, [*((1, x) for x in names), (9, "Forest")])) for n, c, names in seats],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def chapter(s, saga, n, *picks):
    """Chapter ``n`` of ``saga``: n - 1 lore counters set up by hand, then a real proliferate adds the n-th (714.2b: the chapter
    ability triggers); resolve everything (``picks`` answer the chapter's decisions)."""
    if n > 1:
        act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=n - 1 - s.state.cards[saga.id].counters.get("lore", 0))
    mana(s, U=1)
    cast(s, "Test Proliferate 111E")
    answer(s, [saga.id], *picks)
    assert s.state.cards[saga.id].counters.get("lore", 0) == n or s.state.cards[saga.id].zone != "p1:battlefield"


# -- look at the top: Hoshi Sato (X = creature types among non-Borg creatures you control) --------------------------------------------
@pytest.mark.parametrize("bears, x", [(False, 2), (True, 3)])
def test_hoshi_sato_looks_at_one_card_per_creature_type_of_non_borg_creatures(cards, bears, x):
    s = build(cards, ["Hoshi Sato, Exolinguist", "Stratagem Emulator", "Grizzly Bears"])
    put(s, "Stratagem Emulator")  # (a Borg: its type isn't counted)
    if bears:
        put(s, "Grizzly Bears")
    hoshi = to_hand(s, "Hoshi Sato, Exolinguist")
    lib = library(s)
    hand = set(s.state.zones["p1:hand"])
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=hoshi.id)
    answer(s)
    got = set(s.state.zones["p1:hand"]) - hand
    assert len(got) == 1 and got <= set(lib[:x])  # (Human, Scientist; and Bear)
    after = library(s)
    assert after[0] == lib[x] and set(after[-(x - 1):]) == set(lib[:x]) - got
    check(s)


# -- Sins of the Father II: for each opponent, a Klingon Warrior ---------------------------------------------------------------------------
def test_sins_of_the_father_chapter_two_one_klingon_warrior_per_opponent(cards):
    s = build3(cards, ["Sins of the Father", "Test Proliferate 111E"])
    saga = put(s, "Sins of the Father")
    chapter(s, saga, 2)
    tokens = mine(s, "Klingon Warrior")
    assert len(tokens) == 2
    for t in tokens:
        c = ch(s, t)
        assert {"Klingon", "Warrior"} <= c.subtypes and c.colors == {"R"} and stats(s, t) == (2, 1) and "haste" in c.keywords
    check(s)


# -- Deliver from Chaos: X = the exiled permanent's mana value ------------------------------------------------------------------------------
@pytest.mark.parametrize("victim, x", [("Grizzly Bears", 2), ("Stratagem Emulator", 3)])
def test_deliver_from_chaos_makes_one_borg_per_mana_value(cards, victim, x):
    s = build(cards, ["Deliver from Chaos"], [victim])
    target = put(s, victim, "p2")
    mana(s, W=1, B=1, C=3)
    cast(s, "Deliver from Chaos", [target.id])
    answer(s)
    assert s.state.cards[target.id].zone == "p2:exile"
    borg = mine(s, "Borg")
    assert len(borg) == x
    c = ch(s, borg[0])
    assert c.types == {"Artifact", "Creature"} and "Borg" in c.subtypes and not c.colors and stats(s, borg[0]) == (1, 1)
    check(s)


# -- Strange new worlds: X = differently named lands you control -------------------------------------------------------------------------
def test_excalbian_gamemaster_officers_per_differently_named_land_then_counters_on_deaths(cards):
    s = build(cards, ["Excalbian Gamemaster", "Test Land A 111E", "Test Land B 111E", "Lightning Bolt"], forests=3)
    for name in ("Forest", "Forest", "Test Land A 111E", "Test Land B 111E"):
        put(s, name)  # (Forest, Forest: one name; three in all)
    mana(s, W=1, C=5)
    gm = cast(s, "Excalbian Gamemaster")
    answer(s)
    officers = mine(s, "Officer")
    assert len(officers) == 3
    mana(s, R=1)
    cast(s, "Lightning Bolt", [officers[0].id])
    answer(s, None, [gm.id])  # (another creature you control died: a +1/+1 counter on the Gamemaster)
    assert s.state.cards[gm.id].counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("names, tokens", [(5, False), (6, True)])
def test_destruction_of_praxis_minus_x_and_warriors_at_six_names(cards, names, tokens):
    lands = [f"Test Land {c} 111E" for c in "ABCDE"]
    s = build(cards, ["The Destruction of Praxis", *lands], ["Grizzly Bears", "Excalbian Gamemaster"], forests=3)
    for name in ["Forest", *lands][:names]:
        put(s, name)
    gm, bears = put(s, "Excalbian Gamemaster", "p2"), put(s, "Grizzly Bears", "p2")
    mana(s, B=2, C=3)
    cast(s, "The Destruction of Praxis")
    answer(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert (s.state.cards[gm.id].zone == "p2:graveyard") is (names == 6)  # (6/6 gets -6/-6; -5/-5 leaves it 1/1)
    warriors = mine(s, "Klingon Warrior")
    assert len(warriors) == (2 if tokens else 0)
    for w in warriors:  # (created after the -X/-X: not affected by it, 611.2c)
        assert stats(s, w) == (2, 1) and "haste" in ch(s, w).keywords
    check(s)


# -- dies: X = its power (last known information, 608.2h) ------------------------------------------------------------------------------------
@pytest.mark.parametrize("pumped", [False, True])
def test_stratagem_emulator_dies_into_borg_by_its_last_power(cards, pumped):
    s = build(cards, ["Stratagem Emulator", "Test Officer Pump 111E", "Lightning Bolt"])
    em = put(s, "Stratagem Emulator")
    if pumped:
        mana(s, R=1)
        cast(s, "Test Officer Pump 111E", [em.id])
        answer(s)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [em.id])
    answer(s)
    assert s.state.cards[em.id].zone == "p1:graveyard"
    borg = mine(s, "Borg")
    assert len(borg) == (5 if pumped else 2)
    assert ch(s, borg[0]).types == {"Artifact", "Creature"}
    check(s)


def on_top(s, *cs, pid="p1"):
    """``cs`` on top of the library, the first one topmost."""
    for c in reversed(cs):
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")


# -- attack triggers ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("take", ["Ambassador K'Ehleyr", "Test Warrior 111E", None])
def test_sword_of_kahless_attack_puts_a_klingon_or_warrior_from_the_top_five(cards, take):
    from tests.test_rules_conditionals import combat_step, creature, on_field, sandbox

    s = sandbox(cards, "The Sword of Kahless", "Ambassador K'Ehleyr", "Test Warrior 111E", "Grizzly Bears", "Lightning Bolt")
    sword = on_field(s, "The Sword of Kahless")
    host = creature(s, "p1", "Host", "2/2")
    act(s, "p1", type="attach", card_ids=[sword.id], to=host.id)
    named = [card_named(s, n) for n in ("Grizzly Bears", "Ambassador K'Ehleyr", "Lightning Bolt", "Test Warrior 111E", "Forest")]
    on_top(s, *named)
    combat_step(s)
    assert stats(s, host) == (4, 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": host.id, "target": "p2"}])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and any(o.card_id == named[1].id for o in d.options):
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(
            s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    offered = {o.card_id for o in d.options if o.card_id}
    assert offered == {named[1].id, named[3].id}  # (a Klingon, a Warrior: not the Bear, the Bolt or the Forest)
    pick = [o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == take]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    answer(s)
    got = [c for c in named if s.state.cards[c.id].zone == "p1:battlefield"]
    assert [c.name for c in got] == ([take] if take else [])
    assert set(library(s)[-(5 - len(got)):]) == {c.id for c in named} - {c.id for c in got}  # (the rest on the bottom)
    check(s)


@pytest.mark.parametrize("targets", [("p2",), ("p2", "p3")])
def test_rite_of_ascension_one_attacking_warrior_per_opponent_attacked(cards, targets):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck
    from tests.test_rules_conditionals import combat_step, creature, on_field

    seats = (("Alice", "Krenko, Mob Boss", ["Rite of Ascension"]), ("Bob", "Atraxa, Praetors' Voice", []), ("Carol", "Krenko, Mob Boss", []))
    s = GameSession(new_game([PlayerSetup(n, cards=deck(cards, c, [*((1, x) for x in names), (9, "Forest")])) for n, c, names in seats],
                             shuffle=False), cards=cards)
    on_field(s, "Rite of Ascension")
    bears = [creature(s, "p1", f"Bear {i}", "2/2") for i in range(2)]
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": b.id, "target": targets[i % len(targets)]} for i, b in enumerate(bears)])
    asked = []
    for _ in range(20):  # (each token's controller chooses whom it attacks, 508.4; here each opponent attacked, in turn)
        d = s.state.rules.decision
        if d is not None:
            asked.append({o.id for o in d.options})
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[targets[(len(asked) - 1) % len(targets)]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert asked == [{"p2", "p3"}] * len(targets)  # (802.2: every opponent is a defending player)
    warriors = mine(s, "Klingon Warrior")
    assert len(warriors) == len(targets) and s.state.turn.phase == "main2"  # (combat over: no blockers)
    for w in warriors:
        assert s.state.cards[w.id].tapped and "haste" in ch(s, w).keywords and stats(s, w) == (2, 1)
    assert (life(s, "p2"), life(s, "p3")) == ((34, 40) if len(targets) == 1 else (36, 36))  # (each Warrior dealt its 2 too)
    check(s)


def test_tribble_cluster_dies_into_tribbles_that_cant_block(cards):
    s = build(cards, ["Tribble Cluster", "Lightning Bolt"])
    tc = put(s, "Tribble Cluster")
    act(s, "p1", type="counter", card_ids=[tc.id], kind="+1/+1", delta=2)  # (a 3/3)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [tc.id])
    answer(s)
    tribbles = mine(s, "Tribble")
    assert len(tribbles) == 3
    c = ch(s, tribbles[0])
    assert c.colors == {"W"} and "Tribble" in c.subtypes and stats(s, tribbles[0]) == (1, 1)
    check(s)


def to_phase(s, phase, turn=1):
    """Play on to ``phase`` of turn ``turn`` (every player stops there), its triggers resolved."""
    from tests.test_rules_conditionals import until

    for pid in s.state.players:
        act(s, pid, type="set_stops", own=[phase], others=[phase], smart_pass=False)
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == phase and not s.state.zones.get("stack")
          and s.state.rules.decision is None)


def hand(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:hand", []))


# -- Parley, the draws first: Ambassador K'Ehleyr ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tops, n", [(("Lightning Bolt", "Forest", "Lightning Bolt"), 2), (("Forest", "Forest", "Forest"), 0)])
def test_ambassador_kehleyr_parley_counts_the_revealed_nonlands_after_everyone_draws(cards, tops, n):
    s = build3(cards, ["Ambassador K'Ehleyr", "Lightning Bolt"], ["Grizzly Bears"], ["Lightning Bolt"])
    amb = put(s, "Ambassador K'Ehleyr")
    shown = []
    for pid, name in zip(("p1", "p2", "p3"), tops, strict=True):
        top = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
        on_top(s, top, pid=pid)
        shown.append(top)
    act(s, "p1", type="pass_priority")  # (→ beginning of combat: the trigger)
    answer(s)
    assert all(c.id in hand(s, c.owner) for c in shown)  # (each player drew the card they revealed)
    assert s.state.cards[amb.id].counters.get("+1/+1", 0) == n
    check(s)


# -- Exploratory Mission -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("quests", [0, 4])
def test_exploratory_mission_exiles_to_a_nonland_card_you_may_play_and_mana_at_five_quests(cards, quests):
    from tests.game_helpers import mana_pool

    s = build(cards, ["Exploratory Mission", "Lightning Bolt"])
    mission = put(s, "Exploratory Mission")
    if quests:
        act(s, "p1", type="counter", card_ids=[mission.id], kind="quest", delta=quests)
    land = to_hand(s, "Forest")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:2]
    bolt = card_named(s, "Lightning Bolt")
    on_top(s, *forests, bolt)
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s)
    assert s.state.cards[mission.id].counters["quest"] == quests + 1
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in (*forests, bolt))  # (exiled down to the first nonland card)
    assert mana_pool(s).get("R", 0) == (2 if quests == 4 else 0)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # (played from exile this turn)
    answer(s)
    assert life(s, "p2") == 37
    check(s)


# -- U.S.S. Farragut: the creature goes to the bottom at the next end step; when it does, a card -------------------------------------------
@pytest.mark.parametrize("killed", [False, True])
def test_uss_farragut_puts_a_creature_in_with_haste_then_bottom_and_draw(cards, killed):
    s = build(cards, ["U.S.S. Farragut, Bold Explorer", "Grizzly Bears", "Lightning Bolt"])
    put(s, "U.S.S. Farragut, Bold Explorer")
    bears = to_hand(s, "Grizzly Bears")
    c = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=c.id)
    answer(s, [bears.id])  # ("you may": the Bears)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and "haste" in ch(s, bears).keywords
    if killed:
        mana(s, R=1)
        cast(s, "Lightning Bolt", [bears.id])
        answer(s)
    cards_in_hand = len(hand(s))
    to_phase(s, "end")
    answer(s)
    if killed:  # (a new object in the graveyard: not "it", 400.7; nothing went to the library, no card)
        assert s.state.cards[bears.id].zone == "p1:graveyard" and len(hand(s)) == cards_in_hand
    else:
        assert library(s)[-1] == bears.id and len(hand(s)) == cards_in_hand + 1
    check(s)


def test_uss_farragut_may_put_nothing(cards):
    s = build(cards, ["U.S.S. Farragut, Bold Explorer", "Grizzly Bears"])
    put(s, "U.S.S. Farragut, Bold Explorer")
    bears = to_hand(s, "Grizzly Bears")
    c = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=c.id)
    answer(s, [])  # (no card: "you may", 603.5)
    assert s.state.cards[bears.id].zone == "p1:hand"
    cards_in_hand = len(hand(s))
    to_phase(s, "end")
    answer(s)
    assert len(hand(s)) == cards_in_hand
    check(s)


# -- The City on the Edge of Forever I ---------------------------------------------------------------------------------------------------
def test_city_on_the_edge_of_forever_phases_out_artifacts_and_creatures_and_they_stay_out(cards):
    s = build(cards, ["The City on the Edge of Forever", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears", "Sol Ring"])
    gone = [put(s, "Grizzly Bears"), put(s, "Sol Ring"), put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")]
    forest = put(s, "Forest")
    mana(s, W=1, B=1, C=3)
    cast(s, "The City on the Edge of Forever")
    answer(s)
    assert all(s.state.cards[c.id].zone.endswith(":phased") for c in gone)
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    human = mine(s, "Human")
    assert len(human) == 1 and stats(s, human[0]) == (0, 1)
    to_phase(s, "main1", turn=2)  # (Bob's untap step: his permanents can't phase in)
    assert all(s.state.cards[c.id].zone.endswith(":phased") for c in gone)
    check(s)


# -- Those Old Scientists III, Unification I ----------------------------------------------------------------------------------------------
def test_those_old_scientists_three_shuffles_two_graveyard_cards_into_their_owners_libraries(cards):
    s = build(cards, ["Those Old Scientists", "Test Proliferate 111E", "Lightning Bolt"], ["Grizzly Bears"])
    saga = put(s, "Those Old Scientists")
    bolt, bears = card_named(s, "Lightning Bolt"), card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})
    chapter(s, saga, 3, [bolt.id, bears.id])
    assert s.state.cards[bolt.id].zone == "p1:library" and s.state.cards[bears.id].zone == "p2:library"
    assert s.state.cards[saga.id].zone == "p1:graveyard"  # (sacrificed after III, 714.4)
    check(s)


@pytest.mark.parametrize("chosen", [True, False])
def test_unification_one_the_owner_draws_two_then_shuffles_the_creature_away(cards, chosen):
    s = build(cards, ["Unification"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, W=1, U=1, C=3)
    theirs, mine_ = len(hand(s, "p2")), len(hand(s))
    cast(s, "Unification")
    answer(s, [bears.id] if chosen else [])
    assert s.state.cards[bears.id].zone == ("p2:library" if chosen else "p2:battlefield")
    assert len(hand(s, "p2")) == theirs + (2 if chosen else 0) and len(hand(s)) == mine_  # (Alice, who cast it, drew none)
    check(s)


# -- Captain Michael Burnham: the second resolution this turn ----------------------------------------------------------------------------
def test_captain_burnham_pings_each_opponent_and_grows_on_the_second_resolution(cards):
    s = build3(cards, ["Captain Michael Burnham", "Test Ramp 111E"])
    burnham = put(s, "Captain Michael Burnham")
    play_land(s)
    assert (life(s, "p2"), life(s, "p3")) == (39, 39) and not s.state.cards[burnham.id].counters.get("+1/+1")
    to_hand(s, "Forest")
    mana(s, G=1)
    cast(s, "Test Ramp 111E")
    answer(s)
    assert (life(s, "p2"), life(s, "p3")) == (38, 38) and s.state.cards[burnham.id].counters.get("+1/+1") == 1
    check(s)


# -- Miles O'Brien: a permanent returned to your hand this turn ---------------------------------------------------------------------------
@pytest.mark.parametrize("bounce", [True, False])
def test_miles_obrien_draws_at_the_end_step_after_a_bounce(cards, bounce):
    s = build(cards, ["Miles O'Brien, Transporter Ops", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    mana(s, W=1, C=2)
    cast(s, "Miles O'Brien, Transporter Ops")
    answer(s, [bears.id] if bounce else [])
    assert s.state.cards[bears.id].zone == ("p1:hand" if bounce else "p1:battlefield")
    n = len(hand(s))
    to_phase(s, "end")
    answer(s)
    assert len(hand(s)) == n + (1 if bounce else 0)
    check(s)


# -- The Wrath of Khan I -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("victim", ["Excalbian Gamemaster", "Grizzly Bears"])
def test_wrath_of_khan_one_damages_then_steals_the_creature_at_the_next_combat(cards, victim):
    s = build(cards, ["The Wrath of Khan"], [victim])
    target = put(s, victim, "p2")
    act(s, "p2", type="tap", card_ids=[target.id])
    mana(s, R=1, C=2)
    cast(s, "The Wrath of Khan", [target.id])
    answer(s, [target.id])
    survived = victim == "Excalbian Gamemaster"
    assert s.state.cards[target.id].zone == ("p2:battlefield" if survived else "p2:graveyard")
    if survived:
        assert s.state.cards[target.id].controller == "p2" and s.state.cards[target.id].damage == 4
    to_phase(s, "begin_combat")  # (the delayed trigger, resolved)
    if survived:
        card = s.state.cards[target.id]
        assert card.controller == "p1" and not card.tapped and "haste" in ch(s, target).keywords
        to_phase(s, "main1", turn=2)
        assert s.state.cards[target.id].controller == "p2"  # (until end of turn)
    check(s)


# -- La Forge: permanents you control that you've put a counter on this turn ----------------------------------------------------------------
def test_la_forge_one_faerie_per_permanent_you_control_you_put_a_counter_on(cards):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import creature, on_field, sandbox

    s = sandbox(cards, "La Forge, Thoughtful as Ever", "Shuttlecraft Galileo", "Test Counter 111E", p2=("Test Counter 111E",))
    laforge, galileo = on_field(s, "La Forge, Thoughtful as Ever"), on_field(s, "Shuttlecraft Galileo")
    x, v, w = creature(s, "p1", "X", "2/2"), creature(s, "p1", "V", "2/2"), creature(s, "p1", "W", "3/3")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # (→ Alice's main phase)
    mana(s, G=1)
    cast(s, "Test Counter 111E", [x.id])  # (Alice: a +1/+1 counter on X)
    answer(s)
    station = next(a.index for a in ch(s, galileo).abilities if a.text.startswith("Tap another"))
    act(s, "p1", type="activate_ability", card_id=galileo.id, ability=station)
    answer(s, [w.id])  # (W tapped: three charge counters on the Spacecraft, a permanent that isn't a creature)
    assert s.state.cards[galileo.id].counters.get("charge") == 3
    act(s, "p2", type="set_stops", own=[], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")  # (Bob gets priority in Alice's main phase: his counter on V is not one Alice put)
    assert s.state.rules.priority == "p2"
    mana(s, "p2", G=1)
    cast(s, "Test Counter 111E", [v.id], pid="p2")
    answer(s)
    assert s.state.cards[v.id].counters.get("+1/+1") == 1 and s.state.turn.phase == "main1"
    act(s, "p1", type="activate_ability", card_id=laforge.id, ability=0)
    answer(s)
    faeries = mine(s, "Faerie")
    assert len(faeries) == 2  # (X and the Shuttlecraft: not V, W or La Forge)
    assert ch(s, faeries[0]).colors == {"U"} and "flying" in ch(s, faeries[0]).keywords
    check(s)


# -- Ezri Dax: a copy of a creature card put into your graveyard from the battlefield this turn ---------------------------------------------
@pytest.mark.parametrize("how", ["died", "milled", "none"])
def test_ezri_dax_enters_as_a_legendary_trill_copy_of_a_creature_that_died_this_turn(cards, how):
    s = build(cards, ["Ezri Dax, Newly Joined", "Grizzly Bears", "Lightning Bolt", "Murder"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, B=2, C=1)
    cast(s, "Murder", [theirs.id])  # (Bob's Bears died this turn too: not in Alice's graveyard)
    answer(s)
    if how == "died":
        put(s, "Grizzly Bears")
        mana(s, R=1)
        cast(s, "Lightning Bolt", [bears.id])
        answer(s)
    elif how == "milled":  # (put into the graveyard from the library: not "from the battlefield")
        act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    assert s.state.cards[bears.id].zone == ("p1:library" if how == "none" else "p1:graveyard")
    ezri = to_hand(s, "Ezri Dax, Newly Joined")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=ezri.id)
    answer(s, [bears.id])
    c = ch(s, ezri)
    assert c.name == "Ezri Dax, Newly Joined" and c.supertypes == {"Legendary"}
    if how == "died":  # (707.9b: the Bears' copiable values, legendary and a Trill too)
        assert c.subtypes == {"Bear", "Trill"} and c.mana_cost == "{1}{G}" and stats(s, ezri) == (2, 2)
    else:
        assert c.subtypes == {"Trill", "Advisor"} and c.mana_cost == "{1}{W}"
    check(s)


# -- T'Pring: the chosen creatures may fight; each that fought draws a card when it dies this turn ------------------------------------------
def tpring(s, mine_, theirs, fight=True, before=None):
    """Cast T'Pring; her trigger targets ``mine_`` and ``theirs``; ``before`` runs while it waits on the stack; "you may" answered ``fight``."""
    mana(s, G=1, U=1, C=3)
    cast(s, "T'Pring, Never Parted")
    picked = set()
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and {mine_.id, theirs.id} & {o.id for o in d.options}:
            ids = [c.id for c in (mine_, theirs) if c.id in {o.id for o in d.options}]
            act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
            picked |= set(ids)
            if picked == {mine_.id, theirs.id}:
                break  # (the trigger is on the stack with its targets; Alice has priority)
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    assert picked == {mine_.id, theirs.id}
    if before is not None:
        before()
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            yes = [o.id for o in d.options if o.id in ("yes", "no")]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if fight else "no"] if yes else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("fight", [True, False])
def test_tpring_both_fighters_dying_draw_two(cards, fight):
    s = build(cards, ["T'Pring, Never Parted", "Grizzly Bears"], ["Grizzly Bears"])
    mine_, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    n = drew(s)
    tpring(s, mine_, theirs, fight)
    dead = s.state.cards[mine_.id].zone == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:graveyard"
    assert dead is fight and drew(s) == n + (2 if fight else 0)  # (two died at once: it triggers for each)
    check(s)


def drew(s, pid="p1"):
    return s.state.rules.turn_log.drew.get(pid, 0)


def test_tpring_a_fighter_dying_later_this_turn_draws_too(cards):
    s = build(cards, ["T'Pring, Never Parted", "Excalbian Gamemaster", "Murder"], ["Grizzly Bears"])
    mine_, theirs = put(s, "Excalbian Gamemaster"), put(s, "Grizzly Bears", "p2")
    n = drew(s)
    tpring(s, mine_, theirs)
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine_.id].damage == 2 and drew(s) == n + 1
    mana(s, B=2, C=1)
    cast(s, "Murder", [mine_.id])
    answer(s)  # (its own dies trigger puts a counter on T'Pring; the delayed one draws)
    assert s.state.cards[mine_.id].zone == "p1:graveyard" and drew(s) == n + 2
    check(s)


def test_tpring_no_fight_when_a_target_is_gone_and_nothing_is_watched(cards):
    s = build(cards, ["T'Pring, Never Parted", "Excalbian Gamemaster", "Lightning Bolt", "Murder"], ["Grizzly Bears"])
    mine_, theirs = put(s, "Excalbian Gamemaster"), put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_stops", own=["main1"], others=[], smart_pass=False)  # (Alice answers the trigger on the stack)

    def bolt():
        assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
        mana(s, R=1)
        cast(s, "Lightning Bolt", [theirs.id])
        act(s, "p1", type="pass_priority")

    n = drew(s)
    tpring(s, mine_, theirs, before=bolt)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine_.id].damage == 0  # (701.14b: neither fought)
    mana(s, B=2, C=1)
    cast(s, "Murder", [mine_.id])
    answer(s)
    assert s.state.cards[mine_.id].zone == "p1:graveyard" and drew(s) == n  # (it didn't fight this way: no card)
    check(s)
