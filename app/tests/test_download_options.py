"""Tests for ``DownloadOptions``, the value the add path carries whole."""

from __future__ import annotations

import dataclasses

import pytest

from download_options import DownloadOptions
from ytdl import DownloadInfo


def test_repr_leaves_out_secrets():
    options = DownloadOptions(video_password="hunter2", ytdl_options_overrides={"cookiefile": "/secret"})
    text = repr(options)
    assert "hunter2" not in text
    assert "/secret" not in text


def test_keeps_its_own_copies_of_presets_and_overrides():
    presets = ["A"]
    overrides = {"x": 1}
    options = DownloadOptions(ytdl_options_presets=presets, ytdl_options_overrides=overrides)
    presets.append("B")
    overrides["y"] = 2
    assert options.ytdl_options_presets == ("A",)
    assert options.ytdl_options_overrides == {"x": 1}


def test_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DownloadOptions().quality = "720"


def test_download_info_fields_build_a_download_info():
    options = DownloadOptions(download_type="audio", format="mp3", sponsorblock=True, audio_tags="none",
                              video_password="pw", clip_start=1.0, auto_start=False)
    fields = options.download_info_fields()
    assert "auto_start" not in fields
    info = DownloadInfo(id="i", title="t", url="u", error=None, entry=None, **fields)
    assert (info.download_type, info.format, info.sponsorblock, info.audio_tags, info.video_password,
            info.clip_start) == ("audio", "mp3", True, "none", "pw", 1.0)


def test_round_trips_through_a_stored_download():
    options = DownloadOptions(download_type="captions", format="vtt", subtitle_language="de",
                              ytdl_options_presets=["A"], split_by_chapters=True, chapter_template="%(title)s")
    info = DownloadInfo(id="i", title="t", url="u", error=None, entry=None, **options.download_info_fields())
    assert DownloadOptions.from_info(info) == options
    assert DownloadOptions.from_info(info, auto_start=False).auto_start is False
