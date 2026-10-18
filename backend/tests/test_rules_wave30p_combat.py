"""Wave 30P: combat-structure wordings (CR 2026-09-25). Real Oracle text (tests/fixtures/wave30p_cards.json, from data/cards.sqlite); every scenario
runs in a 3-player game and checks the replay and a save and a load.

* 509.1c: a block requirement. "Blocks it / this creature this combat if able" (Avalanche Tusker, Grappling Hook, Giant Ambush Beetle), "Target creature
  blocks target creature this turn if able" (Hunt Down) and "~ must be blocked each combat this turn if able" (Anzrag) are obeyed whenever the blocker could
  block as declared; a creature that can't block (tapped, or not a defending player's: 506.2, 508.5) has nothing to obey (509.1c: "if able").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30p_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30p", number=f"P{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, a=(), b=(), c=()):
    """Alice, Bob and Carol; each deck is the named cards plus basic lands; Alice's first main phase (turn 1)."""
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in a), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in b), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in c), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def to_phase(s, phase, turn=None, limit=160):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached (its triggers may be on the stack)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def drive(s, pick=(), stop_at=("declare_blockers",), limit=40):
    """Resolve what is on the stack; a choice is answered with the first of ``pick`` (option ids or labels) it offers, else its first option; a
    decision of a kind in ``stop_at`` ends the drive and is returned. Every (player, kind, option ids) asked is recorded in ``s.asked``."""
    s.asked = getattr(s, "asked", [])
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return None
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        s.asked.append((d.player, d.kind, [o.id for o in d.options]))
        if d.kind in stop_at:
            return d
        want = [o.id for p in pick for o in d.options if p in (o.id, o.label)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=(want or [o.id for o in d.options])[: max(1, d.min_choices)])
    raise AssertionError("never settled")


def attack(s, *pairs, pid="p1"):
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def block(s, pid, *pairs):
    act(s, pid, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


# -- 509.1c: forced blocks ----------------------------------------------------------------------------------------------------------------


def test_avalanche_tusker_forces_only_the_defending_players_creature_to_block(cards):
    """Avalanche Tusker: "Whenever this creature attacks, target creature defending player controls blocks it this combat if able." Attacking Carol,
    the target is one of Carol's creatures (508.5: Carol is the defending player; Bob's Bears can't be chosen) and it must block (509.1c)."""
    s = three(cards, ["Avalanche Tusker"], ["Grizzly Bears"], ["Grizzly Bears", "Serra Angel"])
    tusker, bob_bears = put(s, "Avalanche Tusker"), put(s, "Grizzly Bears", "p2")
    carol_bears, carol_angel = put(s, "Grizzly Bears", "p3"), put(s, "Serra Angel", "p3")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (tusker, "p3"))
    d = drive(s, pick=[carol_bears.id])
    assert d.kind == "declare_blockers" and d.player == "p3"
    targets = [ids for p, k, ids in s.asked if k == "choose_one"]
    assert targets == [[carol_bears.id, carol_angel.id]] and bob_bears.id not in targets[0], targets  # (508.5: Carol's creatures only)
    with pytest.raises(ActionError, match="if able"):
        block(s, "p3")  # (no block at all)
    with pytest.raises(ActionError, match="if able"):
        block(s, "p3", (carol_angel, tusker))  # (the Angel blocks, but the forced Bears doesn't)
    block(s, "p3", (carol_bears, tusker))
    check(s)


def test_a_tapped_creature_can_not_be_forced_to_block(cards):
    """509.1c: a creature that can't block (it is tapped) isn't required to; Avalanche Tusker's target is still legal (115.1) and the requirement
    simply can't be obeyed, so Carol (whose Angel can block) may declare no blockers."""
    s = three(cards, ["Avalanche Tusker"], [], ["Grizzly Bears", "Serra Angel"])
    tusker, carol_bears = put(s, "Avalanche Tusker"), put(s, "Grizzly Bears", "p3")
    put(s, "Serra Angel", "p3")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p3", type="tap", card_ids=[carol_bears.id])
    attack(s, (tusker, "p3"))
    d = drive(s, pick=[carol_bears.id])
    assert d.kind == "declare_blockers" and d.player == "p3"
    block(s, "p3")
    assert s.state.players["p3"].life == 34  # (the 6/4 Elephant Warrior was unblocked)
    check(s)


