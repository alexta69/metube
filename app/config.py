from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Mapping
from urllib.parse import urlparse

log = logging.getLogger("config")


class SettingsError(ValueError):
    """Raised when environment-backed configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    DOWNLOAD_DIR: str
    AUDIO_DOWNLOAD_DIR: str
    TEMP_DIR: str
    DOWNLOAD_DIRS_INDEXABLE: bool
    CUSTOM_DIRS: bool
    CREATE_CUSTOM_DIRS: bool
    CUSTOM_DIRS_EXCLUDE_REGEX: str
    DELETE_FILE_ON_TRASHCAN: bool
    STATE_DIR: str
    URL_PREFIX: str
    PUBLIC_HOST_URL: str
    PUBLIC_HOST_AUDIO_URL: str
    OUTPUT_TEMPLATE: str
    OUTPUT_TEMPLATE_CHAPTER: str
    OUTPUT_TEMPLATE_PLAYLIST: str
    OUTPUT_TEMPLATE_CHANNEL: str
    DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT: int
    CLEAR_COMPLETED_AFTER: int
    YTDL_OPTIONS: dict[str, Any] = field(repr=False)
    YTDL_OPTIONS_FILE: str
    ROBOTS_TXT: str
    HOST: str
    PORT: int
    HTTPS: bool
    CERTFILE: str
    KEYFILE: str
    DEFAULT_THEME: str
    MAX_CONCURRENT_DOWNLOADS: int
    LOGLEVEL: str
    ENABLE_ACCESSLOG: bool
    TRUSTED_ORIGINS: tuple[str, ...]
    APP_ROOT: Path = field(repr=False, compare=False)
    UI_DIST_DIR: Path = field(repr=False, compare=False)
    ROBOTS_TXT_PATH: Path | None = field(repr=False, compare=False)
    COOKIES_PATH: Path = field(repr=False, compare=False)
    _inline_ytdl_options: dict[str, Any] = field(repr=False, compare=False)
    _runtime_overrides: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    _DEFAULTS: ClassVar[dict[str, str]] = {
        "DOWNLOAD_DIR": ".",
        "AUDIO_DOWNLOAD_DIR": "%%DOWNLOAD_DIR",
        "TEMP_DIR": "%%DOWNLOAD_DIR",
        "DOWNLOAD_DIRS_INDEXABLE": "false",
        "CUSTOM_DIRS": "true",
        "CREATE_CUSTOM_DIRS": "true",
        "CUSTOM_DIRS_EXCLUDE_REGEX": r"(^|/)[.@].*$",
        "DELETE_FILE_ON_TRASHCAN": "false",
        "STATE_DIR": ".",
        "URL_PREFIX": "",
        "PUBLIC_HOST_URL": "download/",
        "PUBLIC_HOST_AUDIO_URL": "audio_download/",
        "OUTPUT_TEMPLATE": "%(title)s.%(ext)s",
        "OUTPUT_TEMPLATE_CHAPTER": "%(title)s - %(section_number)02d - %(section_title)s.%(ext)s",
        "OUTPUT_TEMPLATE_PLAYLIST": "%(playlist_title)s/%(title)s.%(ext)s",
        "OUTPUT_TEMPLATE_CHANNEL": "%(channel)s/%(title)s.%(ext)s",
        "DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT": "0",
        "CLEAR_COMPLETED_AFTER": "0",
        "YTDL_OPTIONS": "{}",
        "YTDL_OPTIONS_FILE": "",
        "ROBOTS_TXT": "",
        "HOST": "0.0.0.0",
        "PORT": "8081",
        "HTTPS": "false",
        "CERTFILE": "",
        "KEYFILE": "",
        "DEFAULT_THEME": "auto",
        "MAX_CONCURRENT_DOWNLOADS": "3",
        "LOGLEVEL": "INFO",
        "ENABLE_ACCESSLOG": "false",
        "TRUSTED_ORIGINS": "",
    }
    _BOOLEAN: ClassVar[tuple[str, ...]] = (
        "DOWNLOAD_DIRS_INDEXABLE",
        "CUSTOM_DIRS",
        "CREATE_CUSTOM_DIRS",
        "DELETE_FILE_ON_TRASHCAN",
        "HTTPS",
        "ENABLE_ACCESSLOG",
    )
    _INTEGER: ClassVar[tuple[str, ...]] = (
        "PORT",
        "DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT",
        "CLEAR_COMPLETED_AFTER",
        "MAX_CONCURRENT_DOWNLOADS",
    )
    _FRONTEND_KEYS: ClassVar[tuple[str, ...]] = (
        "CUSTOM_DIRS",
        "CREATE_CUSTOM_DIRS",
        "OUTPUT_TEMPLATE_CHAPTER",
        "PUBLIC_HOST_URL",
        "PUBLIC_HOST_AUDIO_URL",
        "DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT",
    )
    _SENSITIVE_INLINE_YTDL_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "ap_mso",
            "ap_password",
            "ap_username",
            "client_certificate",
            "client_certificate_key",
            "client_certificate_password",
            "cookiefile",
            "cookiesfrombrowser",
            "netrc",
            "netrc_cmd",
            "netrc_location",
            "password",
            "username",
        }
    )
    _VALID_THEMES: ClassVar[frozenset[str]] = frozenset({"auto", "dark", "light"})

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        app_root: Path | None = None,
    ) -> "Settings":
        source = os.environ if env is None else env
        raw = cls._resolve_defaults(source)
        resolved_app_root = (app_root or Path(__file__).resolve().parent.parent).resolve()
        ui_dist_dir = resolved_app_root / "ui" / "dist" / "metube" / "browser"

        raw["URL_PREFIX"] = cls._normalize_url_prefix(raw["URL_PREFIX"])
        inline_ytdl_options = cls._parse_ytdl_options(raw["YTDL_OPTIONS"])
        cls._validate_inline_ytdl_options(inline_ytdl_options)

        download_dir = cls._resolve_directory(raw["DOWNLOAD_DIR"], "DOWNLOAD_DIR")
        audio_download_dir = cls._resolve_directory(raw["AUDIO_DOWNLOAD_DIR"], "AUDIO_DOWNLOAD_DIR")
        temp_dir = cls._resolve_directory(raw["TEMP_DIR"], "TEMP_DIR")
        state_dir = cls._resolve_directory(raw["STATE_DIR"], "STATE_DIR")

        ytdl_options_file = cls._resolve_optional_file(raw["YTDL_OPTIONS_FILE"], "YTDL_OPTIONS_FILE")
        certfile = cls._resolve_optional_file(raw["CERTFILE"], "CERTFILE")
        keyfile = cls._resolve_optional_file(raw["KEYFILE"], "KEYFILE")
        robots_txt_path = cls._resolve_optional_file(
            raw["ROBOTS_TXT"],
            "ROBOTS_TXT",
            base_dir=resolved_app_root,
        )

        parsed = {
            "DOWNLOAD_DIR": str(download_dir),
            "AUDIO_DOWNLOAD_DIR": str(audio_download_dir),
            "TEMP_DIR": str(temp_dir),
            "DOWNLOAD_DIRS_INDEXABLE": cls._parse_bool("DOWNLOAD_DIRS_INDEXABLE", raw["DOWNLOAD_DIRS_INDEXABLE"]),
            "CUSTOM_DIRS": cls._parse_bool("CUSTOM_DIRS", raw["CUSTOM_DIRS"]),
            "CREATE_CUSTOM_DIRS": cls._parse_bool("CREATE_CUSTOM_DIRS", raw["CREATE_CUSTOM_DIRS"]),
            "CUSTOM_DIRS_EXCLUDE_REGEX": raw["CUSTOM_DIRS_EXCLUDE_REGEX"],
            "DELETE_FILE_ON_TRASHCAN": cls._parse_bool("DELETE_FILE_ON_TRASHCAN", raw["DELETE_FILE_ON_TRASHCAN"]),
            "STATE_DIR": str(state_dir),
            "URL_PREFIX": raw["URL_PREFIX"],
            "PUBLIC_HOST_URL": raw["PUBLIC_HOST_URL"],
            "PUBLIC_HOST_AUDIO_URL": raw["PUBLIC_HOST_AUDIO_URL"],
            "OUTPUT_TEMPLATE": raw["OUTPUT_TEMPLATE"],
            "OUTPUT_TEMPLATE_CHAPTER": raw["OUTPUT_TEMPLATE_CHAPTER"],
            "OUTPUT_TEMPLATE_PLAYLIST": raw["OUTPUT_TEMPLATE_PLAYLIST"],
            "OUTPUT_TEMPLATE_CHANNEL": raw["OUTPUT_TEMPLATE_CHANNEL"],
            "DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT": cls._parse_int(
                "DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT",
                raw["DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT"],
                minimum=0,
            ),
            "CLEAR_COMPLETED_AFTER": cls._parse_int(
                "CLEAR_COMPLETED_AFTER",
                raw["CLEAR_COMPLETED_AFTER"],
                minimum=0,
            ),
            "YTDL_OPTIONS": {},
            "YTDL_OPTIONS_FILE": str(ytdl_options_file) if ytdl_options_file else "",
            "ROBOTS_TXT": str(robots_txt_path) if robots_txt_path else "",
            "HOST": cls._parse_non_empty("HOST", raw["HOST"]),
            "PORT": cls._parse_int("PORT", raw["PORT"], minimum=1),
            "HTTPS": cls._parse_bool("HTTPS", raw["HTTPS"]),
            "CERTFILE": str(certfile) if certfile else "",
            "KEYFILE": str(keyfile) if keyfile else "",
            "DEFAULT_THEME": cls._parse_theme(raw["DEFAULT_THEME"]),
            "MAX_CONCURRENT_DOWNLOADS": cls._parse_int(
                "MAX_CONCURRENT_DOWNLOADS",
                raw["MAX_CONCURRENT_DOWNLOADS"],
                minimum=1,
            ),
            "LOGLEVEL": cls._parse_loglevel(raw["LOGLEVEL"]),
            "ENABLE_ACCESSLOG": cls._parse_bool("ENABLE_ACCESSLOG", raw["ENABLE_ACCESSLOG"]),
            "TRUSTED_ORIGINS": cls._parse_trusted_origins(raw["TRUSTED_ORIGINS"]),
            "APP_ROOT": resolved_app_root,
            "UI_DIST_DIR": ui_dist_dir,
            "ROBOTS_TXT_PATH": robots_txt_path,
            "COOKIES_PATH": state_dir / "cookies.txt",
            "_inline_ytdl_options": inline_ytdl_options,
        }

        cls._validate_https(parsed["HTTPS"], certfile, keyfile)
        cls._validate_ui_dist(ui_dist_dir)

        settings = cls(**parsed)
        success, message = settings.load_ytdl_options()
        if not success:
            raise SettingsError(message)
        return settings

    def frontend_safe(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self._FRONTEND_KEYS}

    def set_runtime_override(self, key: str, value: Any) -> None:
        self._runtime_overrides[key] = value
        self.YTDL_OPTIONS[key] = value

    def remove_runtime_override(self, key: str) -> None:
        self._runtime_overrides.pop(key, None)
        self.YTDL_OPTIONS.pop(key, None)

    def load_ytdl_options(self) -> tuple[bool, str]:
        options = dict(self._inline_ytdl_options)
        if self.YTDL_OPTIONS_FILE:
            path = Path(self.YTDL_OPTIONS_FILE)
            log.info('Loading yt-dlp custom options from "%s"', path)
            if not path.exists():
                return (False, f'File "{path}" not found')
            try:
                with path.open(encoding="utf-8") as json_data:
                    file_options = json.load(json_data)
                if not isinstance(file_options, dict):
                    raise TypeError("YTDL_OPTIONS_FILE must contain a JSON object")
            except (OSError, TypeError, json.JSONDecodeError):
                return (False, "YTDL_OPTIONS_FILE contents is invalid")
            options.update(file_options)

        options.update(self._runtime_overrides)
        self.YTDL_OPTIONS.clear()
        self.YTDL_OPTIONS.update(options)
        return (True, "")

    @classmethod
    def _resolve_defaults(cls, env: Mapping[str, str]) -> dict[str, str]:
        values = {key: str(env.get(key, default)) for key, default in cls._DEFAULTS.items()}
        for key, value in list(values.items()):
            if value.startswith("%%"):
                values[key] = values[value[2:]]
        return values

    @staticmethod
    def _parse_bool(name: str, value: str) -> bool:
        if value not in ("true", "false", "True", "False", "on", "off", "1", "0"):
            raise SettingsError(f'Environment variable "{name}" is set to a non-boolean value "{value}"')
        return value in ("true", "True", "on", "1")

    @staticmethod
    def _parse_int(name: str, value: str, *, minimum: int | None = None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(f'Environment variable "{name}" must be an integer') from exc
        if minimum is not None and parsed < minimum:
            raise SettingsError(f'Environment variable "{name}" must be >= {minimum}')
        return parsed

    @staticmethod
    def _parse_non_empty(name: str, value: str) -> str:
        stripped = str(value).strip()
        if not stripped:
            raise SettingsError(f'Environment variable "{name}" must not be empty')
        return stripped

    @classmethod
    def _parse_loglevel(cls, value: str) -> str:
        parsed = getattr(logging, str(value).upper(), None)
        if not isinstance(parsed, int):
            raise SettingsError(f'Environment variable "LOGLEVEL" is invalid: "{value}"')
        return str(value).upper()

    @classmethod
    def _parse_theme(cls, value: str) -> str:
        theme = str(value).strip().lower()
        if theme not in cls._VALID_THEMES:
            raise SettingsError('Environment variable "DEFAULT_THEME" must be one of auto, dark, light')
        return theme

    @staticmethod
    def _normalize_url_prefix(value: str) -> str:
        prefix = str(value or "").strip()
        if not prefix:
            return "/"
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix

    @staticmethod
    def _resolve_path(value: str, *, base_dir: Path | None = None) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            anchor = base_dir or Path.cwd()
            path = anchor / path
        return path.resolve(strict=False)

    @classmethod
    def _resolve_directory(cls, value: str, name: str) -> Path:
        path = cls._resolve_path(value)
        if not path.exists():
            raise SettingsError(f'Configured path for "{name}" does not exist: {path}')
        if not path.is_dir():
            raise SettingsError(f'Configured path for "{name}" is not a directory: {path}')
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
            raise SettingsError(f'Configured path for "{name}" is not readable/writable: {path}')
        return path

    @classmethod
    def _resolve_optional_file(
        cls,
        value: str,
        name: str,
        *,
        base_dir: Path | None = None,
    ) -> Path | None:
        if not str(value).strip():
            return None
        path = cls._resolve_path(value, base_dir=base_dir)
        if not path.exists():
            raise SettingsError(f'Configured path for "{name}" does not exist: {path}')
        if not path.is_file():
            raise SettingsError(f'Configured path for "{name}" is not a file: {path}')
        if not os.access(path, os.R_OK):
            raise SettingsError(f'Configured path for "{name}" is not readable: {path}')
        return path

    @staticmethod
    def _parse_ytdl_options(value: str) -> dict[str, Any]:
        try:
            options = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise SettingsError("Environment variable YTDL_OPTIONS is invalid") from exc
        if not isinstance(options, dict):
            raise SettingsError("Environment variable YTDL_OPTIONS is invalid")
        return options

    @classmethod
    def _validate_inline_ytdl_options(cls, options: Mapping[str, Any]) -> None:
        sensitive = sorted(cls._SENSITIVE_INLINE_YTDL_KEYS.intersection(options.keys()))
        if sensitive:
            raise SettingsError(
                "Sensitive yt-dlp options are not allowed in YTDL_OPTIONS; "
                f"use YTDL_OPTIONS_FILE instead ({', '.join(sensitive)})"
            )

    @staticmethod
    def _validate_https(enabled: bool, certfile: Path | None, keyfile: Path | None) -> None:
        if enabled and (certfile is None or keyfile is None):
            raise SettingsError('HTTPS requires both "CERTFILE" and "KEYFILE"')

    @staticmethod
    def _validate_ui_dist(ui_dist_dir: Path) -> None:
        index_file = ui_dist_dir / "index.html"
        if not index_file.exists():
            raise SettingsError(
                "Could not find the frontend UI static assets. "
                "Please run `node_modules/.bin/ng build` inside the ui folder"
            )

    @classmethod
    def _parse_trusted_origins(cls, value: str) -> tuple[str, ...]:
        raw_items: list[str]
        stripped = str(value).strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SettingsError('Environment variable "TRUSTED_ORIGINS" is invalid') from exc
            if not isinstance(parsed, list):
                raise SettingsError('Environment variable "TRUSTED_ORIGINS" is invalid')
            raw_items = [str(item).strip() for item in parsed if str(item).strip()]
        else:
            raw_items = [item.strip() for item in stripped.split(",") if item.strip()]

        origins: list[str] = []
        for item in raw_items:
            parsed = urlparse(item)
            if not parsed.scheme or not parsed.netloc:
                raise SettingsError(f'Environment variable "TRUSTED_ORIGINS" contains an invalid origin: "{item}"')
            if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
                raise SettingsError(f'Environment variable "TRUSTED_ORIGINS" must contain origins only: "{item}"')
            normalized = f"{parsed.scheme}://{parsed.netloc}"
            origins.append(normalized)
        return tuple(dict.fromkeys(origins))
