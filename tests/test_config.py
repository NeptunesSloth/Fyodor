import textwrap

import pytest

from fyodor.config import ConfigError, load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return p


def test_loads_full_config(tmp_path):
    p = _write(tmp_path, """
        thresholds: {min_profit: 20, min_roi: 0.3}
        risk: {max_spend_per_day: 500, category_blacklist: [tickets]}
        modes: {dry_run: true}
        products:
          - name: Thing
            store_url: https://shop.example.com/
            handle: thing
            desired_quantity: 2
            max_per_customer: 2
            sold_prices: [100, 110]
    """)
    cfg = load_config(p)
    assert cfg.thresholds.min_profit == 20
    assert cfg.risk.max_spend_per_day == 500
    assert "tickets" in cfg.risk.category_blacklist
    assert cfg.modes.dry_run is True
    assert cfg.products[0].store_url == "https://shop.example.com"  # trailing slash stripped
    assert cfg.products[0].sold_prices == [100, 110]


def test_poll_floor_enforced(tmp_path):
    p = _write(tmp_path, """
        poll: {min_interval_seconds: 0}
        products:
          - {name: X, store_url: https://x.com, handle: x}
    """)
    cfg = load_config(p)
    assert cfg.poll.min_interval_seconds >= 1


def test_bad_store_url_rejected(tmp_path):
    p = _write(tmp_path, """
        products:
          - {name: X, store_url: not-a-url, handle: x}
    """)
    with pytest.raises(ConfigError):
        load_config(p)


def test_missing_file():
    with pytest.raises(ConfigError):
        load_config("/nonexistent/config.yaml")


def test_empty_products_ok(tmp_path):
    p = _write(tmp_path, "modes: {alert_only: true}\nproducts: []\n")
    cfg = load_config(p)
    assert cfg.products == []
