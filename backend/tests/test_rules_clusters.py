"""Clustering the unsupported Oracle text into reusable capabilities (coverage report analysis)."""

from __future__ import annotations

from app.rules import clusters as K
from app.rules import pool


def card(name, type_line, *, text="", cost="{1}", layout="normal", faces=None, power=None, toughness=None, oid=None):
    return {"name": name, "type_line": type_line, "mana_cost": cost, "oracle_text": text, "colors": [], "faces": faces or [],
            "power": power, "toughness": toughness, "legalities": {"commander": "legal"}, "layout": layout,
            "oracle_id": oid or name, "id": f"id-{name}"}


def test_categories():
    assert K.classify("keyword:banding", "Banding", "keyword", "X") == (K.MECHANIC, "banding")
    assert K.classify("text:0", "Whenever you expend 4, draw a card.", "triggered", "X") == \
        (K.TRIGGER, "Whenever you expend N")
    cat, key = K.classify("text:0", "When Foo enters, destroy target creature with flying.", "triggered", "Foo")
    assert cat == K.SELECTOR and key.startswith("target creature with flying")
    cat, _ = K.classify("text:0", "When Foo enters, you draw two cards and lose 2 life.", "triggered", "Foo")
    assert cat == K.EFFECT
    cat, key = K.classify("text:0", "Foo enters tapped unless you control two or fewer other lands.", "replacement", "Foo")
    assert cat == K.REPLACEMENT and key.startswith("~ enters tapped unless")
    assert K.classify("text:0", "{2}{S}: Draw a card.", "activated", "Foo")[0] == K.COST  # (snow; exert: wave 4H)
    assert K.classify("mana:ability", "{T}, Pay 1 life: Add {B}.", "mana_ability", "Foo")[0] == K.MANA


def test_supported_selectors_are_not_missing():
    assert K.missing_selector("Destroy target creature an opponent controls.") is None
    assert K.missing_selector("Exile target artifact or enchantment.") is None
    assert K.missing_selector("Return target creature card from your graveyard to your hand.") == "target creature card"


def test_report_clusters_and_quality():
    rep = pool.analyse([
        card("Combat A", "Creature — Test", text="Whenever you expend 4, put a +1/+1 counter on "
             "target creature you control.", power="1", toughness="1"),
        card("Combat B", "Creature — Test", text="Whenever you expend 4, draw a card.", power="1",
             toughness="1"),
        card("Bear", "Creature — Bear", power="2", toughness="2"),
    ])
    data = pool.as_json(rep, {})
    top = data["clusters"][0]
    assert top["category"] == K.TRIGGER and top["commander_cards"] == 2 and top["only_missing_piece_for"] == 2
    assert data["categories"][K.TRIGGER] == {"cards": 2, "lines": 2}
    q = data["quality"]
    assert q["unrecognized_clauses"] == 2 and q["unclassified_clauses"] == 0 and q["classified_share"] == "100.0%"
    md = pool.markdown({**data, "commander_legal_cards": 3, "commander_banned": 0})
    assert "## Missing capabilities by category" in md and "## Highest-payoff clusters" in md


def test_split_cards_are_analysed_per_half():
    from app.rules import coverage

    fire_ice = card("Fire // Ice", "Instant // Instant", layout="split",
                    text="Fire deals 2 damage divided as you choose among one or two targets.\n//\nTap target permanent.\nDraw a card.",
                    faces=[{"name": "Fire", "mana_cost": "{1}{R}", "type_line": "Instant",
                            "oracle_text": "Fire deals 2 damage divided as you choose among one or two targets."},
                           {"name": "Ice", "mana_cost": "{1}{U}", "type_line": "Instant",
                            "oracle_text": "Tap target permanent.\nDraw a card."}])
    cov = coverage.of_card_data(fire_ice)
    assert "//" not in {f.label for f in cov.features}
    assert [f.supported for f in cov.features if f.label == "Draw a card."] == [True]
