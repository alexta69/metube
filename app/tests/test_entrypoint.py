"""Tests for the hardened container entrypoint."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "docker-entrypoint.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _prepare_stub_bin(tmp_path: Path) -> Path:
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()

    _write_executable(
        stub_bin / "id",
        """#!/bin/sh
case "$1" in
    -u) echo "${TEST_ID_U:-1000}" ;;
    -g) echo "${TEST_ID_G:-1000}" ;;
    *) exit 1 ;;
esac
""",
    )
    _write_executable(
        stub_bin / "gosu",
        """#!/bin/sh
shift
"$@"
""",
    )
    _write_executable(
        stub_bin / "chown",
        """#!/bin/sh
echo "$@" >> "${CHOWN_LOG}"
exit 0
""",
    )
    _write_executable(
        stub_bin / "python3",
        """#!/bin/sh
echo "$@" >> "${PYTHON_LOG}"
exit 0
""",
    )
    _write_executable(
        stub_bin / "bgutil-pot",
        """#!/bin/sh
echo "$@" >> "${BGUTIL_LOG}"
exit 0
""",
    )
    return stub_bin


def _base_env(tmp_path: Path) -> dict[str, str]:
    download_dir = tmp_path / "downloads"
    state_dir = tmp_path / "state"
    temp_dir = tmp_path / "temp"
    download_dir.mkdir(exist_ok=True)
    state_dir.mkdir(exist_ok=True)
    temp_dir.mkdir(exist_ok=True)

    return {
        "DOWNLOAD_DIR": str(download_dir),
        "STATE_DIR": str(state_dir),
        "TEMP_DIR": str(temp_dir),
        "PUID": "1000",
        "PGID": "1000",
        "UMASK": "022",
        "CHOWN_DIRS": "true",
    }


def _run_entrypoint(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    stub_bin = _prepare_stub_bin(tmp_path)
    env = os.environ.copy()
    env.update(_base_env(tmp_path))
    env.update(
        {
            "PATH": f"{stub_bin}:{env['PATH']}",
            "CHOWN_LOG": str(tmp_path / "chown.log"),
            "PYTHON_LOG": str(tmp_path / "python.log"),
            "BGUTIL_LOG": str(tmp_path / "bgutil.log"),
            "TEST_ID_U": "0",
            "TEST_ID_G": "0",
            "UID": "",
            "GID": "",
        }
    )
    env.update(overrides)
    return subprocess.run(
        ["sh", str(ENTRYPOINT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("PUID", "abc", "PUID must be numeric"),
        ("PGID", "abc", "PGID must be numeric"),
        ("UMASK", "89", "UMASK must be a 3 or 4 digit octal value"),
    ],
)
def test_entrypoint_rejects_invalid_identity_inputs(tmp_path, key, value, expected):
    result = _run_entrypoint(tmp_path, **{key: value})
    assert result.returncode != 0
    assert expected in result.stderr


def test_entrypoint_chowns_only_data_directories(tmp_path):
    result = _run_entrypoint(tmp_path)
    assert result.returncode == 0
    chown_log = (tmp_path / "chown.log").read_text(encoding="utf-8")
    assert "/app" not in chown_log
    assert str(tmp_path / "downloads") in chown_log
    assert str(tmp_path / "state") in chown_log
    assert str(tmp_path / "temp") in chown_log


def test_entrypoint_fails_when_directories_are_not_accessible(tmp_path):
    protected_dir = tmp_path / "state"
    protected_dir.mkdir(exist_ok=True)
    protected_dir.chmod(0)
    try:
        result = _run_entrypoint(tmp_path, CHOWN_DIRS="false")
    finally:
        protected_dir.chmod(0o700)
    assert result.returncode != 0
    assert "Configured directories are not accessible" in result.stderr