@pytest.mark.parametrize("victim", ["p2", "p3", "declined"])
def test_grappling_hook_only_binds_a_creature_that_is_defending(cards, victim):
    """Grappling Hook: "Whenever equipped creature attacks, you may have target creature block it this turn if able." Targeting Bob's creature
    while attacking Carol binds nothing (506.2: Bob isn't a defending player, so his creature can't block it: 509.1c); targeting Carol's does, unless
    the "you may" is declined."""
    s = three(cards, ["Grappling Hook", "Grizzly Bears"], ["Grizzly Bears"], ["Grizzly Bears"])
    hook, bears = put(s, "Grappling Hook"), put(s, "Grizzly Bears")
    bob_bears, carol_bears = put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    act(s, "p1", type="attach", card_ids=[hook.id], to=bears.id)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (bears, "p3"))
    d = drive(s, pick=["no" if victim == "declined" else "yes", (bob_bears if victim == "p2" else carol_bears).id])
    assert d.kind == "declare_blockers" and d.player == "p3"
    if victim == "p3":
        with pytest.raises(ActionError, match="if able"):
            block(s, "p3")
        block(s, "p3", (carol_bears, bears))
    else:
        block(s, "p3")  # (Bob's Bears is bound, but it is not able to block Carol's attacked creature; or nobody is bound)
    check(s)


def test_anzrag_must_be_blocked_each_combat_this_turn(cards):
    """Anzrag, the Quake-Mole: "{3}{R}{R}{G}{G}: Anzrag must be blocked each combat this turn if able." (509.1c) Carol, attacked, has to block it
    with a creature she can; Bob (not defending) is not asked."""
    s = three(cards, ["Anzrag, the Quake-Mole"], ["Grizzly Bears"], ["Grizzly Bears"])
    anzrag, carol_bears = put(s, "Anzrag, the Quake-Mole"), put(s, "Grizzly Bears", "p3")
    put(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=4)
    mana(s, R=2, G=2, C=3)
    act(s, "p1", type="activate_ability", card_id=anzrag.id, ability=1)
    drive(s, stop_at=())
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (anzrag, "p3"))
    d = drive(s)
    assert d.kind == "declare_blockers" and d.player == "p3"
    with pytest.raises(ActionError, match="must be blocked"):
        block(s, "p3")
    block(s, "p3", (carol_bears, anzrag))
    check(s)


def test_hunt_down_binds_the_first_target_to_the_second(cards):
    """Hunt Down: "Target creature blocks target creature this turn if able." Bob's Bears must block Alice's Bears, which attacks Bob; the same
    Bears does not have to block when Alice's Bears attacks Carol (it is not a defending player's creature then)."""
    for attacked in ("p2", "p3"):
        s = three(cards, ["Hunt Down", "Grizzly Bears"], ["Grizzly Bears"], ["Grizzly Bears"])
        bears, bob_bears = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
        put(s, "Grizzly Bears", "p3")
        to_phase(s, "main1", turn=4)
        to_hand(s, "Hunt Down")
        mana(s, G=1)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Hunt Down").id, targets=[bob_bears.id, bears.id], target_counts=[1, 1])
        drive(s, stop_at=())
        to_phase(s, "declare_attackers", turn=4)
        attack(s, (bears, attacked))
        d = drive(s)
        assert d.kind == "declare_blockers" and d.player == attacked
        if attacked == "p2":
            with pytest.raises(ActionError, match="if able"):
                block(s, "p2")
            block(s, "p2", (bob_bears, bears))
        else:
            block(s, "p3")
        check(s)


