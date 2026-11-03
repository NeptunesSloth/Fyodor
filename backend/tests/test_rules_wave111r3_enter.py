"""Wave 111R3: "If a creature you control would enter while you control an attacking creature, instead it enters tapped and attacking." (Kira Nerys,
Firebrand; rules/wave111r3_enter.py). A replacement effect on entering (614.1d, 614.12: the creature as it would exist on the battlefield, the
condition read before it enters); its controller chooses what it attacks as it enters (508.4, 614.12a): each creature its own question with three
players, none when there is one choice; never "attacked", unblocked after blockers are declared (508.4d). Every way it enters: a creature spell
(608.3), tokens (701.7a), a return (Miraculous Recovery), a blink (Cloudshift), a face-down card (manifest, 701.40: asked right after it entered);
not an opponent's creature, nor a noncreature, nor outside combat; an instruction that puts it attacking itself asks once (Hero of Bladehold).
Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, on_field, sandbox, through_combat
from tests.test_rules_conditionals import combat_step as _combat_step
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

KIRA = real("Kira Nerys, Firebrand", "{1}{R}{W}", 3, "Legendary Creature — Bajoran Soldier",
            "Trample\nIf a creature you control would enter while you control an attacking creature, instead it enters tapped and attacking.\n"
            "Whenever another creature you control enters, it gets +1/+1 until end of turn.", ("4", "3"), "RW")
EXTRA = [
    KIRA,
    real("Ambush Viper", "{1}{G}", 2, "Creature — Snake", "Flash\nDeathtouch", ("2", "1"), "G"),
    real("Raise the Alarm", "{1}{W}", 2, "Instant", "Create two 1/1 white Soldier creature tokens.", None, "W"),
    real("Cloudshift", "{W}", 1, "Instant", "Exile target creature you control, then return that card to the battlefield under your control.", None, "W"),
    real("Miraculous Recovery", "{4}{W}", 5, "Instant", "Return target creature card from your graveyard to the battlefield. Put a +1/+1 counter on it.", None, "W"),
    real("Hero of Bladehold", "{2}{W}{W}", 4, "Creature — Human Knight",
         "Battle cry (Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.)\n"
         "Whenever this creature attacks, create two 1/1 white Soldier creature tokens that are tapped and attacking.", ("3", "4"), "W"),
    real("Mind Stone", "{2}", 2, "Artifact", "{T}: Add {C}.\n{1}, {T}, Sacrifice this artifact: Draw a card.", None, ""),
    real("Test Bear 111R3", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Test Manifest 111R3", "{G}", 1, "Instant", "Manifest the top card of your library.", None, "G"),
    real("Warchief Giant", "{3}{R}{R}", 5, "Creature — Giant Warrior",
         "Haste\nMyriad (Whenever this creature attacks, for each opponent other than defending player, you may create a token copy that's tapped and "
         "attacking that player or a planeswalker they control. Exile the tokens at end of combat.)", ("5", "3"), "R"),
    real("Zara, Renegade Recruiter", "{3}{U}{B}", 5, "Legendary Creature — Dragon", "Flying\nWhenever Zara attacks, look at defending player's hand. You may put a "
         "creature card from it onto the battlefield under your control tapped and attacking that player or a planeswalker they control. Return that creature to its "
         "owner's hand at the beginning of the next end step.", ("4", "4"), "UB"),
]
NAMES = ["Kira Nerys, Firebrand"]
MINE = ["Kira Nerys, Firebrand", "Ambush Viper", "Raise the Alarm", "Cloudshift", "Miraculous Recovery", "Hero of Bladehold", "Mind Stone",
        "Test Bear 111R3", "Test Manifest 111R3"]


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


ASKED = "attacking whom"


def settle(s, *picks, limit=80):
    """Resolve the stack; a 508.4 question takes the next of ``picks`` (a player id), anything else its first options. Returns the questions asked."""
    picks, asked = list(picks), []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if ASKED in d.prompt:
                asked.append(d)
                ids = [picks.pop(0)] if picks else [d.options[0].id]
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
                continue
            else:
                ids = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def by_name(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def cast(s, name, targets=(), pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone in (f"{pid}:library", f"{pid}:hand"))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    return c


STEPS = ["declare_attackers", "declare_blockers"]


def combat_step(s):
    """Rules on, to Alice's declare attackers step; every player stops in the declare attackers and blockers steps (to act there)."""
    _combat_step(s)
    for pid in s.state.players:
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)


def table(cards, players=2, p2=()):
    """Kira on Alice's side, rules on, Alice in her declare attackers step."""
    s = sandbox(cards, *MINE, p2=p2, players=players)
    kira = on_field(s, "Kira Nerys, Firebrand")
    return s, kira


