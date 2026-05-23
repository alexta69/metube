import unittest

from aiohttp import web

from main import parse_clips_list
from ytdl import clip_batch_autoname_prefix, download_queue_key


class ParseClipsListTests(unittest.TestCase):
    def test_parses_mm_ss_ranges(self):
        clips = parse_clips_list([
            {'start': '1:30', 'end': '1:45'},
            {'start': '10:00', 'end': '10:05'},
        ])
        self.assertEqual(clips, [(90.0, 105.0), (600.0, 605.0)])

    def test_rejects_invalid_range(self):
        with self.assertRaises(web.HTTPBadRequest):
            parse_clips_list([{'start': '2:00', 'end': '1:00'}])


class BatchQueueKeyTests(unittest.TestCase):
    def test_merged_batch_key(self):
        url = 'https://example.com/v'
        ranges = [(10.0, 20.0), (30.0, 40.0)]
        key = download_queue_key(url, clip_ranges=ranges, merge_clips=True)
        self.assertIn('clipmerged', key)
        self.assertEqual(
            clip_batch_autoname_prefix(ranges, merge=True),
            'clipmerged_10-20_30-40',
        )


if __name__ == '__main__':
    unittest.main()
