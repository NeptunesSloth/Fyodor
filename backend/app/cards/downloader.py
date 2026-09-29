"""Network side of card updates: Scryfall bulk-data download and image caching.

Only the ``tools.update_cards`` command (and the explicit "download images" API action)
use this module. Gameplay never touches the network.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.cards.images import ImageStore

log = logging.getLogger(__name__)

CHUNK = 1 << 16


class DownloadError(RuntimeError):
    pass


@dataclass
class BulkInfo:
    type: str
    updated_at: str
    url: str
    size: int | None


def make_client(user_agent: str, timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json;q=0.9,*/*;q=0.8"},
        timeout=httpx.Timeout(timeout, connect=15.0),
        follow_redirects=True,
    )


def fetch_bulk_info(client: httpx.Client, api_base: str, bulk_type: str) -> BulkInfo:
    res = client.get(f"{api_base.rstrip('/')}/bulk-data")
    res.raise_for_status()
    for entry in res.json().get("data", []):
        if entry.get("type") == bulk_type:
            url = entry.get("jsonl_download_uri") or entry.get("download_uri")
            if not url:
                raise DownloadError(f"bulk entry {bulk_type} has no download URI")
            return BulkInfo(
                type=bulk_type,
                updated_at=str(entry.get("updated_at", "")),
                url=str(url),
                size=entry.get("compressed_size") or entry.get("size"),
            )
    raise DownloadError(f"Scryfall does not list a bulk file of type {bulk_type!r}")


def download_file(
    client: httpx.Client, url: str, dest: Path, *, progress: Callable[[int, int | None], None] | None = None
) -> Path:
    """Download ``url`` to ``dest``, resuming a previous ``.part`` file when the server allows it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return dest
    part = dest.with_name(dest.name + ".part")
    offset = part.stat().st_size if part.is_file() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with client.stream("GET", url, headers=headers) as res:
        if res.status_code == 416:  # already complete
            part.rename(dest)
            return dest
        if res.status_code not in (200, 206):
            raise DownloadError(f"GET {url} -> HTTP {res.status_code}")
        if res.status_code == 200 and offset:
            log.info("Server ignored resume request; restarting download")
            offset = 0
        total_header = res.headers.get("Content-Length")
        total = int(total_header) + offset if total_header else None
        done = offset
        with part.open("ab" if offset else "wb") as fh:
            for chunk in res.iter_bytes(CHUNK):
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    part.rename(dest)
    return dest


@dataclass
class ImageJob:
    card_id: str
    is_token: bool
    faces: list[dict[str, str]]


@dataclass
class ImageReport:
    requested: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def download_images(
    client: httpx.Client,
    store: ImageStore,
    jobs: Iterable[ImageJob],
    *,
    size: str = "normal",
    workers: int = 8,
    progress: Callable[[ImageReport], None] | None = None,
) -> ImageReport:
    """Download missing images. Existing files are skipped; partial files are retried."""
    report = ImageReport()
    lock = threading.Lock()
    tasks: list[tuple[Path, str]] = []
    for job in jobs:
        for face, uris in enumerate(job.faces):
            url = uris.get(size) or uris.get("normal") or uris.get("large")
            if not url:
                continue
            report.requested += 1
            path = store.path_for(job.card_id, face=face, size=size, is_token=job.is_token)
            if path.is_file():
                report.skipped += 1
            else:
                tasks.append((path, url))

    def fetch(path: Path, url: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        res = client.get(url)
        if res.status_code != 200:
            raise DownloadError(f"HTTP {res.status_code}")
        tmp.write_bytes(res.content)
        tmp.replace(path)

    if progress:
        progress(report)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch, path, url): (path, url) for path, url in tasks}
        for future in as_completed(futures):
            path, url = futures[future]
            with lock:
                try:
                    future.result()
                    report.downloaded += 1
                except (httpx.HTTPError, DownloadError, OSError) as exc:
                    report.failed += 1
                    if len(report.errors) < 20:
                        report.errors.append(f"{path.name}: {exc}")
                    log.warning("Image download failed for %s: %s", url, exc)
                if progress:
                    progress(report)
    return report


def image_jobs_from_rows(rows: Iterable[Any]) -> list[ImageJob]:
    import json

    jobs = []
    for row in rows:
        if row["image_uris"]:
            faces = [json.loads(row["image_uris"])]
        else:
            faces = [f.get("image_uris") for f in json.loads(row["card_faces"] or "[]") if f.get("image_uris")]
        if faces:
            jobs.append(ImageJob(card_id=row["id"], is_token=bool(row["is_token"]), faces=faces))
    return jobs
