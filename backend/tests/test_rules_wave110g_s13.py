"""Wave 110G session 13: Roar of Jukai (702.47a splice; 118.1 "An opponent gains 5 life" is a cost paid as an additional cost)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave110b_kit import ch

SPLICE = " (As you cast an Arcane spell, you may reveal this card from your hand and pay its splice cost. If you do, add this card's effects to that spell.)"
EXTRA = [
    real("Roar of Jukai", "{1}{G}", 2, "Instant", "If you control a Forest, each blocked creature gets +2/+2 until end of turn.\nSplice onto Arcane—An opponent gains 5 life." + SPLICE, None, "G"),
    real("Kodama's Might", "{G}", 1, "Instant — Arcane", "Target creature gets +2/+2 until end of turn.\nSplice onto Arcane {G}" + SPLICE, None, "G"),
    real("Raging River", "{R}{G}", 2, "Enchantment", "Whenever one or more creatures you control attack, each defending player divides all creatures without flying they control into a \"left\" pile and a \"right\" pile. Then, for each attacking creature you control, choose \"left\" or \"right.\" That creature can't be blocked this combat except by creatures with flying and creatures in a pile with the chosen label.", None, "GR"),
    real("Spellweaver Volute", "{1}{U}", 2, "Enchantment \u2014 Aura", "Enchant instant card in a graveyard\nWhenever you cast a sorcery spell, copy the enchanted instant card. You may cast the copy without paying its mana cost. If you do, exile the enchanted card and attach this Aura to another instant card in a graveyard.", None, "U"),
    real("Test Shock", "{R}", 1, "Instant", "Test Shock deals 2 damage to any target.", None, "R"),
    real("Test Jolt", "{U}", 1, "Instant", "Target player loses 3 life.", None, "U"),
    real("Test Tonic", "{1}", 1, "Sorcery", "You gain 1 life.", None, ""),
    real("Pygmy Hippo", "{1}{G}{U}", 3, "Creature \u2014 Hippopotamus", "Whenever this creature attacks and isn't blocked, you may have defending player activate a mana ability of each land they control and lose all unspent mana. If you do, this creature assigns no combat damage this turn and at the beginning of your next main phase this turn, you add an amount of {C} equal to the amount of mana that player lost this way.", ("2", "2"), "GU"),
    real("Test Filter", "", 0, "Land", "{1}, {T}: Add {G}{G}.", None, ""),
    real("Test Dual", "", 0, "Land", "{T}: Add {W} or {U}.", None, ""),
    real("Sky Hawk", "{2}{U}", 3, "Creature \u2014 Bird", "Flying", ("1", "1"), "U"),
    real("Bear Cub", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Roar of Jukai", "Raging River", "Spellweaver Volute", "Pygmy Hippo"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("forest", [True, False])
def test_roar_spliced_onto_arcane_gives_opponent_life_and_pumps_blocked(cards, forest):
    s = build(cards, ["Bear Cub", "Kodama's Might", "Roar of Jukai", "Forest"], ["Bear Cub"])
    atk, blk = put(s, "Bear Cub"), put(s, "Bear Cub", "p2")
    if forest:
        put(s, "Forest")
    might, roar = to_hand(s, "Kodama's Might"), to_hand(s, "Roar of Jukai")
    s.state.rules.controlled_since[atk.id].turn = 0
    act(s, "p1", type="pass_priority")
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atk.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blk.id, "attacker_id": atk.id}])
    mana(s, G=2)
    life = s.state.players["p2"].life
    act(s, "p1", type="cast_spell", card_id=might.id, splice=[roar.id], targets=[atk.id], target_counts=[1])
    assert s.state.cards[roar.id].zone == "p1:hand" and s.state.players["p2"].life == life + 5  # 702.47a: cost paid at cast, card stays in hand
    for _ in range(10):
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # Might +2/+2 on the attacker; Roar +2/+2 on each blocked creature (the attacker is blocked) if a Forest is controlled
    assert ch(s, atk).pt == ((6, 6) if forest else (4, 4))
    check(s)


def _decide(s, player, ids):
    d = s.state.rules.decision
    assert d is not None and d.player == player, d
    act(s, player, type="choose", decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize("label, flier", [("left", False), ("right", False), ("left", True)])
def test_raging_river_piles_limit_blockers(cards, label, flier):
    """508.5 / 509.1b: Bob's left pile is B1; the chosen label decides which ground blocker may block; a flier always may."""
    s = build(cards, ["Raging River", "Bear Cub"], ["Bear Cub", "Grizzly Bears", "Sky Hawk"])
    put(s, "Raging River")
    atk, b1, b2 = put(s, "Bear Cub"), put(s, "Bear Cub", "p2"), put(s, "Grizzly Bears", "p2")
    hawk = put(s, "Sky Hawk", "p2")
    s.state.rules.controlled_since[atk.id].turn = 0
    act(s, "p1", type="pass_priority")
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atk.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")  # the trigger resolves
    act(s, "p2", type="pass_priority")
    _decide(s, "p2", [b1.id])  # left pile: B1 (the flier isn't divided)
    _decide(s, "p1", [label])
    ok, bad = (b1, b2) if label == "left" else (b2, b1)
    for p in ("p1", "p2"):
        if s.state.rules.priority == p:
            act(s, p, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bad.id, "attacker_id": atk.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": (hawk if flier else ok).id, "attacker_id": atk.id}])
    check(s)


def _volute(cards, shocks=("Test Shock",)):
    """Alice's Volute enchants Test Shock (in her graveyard); other instants in `shocks` sit in a graveyard too."""
    s = build(cards, ["Spellweaver Volute", "Test Tonic", *shocks], [])
    vol = to_hand(s, "Spellweaver Volute")
    shock = card_named(s, "Test Shock", "p1")
    for n in shocks:
        c = card_named(s, n, "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=vol.id, targets=[shock.id])
    _drain(s)
    return s, vol, shock


def _drain(s, first=None, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options][: max(1, d.min_choices)]
            if first and any(f in [o.id for o in d.options] for f in first):
                ids = [next(f for f in first if f in [o.id for o in d.options])]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_volute_enchants_a_graveyard_instant_and_only_that(cards):
    """303.4a / 704.5m: it enchants an instant card in a graveyard; the Aura stays while the card is still there."""
    s, vol, shock = _volute(cards)
    assert s.state.cards[vol.id].zone == "p1:battlefield"
    check(s)


def test_volute_copy_cast_exiles_the_card_and_moves_to_another_instant(cards):
    s, vol, shock = _volute(cards, ("Test Shock", "Test Jolt"))
    jolt = card_named(s, "Test Jolt", "p1")
    tonic = to_hand(s, "Test Tonic")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=tonic.id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            opts = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o for o in opts if o in ("yes", shock.id, "p2", jolt.id)), opts[0])])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.players["p2"].life == 38  # the copy of Test Shock (cast free) hit Bob
    assert s.state.cards[shock.id].zone == "p1:exile"  # the enchanted card is exiled
    assert s.state.cards[vol.id].zone == "p1:battlefield"
    assert s.state.rules.aura_links[s.state.rules.object_id(vol.id)] == [s.state.rules.object_id(jolt.id)]  # attached to the other instant
    check(s)


