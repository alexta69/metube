"""Channel/playlist subscriptions: periodic yt-dlp flat extract + queue new videos."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
import types
import uuid
from dataclasses import dataclass, field, fields
from typing import Any, Optional

import yt_dlp
import yt_dlp.networking.impersonate
from state_store import AtomicJsonStore, read_legacy_shelf

log = logging.getLogger("subscriptions")

VIDEO_ONLY_MSG = (
    "This URL points to a single video, not a channel or playlist. Use Download instead."
)
_MEDIA_HINT_FIELDS = (
    "duration",
    "timestamp",
    "release_timestamp",
    "upload_date",
    "view_count",
    "live_status",
    "availability",
)


def _impersonate_opt(ytdl_options: dict) -> dict:
    opts = dict(ytdl_options)
    if "impersonate" in opts:
        opts["impersonate"] = yt_dlp.networking.impersonate.ImpersonateTarget.from_str(
            opts["impersonate"]
        )
    return opts


def _build_ydl_params(config, *, playlistend: Optional[int] = None) -> dict:
    params: dict[str, Any] = {
        "quiet": not logging.getLogger().isEnabledFor(logging.DEBUG),
        "verbose": logging.getLogger().isEnabledFor(logging.DEBUG),
        "no_color": True,
        "extract_flat": True,
        "ignore_no_formats_error": True,
        "lazy_playlist": True,
        "paths": {"home": config.DOWNLOAD_DIR, "temp": config.TEMP_DIR},
        **config.YTDL_OPTIONS,
    }
    params = _impersonate_opt(params)
    if playlistend is not None and playlistend > 0:
        params["playlistend"] = playlistend
    return params


def _is_media_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    etype = str(entry.get("_type") or "")
    if etype in ("playlist", "multi_video", "channel"):
        return False
    if entry.get("entries"):
        return False
    url = _entry_video_url(entry)
    if not url:
        return False
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if any(token in ie_key for token in ("playlist", "channel", "tab")):
        return any(entry.get(field) is not None for field in _MEDIA_HINT_FIELDS)
    return True


def extract_flat_playlist(config, url: str, playlistend: int, *, _depth: int = 0):
    """Return (info_dict, entries_list) for playlist/channel URLs."""
    params = _build_ydl_params(config, playlistend=playlistend)
    with yt_dlp.YoutubeDL(params=params) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return None, []
    etype = info.get("_type") or "video"
    if etype == "video":
        return info, []
    if etype in ("playlist", "channel"):
        entries = info.get("entries") or []
        if isinstance(entries, types.GeneratorType):
            entries = list(entries)
        # Drop None placeholders from incomplete flat playlists
        entries = [e for e in entries if e]
        media_entries = [e for e in entries if _is_media_entry(e)]
        if media_entries:
            return info, media_entries
        if _depth < 1:
            for ent in entries[:5]:
                nested_url = _entry_video_url(ent)
                if not nested_url:
                    continue
                nested_info, nested_entries = extract_flat_playlist(
                    config,
                    nested_url,
                    playlistend,
                    _depth=_depth + 1,
                )
                if nested_entries:
                    return nested_info, nested_entries
        return info, entries
    if etype.startswith("url") and info.get("url"):
        # Single nested URL without playlist wrapper — treat as non-subscribable
        return info, []
    return info, []


def _entry_video_url(entry: dict) -> Optional[str]:
    return entry.get("webpage_url") or entry.get("url")


def _entry_id(entry: dict) -> Optional[str]:
    eid = entry.get("id")
    if eid is not None:
        return str(eid)
    url = _entry_video_url(entry)
    return url


@dataclass
class SubscriptionInfo:
    id: str
    name: str
    url: str
    enabled: bool = True
    check_interval_minutes: int = 60
    download_type: str = "video"
    codec: str = "auto"
    format: str = "any"
    quality: str = "best"
    folder: str = ""
    custom_name_prefix: str = ""
    auto_start: bool = True
    playlist_item_limit: int = 0
    split_by_chapters: bool = False
    chapter_template: str = ""
    subtitle_language: str = "en"
    subtitle_mode: str = "prefer_manual"
    ytdl_options_presets: list[str] = field(default_factory=list)
    ytdl_options_overrides: dict[str, Any] = field(default_factory=dict)
    last_checked: Optional[float] = None
    seen_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def seen_set(self) -> set[str]:
        return set(self.seen_ids)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "check_interval_minutes": self.check_interval_minutes,
            "download_type": self.download_type,
            "codec": self.codec,
            "format": self.format,
            "quality": self.quality,
            "folder": self.folder,
            "last_checked": self.last_checked,
            "seen_count": len(self.seen_ids),
            "error": self.error,
        }


def _subscription_to_record(sub: SubscriptionInfo) -> dict[str, Any]:
    return {
        "id": sub.id,
        "name": sub.name,
        "url": sub.url,
        "enabled": sub.enabled,
        "check_interval_minutes": sub.check_interval_minutes,
        "download_type": sub.download_type,
        "codec": sub.codec,
        "format": sub.format,
        "quality": sub.quality,
        "folder": sub.folder,
        "custom_name_prefix": sub.custom_name_prefix,
        "auto_start": sub.auto_start,
        "playlist_item_limit": sub.playlist_item_limit,
        "split_by_chapters": sub.split_by_chapters,
        "chapter_template": sub.chapter_template,
        "subtitle_language": sub.subtitle_language,
        "subtitle_mode": sub.subtitle_mode,
        "ytdl_options_presets": list(sub.ytdl_options_presets),
        "ytdl_options_overrides": sub.ytdl_options_overrides,
        "last_checked": sub.last_checked,
        "seen_ids": list(sub.seen_ids),
        "error": sub.error,
    }


def _normalize_subscription_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy ytdl_options_preset (str) to ytdl_options_presets (list)."""
    out = dict(rec)
    if "ytdl_options_presets" not in out:
        old = out.pop("ytdl_options_preset", None)
        if old is None:
            out["ytdl_options_presets"] = []
        elif isinstance(old, list):
            out["ytdl_options_presets"] = [str(x).strip() for x in old if str(x).strip()]
        elif isinstance(old, str):
            out["ytdl_options_presets"] = [old.strip()] if old.strip() else []
        else:
            out["ytdl_options_presets"] = []
    else:
        out.pop("ytdl_options_preset", None)
    return out


