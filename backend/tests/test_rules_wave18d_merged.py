"""Wave 18D: merged permanents - mutate (CR 702.140, 730) and meld (CR 701.42, 712.4, 712.21), real Oracle text, CR 2026-09-25.

Every scenario checks the replay and a save/load round trip; the privacy test builds every viewer's table mid-decision.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave6c_tokens_pumps import chars, mana, pt, put, to_hand
from tests.wave9c_kit import build, check, life


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18D-{name[:9]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


MUTATE_REMINDER = " (If you cast this spell for its mutate cost, put it over or under target non-Human creature you own. They mutate into the creature on top plus all abilities from under it.)"
EXTRA = [
    real("Gemrazer", "{3}{G}", 4, "Creature — Beast Mutant",
         "Mutate {1}{G}{G}" + MUTATE_REMINDER + "\nReach, trample\nWhenever this creature mutates, destroy target artifact or enchantment an opponent controls.", ("4", "4"), "G"),
    real("Glowstone Recluse", "{2}{G}", 3, "Creature — Spider Mutant",
         "Mutate {3}{G}" + MUTATE_REMINDER + "\nReach\nWhenever this creature mutates, put two +1/+1 counters on it.", ("2", "2"), "G"),
    real("Huntmaster Liger", "{3}{W}", 4, "Creature — Cat Mutant",
         "Mutate {2}{W}" + MUTATE_REMINDER + "\nWhenever this creature mutates, other creatures you control get +X/+X until end of turn, where X is the number of times this creature has mutated.", ("4", "4"), "W"),
    real("Insatiable Hemophage", "{3}{B}", 4, "Creature — Vampire Mutant",
         "Mutate {2}{B}" + MUTATE_REMINDER + "\nDeathtouch\nWhenever this creature mutates, each opponent loses X life and you gain X life, where X is the number of times this creature has mutated.", ("3", "3"), "B"),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "Vigilance", ("2", "2"), "G"),
    real("Probe Human", "{1}{W}", 2, "Creature — Human Soldier", "", ("2", "2"), "W"),
    real("Probe Altar", "{2}", 2, "Artifact", "", None),
    real("Probe Mourner", "{1}{G}", 2, "Creature — Elf", "When this creature dies, draw a card.", ("1", "1"), "G"),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 3 damage to any target.", None, "R"),
    real("Probe Counterspell", "{U}{U}", 2, "Instant", "Counter target spell.", None, "U"),
    real("Probe Bounce", "{U}", 1, "Instant", "Return target creature to its owner's hand.", None, "U"),
]
NAMES = ["Gemrazer", "Glowstone Recluse", "Huntmaster Liger", "Insatiable Hemophage"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_mutate_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def mutate_key(s, c, pid="p1"):
    from app.rules import alt_costs
    from app.rules.plan import Plan

    plan = Plan(s.state, pid, s.cards, None)
    found = [o.key for o in alt_costs.offers(s.state, pid, c, plan.ch(c), s.cards) if o.tag == "mutate"]
    return found[0] if found else None


def mutate(s, name, onto, over="over", pid="p1", **m):
    spell = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=spell.id, targets=[onto.id], alt_cost=mutate_key(s, spell, pid))
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [over] if d.resume and d.resume.get("step") == "mutate_choice" else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return spell


def test_mutate_over_merges_and_triggers(cards):
    s = build(cards, ["Gemrazer", "Probe Bear", "Probe Altar"], ["Probe Altar"])
    bear = put(s, "Probe Bear")
    altar = put(s, "Probe Altar", "p2")
    assert mutate_key(s, to_hand(s, "Gemrazer")) is not None
    g = mutate(s, "Gemrazer", bear, G=3)
    host = s.state.cards[bear.id]
    assert g.id not in s.state.cards and host.name == "Gemrazer" and [p.name for p in host.merged] == ["Gemrazer", "Probe Bear"]
    ch = chars(s, host)
    assert pt(s, host) == (4, 4) and {"reach", "trample", "vigilance"} <= ch.keywords  # 702.140e: every ability, the top's characteristics
    assert altar.id not in s.state.zones["p2:battlefield"]  # 702.140d: the trigger destroyed it
    check(s)


def test_mutate_under_keeps_the_target_on_top_with_every_ability(cards):
    s = build(cards, ["Gemrazer", "Probe Bear"])
    bear = put(s, "Probe Bear")
    mutate(s, "Gemrazer", bear, over="under", G=3)
    host = s.state.cards[bear.id]
    assert host.name == "Probe Bear" and [p.name for p in host.merged] == ["Probe Bear", "Gemrazer"]
    assert pt(s, host) == (2, 2) and {"reach", "trample", "vigilance"} <= chars(s, host).keywords  # 730.2a: the top's characteristics
    check(s)


def test_mutate_counts_each_merge_and_the_pile_breaks_up_when_it_dies(cards):
    s = build(cards, ["Insatiable Hemophage", "Glowstone Recluse", "Probe Bear"], ["Probe Bolt"])
    bear = put(s, "Probe Bear")
    mutate(s, "Glowstone Recluse", bear, G=4)
    assert s.state.cards[bear.id].counters == {"+1/+1": 2} and pt(s, s.state.cards[bear.id]) == (4, 4)  # 702.140d, 730.2c
    mutate(s, "Insatiable Hemophage", bear, B=3)
    assert life(s, "p2") == 38 and life(s) == 42  # X = the number of times it has mutated (twice)
    host = s.state.cards[bear.id]
    assert [p.name for p in host.merged] == ["Insatiable Hemophage", "Glowstone Recluse", "Probe Bear"]
    assert pt(s, host) == (7, 7) and host.counters == {"+1/+1": 4}  # 3/3; the Recluse's trigger, an ability of the pile, fired again (702.140e)
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})  # destroyed by hand: one permanent leaves, 730.3
    gy = sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"])
    assert gy == ["Glowstone Recluse", "Insatiable Hemophage", "Probe Bear"] and not s.state.cards[bear.id].merged
    check(s)


def test_mutate_is_not_offered_without_a_non_human_creature_you_own(cards):
    s = build(cards, ["Gemrazer", "Probe Human"])
    g = to_hand(s, "Gemrazer")
    assert mutate_key(s, g) is None  # nothing to merge with
    put(s, "Probe Human")
    assert mutate_key(s, g) is None  # 702.140a: a Human isn't a legal target


def test_mutating_spell_with_an_illegal_target_enters_as_a_creature(cards):
    s = build(cards, ["Gemrazer", "Probe Bear"], ["Probe Bolt"])
    act(s, "p2", type="set_prefs", response="on")
    bear = put(s, "Probe Bear")
    g = to_hand(s, "Gemrazer")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[bear.id], alt_cost=mutate_key(s, g))
    bolt = to_hand(s, "Probe Bolt", "p2")
    mana(s, "p2", R=1)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # in response: the target dies
    settle(s)
    gem = s.state.cards[g.id]
    assert gem.zone == "p1:battlefield" and not gem.merged and gem.name == "Gemrazer"  # 702.140b: a creature spell, it enters
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


# -- meld ---------------------------------------------------------------------------------------------------------------------
def meld_set(a, b, result):
    """Three cards of a meld pair as the card database lists them: each front half names the other half and the result."""
    from tests.fixtures.cards import cid

    ids = {c[0]: cid(f"{c[0]}|tst|18D-{c[0][:9]}") for c in (a, b, result)}

    def parts(own):
        return [{"id": ids[n], "component": "meld_result" if n == result[0] else "meld_part", "name": n, "type_line": "Creature"}
                for n in (a[0], b[0], result[0]) if n != own]

    out = []
    for c in (a, b, result):
        name, cost, cmc, types, text, p, colors = c
        out.append(card(name, set_code="tst", number=f"18D-{name[:9]}", layout="meld", mana_cost=cost, cmc=float(cmc), type_line=types,
                        oracle_text=text, colors=list(colors), color_identity=list(colors), keywords=[],
                        power=p[0], toughness=p[1], all_parts=parts(name), **({"loyalty": "7"} if "Planeswalker" in types else {})))
    return out


GISELA = ("Gisela, the Broken Blade", "{2}{W}{W}", 4, "Legendary Creature — Angel Horror",
          "Flying, first strike, lifelink\nAt the beginning of your end step, if you both own and control Gisela and a creature named Bruna, the Fading Light, exile them, then meld them into Brisela, Voice of Nightmares.",
          ("4", "3"), "W")
BRUNA = ("Bruna, the Fading Light", "{5}{W}{W}", 7, "Legendary Creature — Angel Horror",
         "When you cast this spell, you may return target Angel or Human creature card from your graveyard to the battlefield.\nFlying, vigilance\n(Melds with Gisela, the Broken Blade.)",
         ("5", "7"), "W")
BRISELA = ("Brisela, Voice of Nightmares", "", 0, "Legendary Creature — Eldrazi Angel",
           "Flying, first strike, vigilance, lifelink\nYour opponents can't cast spells with mana value 3 or less.", ("9", "10"), "W")
GRAF = ("Graf Rats", "{1}{B}", 2, "Creature — Rat", "At the beginning of combat on your turn, if you both own and control this creature and a creature named Midnight Scavengers, exile them, then meld them into Chittering Host.", ("2", "1"), "B")
SCAV = ("Midnight Scavengers", "{4}{B}", 5, "Creature — Human Rogue", "When this creature enters, you may return target creature card with mana value 3 or less from your graveyard to your hand.\n(Melds with Graf Rats.)", ("3", "3"), "B")
HOST = ("Chittering Host", "", 0, "Creature — Eldrazi Horror", "Menace\nWhen this creature enters, other creatures you control get +1/+0 and gain menace until end of turn.", ("5", "6"), "B")
MELD_CARDS = [*meld_set(GISELA, BRUNA, BRISELA), *meld_set(GRAF, SCAV, HOST)]
EXTRA.extend(MELD_CARDS)


def test_meld_cards_are_full(cards):
    for name in ("Gisela, the Broken Blade", "Graf Rats"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_meld_exiles_both_and_one_melded_permanent_enters(cards):
    from tests.test_rules_conditionals import the_end_step

    s = build(cards, ["Gisela, the Broken Blade", "Bruna, the Fading Light"])
    gisela, bruna = put(s, "Gisela, the Broken Blade"), put(s, "Bruna, the Fading Light")
    the_end_step(s)
    host = s.state.cards[gisela.id]
    assert bruna.id not in s.state.cards and host.zone == "p1:battlefield" and host.melded
    assert host.name == "Brisela, Voice of Nightmares" and [p.name for p in host.merged] == ["Gisela, the Broken Blade", "Bruna, the Fading Light"]
    ch = chars(s, host)
    assert pt(s, host) == (9, 10) and ch.mana_value == 11 and {"flying", "first strike", "vigilance", "lifelink"} <= ch.keywords  # 712.8g
    check(s)
    act(s, "p1", type="move", card_ids=[gisela.id], to={"zone": "graveyard"})  # 712.21: one permanent leaves, two cards arrive
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"]) == ["Bruna, the Fading Light", "Gisela, the Broken Blade"]
    assert chars(s, s.state.cards[gisela.id]).name == "Gisela, the Broken Blade" and not s.state.cards[gisela.id].melded
    check(s)


def test_meld_does_nothing_without_the_partner(cards):
    from tests.test_rules_conditionals import the_end_step

    s = build(cards, ["Gisela, the Broken Blade", "Bruna, the Fading Light"])
    gisela = put(s, "Gisela, the Broken Blade")
    the_end_step(s)
    assert s.state.cards[gisela.id].zone == "p1:battlefield" and not s.state.cards[gisela.id].melded  # the intervening if (603.4)
    check(s)


def test_a_merged_commander_goes_to_the_command_zone_and_the_rest_to_the_hand(cards):
    """903.3c: the pile with a commander is that player's commander; 903.9c: put into the command zone instead of the hand, only the
    commander goes there, every other card of it goes to the hand."""
    s = build(cards, ["Gemrazer"], ["Probe Bounce"])
    act(s, "p2", type="set_prefs", response="on")
    krenko = put(s, "Krenko, Mob Boss")
    assert s.state.cards[krenko.id].commander_key
    mutate(s, "Gemrazer", krenko, over="over", G=3)
    host = s.state.cards[krenko.id]
    assert host.name == "Gemrazer" and host.commander_key and [p.name for p in host.merged] == ["Gemrazer", "Krenko, Mob Boss"]
    bounce = to_hand(s, "Probe Bounce", "p2")
    mana(s, "p2", U=1)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=bounce.id, targets=[krenko.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[krenko.id].zone == "p1:command" and s.state.cards[krenko.id].name == "Krenko, Mob Boss"
    gem = next(c for c in s.state.cards.values() if c.name == "Gemrazer")
    assert gem.zone == "p1:hand" and not s.state.cards[krenko.id].merged
    check(s)


def test_privacy_every_view_mid_decision_and_a_face_down_pile(cards):
    """Nothing hidden appears in any viewer's table while the over / under question is open: Bob's hand stays Bob's, a spectator and
    Alice's opponent see the same public pile, and a pile turned face down is shown to nobody but its controller."""
    import json

    from app.game.visibility import SPECTATOR

    s = build(cards, ["Gemrazer", "Probe Bear"], ["Probe Bolt"])
    bear = put(s, "Probe Bear")
    to_hand(s, "Probe Bolt", "p2")
    spell = to_hand(s, "Gemrazer")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], alt_cost=mutate_key(s, spell))
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "mutate_choice" and d.player == "p1"
    for viewer in ("p1", "p2", SPECTATOR):
        blob = json.dumps(s.view(viewer))
        assert ("Probe Bolt" in blob) == (viewer == "p2")  # Bob's hand card: Bob's alone (nothing leaks in the decision or the log)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["over"])
    settle(s)
    for viewer in ("p1", "p2", SPECTATOR):
        view = json.dumps(s.view(viewer))
        assert '"merged"' in view and view.count("Probe Bear") >= 1  # the public pile, for every viewer
        assert ("Probe Bolt" in view) == (viewer == "p2")
    act(s, "p1", type="face_down", card_ids=[bear.id], face_down=True)  # (730.2f) the merged permanent turned face down
    host = s.state.cards[bear.id]
    assert host.face_down and len(host.merged) == 2
    for viewer in ("p2", SPECTATOR):
        face = s.view(viewer)["cards"][bear.id]
        assert face.get("hidden") and "merged" not in face and "Gemrazer" not in json.dumps(face)  # nothing of the pile
    assert "merged" in s.view("p1")["cards"][bear.id]  # its controller may look at it (708.5)
    check(s)


