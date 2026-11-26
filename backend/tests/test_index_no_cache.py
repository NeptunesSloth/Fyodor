"""The built page is revalidated on every load, so a window kept from an older build gets the new page."""

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app


def test_index_is_not_kept_by_the_browser(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Fyodor</title>", encoding="utf-8")
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_ALLOW_NETWORK": "0", "FYODOR_FRONTEND_DIST": str(dist)})
    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-cache"
