import unittest

from ytdl import clip_autoname_prefix, download_queue_key, merge_custom_name_prefix


class ClipQueueKeyTests(unittest.TestCase):
    def test_same_url_different_clips_get_different_keys(self):
        url = "https://www.youtube.com/watch?v=abc"
        k1 = download_queue_key(url, 10.0, 20.0)
        k2 = download_queue_key(url, 30.0, 40.0)
        self.assertNotEqual(k1, k2)
        self.assertTrue(k1.startswith(url))
        self.assertTrue(k2.startswith(url))

    def test_full_video_uses_url_only(self):
        url = "https://example.com/v"
        self.assertEqual(download_queue_key(url), url)

    def test_merge_custom_name_prefix_adds_clip_suffix(self):
        self.assertEqual(
            merge_custom_name_prefix("", 90.0, 120.0),
            "clip_90-120",
        )
        self.assertEqual(
            merge_custom_name_prefix("mine", 1.0, 5.0),
            "mine_clip_1-5",
        )

    def test_clip_autoname_prefix_empty_without_bounds(self):
        self.assertEqual(clip_autoname_prefix(), "")


if __name__ == "__main__":
    unittest.main()
