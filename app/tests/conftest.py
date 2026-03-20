"""Pytest configuration: set env and filesystem layout before importing ``main``."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _ensure_test_env() -> None:
    if os.environ.get("METUBE_TEST_ENV_READY"):
        return
    tmp = tempfile.mkdtemp(prefix="metube-pytest-")
    base = Path(tmp)
    browser = base / "ui" / "dist" / "metube" / "browser"
    browser.mkdir(parents=True)
    (browser / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
    dl = base / "downloads"
    st = base / "state"
    dl.mkdir(parents=True)
    st.mkdir(parents=True)
    os.environ["DOWNLOAD_DIR"] = str(dl)
    os.environ["STATE_DIR"] = str(st)
    os.environ["TEMP_DIR"] = str(dl)
    os.environ["YTDL_OPTIONS"] = "{}"
    os.environ["YTDL_OPTIONS_FILE"] = ""
    os.environ["BASE_DIR"] = str(base)
    os.environ["LOGLEVEL"] = "INFO"
    os.environ["METUBE_TEST_ENV_READY"] = "1"


_ensure_test_env()
