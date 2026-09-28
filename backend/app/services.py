"""Service container: owns long-lived resources (DB connections, game hub)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import Settings
from app.storage.app_db import open_app_db

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings

    def __post_init__(self) -> None:
        self.settings.ensure_dirs()
        self.app_db = open_app_db(self.settings.app_db_path)

    def health(self) -> dict[str, object]:
        return {"data_dir": str(self.settings.data_dir)}

    def close(self) -> None:
        self.app_db.close()
