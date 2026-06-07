"""Notifications: console, Discord, Telegram, and email — with dedupe + logging."""

from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage

import requests

from .config import NotifyConfig

log = logging.getLogger("fyodor.notify")

_LEVEL_COLORS = {"info": 0x3498DB, "success": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C}


class Notifier:
    def __init__(self, config: NotifyConfig, *, persist: bool = True) -> None:
        self.config = config
        self.persist = persist
        self._recent: dict[str, float] = {}

    # -- public -----------------------------------------------------------

    def send(self, title: str, message: str, *, level: str = "info", dedupe_key: str | None = None) -> bool:
        """Send to all configured channels. Returns False if suppressed by dedupe."""
        if dedupe_key and self._is_duplicate(dedupe_key):
            log.debug("suppressed duplicate alert: %s", dedupe_key)
            return False

        if self.config.console:
            level_no = logging.WARNING if level in ("warn", "error") else logging.INFO
            log.log(level_no, "%s — %s", title, message)
        if self.config.discord_webhook_url:
            self._discord(title, message, level)
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            self._telegram(title, message)
        if self.config.email_to and self.config.smtp_host:
            self._email(title, message)

        if self.persist:
            self._log_to_db(title, message, level, dedupe_key or "")
        return True

    # -- channels ---------------------------------------------------------

    def _discord(self, title: str, message: str, level: str) -> None:
        payload = {"embeds": [{"title": title[:256], "description": message[:4000],
                               "color": _LEVEL_COLORS.get(level, _LEVEL_COLORS["info"])}]}
        try:
            requests.post(self.config.discord_webhook_url, json=payload, timeout=10).raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network
            log.warning("Discord notification failed: %s", exc)

    def _telegram(self, title: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        text = f"*{title}*\n{message}"
        try:
            requests.post(
                url,
                json={"chat_id": self.config.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            ).raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network
            log.warning("Telegram notification failed: %s", exc)

    def _email(self, title: str, message: str) -> None:  # pragma: no cover - network
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = self.config.smtp_user or self.config.email_to
        msg["To"] = self.config.email_to
        msg.set_content(message)
        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=15) as s:
                s.starttls()
                if self.config.smtp_user:
                    s.login(self.config.smtp_user, self.config.smtp_password)
                s.send_message(msg)
        except Exception as exc:  # noqa: BLE001
            log.warning("Email notification failed: %s", exc)

    # -- helpers ----------------------------------------------------------

    def _is_duplicate(self, key: str) -> bool:
        now = time.time()
        window = self.config.dedupe_minutes * 60
        # prune
        self._recent = {k: t for k, t in self._recent.items() if now - t < window}
        if key in self._recent:
            return True
        self._recent[key] = now
        return False

    def _log_to_db(self, title: str, message: str, level: str, dedupe_key: str) -> None:
        try:
            from .db import session_scope
            from .models import AlertLog

            with session_scope() as s:
                s.add(AlertLog(title=title[:300], body=message, level=level, dedupe_key=dedupe_key[:200]))
        except Exception as exc:  # noqa: BLE001 - never let logging break alerting
            log.debug("could not persist alert: %s", exc)
