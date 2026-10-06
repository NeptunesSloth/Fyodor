"""Review of wave 27B (attack-trigger defenders, "you and that player each", value lists in selectors). Real Oracle text;
scenarios check the replay and a save and a load.

* 508.3e: "Whenever you attack a player, tap target creature that player controls" — the player attacked, once for each.
* 121.2c: "you and the attacking player each draw a card and lose 1 life" — one draw instruction for both (APNAP).
* 202.3e / Unsealing rulings: X on the stack counts toward mana value; counters it will enter with don't count toward power.
* Every selector consumer either honours "in:<stat>:<values>" or refuses the wording.
"""

from __future__ import annotations

import re

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import card_named, check, life, mana

KARAZIKAR = ("Whenever you attack a player, tap target creature that player controls and goad it. (Until your next turn, that creature "
             "attacks each combat if able and attacks a player other than you if able.)\nWhenever an opponent attacks another one of "
             "your opponents, you and the attacking player each draw a card and lose 1 life.")
CARDS = [
    ("Karazikar, the Eye Tyrant", "{3}{B}{R}", "Legendary Creature — Beholder", "5", "5", KARAZIKAR),
    ("Kozilek's Unsealing", "{1}{U}", "Enchantment", None, None,
     "Devoid (This card has no color.)\nWhenever you cast a creature spell with mana value 4, 5, or 6, create two 0/1 colorless Eldrazi "
     "Spawn creature tokens with \"Sacrifice this token: Add {C}.\"\nWhenever you cast a creature spell with mana value 7 or greater, "
     "draw three cards."),
    ("Sarkhan's Unsealing", "{3}{R}", "Enchantment", None, None,
     "Whenever you cast a creature spell with power 4, 5, or 6, this enchantment deals 4 damage to any target.\nWhenever you cast a "
     "creature spell with power 7 or greater, this enchantment deals 4 damage to each opponent and each creature and planeswalker "
     "they control."),
    ("Jolene, the Plunder Queen", "{2}{R}", "Legendary Creature — Human Warlock", "2", "2",
     "Whenever a player attacks one or more of your opponents, that attacking player creates a Treasure token.\nIf you would create one or "
     "more Treasure tokens, instead create those tokens plus an additional Treasure token.\nSacrifice five Treasures: Put five +1/+1 "
     "counters on Jolene."),
    ("Review Imp", "{1}", "Creature — Imp", "1", "1", ""),
    ("Review Pair", "{1}", "Creature — Imp", "2", "2", ""),
    ("Review Hydra", "{X}{G}", "Creature — Hydra", "0", "0", "This creature enters with X +1/+1 counters on it."),
    ("Review Wall", "{1}", "Enchantment", None, None, "Creatures with power 2 or 3 can't block."),
]
def _mv(cost):  # 202.3: generic numbers plus one for each other symbol (X is 0 off the stack)
    syms = re.findall(r"\{([^}]+)\}", cost)
    return float(sum(int(x) if x.isdigit() else 0 if x == "X" else 1 for x in syms))


