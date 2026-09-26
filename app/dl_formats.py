import copy

AUDIO_FORMATS = ("auto", "m4a", "mp3", "opus", "wav", "flac")
AUDIO_TAGS_MODES = ("with_cover", "no_cover", "none")
CAPTION_MODES = ("auto_only", "manual_only", "prefer_manual", "prefer_auto")

# FFmpegExtractAudio targets for the "auto" audio format, in yt-dlp's
# --audio-format rule syntax ("SOURCE>TARGET/.../FALLBACK", matched on the
# downloaded file's extension).
#
# With tags: "best" keeps the codec the site served and only moves it into a
# container that can carry tags and a cover (YouTube's webm Opus -> .opus, by
# stream copy). The explicit rules cover the files "best" would leave as they
# are but EmbedThumbnail refuses; a failed embed would fail the download.
_AUTO_AUDIO_TAGGABLE = "wav>flac/aiff>flac/wma>mp3/best"
# Without tags the file is kept exactly as served; only a video container
# (a site with no audio-only stream) has its audio copied out. An extension
# with no rule is skipped before ffmpeg runs at all. webm is deliberately
# absent: YouTube's audio-only streams are webm.
_AUTO_AUDIO_AS_SERVED = "/".join(
    f"{ext}>best"
    for ext in ("mp4", "m4v", "mov", "mkv", "flv", "avi", "3gp", "wmv", "mpg", "ogv")
)


def merge_ytdl_option_layers(presets, overrides, presets_config) -> dict:
    """Overlay named presets (in order) then per-item overrides onto a fresh dict.

    Does NOT include any base ``YTDL_OPTIONS`` — callers layer this on top of
    their own base (a per-download build adds the global base; a subscription
    scan relies on ``**config.YTDL_OPTIONS`` already being present in its
    params). ``presets_config`` maps a preset name to its options dict.
    """
    merged: dict = {}
    for name in presets or []:
        merged.update(presets_config.get(name, {}))
    merged.update(overrides or {})
    return merged

CODEC_FILTER_MAP = {
    'h264': "[vcodec~='^(h264|avc)']",
    'h265': "[vcodec~='^(h265|hevc)']",
    'av1':  "[vcodec~='^av0?1']",
    'vp9':  "[vcodec~='^vp0?9']",
}


def _normalize_caption_mode(mode: str) -> str:
    mode = (mode or "").strip()
    return mode if mode in CAPTION_MODES else "prefer_manual"


def _normalize_subtitle_language(language: str) -> str:
    language = (language or "").strip()
    return language or "en"


def get_format(download_type: str, codec: str, format: str, quality: str) -> str:
    """
    Returns yt-dlp format selector.

    Args:
      download_type (str): selected content type (video, audio, captions, thumbnail)
      codec (str): selected video codec (auto, h264, h265, av1, vp9)
      format (str): selected output format/profile for type
      quality (str): selected quality

    Raises:
      Exception: unknown type/format

    Returns:
      str: yt-dlp format selector
    """
    download_type = (download_type or "video").strip().lower()
    format = (format or "any").strip().lower()
    codec = (codec or "auto").strip().lower()
    quality = (quality or "best").strip().lower()

    if format.startswith("custom:"):
        # Unreachable via the HTTP API (format is validated against a fixed
        # set in main.py), but legacy persisted downloads may carry a
        # custom: format from before that validation existed; removing this
        # would crash PersistentQueue.load() for those records.
        return format[7:]

    if download_type == "thumbnail":
        return "bestaudio/best"

    if download_type == "captions":
        return "bestaudio/best"

    if download_type == "audio":
        if format not in AUDIO_FORMATS:
            raise ValueError(f"Unknown audio format {format}")
        if format == "auto":
            return "bestaudio/best"
        return f"bestaudio[ext={format}]/bestaudio/best"

    if download_type == "video":
        if format not in ("any", "mp4", "ios"):
            raise ValueError(f"Unknown video format {format}")
        vfmt, afmt = ("[ext=mp4]", "[ext=m4a]") if format in ("mp4", "ios") else ("", "")
        vres = f"[height<={quality}]" if quality not in ("best", "worst") else ""
        vcombo = vres + vfmt
        codec_filter = CODEC_FILTER_MAP.get(codec, "")

        if format == "ios":
            return f"bestvideo[vcodec~='^((he|a)vc|h26[45])']{vres}+bestaudio[acodec=aac]/bestvideo[vcodec~='^((he|a)vc|h26[45])']{vres}+bestaudio{afmt}/bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"

        if codec_filter:
            return f"bestvideo{codec_filter}{vcombo}+bestaudio{afmt}/bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"
        return f"bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"

    raise ValueError(f"Unknown download_type {download_type}")


