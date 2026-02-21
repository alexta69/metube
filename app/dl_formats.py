import copy

AUDIO_FORMATS = ("m4a", "mp3", "opus", "wav", "flac")
CAPTION_MODES = ("auto_only", "manual_only", "prefer_manual", "prefer_auto")


def _normalize_caption_mode(mode: str) -> str:
    mode = (mode or "").strip()
    return mode if mode in CAPTION_MODES else "prefer_manual"


def _normalize_subtitle_language(language: str) -> str:
    language = (language or "").strip()
    return language or "en"


def get_format(format: str, quality: str) -> str:
    """
    Returns format for download

    Args:
      format (str): format selected
      quality (str): quality selected

    Raises:
      Exception: unknown quality, unknown format

    Returns:
      dl_format: Formatted download string
    """
    format = format or "any"

    if format.startswith("custom:"):
        return format[7:]

    if format == "thumbnail":
        # Quality is irrelevant in this case since we skip the download
        return "bestaudio/best"

    if format == "captions":
        # Quality is irrelevant in this case since we skip the download
        return "bestaudio/best"

    if format in AUDIO_FORMATS:
        # Audio quality needs to be set post-download, set in opts
        return f"bestaudio[ext={format}]/bestaudio/best"

    if format in ("mp4", "any"):
        if quality == "audio":
            return "bestaudio/best"
        # video {res} {vfmt} + audio {afmt} {res} {vfmt}
        vfmt, afmt = ("[ext=mp4]", "[ext=m4a]") if format == "mp4" else ("", "")
        vres = f"[height<={quality}]" if quality not in ("best", "best_ios", "worst") else ""
        vcombo = vres + vfmt

        if quality == "best_ios":
            # iOS has strict requirements for video files, requiring h264 or h265
            # video codec and aac audio codec in MP4 container. This format string
            # attempts to get the fully compatible formats first, then the h264/h265
            # video codec with any M4A audio codec (because audio is faster to
            # convert if needed), and falls back to getting the best available MP4
            # file.
            return f"bestvideo[vcodec~='^((he|a)vc|h26[45])']{vres}+bestaudio[acodec=aac]/bestvideo[vcodec~='^((he|a)vc|h26[45])']{vres}+bestaudio{afmt}/bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"
        return f"bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"

    raise Exception(f"Unkown format {format}")


def get_opts(
    format: str,
    quality: str,
    ytdl_opts: dict,
    subtitle_format: str = "srt",
    subtitle_language: str = "en",
    subtitle_mode: str = "prefer_manual",
) -> dict:
    """
    Returns extra download options
    Mostly postprocessing options

    Args:
      format (str): format selected
      quality (str): quality of format selected (needed for some formats)
      ytdl_opts (dict): current options selected

    Returns:
      ytdl_opts: Extra options
    """

    opts = copy.deepcopy(ytdl_opts)

    postprocessors = []

    if format in AUDIO_FORMATS:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": format,
                "preferredquality": 0 if quality == "best" else quality,
            }
        )

        # Audio formats without thumbnail
        if format not in ("wav") and "writethumbnail" not in opts:
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

    if format == "thumbnail":
        opts["skip_download"] = True
        opts["writethumbnail"] = True
        postprocessors.append(
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        )

    if format == "captions":
        mode = _normalize_caption_mode(subtitle_mode)
        language = _normalize_subtitle_language(subtitle_language)
        opts["skip_download"] = True
        requested_subtitle_format = (subtitle_format or "srt").lower()
        # txt is a derived, non-timed format produced from SRT after download.
        if requested_subtitle_format == "txt":
            requested_subtitle_format = "srt"
        opts["subtitlesformat"] = requested_subtitle_format
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
