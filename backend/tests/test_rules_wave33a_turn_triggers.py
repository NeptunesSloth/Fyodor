"""Wave 33A: triggered abilities an effect creates for the rest of the turn, researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave33a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.7, 603.7a, 603.7c: a resolving spell or ability creates a delayed triggered ability; one that names an object ("Whenever that creature
  deals combat damage to a player or planeswalker this turn", Hunter's Insight; "Whenever Lyra deals combat damage …", Lyra) is on that
  object only: it keeps working whatever the object becomes, but a new object is not it (400.7: Cloudshift returns a new creature).
* 611.2a, 514.2: "Until end of turn, whenever …" (Benefactor's Draught, Mountain Titan, Lyra) lasts to the cleanup step, no longer.
* 603.2c: a "whenever" trigger triggers each time its event happens (two combat damage steps, two blockers, two spells).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle as settle_stack
from tests.test_rules_conditionals import through_combat, until
from tests.wave9c_kit import build, card_named, cast, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave33a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w33a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Hunter's Insight", "Lyra, Tolarian Archangel", "Benefactor's Draught", "Mountain Titan", "Maeve, Insidious Singer",
        "Subira, Tulzidi Caravanner", "The Mirari Conjecture"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def watches(s):
    return [t for t in s.state.rules.delayed if t.when.get("kind") == "watch"]


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def attack(s, *attackers):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"} for a in attackers])


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_turn_trigger_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "Until end of turn, whenever target creature deals damage to one or more permanents, you gain that much life.",  # (that recipient class is unsupported)
    # ("… a creature an opponent controls is dealt damage, destroy it." is read since wave 110I: Green Dragon)
    "Whenever one or more creatures you control deal combat damage to a player this turn, draw that many cards.",  # (one trigger, many amounts)
    "Until end of turn, whenever a creature you control deals combat damage to a player, destroy it.",  # ("it" moved: no such object for this event)
])
def test_the_shapes_that_join_several_events_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Spell", "Sorcery", text)
    assert coverage.of_characteristics(chs).level != "FULL"


# -- a watch on one creature (Hunter's Insight) -----------------------------------------------------------------------
def test_hunters_insight_draws_for_each_combat_damage_step_of_that_creature_only(cards):
    """603.7: "draw that many cards" each time the chosen creature deals combat damage to a player this turn: a double striker
    deals it twice (510.2: first-strike and regular damage are two steps), 2 cards each; another creature's damage draws nothing."""
    s = build(cards, ["Hunter's Insight"], forests=20)
    striker = token(s, "p1", "Striker", "2/2", "Haste, Double strike")
    other = token(s, "p1", "Other", "3/3", "Haste")
    to_hand(s, "Hunter's Insight")
    mana(s, G=3)
    cast(s, "Hunter's Insight", targets=[striker.id], target_counts=[1])
    assert len(watches(s)) == 1 and watches(s)[0].once is False
    before = hand(s)
    attack(s, striker, other)
    through_combat(s)
    assert hand(s) == before + 4 and s.state.players["p2"].life == 40 - 4 - 3
    assert len(watches(s)) == 1  # ("whenever": it keeps watching to the end of the turn)
    check(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert watches(s) == []  # (514.2: gone the next turn)
    check(s)


def test_hunters_insight_does_not_follow_a_creature_that_was_blinked(cards):
    """400.7: Cloudshift returns Raging Goblin as a new object, which the watch (bound to the old one) isn't about: its combat damage
    draws nothing. Without the blink the same attack draws a card."""
    drawn = {}
    for blink in (False, True):
        s = build(cards, ["Hunter's Insight", "Cloudshift", "Raging Goblin"], forests=20)
        goblin = put(s, "Raging Goblin")
        to_hand(s, "Hunter's Insight")
        to_hand(s, "Cloudshift")
        mana(s, G=3, W=1)
        cast(s, "Hunter's Insight", targets=[goblin.id], target_counts=[1])
        if blink:
            cast(s, "Cloudshift", targets=[goblin.id], target_counts=[1])
            assert s.state.cards[goblin.id].zone.endswith(":battlefield")
        before = hand(s)
        attack(s, card_named(s, "Raging Goblin"))
        through_combat(s)
        assert s.state.players["p2"].life == 39  # (the Goblin hit either way)
        drawn[blink] = hand(s) - before
        assert len(watches(s)) == 1
        check(s)
    assert drawn == {False: 1, True: 0}


def test_a_pending_watch_survives_a_save_and_a_load(cards):
    """The delayed trigger, its bound object and its turn are in the saved game: reloaded before combat, it still draws."""
    s = build(cards, ["Hunter's Insight"], forests=20)
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    to_hand(s, "Hunter's Insight")
    mana(s, G=3)
    cast(s, "Hunter's Insight", targets=[bear.id], target_counts=[1])
    s = reloaded(s)
    assert len(watches(s)) == 1 and watches(s)[0].refs["watch"]["objects"]
    before = hand(s)
    attack(s, next(c for c in s.state.cards.values() if c.name == "Bear"))
    through_combat(s)
    assert hand(s) == before + 2
    check(s)


# -- "{cost}: Until end of turn, whenever Lyra deals combat damage to a player, draw two cards." (Lyra) -------------------------
def test_lyra_draws_two_only_when_lyra_deals_the_damage(cards):
    s = build(cards, ["Lyra, Tolarian Archangel"], forests=20)
    lyra = put(s, "Lyra, Tolarian Archangel")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (no longer summoning sick)
    token(s, "p1", "Other", "3/3", "Haste")
    mana(s, U=2, G=3)
    act(s, "p1", type="activate_ability", card_id=lyra.id, ability=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert len(watches(s)) == 1
    s = reloaded(s)  # (pending across a save and a load)
    assert len(watches(s)) == 1
    before = hand(s)
    attack(s, lyra, next(c for c in s.state.cards.values() if c.name == "Other"))
    through_combat(s)
    assert hand(s) == before + 2 and s.state.players["p2"].life == 40 - 3 - 3  # (Lyra's 3 drew two; the other 3/3 drew nothing)
    check(s)
    until(s, lambda s: s.state.turn.number == 4)
    assert watches(s) == []
    check(s)


# -- "Until end of turn, whenever a creature an opponent controls blocks, draw a card." (Benefactor's Draught) ------------------
def test_benefactors_draught_draws_for_each_blocking_creature(cards):
    s = build(cards, ["Benefactor's Draught"], forests=20)
    runner = token(s, "p1", "Runner", "2/2", "Haste")
    runner_b = token(s, "p1", "Runner B", "2/2", "Haste")
    wall_a = token(s, "p2", "Wall A", "0/4")
    wall_b = token(s, "p2", "Wall B", "0/4")
    to_hand(s, "Benefactor's Draught")
    mana(s, G=2)
    cast(s, "Benefactor's Draught")
    assert len(watches(s)) == 1
    before = hand(s)
    attack(s, runner, runner_b)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": wall_a.id, "attacker_id": runner.id},
                                                              {"blocker_id": wall_b.id, "attacker_id": runner_b.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    through_combat(s)
    assert hand(s) == before + 2  # (two blockers, two triggers)
    check(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert watches(s) == []
    check(s)


# -- "{1}{R}{R}: Until end of turn, whenever you cast a black spell, put a +1/+1 counter on this creature." (Mountain Titan) --------
def test_mountain_titan_grows_for_each_black_spell_this_turn_only(cards):
    s = build(cards, ["Mountain Titan", "Dark Ritual"], forests=20)
    titan = put(s, "Mountain Titan")
    to_hand(s, "Dark Ritual")
    mana(s, R=3, B=1)
    act(s, "p1", type="activate_ability", card_id=titan.id, ability=0)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert len(watches(s)) == 1
    s = reloaded(s)
    cast(s, "Dark Ritual")
    assert s.state.cards[titan.id].counters.get("+1/+1") == 1
    check(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert watches(s) == []
    to_hand(s, "Dark Ritual")
    mana(s, B=1)
    cast(s, "Dark Ritual")
    assert s.state.cards[titan.id].counters.get("+1/+1") == 1  # (no watch any more)
    check(s)


# -- "one or more …" is one trigger for the whole batch (603.2c): Aphelia, Forth Eorlingas! ---------------------------------------
def snakes(s, n, text="Haste"):
    for i in range(n):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Snake {i}", "type_line": "Token Creature — Snake", "power": "2",
                                                              "toughness": "2", "text": text})
    return [c for c in s.state.cards.values() if c.name.startswith("Snake ") and c.owner == "p1"]


def test_aphelia_halves_the_life_once_for_two_snakes_dealing_damage_together(cards):
    """Two Snakes deal combat damage to the same player at once: one event (603.2c), so one trigger: 40 - 4 = 36, then half of it,
    rounded up (18), is lost."""
    s = build(cards, ["Aphelia, Viper Whisperer"], forests=20)
    aphelia = put(s, "Aphelia, Viper Whisperer")
    pair = snakes(s, 2)
    mana(s, B=1, G=4)
    act(s, "p1", type="activate_ability", card_id=aphelia.id, ability=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert len(watches(s)) == 1
    s = reloaded(s)
    attack(s, *pair)
    through_combat(s)
    assert s.state.players["p2"].life == 18
    check(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert watches(s) == []
    check(s)


def test_aphelia_triggers_again_for_a_later_damage_step(cards):
    """A double-striking Snake deals combat damage twice (two events, two batches): 40 - 2 = 38, lose 19 → 19; 19 - 2 = 17, lose 9 → 8."""
    s = build(cards, ["Aphelia, Viper Whisperer"], forests=20)
    aphelia = put(s, "Aphelia, Viper Whisperer")
    (snake,) = snakes(s, 1, "Haste, Double strike")
    mana(s, B=1, G=4)
    act(s, "p1", type="activate_ability", card_id=aphelia.id, ability=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    attack(s, snake)
    through_combat(s)
    assert s.state.players["p2"].life == 8
    check(s)


def test_forth_eorlingas_makes_you_the_monarch_when_a_knight_connects(cards):
    s = build(cards, ["Forth Eorlingas!"], forests=20)
    to_hand(s, "Forth Eorlingas!")
    mana(s, R=1, W=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Forth Eorlingas!").id, x_value=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    knights = [c for c in s.state.cards.values() if c.name == "Human Knight" and c.owner == "p1"]
    assert len(knights) == 2 and s.state.table.monarch is None and len(watches(s)) == 1
    attack(s, *knights)
    through_combat(s)
    assert s.state.table.monarch == "p1" and s.state.players["p2"].life == 40 - 4
    check(s)


# -- "When this creature enters, until end of turn, whenever a nontoken creature you control dies, …" (Infested Thrinax) ----------
def test_infested_thrinax_makes_saprolings_equal_to_each_nontoken_creatures_power(cards):
    s = build(cards, ["Infested Thrinax", "Grizzly Bears", "Raging Goblin", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"], forests=20)
    bears, goblin = put(s, "Grizzly Bears"), put(s, "Raging Goblin")
    runt = token(s, "p1", "Runt", "1/1")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for b in bolts:
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
    to_hand(s, "Infested Thrinax")
    mana(s, B=1, G=4)
    cast(s, "Infested Thrinax")
    assert len(watches(s)) == 1

    def saprolings():
        return len([c for c in s.state.cards.values() if c.name == "Saproling" and c.owner == "p1"])

    for victim, bolt, count in ((bears, bolts[0], 2), (goblin, bolts[1], 3), (runt, bolts[2], 3)):  # (a token dying makes none: "nontoken")
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[victim.id], target_counts=[1])
        settle_stack(s)
        assert saprolings() == count
    check(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert watches(s) == []
    check(s)


# -- "Whenever Human Torch attacks, you may pay {R}{G}{W}{U}. If you do, until end of turn, whenever he deals combat damage to an opponent,
# he deals that much damage to each other opponent." (Human Torch: three players) -------------------------------------------------
def three_players(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Human Torch"), (30, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(30, "Mountain")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


@pytest.mark.parametrize("pay", [True, False])
def test_human_torch_passes_its_damage_to_the_other_opponents_only_when_paid(cards, pay):
    s = three_players(cards)
    torch = put(s, "Human Torch")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")  # (Alice's second turn of three players)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    mana(s, R=1, G=1, W=1, U=1)  # (the pool empties between steps: for the payment as the trigger resolves)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": torch.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        if d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            assert [o.id for o in d.options] == ["pay", "decline"]  # ("you may pay {R}{G}{W}{U}")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
    assert len(watches(s)) == int(pay)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 3
    assert s.state.players["p3"].life == (40 - 3 if pay else 40)
    check(s)


# -- "III — Until end of turn, whenever you cast an instant or sorcery spell, copy it. You may choose new targets for the copy." --------
def test_the_mirari_conjecture_chapter_three_copies_each_instant_or_sorcery_that_turn(cards):
    s = build(cards, ["The Mirari Conjecture", "Dark Ritual"], forests=30)
    to_hand(s, "The Mirari Conjecture")
    mana(s, U=1, G=4)
    cast(s, "The Mirari Conjecture")
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")  # (lore counter III on Alice's third turn)
    settle_stack(s)
    assert len(watches(s)) == 1
    s = reloaded(s)
    to_hand(s, "Dark Ritual")
    mana(s, B=1)
    cast(s, "Dark Ritual")
    assert mana_pool(s).get("B") == 6  # (the Ritual's BBB and its copy's)
    check(s)
    until(s, lambda s: s.state.turn.number == 7 and s.state.turn.phase == "main1")
    assert watches(s) == []
    check(s)


# -- "{1}{R}, {T}, Discard your hand: Until end of turn, whenever a creature you control with power 2 or less deals combat damage to a
# player, draw a card." (Subira) ---------------------------------------------------------------------------------------------
def test_subira_draws_for_creatures_with_power_two_or_less_only(cards):
    s = build(cards, ["Subira, Tulzidi Caravanner"], forests=20)
    subira = put(s, "Subira, Tulzidi Caravanner")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    small, big = token(s, "p1", "Small", "2/2", "Haste"), token(s, "p1", "Big", "3/3", "Haste")
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=subira.id, ability=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert hand(s) == 0 and len(watches(s)) == 1  # (the hand was the cost)
    attack(s, small, big)
    through_combat(s)
    assert hand(s) == 1 and s.state.players["p2"].life == 40 - 2 - 3
    check(s)


# -- "{2}{U}: Goad target creature. Whenever that creature attacks one of your opponents this turn, you draw a card." (Maeve) -------
def test_maeve_draws_when_the_goaded_creature_attacks_an_opponent(cards):
    """The pronoun "that creature" is the goad's target (603.7c): her other creature attacking draws nothing."""
    s = build(cards, ["Maeve, Insidious Singer"], forests=20)
    maeve = put(s, "Maeve, Insidious Singer")
    raider = token(s, "p1", "Raider", "2/2", "Haste")
    token(s, "p1", "Other", "2/2", "Haste")
    mana(s, U=3)
    act(s, "p1", type="activate_ability", card_id=maeve.id, ability=0, targets=[raider.id], target_counts=[1])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert len(watches(s)) == 1
    s = reloaded(s)
    before = hand(s)
    attack(s, *[next(c for c in s.state.cards.values() if c.name == n) for n in ("Raider", "Other")])
    through_combat(s)
    assert hand(s) == before + 1 and s.state.players["p2"].life == 40 - 4
    check(s)
