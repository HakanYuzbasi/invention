"""File-based run lock to prevent concurrent runs from corrupting state."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from ..errors import LockHeldError
from ..logging_config import get_logger

log = get_logger(__name__)


class RunLock:
    """A best-effort exclusive lock backed by an ``O_CREAT | O_EXCL`` file.

    Stale-lock handling: if the recorded PID is no longer alive, the lock is
    reclaimed. This avoids a crashed run wedging the system permanently.
    """

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._acquired = False

    def acquire(self) -> "RunLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists() and self._is_stale():
            log.warning("Reclaiming stale lock at %s", self.lock_path)
            self.lock_path.unlink(missing_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as e:
            raise LockHeldError(f"Another run holds the lock: {self.lock_path}") from e
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        self._acquired = True
        log.debug("Acquired run lock %s (pid=%s)", self.lock_path, os.getpid())
        return self

    def _is_stale(self) -> bool:
        try:
            pid = int(self.lock_path.read_text().strip() or "0")
        except (ValueError, OSError):
            return True
        if pid <= 0:
            return True
        try:
            os.kill(pid, 0)  # signal 0 == existence check
        except ProcessLookupError:
            return True
        except PermissionError:
            return False  # exists but owned by another user
        return False

    def release(self) -> None:
        if self._acquired:
            self.lock_path.unlink(missing_ok=True)
            self._acquired = False
            log.debug("Released run lock %s", self.lock_path)

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