def test_giant_ambush_beetle_makes_the_chosen_creature_block_it(cards):
    """Giant Ambush Beetle: "When this creature enters, you may have target creature block it this turn if able." ("it" is the Beetle itself.)"""
    s = three(cards, ["Giant Ambush Beetle"], [], ["Grizzly Bears"])
    to_phase(s, "main1", turn=4)
    carol_bears = put(s, "Grizzly Bears", "p3")
    to_hand(s, "Giant Ambush Beetle")
    mana(s, G=6, R=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Giant Ambush Beetle").id)
    drive(s, pick=["yes", carol_bears.id], stop_at=())
    beetle = card_named(s, "Giant Ambush Beetle")
    imposed = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[carol_bears.id]).imposed
    assert f"must_block_obj:{s.state.rules.object_id(beetle.id)}" in imposed, imposed  # (Carol's Bears must block that very Beetle, 509.1c)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (beetle, "p3"))  # (it has haste)
    d = drive(s)
    assert d.kind == "declare_blockers" and d.player == "p3"
    with pytest.raises(ActionError, match="if able"):
        block(s, "p3")
    block(s, "p3", (carol_bears, beetle))
    check(s)


# -- 509.1b: "can't be blocked this combat" / "and up to one other target creature" ----------------------------------------------------------


def test_yuan_shaos_infantry_is_unblockable_only_for_the_combat_it_attacked_alone_in(cards):
    """Yuan Shao's Infantry: "Whenever this creature attacks alone, this creature can't be blocked this combat." (509.1b; a turn may have several combats,
    500.8.) Alone against Carol it can't be blocked; in the additional combat of Relentless Assault it attacks with a Bears (not alone: no trigger) and
    the first combat's restriction is over, so Carol's Bears blocks it."""
    s = three(cards, ["Yuan Shao's Infantry", "Relentless Assault", "Grizzly Bears"], [], ["Grizzly Bears"])
    inf, bears, carol_bears = put(s, "Yuan Shao's Infantry"), put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p3")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (inf, "p3"))
    drive(s, stop_at=("declare_blockers",))
    with pytest.raises(ActionError, match="can't be blocked"):
        block(s, "p3", (carol_bears, inf))
    block(s, "p3")
    to_phase(s, "main2", turn=4)
    to_hand(s, "Relentless Assault")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Relentless Assault").id)
    drive(s, stop_at=())
    to_phase(s, "declare_attackers", turn=4)
    assert s.state.rules.combats == 2, s.state.rules.combats
    attack(s, (inf, "p3"), (bears, "p3"))
    drive(s, stop_at=("declare_blockers",))
    block(s, "p3", (carol_bears, inf))  # (no longer "this combat" of the first one)
    check(s)


def test_martha_jones_makes_two_creatures_unblockable_this_turn_and_not_a_third(cards):
    """Martha Jones: "Whenever you sacrifice a Clue, Martha Jones and up to one other target creature can't be blocked this turn." Martha and the
    chosen Bears can't be blocked; Alice's other Bears can."""
    s = three(cards, ["Martha Jones", "Grizzly Bears", "Grizzly Bears"], [], ["Grizzly Bears"])
    martha, carol_bears = put(s, "Martha Jones"), put(s, "Grizzly Bears", "p3")
    bears, other = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"][:2]
    for c in (bears, other):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="create_token", player="p1", token={"name": "Clue", "type_line": "Token Artifact — Clue", "text": "{2}, Sacrifice this token: Draw a card."})
    clue = next(c for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=clue.id, ability=0)
    drive(s, pick=[bears.id], stop_at=())
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (martha, "p3"), (bears, "p3"), (other, "p3"))
    drive(s, stop_at=("declare_blockers",))
    for unblockable in (martha, bears):
        with pytest.raises(ActionError, match="can't be blocked"):
            block(s, "p3", (carol_bears, unblockable))
    block(s, "p3", (carol_bears, other))
    check(s)


