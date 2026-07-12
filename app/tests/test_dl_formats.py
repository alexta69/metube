"""Tests for ``app.dl_formats`` format selectors and yt-dlp option mapping."""

from __future__ import annotations

import copy
import unittest

from app.dl_formats import (
    _normalize_caption_mode,
    _normalize_subtitle_language,
    get_format,
    get_opts,
    merge_ytdl_option_layers,
)


class DlFormatsTests(unittest.TestCase):
    def test_audio_unknown_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_format("audio", "auto", "invalid", "best")

    def test_wav_does_not_enable_thumbnail_postprocessing(self):
        opts = get_opts("audio", "auto", "wav", "best", {})
        self.assertNotIn("writethumbnail", opts)

    def test_mp3_enables_thumbnail_postprocessing(self):
        opts = get_opts("audio", "auto", "mp3", "best", {})
        self.assertTrue(opts.get("writethumbnail"))

    def test_custom_format_passthrough(self):
        self.assertEqual(get_format("video", "auto", "custom:bestvideo+bestaudio", "best"), "bestvideo+bestaudio")

    def test_thumbnail_and_captions_format_strings(self):
        self.assertEqual(get_format("thumbnail", "auto", "jpg", "best"), "bestaudio/best")
        self.assertEqual(get_format("captions", "auto", "srt", "best"), "bestaudio/best")

    def test_audio_formats(self):
        for fmt in ("m4a", "mp3", "opus", "wav", "flac"):
            with self.subTest(fmt=fmt):
                self.assertIn(f"ext={fmt}", get_format("audio", "auto", fmt, "best"))

    def test_video_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            get_format("video", "auto", "mkv", "best")

    def test_unknown_download_type_raises(self):
        with self.assertRaises(ValueError):
            get_format("unknown", "auto", "any", "best")

    def test_video_any_mp4_ios_with_height_quality(self):
        self.assertIn("height<=1080", get_format("video", "auto", "any", "1080"))
        self.assertNotIn("height<=", get_format("video", "auto", "any", "best"))
        self.assertNotIn("height<=", get_format("video", "auto", "any", "worst"))

    def test_video_codec_filters(self):
        self.assertIn("h264", get_format("video", "h264", "any", "best"))
        self.assertIn("hevc", get_format("video", "h265", "any", "best"))
        self.assertIn("av0?1", get_format("video", "av1", "any", "best"))
        self.assertIn("vp0?9", get_format("video", "vp9", "any", "best"))

    def test_video_mp4_includes_m4a_audio(self):
        s = get_format("video", "auto", "mp4", "720")
        self.assertIn("[ext=m4a]", s)

    def test_video_ios_selector_contains_avc_pattern(self):
        s = get_format("video", "auto", "ios", "best")
        self.assertIn("h26[45]", s)

    def test_get_opts_deepcopy_does_not_mutate_input(self):
        base = {"postprocessors": [{"key": "Existing"}]}
        orig = copy.deepcopy(base)
        get_opts("audio", "auto", "mp3", "best", base)
        self.assertEqual(base, orig)

    def test_get_opts_audio_m4a_postprocessors(self):
        opts = get_opts("audio", "auto", "m4a", "best", {})
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertIn("FFmpegExtractAudio", keys)

    def test_get_opts_audio_mp3_quality_not_best(self):
        opts = get_opts("audio", "auto", "mp3", "192", {})
        ext = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegExtractAudio")
        self.assertEqual(ext["preferredquality"], "192")

    def test_get_opts_thumbnail_skip_download(self):
        opts = get_opts("thumbnail", "auto", "jpg", "best", {})
        self.assertTrue(opts.get("skip_download"))
        self.assertTrue(opts.get("writethumbnail"))

    def test_get_opts_captions_manual_only(self):
        opts = get_opts(
            "captions", "auto", "vtt", "best", {}, subtitle_language="fr", subtitle_mode="manual_only"
        )
        self.assertTrue(opts.get("writesubtitles"))
        self.assertFalse(opts.get("writeautomaticsub"))
        self.assertEqual(opts["subtitleslangs"], ["fr"])

    def test_get_opts_captions_auto_only(self):
        opts = get_opts(
            "captions", "auto", "srt", "best", {}, subtitle_language="de", subtitle_mode="auto_only"
        )
        self.assertFalse(opts.get("writesubtitles"))
        self.assertTrue(opts.get("writeautomaticsub"))
        self.assertEqual(opts["subtitleslangs"], ["de-orig", "de"])

    def test_get_opts_captions_prefer_auto(self):
        opts = get_opts(
            "captions", "auto", "srt", "best", {}, subtitle_language="es", subtitle_mode="prefer_auto"
        )
        self.assertTrue(opts.get("writesubtitles"))
        self.assertTrue(opts.get("writeautomaticsub"))
        self.assertEqual(opts["subtitleslangs"], ["es-orig", "es"])

    def test_get_opts_captions_prefer_manual_default_branch(self):
        opts = get_opts(
            "captions", "auto", "srt", "best", {}, subtitle_language="it", subtitle_mode="prefer_manual"
        )
        self.assertEqual(opts["subtitleslangs"], ["it", "it-orig"])

    def test_get_opts_captions_txt_maps_to_srt_format(self):
        opts = get_opts("captions", "auto", "txt", "best", {})
        self.assertEqual(opts["subtitlesformat"], "srt/best")
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertIn("FFmpegSubtitlesConvertor", keys)
        convertor = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegSubtitlesConvertor")
        self.assertEqual(convertor["format"], "srt")

    def test_get_opts_captions_srt_guarantees_convertor(self):
        opts = get_opts("captions", "auto", "srt", "best", {})
        self.assertEqual(opts["subtitlesformat"], "srt/best")
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertIn("FFmpegSubtitlesConvertor", keys)

    def test_get_opts_captions_vtt_guarantees_convertor(self):
        opts = get_opts("captions", "auto", "vtt", "best", {})
        self.assertEqual(opts["subtitlesformat"], "vtt/best")
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertIn("FFmpegSubtitlesConvertor", keys)
        convertor = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegSubtitlesConvertor")
        self.assertEqual(convertor["format"], "vtt")

    def test_get_opts_captions_ttml_has_no_convertor(self):
        opts = get_opts("captions", "auto", "ttml", "best", {})
        self.assertEqual(opts["subtitlesformat"], "ttml/best")
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertNotIn("FFmpegSubtitlesConvertor", keys)

    def test_get_opts_merges_existing_postprocessors(self):
        opts = get_opts("audio", "auto", "opus", "best", {"postprocessors": [{"key": "SponsorBlock"}]})
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertIn("SponsorBlock", keys)
        self.assertIn("FFmpegExtractAudio", keys)

    def test_normalize_caption_mode_invalid_defaults(self):
        self.assertEqual(_normalize_caption_mode(""), "prefer_manual")
        self.assertEqual(_normalize_caption_mode("not_a_mode"), "prefer_manual")

    def test_normalize_subtitle_language_empty_defaults_en(self):
        self.assertEqual(_normalize_subtitle_language(""), "en")
        self.assertEqual(_normalize_subtitle_language("  "), "en")


class MergeYtdlOptionLayersTests(unittest.TestCase):
    def test_presets_applied_in_order_then_overrides(self):
        presets_config = {
            "a": {"x": 1, "y": 1},
            "b": {"y": 2, "z": 2},
        }
        merged = merge_ytdl_option_layers(["a", "b"], {"z": 3, "w": 4}, presets_config)
        # b overrides a's y; explicit overrides win over presets.
        self.assertEqual(merged, {"x": 1, "y": 2, "z": 3, "w": 4})

    def test_no_base_options_included(self):
        # The helper only produces the preset/override layer, never base opts.
        self.assertEqual(merge_ytdl_option_layers(None, None, {}), {})

    def test_unknown_preset_names_ignored(self):
        self.assertEqual(merge_ytdl_option_layers(["missing"], {"a": 1}, {}), {"a": 1})


if __name__ == "__main__":
    unittest.main()
