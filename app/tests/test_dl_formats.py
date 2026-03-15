import unittest

from app.dl_formats import get_format, get_opts


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


if __name__ == "__main__":
    unittest.main()