def test_a_lower_cards_dies_trigger_works_from_the_pile_as_it_last_existed(cards):
    """702.140e + 603.10a: the pile has every ability (Gemrazer's trigger fires although it is underneath); when it dies its
    leaves-the-battlefield abilities look back at all of them; one permanent died, two cards are in the graveyard (730.3)."""
    s = build(cards, ["Gemrazer", "Probe Mourner"], ["Probe Bolt", "Probe Altar"])
    act(s, "p2", type="set_prefs", response="on")
    altar = put(s, "Probe Altar", "p2")
    mourner = put(s, "Probe Mourner")
    mutate(s, "Gemrazer", mourner, over="under", G=3)
    assert altar.id not in s.state.zones["p2:battlefield"]  # Gemrazer's "whenever this creature mutates", from underneath
    assert chars(s, s.state.cards[mourner.id]).name == "Probe Mourner" and pt(s, s.state.cards[mourner.id]) == (1, 1)
    before = len(s.state.zones["p1:hand"])
    bolt = to_hand(s, "Probe Bolt", "p2")
    mana(s, "p2", R=1)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[mourner.id])
    settle(s)
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"]) == ["Gemrazer", "Probe Mourner"]
    assert len(s.state.zones["p1:hand"]) == before + 1  # "When this creature dies, draw a card" (a lower card's ability, 603.10a)
    check(s)


