"""Direct streaming routes (``/watch``, ``/dl/<name>.<ext>``) — parsing and handler plumbing."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aiohttp import web

import direct
import main


def _request(query: dict, name: str | None = None):
    req = MagicMock(spec=web.Request)
    req.query = query
    req.match_info = {'name': name} if name is not None else {}
    return req


def test_parse_name_turns_separators_into_a_search_term():
    assert direct.parse_name('Greenday-Basketcase.mp3') == ('Greenday Basketcase', 'mp3')
    assert direct.parse_name('some_thing+else.MP4') == ('some thing else', 'mp4')
    assert direct.parse_name('cover.JPEG') == ('cover', 'jpg')


@pytest.mark.parametrize('name', ['noext', 'file.exe', '.mp4', '---.mp3'])
def test_parse_name_rejects_bad_names(name):
    with pytest.raises(web.HTTPBadRequest):
        direct.parse_name(name)


def test_parse_ts():
    assert direct.parse_ts(None) is None
    assert direct.parse_ts('') is None
    assert direct.parse_ts('90') == 90
    assert direct.parse_ts('1:30') == 90
    assert direct.parse_ts('1m30s') == 90
    with pytest.raises(web.HTTPBadRequest):
        direct.parse_ts('soon')


def test_content_disposition_inline_vs_attachment_with_utf8_name():
    inline = direct.content_disposition('Grün Day: Basket/Case', 'mp3', download=False)
    assert inline.startswith('inline; filename="')
    assert "filename*=UTF-8''Gr%C3%BCn%20Day" in inline
    assert direct.content_disposition('x', 'mp4', download=True).startswith('attachment; ')


@pytest.mark.asyncio
async def test_dl_searches_by_name_and_serves_temp_file(monkeypatch):
    calls = []

    async def fake_fetch(source, ext, ts, tmpdir, ytdl_opts, allow_private):
        calls.append((source, ext, ts))
        path = os.path.join(tmpdir, f'media.{ext}')
        Path(path).write_bytes(b'ID3')
        return path, 'Green Day - Basket Case'

    monkeypatch.setattr(main, '_run_direct_fetch', fake_fetch)
    resp = await main.dl(_request({'download': '1', 'ts': '5'}, name='Greenday-Basketcase.mp3'))
    assert isinstance(resp, direct.TempFileResponse)
    assert calls == [('ytsearch1:Greenday Basketcase', 'mp3', 5)]
    assert resp.headers['Content-Disposition'].startswith('attachment; filename="Green_Day_-_Basket_Case.mp3"')
    resp._tmpdir.cleanup()


@pytest.mark.asyncio
async def test_watch_passes_v_through_and_cleans_up_on_failure(monkeypatch):
    seen = {}

    async def failing_fetch(source, ext, ts, tmpdir, ytdl_opts, allow_private):
        seen['source'], seen['tmpdir'] = source, tmpdir
        raise direct.FetchError('no results')

    monkeypatch.setattr(main, '_run_direct_fetch', failing_fetch)
    with pytest.raises(web.HTTPBadGateway):
        await main.watch(_request({'v': 'dQw4w9WgXcQ'}))
    assert seen['source'] == 'dQw4w9WgXcQ'
    assert not os.path.exists(seen['tmpdir'])


@pytest.mark.asyncio
async def test_dl_explicit_url_wins_over_search_and_internal_hosts_are_refused(monkeypatch):
    calls = []

    async def fake_fetch(source, ext, ts, tmpdir, ytdl_opts, allow_private):
        calls.append(source)
        path = os.path.join(tmpdir, 'media.jpg')
        Path(path).write_bytes(b'\xff\xd8')
        return path, 't'

    monkeypatch.setattr(main, '_run_direct_fetch', fake_fetch)
    resp = await main.dl(_request({'url': 'https://example.com/v/1'}, name='whatever.jpg'))
    assert calls == ['https://example.com/v/1']
    assert resp.headers['Content-Disposition'].startswith('inline; ')
    resp._tmpdir.cleanup()

    with pytest.raises(web.HTTPBadRequest):
        await main.dl(_request({'url': 'http://localhost/secret'}, name='whatever.jpg'))
    assert calls == ['https://example.com/v/1']
