"""HTTP handler tests for ``main`` using mocked ``web.Request`` (no TestServer)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import main


@pytest.fixture
def mock_dqueue(monkeypatch):
    d = MagicMock()
    d.initialize = AsyncMock(return_value=None)
    d.add = AsyncMock(return_value={"status": "ok"})
    d.cancel = AsyncMock(return_value={"status": "ok"})
    d.start_pending = AsyncMock(return_value={"status": "ok"})
    d.cancel_add = MagicMock()
    d.queue = MagicMock()
    d.done = MagicMock()
    d.pending = MagicMock()
    d.queue.saved_items = MagicMock(return_value=[])
    d.done.saved_items = MagicMock(return_value=[])
    d.pending.saved_items = MagicMock(return_value=[])
    d.get = MagicMock(return_value=([], []))
    monkeypatch.setattr(main, "dqueue", d)
    return d


def _valid_video_add_body(**kwargs):
    base = {
        "url": "https://example.com/watch?v=1",
        "download_type": "video",
        "codec": "auto",
        "format": "any",
        "quality": "best",
        "ytdl_options_presets": [],
        "ytdl_options_overrides": "",
    }
    base.update(kwargs)
    return base


def _json_request(body: dict | None):
    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(return_value=body)
    return req


@pytest.mark.asyncio
async def test_add_ok(mock_dqueue):
    req = _json_request(_valid_video_add_body())
    resp = await main.add(req)
    assert resp.status == 200
    text = resp.text
    data = json.loads(text)
    assert data["status"] == "ok"
    mock_dqueue.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_passes_preset_and_overrides(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Preset A": {"writesubtitles": True}})
    monkeypatch.setattr(main.config, "ALLOW_YTDL_OPTIONS_OVERRIDES", True)
    req = _json_request(
        _valid_video_add_body(
            ytdl_options_presets=["Preset A"],
            ytdl_options_overrides='{"writesubtitles": true}',
        )
    )
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[13] == ["Preset A"]
    assert call.args[14] == {"writesubtitles": True}


@pytest.mark.asyncio
async def test_add_legacy_string_preset_normalized(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Legacy": {}})
    body = _valid_video_add_body()
    del body["ytdl_options_presets"]
    body["ytdl_options_preset"] = "Legacy"
    req = _json_request(body)
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call.args[13] == ["Legacy"]


@pytest.mark.asyncio
async def test_add_missing_url_returns_400(mock_dqueue):
    req = _json_request({"download_type": "video", "quality": "best", "format": "any"})
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)
    mock_dqueue.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_invalid_download_type(mock_dqueue):
    req = _json_request(_valid_video_add_body(download_type="invalid"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_video_quality(mock_dqueue):
    req = _json_request(_valid_video_add_body(quality="9999"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_subtitle_language(mock_dqueue):
    req = _json_request(
        {
            "url": "https://example.com/v",
            "download_type": "captions",
            "codec": "auto",
            "format": "srt",
            "quality": "best",
            "subtitle_language": "bad language!",
        }
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_custom_name_prefix_path_traversal(mock_dqueue):
    req = _json_request(_valid_video_add_body(custom_name_prefix="../evil"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_chapter_template_path_traversal(mock_dqueue):
    req = _json_request(
        _valid_video_add_body(
            split_by_chapters=True,
            chapter_template="/etc/passwd%(title)s",
        )
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_json_body(mock_dqueue):
    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(side_effect=json.JSONDecodeError("msg", "", 0))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_ytdl_options_override_json(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_overrides="{bad json}"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_rejects_ytdl_options_overrides_when_disabled(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_overrides='{"exec": "rm -rf /"}'))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_allows_any_ytdl_options_override_key_when_enabled(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "ALLOW_YTDL_OPTIONS_OVERRIDES", True)
    req = _json_request(_valid_video_add_body(ytdl_options_overrides='{"exec": "echo hi"}'))
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[14] == {"exec": "echo hi"}


@pytest.mark.asyncio
async def test_add_unknown_ytdl_preset(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_presets=["Missing"]))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_delete_missing_ids(mock_dqueue):
    req = _json_request({"where": "queue"})
    with pytest.raises(web.HTTPBadRequest):
        await main.delete(req)


@pytest.mark.asyncio
async def test_delete_queue_calls_cancel(mock_dqueue):
    req = _json_request({"where": "queue", "ids": ["http://x"]})
    resp = await main.delete(req)
    assert resp.status == 200
    mock_dqueue.cancel.assert_awaited_once_with(["http://x"])


@pytest.mark.asyncio
async def test_start_pending(mock_dqueue):
    req = _json_request({"ids": ["a"]})
    resp = await main.start(req)
    assert resp.status == 200
    mock_dqueue.start_pending.assert_awaited_once_with(["a"])


@pytest.mark.asyncio
async def test_history_shape(mock_dqueue):
    mock_dqueue.queue.saved_items.return_value = []
    mock_dqueue.done.saved_items.return_value = []
    mock_dqueue.pending.saved_items.return_value = []
    req = MagicMock(spec=web.Request)
    resp = await main.history(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert set(data.keys()) == {"done", "queue", "pending"}


@pytest.mark.asyncio
async def test_version_json(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.version(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert "yt-dlp" in body and "version" in body


@pytest.mark.asyncio
async def test_presets_endpoint_returns_names(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Preset B": {}, "Preset A": {}})
    req = MagicMock(spec=web.Request)
    resp = await main.presets(req)
    assert resp.status == 200
    assert json.loads(resp.text) == {"presets": ["Preset A", "Preset B"]}


@pytest.mark.asyncio
async def test_cookie_status(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.cookie_status(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data.get("status") == "ok"
    assert "has_cookies" in data


@pytest.mark.asyncio
async def test_options_add_cors(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.add_cors(req)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_upload_cookies_missing_field(mock_dqueue):
    req = MagicMock(spec=web.Request)
    reader = MagicMock()
    field = MagicMock()
    field.name = "wrongname"
    reader.next = AsyncMock(side_effect=[field, None])
    req.multipart = AsyncMock(return_value=reader)
    resp = await main.upload_cookies(req)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_add_legacy_format_migrated(mock_dqueue):
    req = _json_request({"url": "https://example.com/v", "format": "m4a", "quality": "best"})
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[1] == "audio"