# -- 508.4: put onto the battlefield attacking, "that player" ------------------------------------------------------------------------------


def test_kaalia_puts_the_angel_onto_the_battlefield_attacking_the_opponent_she_attacked(cards):
    """Kaalia of the Vast: "Whenever Kaalia attacks an opponent, you may put an Angel, Demon, or Dragon creature card from your hand onto the
    battlefield tapped and attacking that opponent." (508.4: the effect says whom, so there is no choice: Carol, not Bob.) A planeswalker she attacks
    instead is not "an opponent" (506.3d): no trigger."""
    s = three(cards, ["Kaalia of the Vast", "Serra Angel", "Shivan Dragon"], ["Grizzly Bears"], ["Grizzly Bears"])
    kaalia = put(s, "Kaalia of the Vast")
    put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    to_phase(s, "main1", turn=4)
    angel, dragon = to_hand(s, "Serra Angel"), to_hand(s, "Shivan Dragon")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (kaalia, "p3"))
    drive(s, pick=["yes", angel.id], stop_at=("declare_blockers",))
    got = s.state.cards[angel.id]
    assert got.zone == "p1:battlefield" and got.tapped and got.attacking is not None and got.attacking.id == "p3", got
    assert all(k != "choose_one" for _, k, _ in s.asked), s.asked  # (never asked whom the Angel attacks)
    assert s.state.cards[dragon.id].zone == "p1:hand"
    check(s)


def test_kaalia_attacking_a_planeswalker_does_not_trigger(cards):
    s = three(cards, ["Kaalia of the Vast", "Serra Angel"], [], ["Gideon Jura", "Grizzly Bears"])
    kaalia, gideon = put(s, "Kaalia of the Vast"), put(s, "Gideon Jura", "p3")
    put(s, "Grizzly Bears", "p3")
    act(s, "p3", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    to_phase(s, "main1", turn=4)
    angel = to_hand(s, "Serra Angel")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (kaalia, gideon.id))
    drive(s, stop_at=("declare_blockers",))
    assert s.state.cards[angel.id].zone == "p1:hand"
    check(s)


def test_kari_zevs_ragavan_enters_attacking_whatever_alice_chooses_even_a_battle(cards):
    """Kari Zev, Skyship Raider: "Whenever Kari Zev attacks, create Ragavan, a legendary 2/1 red Monkey creature token. Ragavan enters tapped and
    attacking. Exile that token at end of combat." Nothing says whom, so its controller chooses (508.4) among every defending player (802.2: Bob
    and Carol), the planeswalkers they control and the battles their players protect (310.9b) — here Carol protects Bob's Siege. Ragavan attacks
    the battle, then is exiled at end of combat."""
    s = three(cards, ["Kari Zev, Skyship Raider"], ["Invasion of Zendikar // Awakened Skyclave", "Grizzly Bears"], ["Gideon Jura"])
    kari = put(s, "Kari Zev, Skyship Raider")
    put(s, "Grizzly Bears", "p2")
    gideon = put(s, "Gideon Jura", "p3")
    act(s, "p3", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    siege = put(s, "Invasion of Zendikar // Awakened Skyclave", "p2")
    act(s, "p2", type="counter", card_ids=[siege.id], kind="defense", delta=4)
    for _ in range(6):  # 310.11: no protector yet - Bob chooses one of his opponents, Carol
        if (d := s.state.rules.decision) is not None:
            act(s, "p2", type="choose", decision_id=d.id, option_ids=["p3"])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == "p3"
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (kari, "p2"))
    d = drive(s, pick=[siege.id], stop_at=("choose_one", "declare_blockers"))
    assert d.kind == "choose_one" and d.player == "p1", d
    labels = sorted(o.label for o in d.options)
    assert labels == ["Bob", "Carol", "Gideon Jura (Carol)", "Invasion of Zendikar // Awakened Skyclave (battle)"], labels
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[siege.id])
    d = drive(s, stop_at=("declare_blockers",))
    ragavan = next(c for c in s.state.cards.values() if c.name == "Ragavan" and c.zone == "p1:battlefield")
    assert ragavan.tapped and ragavan.attacking is not None and ragavan.attacking.id == siege.id, ragavan.attacking
    check(s)
    block(s, "p2")
    drive(s, stop_at=())
    assert not any(c.name == "Ragavan" and c.zone == "p1:battlefield" for c in s.state.cards.values())  # (exiled at end of combat)
    check(s)