def _subscription_from_record(record: Any) -> Optional[SubscriptionInfo]:
    field_names = {f.name for f in fields(SubscriptionInfo)}
    if isinstance(record, SubscriptionInfo):
        return record
    if isinstance(record, dict):
        try:
            normalized = _normalize_subscription_record(dict(record))
            return SubscriptionInfo(**{k: v for k, v in normalized.items() if k in field_names})
        except TypeError:
            return None
    return None


def _coerce_bool(value: Any) -> bool:
    """Accept JSON booleans and common string forms used by API clients."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "on"}:
            return True
        if lowered in {"false", "0", "off"}:
            return False
    raise ValueError("enabled must be a boolean")


class SubscriptionNotifier:
    """Hook for Socket.IO / UI updates."""

    async def subscription_added(self, sub: SubscriptionInfo) -> None:
        raise NotImplementedError

    async def subscription_updated(self, sub: SubscriptionInfo) -> None:
        raise NotImplementedError

    async def subscription_removed(self, sub_id: str) -> None:
        raise NotImplementedError

    async def subscriptions_all(self, subs: list[SubscriptionInfo]) -> None:
        raise NotImplementedError


class SubscriptionManager:
    def __init__(self, config, download_queue, notifier: SubscriptionNotifier):
        self.config = config
        self.dqueue = download_queue
        self.notifier = notifier
        pdir = config.STATE_DIR
        if not os.path.isdir(pdir):
            os.makedirs(pdir, exist_ok=True)
        self._legacy_path = os.path.join(pdir, "subscriptions")
        self._path = os.path.join(pdir, "subscriptions.json")
        self._store = AtomicJsonStore(self._path, kind="subscriptions")
        self._subs: dict[str, SubscriptionInfo] = {}
        self._url_index: dict[str, str] = {}  # normalized url -> id
        self._pending_urls: set[str] = set()
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._load_all()

    def close(self) -> None:
        # No persistent shelf handle to close.
        return

    def _normalize_url(self, url: str) -> str:
        return (url or "").strip()

    def _normalize_seen_ids(self, seen_ids: list[str]) -> list[str]:
        max_seen = int(getattr(self.config, "SUBSCRIPTION_MAX_SEEN_IDS", 50000))
        normalized = [str(sid) for sid in dict.fromkeys(seen_ids)]
        if len(normalized) > max_seen:
            normalized = normalized[:max_seen]
        return normalized

    def _load_all(self) -> None:
        payload = self._store.load()
        loaded_from_legacy = False
        if payload is not None:
            records = payload.get("items") or []
        else:
            legacy_items = read_legacy_shelf(self._legacy_path)
            records = [raw for _key, raw in legacy_items] if legacy_items else []
            if records:
                loaded_from_legacy = True

        loaded_subs = self._iter_valid_subs(records)
        compact_records = []
        for sub in loaded_subs:
            sub.seen_ids = self._normalize_seen_ids(sub.seen_ids)
            self._subs[sub.id] = sub
            self._url_index[self._normalize_url(sub.url)] = sub.id
            compact_records.append(_subscription_to_record(sub))

        if loaded_from_legacy or (
            payload is not None
            and (
                payload.get("schema_version") != self._store.schema_version
                or compact_records != records
            )
        ):
            self._store.save({"items": compact_records})

    def _iter_valid_subs(self, records: list[Any]) -> list[SubscriptionInfo]:
        subs: list[SubscriptionInfo] = []
        for record in records:
            sub = _subscription_from_record(record)
            if sub is not None:
                subs.append(sub)
        return subs

    def _save_locked(self) -> None:
        self._store.save({"items": [_subscription_to_record(sub) for sub in self._subs.values()]})

    async def _queue_subscription_entries(
        self,
        entries: list[dict],
        *,
        download_type: str,
        codec: str,
        format: str,
        quality: str,
        folder: str,
        custom_name_prefix: str,
        playlist_item_limit: int,
        auto_start: bool,
        split_by_chapters: bool,
        chapter_template: str,
        subtitle_language: str,
        subtitle_mode: str,
        ytdl_options_presets: Optional[list[str]] = None,
        ytdl_options_overrides: Optional[dict[str, Any]] = None,
    ) -> tuple[list[str], list[str]]:
        queued_ids: list[str] = []
        queue_errors: list[str] = []
        presets = list(ytdl_options_presets or [])
        for ent in entries:
            eid = _entry_id(ent)
            vurl = _entry_video_url(ent)
            if not eid or not vurl:
                continue
            queue_entry = dict(ent)
            if "id" not in queue_entry:
                queue_entry["id"] = eid
            queue_entry["_type"] = "video"
            queue_entry["webpage_url"] = vurl
            result = await self.dqueue.add_entry(
                queue_entry,
                download_type,
                codec,
                format,
                quality,
                folder or None,
                custom_name_prefix,
                playlist_item_limit,
                auto_start,
                split_by_chapters,
                chapter_template or None,
                subtitle_language,
                subtitle_mode,
                presets,
                ytdl_options_overrides,
            )
            if isinstance(result, dict) and result.get("status") == "error":
                msg = str(result.get("msg") or f"Queueing failed for {vurl}")
                queue_errors.append(msg)
                log.warning("Subscription queueing failed for %s: %s", vurl, msg)
                continue
            queued_ids.append(eid)
        return queued_ids, queue_errors

    def list_all(self) -> list[SubscriptionInfo]:
        return list(self._subs.values())

    def get(self, sub_id: str) -> Optional[SubscriptionInfo]:
        return self._subs.get(sub_id)

    def start_background_loop(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._loop_task = asyncio.create_task(self._periodic_loop())
        self._loop_task.add_done_callback(
            lambda t: log.error("Subscription loop failed: %s", t.exception())
            if not t.cancelled() and t.exception()
            else None
        )

    async def _periodic_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await self.run_due_checks()
            except Exception as e:
                log.exception("Subscription periodic check error: %s", e)

    async def run_due_checks(self) -> None:
        now = time.time()
        due: list[SubscriptionInfo] = []
        async with self._lock:
            for sub in list(self._subs.values()):
                if not sub.enabled:
                    continue
                interval_sec = max(60, int(sub.check_interval_minutes) * 60)
                if sub.last_checked is None:
                    due.append(sub)
                    continue
                if now - sub.last_checked < interval_sec:
                    continue
                due.append(sub)
        for sub in due:
            await self._check_one_unlocked(sub)

    async def add_subscription(
        self,
        url: str,
        *,
        check_interval_minutes: int,
        download_type: str,
        codec: str,
        format: str,
        quality: str,
        folder: str,
        custom_name_prefix: str,
        auto_start: bool,
        playlist_item_limit: int,
        split_by_chapters: bool,
        chapter_template: str,
        subtitle_language: str,
        subtitle_mode: str,
        ytdl_options_presets: Optional[list[str]] = None,
        ytdl_options_overrides: Optional[dict[str, Any]] = None,
    ) -> dict:
        url = self._normalize_url(url)
        if not url:
            return {"status": "error", "msg": "Missing URL"}

        async with self._lock:
            if url in self._url_index or url in self._pending_urls:
                return {"status": "error", "msg": "This URL is already subscribed"}
            self._pending_urls.add(url)

        try:
            scan_first = max(int(getattr(self.config, "SUBSCRIPTION_SCAN_PLAYLIST_END", 50)), 1)
            try:
                info, entries = extract_flat_playlist(self.config, url, scan_first)
            except yt_dlp.utils.YoutubeDLError as exc:
                return {"status": "error", "msg": str(exc)}

            if not info:
                return {"status": "error", "msg": "Could not resolve URL"}

            etype = info.get("_type") or "video"
            if etype not in ("playlist", "channel"):
                return {"status": "error", "msg": VIDEO_ONLY_MSG}

            name = (
                info.get("title")
                or info.get("channel")
                or info.get("playlist_title")
                or info.get("uploader")
                or url
            )

            seen_entries = [ent for ent in entries if _is_media_entry(ent)]
            all_ids: list[str] = []
            for ent in seen_entries:
                if ent.get("live_status") == "is_upcoming":
                    continue  # Don't mark scheduled streams as seen; queue them when they go live
                eid = _entry_id(ent)
                if eid:
                    all_ids.append(eid)

            sub = SubscriptionInfo(
                id=str(uuid.uuid4()),
                name=str(name),
                url=url,
                enabled=True,
                check_interval_minutes=max(1, int(check_interval_minutes)),
                download_type=download_type,
                codec=codec,
                format=format,
                quality=quality,
                folder=folder or "",
                custom_name_prefix=custom_name_prefix or "",
                auto_start=bool(auto_start),
                playlist_item_limit=int(playlist_item_limit),
                split_by_chapters=bool(split_by_chapters),
                chapter_template=chapter_template or "",
                subtitle_language=subtitle_language,
                subtitle_mode=subtitle_mode,
                ytdl_options_presets=list(ytdl_options_presets or []),
                ytdl_options_overrides=dict(ytdl_options_overrides or {}),
                last_checked=time.time(),
                seen_ids=list(dict.fromkeys(all_ids)),
                error=None,
            )

            async with self._lock:
                if url in self._url_index:
                    return {"status": "error", "msg": "This URL is already subscribed"}
                self._subs[sub.id] = sub
                self._url_index[url] = sub.id
                try:
                    self._save_locked()
                except Exception:
                    self._subs.pop(sub.id, None)
                    self._url_index.pop(url, None)
                    raise

            await self.notifier.subscription_added(sub)
            return {"status": "ok", "subscription": sub.to_public_dict()}
        finally:
            async with self._lock:
                self._pending_urls.discard(url)

    async def delete_subscriptions(self, ids: list[str]) -> dict:
        removed: list[str] = []
        async with self._lock:
            previous_subs = self._subs.copy()
            previous_index = self._url_index.copy()
            for sid in ids:
                sub = self._subs.pop(sid, None)
                if sub:
                    normalized_url = self._normalize_url(sub.url)
                    self._url_index.pop(normalized_url, None)
                    removed.append(sid)
            if removed:
                try:
                    self._save_locked()
                except Exception:
                    self._subs = previous_subs
                    self._url_index = previous_index
                    raise
        for sid in removed:
            await self.notifier.subscription_removed(sid)
        return {"status": "ok"}

    async def update_subscription(self, sub_id: str, changes: dict) -> dict:
        async with self._lock:
            sub = self._subs.get(sub_id)
            if not sub:
                return {"status": "error", "msg": "Subscription not found"}
            previous = copy.deepcopy(sub)
            old_enabled = sub.enabled

            if "enabled" in changes:
                sub.enabled = _coerce_bool(changes["enabled"])
            if "check_interval_minutes" in changes:
                sub.check_interval_minutes = max(1, int(changes["check_interval_minutes"]))
            if "name" in changes and changes["name"]:
                sub.name = str(changes["name"])

            try:
                self._save_locked()
            except Exception:
                self._subs[sub_id] = previous
                raise
            updated = sub
        if "enabled" in changes and updated.enabled != old_enabled:
            log.info(
                "Subscription %s %s",
                updated.name,
                "resumed" if updated.enabled else "paused",
            )
        await self.notifier.subscription_updated(updated)
        return {"status": "ok", "subscription": updated.to_public_dict()}

    async def check_now(self, ids: Optional[list[str]] = None) -> dict:
        async with self._lock:
            targets = (
                [self._subs[i] for i in ids if i in self._subs]
                if ids
                else [s for s in self._subs.values() if s.enabled]
            )
        log.info(
            "Manual subscription check requested for %d subscription(s)",
            len(targets),
        )
        for sub in targets:
            await self._check_one_unlocked(sub)
        return {"status": "ok"}

    async def _check_one_unlocked(self, sub: SubscriptionInfo) -> None:
        sid = sub.id
        scan = int(getattr(self.config, "SUBSCRIPTION_SCAN_PLAYLIST_END", 50))
        log.info("Checking subscription: %s", sub.name)
        try:
            info, entries = extract_flat_playlist(self.config, sub.url, scan)
        except yt_dlp.utils.YoutubeDLError as exc:
            async with self._lock:
                cur = self._subs.get(sid)
                if cur:
                    previous = copy.deepcopy(cur)
                    cur.error = str(exc)
                    try:
                        self._save_locked()
                    except Exception:
                        self._subs[sid] = previous
                        raise
                    sub = cur
            log.warning("Subscription check failed for %s: %s", sub.name, exc)
            await self.notifier.subscription_updated(sub)
            return
        entries = [ent for ent in entries if _is_media_entry(ent)]

        etype = (info or {}).get("_type") or "video"
        if etype == "video" or not entries:
            async with self._lock:
                cur = self._subs.get(sid)
                if cur:
                    previous = copy.deepcopy(cur)
                    cur.error = VIDEO_ONLY_MSG
                    try:
                        self._save_locked()
                    except Exception:
                        self._subs[sid] = previous
                        raise
                    sub = cur
            log.warning("Subscription %s no longer resolves to a subscribable feed", sub.name)
            await self.notifier.subscription_updated(sub)
            return

        async with self._lock:
            cur = self._subs.get(sid)
            if not cur:
                return
            seen = cur.seen_set()
            seen_ids_snapshot = list(cur.seen_ids)
            dl_type = cur.download_type
            dl_codec = cur.codec
            dl_format = cur.format
            dl_quality = cur.quality
            dl_folder = cur.folder
            dl_prefix = cur.custom_name_prefix
            dl_plimit = cur.playlist_item_limit
            dl_autostart = cur.auto_start
            dl_split = cur.split_by_chapters
            dl_chapter = cur.chapter_template
            dl_sublang = cur.subtitle_language
            dl_submode = cur.subtitle_mode
            dl_ytdl_presets = list(cur.ytdl_options_presets)
            dl_ytdl_overrides = dict(cur.ytdl_options_overrides)

        new_entries: list[dict] = []
        new_ids: list[str] = []
        for ent in entries:
            eid = _entry_id(ent)
            if not eid:
                continue
            if eid in seen and ent.get("live_status") != "is_live":
                continue
            new_entries.append(ent)
            new_ids.append(eid)

        queued_ids, queue_errors = await self._queue_subscription_entries(
            new_entries,
            download_type=dl_type,
            codec=dl_codec,
            format=dl_format,
            quality=dl_quality,
            folder=dl_folder,
            custom_name_prefix=dl_prefix,
            playlist_item_limit=dl_plimit,
            auto_start=dl_autostart,
            split_by_chapters=dl_split,
            chapter_template=dl_chapter or "",
            subtitle_language=dl_sublang,
            subtitle_mode=dl_submode,
            ytdl_options_presets=dl_ytdl_presets,
            ytdl_options_overrides=dl_ytdl_overrides,
        )
        log.info(
            "Subscription check finished for %s: %d new, %d queued, %d failed",
            sub.name,
            len(new_entries),
            len(queued_ids),
            len(queue_errors),
        )

        merged = list(dict.fromkeys(queued_ids + seen_ids_snapshot))
        max_seen = int(getattr(self.config, "SUBSCRIPTION_MAX_SEEN_IDS", 50000))
        if len(merged) > max_seen:
            merged = merged[:max_seen]

        async with self._lock:
            cur = self._subs.get(sid)
            if not cur:
                return
            previous = copy.deepcopy(cur)
            cur.seen_ids = merged
            cur.last_checked = time.time()
            cur.error = "; ".join(queue_errors[:3]) if queue_errors else None
            try:
                self._save_locked()
            except Exception:
                self._subs[sid] = previous
                raise
            sub = cur
        await self.notifier.subscription_updated(sub)

    async def emit_all(self) -> None:
        await self.notifier.subscriptions_all(self.list_all())
