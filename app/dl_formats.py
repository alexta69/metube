import copy

AUDIO_FORMATS = ("m4a", "mp3", "opus", "wav", "flac")
CAPTION_MODES = ("auto_only", "manual_only", "prefer_manual", "prefer_auto")

CODEC_FILTER_MAP = {
    'h264': "[vcodec~='^(h264|avc)']",
    'h265': "[vcodec~='^(h265|hevc)']",
    'av1':  "[vcodec~='^av0?1']",
    'vp9':  "[vcodec~='^vp0?9']",
}

# Common language variant suffixes that yt-dlp may encounter on YouTube and
# other platforms.  When a user requests "en" we also try "en-GB", "en-US",
# etc. so that a request isn't silently skipped when only a regional variant
# exists.  yt-dlp processes the list in order and picks the first match.
_LANGUAGE_REGION_VARIANTS = {
    "en": ("US", "GB", "AU", "CA", "IN", "NZ", "IE", "ZA"),
    "zh": ("CN", "TW", "HK", "SG"),
    "pt": ("BR", "PT"),
    "es": ("ES", "MX", "AR", "CO", "CL", "PE", "VE"),
    "fr": ("FR", "CA", "BE", "CH"),
    "de": ("DE", "AT", "CH"),
    "ar": ("SA", "AE", "EG", "MA", "DZ"),
    "nl": ("NL", "BE"),
    "ro": ("RO", "MD"),
    "ms": ("MY", "BN", "SG"),
    "it": ("IT", "SM"),
    "ja": (),
    "ko": (),
    "hi": (),
    "th": (),
    "vi": (),
    "id": (),
    "pl": (),
    "uk": (),
    "ru": ("RU", "BY", "KZ", "UA"),
    "cs": (),
    "sv": ("SE", "FI"),
    "da": ("DK",),
    "no": ("NO", "NB", "NN"),
    "fi": (),
    "tr": (),
    "el": ("GR", "CY"),
    "he": (),
    "hu": (),
    "bn": ("BD", "IN"),
    "ta": ("IN", "SG", "LK", "MY"),
}


def _subtitle_lang_list(language: str, include_orig: bool = False) -> list[str]:
    """Build a prioritised list of subtitle language codes for yt-dlp.

    Starts with the exact language, then appends common regional variants
    (e.g. ``en`` → ``en-US, en-GB, en-AU, …``).  ``include_orig`` adds the
    ``<lang>-orig`` tag that YouTube uses for original-language auto-captions.

    Handles user input that already contains a region or script subtag (e.g.
    ``zh-Hans``, ``pt-BR``): extracts the base language (``zh``, ``pt``) so
    regional variants for that base language are still included as fallbacks.
    """
    langs = [language]
    # Extract base language (e.g. "zh-Hans" → "zh", "en-GB" → "en")
    base = language.split('-')[0]
    # If user provided a qualified tag, also include the base form as fallback
    if base != language:
        langs.append(base)
    variants = _LANGUAGE_REGION_VARIANTS.get(base)
    if variants:
        for region in variants:
            variant = f"{base}-{region}"
            if variant not in langs:
                langs.append(variant)
    if include_orig:
        orig_tag = f"{base}-orig"
        if orig_tag not in langs:
            langs.append(orig_tag)
    return langs


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
        return format[7:]

    if download_type == "thumbnail":
        return "bestaudio/best"

    if download_type == "captions":
        return "bestaudio/best"

    if download_type == "audio":
        if format not in AUDIO_FORMATS:
            raise ValueError(f"Unknown audio format {format}")
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
) -> dict:
    """
    Returns extra yt-dlp options/postprocessors.

    Args:
      download_type (str): selected content type
      codec (str): selected codec (unused currently, kept for API consistency)
      format (str): selected format/profile
      quality (str): selected quality
      ytdl_opts (dict): current options selected

    Returns:
      dict: extended options
    """
    download_type = (download_type or "video").strip().lower()
    format = (format or "any").strip().lower()
    opts = copy.deepcopy(ytdl_opts)

    postprocessors = []

    if download_type == "audio":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": format,
                "preferredquality": 0 if quality == "best" else quality,
            }
        )

        if format != "wav" and "writethumbnail" not in opts:
            opts["writethumbnail"] = True
            postprocessors.append(
                {
                    "key": "FFmpegThumbnailsConvertor",
                    "format": "jpg",
                    "when": "before_dl",
                }
            )
            postprocessors.append({"key": "FFmpegMetadata"})
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
        opts["subtitlesformat"] = requested_subtitle_format
        if mode == "manual_only":
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = False
            opts["subtitleslangs"] = _subtitle_lang_list(language)
        elif mode == "auto_only":
            opts["writesubtitles"] = False
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = _subtitle_lang_list(language, include_orig=True)
        elif mode == "prefer_auto":
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = _subtitle_lang_list(language, include_orig=True)
        else:
            # prefer_manual (default)
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = _subtitle_lang_list(language, include_orig=True)

    opts["postprocessors"] = postprocessors + (
        opts["postprocessors"] if "postprocessors" in opts else []
    )
    return opts
