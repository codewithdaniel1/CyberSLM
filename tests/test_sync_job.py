import threading
import time

from cyberslm.knowledge.sync_job import KnowledgeSyncManager


def test_sync_job_reports_completion() -> None:
    manager = KnowledgeSyncManager()
    finished = threading.Event()

    def worker(update) -> None:
        update(phase="sources", completed=1, total=1, message="Indexed source")
        finished.set()

    started = manager.start(worker)
    assert started is not None
    assert finished.wait(timeout=2)
    deadline = time.monotonic() + 2
    while manager.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.001)
    assert manager.status()["status"] == "complete"


def test_sync_job_prevents_concurrent_rebuilds() -> None:
    manager = KnowledgeSyncManager()
    release = threading.Event()

    def worker(update) -> None:
        release.wait(timeout=2)

    assert manager.start(worker) is not None
    assert manager.start(worker) is None
    release.set()
