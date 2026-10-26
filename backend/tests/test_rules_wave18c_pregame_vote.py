"""Wave 18C: opening-hand actions (CR 103.6) and voting (CR 701.38).

Opening hand: after the mulligans every player, the starting player first and then in turn order, is asked which of the cards in
their hand to use: "begin the game with it on the battlefield" (the Leylines, Quicksilver, Gemstone Caverns for a player who is
not the starting player) or "reveal this card from your opening hand" (the Chancellors, Sphinx of Foresight), whose delayed
trigger is the revealer's (603.7a). A revealed card stays revealed until the first turn begins (103.6b).

Voting (701.38): "Starting with you, each player votes for X or Y." in turn order from the controller, public votes logged as made,
"gets more votes" / "or the vote is tied", "for each X vote", "the most votes or tied for most votes", extra votes ("While voting, you
may vote an additional time"), and the secret council vote of Vault 11 (revealed together; nothing visible to others before).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import COMMANDER_LONDON
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from app.game.visibility import SPECTATOR
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, engine_pays
from tests.test_rules_conditionals import build, to_hand
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18C-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Leyline of Sanctity", "{2}{W}{W}", 4, "Enchantment",
         "If this card is in your opening hand, you may begin the game with it on the battlefield.\nYou have hexproof. (You can't be the target of spells or abilities your opponents control.)", colors="W"),
    real("Chancellor of the Dross", "{4}{B}{B}{B}", 7, "Creature — Phyrexian Vampire",
         "You may reveal this card from your opening hand. If you do, at the beginning of the first upkeep, each opponent loses 3 life, then you gain life equal to the life lost this way.\nFlying, lifelink", ("6", "6"), "B"),
    real("Sphinx of Foresight", "{2}{U}{U}", 4, "Creature — Sphinx",
         "You may reveal this card from your opening hand. If you do, scry 3 at the beginning of your first upkeep.\nFlying\nAt the beginning of your upkeep, scry 1.", ("4", "4"), "U"),
    real("Gemstone Caverns", "", 0, "Legendary Land",
         "If this card is in your opening hand and you're not the starting player, you may begin the game with Gemstone Caverns on the battlefield with a luck counter on it. If you do, exile a card from your hand.\n{T}: Add {C}. If Gemstone Caverns has a luck counter on it, instead add one mana of any color."),
    real("Tyrant's Choice", "{1}{B}", 2, "Sorcery",
         "Will of the council — Starting with you, each player votes for death or torture. If death gets more votes, each opponent sacrifices a creature of their choice. If torture gets more votes or the vote is tied, each opponent loses 4 life.", colors="B"),
    real("Lieutenants of the Guard", "{4}{W}", 5, "Creature — Human Soldier",
         "Council's dilemma — When this creature enters, starting with you, each player votes for strength or numbers. Put a +1/+1 counter on this creature for each strength vote and create a 1/1 white Soldier creature token for each numbers vote.", ("2", "2"), "W"),
    real("Ballot Broker", "{2}{W}", 3, "Creature — Human Advisor",
         "While voting, you may vote an additional time. (The votes can be for different choices or for the same choice.)", ("2", "3"), "W"),
    real("Capital Punishment", "{4}{B}{B}", 6, "Sorcery",
         "Council's dilemma — Starting with you, each player votes for death or taxes. Each opponent sacrifices a creature of their choice for each death vote and discards a card for each taxes vote.", colors="B"),
    real("Tempt with Bunnies", "{2}{W}", 3, "Sorcery",
         "Tempting Offer — Draw a card and create a 1/1 white Rabbit creature token. Then each opponent may draw a card and create a 1/1 white Rabbit creature token. For each opponent who does, you draw a card and you create a 1/1 white Rabbit creature token.", colors="W"),
    real("Tempt with Glory", "{5}{W}", 6, "Sorcery",
         "Tempting offer — Put a +1/+1 counter on each creature you control. Each opponent may put a +1/+1 counter on each creature they control. For each opponent who does, put a +1/+1 counter on each creature you control.", colors="W"),
    real("Tempt with Discovery", "{3}{G}", 4, "Sorcery",
         "Tempting offer — Search your library for a land card and put it onto the battlefield. Each opponent may search their library for a land card and put it onto the battlefield. For each opponent who searches a library this way, search your library for a land card and put it onto the battlefield. Then each player who searched a library this way shuffles.", colors="G"),
    real("Tempt with Reflections", "{3}{U}", 4, "Sorcery",
         "Tempting offer — Choose target creature you control. Create a token that's a copy of that creature. Each opponent may create a token that's a copy of that creature. For each opponent who does, create a token that's a copy of that creature.", colors="U"),
    real("Virtus's Maneuver", "{2}{B}", 3, "Sorcery",
         "For each player, choose friend or foe. Each friend returns a creature card from their graveyard to their hand. Each foe sacrifices a creature of their choice.", colors="B"),
    real("Pir's Whim", "{3}{G}", 4, "Sorcery",
         "For each player, choose friend or foe. Each friend searches their library for a land card, puts it onto the battlefield tapped, then shuffles. Each foe sacrifices an artifact or enchantment of their choice.", colors="G"),
    real("Illusion of Choice", "{U}", 1, "Instant", "You choose how each player votes this turn.\nDraw a card.", colors="U"),
    real("Council's Judgment", "{1}{W}{W}", 3, "Sorcery",
         "Will of the council — Starting with you, each player votes for a nonland permanent you don't control. Exile each permanent with the most votes or tied for most votes.", colors="W"),
    real("Vault 11: Voter's Dilemma", "{2}{W}{B}", 4, "Enchantment — Saga",
         "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — For each opponent, you create a 1/1 white Human Soldier creature token.\nII, III — Each player secretly votes for up to one creature, then those votes are revealed. If no creature got votes, each player draws a card. Otherwise, destroy each creature with the most votes or tied for most votes.", colors="WB"),
    real("Serum Powder", "{3}", 3, "Artifact",
         "{T}: Add {C}.\nAny time you could mulligan and this card is in your hand, you may exile all the cards from your hand, then draw that many cards. (You can do this in addition to taking mulligans.)"),
    real("Chancellor of the Tangle", "{4}{G}{G}{G}", 7, "Creature — Phyrexian Beast",
         "You may reveal this card from your opening hand. If you do, at the beginning of your first main phase of the game, add {G}.\nReach, vigilance", ("6", "7"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, alice, bob, *, policy=COMMANDER_LONDON):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], settings=GameSettings(mulligan=policy), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    return GameSession(state, cards=cards)


def keep_all(s):
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_keep")


def zone_names(s, key):
    return sorted(s.state.cards[c].name for c in s.state.zones[key])


def answer(s, pid, names=()):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, d
    ids = [o.id for n in names for o in d.options if o.label == n]
    act(s, pid, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_leyline_and_chancellor_in_turn_order_with_private_hands(cards):
    s = table(cards, ["Leyline of Sanctity", "Chancellor of the Dross"], ["Gemstone Caverns", "Sphinx of Foresight"])
    keep_all(s)
    d = s.state.rules.decision
    assert d.player == "p1" and s.state.pregame.finished  # 103.6: the starting player first
    # nobody else learns anything from the pending decision (option labels, the prompt's wording, the hand)
    for viewer in ("p2", SPECTATOR):
        view = json.dumps(s.view(viewer))
        assert "Leyline of Sanctity" not in view and "Chancellor of the Dross" not in view
    with pytest.raises(ActionError) as err:  # the refusal an opponent gets says nothing about the hand either
        act(s, "p2", type="pass_priority")
    assert "Leyline" not in str(err.value) and "Chancellor" not in str(err.value)
    mine = s.view("p1")["rules"]["decision"]
    assert sorted(o["label"] for o in mine["options"]) == ["Chancellor of the Dross", "Leyline of Sanctity"]
    answer(s, "p1", ["Chancellor of the Dross", "Leyline of Sanctity"])
    assert zone_names(s, "p1:battlefield") == ["Leyline of Sanctity"]  # 103.6a
    d = s.state.rules.decision
    assert d.player == "p2"
    # Chancellor stays in hand, revealed until the opponents' decisions are done (103.6b); the Leyline is on the table
    seen = json.dumps(s.view("p2")["log"])
    assert "revealed" in seen and "Chancellor of the Dross" in seen
    p2_view_cards = {c["name"] for c in s.view("p2")["cards"].values() if c.get("name")}
    assert "Chancellor of the Dross" in p2_view_cards
    # Bob (not the starting player) begins with Gemstone Caverns, exiling a card from hand, and reveals Sphinx of Foresight
    answer(s, "p2", ["Gemstone Caverns", "Sphinx of Foresight"])
    d = s.state.rules.decision
    assert d.player == "p2" and d.prompt == "Exile a card from your hand"
    hand_before = len(s.state.zones["p2:hand"])
    pick = next(o for o in d.options if o.label == "Island")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick.id])
    assert len(s.state.zones["p2:hand"]) == hand_before - 1 and zone_names(s, "p2:exile") == ["Island"]
    assert s.state.cards[next(c for c in s.state.zones["p2:battlefield"])].counters == {"luck": 1}
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    assert s.state.rules.opening_revealed == []
    p2_after = {c["name"] for c in s.view("p1")["cards"].values() if c.get("name")}
    assert "Sphinx of Foresight" not in p2_after  # hidden again once the first turn begins
    # the first upkeep: Alice's Chancellor triggered for the whole table (Bob's Sphinx waits for Bob's own first upkeep)
    assert s.state.players["p1"].life == 43 and s.state.players["p2"].life == 37
    assert [t.name for t in s.state.rules.delayed] == ["Sphinx of Foresight"]
    roundtrip(s)


def test_nothing_to_use_still_asks_everyone(cards):
    s = table(cards, [], [])
    keep_all(s)
    assert s.state.rules.decision.player == "p1"
    assert s.view("p1")["rules"]["decision"]["options"] == []
    answer(s, "p1")
    assert s.state.rules.decision.player == "p2"
    answer(s, "p2")
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    roundtrip(s)


def test_serum_powder_exiles_the_hand_and_redraws_without_taking_a_mulligan(cards):
    s = table(cards, ["Serum Powder"], [])
    powder = next(c for c in s.state.zones["p1:hand"] if s.state.cards[c].name == "Serum Powder")
    assert s.view("p1")["pregame"]["mine"] == {"powder": [powder]}  # only its owner is told (103.5b)
    assert "mine" not in s.view("p2")["pregame"]
    forest = next(c for c in s.state.zones["p1:hand"] if s.state.cards[c].name == "Forest")
    with pytest.raises(ActionError):  # a client can't claim the ability for another card
        act(s, "p1", type="mulligan_powder", card_id=forest, verified=True)
    old_hand = list(s.state.zones["p1:hand"])
    act(s, "p1", type="mulligan_powder", card_id=powder)
    assert s.state.zones["p1:exile"] == old_hand and len(s.state.zones["p1:hand"]) == 7  # exiled (public), then drew that many
    assert s.state.pregame.seats["p1"].status == "deciding" and s.state.pregame.seats["p1"].mulligans == 0
    assert "Serum Powder" in json.dumps(s.view("p2")["log"])
    keep_all(s)
    replay_matches(s)


def test_gemstone_caverns_not_for_the_starting_player(cards):
    s = table(cards, ["Gemstone Caverns"], [])
    keep_all(s)
    assert s.view("p1")["rules"]["decision"]["options"] == []  # 103.6: only a player who is not the starting player


def test_gemstone_caverns_mana_is_any_color_with_a_luck_counter(cards):
    s = table(cards, [], ["Gemstone Caverns"])
    keep_all(s)
    answer(s, "p1")
    answer(s, "p2", ["Gemstone Caverns"])
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    from app.rules import casting
    from app.rules import mana as M

    caverns = next(iter(s.state.zones["p2:battlefield"]))
    ab = M.parse_mana_ability("{T}: Add {C}. If Gemstone Caverns has a luck counter on it, instead add one mana of any color.")
    assert ab is not None and ab.instead == tuple((c,) for c in "WUBRG")
    assert casting._resolve_options(s.state, s.state.cards[caverns], ab, s.cards) == ab.instead
    s.state.cards[caverns].counters.clear()
    assert casting._resolve_options(s.state, s.state.cards[caverns], ab, s.cards) == ab.options


def test_chancellor_of_the_tangle_adds_mana_in_their_first_main_phase(cards):
    s = table(cards, ["Chancellor of the Tangle"], [])
    keep_all(s)
    answer(s, "p1", ["Chancellor of the Tangle"])
    answer(s, "p2")
    for _ in range(3):
        if s.state.turn.phase != "main1":
            act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(3):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "main1" and visible_pool(s.state, "p1").get("G") == 1
    assert s.state.rules.delayed == []
    roundtrip(s)


# -- voting ------------------------------------------------------------------------------------------
def ballot(s, pid, label):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    pick = next(o for o in d.options if o.label == label)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[pick.id])


def cast(s, name, **m):
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def settle_stack(s):
    for _ in range(10):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_tyrants_choice_tie_goes_to_torture_and_votes_are_public(cards):
    s = build(cards, "Tyrant's Choice")
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.prompt == "Vote: death or torture"  # 701.38a: starting with the controller
    ballot(s, "p1", "death")
    assert "Alice voted for death" in json.dumps(s.view("p2")["log"])  # a public vote is seen by the next voter
    assert s.state.rules.decision.player == "p2"
    ballot(s, "p2", "torture")
    assert s.state.rules.decision is None and s.state.players["p2"].life == 36  # a tie: "torture … or the vote is tied"
    assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_tyrants_choice_death_wins_a_sacrifice(cards):
    s = build(cards, "Tyrant's Choice")
    from tests.test_rules_conditionals import creature

    bear = creature(s, "p2", "Bear")
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "death")
    ballot(s, "p2", "death")
    assert bear.id not in s.state.cards  # the token is sacrificed
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_lieutenants_counts_votes_and_ballot_broker_votes_twice(cards):
    s = build(cards, "Lieutenants of the Guard", "Ballot Broker")
    from tests.test_rules_conditionals import on_field

    on_field(s, "Ballot Broker")
    lt = cast(s, "Lieutenants of the Guard", W=1, C=4)
    settle_stack(s)
    for label in ("strength", "numbers"):  # Alice votes, then votes an additional time (701.38d: optional, Ballot Broker)
        ballot(s, "p1", label)
    d = s.state.rules.decision
    assert d.player == "p2"
    ballot(s, "p2", "numbers")
    settle_stack(s)
    assert s.state.cards[lt.id].counters.get("+1/+1") == 1  # one strength vote
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:battlefield"]).count("Soldier") == 2  # two numbers votes
    roundtrip(s)


def test_ballot_broker_extra_vote_may_be_declined(cards):
    s = build(cards, "Tyrant's Choice", "Ballot Broker")
    from tests.test_rules_conditionals import on_field

    on_field(s, "Ballot Broker")
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "death")
    ballot(s, "p1", "Don't vote again")
    assert s.state.rules.decision.player == "p2"


def test_councils_judgment_exiles_every_permanent_tied_for_most_votes(cards):
    s = build(cards, "Council's Judgment")
    from tests.test_rules_conditionals import creature

    bear, wolf, cub = creature(s, "p2", "Bear"), creature(s, "p2", "Wolf"), creature(s, "p2", "Cub")
    cast(s, "Council's Judgment", W=3)
    settle_stack(s)
    ballot(s, "p1", "Bear")
    ballot(s, "p2", "Wolf")
    settle_stack(s)
    assert bear.id not in s.state.cards and wolf.id not in s.state.cards  # tied for most votes: both are exiled (tokens cease to exist)
    assert s.state.cards[cub.id].zone == "p2:battlefield"
    roundtrip(s)


def test_secret_council_vote_is_hidden_until_revealed(cards):
    s = build(cards, "Vault 11: Voter's Dilemma")
    from tests.test_rules_conditionals import creature

    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p1", "Wolf")
    from tests.test_rules_sagas import main_phase

    cast(s, "Vault 11: Voter's Dilemma", W=1, B=1, C=2)
    settle_stack(s)  # chapter I: a Human Soldier for the one opponent
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:battlefield"]).count("Human Soldier") == 1
    main_phase(s, 3)  # Alice's next precombat main phase: a lore counter, chapter II
    settle_stack(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "secret" in d.prompt
    assert {o.label for o in d.options} == {"Bear", "Wolf", "Human Soldier"}
    ballot(s, "p1", "Bear")
    roundtrip(s)  # (a save and a load with Alice's secret ballot pending)
    # Bob decides without any sign of what Alice voted for; nobody else sees the pending ballot
    for viewer in ("p2", SPECTATOR):
        seen = json.dumps(s.view(viewer))
        assert "voted for" not in seen and "ballots" not in seen
    assert s.state.rules.decision.player == "p2"
    ballot(s, "p2", "Bear")
    settle_stack(s)
    log = json.dumps(s.view("p2")["log"])
    assert "The votes are revealed: Alice voted for Bear; Bob voted for Bear" in log
    assert bear.id not in s.state.cards  # destroyed (token)
    assert s.state.cards[wolf.id].zone == "p1:battlefield"
    roundtrip(s)


def test_capital_punishment_repeats_each_instruction_once_per_vote(cards):
    s = build(cards, "Capital Punishment")
    from tests.test_rules_conditionals import creature

    bear, wolf = creature(s, "p2", "Bear"), creature(s, "p2", "Wolf")
    act(s, "p2", type="draw", count=3)
    cast(s, "Capital Punishment", B=2, C=4)
    settle_stack(s)
    ballot(s, "p1", "death")
    ballot(s, "p2", "taxes")
    assert s.state.rules.decision.player == "p2"  # one death vote: Bob sacrifices one creature of his choice
    ballot(s, "p2", "Bear")
    d = s.state.rules.decision  # one taxes vote: Bob discards one card of his choice
    assert d.player == "p2" and d.max_choices == 1
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle_stack(s)
    assert bear.id not in s.state.cards and s.state.cards[wolf.id].zone == "p2:battlefield"
    assert len(s.state.zones["p2:hand"]) == 2 and len(s.state.zones["p2:graveyard"]) == 1
    roundtrip(s)




def answer_yes(s, pid, yes=True):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.kind == "confirm", d
    act(s, pid, type="choose", decision_id=d.id, option_ids=["yes" if yes else "no"])


def test_tempt_with_glory_gives_the_offer_to_each_opponent_who_takes_it(cards):
    s = build(cards, "Tempt with Glory")
    from tests.test_rules_conditionals import creature

    mine, theirs, theirs2 = creature(s, "p1", "Ox"), creature(s, "p2", "Bear"), creature(s, "p2", "Wolf")
    cast(s, "Tempt with Glory", W=1, C=5)
    settle_stack(s)
    assert s.state.cards[mine.id].counters == {"+1/+1": 1}  # the offer first (you do it)
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "confirm"
    answer_yes(s, "p2")
    settle_stack(s)
    assert s.state.cards[theirs.id].counters == {"+1/+1": 1} and s.state.cards[theirs2.id].counters == {"+1/+1": 1}
    assert s.state.cards[mine.id].counters == {"+1/+1": 2}  # once more for the opponent who did
    roundtrip(s)


def test_tempt_with_glory_declined(cards):
    s = build(cards, "Tempt with Glory")
    from tests.test_rules_conditionals import creature

    mine, theirs = creature(s, "p1", "Ox"), creature(s, "p2", "Bear")
    cast(s, "Tempt with Glory", W=1, C=5)
    settle_stack(s)
    answer_yes(s, "p2", yes=False)
    settle_stack(s)
    assert s.state.cards[mine.id].counters == {"+1/+1": 1} and not s.state.cards[theirs.id].counters
    roundtrip(s)


def test_tempt_with_bunnies_draws_and_makes_tokens_for_each_side(cards):
    s = build(cards, "Tempt with Bunnies")
    cast(s, "Tempt with Bunnies", W=1, C=2)
    settle_stack(s)
    answer_yes(s, "p2")
    settle_stack(s)
    rabbits = [c for c in s.state.cards.values() if c.name == "Rabbit"]
    assert sorted(c.controller for c in rabbits) == ["p1", "p1", "p2"]  # you, then once more for the opponent who did
    assert len(s.state.zones["p2:hand"]) == 1 and len(s.state.zones["p1:hand"]) == 2
    roundtrip(s)


def test_tempt_with_discovery_searches_privately_and_shuffles_only_the_searchers(cards):
    s = build(cards, "Tempt with Discovery")
    cast(s, "Tempt with Discovery", G=1, C=3)
    settle_stack(s)
    d = s.state.rules.decision  # Alice searches first (the offer)
    assert d.player == "p1" and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer_yes(s, "p2")
    d = s.state.rules.decision  # Bob's own search: only Bob is shown his library
    assert d.player == "p2" and d.kind == "choose_cards"
    assert "Forest" not in json.dumps(s.view("p1")["rules"]["decision"]) and "Island" not in json.dumps(s.view("p1")["rules"])
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision  # once more for the opponent who searched
    assert d.player == "p1" and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle_stack(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p2:battlefield"] == ["Island"]
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield") == ["Forest", "Forest"]
    roundtrip(s)


def test_tempt_with_reflections_copies_the_chosen_creature_for_the_opponent_too(cards):
    s = build(cards, "Tempt with Reflections")
    from tests.test_rules_conditionals import creature

    ox = creature(s, "p1", "Ox")
    c = to_hand(s, "Tempt with Reflections")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[ox.id])
    settle_stack(s)
    answer_yes(s, "p2")
    settle_stack(s)
    oxen = [x for x in s.state.cards.values() if x.name == "Ox" and x.zone.endswith(":battlefield")]
    assert sorted(x.controller for x in oxen) == ["p1", "p1", "p1", "p2"]  # Ox, your copy, the opponent's copy, your second copy
    roundtrip(s)


def side(s, who, label):
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.prompt == f"Is {who} a friend or a foe?", d
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[label])


def test_virtus_maneuver_friends_return_and_foes_sacrifice(cards):
    s = build(cards, "Virtus's Maneuver", "Elvish Visionary")
    from tests.test_rules_conditionals import creature

    dead = next(c for c in s.state.cards.values() if c.name == "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[dead.id], to={"player": "p1", "zone": "graveyard"})
    bear = creature(s, "p2", "Bear")
    cast(s, "Virtus's Maneuver", B=1, C=2)
    settle_stack(s)
    side(s, "Alice", "friend")  # the controller sorts everyone, herself included, in turn order
    assert "Alice is a friend" in json.dumps(s.view("p2")["log"])  # public
    side(s, "Bob", "foe")
    settle_stack(s)
    assert s.state.cards[dead.id].zone == "p1:hand" and bear.id not in s.state.cards
    roundtrip(s)


def test_pirs_whim_with_nobody_in_a_group_does_nothing_for_it(cards):
    s = build(cards, "Pir's Whim")
    cast(s, "Pir's Whim", G=1, C=3)
    settle_stack(s)
    side(s, "Alice", "friend")
    side(s, "Bob", "friend")  # no foes: "Each foe sacrifices …" has nobody to act
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_cards"  # Alice searches
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_cards"  # then Bob, for his own library
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle_stack(s)
    assert [c.tapped for c in s.state.cards.values() if c.zone in ("p1:battlefield", "p2:battlefield")] == [True, True]
    roundtrip(s)


def test_illusion_of_choice_makes_its_controller_cast_every_vote_this_turn(cards):
    s = build(cards, "Illusion of Choice", "Tyrant's Choice")
    cast(s, "Illusion of Choice", U=1)
    settle_stack(s)
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "death")
    d = s.state.rules.decision
    assert d.player == "p1" and d.prompt == "Vote for Bob: death or torture"  # Alice makes Bob's vote too
    ballot(s, "p1", "torture")
    assert s.state.rules.decision is None and s.state.players["p2"].life == 36
    assert "Bob voted for torture" in json.dumps(s.view("p1")["log"])
    roundtrip(s)


# -- review (system 18C) ---------------------------------------------------------------------------------
EXTRA += [
    real("Hardened Scales", "{G}", 1, "Enchantment",
         "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.",
         colors="G"),
]


def build3(cards, *names):
    """Alice (p1, active, in her main phase), Bob (p2) and Carol (p3)."""
    from tests.game_helpers import enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    players = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)]
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_a_voter_leaving_mid_vote_does_not_stop_the_count(cards):
    # 800.4a: the leaver's vote isn't made; the others still vote, and the result is counted
    s = build3(cards, "Tyrant's Choice")
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "torture")
    act(s, "p3", type="concede")  # Carol leaves while Bob is voting: she is skipped later
    ballot(s, "p2", "death")
    assert s.state.rules.decision is None and s.state.players["p2"].life == 36  # tied: torture
    roundtrip(s)
    s = build3(cards, "Tyrant's Choice")
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "torture")
    act(s, "p2", type="concede")  # Bob leaves while it is his vote: Carol still votes
    ballot(s, "p3", "death")
    assert s.state.rules.decision is None and s.state.players["p3"].life == 36
    roundtrip(s)


def test_illusion_of_choice_the_ballot_broker_player_decides_on_the_extra_vote(cards):
    # Illusion of Choice ruling: Bob (Ballot Broker) decides whether he takes the additional vote; Alice chooses what it is
    s = build(cards, "Illusion of Choice", "Tyrant's Choice", p2=["Ballot Broker"])
    broker = next(c for c in s.state.cards.values() if c.name == "Ballot Broker")
    act(s, "p2", type="move", card_ids=[broker.id], to={"player": "p2", "zone": "battlefield"})
    cast(s, "Illusion of Choice", U=1)
    settle_stack(s)
    cast(s, "Tyrant's Choice", B=2)
    settle_stack(s)
    ballot(s, "p1", "torture")  # Alice's own vote
    d = s.state.rules.decision
    assert d.player == "p1" and "Don't vote again" not in {o.label for o in d.options}  # Bob's normal vote: Alice picks it
    ballot(s, "p1", "death")
    answer_yes(s, "p2")  # Bob: an additional vote?
    d = s.state.rules.decision
    assert d.player == "p1" and "Don't vote again" not in {o.label for o in d.options}
    ballot(s, "p1", "death")  # Alice chooses it
    assert s.state.rules.decision is None and s.state.players["p2"].life == 40  # death 2, torture 1
    roundtrip(s)


def test_votes_for_counters_are_one_instruction_not_one_per_vote(cards):
    # "Put a +1/+1 counter on this creature for each strength vote": one event of N counters (Hardened Scales adds one, not N)
    s = build(cards, "Lieutenants of the Guard", "Hardened Scales")
    from tests.test_rules_conditionals import on_field

    on_field(s, "Hardened Scales")
    lt = cast(s, "Lieutenants of the Guard", W=1, C=4)
    settle_stack(s)
    ballot(s, "p1", "strength")
    ballot(s, "p2", "strength")
    settle_stack(s)
    assert s.state.cards[lt.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_tempting_offer_every_opponent_decides_before_anyone_acts(cards):
    # ruling: the opponents decide in turn order, then the effect happens for each who accepted
    s = build3(cards, "Tempt with Discovery")
    cast(s, "Tempt with Discovery", G=1, C=3)
    settle_stack(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer_yes(s, "p2")
    answer_yes(s, "p3")  # Carol decides before Bob searches
    for pid in ("p2", "p3", "p1", "p1"):
        d = s.state.rules.decision
        assert d.player == pid and d.kind == "choose_cards", d
        act(s, pid, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle_stack(s)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest"]) == 3
    roundtrip(s)


def table3(cards, alice, bob, carol):
    decks = [deck(cards, cmdr, [*((1, n) for n in names), (20, land)]) for cmdr, names, land in
             (("Krenko, Mob Boss", alice, "Forest"), ("Atraxa, Praetors' Voice", bob, "Island"), ("Krenko, Mob Boss", carol, "Mountain"))]
    state = new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
                     settings=GameSettings(mulligan=COMMANDER_LONDON), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    return GameSession(state, cards=cards)


def test_opening_hand_players_leaving_and_a_save_mid_step(cards):
    s = table3(cards, ["Leyline of Sanctity"], ["Chancellor of the Dross"], ["Leyline of Sanctity"])
    for p in ("p1", "p2", "p3"):
        act(s, p, type="mulligan_keep")
    answer(s, "p1", ["Leyline of Sanctity"])
    answer(s, "p2", ["Chancellor of the Dross"])  # Bob reveals; then Carol is asked
    assert s.state.rules.decision.player == "p3"
    roundtrip(s)  # a save and a load (and a replay) mid-step
    act(s, "p2", type="concede")  # Bob leaves before the game begins: his revealed card and delayed trigger go with him
    assert s.state.rules.decision.player == "p3"
    act(s, "p3", type="concede")  # Carol leaves while it is her decision: Alice is the last player standing
    assert s.state.rules.winner == "p1"
    roundtrip(s)
    s = table3(cards, [], ["Chancellor of the Dross"], [])
    for p in ("p1", "p2", "p3"):
        act(s, p, type="mulligan_keep")
    answer(s, "p1")
    act(s, "p2", type="concede")  # Bob leaves while it is his decision: Carol still decides, then the game begins
    answer(s, "p3")
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    assert s.state.rules.opening_revealed == [] and s.state.players["p1"].life == 40
    roundtrip(s)


def test_a_non_starting_players_chancellor_triggers_in_the_first_upkeep(cards):
    s = table3(cards, [], ["Chancellor of the Dross"], [])
    for p in ("p1", "p2", "p3"):
        act(s, p, type="mulligan_keep")
    answer(s, "p1")
    for viewer in ("p1", "p3", SPECTATOR):  # the pending decision says nothing about Bob's hand
        assert "Chancellor" not in json.dumps(s.view(viewer))
    answer(s, "p2", ["Chancellor of the Dross"])
    assert "Chancellor of the Dross" in {c.get("name") for c in s.view("p3")["cards"].values()}  # revealed (103.6b)
    answer(s, "p3")
    assert "Chancellor of the Dross" not in {c.get("name") for c in s.view("p3")["cards"].values()}
    assert "Chancellor of the Dross" not in {c.get("name") for c in s.view(SPECTATOR)["cards"].values()}
    # "the first upkeep" is Alice's (the starting player's): each of Bob's opponents loses 3, Bob gains 6
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [37, 46, 37]
    roundtrip(s)
