"""HTTP handler and app factory tests for ``main``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from yarl import URL

import main


def _make_settings(tmp_path: Path, **overrides):
    app_root = tmp_path / "app_root"
    browser = app_root / "ui" / "dist" / "metube" / "browser"
    browser.mkdir(parents=True)
    (browser / "index.html").write_text("<html><body></body></html>", encoding="utf-8")

    download_dir = tmp_path / "downloads"
    state_dir = tmp_path / "state"
    temp_dir = tmp_path / "temp"
    download_dir.mkdir()
    state_dir.mkdir()
    temp_dir.mkdir()

    env = {k: str(v) for k, v in main.Config._DEFAULTS.items()}
    env.update(
        {
            "DOWNLOAD_DIR": str(download_dir),
            "AUDIO_DOWNLOAD_DIR": str(download_dir),
            "STATE_DIR": str(state_dir),
            "TEMP_DIR": str(temp_dir),
            "YTDL_OPTIONS": "{}",
            "YTDL_OPTIONS_FILE": "",
            "LOGLEVEL": "INFO",
        }
    )
    env.update({key: str(value) for key, value in overrides.items()})
    return main.Config.from_env(env, app_root=app_root)


@pytest.fixture
def app(tmp_path):
    return main.create_app(_make_settings(tmp_path))


@pytest.fixture
def mock_dqueue(app):
    dqueue = MagicMock()
    dqueue.initialize = AsyncMock(return_value=None)
    dqueue.add = AsyncMock(return_value={"status": "ok"})
    dqueue.cancel = AsyncMock(return_value={"status": "ok"})
    dqueue.clear = AsyncMock(return_value={"status": "ok"})
    dqueue.start_pending = AsyncMock(return_value={"status": "ok"})
    dqueue.cancel_add = MagicMock()
    dqueue.queue = MagicMock()
    dqueue.done = MagicMock()
    dqueue.pending = MagicMock()
    dqueue.queue.saved_items = MagicMock(return_value=[])
    dqueue.done.saved_items = MagicMock(return_value=[])
    dqueue.pending.saved_items = MagicMock(return_value=[])
    dqueue.get = MagicMock(return_value=([], []))
    app[main.DQUEUE_KEY] = dqueue
    return dqueue


def _valid_video_add_body(**kwargs):
    base = {
        "url": "https://example.com/watch?v=1",
        "download_type": "video",
        "codec": "auto",
        "format": "any",
        "quality": "best",
    }
    base.update(kwargs)
    return base


def _request(app, body: dict | None = None):
    req = MagicMock(spec=web.Request)
    req.app = app
    req.headers = {}
    req.cookies = {}
    req.scheme = "http"
    req.host = "localhost:8081"
    req.url = URL("http://localhost:8081/")
    if body is not None:
        req.json = AsyncMock(return_value=body)
    return req


@pytest.mark.asyncio
async def test_add_ok(app, mock_dqueue):
    req = _request(app, _valid_video_add_body())
    resp = await main.add(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["status"] == "ok"
    mock_dqueue.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_missing_url_returns_400(app, mock_dqueue):
    req = _request(app, {"download_type": "video", "quality": "best", "format": "any"})
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)
    mock_dqueue.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_invalid_download_type(app, mock_dqueue):
    req = _request(app, _valid_video_add_body(download_type="invalid"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_video_quality(app, mock_dqueue):
    req = _request(app, _valid_video_add_body(quality="9999"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_subtitle_language(app, mock_dqueue):
    req = _request(
        app,
        {
            "url": "https://example.com/v",
            "download_type": "captions",
            "codec": "auto",
            "format": "srt",
            "quality": "best",
            "subtitle_language": "bad language!",
        },
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_custom_name_prefix_path_traversal(app, mock_dqueue):
    req = _request(app, _valid_video_add_body(custom_name_prefix="../evil"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_chapter_template_path_traversal(app, mock_dqueue):
    req = _request(
        app,
        _valid_video_add_body(
            split_by_chapters=True,
            chapter_template="/etc/passwd%(title)s",
        ),
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_json_body(app, mock_dqueue):
    req = _request(app)
    req.json = AsyncMock(side_effect=json.JSONDecodeError("msg", "", 0))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_delete_missing_ids(app, mock_dqueue):
    req = _request(app, {"where": "queue"})
    with pytest.raises(web.HTTPBadRequest):
        await main.delete(req)


@pytest.mark.asyncio
async def test_delete_queue_calls_cancel(app, mock_dqueue):
    req = _request(app, {"where": "queue", "ids": ["http://x"]})
    resp = await main.delete(req)
    assert resp.status == 200
    mock_dqueue.cancel.assert_awaited_once_with(["http://x"])


@pytest.mark.asyncio
async def test_start_pending(app, mock_dqueue):
    req = _request(app, {"ids": ["a"]})
    resp = await main.start(req)
    assert resp.status == 200
    mock_dqueue.start_pending.assert_awaited_once_with(["a"])


@pytest.mark.asyncio
async def test_history_shape(app, mock_dqueue):
    req = _request(app)
    resp = await main.history(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert set(data.keys()) == {"done", "queue", "pending"}


@pytest.mark.asyncio
async def test_version_json(app, mock_dqueue):
    req = _request(app)
    resp = await main.version(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert "yt-dlp" in body and "version" in body


@pytest.mark.asyncio
async def test_cookie_status(app, mock_dqueue):
    req = _request(app)
    resp = await main.cookie_status(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data.get("status") == "ok"
    assert "has_cookies" in data


@pytest.mark.asyncio
async def test_options_add_cors(app, mock_dqueue):
    req = _request(app)
    resp = await main.add_cors(req)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_upload_cookies_missing_field(app, mock_dqueue):
    req = _request(app)
    reader = MagicMock()
    field = MagicMock()
    field.name = "wrongname"
    reader.next = AsyncMock(side_effect=[field, None])
    req.multipart = AsyncMock(return_value=reader)
    resp = await main.upload_cookies(req)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_add_legacy_format_migrated(app, mock_dqueue):
    req = _request(app, {"url": "https://example.com/v", "format": "m4a", "quality": "best"})
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[1] == "audio"


def test_create_app_registers_state(tmp_path):
    app = main.create_app(_make_settings(tmp_path))
    assert app[main.SETTINGS_KEY].URL_PREFIX == "/"
    assert main.DQUEUE_KEY in app
    assert main.SOCKETIO_KEY in app


@pytest.mark.asyncio
async def test_on_prepare_allows_same_origin(app, mock_dqueue):
    req = _request(app)
    req.headers = {"Origin": "http://localhost:8081"}
    response = web.Response()
    await main.on_prepare(req, response)
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"


@pytest.mark.asyncio
async def test_on_prepare_rejects_untrusted_origin(app, mock_dqueue):
    req = _request(app)
    req.headers = {"Origin": "https://evil.example"}
    response = web.Response()
    await main.on_prepare(req, response)
    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.asyncio
async def test_on_prepare_allows_trusted_origin(tmp_path):
    app = main.create_app(
        _make_settings(tmp_path, TRUSTED_ORIGINS="https://trusted.example")
    )
    req = _request(app)
    req.headers = {"Origin": "https://trusted.example"}
    response = web.Response()
    await main.on_prepare(req, response)
    assert response.headers["Access-Control-Allow-Origin"] == "https://trusted.example"
