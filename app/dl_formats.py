import copy

AUDIO_FORMATS = ("m4a", "mp3", "opus", "wav")

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

    if format in AUDIO_FORMATS:
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

    postprocessors = []

    if format in AUDIO_FORMATS:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": format,
            "preferredquality": 0 if quality == "best" else quality,
        })

        #Audio formats without thumbnail
        if format not in ("wav") and "writethumbnail" not in opts:
            opts["writethumbnail"] = True
            postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
            postprocessors.append({"key": "FFmpegMetadata"})
            postprocessors.append({"key": "EmbedThumbnail"})
    
    if format == "thumbnail":
        opts["skip_download"] = True
        opts["writethumbnail"] = True
        postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
    
    opts["postprocessors"] = postprocessors + (opts["postprocessors"] if "postprocessors" in opts else [])
    return opts