BATTLEMENTS = ("Hanweir Battlements", "", 0, "Land",
               "{T}: Add {C}.\n{R}, {T}: Target creature gains haste until end of turn.\n{3}{R}{R}, {T}: If you both own and control this land and a creature named Hanweir Garrison, exile them, then meld them into Hanweir, the Writhing Township.\n(Melds with Hanweir Garrison.)",
               (None, None), "")
GARRISON = ("Hanweir Garrison", "{2}{R}", 3, "Creature — Human Soldier",
            "Whenever this creature attacks, create two 1/1 red Human creature tokens that are tapped and attacking.\n(Melds with Hanweir Battlements.)", ("2", "3"), "R")
HANWEIR = ("Hanweir, the Writhing Township", "", 0, "Legendary Creature — Eldrazi Ghoul",
           "Trample, haste\nWhenever Hanweir attacks, create two 3/2 colorless Eldrazi Horror creature tokens that are tapped and attacking.", ("7", "4"), "R")
URZA_LP = ("Urza, Lord Protector", "{1}{W}{U}", 3, "Legendary Creature — Human Artificer",
           "Artifact, instant, and sorcery spells you cast cost {1} less to cast.\n{7}: If you both own and control Urza, Lord Protector and an artifact named The Mightstone and Weakstone, exile them, then meld them into Urza, Planeswalker. Activate only as a sorcery.",
           ("2", "4"), "WU")
