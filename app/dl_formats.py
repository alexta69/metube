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
    audio_fmt = ""
    video_fmt = ""
    final_fmt = ""

    if format.startswith("custom: "):
        final_fmt = format[7:]
    elif format == "any":
        final_fmt = "bv*+ba/b"
    elif format == "mp3":
        audio_fmt = _get_audio_fmt(quality)
    elif format == "mp4":
        audio_fmt = "ba/b"
        video_fmt = _get_video_fmt(quality)
    else:
        raise Exception(f"Unknown format {format}")

    if not final_fmt:
        final_fmt = video_fmt + audio_fmt

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

    elif format == "mp4":
        ytdl_opts["merge_output_format"] = "mp4"

    return ytdl_opts


def _get_audio_fmt(quality: str) -> str:
    if quality == "best" or quality in ("128", "192", "320"):
        audio_fmt = "ba/b"
        # Audio quality needs to be set post-download, set in opts
    else:
        raise Exception(f"Unknown quality {quality}")

    return audio_fmt


def _get_video_fmt(quality: str) -> str:
    if quality == "best":
        video_fmt = "bv*+"
    elif quality in ("1440", "1080", "720", "480"):
        video_fmt = f"bv[height<={quality}]+"
    else:
        raise Exception(f"Unknown quality {quality}")

    return video_fmt
