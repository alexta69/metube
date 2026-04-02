from __future__ import annotations

import base64
import collections.abc
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
        parent = os.path.dirname(self.path) or "."
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(self.path)}.",
            suffix=".tmp",
            dir=parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
            self._fsync_directory(parent)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

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
