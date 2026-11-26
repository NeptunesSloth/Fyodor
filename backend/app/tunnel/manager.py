"""The tunnel's state: the loopback port cloudflared forwards to and the public hostname it was given."""

from __future__ import annotations

from typing import Literal

from app.config import Settings

TunnelState = Literal["stopped", "starting", "running", "failed"]


class TunnelManager:
    """``port``: the tunnel port the launcher bound (127.0.0.1, chosen by the OS); None for a server the launcher didn't start
    (``uvicorn --factory``), which then has no tunnel port and cannot share. ``hostname``: the ``*.trycloudflare.com`` name while
    running. Requests that arrive on ``port`` are tunnel requests (app/api/deps.py is_tunnel_request)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.port: int | None = None
        self.hostname: str | None = None
        self.state: TunnelState = "stopped"
        self.reason: str | None = None
