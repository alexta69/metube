"""The options of one download request, as a single value.

Everything an /add request or a subscription specifies besides the URL. It
is built once, where a request is validated (``parse_download_options`` in
``main``, a subscription's stored settings, a failed row being retried), and
then handed down whole: through the queue's add path, its recursion into
playlists and channels, the failed-add record and the retry. Before it, each
of those took the same twenty-odd parameters positionally, and an option
added to some of them but not all was silently dropped on the paths that
missed it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class DownloadOptions:
    download_type: str = 'video'
    codec: str = 'auto'
    format: str = 'any'
    quality: str = 'best'
    folder: Optional[str] = None
    custom_name_prefix: str = ''
    playlist_item_limit: int = 0
    auto_start: bool = True
    split_by_chapters: bool = False
    chapter_template: Optional[str] = None
    subtitle_language: str = 'en'
    subtitle_mode: str = 'prefer_manual'
    ytdl_options_presets: tuple[str, ...] = ()
    # Left out of repr so logging a request cannot leak them: overrides can
    # carry cookies or credentials, and the password is a secret.
    ytdl_options_overrides: dict[str, Any] = field(default_factory=dict, repr=False)
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    sponsorblock: bool = False
    audio_tags: str = 'with_cover'
    video_password: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        # Own copies, so neither the caller's list/dict nor a later mutation
        # of one download's options can reach another download's.
        object.__setattr__(self, 'ytdl_options_presets', tuple(self.ytdl_options_presets or ()))
        object.__setattr__(self, 'ytdl_options_overrides', dict(self.ytdl_options_overrides or {}))

    def replace(self, **changes) -> 'DownloadOptions':
        return dataclasses.replace(self, **changes)

    def download_info_fields(self) -> dict[str, Any]:
        """These options as DownloadInfo keyword arguments.

        auto_start is not one: it decides which queue the download goes to,
        and is not kept on the download itself.
        """
        values = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        del values['auto_start']
        return values

    @classmethod
    def from_info(cls, info, **changes) -> 'DownloadOptions':
        """The options a stored download was made with, for a retry."""
        names = {f.name for f in dataclasses.fields(cls)} - {'auto_start'}
        values = {name: getattr(info, name) for name in names if hasattr(info, name)}
        values.update(changes)
        return cls(**values)
