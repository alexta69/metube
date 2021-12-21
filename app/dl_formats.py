import copy

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

    if format == "mp3":
        # Audio quality needs to be set post-download, set in opts
        return "bestaudio/best"

    if format in ("mp4", "any"):
        if quality == "audio":
            return "bestaudio/best"

        # video {res} {vfmt} + audio {afmt} {res} {vfmt}
        vfmt, afmt = ("[ext=mp4]", "[ext=m4a]") if format == "mp4" else ("", "")
        vres = f"[height<={quality}]" if quality != "best" else ""
        vcombo = vres + vfmt

        return f"bestvideo{vcombo}+bestaudio{afmt}/best{vcombo}"

    raise Exception(f"Unkown format {format}")


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
    
    opts = copy.deepcopy(ytdl_opts)

    if "postprocessors" not in opts:
        opts["postprocessors"] = []

    if format == "mp3":
        opts["postprocessors"].append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": 0 if quality == "best" else quality,
        })
        opts["writethumbnail"] = True
        opts["postprocessors"].append({"key": "FFmpegMetadata"})
        opts["postprocessors"].append({"key": "EmbedThumbnail"})
    
    return opts