MIGHTSTONE = ("The Mightstone and Weakstone", "{5}", 5, "Legendary Artifact — Powerstone",
              "When The Mightstone and Weakstone enters, choose one —\n• Draw two cards.\n• Target creature gets -5/-5 until end of turn.\n{T}: Add {C}{C}. This mana can't be spent to cast nonartifact spells.\n(Melds with Urza, Lord Protector.)",
              (None, None), "")
URZA_PW = ("Urza, Planeswalker", "", 0, "Legendary Planeswalker — Urza",
           "You may activate the loyalty abilities of Urza twice each turn rather than only once.\n+2: Artifact, instant, and sorcery spells you cast this turn cost {2} less to cast. You gain 2 life.\n+1: Draw two cards, then discard a card.\n0: Create two 1/1 colorless Soldier artifact creature tokens.\n−3: Exile target nonland permanent.",
           (None, None), "WU")
MELD_CARDS2 = [*meld_set(GARRISON, BATTLEMENTS, HANWEIR), *meld_set(URZA_LP, MIGHTSTONE, URZA_PW)]
EXTRA.extend(MELD_CARDS2)


def activate(s, c, needle, pid="p1", **kw):
    idx = next(a.index for a in chars(s, c).abilities if needle in a.text)
    act(s, pid, type="activate_ability", card_id=c.id, ability=idx, **kw)
    settle(s)


