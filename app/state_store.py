from __future__ import annotations

import base64
import collections.abc
import errno
import json
import logging
import os
import shelve
import tempfile
import time
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger("state_store")

STATE_SCHEMA_VERSION = 2
_BYTES_MARKER = "__metube_bytes__"
_DATETIME_MARKER = "__metube_datetime__"

# Errnos that signal the filesystem cannot support the temp-file + rename
# atomic-write strategy (for example an NFS-backed state dir returning EPERM on
# mkstemp). These are safe to fall back on because they mean the atomic
# mechanism is unavailable, not that the data write itself failed. Errors like
# ENOSPC/EIO are deliberately excluded so a genuine storage failure surfaces
# instead of silently truncating an existing good state file.
_ATOMIC_UNSUPPORTED_ERRNOS = frozenset(
    e
    for e in (
        errno.EPERM,
        errno.EACCES,
        errno.ENOSYS,
        errno.EINVAL,
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOTSUP", None),
    )
    if e is not None
)


def to_json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {_BYTES_MARKER: base64.b64encode(value).decode("ascii")}
    if isinstance(value, datetime):
        return {_DATETIME_MARKER: value.isoformat()}
    if isinstance(value, collections.abc.Mapping):
        return {str(k): to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_compatible(v) for v in value]
    if isinstance(value, collections.abc.Iterable):
        return [to_json_compatible(v) for v in value]
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable")


def from_json_compatible(value: Any) -> Any:
    if isinstance(value, list):
        return [from_json_compatible(v) for v in value]
    if isinstance(value, dict):
        if set(value.keys()) == {_BYTES_MARKER}:
            return base64.b64decode(value[_BYTES_MARKER].encode("ascii"))
        if set(value.keys()) == {_DATETIME_MARKER}:
            return datetime.fromisoformat(value[_DATETIME_MARKER])
        return {k: from_json_compatible(v) for k, v in value.items()}
    return value


def read_legacy_shelf(path: str) -> Optional[list[tuple[Any, Any]]]:
    if not os.path.exists(path):
        return None
    try:
        with shelve.open(path, "r") as shelf:
            return list(shelf.items())
    except Exception as exc:
        log.warning("Could not read legacy shelf at %s: %s", path, exc)
        return None


class AtomicJsonStore:
    def __init__(self, path: str, *, kind: str, schema_version: int = STATE_SCHEMA_VERSION):
        self.path = path
        self.kind = kind
        self.schema_version = schema_version
        self._direct_write_fallback_warned = False

    def _ensure_parent(self) -> None:
        parent = os.path.dirname(self.path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

    def _build_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "kind": self.kind,
        }
        payload.update(data)
        return payload

    def load(self) -> Optional[dict[str, Any]]:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                raise ValueError("State file must contain a JSON object")
            if payload.get("kind") != self.kind:
                raise ValueError(
                    f"State file kind mismatch: expected {self.kind}, got {payload.get('kind')}"
                )
            return payload
        except Exception as exc:
            self.quarantine_invalid_file(exc)
            return None

    def save(self, data: dict[str, Any]) -> None:
        self._ensure_parent()
        payload = self._build_payload(data)
        try:
            self._atomic_write(payload)
        except OSError as exc:
            if exc.errno not in _ATOMIC_UNSUPPORTED_ERRNOS:
                raise
            self._warn_direct_write_fallback(exc)
            self._direct_write(payload)

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        text = self._serialize(payload)
        parent = os.path.dirname(self.path) or "."
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(self.path)}.",
            suffix=".tmp",
            dir=parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                self._best_effort_fsync(f.fileno())
            os.replace(tmp_path, self.path)
            self._fsync_directory(parent)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def _direct_write(self, payload: dict[str, Any]) -> None:
        # Serialize before truncating so a serialization failure never destroys
        # the existing state file (the atomic path gets this for free via its
        # temp file).
        text = self._serialize(payload)
        # Create with 0o600 so the fallback keeps the owner-only permissions the
        # atomic path gets from mkstemp; state files can contain URLs and
        # per-download option overrides that must not leak on shared mounts.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            # The 0o600 mode above only applies when the file is created; force
            # it on rewrites too so an existing, broadly-permissioned state file
            # is tightened to match the atomic path. Best-effort because some
            # network filesystems reject chmod, and that must not re-crash save.
            try:
                os.fchmod(f.fileno(), 0o600)
            except OSError:
                pass
            f.write(text)
            f.flush()
            self._best_effort_fsync(f.fileno())

    @staticmethod
    def _best_effort_fsync(fileno: int) -> None:
        # Tolerate fsync being unsupported on the underlying filesystem (for
        # example a network mount that returns EINVAL/ENOSYS), but let genuine
        # storage failures such as ENOSPC/EIO surface so a non-durable write is
        # never reported as success. An unsupported fsync must not by itself
        # abandon the atomic rename path.
        try:
            os.fsync(fileno)
        except OSError as exc:
            if exc.errno not in _ATOMIC_UNSUPPORTED_ERRNOS:
                raise

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    def _warn_direct_write_fallback(self, exc: OSError) -> None:
        if self._direct_write_fallback_warned:
            return
        self._direct_write_fallback_warned = True
        log.warning(
            "Atomic state write failed for %s (%s); falling back to direct write",
            self.path,
            exc,
        )

    def quarantine_invalid_file(self, exc: Exception) -> None:
        if not os.path.exists(self.path):
            return
        ts = time.strftime("%Y%m%d%H%M%S")
        backup_path = f"{self.path}.invalid.{ts}"
        try:
            os.replace(self.path, backup_path)
            log.warning(
                "State file at %s was invalid (%s); moved it to %s",
                self.path,
                exc,
                backup_path,
            )
        except OSError as move_exc:
            log.warning(
                "State file at %s was invalid (%s) and could not be moved aside: %s",
                self.path,
                exc,
                move_exc,
            )

    @staticmethod
    def _fsync_directory(path: str) -> None:
        try:
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            fd = os.open(path, flags)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
