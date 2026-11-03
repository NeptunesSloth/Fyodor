"""Tiny background-job runner for slow, optional work (e.g. caching deck artwork).

Jobs run on a small thread pool, report progress through a shared dict, and never touch
game state. Results are kept in memory for the life of the server.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

MAX_KEPT = 50


@dataclass
class Job:
    id: str
    kind: str
    label: str
    state: str = "running"  # running | done | failed
    done: int = 0
    total: int = 0
    failed: int = 0
    message: str = ""
    phase: str = ""  # what a multi-step job is doing now ("Downloading", "Importing" …)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "state": self.state,
            "done": self.done,
            "total": self.total,
            "failed": self.failed,
            "message": self.message,
            "phase": self.phase,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ProgressFn(Protocol):
    def __call__(self, done: int, total: int, failed: int, phase: str | None = None) -> None: ...


class JobManager:
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fyodor-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, label: str, work: Callable[[ProgressFn], str]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label)
        with self._lock:
            self._jobs[job.id] = job
            if len(self._jobs) > MAX_KEPT:
                for old in sorted(self._jobs.values(), key=lambda j: j.started_at)[: len(self._jobs) - MAX_KEPT]:
                    if old.state != "running":
                        del self._jobs[old.id]

        def progress(done: int, total: int, failed: int, phase: str | None = None) -> None:
            job.done, job.total, job.failed = done, total, failed
            if phase is not None:
                job.phase = phase

        def run() -> None:
            try:
                job.message = work(progress)
                job.state = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the user through the job status
                log.exception("Job %s (%s) failed", job.id, kind)
                job.state = "failed"
                job.message = str(exc) or exc.__class__.__name__
            finally:
                job.finished_at = time.time()

        self._pool.submit(run)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def latest(self, kind: str) -> Job | None:
        """The newest job of a kind (running or finished), e.g. the card update a reloaded Settings page should show."""
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.kind == kind]
        return max(jobs, key=lambda j: j.started_at, default=None)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
