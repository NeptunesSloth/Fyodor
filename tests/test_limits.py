from fyodor.limits import clamp_quantity, detect_limit_from_text


def test_buys_up_to_limit_not_over():
    # "if only 2 per customer, buy 2" — and never more.
    d = clamp_quantity(5, detected_limit=2)
    assert d.quantity == 2
    assert "limit" in d.reason


def test_respects_desired_when_below_limit():
    d = clamp_quantity(1, detected_limit=2)
    assert d.quantity == 1
    assert d.reason == "desired"


def test_most_restrictive_cap_wins():
    d = clamp_quantity(10, detected_limit=5, configured_cap=3, variant_available_qty=2)
    assert d.quantity == 2
    assert d.reason == "available stock"


def test_zero_when_nothing_available():
    d = clamp_quantity(3, variant_available_qty=0)
    assert d.quantity == 0


def test_detect_limit_phrasings():
    assert detect_limit_from_text("Limit 2 per customer") == 2
    assert detect_limit_from_text("Maximum 3 per person") == 3
    assert detect_limit_from_text("4 per household limit") == 4
    assert detect_limit_from_text("no limit mentioned") is None


def test_detect_limit_picks_smallest():
    assert detect_limit_from_text("limit 5 per order, max 2 per customer") == 2