EXTRA = [card(n, set_code="r27b", number=f"R{i:02d}", mana_cost=mc, cmc=_mv(mc),
              type_line=tl, colors=["R"], color_identity=["R"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]
EXTRA.append(card("Review Twin // Review Twin Giant", set_code="r27b", number="R90", layout="modal_dfc", mana_cost="{1}{G}", cmc=2.0,
                  type_line="Creature — Elf // Creature — Giant", colors=["G"], color_identity=["G"],
                  card_faces=[{"object": "card_face", "name": "Review Twin", "mana_cost": "{1}{G}", "type_line": "Creature — Elf",
                               "oracle_text": "", "power": "1", "toughness": "1"},
                              {"object": "card_face", "name": "Review Twin Giant", "mana_cost": "{3}{G}", "type_line": "Creature — Giant",
                               "oracle_text": "", "power": "4", "toughness": "4"}]))


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


MINE = ["Review Twin // Review Twin Giant", "Test Walker Card", "Jolene, the Plunder Queen", "Karazikar, the Eye Tyrant", "Kozilek's Unsealing", "Sarkhan's Unsealing", "Review Hydra", "Review Wall", "Review Pair"]


def table(cards, players=3):
    lands = ("Forest", "Island", "Mountain", "Forest")
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in MINE), (3, "Review Imp"), (10, lands[i])]) for i in range(players)]
    names = ("Alice", "Bob", "Carol", "Dave")
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(names[:players], decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield"))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    s.state.rules.controlled_since[c.id].turn = 0
    return c


def settle(s, choose=None):
    """Resolve the stack up to the next combat declaration."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            picked = (choose(d) if choose else None) or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=picked)
        elif not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def to_declare(s):
    act(s, "p1", type="pass_priority")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no declare attackers")


def test_karazikar_targets_a_creature_the_attacked_player_controls(cards):
    s = table(cards)
    put(s, "Karazikar, the Eye Tyrant", "p1")
    mine, bobs, carols = put(s, "Review Imp", "p1"), put(s, "Review Imp", "p2"), put(s, "Review Imp", "p3")
    to_declare(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    seen = []

    def choose(d):
        ids = {o.id for o in d.options}
        if mine.id in ids or bobs.id in ids or carols.id in ids:
            seen.append(ids)
        return None

    settle(s, choose)
    assert seen and all(bobs.id in ids and mine.id not in ids and carols.id not in ids for ids in seen), seen
    assert s.state.cards[bobs.id].tapped and not s.state.cards[carols.id].tapped
    check(s)


def test_karazikar_triggers_once_for_each_player_attacked_directly(cards):
    s = table(cards, players=4)
    put(s, "Karazikar, the Eye Tyrant", "p1")
    a, b, c = put(s, "Review Imp", "p1"), put(s, "Review Imp", "p1"), put(s, "Review Imp", "p1")
    bobs, carols, daves = put(s, "Review Imp", "p2"), put(s, "Review Imp", "p3"), put(s, "Review Imp", "p4")
    walker = put(s, "Test Walker Card", "p4")
    act(s, "p4", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    assert s.state.cards[walker.id].zone == "p4:battlefield"
    to_declare(s)  # Bob and Carol directly, Dave only through his planeswalker: two triggers (508.3e)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}, {"card_id": b.id, "target": "p3"},
                                                      {"card_id": c.id, "target": walker.id}])
    creatures = {bobs.id, carols.id, daves.id, a.id, b.id, c.id}
    seen = []

    def choose(d):
        if {o.id for o in d.options} & creatures:
            seen.append(sorted({o.id for o in d.options} & creatures))
        return None

    settle(s, choose)
    assert sorted(seen) == sorted([[bobs.id], [carols.id]]), seen
    assert s.state.cards[bobs.id].tapped and s.state.cards[carols.id].tapped and not s.state.cards[daves.id].tapped
    check(s)


def _treasures(s, pid):
    return len([c for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.controller == pid and c.zone.endswith(":battlefield")])


def test_jolene_ignores_an_attack_on_a_planeswalker_only(cards):
    s = table(cards)
    put(s, "Jolene, the Plunder Queen", "p3")
    a = put(s, "Review Imp", "p1")
    walker = put(s, "Test Walker Card", "p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    assert s.state.cards[walker.id].zone == "p2:battlefield"
    to_declare(s)  # Alice attacks only Bob's planeswalker: not "attacks one or more of your opponents" (508.3e)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": walker.id}])
    settle(s)
    assert _treasures(s, "p1") == 0
    check(s)


def test_jolene_controller_attacking_gets_the_extra_treasure(cards):
    s = table(cards)
    put(s, "Jolene, the Plunder Queen", "p1")
    a, b = put(s, "Review Imp", "p1"), put(s, "Review Imp", "p1")
    to_declare(s)  # two opponents in one declaration: one trigger; Jolene's controller creates it, plus one more (614.1a)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}, {"card_id": b.id, "target": "p3"}])
    settle(s)
    assert _treasures(s, "p1") == 2
    check(s)


def test_karazikar_draw_is_one_instruction_for_both_players():
    data = next(c for c in EXTRA if c["name"].startswith("Karazikar"))
    d = scripts.definitions(printed_from_data({**data, "faces": []}, 0))
    effects = next(a["effects"] for a in d.values() if a.get("cond", {}).get("defender") == "other_opponent")
    assert effects[0] == {"do": "draw", "who": "event_player", "also": "you", "n": 1}  # 121.2c: the active (attacking) player first
    assert {e["who"] for e in effects[1:]} == {"you", "event_player"} and all(e["do"] == "lose_life" for e in effects[1:])


def probe(text, type_line="Enchantment"):
    n = f"Review Probe {abs(hash(text))}"  # (a name, id and Oracle id of its own: definitions and coverage are cached)
    return {"name": n, "oracle_id": n, "id": n, "type_line": type_line, "mana_cost": "{2}", "cmc": 2.0, "colors": [], "color_identity": [],
            "keywords": [], "faces": [], "oracle_text": text, **({"power": "1", "toughness": "1"} if "Creature" in type_line else {})}


@pytest.mark.parametrize("text", [
    "Whenever ~ deals combat damage to a player, you and that player each draw that many cards.",  # Xyris, Diviner Spirit
    "Whenever ~ deals combat damage to an opponent, you and that player each draw two cards.",  # Black Widow
])
def test_you_and_that_player_each_draw_stays_one_instruction(text):
    effects = next(iter(scripts.definitions(printed_from_data(probe(text, "Creature — Bird"), 0)).values()))["effects"]
    assert len(effects) == 1 and effects[0]["also"] == "you" and effects[0]["who"] == "event_player"  # 121.2c


def test_the_attacking_player_is_read_only_on_an_attack_event():
    # "Whenever you're dealt combat damage, the attacking player …": the event's player is the one dealt damage, not the attacker
    assert coverage.of_card_data(probe("Whenever you're dealt combat damage, the attacking player draws a card.", "Artifact")).level != "FULL"


@pytest.mark.parametrize("text", [
    "Whenever a creature you control attacks one or more of your opponents, draw a card.",  # (a creature's attack: not read)
    "Whenever a creature attacks another one of your opponents, draw a card.",
    "Whenever a creature you control attacks one or more of your opponents and isn't blocked, draw a card.",
    "Whenever you attack another one of your opponents, draw a card.",  # ("another": than whom?)
    "Whenever a player attacks another one of your opponents, draw a card.",
    "Whenever a player attacks one or more of your opponents with two or more creatures, draw a card.",  # (a count for the declaration)
    "Whenever two or more creatures attack one or more of your opponents, draw a card.",
])
def test_defender_kinds_only_on_a_players_attack(text):
    assert coverage.of_card_data(probe(text)).level != "FULL", text


def test_that_player_on_your_own_attack_is_the_player_attacked():
    # (Archnemesis) the event's player is you, the attacker: "that player" isn't it
    text = "Enchant opponent\nWhenever you attack enchanted player, that player loses 2 life, you draw a card, and you gain 2 life."
    assert coverage.of_card_data(probe(text, "Enchantment — Aura Curse")).level != "FULL"


def test_karazikar_attack_between_opponents(cards):
    s = table(cards)
    put(s, "Karazikar, the Eye Tyrant", "p3")
    a = put(s, "Review Imp", "p1")  # Alice (Carol's opponent) attacks Bob (another of Carol's opponents)
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    to_declare(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    settle(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (39, 39, 39)  # (Bob: the Imp's 1 combat damage, unblocked)
    assert [len(s.state.zones[f"{p}:hand"]) - hand[p] for p in ("p1", "p2", "p3")] == [1, 0, 1]
    check(s)


def test_karazikar_attack_on_two_other_opponents_triggers_for_each(cards):
    # 508.3e: "Whenever [a player] attacks [another player]" — once for each other opponent attacked (no ruling says otherwise)
    s = table(cards, players=4)
    put(s, "Karazikar, the Eye Tyrant", "p3")
    a, b = put(s, "Review Imp", "p1"), put(s, "Review Imp", "p1")
    to_declare(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}, {"card_id": b.id, "target": "p4"}])
    settle(s)
    assert (life(s, "p1"), life(s, "p3")) == (38, 38)
    check(s)


def test_karazikar_does_not_trigger_when_its_controller_is_attacked(cards):
    s = table(cards)
    put(s, "Karazikar, the Eye Tyrant", "p2")
    a = put(s, "Review Imp", "p1")
    to_declare(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 40)


def _spawns(s):
    return len([x for x in s.state.cards.values() if x.is_token and x.name == "Eldrazi Spawn" and x.controller == "p1"])


def test_x_counts_toward_the_mana_value_list_and_counters_not_toward_power(cards):
    s = table(cards, players=2)
    put(s, "Kozilek's Unsealing", "p1")
    put(s, "Sarkhan's Unsealing", "p1")
    hydra = card_named(s, "Review Hydra")
    act(s, "p1", type="move", card_ids=[hydra.id], to={"zone": "hand"})
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=hydra.id, x_value=3)  # mana value 4 on the stack (202.3e); power 0 (it enters with counters)
    settle(s)
    assert _spawns(s) == 2 and life(s, "p2") == 40
    check(s)


def test_x_zero_is_outside_the_list(cards):
    s = table(cards, players=2)
    put(s, "Kozilek's Unsealing", "p1")
    hydra = card_named(s, "Review Hydra")
    act(s, "p1", type="move", card_ids=[hydra.id], to={"zone": "hand"})
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=hydra.id, x_value=0)
    settle(s)
    assert _spawns(s) == 0


@pytest.mark.parametrize("face, spawns", [(0, 0), (1, 2)])
def test_a_modal_double_faced_spell_has_the_mana_value_of_the_face_cast(cards, face, spawns):
    s = table(cards, players=2)
    put(s, "Kozilek's Unsealing", "p1")
    twin = card_named(s, "Review Twin // Review Twin Giant")
    act(s, "p1", type="move", card_ids=[twin.id], to={"zone": "hand"})
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=twin.id, face=face)  # 712.8f / 202.3: {1}{G} is 2, {3}{G} is 4
    settle(s)
    assert _spawns(s) == spawns
    check(s)


def test_combat_rules_honour_a_value_list(cards):
    from app.rules.combat import block_problem
    from app.rules.plan import Plan

    s = table(cards, players=2)
    put(s, "Review Wall", "p1")
    attacker, pair, imp = put(s, "Review Imp", "p1"), put(s, "Review Pair", "p2"), put(s, "Review Imp", "p2")
    plan = Plan(s.state, "p1", s.cards, None)
    ach = plan.ch(s.state.cards[attacker.id])
    assert "can't block" in (block_problem(s.state, s.state.cards[pair.id], plan.ch(s.state.cards[pair.id]), s.state.cards[attacker.id],
                                           ach, s.cards) or "")  # power 2: listed
    assert block_problem(s.state, s.state.cards[imp.id], plan.ch(s.state.cards[imp.id]), s.state.cards[attacker.id], ach, s.cards) is None


# Each selector consumer that can't read a value list refuses the wording (the card stays not FULL): turn history, cast limits,
# cost changers, cast permissions, put-from-hand.
@pytest.mark.parametrize("text", [
    "At the beginning of your end step, if you cast a creature spell with power 4, 5, or 6 this turn, draw a card.",
    "At the beginning of your end step, if you sacrificed a creature with power 4, 5, or 6 this turn, draw a card.",
    "At the beginning of your end step, if a creature with power 4, 5, or 6 died this turn, draw a card.",
    "Whenever you cast your first creature spell with power 4, 5, or 6 each turn, draw a card.",
    "At the beginning of your end step, draw a card for each creature with power 2 or 3 that died this turn.",
    "Each player can't cast more than one creature spell with mana value 4, 5, or 6 each turn.",
    "Creature spells you cast with mana value 4, 5, or 6 cost {1} less to cast.",
    "You may cast creature spells with mana value 4, 5, or 6 from your graveyard.",
    "{T}: You may put a creature card with power 4, 5, or 6 from your hand onto the battlefield.",
])
def test_consumers_without_value_lists_refuse(text):
    assert coverage.of_card_data(probe(text)).level != "FULL", text
