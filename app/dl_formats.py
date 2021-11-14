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
    final_fmt = ""

    if format.startswith("custom:"):
        final_fmt = format[7:]
    else:
        final_fmt = _get_final_fmt(format, quality)

    return final_fmt


def get_opts(format: str, quality: str, ytdl_opts: dict) -> dict:
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
    if "postprocessors" not in ytdl_opts:
        ytdl_opts["postprocessors"] = []

    if format == "mp3":
        extra_args = {}
        if quality != "best":
            extra_args = {"preferredquality": quality}
        ytdl_opts["postprocessors"].append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", **extra_args},
        )

    return ytdl_opts


def _get_audio_fmt(quality: str) -> str:
    if quality == "best" or quality in ("128", "192", "320"):
        audio_fmt = "bestaudio/best"
        # Audio quality needs to be set post-download, set in opts
    else:
        raise Exception(f"Unknown quality {quality}")

    return audio_fmt


def _get_video_res(quality: str) -> str:
    if quality in ("best", "audio"):
        video_fmt = ""
    elif quality in ("1440", "1080", "720", "480"):
        video_fmt = f"[height<={quality}]"
    else:
        raise Exception(f"Unknown quality {quality}")

    return video_fmt


def _get_final_fmt(format: str, quality: str) -> str:
    vfmt, afmt, vres = "", "", ""

    if format in ("mp4", "any"):
        # video {res} {vfmt} + audio {afmt} {res} {vfmt}
        if format == "mp4":
            vfmt, afmt = "[ext=mp4]", "[ext=m4a]"

        if quality == "audio":
            final_fmt = "bestaudio/best"
        else:
            vres = _get_video_res(quality)
            combo = vres + vfmt
            final_fmt = f"bestvideo{combo}+bestaudio{afmt}/best{combo}"
    elif format == "mp3":
        final_fmt = _get_audio_fmt(quality)
    else:
        raise Exception(f"Unkown format {format}")

    return final_fmt