def test_shark_shredder_reanimates_from_the_damaged_players_graveyard_attacking_that_player(cards):
    """Shark Shredder, Killer Clone: "Whenever Shark Shredder deals combat damage to a player, put up to one target creature card from that player's
    graveyard onto the battlefield under your control. It enters tapped and attacking that player." In a 3-player game that is Bob (the player it
    damaged): only Bob's graveyard is a choice, and the Bears attacks Bob, unblocked (508.4d), for 2 more."""
    s = three(cards, ["Shark Shredder, Killer Clone"], ["Grizzly Bears"], ["Serra Angel"])
    shark = put(s, "Shark Shredder, Killer Clone")
    bob_bears, carol_angel = card_named(s, "Grizzly Bears", "p2"), card_named(s, "Serra Angel", "p3")
    act(s, "p2", type="move", card_ids=[bob_bears.id], to={"zone": "graveyard"})
    act(s, "p3", type="move", card_ids=[carol_angel.id], to={"zone": "graveyard"})
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (shark, "p2"))
    drive(s, pick=[bob_bears.id], stop_at=())
    got = s.state.cards[bob_bears.id]
    assert got.zone == "p1:battlefield" and got.controller == "p1", got.zone
    assert s.state.cards[carol_angel.id].zone == "p3:graveyard"
    assert [s.state.players[p].life for p in ("p2", "p3")] == [40 - 4 - 2, 40]  # (Shark Shredder's first strike, then the Bears in the regular damage step)
    check(s)


# -- 508.4: a limit on the card put onto the battlefield attacking ------------------------------------------------------------------------------


@pytest.mark.parametrize("together", [False, True])
def test_kinscaer_sentry_puts_in_a_creature_up_to_the_number_of_attackers(cards, together):
    """Kinscaer Sentry: "Whenever this creature attacks, you may put a creature card with mana value X or less from your hand onto the battlefield tapped
    and attacking, where X is the number of attacking creatures you control." X is read as the card is chosen (608.2h): alone, X is 1 (Llanowar Elves);
    with a Grizzly Bears attacking too it is 2 (the Bears of the hand also fit). The card attacks the player its controller chooses (3 players)."""
    s = three(cards, ["Kinscaer Sentry", "Grizzly Bears", "Llanowar Elves", "Serra Angel"], ["Grizzly Bears"], ["Grizzly Bears"])
    sentry = put(s, "Kinscaer Sentry")
    put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    mate = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[mate.id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", turn=4)
    hand = {n: to_hand(s, n) for n in ("Llanowar Elves", "Serra Angel")}
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (sentry, "p3"), *([(mate, "p3")] if together else []))
    d = drive(s, pick=["yes"], stop_at=("choose_cards",))
    assert d.kind == "choose_cards" and d.player == "p1", d
    assert sorted(o.label for o in d.options) == (["Llanowar Elves"] if not together else ["Llanowar Elves"]), d.options  # (the Bears is on the battlefield)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hand["Llanowar Elves"].id])
    d = drive(s, pick=["p3"], stop_at=("declare_blockers",))
    elves = s.state.cards[hand["Llanowar Elves"].id]
    assert elves.zone == "p1:battlefield" and elves.tapped and elves.attacking is not None and elves.attacking.id == "p3", elves
    assert s.state.cards[hand["Serra Angel"].id].zone == "p1:hand"  # (mana value 5 is more than the number of attackers)
    check(s)