def test_meld_by_an_activated_ability_of_a_land(cards):
    """701.42a: Hanweir Battlements' ability exiles it and Hanweir Garrison and melds them: one permanent, a creature."""
    s = build(cards, ["Hanweir Battlements", "Hanweir Garrison"])
    battlements, garrison = put(s, "Hanweir Battlements"), put(s, "Hanweir Garrison")
    mana(s, R=5)
    activate(s, battlements, "meld them")
    host = s.state.cards[battlements.id]
    assert garrison.id not in s.state.cards and host.melded and host.zone == "p1:battlefield"
    assert host.name == "Hanweir, the Writhing Township" and pt(s, host) == (7, 4) and chars(s, host).is_creature and not chars(s, host).is_land
    assert chars(s, host).mana_value == 3  # 202.3c: the sum of the front faces' mana values ({2}{R} and a land)
    check(s)


def test_meld_without_the_partner_never_happens_and_the_cost_isnt_wasted_silently(cards):
    s = build(cards, ["Hanweir Battlements", "Hanweir Garrison"])
    battlements = put(s, "Hanweir Battlements")
    mana(s, R=5)
    activate(s, battlements, "meld them")  # 608.2c: the condition isn't true: nothing happens (the cost was paid)
    assert not s.state.cards[battlements.id].melded
    check(s)


def test_meld_into_a_planeswalker_enters_with_its_loyalty_at_sorcery_speed(cards):
    s = build(cards, ["Urza, Lord Protector", "The Mightstone and Weakstone"])
    urza, stone = put(s, "Urza, Lord Protector"), put(s, "The Mightstone and Weakstone")
    mana(s, W=7)
    activate(s, urza, "meld them")
    host = s.state.cards[urza.id]
    assert stone.id not in s.state.cards and host.melded and host.name == "Urza, Planeswalker"
    assert "Planeswalker" in chars(s, host).types and host.counters.get("loyalty") == 7  # 306.5b: it enters with its loyalty
    assert chars(s, host).mana_value == 8
    check(s)