def target_of(s, c):
    a = s.state.cards[c.id].attacking
    return a.id if a is not None else None


def power(s, c):
    from app.rules import sba

    plan = Plan(s.state, "p1", s.cards, None)
    return sba.power(s.state.cards[c.id], plan.ch(s.state.cards[c.id]))


# -- a creature spell (608.3) -----------------------------------------------------------------------------------------------------------------
def test_flash_creature_enters_tapped_and_attacking(cards):
    s, kira = table(cards)
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", G=2)
    viper = cast(s, "Ambush Viper")
    assert settle(s) == []  # (one defending player: nothing to choose)
    v = s.state.cards[viper.id]
    assert v.zone == "p1:battlefield" and v.tapped and target_of(s, viper) == "p2"
    assert power(s, viper) == 3  # Kira's other ability: it entered (+1/+1)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 4 - 3  # it was attacking: unblocked, it deals its combat damage
    check(s)


@pytest.mark.parametrize("pick", ["p2", "p3"])
def test_its_controller_chooses_whom_it_attacks(cards, pick):  # 508.4: any defending player (802.2: each opponent)
    s, kira = table(cards, players=3)
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", G=2)
    viper = cast(s, "Ambush Viper")
    asked = settle(s, pick)
    assert len(asked) == 1 and {o.id for o in asked[0].options} == {"p2", "p3"} and asked[0].player == "p1"
    assert target_of(s, viper) == pick and s.state.cards[viper.id].tapped
    check(s)


@pytest.mark.parametrize("when", ["main phase", "no attackers"])
def test_not_while_you_control_no_attacking_creature(cards, when):
    s, kira = table(cards, players=3)
    combat_step(s)
    if when == "main phase":
        act(s, "p1", type="declare_attackers", attackers=[])
        through_combat(s)
    else:
        attack(s)
    mana(s, "p1", G=2)
    viper = cast(s, "Ambush Viper")
    assert settle(s) == []
    v = s.state.cards[viper.id]
    assert v.zone == "p1:battlefield" and not v.tapped and not v.is_attacking
    check(s)


def test_an_opponents_creature_is_not_changed(cards):  # "a creature you control": Bob's flash creature on Alice's turn
    s = sandbox(cards, *MINE, p2=["Ambush Viper"], players=3)
    kira = on_field(s, "Kira Nerys, Firebrand")
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p2", G=2)
    viper = next(c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "hand"})
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=viper.id)
    assert settle(s) == []
    v = s.state.cards[viper.id]
    assert v.zone == "p2:battlefield" and not v.tapped and not v.is_attacking
    check(s)


def test_a_noncreature_is_not_changed(cards):  # 614.12: the permanent as it would exist on the battlefield
    from app.rules import wave111r3_enter

    s, kira = table(cards)
    combat_step(s)
    attack(s, (kira, "p2"))
    plan = Plan(s.state, "p1", s.cards, None)
    stone = next(c for c in s.state.cards.values() if c.name == "Mind Stone")
    bear = next(c for c in s.state.cards.values() if c.name == "Test Bear 111R3")
    assert not wave111r3_enter.applies(plan, stone, "p1") and wave111r3_enter.applies(plan, bear, "p1")
    assert not wave111r3_enter.applies(plan, bear, "p2")  # (Bob controls no Kira)


# -- tokens (701.7a): each its own question -----------------------------------------------------------------------------------------------------
def test_each_token_chooses(cards):
    s, kira = table(cards, players=3)
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", W=1, C=1)
    cast(s, "Raise the Alarm")
    asked = settle(s, "p2", "p3")
    tokens = by_name(s, "Soldier")
    assert len(asked) == 2 and len(tokens) == 2
    assert sorted(target_of(s, t) for t in tokens) == ["p2", "p3"] and all(t.tapped for t in tokens)
    check(s)


def test_an_attacking_instruction_asks_once(cards):  # Hero of Bladehold's tokens are made attacking by the instruction itself
    s, kira = table(cards, players=3)
    hero = on_field(s, "Hero of Bladehold")
    combat_step(s)
    attack(s, (kira, "p2"), (hero, "p2"))
    asked = settle(s, "p3", "p3")
    tokens = by_name(s, "Soldier")
    assert len(tokens) == 2 and len(asked) == 2  # one question for each token, not two
    assert [target_of(s, t) for t in tokens] == ["p3", "p3"]
    check(s)