def _tonic(s, answers):
    """Cast Test Tonic; each decision takes the first of `answers` among its options (else the first option)."""
    tonic = to_hand(s, "Test Tonic")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=tonic.id)
    for _ in range(14):
        d = s.state.rules.decision
        if d is not None:
            opts = [o.id for o in d.options]
            pick = [] if "none" in answers and d.min_choices == 0 else [next((o for a in answers for o in opts if o == a), opts[0])]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break



def test_volute_declined_cast_changes_nothing(cards):
    s, vol, shock = _volute(cards)
    _tonic(s, ["none"])
    assert s.state.players["p2"].life == 40 and s.state.cards[shock.id].zone == "p1:graveyard" and s.state.cards[vol.id].zone == "p1:battlefield"
    check(s)


def test_volute_with_no_other_instant_falls_off(cards):
    s, vol, shock = _volute(cards)
    _tonic(s, ["yes", shock.id, "p2"])
    assert s.state.cards[shock.id].zone == "p1:exile" and s.state.cards[vol.id].zone == "p1:graveyard"  # 704.5m: nothing left to enchant
    check(s)


def test_volute_cannot_enchant_a_sorcery_card(cards):
    s = build(cards, ["Spellweaver Volute", "Test Tonic"], [])
    vol, tonic = to_hand(s, "Spellweaver Volute"), card_named(s, "Test Tonic", "p1")
    act(s, "p1", type="move", card_ids=[tonic.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, U=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=vol.id, targets=[tonic.id])


def _c(s):
    """Alice's unspent {C} (the mana of her Hippo is tracked as units)."""
    p = s.state.players["p1"]
    return p.mana.get("C", 0) + sum(u.sym == "C" for u in p.mana_units)


def _hippo(cards, lands, accept=True, floating=0, picks=(), tapped=()):
    """Alice's Hippo attacks unblocked; Bob controls `lands` (and has `floating` {R} in his pool). Returns the table in Alice's second main phase."""
    s = build(cards, ["Pygmy Hippo"], lands)
    hippo = put(s, "Pygmy Hippo")
    for n in lands:
        put(s, n, "p2")
    s.state.rules.controlled_since[hippo.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hippo.id, "target": "p2"}])
    if floating:  # unspent mana of Bob's, with the Hippo trigger on the stack
        mana(s, "p2", R=floating)
    for n in tapped:
        act(s, "p2", type="tap", card_ids=[card_named(s, n, "p2").id])
    asked = list(picks)
    for _ in range(60):
        if s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        if d is not None:
            opts = [o.id for o in d.options]
            if d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            elif set(opts) >= {"yes", "no"}:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if accept else "no"])
            else:
                want = asked.pop(0) if asked else None
                pick = next((o for o in opts if want and want in o), opts[0])
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(6):  # the delayed mana trigger of the main phase
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_pygmy_hippo_drains_all_of_defenders_mana_and_adds_it_later(cards):
    """605.3a / 106.4: each land is activated, the pool (2 lands + 1 floating) is lost: Hippo deals no damage and Alice gets {C}{C}{C} in main phase 2."""
    s = _hippo(cards, ["Forest", "Island"], floating=1)
    assert s.state.players["p2"].life == 40 and not any(s.state.players["p2"].mana.values())
    assert _c(s) == 3
    check(s)


def test_pygmy_hippo_declined_deals_damage(cards):
    s = _hippo(cards, ["Forest"], accept=False, floating=2)
    assert s.state.players["p2"].life == 38 and not _c(s)
    check(s)


def test_pygmy_hippo_filter_land_is_paid_from_the_pool_in_the_defenders_order(cards):
    """The Filter land's {1} comes from mana already in the pool: Forest first (G), then the Filter pays it and adds {G}{G}: two mana lost."""
    s = _hippo(cards, ["Forest", "Test Filter"])
    assert _c(s) == 2
    check(s)


def test_pygmy_hippo_dual_land_asks_the_defender_which_mana(cards):
    s = _hippo(cards, ["Test Dual"], picks=["1"])
    assert _c(s) == 1
    check(s)


def test_pygmy_hippo_a_tapped_land_has_no_mana_ability_to_activate(cards):
    s = _hippo(cards, ["Forest", "Island"], tapped=["Island"])
    assert _c(s) == 1
    check(s)
