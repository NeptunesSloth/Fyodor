"""A window profile kept from an older build drops its saved page when the built page changes."""

from app.config import load_settings
from app.launcher import forget_old_page


def _settings(tmp_path, page: str):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(page, encoding="utf-8")
    return load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_ALLOW_NETWORK": "0", "FYODOR_FRONTEND_DIST": str(dist)})


def test_a_new_build_clears_the_window_cache_once(tmp_path):
    profile = tmp_path / "data" / "window"
    cache = profile / "Default" / "Cache"
    cache.mkdir(parents=True)
    (cache / "old").write_text("old page", encoding="utf-8")
    (profile / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    old = _settings(tmp_path, "<script src=assets/index-old.js>")
    assert forget_old_page(profile, old) is True
    assert not cache.exists() and (profile / "Default" / "Preferences").exists()
    cache.mkdir(parents=True)
    assert forget_old_page(profile, old) is False and cache.exists()  # the same build: nothing to forget
    new = _settings(tmp_path, "<script src=assets/index-new.js>")
    assert forget_old_page(profile, new) is True and not cache.exists()