def test_shadowfax_puts_in_only_a_creature_with_less_power(cards):
    """Shadowfax, Lord of Horses (a 4/4): "Whenever Shadowfax attacks, you may put a creature card with lesser power from your hand onto the battlefield
    tapped and attacking." A 2/2 Bears fits; a 4/4 Serra Angel (equal power) and a 5/5 Shivan Dragon do not."""
    s = three(cards, ["Shadowfax, Lord of Horses", "Grizzly Bears", "Serra Angel", "Shivan Dragon"], ["Grizzly Bears"], ["Grizzly Bears"])
    fax = put(s, "Shadowfax, Lord of Horses")
    put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    to_phase(s, "main1", turn=4)
    hand = {n: to_hand(s, n) for n in ("Grizzly Bears", "Serra Angel", "Shivan Dragon")}
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (fax, "p2"))
    d = drive(s, pick=["yes"], stop_at=("choose_cards",))
    assert [o.label for o in d.options] == ["Grizzly Bears"], d.options
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hand["Grizzly Bears"].id])
    drive(s, pick=["p3"], stop_at=("declare_blockers",))
    bears = s.state.cards[hand["Grizzly Bears"].id]
    assert bears.zone == "p1:battlefield" and bears.attacking is not None and bears.attacking.id == "p3", bears  # (its controller chose Carol, not whom Shadowfax attacks)
    check(s)


# -- coverage ---------------------------------------------------------------------------------------------------------------------------------

FULL = ["Avalanche Tusker", "Impetuous Devils", "Fighter Class", "Grappling Hook", "Turntimber Basilisk", "Giant Ambush Beetle", "Tower Above", "Hunt Down",
        "Rimehorn Aurochs", "Anzrag, the Quake-Mole", "Ma Chao, Western Warrior", "Yuan Shao's Infantry", "Martha Jones", "Lockjaw, Slobbering Teleporter",
        "Flummoxed Cyclops", "Forgestoker Dragon", "Kaalia of the Vast", "Kari Zev, Skyship Raider", "Shark Shredder, Killer Clone", "Seraphic Greatsword",
        "Pugnacious Pugilist", "Maestros Diabolist", "Ghalta and Mavren", "Kinscaer Sentry", "Shadowfax, Lord of Horses", "Paladin Elizabeth Taggerdy",
        "Aether Vial", "Jhoira, Ageless Innovator"]


@pytest.mark.parametrize("name", FULL)
def test_the_wordings_this_wave_reads_are_full(cards, name):
    """Every card above reads completely now (the first four sentences' scenarios are above; the rest share their wordings)."""
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("text", [
    "create a 1/1 white Soldier creature token. Bob enters tapped and attacking.",  # (not the token that was made)
    "create two 1/1 white Soldier creature tokens. They enter tapped and attacking.",
    "put a creature card from your hand onto the battlefield tapped and attacking that player or a planeswalker they control.",  # (Zara, Hans Eriksson)
])
def test_wordings_this_wave_does_not_read_stay_manual(text):
    assert scripts.parse_effects(text) is None


def test_a_bare_x_or_less_is_the_spells_x():
    # wave 51G (put_from_hand): with no "where X is", X is the spell's X (107.3; Mind into Matter); this wave had refused it
    effects = scripts.parse_effects("put a creature card with mana value X or less from your hand onto the battlefield.")
    assert effects is not None and effects[0][0]["mv"] == ["<=", {"x": 1}]


def test_a_saved_question_from_before_the_attack_choice_was_shared_still_resumes():
    """The question "attacking whom?" of a creature put onto the battlefield attacking was asked by three copies of one routine (wave 30P made it one);
    a game saved with the old step name ("enter_attacking") answers through the shared one."""
    from app.rules import refused_zones, token_grammar

    assert refused_zones.RESUME["enter_attacking"] is token_grammar.RESUME["token_attack"]
