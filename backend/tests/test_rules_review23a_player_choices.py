"""Review of wave 23A (per-player iteration and player choices): 3–4 player probes of the cards the wave made FULL.

CR 2026-09-25: 608.2c / 608.2h (a "who …" group is read as the instruction is carried out), 701.9a/c (a discard replaced by exile is
still a discard), 701.21a, 701.55a-d (villainous choice: one player at a time, APNAP), 601.2c / 603.3d (a target group for each
opponent), 800.4a (a player who left is none of them). Real Oracle text; every scenario replays and survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, player_filter, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, pick, settle, to_hand, until, until_asked
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=(), keywords=(), loyalty=None):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    if loyalty is not None:
        extra["loyalty"] = str(loyalty)
    return card(name, set_code="tst", number=f"R23A-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=list(keywords), **extra)


EXTRA = [
    real("Kroxa, Titan of Death's Hunger", "{B}{R}", 2, "Legendary Creature — Elder Giant",
         "When Kroxa enters, sacrifice it unless it escaped.\nWhenever Kroxa enters or attacks, each opponent discards a card, then each opponent who didn't discard a nonland card this way loses 3 life.\nEscape—{B}{B}{R}{R}, Exile five other cards from your graveyard. (You may cast this card from your graveyard for its escape cost.)",
         ("6", "6"), "BR", ("Escape",)),
    real("Rest in Peace", "{1}{W}", 2, "Enchantment",
         "When Rest in Peace enters, exile all graveyards.\nIf a card or token would be put into a graveyard from anywhere, exile it instead.", colors="W"),
    real("Cruel Grimnarch", "{3}{B}", 4, "Creature — Phyrexian Cleric",
         "Deathtouch\nWhen this creature enters, each opponent discards a card. For each opponent who can't, you gain 4 life.", ("3", "3"), "B",
         ("Deathtouch",)),
    real("Liliana, Waker of the Dead", "{2}{B}{B}", 4, "Legendary Planeswalker — Liliana",
         "+1: Each player discards a card. Each opponent who can't loses 3 life.\n−3: Target creature gets -X/-X until end of turn, where X is the number of cards in your graveyard.\n−7: You get an emblem with \"At the beginning of combat on your turn, put target creature card from a graveyard onto the battlefield under your control. It gains haste.\"",
         colors="B", loyalty=4),
    real("Azula, Ruthless Firebender", "{2}{B}", 3, "Legendary Creature — Human Noble",
         "Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nWhenever Azula attacks, you may discard a card. Then you get an experience counter for each player who discarded a card this turn.\n{2}{B}: Until end of turn, Azula gets +1/+1 for each experience counter you have and gains menace.",
         ("3", "3"), "B", ("Firebending",)),
    real("Tectonic Hellion", "{3}{R}{R}", 5, "Creature — Hellion",
         "Haste\nWhenever this creature attacks, each player who controls the most lands sacrifices two lands of their choice.", ("4", "4"), "R",
         ("Haste",)),
    real("Snort", "{3}{R}", 4, "Sorcery",
         "Each player may discard their hand and draw five cards. Then Snort deals 5 damage to each opponent who discarded their hand this way.\nFlashback {5}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
         colors="R", keywords=("Flashback",)),
    real("The Dalek Emperor", "{5}{B}{R}", 7, "Legendary Artifact Creature — Dalek",
         "Affinity for Daleks (This spell costs {1} less to cast for each Dalek you control.)\nOther Daleks you control have haste.\nAt the beginning of combat on your turn, each opponent faces a villainous choice — That player sacrifices a creature of their choice, or you create a 3/3 black Dalek artifact creature token with menace.",
         ("6", "6"), "BR", ("Affinity",)),
    real("Frenzied Gorespawn", "{4}{R}", 5, "Creature — Horror",
         "When this creature enters, for each opponent, goad target creature that player controls. (Until your next turn, that creature attacks each combat if able and attacks a player other than you if able.)",
         ("5", "4"), "R"),
    real("Elminster's Simulacrum", "{4}{U}{U}", 6, "Instant",
         "For each opponent, you create a token that's a copy of up to one target creature that player controls.", colors="U"),
    real("Bonder's Ornament", "{3}", 3, "Artifact",
         "{T}: Add one mana of any color.\n{4}, {T}: Each player who controls a permanent named Bonder's Ornament draws a card."),
    real("Garruk, Veiled Butcher", "{3}{B}{B}", 5, "Legendary Planeswalker — Garruk",
         "If a creature an opponent controls would die, exile it instead.\n+2: Up to one target creature gets -4/-1 until your next turn.\n−2: Each player sacrifices a creature of their choice. If you sacrificed a creature this way, create a 4/4 green Beast creature token with trample.\n−3: Each opponent discards two cards. For each opponent who didn't discard two nonland cards this way, you draw a card.",
         colors="B", loyalty=5),
    real("Heidegger, Shinra Executive", "{3}{W}", 4, "Legendary Creature — Human Soldier",
         "At the beginning of combat on your turn, target creature you control gets +X/+0 until end of turn, where X is the number of Soldiers you control.\nAt the beginning of your end step, create a number of 1/1 white Soldier creature tokens equal to the number of opponents who control more creatures than you.",
         ("3", "3"), "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, mine=(), bob=(), carol=(), dave=None):
    """Alice (p1, in her main phase), Bob (p2), Carol (p3) and, given, Dave (p4)."""
    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (12, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (12, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (12, "Mountain")]))]
    if dave is not None:
        seats.append(PlayerSetup("Dave", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in dave), (12, "Island")])))
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def hand(s, pid):
    return zone(s.state, pid, "hand")


def deal(s, pid, name, n=1):
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def empty_hand(s, pid):
    for c in list(hand(s, pid)):
        act(s, pid, type="move", card_ids=[c], to={"zone": "library"})


def cast(s, name, pid="p1", **pool):
    c = to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id)
    return c


def attack(s, *cards, target="p2"):
    for c in cards:
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in cards])


# -- predicates: "you" inside the predicate is the ability's controller, never the player judged (608.2c) --

@pytest.mark.parametrize("text", ["controls your commander", "controls a creature you own", "controls a creature you control",
                                  "controls an artifact you own"])
def test_a_predicate_naming_you_is_not_read_as_that_player(text):
    assert player_filter.parse_pred(text) is None, text
    assert scripts.parse_effects(f"Each opponent who {text} loses 2 life.") is None


# -- "this way" discards (701.9a, 701.9c) --

def test_kroxa_a_discard_rest_in_peace_exiles_is_still_a_discard(cards):
    s = build(cards, mine=["Kroxa, Titan of Death's Hunger", "Rest in Peace"], bob=["Cruel Grimnarch"])
    on_field(s, "Rest in Peace")
    empty_hand(s, "p2")
    deal(s, "p2", "Cruel Grimnarch")  # a nonland card, exiled instead of put into the graveyard: still discarded
    empty_hand(s, "p3")
    deal(s, "p3", "Mountain")
    cast(s, "Kroxa, Titan of Death's Hunger", B=1, R=1)
    settle(s)
    assert life(s, "p2") == 40 and life(s, "p3") == 37
    grim = next(c for c in s.state.cards.values() if c.name == "Cruel Grimnarch")
    assert grim.zone == "p2:exile"
    roundtrip(s)


def test_cruel_grimnarch_a_player_who_left_is_not_an_opponent_who_cant(cards):
    s = build(cards, mine=["Cruel Grimnarch"], dave=[])
    empty_hand(s, "p2")  # Bob can't
    deal(s, "p3", "Mountain")  # Carol can
    empty_hand(s, "p4")
    act(s, "p4", type="concede")  # Dave leaves the game (800.4a)
    cast(s, "Cruel Grimnarch", B=1, C=3)
    settle(s)
    assert life(s, "p1") == 44  # only Bob
    roundtrip(s)


def test_liliana_each_player_discards_and_only_opponents_who_cant_lose_life(cards):
    s = build(cards, mine=["Liliana, Waker of the Dead"], dave=[])
    deal(s, "p3", "Mountain")  # (hands start empty: Bob and Dave can't discard, Carol can)
    walker = cast(s, "Liliana, Waker of the Dead", B=2, C=2)
    settle(s)
    empty_hand(s, "p1")  # Alice can't discard either: she isn't an opponent
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    settle(s)
    assert [life(s, p) for p in ("p1", "p2", "p3", "p4")] == [40, 37, 40, 37]
    roundtrip(s)


def test_garruk_counts_two_nonland_discards_per_opponent(cards):
    s = build(cards, mine=["Garruk, Veiled Butcher"], bob=["Cruel Grimnarch", "Snort"], carol=["Tectonic Hellion"])
    for p in ("p2", "p3"):
        empty_hand(s, p)
    deal(s, "p2", "Cruel Grimnarch")
    deal(s, "p2", "Snort")  # Bob discards two nonland cards
    deal(s, "p3", "Tectonic Hellion")
    deal(s, "p3", "Mountain")  # Carol discards one nonland card and a land
    walker = cast(s, "Garruk, Veiled Butcher", B=2, C=3)
    settle(s)
    before = len(hand(s, "p1"))
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=3)
    settle(s)
    assert len(hand(s, "p1")) == before + 1  # Carol only
    roundtrip(s)


# -- "each player who discarded a card this turn": counted for each player, whatever Alice chooses --

def test_azula_a_this_turn_count_after_her_own_discard_stays_manual(cards):
    # The turn's log takes in a discard only after the resolution (history.note_events): "you may discard a card. Then … for
    # each player who discarded a card this turn" would miss Azula's own discard (and declining skipped the count too).
    assert coverage.of_card_data(cards.resolve("Azula, Ruthless Firebender")).level != "FULL"
    assert scripts.parse_effects("Each opponent loses 1 life. Each opponent who lost life this turn discards a card.") is not None
    ch_text = "Whenever this creature attacks, each opponent loses 1 life. Then each opponent who lost life this turn discards a card."
    assert not _defined(ch_text)
    assert _defined("Whenever this creature attacks, each opponent who lost life this turn discards a card.")


def _defined(text):
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText

    ab = AbilityText(index=0, text=text, kind="triggered")
    return scripts.define(ab, Characteristics(name="X", abilities=(ab,), types=frozenset({"Creature"}))) is not None


# -- the most lands: every player tied for it (608.2c) --

def test_tectonic_hellion_ties_for_the_most_lands_all_sacrifice(cards):
    s = build(cards, mine=["Tectonic Hellion"], dave=[])
    hellion = on_field(s, "Tectonic Hellion")
    for pid, land, n in (("p1", "Forest", 2), ("p2", "Island", 3), ("p3", "Mountain", 3), ("p4", "Island", 1)):
        for c in [c for c in s.state.cards.values() if c.name == land and c.owner == pid and c.zone == f"{pid}:library"][:n]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    attack(s, hellion)
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None or s.state.turn.phase == "end", limit=60)
    lands = {p: sum(1 for c in zone(s.state, p, "battlefield") if s.state.cards[c].name in ("Forest", "Island", "Mountain"))
             for p in ("p1", "p2", "p3", "p4")}
    assert lands == {"p1": 2, "p2": 1, "p3": 1, "p4": 1}
    roundtrip(s)


# -- each player may discard their hand (Snort): the payers, then damage only to opponents who did --

def test_snort_alice_declines_bob_and_dave_discard_carol_declines(cards):
    s = build(cards, mine=["Snort"], dave=[])
    for p in ("p2", "p3", "p4"):
        empty_hand(s, p)
    deal(s, "p2", "Island", 2)
    deal(s, "p3", "Mountain", 3)
    before1 = len(hand(s, "p1")) - 1
    cast(s, "Snort", R=1, C=3)
    answers = {"p1": False, "p2": True, "p3": False, "p4": True}
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        asked.append(d.player)
        ids = [o.id for o in d.options]
        if d.player in answers and len(ids) >= 2 and d.kind != "choose_cards":
            yes = next((i for i in ids if i in ("yes", "pay", "accept")), ids[0])
            no = next((i for i in ids if i in ("no", "decline", "skip")), ids[-1])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[yes if answers[d.player] else no])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)])
    assert asked[:4] == ["p1", "p2", "p3", "p4"]  # APNAP, every choice before the discards
    assert len(hand(s, "p1")) == before1 and len(hand(s, "p2")) == 5 and len(hand(s, "p3")) == 3 and len(hand(s, "p4")) == 5
    assert [life(s, p) for p in ("p1", "p2", "p3", "p4")] == [40, 35, 40, 35]
    roundtrip(s)


# -- villainous choice (701.55d): APNAP, one at a time; a player who left is skipped --

def test_dalek_emperor_four_players_in_turn_order_and_a_player_who_left(cards):
    s = build(cards, mine=["The Dalek Emperor"], dave=[])
    on_field(s, "The Dalek Emperor")
    creature(s, "p2", "Bear")
    creature(s, "p4", "Wolf")
    act(s, "p3", type="concede")
    act(s, "p1", type="pass_priority")  # → beginning of combat
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    pick(s, "b")
    d = s.state.rules.decision
    assert d is not None and d.player == "p4"  # (Carol left: never asked)
    roundtrip(s)
    pick(s, "b")
    assert sum(1 for c in zone(s.state, "p1", "battlefield") if s.state.cards[c].name == "Dalek") == 2
    roundtrip(s)


# -- a group of targets for each opponent: a required one an opponent can't offer drops that opponent (603.3d) --

def test_frenzied_gorespawn_goads_one_creature_of_each_opponent(cards):
    s = build(cards, mine=["Frenzied Gorespawn"], dave=[])
    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p4", "Wolf")  # Carol controls no creature
    cast(s, "Frenzied Gorespawn", R=1, C=4)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {bear.id}
    roundtrip(s)
    pick(s, bear.id)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {wolf.id}
    pick(s, wolf.id)
    settle(s)
    from app.rules import keyword_actions as K
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    assert [K.goaded_by(plan.ch(s.state.cards[c.id])) for c in (bear, wolf)] == [{"p1"}, {"p1"}]
    roundtrip(s)


def test_elminsters_simulacrum_a_copy_for_each_opponents_creature(cards):
    s = build(cards, mine=["Elminster's Simulacrum"])
    creature(s, "p2", "Bear", "2/2")
    wolf = creature(s, "p3", "Wolf", "3/3")
    cast(s, "Elminster's Simulacrum", U=2, C=4)
    d = until_asked(s)
    assert d is not None
    pick(s)  # (none of Bob's)
    pick(s, wolf.id)
    settle(s)
    mine = sorted(s.state.cards[c].name for c in zone(s.state, "p1", "battlefield"))
    assert mine == ["Wolf"]
    roundtrip(s)


def test_bonders_ornament_each_player_who_controls_one_draws(cards):
    s = build(cards, mine=["Bonder's Ornament"], carol=["Bonder's Ornament"])
    mine = on_field(s, "Bonder's Ornament")
    on_field(s, "Bonder's Ornament", "p3")
    before = {p: len(hand(s, p)) for p in ("p1", "p2", "p3")}
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=1)
    settle(s)
    assert {p: len(hand(s, p)) - before[p] for p in before} == {"p1": 1, "p2": 0, "p3": 1}
    roundtrip(s)


def test_heidegger_counts_opponents_with_more_creatures(cards):
    s = build(cards, mine=["Heidegger, Shinra Executive"], dave=[])
    on_field(s, "Heidegger, Shinra Executive")
    for n in ("A", "B"):
        creature(s, "p2", n)
    creature(s, "p3", "C")
    for n in ("D", "E", "F"):
        creature(s, "p4", n)
    for pid in ("p1", "p2", "p3", "p4"):
        act(s, pid, type="set_stops", own=["end"], others=["end"])
    until(s, lambda s: s.state.turn.number == 1 and s.state.turn.phase == "end")
    settle(s)
    soldiers = [c for c in zone(s.state, "p1", "battlefield") if s.state.cards[c].name == "Soldier"]
    assert len(soldiers) == 2  # Bob (2 > 1) and Dave (3 > 1); Carol has as many
    roundtrip(s)
