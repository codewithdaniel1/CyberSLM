from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeSyncManager:
    """Owns the single background knowledge rebuild allowed by the local API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "id": None,
            "status": "idle",
            "phase": None,
            "message": "No knowledge synchronization is running.",
            "completed": 0,
            "total": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def start(self, worker: Callable[[Callable[..., None]], None]) -> dict[str, Any] | None:
        with self._lock:
            if self._state["status"] == "running":
                return None
            job_id = uuid.uuid4().hex
            self._state = {
                "id": job_id,
                "status": "running",
                "phase": "starting",
                "message": "Starting verified knowledge synchronization…",
                "completed": 0,
                "total": 0,
                "started_at": utc_now(),
                "finished_at": None,
                "error": None,
            }

        def run() -> None:
            try:
                worker(self.update)
            except Exception as exc:
                self.update(
                    status="failed",
                    message="Knowledge synchronization failed.",
                    error=f"{type(exc).__name__}: {exc}",
                    finished_at=utc_now(),
                )
            else:
                self.update(
                    status="complete",
                    phase="complete",
                    message="Knowledge index is verified and ready.",
                    error=None,
                    finished_at=utc_now(),
                )

        threading.Thread(target=run, name=f"knowledge-sync-{job_id[:8]}", daemon=True).start()
        return self.status()