def get_opts(
    download_type: str,
    _codec: str,
    format: str,
    quality: str,
    ytdl_opts: dict,
    subtitle_language: str = "en",
    subtitle_mode: str = "prefer_manual",
    audio_tags: str = "with_cover",
) -> dict:
    """
    Returns extra yt-dlp options/postprocessors.

    Args:
      download_type (str): selected content type
      codec (str): selected codec (unused currently, kept for API consistency)
      format (str): selected format/profile
      quality (str): selected quality
      ytdl_opts (dict): current options selected
      audio_tags (str): for audio, what to write into the file
        (with_cover, no_cover, none)

    Returns:
      dict: extended options
    """
    download_type = (download_type or "video").strip().lower()
    format = (format or "any").strip().lower()
    opts = copy.deepcopy(ytdl_opts)

    postprocessors = []

    if download_type == "audio":
        if audio_tags not in AUDIO_TAGS_MODES:
            audio_tags = "with_cover"

        if format == "auto":
            preferredcodec = _AUTO_AUDIO_AS_SERVED if audio_tags == "none" else _AUTO_AUDIO_TAGGABLE
        else:
            preferredcodec = format
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": preferredcodec,
                "preferredquality": 0 if quality == "best" else quality,
            }
        )

        # A writethumbnail key in the user's options means they manage
        # thumbnails themselves, so the whole tagging chain stays off.
        if format != "wav" and audio_tags != "none" and "writethumbnail" not in opts:
            if audio_tags == "with_cover":
                opts["writethumbnail"] = True
                postprocessors.append(
                    {
                        "key": "FFmpegThumbnailsConvertor",
                        "format": "jpg",
                        "when": "before_dl",
                    }
                )
            postprocessors.append({"key": "FFmpegMetadata"})
            if audio_tags == "with_cover":
                postprocessors.append({"key": "EmbedThumbnail"})

    if download_type == "thumbnail":
        opts["skip_download"] = True
        opts["writethumbnail"] = True
        postprocessors.append(
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        )

    if download_type == "captions":
        mode = _normalize_caption_mode(subtitle_mode)
        language = _normalize_subtitle_language(subtitle_language)
        opts["skip_download"] = True
        requested_subtitle_format = (format or "srt").lower()
        if requested_subtitle_format == "txt":
            requested_subtitle_format = "srt"
        opts["subtitlesformat"] = f"{requested_subtitle_format}/best"
        if requested_subtitle_format in ("srt", "vtt"):
            # subtitlesformat above is only a preference: if the extractor
            # doesn't natively offer this ext (e.g. YouTube has no native srt),
            # yt-dlp silently falls back to whatever it has. ffmpeg can only
            # convert to srt/vtt/ass/lrc, so only guarantee the requested
            # container for those; other formats stay best-effort.
            postprocessors.append(
                {
                    "key": "FFmpegSubtitlesConvertor",
                    "format": requested_subtitle_format,
                    "when": "before_dl",
                }
            )
        if mode == "manual_only":
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = False
            opts["subtitleslangs"] = [language]
        elif mode == "auto_only":
            opts["writesubtitles"] = False
            opts["writeautomaticsub"] = True
            # `-orig` captures common YouTube auto-sub tags. The plain language
            # fallback keeps behavior useful across other extractors.
            opts["subtitleslangs"] = [f"{language}-orig", language]
        elif mode == "prefer_auto":
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = [f"{language}-orig", language]
        else:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = [language, f"{language}-orig"]

    opts["postprocessors"] = postprocessors + (
        opts["postprocessors"] if "postprocessors" in opts else []
    )
    return opts