def test_myriad_tokens_attack_the_player_they_are_made_for(cards):  # 702.116a: the myriad instruction says what each copy attacks (508.4)
    s = sandbox(cards, *MINE, "Warchief Giant", players=3)
    kira = on_field(s, "Kira Nerys, Firebrand")
    giant = on_field(s, "Warchief Giant")
    combat_step(s)
    attack(s, (kira, "p2"), (giant, "p2"))
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            asked += [d] if ASKED in d.prompt else []
            ids = ["p3"] if any(o.id == "p3" for o in d.options) and ASKED not in d.prompt else [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    copies = [c for c in s.state.cards.values() if c.name == "Warchief Giant" and c.is_token and c.zone == "p1:battlefield"]
    assert asked == []  # (no 508.4 question of Kira's: Carol is the one it attacks)
    assert len(copies) == 1 and copies[0].tapped and target_of(s, copies[0]) == "p3"
    check(s)


def test_zaras_creature_attacks_the_player_it_was_taken_from(cards):  # "tapped and attacking that player or a planeswalker they control"
    s = sandbox(cards, *MINE, "Zara, Renegade Recruiter", p2=["Ambush Viper"], players=3)
    kira = on_field(s, "Kira Nerys, Firebrand")
    zara = on_field(s, "Zara, Renegade Recruiter")
    viper = next(c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "hand"})
    combat_step(s)
    attack(s, (kira, "p3"), (zara, "p2"))
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            asked += [d] if ASKED in d.prompt else []
            ids = [viper.id] if any(o.id == viper.id for o in d.options) else [o.id for o in d.options if o.id == "p3"][:1] or [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    v = s.state.cards[viper.id]
    assert asked == []  # (no 508.4 question of Kira's: Zara's instruction names Bob)
    assert v.zone == "p1:battlefield" and v.tapped and target_of(s, viper) == "p2"
    check(s)


# -- a return and a blink (400.7: a new object enters) -------------------------------------------------------------------------------------------
def test_returned_creature_enters_tapped_and_attacking(cards):
    s, kira = table(cards, players=3)
    bear = next(c for c in s.state.cards.values() if c.name == "Test Bear 111R3")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", W=1, C=4)
    cast(s, "Miraculous Recovery", [bear.id])
    asked = settle(s, "p3")
    b = s.state.cards[bear.id]
    assert len(asked) == 1 and b.zone == "p1:battlefield" and b.tapped and target_of(s, bear) == "p3" and b.counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("kira_attacks", [True, False])
def test_blinked_attacker(cards, kira_attacks):  # the condition is read as it would enter: the blinked creature left combat (506.4)
    s, kira = table(cards)
    bear = on_field(s, "Test Bear 111R3")
    combat_step(s)
    attack(*((s, (kira, "p2"), (bear, "p2")) if kira_attacks else (s, (bear, "p2"))))
    mana(s, "p1", W=1)
    cast(s, "Cloudshift", [bear.id])
    settle(s)
    b = s.state.cards[bear.id]
    assert b.zone == "p1:battlefield"
    assert (b.tapped, b.is_attacking) == ((True, True) if kira_attacks else (False, False))
    check(s)


# -- after blockers are declared (508.4d) and a face-down creature (701.40) ----------------------------------------------------------------------
def test_entering_after_blocks_is_unblocked(cards):
    s, kira = table(cards)
    combat_step(s)
    attack(s, (kira, "p2"))
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "declare_blockers"
    mana(s, "p1", G=2)
    viper = cast(s, "Ambush Viper")
    settle(s)
    assert target_of(s, viper) == "p2"
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 4 - 3
    check(s)


def test_manifested_card_is_asked_right_after_it_entered(cards):
    s, kira = table(cards, players=3)
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", G=1)
    cast(s, "Test Manifest 111R3")
    asked = settle(s, "p3")
    down = [c for c in s.state.cards.values() if c.face_down and c.zone == "p1:battlefield"]
    assert len(asked) == 1 and len(down) == 1 and down[0].tapped and target_of(s, down[0]) == "p3"
    assert "options" not in (s.view("p2")["rules"].get("decision") or {})
    check(s)


def test_manifested_card_with_one_choice_attacks_it(cards):  # (one defending player: nothing asked, it attacks him)
    s, kira = table(cards)
    combat_step(s)
    attack(s, (kira, "p2"))
    mana(s, "p1", G=1)
    cast(s, "Test Manifest 111R3")
    assert settle(s) == []
    down = [c for c in s.state.cards.values() if c.face_down and c.zone == "p1:battlefield"]
    assert len(down) == 1 and down[0].tapped and target_of(s, down[0]) == "p2" and not s.state.rules.attack_pending111r3
    check(s)
